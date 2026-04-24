import decimal
import json
import random
from datetime import datetime

import tornado
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg


# 查询用户抽奖机会
class getLotteryChance(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        sql_part = ''
        values = []

        # 从searchData中获取user_id条件查询
        search_data = data.get('searchData', {})
        if 'user_id' in search_data and search_data['user_id']:
            sql_part = ' where user_id = %s'
            values.append(search_data['user_id'])

        # 获取总数
        sql = "select count(id) from prize_lottery_chance"
        sql += sql_part
        total = await self.query(sql, *values)
        total = total[0]['count(id)'] if total else 0

        # 分页查询
        sql = 'select * from prize_lottery_chance'
        sql += sql_part + ' order by created_at desc '
        if data.get('size') and data.get('page', 0) > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]

        data_r = await self.query(sql, *values)

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


# 增加用户抽奖机会
class addLotteryChance(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if not all([data.get('user_id'), data.get('num')]):
            return await self.json_response(msg[10007])

        user_id = int(data['user_id'])
        num = int(data['num'])
        remark = data.get('remark', '')

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 查询用户当前抽奖机会
                    sql = 'select chance_num from prize_lottery_chance where user_id = %s limit 1'
                    await cur.execute(sql, (user_id,))
                    result = await cur.fetchone()

                    before_num = 0
                    if result:
                        before_num = result['chance_num']
                        # 更新用户抽奖机会
                        sql = 'update prize_lottery_chance set chance_num = chance_num + %s where user_id = %s'
                        if not await cur.execute(sql, (num, user_id)):
                            return await self.json_response(msg[10007])
                    else:
                        # 新增用户抽奖机会记录
                        sql = 'insert into prize_lottery_chance (user_id, chance_num, created_at, updated_at) values (%s, %s, %s, %s)'
                        if not await cur.execute(sql, (user_id, num, datetime.now(), datetime.now())):
                            return await self.json_response(msg[10007])

                    after_num = before_num + num

                    # 记录抽奖机会变动日志
                    chance_log = {
                        'user_id': user_id,
                        'before_num': before_num,
                        'num': num,
                        'after_num': after_num,
                        'remark': remark + ', 管理员={e}'.format(e=self.current_user['id']),
                        'created_at': datetime.now()
                    }

                    k, p, v = await self.dict_to_kv(chance_log)
                    sql = f"insert into prize_lottery_chance_log ({k}) values ({p})"
                    if not await cur.execute(sql, (*v,)):
                        return await self.json_response(msg[10007])

                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    return await self.json_response(msg[10007])

        result = dict(code=20000, data=after_num, msg='操作成功')
        return await self.json_response(result)

    # 创建编码
    @staticmethod
    async def create_code(PRE='R'):
        return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))


# 查询用户抽奖机会变动记录
class getLotteryChanceLog(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        sql_part = ''
        values = []

        # 处理时间范围条件
        condition, between = await self.split_between_condition(data.get('searchData', {}), 'created_at')
        if between:
            sql_part = ' where '
            bt_key, bt_start, bt_end = await self.dict_to_between(between)
            sql_part += bt_key
            values += [bt_start, bt_end]

        # 添加user_id条件
        if 'user_id' in data and data['user_id']:
            sql_part = sql_part + ' and user_id = %s' if sql_part else ' where user_id = %s'
            values.append(data['user_id'])

        # 获取所有数据总数
        sql = "select count(id) from prize_lottery_chance_log"
        sql += sql_part
        total = await self.query(sql, *values)
        total = total[0]['count(id)'] if total else 0

        # 分页查询日志
        sql = 'select * from prize_lottery_chance_log'
        sql += sql_part + ' order by created_at desc '
        if data.get('size') and data.get('page', 0) > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]

        data_r = await self.query(sql, *values)

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
