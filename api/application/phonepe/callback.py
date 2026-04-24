import json
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from aiomysql import DictCursor


# 代收确认
async def success_ds(self, data):
    # 根据确认码或UTR查找订单
    condition = 'utr'
    if data['code']:
        if data['bank_name'] == 'indusind' and len(data['code']) == 4:
            condition = 'left(auth_code,4)'
        elif len(data['code']) == 5:
            condition = 'auth_code'
    # 根据确认码或UTR查找订单
    sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) and 
                            date_add(time_create, interval 30 minute) > now() order by id limit 1""".format(condition)
    # 商户代理费率
    sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant 
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join 
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
    # 码商代理费率
    sql_select_rates_partner = """select rates from channel where code=%s"""
    # 更新系统余额
    sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
    # 更新订单
    sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,payment_id=%s,
                        utr=%s,time_success=%s,status=3,upi=%s where code=%s and status in (-1,1,2) limit 1"""
    # 根据收款资料id查询
    sql_select_payment = """select * from payment where id=%s order by id limit 1"""

    # _order = await self.query(sql_select_order, Decimal(data['amount']), data['code'] if condition != 'utr' else data['utr'])
    amount = Decimal(data['amount'])
    original_amount = amount  # 保存原始小数金额
    has_decimal = amount % 1 != 0  # 判断金额是否为小数

    if has_decimal:
        # 小数点回调超时检查
        if 'payment_id' in data:
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
        
        self.logger.info(f"[订单匹配] 金额 {amount} 含小数，使用更严格规则匹配订单（按 payment_id + 时间）")
        sql_select_order = """
            SELECT * FROM orders_ds 
            WHERE amount=%s AND payment_id=%s AND status IN (-1,1,2) 
            AND date_add(time_create, interval 180 minute) > now() 
            ORDER BY id DESC LIMIT 1
        """
        self.logger.info(f"[订单匹配] 执行 SQL: {sql_select_order.strip()} 参数: 金额={amount}, payment_id={data['payment_id']}")
        _order = await self.query(sql_select_order, amount, data['payment_id'])
    else:
        self.logger.info(f"[订单匹配] 金额 {amount} 为整数，使用默认规则（{condition} 匹配）")
        self.logger.info(f"[订单匹配] 执行 SQL: {sql_select_order.strip()} 参数: 金额={amount}, 匹配字段={condition}, 值={data['code'] if condition != 'utr' else data['utr']}")
        _order = await self.query(sql_select_order,
            amount, data['code'] if condition != 'utr' else data['utr'])
        
    if not _order:
        if not condition == 'utr': # 如果查询不到，重新按utr查询
            self.logger.warning('utr:{}Not Order not found'.format(data['utr']))
            sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) and 
                                    date_add(time_create, interval 30 minute) > now() order by id limit 1""".format('utr')
            _order = await self.query(sql_select_order, Decimal(data['amount']), data['utr'])
        if not _order:
            self.logger.warning('utr:{}Not Order not found k2'.format(data['utr']))
            self.logger.warning(f"准备执行订单查询 | SQL: {sql_select_order}")
            self.logger.warning(f"参数: amount={Decimal(data['amount'])}, code={data['code'] if condition != 'utr' else data['utr']}")
            return dict(code=99, msg='Order not found')
    _payment = await self.query(sql_select_payment, self.payment_id)
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
            self.logger.warning('utr:{}Do not operate frequently'.format(data['utr']))
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                amount = Decimal(data['amount'])
                partner_id = int(self.partner_id)
                # 查找订单
                if has_decimal:
                    # 小数金额，使用 payment_id + 金额 精确查询
                    sql_select_order = """
                        SELECT * FROM orders_ds 
                        WHERE amount=%s AND payment_id=%s AND status IN (-1,1,2) 
                        AND date_add(time_create, interval 180 minute) > now() 
                        ORDER BY id DESC LIMIT 1
                    """
                    if not await cur.execute(sql_select_order, (amount, data['payment_id'])):
                        self.logger.warning(f"utr:{data['utr']} 仍未找到订单（小数金额）")
                        return dict(code=99, msg='Order not found')
                else:
                    if not await cur.execute(sql_select_order, (Decimal(amount), data['code'] if condition != 'utr' else data['utr'])):
                        if not condition == 'utr':  # 如果查询不到，重新按utr查询
                            sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) and 
                                                    date_add(time_create, interval 30 minute) > now() order by id limit 1""".format('utr')
                            if not await cur.execute(sql_select_order, (amount, data['utr'])):
                                self.logger.warning('utr:{}Not Order not found2'.format(data['utr']))
                                return dict(code=99, msg='Order not found')
                        else:
                            self.logger.warning('utr:{}Not Order not found'.format(data['utr']))
                            return dict(code=99, msg='Order not found')
                order = (await cur.fetchall())[0]
                code = order['code']
                amount = order['original_amount'] or amount

                # 打印中文日志
                self.logger.info(f"code: {code}, 原始充值金额: {amount}")

                # 去掉小数部分（向下取整）
                # amount = amount.to_integral_value(rounding=ROUND_DOWN)

                # 打印中文日志
                self.logger.info(f"code: {code}, 去除小数部分后金额: {amount}")

                # 订单里的码和码商id比较银行流水里的判断  1207
                self.logger.info("Comparing order['partner_id']={} with partner_id={}".format(order['partner_id'], partner_id))
                self.logger.info("Comparing order['payment_id']={} with self.payment_id={}".format(order['payment_id'], self.payment_id))

                # 转换为字符串并去除空格后比较
                if str(order['partner_id']).strip() != str(partner_id).strip() or str(order['payment_id']).strip() != str(self.payment_id).strip():
                    self.logger.warning(
                        '订单中的码和码商ID与银行流水中的信息不匹配 | UTR: {} | 订单信息: [码商ID: {}, 支付码: {}] | 输入值: [码商ID: {}, 支付码: {}]'
                        .format(data['utr'], order['partner_id'], order['payment_id'], partner_id, self.payment_id)
                    )
                    return dict(code=99, msg='订单中的码和码商ID与银行流水中的信息不匹配')

                # 补扣码商(非自身订单、过期订单)
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
                if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], code, 0):
                    self.logger.warning('utr:{}Failed to add merchant balance'.format(data['utr']))
                    return dict(code=99, msg='Failed to add merchant balance')
                # 商户代理费用
                earn_merchant = Decimal(0)
                if order['earn_merchant'] > 0:
                    if not await cur.execute(sql_select_rates_merchant, (order['merchant_id'], order['channel_code'])):
                        await conn.rollback()
                        self.logger.warning('utr:{}DNot found merchant agent'.format(data['utr']))
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
                if earn_system < 0:
                    await conn.rollback()
                    self.logger.warning('utr:{}Rate exception'.format(data['utr']))
                    return dict(code=99, msg='Rate exception')
                # 修改卡系统余额
                if not await cur.execute(sql_update_payment, (amount, self.payment_id)):
                    await conn.rollback()
                    self.logger.warning('utr:{}Update payment system balance error'.format(data['utr']))
                    return dict(code=99, msg='Update payment system balance error')
                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id,
                                                            self.payment_id, data['utr'], time_now, _payment[0]['upi'], code)):
                    await conn.rollback()
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
                        decimal_amount = Decimal(data['amount'])  # 这里是实际的小数点金额
                        await pay_instance.cleanup_decimal_callback_on_success(self.payment_id, decimal_amount, "成功回调")
                    except Exception as cleanup_error:
                        self.logger.exception(f'小数点回调清理失败: {cleanup_error}')
                
                # 加入回调
                await self.redis.publish('order_notify', code)
                return dict(code=100, msg='Callback Success:{}'.format(code), order=code)


# 代付确认
async def success_df(self, data):
    amount = abs(Decimal(data['amount']))
    if data['bank_name'] == 'freecharge':
        condition = '  and ifsc=%s'
        value = (amount, data['ifsc'], data['code'])
    else:
        condition = ' and left(ifsc,4)=%s' if data['ifsc'] else ''
        value = (amount, data['ifsc'][:4], data['code'][-4:]) if data['ifsc'] else (amount, data['code'][-4:])

    # 通过IFSC前四位和银行卡后四位查找订单
    sql_select_order = """select * from orders_df where amount=%s{condition} and right(payment_account,4)=%s and status
                        in (-1,1,2) and date_add(time_accept, interval 3 hour ) > now() order by id limit 1""".format(condition=condition)
    # 商户代理费率
    sql_select_rates = """select id,rate_df from (select @orgId id, (select rate_df from merchant where id=@orgId) rate_df,
                            (select @orgId:=pid from merchant where id=@orgId) pid from 
                            (select @orgId:=%s) vars,merchant) t where id is not null order by pid desc"""
    # 更新系统余额
    sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
    # 更新订单
    sql_update = """update orders_df set earn_merchant=%s,time_success=%s,status=3 where code=%s and status in (-1,1,2) limit 1"""

    _order = await self.query(sql_select_order, *value)
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
                code = order['code']
                # 扣商户(过期订单)
                if order['status'] == -1:
                    self.logger.info(f"[{code}] 准备扣除商户 {order['merchant_id']} 过期订单金额 {order['realpay']}。")

                    if not await self.change_balance(conn, cur, 'mercahnt', order['merchant_id'], -order['realpay'], code, 0):
                        return dict(code=99, msg='Failed to deduct merchant balance')
                # 商户代理费用
                earn_merchant = Decimal(0)
                if order['earn_merchant'] > Decimal(0):
                    if not await cur.execute(sql_select_rates, order['merchant_id']):
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
                                return dict(code=99, msg='Merchant agent rate error')
                            self.logger.info(f"[{code}] 准备为商户代理 {v['id']} 增加佣金 {_amount}。")
                            if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                return dict(code=99, msg='Failed to add merchant agent balance')
                            earn_merchant += _amount
                # 码商余额
                partner_id = order['partner_id']
                self.logger.info(f"[{code}] 准备为码商 {partner_id} 增加代付金额 {amount}。")
                if not await self.change_balance(conn, cur, 'partner', partner_id, amount, code, 1):
                    await conn.rollback()
                    return dict(code=99, msg='Failed to add partner balance')
                # 码商佣金
                self.logger.info(f"[{code}] 准备为码商 {partner_id} 增加佣金 {order['earn_partner_self']}。")
                if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code, 3):
                    await conn.rollback()
                    return dict(code=99, msg='Failed to add parter balacne')

                # 代付优惠
                disprice = Decimal(0)
                range_df = (await self.get_cache_result('sys_info', ['range_df']))['range_df']
                if range_df:
                    range_df = json.loads(range_df)
                    for i in range(1, 7):
                        if range_df['isOpen' + str(i)] == 1:
                            if Decimal(range_df['rangemin' + str(i)]) <= amount <= Decimal(
                                    range_df['rangemax' + str(i)]):
                                disprice = Decimal(range_df['disprice' + str(i)])
                                self.logger.info(
                                    '代付优惠 disprice:{disprice} rangemin:{rangemin} rangemax:{rangemax} amount:{amount} merchant_id:{merchant_id}'.format(
                                        disprice=disprice, rangemin=range_df['rangemin' + str(i)],
                                        rangemax=range_df['rangemax' + str(i)], amount=amount, merchant_id=order['merchant_id']))
                                break
                #代付优惠入库
                if disprice > 0:
                    self.logger.info(f"[{code}] 准备为码商 {partner_id} 增加代付优惠 {disprice}。")
                    if not await self.change_balance(conn, cur, 'partner', partner_id, disprice, code, 10):
                        await conn.rollback()
                        return dict(code=99, msg='Failed to add partner balance')


                # 修改卡系统余额
                if not await cur.execute(sql_update_payment, (-amount, self.payment_id)):
                    await conn.rollback()
                    return dict(code=99, msg='Update payment system balance error')
                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if not await cur.execute(sql_update, (earn_merchant, time_now, order['code'])):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return dict(code=99, msg='Update order error')
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                await conn.rollback()
                return dict(code=99, msg='Order exception')
            else:
                finish_flag = False
                if order.get('parent_id'):
                    # 如果是拆分父订单，则检查所有子订单是否已完成
                    sql_update = """update orders_df set time_success=%s,status=4 where code=%s limit 1"""
                    self.logger.info( f'更新子单状态=={sql_update}, {code}')
                    await cur.execute(sql_update, (time_now, code))
                    
                    sql_check_children = """
                        SELECT COUNT(*) count1 FROM orders_df
                        WHERE parent_id = %s AND status != 4 AND is_split = 0 AND is_del = 0
                    """
                    if not await cur.execute(sql_check_children, (order.get('parent_id'))):
                        self.logger.info('%s %s 查询子订单失败 %s' % (data['otherpay_id'], data['otherpay'], code))
                    incomplete_children_count = (await cur.fetchone())
                    if incomplete_children_count['count1'] == 0:
                        sql_update = """update orders_df set time_success=%s,status=3 where code=%s and status in (-1,1,2) limit 1"""
                        await cur.execute(sql_update, (time_now, order.get('parent_id')))
                        finish_flag = True
                await conn.commit()
                # 重新接单
                if await self.redis.sismember('payment_online_df', self.payment_id):
                    await self.redis.lrem('payment_active_df', 0, self.payment_id)
                    await self.redis.rpush('payment_active_df', self.payment_id)
                # 回调
                # ==================== 变更前：无条件回调 ====================
                # await self.redis.publish('order_df_notify', code)
                if finish_flag is True:
                    # 所有子订单均已完成，发布回调通知
                    await self.redis.publish('order_df_notify', order.get('parent_id'))
                    self.logger.info(f"没有有未完成的子订单,finish_flag=={code}==={order.get('parent_id')}={finish_flag}, 通知商户。")
                else:
                    self.logger.info(f'有未完成的子订单,finish_flag=={code}=={finish_flag}, 不能通知商户。')
                # ==================== 变更后结束 ====================
                return dict(code=100, msg='Callback Success:{}'.format(code), order=code)


# 代付手续费
async def sxf_df(self, data):
    # 更新系统余额
    sql_select = """select partner_id from payment where id=%s"""
    sql_update = """update payment set sys_balance=sys_balance+%s where id=%s"""
    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                if not await cur.execute(sql_select, self.payment_id):
                    return dict(code=99, msg='Partner not found')
                partner_id = (await cur.fetchall())[0]['partner_id']
                if not await self.change_balance(conn, cur, 'partner', partner_id, abs(Decimal(data['amount'])), 0, 0):
                    return dict(code=99, msg='Failed add partner balance')
                # 修改卡系统余额
                if not await cur.execute(sql_update, (abs(Decimal(data['amount'])), self.payment_id)):
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
    sql_select_order = """select order_code from bank_record where utr=%s and trade_tye=1 limit 1"""
    # 查找流水
    sql_select_record = """select amount,user_type,user_id,record_type from balance_record where code=%s"""
    # 更新系统余额
    sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
    # 更新订单
    sql_update = """update orders_df set status=-1 where code=%s and status != -1 limit 1"""

    _order = await self.query(sql_select_order, data['utr'])
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
                # 查询订单
                if not await cur.execute(sql_select_order, data['utr']):
                    return dict(code=99, msg='Order not found')
                order = (await cur.fetchall())[0]
                code = order['code']
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
                    if not await cur.execute(sql_update_payment, (data['amount'], self.payment_id)):
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
                await self.redis.lrem('payment_active_df', 0, order['payment_id'])
                await self.redis.rpush('payment_active_df', order['payment_id'])
                # 驳回回调
                await self.redis.publish('order_df_notify', code)
                return dict(code=100, msg='Return Success:{}'.format(code))
