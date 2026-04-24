import decimal
import json
import random
from datetime import datetime

import tornado
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg


# 查询奖池金额
class getPoolAmount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        pool_amount = await self.get_result_no_condition('prize_pool',['pool_amount'])

        result = dict(code=20000, data=pool_amount, msg='获取成功')
        return await self.json_response(result)

# 增加奖池金额
class addPoolAmount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if not data['pool_amount']:
            return await self.json_response(msg[10007])
        amount =  decimal.Decimal(data['pool_amount'])
        busy_key = 'prize_pool_lock'
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 锁定奖池
                    # 获取锁，10秒内锁定
                    if not await self.redis.setnx(busy_key, 1):
                        return await self.json_response(msg[10007])
                    await self.redis.expire(busy_key, 10)
                    result = await self.get_result_no_condition('prize_pool',['pool_amount'])
                    if not result:
                        return await self.json_response(msg[10007])


                    pool_amount = result['pool_amount']
                    # 修改奖池金额
                    _before_amount = pool_amount
                    _change_after = pool_amount + amount

                    sql = 'update prize_pool set pool_amount = {pool_amount} where id= {id} limit 1'.format(pool_amount=_change_after, id=1)
                    if not await cur.execute(sql):
                        return await self.json_response(msg[10007])

                    # 保存奖池变动记录
                    code = await self.create_code("JC")
                    remark = '增加奖池余额{amount}, 管理员={e}'.format(amount=amount, e=self.current_user['id'])
                    prize_pool_log = {
                        'code': code,
                        'record_type': 1,
                        'change_before': _before_amount,
                        'amount': amount,
                        'change_after': _change_after,
                        'remark': remark,
                        'created_at': datetime.now()
                    }
                    k, p, v = await self.dict_to_kv(prize_pool_log)
                    sql = "insert into prize_pool_log ({keys}) values ({vals})".format(keys=k, vals=p)
                    if not await cur.execute(sql, (*v,)):
                        return await self.json_response(msg[10007])

                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    return await self.json_response(msg[10007])
                finally:
                    # 执行完成删除锁
                    await self.redis.delete(busy_key)

        result = dict(code=20000, data=_change_after, msg='操作成功')
        return await self.json_response(result)

    # 创建编码
    @staticmethod
    async def create_code(PRE='R'):
        return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))

# 获取
class getPoolLogs(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        sql_part = ''
        values = []
        condition, between = await self.split_between_condition(data['searchData'], 'created_at')

        if between:
            sql_part = ' where '
            bt_key, bt_start, bt_end = await self.dict_to_between(between)
            sql_part += bt_key
            values += [bt_start, bt_end]

        # 获取所有数据总数
        sql = "select count(id) from prize_pool_log"
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0

        # 分页查询日志
        sql = 'select * from prize_pool_log'
        sql += sql_part + ' order by created_at desc '
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


