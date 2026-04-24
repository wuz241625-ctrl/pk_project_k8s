from datetime import time, datetime
from decimal import Decimal

from application.base import BaseHandler
from application.lakshmi_api.error_handler import handle_errors
from aiomysql import DictCursor

from application.message import msg_en, msg
from application.sign import SignatureAndVerification


class commandListener(BaseHandler):
    def getDefault(self, *args):
        self.logger.info(f"进入 getDefault 方法, 参数: {args}")
        return None, '命令错误'

    async def getMerchant(self, mid):
        self.logger.info(f"进入 getMerchant 方法, mid: {mid}")
        if not mid:
            self.logger.info("参数错误: mid 为空")
            return None, '参数错误'
        data = await self.query("SELECT id, balance, balance_frozen FROM `merchant` WHERE id=%s", mid)
        self.logger.info(f"查询商户信息结果: {data[0]}")
        return data[0], None

    async def getOrderInfo(self, token):
        self.logger.info(f"进入 getOrderInfo 方法, token: {token}")
        if not token:
            self.logger.info("参数错误: token 为空")
            return None, '参数错误'
        args = await self.token_decode(token)
        self.logger.info(f"token 解码结果: {args}")
        if args in [10016, 10017]:
            self.logger.info(f"数据错误: args 为 {args}")
            return None, '数据错误'
        args = args.split(',')
        merchant_id = args[0]
        merchant_code = args[1]
        self.logger.info(f"解构参数: merchant_id={merchant_id}, merchant_code={merchant_code}")
        
        ds = await self.get_result_by_condition("orders_ds", ['code', 'status', 'utr', 'amount'], { 'merchant_code': merchant_code, 'merchant_id': merchant_id})
        self.logger.info(f"查询 orders_ds 结果: {ds}")
        
        df = await self.get_result_by_condition("orders_df", ['code', 'status', 'utr', 'amount'], { 'merchant_code': merchant_code, 'merchant_id': merchant_id})
        self.logger.info(f"查询 orders_df 结果: {df}")
        
        list = []
        if ds.get('code', None):
            self.logger.info("orders_ds 有数据, 添加到列表")
            list.append(ds)
        if df.get('code', None):
            self.logger.info("orders_df 有数据, 添加到列表")
            list.append(df)
            
        self.logger.info(f"最终订单信息列表: {list}")
        return list, None

    async def getVolume(self, mid):
        self.logger.info(f"进入 getVolume 方法, mid: {mid}")
        if not mid:
            self.logger.info("参数错误: mid 为空")
            return None, '参数错误'
        
        ds_total = await self.query('SELECT count(1) as allTotal FROM `orders_ds` WHERE DATE(time_create) = CURDATE() AND merchant_id=%s', mid)
        self.logger.info(f"查询 orders_ds 当日总单量结果: {ds_total}")
        
        df_total = await self.query('SELECT count(1) as allTotal FROM `orders_df` WHERE DATE(time_create) = CURDATE() AND merchant_id=%s', mid)
        self.logger.info(f"查询 orders_df 当日总单量结果: {df_total}")
        
        ds = await self.query('SELECT count(1) as total, COALESCE(sum(amount), 0) as totalAmount FROM `orders_ds` WHERE status=4 AND DATE(time_success) = CURDATE() AND merchant_id=%s', mid)
        self.logger.info(f"查询 orders_ds 当日成功单量和总金额结果: {ds}")
        
        df = await self.query('SELECT count(1) as total, COALESCE(sum(amount), 0) as totalAmount FROM `orders_df` WHERE status=4 AND DATE(time_success) = CURDATE() AND merchant_id=%s', mid)
        self.logger.info(f"查询 orders_df 当日成功单量和总金额结果: {df}")
        
        ds[0]['allTotal'] = ds_total[0]['allTotal']
        df[0]['allTotal'] = df_total[0]['allTotal']
        
        self.logger.info(f"最终返回的统计数据: S={ds[0]}, F={df[0]}")
        return {
            'S': ds[0],
            'F': df[0]
        }, None

    async def get(self, cmd):
        self.logger.info(f"进入 get 方法, cmd: {cmd}")
        if not cmd:
            self.logger.info("参数错误: cmd 为空")
            return await self.json_response(msg_en[10000]);
        
        cases = {
            'mid': self.getMerchant,
            'info': self.getOrderInfo,
            'balance': self.getMerchant,
            'volume': self.getVolume,
            'sign': self.getSign
        }
        
        self.logger.info(f"根据 cmd='{cmd}' 匹配到的方法: {cases.get(cmd, self.getDefault).__name__}")
        data, msg = await cases.get(cmd, self.getDefault)(self.get_argument("args", None))
        self.logger.info(f"调用方法 '{cmd}' 结果: data={data}, msg={msg}")
        
        return await self.json_response({ 'data': data, 'msg': msg })

    async def getSign(self, token):
        self.logger.info(f"进入 getSign 方法, token: {token}")
        if not token:
            self.logger.info("参数错误: token 为空")
            return None, '参数不正确'
            
        args = await self.token_decode(token)
        self.logger.info(f"token 解码结果: {args}")
        
        args = args.split(',')
        mid = args[0]
        mcode = args[1]
        utr = args[2]
        self.logger.info(f"解构参数: mid={mid}, mcode={mcode}, utr={utr}")

        order = await self.get_result_by_condition('orders_ds',
                                                   ['code', 'amount', 'realpay', 'status', 'time_create', 'time_success', 'time_updated', 'utr', 'upi', 'third_party_name'],
                                                   { 'merchant_id': mid, 'merchant_code': mcode });
        self.logger.info(f"查询订单结果: {order}")
        
        if not order:
            self.logger.info("订单不存在")
            return None, '订单不存在'
        
        if not order['status'] in [-1, 1, 2]:
            self.logger.info(f"订单状态为 {order['status']}, 查询成功")
            return { 'order': order }, '查询成功'
        
        merchant = await self.get_result_by_condition('merchant', ['mc_key', 'status'], {'id': mid})
        self.logger.info(f"查询商户信息结果: {merchant}")
        
        if not merchant:
            self.logger.info("商户信息查询失败")
            return None, '商户信息查询失败'

        sign = SignatureAndVerification.md5_sign({ 'mer_id': mid, 'order_id': mcode, 'utr': utr, 'robot': 1 }, merchant['mc_key'])
        self.logger.info(f"生成签名: {sign}")

        return {
            'order': order,
            'sign': sign
        }, '签名成功'

    # 弃用
    async def updateUtr(self, token):
        self.logger.info(f"进入 updateUtr 方法, token: {token}")
        if not token:
            self.logger.info("参数错误: token 为空")
            return False, '参数不正确'
            
        args = await self.token_decode(token)
        self.logger.info(f"token 解码结果: {args}")
        
        args = args.split(',')
        mid = args[0]
        mcode = args[1]
        utr = args[2]
        self.logger.info(f"解构参数: mid={mid}, mcode={mcode}, utr={utr}")

        self.logger.info("开始自旋锁, 防止取消的同时回调")
        count_circle = 0
        while True:
            busy_key = 'order_success_busy_{code}'.format(code=mcode)
            self.logger.info(f"尝试获取锁: {busy_key}, 当前尝试次数: {count_circle}")
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                self.logger.info(f"成功获取锁: {busy_key}")
                break
            if count_circle >= 25:
                self.logger.warning('merchant_code:{}有其他进程正在处理中'.format(mcode))
                return False, '正在处理中...'
            time.sleep(0.2)
            count_circle = count_circle + 1

        async with self.application.db.acquire() as conn:
            self.logger.info("获取数据库连接")
            async with conn.cursor(DictCursor) as cur:
                try:
                    self.logger.info("查询订单: select * from orders_ds where merchant_id=%s and merchant_code=%s and status in (-1,1,2)", [mid,mcode])
                    if not await cur.execute('select * from orders_ds where merchant_id=%s and merchant_code=%s and status in (-1,1,2)', [mid,mcode]):
                        self.logger.warning("未查询到需要补单的订单")
                        return False, '未查询到需要补单的订单'
                    order = (await cur.fetchall())[0]
                    self.logger.info(f"查询到订单信息: {order}")
                    
                    self.logger.info("查询银行记录: select * from bank_record where utr=%s and amount=%s and callback=0 and trade_type=1", (utr, amount))
                    if not await cur.execute('select * from bank_record where utr=%s and amount=%s and callback=0 and trade_type=1 ', (utr, amount)):
                        self.logger.warning("未查询到银行流水记录")
                        return False, '未查询到银行流水记录'
                    bank_record = (await cur.fetchall())[0]
                    self.logger.info(f"查询到银行记录: {bank_record}")
                    
                    payment_id = bank_record['payment_id']
                    
                    self.logger.info("修改银行记录: update bank_record set callback=1,order_code=%s where id=%s and callback=0", (order['code'], bank_record['id']))
                    if not await cur.execute('update bank_record set callback=1,order_code=%s where id=%s and callback=0', (order['code'], bank_record['id'])):
                        await conn.rollback()
                        self.logger.warning("修改流水记录失败")
                        return False, '修改流水记录失败'
                    
                    self.logger.info("查询码商信息: select partner_id,upi from payment where id=%s", payment_id)
                    if not await cur.execute('select partner_id,upi from payment where id=%s', payment_id):
                        await conn.rollback()
                        self.logger.warning("查询支付信息失败")
                        return False, '查询支付信息失败'
                    _payment = (await cur.fetchall())[0]
                    self.logger.info(f"查询到支付信息: {_payment}")
                    
                    partner_id = _payment['partner_id']
                    
                    if bank_record['ew_code']:
                        self.logger.info("存在额外扣款，开始退款")
                        if not await self.change_balance(conn, cur, 'partner', partner_id, amount, bank_record['ew_code'], 0):
                            self.logger.warning("退还扣款失败")
                            return False, '退还扣款失败'
                    
                    if not order['partner_id'] == partner_id or order['status'] == -1:
                        self.logger.info("补扣码商: 非自身订单或过期订单")
                        if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, order['code'], 0):
                            self.logger.warning("增加余额失败")
                            return False, '增加余额失败'
                    
                    if not order['partner_id'] == partner_id and not order['status'] == -1:
                        self.logger.info("非自身订单并且未过期，退款给旧码商")
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount, order['code'], 0):
                            self.logger.warning("增加旧码商余额失败")
                            return False, '增加余额失败'
                    
                    self.logger.info("增加商户余额")
                    if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], order['code'], 0):
                        self.logger.warning("增加商户余额失败")
                        return False, '增加余额失败'
                    
                    earn_merchant = Decimal(0)
                    if order['earn_merchant'] > 0:
                        self.logger.info("商户代理费用大于0，开始计算")
                        
                        sql_merchant_rates = 'select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc'
                        self.logger.info(f"查询商户代理信息: {sql_merchant_rates} with params: {(order['merchant_id'], order['channel_code'])}")
                        
                        if not await cur.execute(sql_merchant_rates, (order['merchant_id'], order['channel_code'])):
                            await conn.rollback()
                            self.logger.warning("查询商户代理信息失败")
                            return False, '查询商户代理信息失败'
                        merchant_rates = (await cur.fetchall())
                        self.logger.info(f'订单号{order["code"]}商户汇率{merchant_rates}')
                        
                        for k, v in enumerate(merchant_rates):
                            if not k == 0 and v['rate']:
                                _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                                self.logger.info(f'订单号{order["code"]}手续费{_amount}')
                                
                                if _amount < 0:
                                    await conn.rollback()
                                    self.logger.warning("商户代理手续费计算错误")
                                    return False, '商户代理手续错误'
                                
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, order['code'], 3):
                                    self.logger.warning("修改商户代理余额失败")
                                    return False, '修改商户代理余额失败'
                                earn_merchant += _amount
                                
                    self.logger.info("增加码商佣金")
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], order['code'], 3):
                        self.logger.warning("码商佣金增加失败")
                        return False, '码商佣金增加失败'
                    
                    self.logger.info("开始增加码商代理佣金")
                    earn_partner = order['earn_partner_self']
                    
                    self.logger.info("查询渠道费率: select rates from channel where code=%s", order['channel_code'])
                    if not await cur.execute('select rates from channel where code=%s', order['channel_code']):
                        self.logger.warning("查询渠道费率失败")
                        return False, '查询渠道费率失败'
                    rates = (await cur.fetchall())[0]['rates'].split(',')
                    self.logger.info(f"渠道费率: {rates}")

                    _partner_id = partner_id
                    for i in range(len(rates)):
                        partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                        self.logger.info(f"查询码商代理: {partner}")
                        if not partner['pid']:
                            self.logger.info("没有上级代理，跳出循环")
                            break
                        _partner_id = partner['pid']
                        _amount = amount * Decimal(rates[i])
                        self.logger.info(f"计算码商代理佣金: {_amount}")
                        
                        if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, order['code'], 3):
                            self.logger.warning("码商代理佣金增加失败")
                            return False, '码商代理佣金增加失败'
                        earn_partner += _amount
                        
                    earn_system = order['poundage'] - earn_merchant - earn_partner
                    self.logger.info(f'订单号{order["code"]}系统盈利{earn_system}')
                    
                    if earn_system < 0:
                        await conn.rollback()
                        self.logger.warning("系统盈利错误")
                        return False, '系统盈利错误'
                    
                    self.logger.info("修改卡系统余额")
                    if not await cur.execute('update payment set sys_balance=sys_balance+%s where id=%s', (amount, payment_id)):
                        await conn.rollback()
                        self.logger.warning("修改系统余额失败")
                        return False, '修改系统余额失败'
                    
                    self.logger.info("修改订单状态")
                    time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    sql_update_order = 'update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s, payment_id=%s,utr=%s,time_success=%s,status=3,upi=%s where merchant_id=%s and code=%s and status in (-1,1,2) limit 1'
                    if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id, payment_id, utr, time_now, _payment['upi'], mid, order['code'])):
                        await conn.rollback()
                        self.logger.warning("订单状态修改失败")
                        return False, '订单状态修改失败'
                        
                    self.logger.info('更新订单状态%s' % cur._last_executed)
                    
                    self.logger.info("登记操作记录")
                    if not await self.create_result('operate', {'type': 11, 'admin_id': 1, 'ip': await self.get_ip()}):
                        await conn.rollback()
                        self.logger.warning("操作登记失败")
                        self.logger.warning(cur._last_executed)
                        return False, '操作登记失败'
                        
                except Exception as e:
                    self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=order['code'], e=e))
                    await conn.rollback()
                    return False, '确认订单失败，系统异常'
                else:
                    await conn.commit()
                    self.logger.info(f"事务提交成功, 发布 order_notify: {order['code']}")
                    await self.redis.publish('order_notify', order['code'])
                    
        return True, '补单成功'



class ExistPaymentByUpi(BaseHandler):
    @handle_errors
    async def post(self):
        upi = self.get_body_argument('upi')
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                query_payment_by_upi = "select count(1) as cnt from payment where upi = %s"
                if not await cur.execute(query_payment_by_upi, (upi,)):
                    self.logger.warning(f"参数: upi={upi} 查询失败")
                    return self.write({
                        "data": {
                            "exist": False
                        }})
                query_result = await cur.fetchone()

                if query_result['cnt'] > 0:
                    return self.write({
                        "data": {
                            "exist": True
                        }})
                else:
                    return self.write({
                        "data": {
                            "exist": False
                        }})

class getReceiptByOrderId(BaseHandler):

    async def post(self):
        interface_function_name = 'getReceiptByOrderId'
        order_id = self.get_body_argument('order_id')
        mid = self.get_body_argument('mid')
        self.logger.warning(f"{interface_function_name}, 请求参数: order_id = {order_id}")

        code = await self.token_decode(order_id)

        target_cols = ['code', 'amount', 'status', 'ifsc', 'utr', 'debit_account', 'payment_account', 'payment_name',
                       'time_success']
        target_table = "orders_df"

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                query_orderdf_by_code_sql = 'select {keys} from {table} where merchant_id = %s AND merchant_code = %s'.format(
                    keys=','.join(target_cols), table=target_table)
                if not await cur.execute(query_orderdf_by_code_sql, (mid, code,)):
                    self.logger.warning(f"{interface_function_name}, code ={order_id} 数据查询无结果!")
                    return self.write({
                        "code": -1,
                        "data": None})

                query_result = await cur.fetchone()

                # 转换 Decimal 为字符串
                if query_result and 'amount' in query_result:
                    query_result['amount'] = str(query_result['amount'])

                # 转换 datetime 为字符串
                if query_result and 'time_success' in query_result and query_result['time_success'] is not None:
                    query_result['time_success'] = query_result['time_success'].strftime('%Y-%m-%d %H:%M:%S')

                return self.write({"code": 0, "data": query_result})