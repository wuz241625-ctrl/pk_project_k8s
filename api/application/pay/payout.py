"""Payout (代付) handler."""

import datetime
from decimal import Decimal

import requests
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg
from application.sign import SignatureAndVerification
from application.pay.payout_channel_guard import is_jazzcash_payout_request


# 代付订单
class Pay_df(BaseHandler):
    async def post(self):
        try:
            request_data = {k: self.get_argument(k, "") for k in self.request.arguments}
            r = await self.get_cache_result('sys_info', ['status_payment_service'], {'id': 1})
            if not r['status_payment_service']:
                self.logger.info('pay 支付服务关闭，不再接受新订单: {data}'.format(data=str(request_data)))
                return await self.json_response(data=msg[10031])  # 支付服务关闭，不再接受新订单

            r = await self.get_cache_result('sys_info', ['status_jazzcash_payout_service'], {'id': 1})
            if not r['status_jazzcash_payout_service'] and is_jazzcash_payout_request(request_data):
                self.logger.info('JazzCash单独代付渠道关闭，不再接受新订单: {data}'.format(data=str(request_data)))
                return await self.json_response(data=msg[10010])  # 通道维护

            is_locked = await self.check_dsdf_lock()
            if is_locked:
                return await self.json_response(data=msg[10026])  # 锁定状态，返回相应的消息

            try:
                data = request_data
                self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
            except Exception:
                self.logger.exception('参数异常')
                return await self.json_response(msg[10001])
            ip = await self.get_ip()
            ref = self.request.headers['Referer'] if 'Referer' in self.request.headers else ''
            self.logger.info('pay_df 收到参数{data},referrer={ref},ip={ip}'.format(data=str(data), ref=ref, ip=ip))
            r = await self.get_cache_result('sys_info', ['status_df'], {"id": 1})
            if r['status_df'] == 0:
                return await self.json_response(data=msg[10022])
            if 'notice_api' not in data.keys():
                data['notice_api'] = None
                self.data_receive_filter_xss['notice_api'] = None

            valid_keys = ['mer_id', 'order_id', 'gateway', 'amount', 'account', 'user', 'bank_code', 'bank', 'notify',
                          'notice_api', 'sign']
            not_null_keys = ['mer_id', 'order_id', 'gateway', 'amount', 'account', 'user', 'bank_code', 'bank', 'sign']

            if not await self.is_valid_key(data, valid_keys):
                return await self.json_response(data=msg[10002])

            if await self.is_null(data, not_null_keys):
                return await self.json_response(data=msg[10003])

            self.logger.info("检查接收的数据和过滤后数据是否一致")
            if not await self.check_different_new(data, self.data_receive_filter_xss, valid_keys):
                self.logger.info('pay 参数非法{data}'.format(data=str(data)))
                return await self.json_response(data=msg[10002])

            merchant_id = int(data['mer_id'])
            amount = Decimal(data['amount'])
            if '.' in str(amount) and not set(str(amount).split('.')[1]) == {'0'}:
                return await self.json_response(data=msg[10024])
            merchant_code = data['order_id']

            # 获取并检查商户
            keys = {'status', 'mc_key', 'status', 'balance', 'fee_df', 'rate_df', 'pid', 'ip_df', 'status_df', 'amount_fixed', 'amount_fixed_max', 'target_payment'}
            merchant = await self.get_result_by_condition('merchant', keys, {'id': merchant_id})
            if not merchant:
                return await self.json_response(data=msg[10004])
            if merchant['status'] == 0:
                return await self.json_response(data=msg[10005])
            if merchant['status_df'] == 0:
                return await self.json_response(data=msg[10023])

            # region 检查商户固定金额是否有效
            amount_fixed_min = merchant.get('amount_fixed')
            amount_fixed_min = 0 if amount_fixed_min is None else amount_fixed_min

            amount_fixed_max = merchant.get('amount_fixed_max')
            amount_fixed_max = 0 if amount_fixed_max is None else amount_fixed_max

            # if amount < merchant['amount_fixed']:
            #     return await self.json_response(data=msg[10011])
            # 记录输入的金额和商户的固定金额
            self.logger.info("检查金额逻辑: 输入金额: %s, 商户限制金额: %s - %s", amount, amount_fixed_min, amount_fixed_max)

            if amount_fixed_min <= 0:
                self.logger.info("商户最小限制金额小于等于0，不参与判断.")
            else:
                # 检查逻辑
                if amount < amount_fixed_min:
                    self.logger.warning("金额小于商户最小限制金额: %s < %s", amount, amount_fixed_min)
                    return await self.json_response(data=msg[10011])
                else:
                    self.logger.info("金额大于或等于商户最小限制金额: %s >= %s", amount, amount_fixed_min)

            if amount_fixed_max <= 0:
                self.logger.info("商户最大限制金额小于等于0，不参与判断.")
            else:
                # 检查逻辑
                if amount > amount_fixed_max:
                    self.logger.warning("金额小于商户最大限制金额: %s < %s", amount, amount_fixed_max)
                    return await self.json_response(data=msg[10011])
                else:
                    self.logger.info("金额小于或等于商户最大限制金额: %s >= %s", amount, amount_fixed_max)
            # endregion

            # 检查ip
            merchant['ip_df'] = merchant['ip_df'] if merchant['ip_df'] else ''
            ips = [_ip.strip() for _ip in merchant['ip_df'].split(',') if _ip]
            if not ip in ["127.0.0.1", "::1"] and (not merchant['ip_df'] or not ip in ips):
                return await self.json_response(data=msg[10000])

            # 验签
            sign_data = data
            if not SignatureAndVerification.md5_verify(sign_data, sign_data['sign'], merchant['mc_key']):
                return await self.json_response(msg[10006])

            # 检查IFSC
            ifsc = data['bank_code']
            if not await self.query("""select * from bank_ifsc where ifsc=%s limit 1""", ifsc):
                try:
                    url = "https://ifsc.razorpay.com/{}".format(ifsc)
                    r = requests.get(url, timeout=(5, 5), verify=False)
                    if r.text == '"Not Found"':
                        return await self.json_response(msg[10017])
                except Exception:
                    return await self.json_response(msg[10017])

            # 检查商户费率
            if not merchant['rate_df'] and not merchant['fee_df']:
                return await self.json_response(data=msg[10013])
            # 检查商户余额
            poundage = amount * merchant['rate_df'] + merchant['fee_df']
            if merchant['balance'] < amount + poundage:
                return await self.json_response(msg[10015])
            # 检查所有上级费率并计算代理费用
            earn_merchant = Decimal(0)
            if merchant['pid']:
                sql = """select id,rate_df from
                        (select
                            @orgId id,
                            (select rate_df from merchant where id = @orgId) rate_df,
                            (select @orgId := pid from merchant where id = @orgId) pid
                        from (select @orgId := %s) vars,merchant) t where id is not null order by pid desc"""
                merchant_prates = await self.query(sql, merchant_id)
                if not merchant_prates:
                    return await self.json_response(data=msg[10013])
                merchant_prate = Decimal(0)
                for k, v in enumerate(merchant_prates):
                    if v['rate_df'] < 0 or (k > 0 and v['rate_df'] > merchant_prates[k - 1]['rate_df']):
                        return await self.json_response(data=msg[10013])
                    merchant_prate = Decimal(v['rate_df'])
                earn_merchant = amount * (merchant['rate_df'] - merchant_prate)
                if earn_merchant < 0:
                    return await self.json_response(data=msg[10013])
            # 码商盈利
            rate_df = (await self.get_cache_result('sys_info', ['rate_df']))['rate_df']
            earn_partner_self = rate_df * amount

            # 系统盈利
            earn_system = poundage - earn_merchant - earn_partner_self
            if earn_system <= Decimal(0):
                return await self.json_response(data=msg[10013])
            # 检查订单重复
            if await self.get_result_by_condition('orders_df', ['id'], {'merchant_code': merchant_code}):
                return await self.json_response(data=msg[10014])
            # 生成订单
            order_data = dict()
            order_data['code'] = await self.create_order_code('F')  # 订单号
            order_data['amount'] = amount  # 金额
            order_data['poundage'] = poundage  # 手续费
            order_data['realpay'] = amount + poundage  # 结算金
            order_data['merchant_id'] = merchant_id  # 商户ID
            order_data['merchant_code'] = merchant_code  # 商户订单号
            order_data['merchant_rate'] = merchant['rate_df']  # 商户费率
            order_data['earn_merchant'] = earn_merchant  # 商户代理盈利
            order_data['earn_partner_self'] = earn_partner_self  # 码商盈利
            order_data['earn_system'] = earn_system  # 系统盈利
            order_data['ifsc'] = data['bank_code']
            order_data['payment_account'] = data['account']
            order_data['payment_name'] = data['user']
            order_data['payment_bank'] = data['bank']
            order_data['notify'] = data['notify']  # 通知地址
            order_data['target_payment'] = merchant['target_payment']  # 专卡专户

            # 检查自动代付开关状态并设置payout_type字段
            try:
                emergency_stop = await self.redis.get("easypaisa_emergency_stop")
                # 如果紧急停止为"0"或未设置，启用自动代付(payout_type=1)，否则设为0(手动代付)
                order_data['payout_type'] = 1 if (emergency_stop is None or emergency_stop == b"0" or emergency_stop == "0") else 0
                self.logger.info(f"紧急停止状态: {emergency_stop}, payout_type: {order_data['payout_type']}")
            except Exception as e:
                # 如果Redis查询失败，默认设为0(手动代付)
                order_data['payout_type'] = 0
                self.logger.warning(f"获取紧急停止状态失败，默认设置为手动代付: {e}")

            # 扣除商户余额并创建订单
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 扣除商户余额
                        if not await self.change_balance(conn, cur, 'merchant', merchant_id, -order_data['realpay'],order_data['code'], 1, None, merchant_code):
                            await conn.rollback()
                            return await self.json_response(data=msg[10014])
                        # 生成订单
                        keys = ', '.join(order_data.keys())
                        values = ', '.join(['%s'] * len(order_data))
                        sql = "insert into {table} ({keys}) values ({vals})".format(table="orders_df", keys=keys, vals=values)
                        if not await cur.execute(sql, tuple(order_data.values())):
                            await conn.rollback()
                            return await self.json_response(data=msg[10014])
                    except Exception as e:
                        self.logger.warning(
                            '下单失败,merchant_id={merchant_id},非法数据={e}'.format(merchant_id=merchant_id, e=e))
                        await conn.rollback()
                        return await self.json_response(data=msg[10014])
                    else:
                        await conn.commit()
                        return await self.json_response(({'code': 0, 'massage': '下单成功', 'order_code': order_data['code'], 'amount': amount}))
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10014])

    # in_mins 分钟内到达订单限制，就限制下单 mins 分钟
    async def order_gateway_busy(self, gateway, merchant_id, orders, in_mins, mins):
        mins_ago = datetime.datetime.now() - datetime.timedelta(minutes=in_mins)
        sql_allow = "select count(*) as trx from orders_ds where time_create > %s and status in (0,1,2) and gateway=%s"
        ret = await self.query(sql_allow, mins_ago, gateway)
        if not ret:
            return True
        if ret[0]['trx'] > orders:
            self.logger.info(
                '通道-{gateway}-{in_mins}分钟内到达限制单量{orders}，限制提单时间{mins}分钟,merchant_id={merchant_id}'.format(
                    gateway=gateway, in_mins=in_mins, orders=orders, mins=mins,
                    merchant_id=merchant_id))
            busy_key = 'order_gateway_busy_{gateway}'.format(gateway=gateway)
            await self.redis.set(key=busy_key, value=1, expire=mins * 60)
            return False
        return True
