import time

from aiomysql import DictCursor
from decimal import Decimal
from datetime import datetime

# UTR完成(收款为上传者)
async def order_success_ds(self, code, utr=None):
    # 查找订单(限定60分钟内防止后期全部超时又回调的风险)
    sql_select_order = """select * from orders_ds where code=%s and status in (0,-1,1,2) and time_create>date_sub(now(), interval 60 minute) order by id desc limit 1"""
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
                                    payment_id=%s,utr=%s,time_success=%s,status=3,upi=%s where code=%s and status in (0,-1,1,2) limit 1"""

    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'order_success_busy_{code}'.format(code=code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            break
        if count_circle >= 25:
            self.logger.warning('utr:{utr}Do not operate frequently {code}'.format(utr=utr, code=code))
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle = count_circle + 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查询订单
                if not await cur.execute(sql_select_order, code):
                    self.logger.info("查询不到或超时30分钟：{}".format(code))
                    return False
                order = (await cur.fetchall())[0]
                code = order['code']
                amount = order['amount']
                
                # 检查订单是否启用了小数点回调功能
                is_decimal_callback = False
                original_amount = None
                
                # 如果订单有original_amount字段并且值不为空，说明启用了小数点回调功能
                if 'original_amount' in order and order['original_amount']:
                    is_decimal_callback = True
                    original_amount = order['original_amount']
                    self.logger.info("检测到小数点回调订单：{}, 实际金额：{}, 原始金额：{}".format(
                        code, amount, original_amount))
                
                partner_id= None
                payment_id = None
                # 查询银行记录
                # if not await cur.execute(sql_select_bank_record, (utr, amount)):
                #     return False
                # bank_record = (await cur.fetchall())[0]
                # payment_id = bank_record['payment_id']
                # 修改银行记录
                # if not await cur.execute(sql_update_bank_record, (code, bank_record['id'])):
                #     await conn.rollback()
                #     return False
                # 码商查询
                if not await cur.execute(sql_select_partner, payment_id):
                    await conn.rollback()
                    return False
                _payment = (await cur.fetchall())[0]
                partner_id = _payment['partner_id']
                # # 补扣码商(非自身订单、过期订单)
                # if not order['partner_id'] == partner_id or order['status'] == -1:
                #     if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0):
                #         return False
                # # 非自身订单并且未过期退款给旧码商
                # if not order['partner_id'] == partner_id and not order['status'] == -1:
                #     if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount,
                #                                      code, 0):
                #         return False
                # 增加商户余额
                if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], code, 0):
                    return False
                # 商户代理费用
                earn_merchant = Decimal(0)
                earn_partner = Decimal(0)
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
                # if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code,
                #                                  3):
                #     return False
                # 增加码商代理佣金
                # earn_partner = order['earn_partner_self']
                # if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                #     return False
                # rates = (await cur.fetchall())[0]['rates'].split(',')
                # _partner_id = partner_id
                # for i in range(len(rates)):
                #     partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                #     if not partner['pid']:
                #         break
                #     _partner_id = partner['pid']
                #     _amount = amount * Decimal(rates[i])
                #     if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                #         return False
                #     earn_partner += _amount
                # 系统盈利
                earn_system = order['poundage'] - earn_merchant - earn_partner
                if earn_system < 0:
                    await conn.rollback()
                    return False
                # 修改卡系统余额
                # if not await cur.execute(sql_update_payment, (amount, payment_id)):
                #     await conn.rollback()
                #     return False
                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id, payment_id, utr, time_now, _payment['upi'], code)):
                    await conn.rollback()
                    return False
                self.logger.info('更新订单状态%s' % cur._last_executed)
            except Exception as e:
                self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                await conn.rollback()
                return False
            else:
                await conn.commit()
                self.logger.warning('通知订单,code={code}'.format(code=code))
                await self.redis.publish('order_notify', code)
                return True
            
# UTR完成(收款为上传者)
async def order_success_ds_third(self, code, utr=None, **kwargs):
    # print(f"Starting order_success_ds_third with code: {code}, UTR: {utr}")
    # 查找订单(限定60分钟内防止后期全部超时又回调的风险) 
    sql_select_order = """select * from orders_ds where code=%s and status in (0,-1,1,2)  and time_create>date_sub(now(), interval 60 minute) order by id desc limit 1"""
    # 商户代理费率
    sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant 
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join 
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
    # 更新订单
    sql_update_order = """update orders_ds set earn_merchant=%s, earn_partner=%s, earn_system=%s, partner_id=%s,
                                    payment_id=%s, utr=%s, time_success=%s, status=3, upi=%s where code=%s and status in (0,-1,1,2) limit 1"""
    upi = kwargs.get('upi')

    # 使用锁，5s使用自旋锁, 防止取消的同时回调
    count_circle = 0
    while True:
        busy_key = 'order_success_busy_{code}'.format(code=code)
        if await self.redis.setnx(busy_key, 1):
            await self.redis.expire(busy_key, 10)
            self.logger.warning(f"Lock acquired for code: {code}")
            break
        if count_circle >= 25:
            # self.logger.info(f"Retry limit reached for code: {code}")
            self.logger.warning(f"utr:{utr} Do not operate frequently {code}")
            return dict(code=99, msg='Do not operate frequently')
        time.sleep(0.2)
        count_circle += 1

    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 查询订单
                # print(f"Executing SQL: {sql_select_order} with code: {code}")
                if not await cur.execute(sql_select_order, code):
                    self.logger.warning(f"查询不到或超时60分钟：{code}")
                    # 只有当 UTR 不为 None 时才更新
                    if utr is not None:
                        sql_update_order = """UPDATE orders_ds SET utr=%s WHERE code=%s AND status IN (0,-1,1,2) LIMIT 1"""
                        await cur.execute(sql_update_order, (utr, code))
                        self.logger.info(f"UTR 更新成功，订单号: {code} sql: {sql_update_order}，UTR: {utr}")
                        await conn.commit()
                    else:
                        self.logger.info(f"UTR 为空，跳过更新，订单号: {code}")
                    
                    return False
                order = (await cur.fetchall())[0]
                # print(f"Order found: {order}")
                code = order['code']
                amount = order['amount']
                partner_id = None
                payment_id = None
                upi = upi if upi else order['upi']

                # 增加商户余额
                # print(f"Increasing merchant balance for merchant_id: {order['merchant_id']}, amount: {order['realpay']}")
                if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], code, 0):
                    self.logger.warning("Failed to increase merchant balance.")
                    return False
                
                # 商户代理费用
                earn_merchant = Decimal(0)
                if order['earn_merchant'] > 0:
                    # print("Calculating merchant agent fees.")
                    if not await cur.execute(sql_select_rates_merchant, (order['merchant_id'], order['channel_code'])):
                        self.logger.warning("Failed to fetch merchant rates.")
                        await conn.rollback()
                        return False
                    merchant_rates = await cur.fetchall()
                    # print(f"Merchant rates fetched: {merchant_rates}")
                    for k, v in enumerate(merchant_rates):
                        if k != 0 and v['rate']:
                            _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                            if _amount < 0:
                                self.logger.warning(f"Invalid amount calculated: {_amount}")
                                await conn.rollback()
                                return False
                            if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                self.logger.warning(f"Failed to update balance for merchant {v['id']} with amount {_amount}.")
                                return False
                            earn_merchant += _amount
                    # print(f"Total merchant earnings: {earn_merchant}")

                # 系统盈利
                earn_system = order['poundage'] - earn_merchant
                if earn_system < 0:
                    self.logger.warning(f"System earnings calculation error, earnings: {earn_system}")
                    await conn.rollback()
                    return False

                # 修改订单状态
                time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # print(f"Updating order status with earn_merchant: {earn_merchant}, earn_system: {earn_system}, code: {code}")
                if not await cur.execute(sql_update_order, (earn_merchant, 0, earn_system, partner_id, payment_id, utr, time_now, upi, code)):
                    self.logger.warning("Failed to update order status.")
                    self.logger.warning("SQL: %s", sql_update_order)
                    self.logger.warning("Params: %s", (earn_merchant, 0, earn_system, partner_id, payment_id, utr, time_now, upi, code))
                    await conn.rollback()
                    return False
                # print(f"Order status updated successfully for code: {code}")
                
            except Exception as e:
                # print(f"Exception occurred: {e}")
                self.logger.warning(f"确认订单失败, code={code}, 异常={e}")
                await conn.rollback()
                return False
            else:
                await conn.commit()
                # self.logger.info(f"Order successfully processed for code: {code}")
                self.logger.warning(f"通知订单, code={code}")
                await self.redis.publish('order_notify', code)
                return True
