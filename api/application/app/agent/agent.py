import datetime
import secrets
import string

from decimal import Decimal
from aiomysql import DictCursor

from application.message import msg
from application.timezone import display_now, display_today_between, display_to_utc_naive


async def Agent(self, action, data):
    if action == 'getagentinfo':
        return await getagentinfo(self, data)
    if action == 'getagentlist':
        return await getagentlist(self, data)
    if action == 'addagent':
        return await addagent(self, data)


# 获取代理信息
async def getagentinfo(self, data):
    if await self.is_null(data, ['time']):
        return msg[10100]
    # 邀请码
    user_data = dict()
    user_data['invitation_code'] = (await self.get_result_by_condition('partner', ['invitation_code'],
                                                                       {'id': self.current_user['id']}))['invitation_code']
    # 下级人数佣金
    partner_id = self.current_user['id']
    childs = await self.get_results_by_condition('partner_tree', ['child'], {'parent': partner_id, 'distance': 1})
    user_data['agent_number'] = len(childs)
    time = display_today_between('time_create')['start']
    if data['time'] == 1:
        time -= datetime.timedelta(days=1)
    if data['time'] == 2:
        time -= datetime.timedelta(days=7)
    if data['time'] == 3:
        display_month = display_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        time = display_to_utc_naive(display_month)
    # 佣金查询
    user_data['agent_ds_amount'] = Decimal(0)
    user_data['agentlist'] = []
    value = [time, self.current_user['id']]
    sql = """select sum(r.amount) as amount from balance_record r inner join orders_ds o on  o.code=r.code and 
                o.partner_id!=r.user_id where r.user_type=0 and r.time_create >= %s and r.record_type=3 and r.user_id =%s"""
    r = await self.query(sql, *value)
    if r:
        r = r[0]
        user_data['agent_ds_amount'] = r['amount'] if r['amount'] else Decimal(0)
        # 同时加载下级信息
        agent = await getagentlist(self, {'time': data['time'], 'offset': 0})
        user_data['agentlist'] = agent['data']
    result = {'type': 'agent.getagentinfo', 'data': user_data}
    return result


# 获取订单列表
async def getagentlist(self, data):
    if await self.is_null(data, ['offset', 'time']):
        return msg[10100]
    # 获取直属下级ID和NAME(每次最多5个)
    sql = """select id,name from partner where pid=%s limit 5 offset %s"""
    values = [self.current_user['id'], data['offset']]
    agents = await self.query(sql, *values)
    # 计算查找时间
    time = display_today_between('time_create')['start']
    if data['time'] == 1:
        time -= datetime.timedelta(days=1)
    if data['time'] == 2:
        time -= datetime.timedelta(days=7)
    if data['time'] == 3:
        time.replace(day=1)
    # 分别统计下级的贡献
    for i in agents:
        sql = """select group_concat(child) as childs from partner_tree where parent=%s and distance <= 1"""
        childs = (await self.query(sql, i['id']))[0]['childs']
        value = [time, self.current_user['id']]
        sql = """select sum(r.amount) as amount from balance_record r inner join orders_ds o on 
                    o.code=r.code and partner_id in ({childs}) where r.time_create>=%s and record_type=3 and user_type=0
                     and user_id=%s""".format(childs=childs)
        r = await self.query(sql, *value)
        i['agent_ds_amount'] = r[0]['amount'] if r and r[0]['amount'] else Decimal(0)
    result = {'type': 'agent.getagentlist', 'data': agents}
    return result


# 新增代理
async def addagent(self, data):
    # 暂时关闭添加代理
    return msg[10502]
    if await self.is_null(data, ['cellphone', 'name'] or not data['cellphone'].isdigit()):
        return msg[10100]
    if await self.get_result_by_condition('partner', ['id'], {'cellphone': data['cellphone']}):
        return msg[10500]
    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 生成邀请码
                sql = """select id from partner where invitation_code=%s"""
                while True:
                    invitation_code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
                    if not await cur.execute(sql, invitation_code):
                        break
                # 新增码商
                sql = """insert into partner (name,cellphone,hash_login,hash_trade,pid,invitation_code) value (%s,%s,%s,%s,%s,%s)"""
                password = await self.password_create('123456')
                value = [data['name'], data['cellphone'], password, password, self.current_user['id'],invitation_code]
                if not await cur.execute(sql, value):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return msg[10502]
                # 新增关系树
                sql = """select id from partner where cellphone=%s"""
                if not await cur.execute(sql, data['cellphone']):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return False
                _id = (await cur.fetchall())[0]['id']
                sql = """insert into partner_tree (parent,child,distance) value (%s,%s,%s)"""
                # 加入自己
                if not await cur.execute(sql, (_id, _id, 0)):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return msg[10502]
                # 当前新户所有父级关系+1
                parents = await self.get_results_by_condition('partner_tree', ['parent', 'distance'],
                                                              {'child': self.current_user['id']})
                for i in parents:
                    if not await cur.execute(sql, (i['parent'], _id, i['distance'] + 1)):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return msg[10502]
            except Exception as e:
                self.logger.exception(e)
                return msg[10502]
            else:
                await conn.commit()
                return msg[10501]
