"""UTR confirmation callback handler."""

import re
import time
import datetime
from decimal import Decimal

import requests
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg, msg_en
from application.sign import SignatureAndVerification


class ds_utr(BaseHandler):
    async def post(self):
        try:
            try:
                data = {k: self.get_argument(k) for k in self.request.arguments}
                self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
            except Exception:
                self.logger.exception('商户utr补单 参数异常')
                return await self.json_response(msg_en[10006])
            ip = await self.get_ip()
            ref = self.request.headers['Referer'] if 'Referer' in self.request.headers else ''
            self.logger.info('商户utr补单 收到参数{data},referrer={ref},ip={ip}'.format(data=str(data), ref=ref, ip=ip))

            valid_keys = ['mer_id', 'utr', 'order_id', 'sign']
            not_null_keys = ['mer_id', 'utr', 'order_id', 'sign']
            # 验签 需要深拷贝
            sign_data = data.copy()
            is_robot = data.pop('robot', False)
            trans_id = data.pop('trans_id', False)

            if not await self.is_valid_key(data, valid_keys):
                return await self.json_response(data=msg_en[10006])

            if await self.is_null(data, not_null_keys):
                return await self.json_response(data=msg_en[10007])

            if not await self.check_different(data, self.data_receive_filter_xss, valid_keys):
                self.logger.info('商户utr补单 参数非法{data}'.format(data=str(data)))
                return await self.json_response(data=msg_en[10006])

            try:
                merchant_id = int(data['mer_id'])
                merchant_code = data['order_id'].strip()
                utr = data['utr'].strip()
            except Exception as e:
                self.logger.exception(e)
                return await self.json_response(data=msg_en[10006])
            # 1. 检查是否为非空字符串
            if not trans_id or not isinstance(trans_id, str):
                self.logger.info("错误：交易ID不能为空或非字符串类型。")
            else:
                # 2. 检查长度
                if len(trans_id) > 50:
                    self.logger.info(f"错误：交易ID长度超过50个字符。当前长度为：{len(trans_id)}")
                    return await self.json_response(data=msg_en[10030])
                else:
                    # 3. 检查是否包含特殊字符
                    # 正则表达式：只允许字母、数字、下划线和连字符
                    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
                    if not pattern.match(trans_id):
                        self.logger.info(f"错误：交易ID包含特殊或非法字符。无效的ID为: {trans_id}")
                        return await self.json_response(data=msg_en[10030])
                    else:
                        # --- 验证通过，执行业务逻辑 ---
                        self.logger.info(f"交易ID '{trans_id}' 格式有效，开始处理补单请求...")

            # 获取商户信息
            merchant = await self.get_result_by_condition('merchant', ['mc_key', 'status'], {'id': merchant_id})
            if not merchant:
                return await self.json_response(data=msg_en[10008])

            sign_data['sign'] = sign_data['sign'].upper()
            # 移除 trans_id 字段
            if 'trans_id' in sign_data:
                del sign_data['trans_id']

            self.logger.info(f"sign_data: '{sign_data}'")
            if not SignatureAndVerification.md5_verify(sign_data, sign_data['sign'], merchant['mc_key']):
                return await self.json_response(msg_en[10009])

            keys = ['code', 'amount', 'realpay', 'status', 'time_create', 'time_success', 'time_updated', 'utr', 'upi', 'third_party_name']
            r = await self.get_result_by_condition('orders_ds', keys, {'merchant_code': merchant_code, 'merchant_id': merchant_id})
            if not r:
                self.logger.info("商户utr补单 无此商户订单：{code}，商户：{merchant_id}".format(code=merchant_code, merchant_id=merchant_id))
                return await self.json_response(msg[10016])
            code = r['code']
            if r['utr'] and not is_robot:
                self.logger.info("商户utr补单 已存在utr：{code}，商户：{merchant_id}".format(code=merchant_code, merchant_id=merchant_id))

            # ==================== 变更开始：新增 UTR 并发/频率锁====================
            # 定义 UTR 锁的键名和过期时间
            UTR_LOCK_PREFIX = "utr_submission_lock:"
            UTR_LOCK_EXPIRY_SECONDS = 10 # 锁的有效期，10秒
            utr_lock_key = f'{UTR_LOCK_PREFIX}{utr}:{code}'
            # 先使用 setnx 尝试获取锁，如果成功，再使用 expire 设置过期时间
            got_utr_lock = await self.redis.setnx(utr_lock_key, 1)

            if got_utr_lock: # 只有当成功获取锁时，才设置过期时间
                await self.redis.expire(utr_lock_key, UTR_LOCK_EXPIRY_SECONDS)
                self.logger.info(f'订单：{merchant_code}，上传的卡密信息：{utr} 提交频率锁获取成功并设置过期时间。')
            else: # 未能获取锁 (键已存在且未过期)
                self.logger.warning(f'UTR {utr} 提交过于频繁或正在被其他请求处理，放弃操作。')
                self.logger.info(f"订单：{merchant_code}，上传的卡密信息：{utr} UTR submitted too frequently or already processing.")
                return await self.json_response(msg_en[10012]) # UTR 提交频率过高/处理中

            if trans_id:
                count_circle = 0
                while True:
                    busy_key = 'success_busy_{trans_id}'.format(trans_id=trans_id)
                    if await self.redis.setnx(busy_key, 1):
                        await self.redis.expire(busy_key, 10)
                        break
                    if count_circle >= 10:
                        self.logger.warning(
                            'trans_id:{trans_id}Do not operate frequently'.format(trans_id=trans_id))
                        res = dict(code=99, msg='Do not operate frequently')
                        return await self.json_response(msg_en[10012])
                    time.sleep(0.2)
                    count_circle = count_circle + 1

                sql_check_trans_id = """
                    SELECT code FROM orders_ds WHERE trans_id=%s AND code != %s LIMIT 1
                """
                # 这里的 _order[0]['id'] 是当前找到的订单的ID
                existing_order = await self.query(sql_check_trans_id, trans_id, code)

                # 打印即将执行的查询日志，包含SQL和参数
                self.logger.info(
                    f"新增：交易ID重复校验查询 | SQL: {sql_check_trans_id.strip()} | 参数: ({trans_id}, {merchant_code})"
                )

                # 如果查询结果不为空，则说明有其他订单已使用此交易ID
                if existing_order:
                    self.logger.warning(f"交易ID {trans_id} 已被其他订单使用。冲突订单号: {existing_order[0]['code']}")
                    # 返回一个错误提示
                    res = dict(code=99, msg='交易ID已使用')
                    return await self.json_response(msg_en[10029])
            # ==================== 变更结束 ====================

            # 判断需要转发补单接口的三方订单
            if r['third_party_name'] in ['ospay', 'ospay_upi']:
                # 如果有使用自有收银台的三方代收，需要向三方转发UTR
                self.logger.info(f'准备转发补单信息，订单号: {code}，UTR: {utr}，第三方平台: {r["third_party_name"]}')
                await self.ds_utr_to_third(code, r, utr)
                self.logger.info(f'补单转发完成，订单号: {code}')
                self.logger.info("商户utr补单 订单：{code}，商户utr：{utr}".format(code=code, utr=utr))

            if 'script' in utr or len(utr) < 10:
                return await self.json_response(msg_en[10004])
            # 开始回调
            if not await self.order_success_ds(code, utr, trans_id):
                # 删除操作的key，防止回调占用
                busy_key = 'order_success_busy_{code}'.format(code=code)
                await self.redis.delete(busy_key)
                sql = " update orders_ds set utr=%s,trans_id=%s,time_payed=now() where code=%s and utr is null"
                if not await self.execute(sql, utr, trans_id, code):
                    return await self.json_response(msg_en[10000])
                self.logger.info("商户utr补单 订单：{code}，商户utr补单 失败：{utr}".format(code=code, utr=utr))
                return await self.json_response(msg_en[10005])
            else:
                self.logger.info("商户utr补单 订单：{code}，商户utr补单成功：{utr}".format(code=code, utr=utr))
                return await self.json_response(msg_en[0])
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg_en[10005])

    async def ds_utr_to_third(self, code, order, utr):
        """
        向三方平台转发补单
        不返回参数影响原有补单逻辑
        """
        if order['third_party_name'] in ['ospay', 'ospay_upi']:
            # 查一下订单，获取token
            otherpay = await self.get_result_by_condition('otherpay', '*', {'name': order['third_party_name']})
            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['mer_id'] = otherpay['merchant_id']
            data_post['utr'] = utr
            data_post['order_id'] = code
            data_post['sign'] = SignatureAndVerification.md5_sign(data_post, otherpay['key'])
            # 发起 POST
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            }
            response = requests.post('https://ospay2.com/api/pay/ds/utr', data=data_post, headers=headers, timeout=(5, 5), verify=False)
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f"{code} 向第三方 {order['third_party_name']} 转发补单结果: {result}")
                if str(result.get("code")) == '0':
                    self.logger.info(f"{code} 已成功向三方 {order['third_party_name']} 转发补单")
                else:
                    self.logger.info(f"{code} 向三方 {order['third_party_name']} 转发补单失败 {response.text}")
            else:
                self.logger.info(f"{code} 向三方 {order['third_party_name']} 转发补单失败")

    # UTR完成(收款为上传者) 与pay/order.py card_num 一致
    async def order_success_ds(self, code, utr, trans_id_param=''):
        # 查找订单
        sql_select_order = """select * from orders_ds where code=%s and status in (-1,1,2) order by id desc limit 1"""
        # 查找码商
        sql_select_partner = """select partner_id,upi from payment where id=%s"""
        # 查询银行记录
        sql_select_bank_record = """select * from bank_record where utr=%s and amount=%s and callback=0 and trade_type=1 order by id desc limit 1"""
        # 修改银行记录
        sql_update_bank_record = """update bank_record set callback=1,order_code=%s where id=%s and callback=0"""
        # 商户代理费率
        sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
        # 码商代理费率
        sql_select_rates_partner = """select rates from channel where code=%s"""
        # 更新系统余额
        sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
        # 更新订单
        sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,
                                        payment_id=%s,utr=%s,time_success=%s,status=3,upi=%s,trans_id=%s where code=%s and status in (-1,1,2) limit 1"""
        # 使用锁，5s使用自旋锁, 防止取消的同时回调
        count_circle = 0
        while True:
            busy_key = 'order_success_busy_{code}'.format(code=code)
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                break
            if count_circle >= 25:
                self.logger.warning('商户utr补单 utr:{utr}Do not operate frequently {code}'.format(utr=utr, code=code))
                return dict(code=99, msg='Do not operate frequently')
            time.sleep(0.2)
            count_circle = count_circle + 1

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 查询订单
                    if not await cur.execute(sql_select_order, code):
                        self.logger.error('商户utr补单 utr:{utr} 查不到相应的订单 {code}'.format(utr=utr, code=code))
                        return False
                    order = (await cur.fetchall())[0]
                    code = order['code']
                    amount = order['amount']
                    self.logger.error(f'order: {order}')
                    # 查询银行记录
                    if not await cur.execute(sql_select_bank_record, (utr, amount)):
                        self.logger.error('商户utr补单 utr:{utr} 查不到相应的bank_record {code}'.format(utr=utr, code=code))
                        return False
                    bank_record = (await cur.fetchall())[0]
                    payment_id = bank_record['payment_id']
                    trans_id = bank_record['trans_id']
                    self.logger.info(f"交易ID trans_id_param: {trans_id_param} , trans_id: {trans_id}")
                    if trans_id_param and trans_id and trans_id_param != trans_id:
                        self.logger.warning(f"交易ID trans_id_param: {trans_id_param} , trans_id: {trans_id}")
                        # 返回一个错误提示
                        # return await self.json_response(msg[10330])
                        await conn.rollback()
                        return False

                    # ----------------- 交易ID重复校验逻辑 -----------------
                    if trans_id:
                        sql_check_trans_id = """
                            SELECT code FROM orders_ds WHERE trans_id=%s AND id != %s LIMIT 1
                        """
                        # 这里的 _order[0]['id'] 是当前找到的订单的ID
                        existing_order = await self.query(sql_check_trans_id, trans_id, order['id'])

                        # 打印即将执行的查询日志，包含SQL和参数
                        self.logger.info(
                            f"新增：交易ID重复校验查询 | SQL: {sql_check_trans_id.strip()} | 参数: ({trans_id}, {order['id']})"
                        )

                        # 如果查询结果不为空，则说明有其他订单已使用此交易ID
                        if existing_order:
                            self.logger.warning(f"交易ID {trans_id} 已被其他订单使用。冲突订单号: {existing_order[0]['code']}")
                            # # 返回一个错误提示
                            # return await self.json_response(msg[10330])
                            await conn.rollback()
                            return False
                    # ==================== 变更结束 ====================

                    # 修改银行记录
                    if not await cur.execute(sql_update_bank_record, (code, bank_record['id'])):
                        self.logger.error('商户utr补单 utr:{utr} update_bank_record 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    # 码商查询
                    if not await cur.execute(sql_select_partner, payment_id):
                        self.logger.error('商户utr补单 utr:{utr} 码商查询 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    _payment = (await cur.fetchall())[0]
                    partner_id = _payment['partner_id']

                    # 订单里的码和码商id比较银行流水里的判断  1207
                    self.logger.info("Checking order values: order['partner_id']={}, partner_id={}".format(order['partner_id'], partner_id))
                    self.logger.info("Checking payment values: order['payment_id']={}, payment_id={}".format(order['payment_id'], payment_id))

                    # 比较前确保数据一致性，转换为字符串并去除前后空格
                    if str(order['partner_id']).strip() != str(partner_id).strip() or str(order['payment_id']).strip() != str(payment_id).strip():
                        # 如果不匹配，记录警告日志并回滚事务
                        self.logger.warning(
                            '订单中的码和码商ID与银行流水中的信息不匹配 | UTR: {} | 订单信息: [码商ID: {}, 支付码: {}] | 输入值: [码商ID: {}, 支付码: {}]'
                            .format(utr, order['partner_id'], order['payment_id'], partner_id, payment_id)
                        )
                        await conn.rollback()
                        return False

                    # 退掉额外扣款
                    if bank_record['ew_code']:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, amount,  bank_record['ew_code'], 0):
                            self.logger.error('商户utr补单 utr:{utr} 退掉额外扣款 失败 {code}'.format(utr=utr, code=code))
                            return False
                    # 补扣码商(非自身订单、过期订单)
                    if not order['partner_id'] == partner_id or order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0):
                            self.logger.error('商户utr补单 utr:{utr} 补扣码商(非自身订单、过期订单) 失败 {code}'.format(utr=utr, code=code))
                            return False
                    # 非自身订单并且未过期退款给旧码商
                    if not order['partner_id'] == partner_id and not order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount, code, 0):
                            self.logger.error('商户utr补单 utr:{utr} 退款给码商 失败 {code}'.format(utr=utr, code=code))
                            return False
                    # 增加商户余额
                    if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], code, 0):
                        self.logger.error('商户utr补单 utr:{utr} 增加商户余额 失败 {code}'.format(utr=utr, code=code))
                        return False
                    # 商户代理费用
                    earn_merchant = Decimal(0)
                    if order['earn_merchant'] > 0:
                        if not await cur.execute(sql_select_rates_merchant, (order['merchant_id'], order['channel_code'])):
                            await conn.rollback()
                            return False
                        merchant_rates = (await cur.fetchall())
                        for k, v in enumerate(merchant_rates):
                            if not k == 0 and v['rate']:
                                _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                                if _amount < 0:
                                    await conn.rollback()
                                    return False
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    return False
                                earn_merchant += _amount
                    # 增加码商佣金
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code, 3):
                        self.logger.error('商户utr补单 utr:{utr} 增加码商佣金 失败 {code}'.format(utr=utr, code=code))
                        return False
                    # 增加码商代理佣金
                    earn_partner = order['earn_partner_self']
                    if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                        return False
                    rates = (await cur.fetchall())[0]['rates'].split(',')
                    _partner_id = partner_id
                    for i in range(len(rates)):
                        partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                        if not partner['pid']:
                            break
                        _partner_id = partner['pid']
                        _amount = amount * Decimal(rates[i])
                        if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                            return False
                        earn_partner += _amount
                    # 系统盈利
                    earn_system = order['poundage'] - earn_merchant - earn_partner
                    if earn_system < 0:
                        self.logger.error('商户utr补单 utr:{utr} earn_system小于0 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    # 修改卡系统余额
                    if not await cur.execute(sql_update_payment, (amount, payment_id)):
                        self.logger.error('商户utr补单 utr:{utr} 修改卡系统余额 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    # 修改订单状态
                    time_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id, payment_id, utr, time_now, _payment['upi'], trans_id, code)):
                        self.logger.error('商户utr补单 utr:{utr} 修改订单状态 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    self.logger.info('商户utr补单 更新订单状态%s' % cur._last_executed)
                except Exception as e:
                    self.logger.warning('商户utr补单 确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                    await conn.rollback()
                    return False
                else:
                    await conn.commit()
                    await self.redis.publish('order_notify', code)
                    return True
