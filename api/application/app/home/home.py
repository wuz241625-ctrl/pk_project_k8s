import datetime
import bcrypt

from decimal import Decimal
from aiomysql import DictCursor

from application.message import msg
from application.timezone import display_today_between


async def Home(self, action, data):
    if action == 'getuserinfo':
        return await getUserInfo(self)
    if action == 'getorderinfo':
        return await getOrder(self, data)
    if action == 'charge':
        return await charge(self, data)
    if action == 'withdraw':
        return await withdraw(self, data)


# 获取用户代收信息
async def getUserInfo(self):
    # 余额
    user_data = await self.get_result_by_condition('partner', ['balance', 'balance_frozen', 'balance_deposit'], {'id': self.current_user['id']})
    user_data['balance_all'] = user_data['balance'] + user_data['balance_deposit']
    # 交易中余额
    user_data['balance_locking'] = user_data['balance_frozen']
    sql = """select sum(amount) as balance_locking from orders_ds where partner_id=%s and status in (1,2)"""
    balance_locking = (await self.query(sql, self.current_user['id']))[0]['balance_locking']
    if balance_locking:
        user_data['balance_locking'] += balance_locking
    user_data['balance_all'] += user_data['balance_locking']
    # 今日佣金查询
    sql = """select sum(r.amount) as amount_all,sum(if(s.id is null and f.id is null,r.amount,0)) as amount_other from 
    balance_record r left join orders_ds s on s.code=r.code and s.partner_id=user_id left join orders_df f on 
    f.code=r.code and f.partner_id=user_id where r.time_create>%s and record_type=3 and user_type=0 and user_id=%s"""
    today = display_today_between('time_create')['start']
    values = [today, self.current_user['id']]
    r = (await self.query(sql, *values))[0]
    user_data['amount_all'] = r['amount_all'] if r['amount_all'] else Decimal(0)
    user_data['amount_other'] = r['amount_other'] if r['amount_other'] else Decimal(0)
    user_data['amount_self'] = user_data['amount_all'] - user_data['amount_other']
    # 系统公告和客服
    system = await self.get_cache_result('sys_info', ['bulletin', 'telegram'], {'id': 1})
    user_data['bulletin'] = system['bulletin']
    user_data['telegram'] = system['telegram']
    # 订单信息
    orders = await getOrder(self, {'offset': 0})
    user_data['orders'] = orders['data']
    result = {'type': 'home.getuserinfo', 'data': user_data}
    return result


# 获取订单列表
async def getOrder(self, data):
    if await self.is_null(data, ['offset']):
        return msg[10100]
    sql = """select code,amount,earn_partner_self,time_success,p.account as payment_account,p.name as payment_name from 
                orders_ds o left join payment p on p.id=o.payment_id where o.partner_id=%s and o.status in (3,4) 
                    order by o.id desc limit 5 offset %s"""
    values = [self.current_user['id'], data['offset']]
    orders = await self.query(sql, *values)
    result = {'type': 'home.getorderinfo', 'data': orders}
    return result


# 充值
async def charge(self, data):
    if await self.is_null(data, ['amount', 'password_trade']):
        return msg[10100]
    amount = Decimal(data['amount'])
    partner = await self.get_result_by_condition('partner', ['hash_trade'], {'id': self.current_user['id']})
    if not partner:
        self.logger.warning("充值码商 {partner} 不存在".format(partner=self.current_user['id']))
        return msg[10334]
    # 验证交易密码
    if not bcrypt.checkpw(data['password_trade'].encode('utf8'), partner['hash_trade'].encode('utf8')):
        return msg[10330]
    # 不允许多次提交
    sql = """select * from partner_recharge where partner_id=%s and status in (0,1) and time_create>date_sub(now(), interval 24 hour)"""
    orders = await self.query(sql, self.current_user['id'])
    if orders:
        self.logger.warning("充值码商 {partner} , 当日多次提交".format(partner=self.current_user['id']))
        return msg[10334]
    code = await self.create_order_code('C')
    data_new = dict(code=code, partner_id=self.current_user['id'], amount=amount)
    if not await self.create_result('partner_recharge', data_new):
        self.logger.warning("充值码商 {partner} , 创建充值订单错误".format(partner=self.current_user['id']))
        return msg[10334]
    return msg[10335]


# 提现
async def withdraw(self, data):
    # 暂时关闭提现功能
    return msg[10332]
    if await self.is_null(data, ['amount', 'account', 'name', 'ifsc', 'bank', 'password_trade']):
        return msg[10100]
    amount = Decimal(data['amount'])
    partner = await self.get_result_by_condition('partner', ['balance', 'hash_trade'],
                                                 {'id': self.current_user['id'], 'status': 1})
    if not partner:
        return msg[10332]
    # 验证交易密码
    if not bcrypt.checkpw(data['password_trade'].encode('utf8'), partner['hash_trade'].encode('utf8')):
        return msg[10330]
    if partner['balance'] < amount:
        return msg[10331]
    if not await creat_withdraw(self, amount, data):
        return msg[10332]
    return msg[10333]


# 创建订单并扣除余额
async def creat_withdraw(self, amount, data):
    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                partner_id = self.current_user['id']
                # 生成订单
                code = await self.create_order_code('T')
                sql_insert = """insert into partner_withdraw (code,partner_id,amount,account,name,ifsc,bank) value (%s,%s,%s,%s,%s,%s,%s)"""
                if not await cur.execute(sql_insert, (code, partner_id, amount, data['account'], data['name'],
                                                      data['ifsc'], data['bank'])):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return False
                # 扣除余额
                if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 2):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return False
                if (await self.get_result_by_condition('partner', ['balance'], {'id': partner_id}))['balance'] < 0:
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return False
            except Exception as e:
                self.logger.warning('提现失败partner_id={partner_id},非法数据={e}'.format(partner_id=partner_id, e=e))
                await conn.rollback()
                return False
            else:
                await conn.commit()
                return True
