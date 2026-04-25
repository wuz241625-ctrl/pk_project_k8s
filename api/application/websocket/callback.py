import json
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from aiomysql import DictCursor

from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader


def _is_easypaisa_payment(payment):
    return (
        str((payment or {}).get('bank_type_id') or '') == '97'
        or str((payment or {}).get('bank_type') or '') == '97'
    )


async def _requeue_df_if_online(self, payment_id):
    payment = await self.get_result_by_condition(
        'payment',
        ['bank_type', 'bank_type_id'],
        {'id': payment_id},
    )
    if not payment:
        await self.redis.lrem('payment_active_df', 0, payment_id)
        return False
    bank_type = 97 if _is_easypaisa_payment(payment) else (payment or {}).get('bank_type_id') or (payment or {}).get('bank_type')
    reader = EasyPaisaRuntimeReader(self.redis)
    return await reader.requeue_df_if_online(payment_id, bank_type=bank_type)


# 代收确认
async def success_ds(self, data):
    condition = 'utr'
    if "code" in data.keys() and data['code']:
        if data['bank_name'] == 'indusind' and len(data['code']) == 4:
            condition = 'left(auth_code,4)'
        elif data['bank_name'] == 'phonepe' and len(data['code']) == 5:
            condition = 'auth_code'
        elif len(data['code']) == 5:
            condition = 'auth_code'
    amount = Decimal(data['amount'])
    original_amount = amount  # 保存原始小数金额用于清理
    has_decimal = amount % 1 != 0  # 判断金额是否为小数
    
    # 小数点回调超时检查
    if has_decimal and 'payment_id' in data:
        try:
            # 检查 payment_release_time 中的过期时间
            release_key = f"{data['payment_id']}:{original_amount:.2f}"
            expire_time_str = await self.redis.hget('payment_release_time', release_key)
            
            if expire_time_str:
                expire_time = float(expire_time_str.decode() if isinstance(expire_time_str, bytes) else expire_time_str)
                current_time = time.time()
                
                if current_time > expire_time:
                    # 超时了，使用统一的清理函数
                    try:
                        from application.pay.pay import Pay
                        pay_instance = Pay()
                        pay_instance.redis = self.redis
                        pay_instance.logger = self.logger
                        # 调用统一的清理函数，传入超时清理原因
                        await pay_instance.cleanup_decimal_callback_on_success(data['payment_id'], original_amount, "超时回调")
                        self.logger.info(f'小数点回调超时，已使用统一清理函数完成清理: payment_id={data["payment_id"]}, amount={original_amount}')
                    except Exception as cleanup_error:
                        self.logger.exception(f'小数点回调超时清理失败: {cleanup_error}')
                    
                    self.logger.warning(f'小数点回调超时: payment_id={data["payment_id"]}, amount={original_amount}, 当前时间={current_time}, 过期时间={expire_time}')
                    return dict(code=99, msg='Decimal callback timeout')
                else:
                    self.logger.info(f'小数点回调时间有效: payment_id={data["payment_id"]}, amount={original_amount}, 剩余时间={expire_time - current_time:.2f}秒')
            else:
                self.logger.warning(f'未找到小数点回调释放时间记录: payment_id={data["payment_id"]}, amount={original_amount}')
                return dict(code=99, msg='Decimal callback release time not found')
                
        except Exception as e:
            self.logger.exception(f'检查小数点回调超时失败: {e}')
            return dict(code=99, msg='Decimal callback timeout check failed')
    
    # 根据确认码或UTR查找订单
    sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) and 
                            date_add(time_create, interval 8 minute) > now() order by id limit 1""".format(condition)
    # 商户代理费率
    sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant 
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join 
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
    # 码商代理费率
    sql_select_rates_partner = """select rates from channel where code=%s"""
    # 更新系统余额
    sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
    # 更新订单
    # sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,payment_id=%s,
                        # utr=%s,time_success=%s,status=3,upi=%s where code=%s and status in (-1,1,2) limit 1"""

    sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,payment_id=%s,
                            utr=%s,time_success=%s,status=3,upi=%s,tax=%s,trans_id=%s where code=%s and status in (-1,1,2) limit 1"""

    # 根据收款资料id查询
    sql_select_payment = """select * from payment where id=%s order by id limit 1"""

    # _order = await self.query(sql_select_order, *(Decimal(data['amount']), data['code'] if condition != 'utr' else data['utr']))
    pakistan_flag = True
    if has_decimal or pakistan_flag:
        self.logger.info(f"[订单匹配] 金额 {amount} 含小数，使用更严格规则匹配订单（按 payment_id + 时间）")
        # 检查传入的数据中是否有 trans_id，并获取其值
        input_trans_id = data.get('trans_id')

        # 动态构建 SQL 语句的基础部分
        sql_select_order = """
            SELECT * FROM orders_ds 
            WHERE amount=%s AND payment_id=%s AND utr=%s
        """
        params = [amount, data['payment_id'], data['utr']]

        # 根据传入的 trans_id 是否存在，动态添加 CASE WHEN 条件
        if input_trans_id:
            # 如果传入的 trans_id 不为空，则添加 CASE WHEN 逻辑
            sql_select_order += " AND (CASE WHEN trans_id IS NOT NULL AND trans_id != '' THEN trans_id = %s ELSE 1=1 END)"
            params.append(input_trans_id)

        # 添加其他固定的查询条件
        sql_select_order += """
            AND status IN (-1,1,2) 
            AND date_add(time_create, interval 8 minute) > now()
            ORDER BY id DESC LIMIT 1
        """

        self.logger.info(f"[订单匹配11] 执行 SQL: {sql_select_order.strip()} 参数: {params}")

        _order = await self.query(sql_select_order, *params)

        if not _order:
            self.logger.warning('utr:{} Not Order found. payment_id={}'.format(data['utr'], data['payment_id']))
            return dict(code=99, msg='Order not found')

    else:
        self.logger.info(f"[订单匹配] 金额 {amount} 为整数，使用默认规则（{condition} 匹配）")
        self.logger.info(f"[订单匹配] 执行 SQL: {sql_select_order.strip()} 参数: 金额={amount}, 匹配字段={condition}, 值={data['trans_id'] if condition != 'utr' else data['utr']}")
        _order = await self.query(sql_select_order,
            amount, data['trans_id'] if condition != 'utr' else data['utr'])
    if not _order:
        if not condition == 'utr': # 如果查询不到，重新按utr查询
            self.logger.warning('utr:{}Not Order not found'.format(data['utr']))
            sql_select_order = """select * from orders_ds where amount=%s and {}=%s and utr=%s and trans_id=%s and status in (-1,1,2) and 
                                    date_add(time_create, interval 8 minute) > now() order by id limit 1""".format('utr')
            _order = await self.query(sql_select_order, *(Decimal(data['amount']), data['utr'], data['utr'], data['trans_id']))
        if not _order:
            self.logger.warning('utr:{}Not Order not found k2'.format(data['utr']))
            return dict(code=99, msg='Order not found')
    _payment = await self.query(sql_select_payment, self.qr_id)
    if not _payment:
        return dict(code=99, msg='Payment not found')
    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'order_success_busy_{code}'.format(code=_order[0]['code'])
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('utr:{utr}Do not operate frequently {code}'.format(utr=data['utr'], code=_order[0]['code']))
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                amount = Decimal(data['amount'])
                partner_id = int(self.partner_id)
                # 查找订单
                if has_decimal or pakistan_flag:
                    self.logger.info(f"[订单匹配] 金额 {amount} 含小数，使用更严格规则匹配订单（按 payment_id + 时间）")
                    # 检查传入的数据中是否有 trans_id，并获取其值
                    input_trans_id = data.get('trans_id')

                    # 动态构建 SQL 语句的基础部分
                    sql_select_order = """
                        SELECT * FROM orders_ds 
                        WHERE amount=%s AND payment_id=%s AND utr=%s
                    """
                    params = [amount, data['payment_id'], data['utr']]

                    # 根据传入的 trans_id 是否存在，动态添加 CASE WHEN 条件
                    if input_trans_id:
                        # 如果传入的 trans_id 不为空，则添加 CASE WHEN 逻辑
                        sql_select_order += " AND (CASE WHEN trans_id IS NOT NULL AND trans_id != '' THEN trans_id = %s ELSE 1=1 END)"
                        params.append(input_trans_id)

                    sql_select_order += """
                        AND status IN (-1,1,2) 
                        AND date_add(time_create, interval 8 minute) > now() 
                        ORDER BY id DESC LIMIT 1
                    """

                    self.logger.info(f"[订单匹配22] 执行 SQL: {sql_select_order.strip()} 参数: {params}")

                    # 使用 cur.execute 方法执行查询，并将动态构建的参数列表转换为元组
                    if not await cur.execute(sql_select_order, tuple(params)):
                        self.logger.warning('utr:{} Not Order found. payment_id={}'.format(data['utr'], data['payment_id']))
                        return dict(code=99, msg='Order not found')
                else:
                    if not await cur.execute(sql_select_order, (amount, data['code'] if condition != 'utr' else data['utr'])):
                        if not condition == 'utr':  # 如果查询不到，重新按utr查询
                            sql_select_order = """select * from orders_ds where amount=%s and {}=%s and utr=%s and status in (-1,1,2) and 
                                                    date_add(time_create, interval 8 minute) > now() order by id limit 1""".format('utr')
                            if not await cur.execute(sql_select_order, (amount, data['utr'], data['utr'])):
                                self.logger.warning('utr:{}Not Order not found2'.format(data['utr']))
                                return dict(code=99, msg='Order not found')
                        else:
                            self.logger.warning('utr:{}Not Order not found'.format(data['utr']))
                            return dict(code=99, msg='Order not found')
                order = (await cur.fetchall())[0]
                code = order['code']

                # ----------------- 交易ID重复校验逻辑 -----------------
                sql_check_trans_id = """
                    SELECT code FROM orders_ds WHERE trans_id=%s AND id != %s LIMIT 1
                """
                # 这里的 _order[0]['id'] 是当前找到的订单的ID
                existing_order = await self.query(sql_check_trans_id, data['trans_id'], order['id'])
                
                # 打印即将执行的查询日志，包含SQL和参数
                self.logger.info(
                    f"新增：交易ID重复校验查询 | SQL: {sql_check_trans_id.strip()} | 参数: ({data['trans_id']}, {order['id']})"
                )
                
                # 如果查询结果不为空，则说明有其他订单已使用此交易ID
                if existing_order:
                    self.logger.warning(f"交易ID {data['trans_id']} 已被其他订单使用。冲突订单号: {existing_order[0]['code']}")
                    # 返回一个错误提示
                    return dict(code=99, msg='交易ID已使用')

                amount = order['original_amount'] or amount
                # 打印中文日志
                self.logger.info(f"code: {code}, 原始充值金额: {amount}")

                # 去掉小数部分（向下取整）
                amount = amount.to_integral_value(rounding=ROUND_DOWN)

                # 打印中文日志
                self.logger.info(f"code: {code}, 去除小数部分后金额: {amount}")

                # 补扣码商(非自身订单、过期订单)
                self.logger.info('UTR:{} - 无法扣除合作伙伴余额。合作伙伴ID: {}, 订单状态: {}'.format(data['utr'], partner_id, order['status']))
                if not order['partner_id'] == partner_id or order['status'] == -1:
                    if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0, ):
                        self.logger.warning('utr:{}Failed to deduct partner balance'.format(data['utr']))
                        return dict(code=99, msg='Failed to deduct partner balance')
                # 非自身订单并且未过期退款给旧码商
                if not order['partner_id'] == partner_id and not order['status'] == -1:
                    if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount, code, 0):
                        self.logger.warning('utr:{}Failed to add old partner balance'.format(data['utr']))
                        return dict(code=99, msg='Failed to add old partner balance')
                # 增加商户余额
                self.logger.info('UTR:{} - 尝试扣除商户余额。商户ID: {}, 实际支付金额: {}, 错误码: {}'.format(
                                    data['utr'], order['merchant_id'], order['realpay'], code))
                if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], code, 0):
                    self.logger.warning('utr:{}Failed to add merchant balance'.format(data['utr']))
                    return dict(code=99, msg='Failed to add merchant balance')
                # 商户代理费用
                earn_merchant = Decimal(0)
                if order['earn_merchant'] > 0:
                    if not await cur.execute(sql_select_rates_merchant, (order['merchant_id'], order['channel_code'])):
                        await conn.rollback()
                        self.logger.warning('utr:{}Not found merchant agent'.format(data['utr']))
                        return dict(code=99, msg='Not found merchant agent')
                    merchant_rates = (await cur.fetchall())
                    for k, v in enumerate(merchant_rates):
                        if not k == 0 and v['rate']:
                            _amount = amount * (merchant_rates[k-1]['rate'] - v['rate'])
                            if _amount < 0:
                                await conn.rollback()
                                self.logger.warning('utr:{}Merchant agent rate error'.format(data['utr']))
                                return dict(code=99, msg='Merchant agent rate error')
                            if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                self.logger.warning('utr:{}Failed to add merchant agent balance'.format(data['utr']))
                                return dict(code=99, msg='Failed to add merchant agent balance')
                            earn_merchant += _amount
                # 增加码商佣金
                self.logger.info('UTR:{} - 尝试扣除合作伙伴余额。合作伙伴ID: {}, 合作伙伴自有余额: {}, 错误码: {}'.format(
                        data['utr'], partner_id, order['earn_partner_self'], code))
                if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code, 3):
                    await conn.rollback()
                    self.logger.warning('utr:{}Failed to add partner balance'.format(data['utr']))
                    return dict(code=99, msg='Failed to add partner balance')

                # 增加码商代理佣金
                earn_partner = order['earn_partner_self']
                if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                    self.logger.warning('utr:{}Partner rates error'.format(data['utr']))
                    return dict(code=99, msg='Partner rates error')
                rates = (await cur.fetchall())[0]['rates'].split(',')
                _partner_id = partner_id
                for i in range(len(rates)):
                    partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                    if not partner['pid']:
                        break
                    _partner_id = partner['pid']
                    _amount = amount * Decimal(rates[i])
                    if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                        self.logger.warning('utr:{}Failed to add partner agent balance'.format(data['utr']))
                        return dict(code=99, msg='Failed to add partner agent balance')
                    earn_partner += _amount
                # 系统盈利
                earn_system = order['poundage'] - earn_merchant - earn_partner
                self.logger.info('UTR:{} - 计算系统收入。手续费: {}, 商户收入: {}, 合作伙伴收入: {}, 系统收入: {}'.format(
                                data['utr'], order['poundage'], earn_merchant, earn_partner, earn_system))
                if earn_system < 0:
                    await conn.rollback()
                    self.logger.warning('utr:{}Rate exception'.format(data['utr']))
                    return dict(code=99, msg='Rate exception')
                # 修改卡系统余额
                self.logger.info('UTR:{} - 执行更新支付操作。SQL: {}, 参数: (amount: {}, qr_id: {})'.format(
                                data['utr'], sql_update_payment, amount, self.qr_id))
                if not await cur.execute(sql_update_payment, (amount, self.qr_id)):
                    await conn.rollback()
                    self.logger.warning('utr:{}Update payment system balance error'.format(data['utr']))
                    return dict(code=99, msg='Update payment system balance error')
                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                tax_amount = Decimal(data.get('fee', 0))
                self.logger.info('UTR:{} - 执行更新订单操作。SQL: {}, 参数: (earn_merchant: {}, earn_partner: {}, earn_system: {}, partner_id: {}, qr_id: {}, utr: {}, time_now: {}, upi: {}, tax_amount: {}, code: {})'.format(
                                data['utr'], sql_update_order, earn_merchant, earn_partner, earn_system, partner_id, self.qr_id, data['utr'], time_now, _payment[0]['upi'], tax_amount, code))
                if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id,
                                                            self.qr_id, data['utr'], time_now, _payment[0]['upi'], tax_amount, data['trans_id'], code)):
                    await conn.rollback()
                    self.logger.warning('utr:{}Update order error'.format(data['utr']))
                    return dict(code=99, msg='Update order error')
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                await conn.rollback()
                return dict(code=99, msg='Order exception')
            else:
                await conn.commit()
                
                # 小数点回调成功后的清理工作
                if has_decimal:
                    try:
                        # 调用统一的清理函数，使用原始金额（包含小数部分）
                        from application.pay.pay import Pay
                        pay_instance = Pay()
                        pay_instance.redis = self.redis
                        pay_instance.logger = self.logger
                        # 使用原始的小数金额，而不是处理后的整数金额
                        await pay_instance.cleanup_decimal_callback_on_success(self.qr_id, original_amount, "成功回调")
                    except Exception as cleanup_error:
                        self.logger.exception(f'小数点回调清理失败: {cleanup_error}')
                
                # 加入回调
                self.logger.info('UTR:{} - 正在发布订单通知到 Redis。频道: "order_notify", 消息内容: {}'.format(data['utr'], code))
                await self.redis.publish('order_notify', code)
                return dict(code=100, msg='Callback Success:{}'.format(code), order=code)


# 代付确认
async def success_df(self, data):
    self.logger.info(f'data:{data}')
    amount = abs(Decimal(data['amount']))
    source_utr = data['trans_id']
    final_utr = data['utr']
    if data['bank_name'] == 'freecharge':
        condition = '  and ifsc=%s and right(payment_account,4)=%s and partner_id=%s'
        value = (amount, data['ifsc'], data['code'], data['partner_id'])
    elif data['bank_name'] == 'mobi':
        condition = ' and payment_account=%s and partner_id=%s'
        value = (amount, data['code'], data['partner_id'])
    elif data['bank_name'] == 'AU C':
        condition = ' and ifsc=%s and right(payment_account,4)=%s and partner_id=%s'
        value = (amount, data['ifsc'], data['code'][-4:], data['partner_id'])
    elif data['bank_name'] == 'NAGERCOIL ENBL':
        condition = ' and ifsc=%s and payment_account=%s and partner_id=%s'
        value = (amount, data['ifsc'], data['code'], data['partner_id'])
    elif data['bank_name'] == 'feb':
        condition = ' and ifsc=%s  and payment_id=%s'
        value = (amount, data['ifsc'], data['payment_id'])
    elif data['bank_name'] in ['jio', 'indus']:
        condition = ' and ifsc=%s and payment_account=%s and payment_id=%s'
        value = (amount, data['ifsc'], data['account'], data['payment_id'])
    elif data['bank_name'] == 'maha':
        condition = ' and code=%s and partner_id=%s'
        value = (amount, data['code'], data['partner_id'])
    # 对于 pakistan 银行：使用回调金额和 payment_account、partner_id 进行比对 。
    elif data['bank_name'] in ['easypaisa', 'jazzcash']:
        final_utr = data['account']   # 需要将account作为收款手机号→作为utr的数据处理
        condition = ' and payment_account=%s and payment_id=%s'
        value = (amount, final_utr, data['payment_id'])
    else:
        condition = ' and left(ifsc,4)=%s and right(payment_account,4)=%s' if data['ifsc'] else ''
        value = (amount, data['ifsc'][:4], data['code'][-4:]) if data['ifsc'] else (amount, data['code'][-4:])

    # 通过IFSC前四位和银行卡后四位查找订单
    sql_select_order = """select * from orders_df where amount=%s{condition} and status
                        in (-1,1,2) and date_add(time_accept, interval 3 hour ) > now() order by id limit 1""".format(condition=condition)
    # 商户代理费率
    sql_select_rates = """select id,rate_df from (select @orgId id, (select rate_df from merchant where id=@orgId) rate_df,
                            (select @orgId:=pid from merchant where id=@orgId) pid from 
                            (select @orgId:=%s) vars,merchant) t where id is not null order by pid desc"""
    # 更新系统余额
    sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
    if 'maha' == str(data['bank_name']).lower():
        # 更新订单
        sql_update = f"update orders_df set earn_merchant=%s,time_success=%s,status=3,payment_img=1,utr='{final_utr}' where code=%s and status in (-1,1,2) limit 1"
    else:
        # 更新订单
        sql_update = """update orders_df set earn_merchant=%s,time_success=%s,status=3,utr=%s where code=%s and status in (-1,1,2) limit 1"""
    self.logger.info('UTR:{} - 执行查询订单操作。SQL: {}, 参数: {}'.format(final_utr, sql_select_order, value))
    _order = await self.query(sql_select_order, *value)
    self.logger.info('UTR:{} - 查询订单完成。返回结果: {}'.format(final_utr, _order))
    if not _order:
        return dict(code=99, msg='Order not found')
    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'grab_df_{code}'.format(code=_order[0]['code'])
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('code:{}Do not operate frequently'.format(_order[0]['code']))
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查找订单
                if not await cur.execute(sql_select_order, value):
                    return dict(code=99, msg='Order not found')
                order = (await cur.fetchall())[0]
                self.logger.info('UTR:{} - 获取订单状态码。订单ID: {}'.format(final_utr, order['code']))
                code = order['code']
                
                # 先给-1， 1=常规订单，2=拆单主单，3=拆单子单
                order_type = -1
                if not order.get('is_split') and not order.get('parent_id'):
                    order_type = 1
                if order.get('is_split') and not order.get('parent_id'):
                    order_type = 2
                if order.get('parent_id'):
                    order_type = 3
                
                self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, {order_type}, {order['status']}')
                # #328 & 382, 主单不会走这个逻辑，子单不会直接影响商户金额
                earn_merchant = Decimal(0)
                if order_type in [1]:
                    # 扣商户(过期订单)
                    if order['status'] == -1:
                        self.logger.info(f"[{code}] 准备扣除商户 {order['merchant_id']} 过期订单金额 {order['realpay']}。")
                        if not await self.change_balance(conn, cur, 'mercahnt', order['merchant_id'], -order['realpay'], code, 0):
                            return dict(code=99, msg='Failed to deduct merchant balance')
                        
                    # 商户代理费用
                    # earn_merchant = Decimal(0)
                    if order['earn_merchant'] > Decimal(0):
                        if not await cur.execute(sql_select_rates, order['merchant_id']):
                            self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Not found merchant agent')
                            await conn.rollback()
                            return dict(code=99, msg='Not found merchant agent')
                        merchant_prates = (await cur.fetchall())
                        for k, v in enumerate(merchant_prates):
                            if not k == 0 and v['rate_df']:
                                _amount = amount * (merchant_prates[k - 1]['rate_df'] - v['rate_df'])
                                if _amount == 0:
                                    self.logger.info(
                                        '代付订单{code}没有代付费用差,上级商户{id}费率{rate_df} ,本级商户{id2}费率{rate_df2}'.format(code=code, id=merchant_prates[k - 1]['id'],rate_df=merchant_prates[k - 1]['rate_df'], id2=v['id'],rate_df2=v['rate_df']))
                                    continue
                                if _amount < 0:
                                    await conn.rollback()
                                    self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Merchant agent rate error')
                                    return dict(code=99, msg='Merchant agent rate error')
                                self.logger.info(f"[{code}] 准备为商户代理 {v['id']} 增加佣金 {_amount}。")
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Failed to add merchant agent balance')
                                    return dict(code=99, msg='Failed to add merchant agent balance')
                                earn_merchant += _amount
                
                # #328 & 382，主单不会走这个逻辑
                if order_type in [1, 3]:
                    # 码商余额
                    partner_id = order['partner_id']
                    self.logger.info(f"[{code}] 准备为码商 {partner_id} 增加代付金额 {amount}。")
                    if not await self.change_balance(conn, cur, 'partner', partner_id, amount, code, 1):
                        await conn.rollback()
                        self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Failed to add partner balance')
                        return dict(code=99, msg='Failed to add partner balance')
                
                # #328 & 382, 主单 & 子单 不会走这个逻辑
                if order_type in [1]:
                    # 码商佣金
                    self.logger.info(f"[{code}] 准备为码商 {partner_id} 增加佣金 {order['earn_partner_self']}。")
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code, 3):
                        await conn.rollback()
                        self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Failed to add parter balacne')
                        return dict(code=99, msg='Failed to add parter balacne')
                    
                    # 代付优惠
                    disprice = Decimal(0)
                    range_df = (await self.get_cache_result('sys_info', ['range_df']))['range_df']
                    if range_df:
                        range_df = json.loads(range_df)
                        for i in range(1, 7):
                            if range_df['isOpen' + str(i)] == 1:
                                if Decimal(range_df['rangemin' + str(i)]) <= amount <= Decimal(range_df['rangemax' + str(i)]):
                                    disprice = Decimal(range_df['disprice' + str(i)])
                                    self.logger.info(
                                        '代付优惠 disprice:{disprice} rangemin:{rangemin} rangemax:{rangemax} amount:{amount} merchant_id:{merchant_id}'.format(
                                            disprice=disprice, rangemin=range_df['rangemin' + str(i)],
                                            rangemax=range_df['rangemax' + str(i)], amount=amount,
                                            merchant_id=order['merchant_id']))
                                    break
                    
                    # 代付优惠入库
                    if disprice > 0:
                        self.logger.info(f"[{code}] 准备为码商 {partner_id} 增加代付优惠 {disprice}。")
                        if not await self.change_balance(conn, cur, 'partner', partner_id, disprice, code, 10):
                            await conn.rollback()
                            self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Failed to add partner balance')
                            return dict(code=99, msg='Failed to add partner balance')

                # 修改卡系统余额
                if not await cur.execute(sql_update_payment, (-amount, self.qr_id)):
                    await conn.rollback()
                    self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Update payment system balance error')
                    return dict(code=99, msg='Update payment system balance error')
                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if not await cur.execute(sql_update, (earn_merchant, time_now, source_utr, order['code'])):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    self.logger.info(f'UTR:{final_utr} - 获取订单状态码。订单ID: {order['code']}, Update order error')
                    return dict(code=99, msg='Update order error')
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=code, e=str(e)))
                await conn.rollback()
                return dict(code=99, msg='Order exception')
            else:
                # #328, 取消母子联动
                # inish_flag = True
                # if order.get('parent_id'):
                #     # 如果是拆分父订单，则检查所有子订单是否已完成
                #     sql_update = """update orders_df set time_success=%s,status=4 where code=%s limit 1"""
                #     self.logger.info( f'更新子单状态=={sql_update}, {code}')
                #     await cur.execute(sql_update, (time_now, code))
                    
                #     sql_check_children = """
                #         SELECT COUNT(*) count1 FROM orders_df
                #         WHERE parent_id = %s AND status != 4 AND is_split = 0 AND is_del = 0
                #     """
                #     if not await cur.execute(sql_check_children, (order.get('parent_id'))):
                #         self.logger.info('%s %s 查询子订单失败 %s' % (data['otherpay_id'], data['otherpay'], code))
                #     incomplete_children_count = (await cur.fetchone())
                #     if incomplete_children_count['count1'] == 0:
                #         sql_update = """update orders_df set time_success=%s,status=3 where code=%s and status in (-1,1,2) limit 1"""
                #         await cur.execute(sql_update, (time_now, order.get('parent_id')))
                #         finish_flag = True
                #         code = order.get('parent_id')
                #     else:
                #         finish_flag = False
                        
                await conn.commit()
                
                # 重新接单
                await _requeue_df_if_online(self, self.qr_id)
                    
                # 回调
                await self.redis.publish('order_df_notify', code)
                
                # if finish_flag is True:
                #     # 所有子订单均已完成，发布回调通知
                #     await self.redis.publish('order_df_notify', code)
                #     self.logger.info(f'没有有未完成的子订单,finish_flag=={code}=={order.get('parent_id')}={finish_flag}, 通知商户。')
                # else:
                #     self.logger.info(f'有未完成的子订单,finish_flag=={code}=={finish_flag}, 不能通知商户。')
                
                # ==================== 变更后结束 ====================
                return dict(code=100, msg='Callback Success:{}'.format(code), order=code)

# 三方代付确认
async def success_third_df(self, data, utr=None):
    amount = abs(Decimal(data['amount']))
    code = data['code']
    sql_select_order = """select * from orders_df where code=%s and amount=%s  and status
                        in (-1,1,2) and date_add(time_accept, interval 3 day ) > now() """
    # 商户代理费率
    sql_select_rates = """select id,rate_df from (select @orgId id, (select rate_df from merchant where id=@orgId) rate_df,
                            (select @orgId:=pid from merchant where id=@orgId) pid from 
                            (select @orgId:=%s) vars,merchant) t where id is not null order by pid desc"""
    # 更新订单
    if utr:
        sql_update = """update orders_df set earn_merchant=%s,time_success=%s,status=3,utr=%s where code=%s and status in (-1,1,2) limit 1"""
    else:
        sql_update = """update orders_df set earn_merchant=%s,time_success=%s,status=3 where code=%s and status in (-1,1,2) limit 1"""

    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'grab_df_{code}'.format(code=code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('code:{}Do not operate frequently'.format(code))
            return False
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查找订单
                if not await cur.execute(sql_select_order, (code, amount)):
                    self.logger.info('%s %s 回调确认 订单找不到或不匹配 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                order = (await cur.fetchall())
                if not order:
                    self.logger.info('%s %s 回调确认 订单找不到或不匹配 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                order = order[0]
                
                # 先给-1， 1=常规订单，2=拆单主单，3=拆单子单
                order_type = -1
                if not order.get('is_split') and not order.get('parent_id'):
                    order_type = 1
                if order.get('is_split') and not order.get('parent_id'):
                    order_type = 2
                if order.get('parent_id'):
                    order_type = 3
                
                earn_merchant = Decimal(0)
                # #328 & 382, 主单不会走这个逻辑，子单不会直接影响商户金额
                if order_type in [1]:
                    # 扣商户(过期订单)
                    if order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'mercahnt', order['merchant_id'], -order['realpay'], code, 0):
                            self.logger.warning('code:{} 回调确认 减少商户余额错误'.format(code))
                            return False
                        
                    # 商户代理费用
                    if order['earn_merchant'] > Decimal(0):
                        if not await cur.execute(sql_select_rates, order['merchant_id']):
                            await conn.rollback()
                            self.logger.warning('code:{} 回调确认 商户代理未发现'.format(code))
                            return False
                        merchant_prates = (await cur.fetchall())
                        for k, v in enumerate(merchant_prates):
                            if not k == 0 and v['rate_df']:
                                _amount = amount * (merchant_prates[k - 1]['rate_df'] - v['rate_df'])
                                if _amount == 0:
                                    self.logger.info(
                                        '代付订单{code}没有代付费用差,上级商户{id}费率{rate_df} ,本级商户{id2}费率{rate_df2}'.format(code=code, id=merchant_prates[k - 1]['id'],rate_df=merchant_prates[k - 1]['rate_df'], id2=v['id'],rate_df2=v['rate_df']))
                                    continue
                                if _amount < 0:
                                    await conn.rollback()
                                    self.logger.warning('code:{} 回调确认 商户代理费率错误'.format(code))
                                    return False
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    self.logger.warning('code:{} 回调确认 增加商户代理余额错误'.format(code))
                                    return False
                                earn_merchant += _amount
                
                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if utr:
                    update_ret = await cur.execute(sql_update, (earn_merchant, time_now, utr, code))
                else:
                    update_ret = await cur.execute(sql_update, (earn_merchant, time_now, code))

                if not update_ret:
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    self.logger.warning('code:{} 回调确认 更新订单错误'.format(code))
                    return False
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('回调确认 失败,code={code},异常={e}'.format(code=code, e=str(e)))
                await conn.rollback()
                return False
            else:
                # #328, 取消母子联动
                # finish_flag = True
                # if order.get('parent_id'):
                #     # 如果是拆分父订单，则检查所有子订单是否已完成
                #     sql_update = """update orders_df set time_success=%s,status=4 where code=%s limit 1"""
                #     self.logger.info( f'更新子单状态=={sql_update}, {code}')
                #     await cur.execute(sql_update, (time_now, code))
                    
                #     sql_check_children = """
                #         SELECT COUNT(*) count1 FROM orders_df
                #         WHERE parent_id = %s AND status != 4 AND is_split = 0 AND is_del = 0
                #     """
                #     if not await cur.execute(sql_check_children, (order.get('parent_id'))):
                #         self.logger.info('%s %s 查询子订单失败 %s' % (data['otherpay_id'], data['otherpay'], code))
                #     incomplete_children_count = (await cur.fetchone())
                #     if incomplete_children_count['count1'] == 0:
                #         sql_update = """update orders_df set time_success=%s,status=3 where code=%s and status in (-1,1,2) limit 1"""
                #         await cur.execute(sql_update, (time_now, order.get('parent_id')))
                #         finish_flag = True
                #         code = order.get('parent_id')
                #     else:
                #         finish_flag = False
                
                await conn.commit()
                
                # 回调
                await self.redis.publish('order_df_notify', code)
                
                # if finish_flag is True:
                #     # 所有子订单均已完成，发布回调通知
                #     await self.redis.publish('order_df_notify', code)
                #     self.logger.info(f'没有有未完成的子订单,finish_flag=={code}==={order.get('parent_id')}==={finish_flag}, 通知商户。')
                # else:
                #     self.logger.info(f'有未完成的子订单,finish_flag==={code}=={finish_flag}, 不能通知商户。')
                
                self.logger.info('%s %s 回调确认 订单成功 %s' % (data['otherpay_id'], data['otherpay'], code))
                return True

# 三方代付驳回
async def cancel_third_df(self, data):
    amount = abs(Decimal(data['amount']))
    code = data['code']
    # 查找订单
    sql_select_order = """select * from orders_df where code=%s and amount=%s  and status
                        in (1,2,3,4) and date_add(time_accept, interval 3 day ) > now() """
    # 查找流水
    # sql_select_record = """select amount,user_type,user_id,record_type from balance_record where code=%s"""
    # 更新订单(取消订单驳回直接返回公池)
    # sql_update = """update orders_df set status=-2 where code=%s and status not in (-1,-2) limit 1"""
    sql_update = """update orders_df set status=0,otherpay_id=null,otherpay=null,time_accept=null where code=%s and status not in (-1,-2) limit 1"""

    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'grab_df_{code}'.format(code=code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('code:{}Do not operate frequently'.format(code))
            return False
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查询订单
                if not await cur.execute(sql_select_order, (code, amount)):
                    self.logger.info('%s %s 驳回回调 订单找不到或不匹配 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                order = (await cur.fetchall())
                if not order:
                    self.logger.info('%s %s 回调确认 订单找不到或不匹配 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                # 按流水退款
                # if not await cur.execute(sql_select_record, code):
                #     self.logger.info('%s %s 驳回回调 找不到记录 %s' % (data['otherpay_id'], data['otherpay'], code))
                #     return False
                # record = await cur.fetchall()
                # for i in record:
                #     tabel_name = 'merchant' if i['user_type'] else 'partner'
                #     if not await self.change_balance(conn, cur, tabel_name, i['user_id'], -i['amount'], code, i['record_type']):
                #         self.logger.info('%s %s 驳回回调 返回余额错误 %s' % (data['otherpay_id'], data['otherpay'], code))
                #         return False
                # 修改订单状态
                if not await cur.execute(sql_update, code):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    self.logger.info('%s %s 驳回回调 更新订单错误 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('驳回回调 失败,code={code},异常={e}'.format(code=code, e=e))
                await conn.rollback()
                return False
            else:
                # #328, 取消母子联动
                # finish_flag = True
                # if order[0].get('parent_id'):
                #     # 如果是拆分父订单，则检查所有子订单是否已完成
                #     sql_check_children = """
                #         SELECT COUNT(*) count1 FROM orders_df
                #         WHERE parent_id = %s AND status != 0 AND is_split = 0 AND is_del = 0
                #     """
                #     if not await cur.execute(sql_check_children, (order[0].get('parent_id'))):
                #         self.logger.info('%s %s 查询子订单失败 %s' % (data['otherpay_id'], data['otherpay'], code))
                #     incomplete_children_count = (await cur.fetchone())
                #     if incomplete_children_count['count1'] == 0:
                #         finish_flag = True
                #         code = order[0].get('parent_id')
                #     else:
                #         finish_flag = False
                
                await conn.commit()
                
                # 回调
                # await self.redis.publish('order_df_notify', code)
                
                # if finish_flag is True:
                #     # 所有子订单均已完成，发布回调通知
                #     await self.redis.publish('order_df_notify', code)
                #     self.logger.info(f'没有有未完成的子订单,finish_flag={finish_flag}=={code}=={order[0].get('parent_id')}, 通知商户。')
                # else:
                #     self.logger.info(f'有未完成的子订单,finish_flag={finish_flag}, 不能通知商户。')
                
                self.logger.info('%s %s 驳回回调 成功 %s' % (data['otherpay_id'], data['otherpay'], code))
                return True

# 三方代付revert
async def revert_third_df(self, data):
    amount = abs(Decimal(data['amount']))
    code = data['code']
    # 查找订单
    sql_select_order = """select * from orders_df where code=%s and amount=%s  and status
                        in (1,2,3,4) and date_add(time_accept, interval 3 day ) > now() """
    # 查找流水
    sql_select_record = """select amount,user_type,user_id,record_type from balance_record where code=%s"""
    # 更新订单
    sql_update = """update orders_df set status=-2 where code=%s and status not in (-1,-2) limit 1"""

    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'grab_df_{code}'.format(code=code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('code:{}Do not operate frequently'.format(code))
            return False
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查询订单
                if not await cur.execute(sql_select_order, (code, amount)):
                    self.logger.info('%s %s REVERT回调 订单找不到或不匹配 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                order = (await cur.fetchall())
                if not order:
                    self.logger.info('%s %s REVERT回调 订单找不到或不匹配 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                order = order[0]
                
                # 确定是否是子订单
                if order.get('parent_id') is not None and order.get('parent_id') != '':
                    is_sub_order = True
                self.logger.info(f"订单 {code} 是否为子单: {is_sub_order}")
                if is_sub_order:
                    # --- 子订单特殊处理逻辑 对应处理保留---
                    # merchant_id_for_refund = order.get('merchant_id')
                    # if not merchant_id_for_refund:
                    #     self.logger.warning(f"子订单 {code} 找不到对应的商户ID，无法退款。")
                    #     await conn.rollback()
                    #     return False
                    # 执行退款给商户
                    # refund_amount = order['amount']
                    # if not await self.change_balance(conn, cur, 'merchant', merchant_id_for_refund,
                    #                                     refund_amount, code, 9, data['sys_remark']):
                    #     self.logger.warning(f"子订单 {code} 退款给商户 {merchant_id_for_refund} 失败。")
                    #     await conn.rollback()
                    #     return False
                    # self.logger.info(f"子订单 {code} 金额 {refund_amount} 已退款给商户 {merchant_id_for_refund}。")
                    pass
                else:
                    # --- 母订单或非子订单的常规退款逻辑 ---
                    # 按流水退款
                    if not await cur.execute(sql_select_record, code):
                        self.logger.info('%s %s REVERT回调 找不到记录 %s' % (data['otherpay_id'], data['otherpay'], code))
                        return False
                    record = await cur.fetchall()
                    for i in record:
                        tabel_name = 'merchant' if i['user_type'] else 'partner'
                        if not await self.change_balance(conn, cur, tabel_name, i['user_id'], -i['amount'], code, i['record_type']):
                            self.logger.info('%s %s REVERT回调 返回余额错误 %s' % (data['otherpay_id'], data['otherpay'], code))
                            return False
                # 修改订单状态
                if not await cur.execute(sql_update, code):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    self.logger.info('%s %s REVERT回调 更新订单错误 %s' % (data['otherpay_id'], data['otherpay'], code))
                    return False
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('REVERT回调 失败,code={code},异常={e}'.format(code=code, e=e))
                await conn.rollback()
                return False
            else:
                # #328, 取消母子联动
                # finish_flag = True
                # if order.get('parent_id'):
                #     # 如果是拆分父订单，则检查所有子订单是否已完成
                #     sql_check_children = """
                #         SELECT COUNT(*) count1 FROM orders_df
                #         WHERE parent_id = %s AND status != -2 AND is_split = 0 AND is_del = 0
                #     """
                #     if not await cur.execute(sql_check_children, (order.get('parent_id'))):
                #         self.logger.info('%s %s 查询子订单失败 %s' % (data['otherpay_id'], data['otherpay'], code))
                #     incomplete_children_count = (await cur.fetchone())
                #     if incomplete_children_count['count1'] == 0:
                #         finish_flag = True
                #         code = order.get('parent_id')
                #         self.logger.warning(f"订单 {order.get('parent_id')} 子订单驳回完成, 开始母订单退款。")
                #         # 按流水退款
                #         if not await cur.execute(sql_select_record, order.get('parent_id')):
                #             self.logger.info('%s %s REVERT回调 找不到记录 %s' % (data['otherpay_id'], data['otherpay'], order.get('parent_id')))
                #             return False
                #         record = await cur.fetchall()
                #         for i in record:
                #             tabel_name = 'merchant' if i['user_type'] else 'partner'
                #             if not await self.change_balance(conn, cur, tabel_name, i['user_id'], -i['amount'], order.get('parent_id'), i['record_type']):
                #                 self.logger.info('%s %s REVERT回调 返回余额错误 %s' % (data['otherpay_id'], data['otherpay'], order.get('parent_id')))
                #                 return False
                #     else:
                #         finish_flag = False
                        
                await conn.commit()
                
                # 回调
                await self.redis.publish('order_df_notify', code)
                
                # if finish_flag is True:
                #     # 所有子订单均已完成，发布回调通知
                #     await self.redis.publish('order_df_notify', code)
                #     self.logger.info(f'没有有未完成的子订单,finish_flag={code}===={order.get('parent_id')}==={order.get('parent_id')}={finish_flag}, 通知商户。')
                # else:
                #     self.logger.info(f'有未完成的子订单,finish_flag=={code}={finish_flag}, 不能通知商户。')
                
                self.logger.info('%s %s REVERT回调 成功 %s' % (data['otherpay_id'], data['otherpay'], code))
                return True

# 代付手续费
async def sxf_df(self, data):
    # 更新系统余额
    sql_select = """select partner_id from payment where id=%s"""
    sql_update = """update payment set sys_balance=sys_balance+%s where id=%s"""
    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                if not await cur.execute(sql_select, self.qr_id):
                    return dict(code=99, msg='Partner not found')
                partner_id = (await cur.fetchall())[0]['partner_id']
                if not await self.change_balance(conn, cur, 'partner', partner_id, abs(Decimal(data['amount'])), 0, 0):
                    return dict(code=99, msg='Failed add partner balance')
                # 修改卡系统余额
                if not await cur.execute(sql_update, (abs(Decimal(data['amount'])), self.qr_id)):
                    await conn.rollback()
                    return dict(code=99, msg='Update payment system balance error')
            except Exception as e:
                self.logger.warning('补手续费异常={e}'.format(e=e))
                await conn.rollback()
                return dict(code=99, msg='Order exception')
            else:
                await conn.commit()
                return dict(code=100, msg='Callback Success')


# 代付退款
async def cancel_df(self, data):
    # 查找订单
    sql_select_order = """select * from orders_df where code=%s order by id desc limit 1"""
    # 查找订单号
    sql_select_order_code = """select order_code from bank_record where utr=%s and trade_tye=1 limit 1"""
    # 查找流水
    sql_select_record = """select amount,user_type,user_id,record_type from balance_record where code=%s"""
    # 更新系统余额
    sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
    # 更新订单
    sql_update = """update orders_df set status=-1 where code=%s and status != -1 limit 1"""
    
    sql_update_order_status_remark = """
            UPDATE orders_df SET status=-1, sys_remark=%s
            WHERE code=%s AND status NOT IN (-1, -2)
        """

    _order = await self.query(sql_select_order_code, data['utr'])
    if not _order:
        return dict(code=99, msg='Order not found')
    
    code = _order[0]['code']
    
    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'grab_df_{code}'.format(code=code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('code:{}Do not operate frequently'.format(code))
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查询订单
                if not await cur.execute(sql_select_order, data['utr']):
                    return dict(code=99, msg='Order not found')
                order = (await cur.fetchall())[0]
                    
                is_split = order.get('is_split')
                parent_id = order.get('parent_id')
                
                # 先给-1， 1=常规订单，2=拆单主单，3=拆单子单
                order_type = -1

                if not is_split and not parent_id:
                    order_type = 1
                if is_split and not parent_id:
                    order_type = 2
                if parent_id:
                    order_type = 3
                        
                if order_type == 3:
                    merchant_id_for_refund = order.get('merchant_id')
                    if not merchant_id_for_refund:
                        self.logger.warning(f"子订单 {code} 找不到对应的商户ID，无法退款。")
                        await conn.rollback()
                        return False
                    # # 执行退款给商户
                    # refund_amount = order['amount']
                    # if not await self.change_balance(conn, cur, 'merchant', merchant_id_for_refund,
                    #                                     refund_amount, code, 9, data['sys_remark']):
                    #     self.logger.warning(f"子订单 {code} 退款给商户 {merchant_id_for_refund} 失败。")
                    #     await conn.rollback()
                    #     return False
                    # self.logger.info(f"子订单 {code} 金额 {refund_amount} 已退款给商户 {merchant_id_for_refund}。")
                    sql_update = """update orders_df set status=-1 where code=%s and status in (-1,1,2) limit 1"""
                    await cur.execute(sql_update, parent_id)

                    #region 此处主要是统计
                    self.logger.info(f"开始检查母订单 {parent_id} 的活跃子订单数量...")
                    sql_count_active_children = """
                        SELECT COUNT(1) COUNT1 FROM orders_df
                        WHERE parent_id = %s AND status NOT IN (-2)
                    """
                    try:
                        self.logger.info("执行 SQL（统计活跃子订单）：%s", sql_count_active_children.strip())
                        self.logger.info("SQL 参数：(%s,)", parent_id)

                        await cur.execute(sql_count_active_children, (parent_id,))

                        # 这里务必要 await
                        result = await cur.fetchone()
                        self.logger.info("统计结果：%s", result)

                        active_children_count = result['COUNT1']
                        self.logger.info(f"母订单 {parent_id} 剩余活跃子订单数量: {active_children_count}")
                        
                    except Exception as e:
                        self.logger.exception(f"统计母订单 {parent_id} 子订单数量时发生异常: {e}")
                        await conn.rollback()
                        return self.json_response(self.msg[10017])
                    # endregion

                    # #328-取消自动驳回，母单需要自己手动驳回
                    # region 子单影响母单
                    # if active_children_count == 0:
                    #     self.logger.info(f"检测到母订单 {parent_id} 没有活跃子订单，将自动驳回母订单。")

                    #     parent_remark = f"Parent order {parent_id} automatically rejected as last active sub-order {code} was rejected at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    #     self.logger.info("生成自动驳回母订单备注：%s", parent_remark)

                    #     self.logger.info("执行 SQL（查询母订单）：%s", sql_select_order.strip())
                    #     self.logger.info("SQL 参数：(%s,)", parent_id)
                    #     await cur.execute(sql_select_order, parent_id)
                    #     parent_order_data = await cur.fetchone()

                    #     self.logger.info("母订单数据查询结果：%s", parent_order_data)

                    #     if parent_order_data and parent_order_data['status'] not in (-1, -2):
                    #         self.logger.info(f"母订单 {parent_id} 当前状态为 {parent_order_data['status']}，满足自动驳回条件。")

                    #         self.logger.info("执行 SQL（更新母订单状态）：%s", sql_update_order_status_remark.strip())
                    #         self.logger.info("SQL 参数：(%s, %s)", parent_remark, parent_id)

                    #         if not await cur.execute(sql_update_order_status_remark, (parent_remark, parent_id)):
                    #             self.logger.error(f"自动驳回母订单 {parent_id} 失败，准备回滚。")
                    #             await conn.rollback()
                    #             return self.json_response(self.msg[10007])

                    #         self.logger.info(f"母订单 {parent_id} 已自动驳回。提交事务中 下面继续母单驳回流水...")
                    #         # 按流水退款
                    #         if not await cur.execute(sql_select_record, parent_id):
                    #             return dict(code=99, msg='Record not found')
                    #         record = await cur.fetchall()
                    #         for i in record:
                    #             tabel_name = 'merchant' if i['user_type'] else 'partner'
                    #             if not await self.change_balance(conn, cur, tabel_name, i['user_id'], -i['amount'], parent_id, i['record_type']):
                    #                 return dict(code=99, msg='Failed return balance')
                    #         # 修改卡系统余额
                    #         if order['status'] in [3, 4]:
                    #             if not await cur.execute(sql_update_payment, (data['amount'], self.qr_id)):
                    #                 await conn.rollback()
                    #                 return dict(code=99, msg='Update payment system balance error')
                    # endregion
                else:
                    # 按流水退款
                    if not await cur.execute(sql_select_record, code):
                        return dict(code=99, msg='Record not found')
                    record = await cur.fetchall()
                    for i in record:
                        tabel_name = 'merchant' if i['user_type'] else 'partner'
                        if not await self.change_balance(conn, cur, tabel_name, i['user_id'], -i['amount'], code, i['record_type']):
                            return dict(code=99, msg='Failed return balance')
                    # 修改卡系统余额
                    if order['status'] in [3, 4]:
                        if not await cur.execute(sql_update_payment, (data['amount'], self.qr_id)):
                            await conn.rollback()
                            return dict(code=99, msg='Update payment system balance error')
                    # 修改订单状态
                    if not await cur.execute(sql_update, code):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return dict(code=99, msg='Update order error')
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('回退订单失败,code={code},异常={e}'.format(code=code, e=e))
                await conn.rollback()
                return dict(code=99, msg='Order exception')
            else:
                await conn.commit()
                # 重新接单
                await _requeue_df_if_online(self, order['payment_id'])
                # 驳回回调
                # await self.redis.publish('order_df_notify', code)
                # if active_children_count == 0:
                #     await self.redis.publish('order_df_notify', parent_id)
                #     self.logger.info(f'没有有未完成的子订单,active_children_count={active_children_count}={parent_id}=={code}, 通知商户。')
                # else:
                #     self.logger.info(f'有未完成的子订单,finish_flag=={code}, 不能通知商户。')
                return dict(code=100, msg='Return Success:{}'.format(code))
