import json
from datetime import datetime

import tornado

from decimal import Decimal
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg

async def get_all_sub_merchants(db, merchant_id, logger):
    """
    根据当前商户 ID 查找所有下级商户的 ID，包括商户自己
    """
    try:
        async with db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                sql_get_sub_merchants = """
                SELECT child AS id FROM merchant_tree WHERE parent = %s
                """
                await cur.execute(sql_get_sub_merchants, (merchant_id,))
                sub_merchants = await cur.fetchall()
                return [sub_merchant['id'] for sub_merchant in sub_merchants]

    except Exception as e:
        logger.exception(f'查找下级商户数据失败: {str(e)}')
        return []

# 增加
class addMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['cellphone', 'name', 'google']):
            return await self.json_response(data=msg[10004])
        r = await self.get_result_by_condition('merchant', ['gg_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        del data['google']
        if await self.is_exits('merchant', 'cellphone', data['cellphone']):
            return await self.json_response(msg[10008])
        data['hash_login'] = await self.password_create('88888888')
        data['gg_key'] = await self.create_gg_key()
        data['mc_key'] = data['mc_key'] = await self.create_api_key()
        data['pid'] = self.current_user['id']
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 新增商户
                    k, p, v = await self.dict_to_kv(data)
                    sql = """ insert into merchant ({keys}) values ({vals})""".format(keys=k, vals=p)
                    if not await cur.execute(sql, (*v,)):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return await self.json_response(data=msg[10004])
                    # 查询ID
                    sql = """select id from merchant where cellphone = %s"""
                    if not await cur.execute(sql, data['cellphone']):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return await self.json_response(data=msg[10004])
                    merchant_id = (await cur.fetchall())[0]['id']
                    # 新增关系树
                    sql = """insert into merchant_tree (parent,child,distance) value (%s,%s,%s)"""
                    # 加入自己
                    if not await cur.execute(sql, (merchant_id, merchant_id, 0)):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return await self.json_response(data=msg[10004])
                    # 当前新户所有父级关系+1
                    parents = await self.get_results_by_condition('merchant_tree', ['parent', 'distance'],
                                                                  {'child': self.current_user['id']})
                    for i in parents:
                        if not await cur.execute(sql, (i['parent'], merchant_id, i['distance'] + 1)):
                            await conn.rollback()
                            self.logger.warning(cur._last_executed)
                            return await self.json_response(data=msg[10004])
                except Exception as e:
                    await conn.rollback()
                    self.logger.exception(e)
                    return await self.json_response(data=msg[10004])
                else:
                    await conn.commit()
        result = dict(code=20000, msg='新增成功')
        return await self.json_response(result)


# 获取
class getMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        # 获取条件和时间范围
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        # 查找所有下级商户的 ID
        sub_merchant_ids = await get_all_sub_merchants(self.application.db, self.current_user['id'], self.logger)
        
        # 如果没有下级商户，确保不会返回任何数据
        if not sub_merchant_ids:
            condition['id'] = 'id = -1'
        else:
            condition['id'] = str(sub_merchant_ids)
        # 获取结果
        keys = ['id', 'cellphone', 'name', 'balance', 'balance_frozen', 'status', 'status_df', 'rate_df', 'fee_df',
                'time_create']
        data_r, total = await self.get_result('merchant', keys, None, condition, between, data['size'], data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)

# 更新
class updateMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'rate_df', 'fee_df']):
            return await self.json_response(data=msg[10005])
        rates_p = await self.get_result_by_condition('merchant', ['rate_df', 'fee_df'], {'id': self.current_user['id']})
        if rates_p['rate_df'] > Decimal(data['rate_df']) or rates_p['fee_df'] > Decimal(data['fee_df']):
            return await self.json_response(data=msg[10009])
        update_data = {
            'rate_df': data['rate_df'],
            'fee_df': data['fee_df'],
        }
        await self.update_result('merchant', update_data, {'id': data['id']})
        result = dict(code=20000, msg='修改成功')
        return await self.json_response(result)


# 获取通道
class getMerchatChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10004])
        sql = """select c.code,c.name,m.rate from channel c left join merchant_channel m on c.code=m.code and m.merchant_id=%s"""
        channels = await self.query(sql, data['id'])
        result = dict(code=20000, data=channels, msg='获取成功')
        return await self.json_response(result)


# 更新通道
class updateMerchatChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'merchant_channel']):
            return await self.json_response(data=msg[10005])
        # 获取已有费率通道
        channels = await self.get_results_by_condition('merchant_channel', ['code', 'rate'],
                                                       {'merchant_id': data['id']})
        # 获取父级已有费率通道
        channels_p = await self.get_results_by_condition('merchant_channel', ['code', 'rate'],
                                                         {'merchant_id': self.current_user['id']})
        # 遍历所有填写
        for i in data['merchant_channel']:
            del i['name']
            if not i['rate']:
                continue
            channel_p = list(filter(lambda item: item['code'] == i['code'], channels_p))
            if not channel_p or Decimal(i['rate']) < channel_p[0]['rate']:
                return await self.json_response(data=msg[10009])
            channel = list(filter(lambda item: item['code'] == i['code'], channels))
            i['merchant_id'] = data['id']
            if not channel:
                if not await self.create_result('merchant_channel', i):
                    return await self.json_response(data=msg[10005])
            elif channel[0]['rate'] != Decimal(i['rate']):
                if not await self.update_result('merchant_channel', i, {'merchant_id': data['id'], 'code': i['code']}):
                    return await self.json_response(data=msg[10005])
            else:
                continue
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


# 码商排序
class getMerchantRank(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        # 初始化一个空的 condition 字典
        condition = {}

        # 分别获取 create 和 success 的条件，并合并到 condition 中
        create_condition, create_between = await self.split_between_condition(data['serchData'], 'time_create')
        success_condition, success_between = await self.split_between_condition(data['serchData'], 'time_success')

        # 将 create_condition 和 success_condition 合并到 condition 中
        condition.update(create_condition)
        condition.update(success_condition)

        # 查找所有下级商户的 ID
        sub_merchant_ids = await get_all_sub_merchants(self.application.db, self.current_user['id'], self.logger)

        # 如果有填入筛选商户ID，只保留指定的商户ID
        merchant_id = data['serchData'].get('id', '')
        if merchant_id and merchant_id.isdigit():
            sub_merchant_ids = [merchant_id] if int(merchant_id) in sub_merchant_ids else []
        
        # 如果没有下级商户，确保不会返回任何数据
        if not sub_merchant_ids:
            condition['id'] = 'id = -1'
        else:
            condition['id'] = str(sub_merchant_ids)


        values = []
        flag = False
        success_start = None
        success_end = None
        if create_between:
            flag = True
        if success_between:
            flag = True
            bt_key, success_start, success_end = await self.dict_to_between(success_between)
        if not flag and not success_between:
            today = datetime.now()
            success_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
            success_end = today.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 初始化 SQL 语句
        sql = """
            SELECT m.id,
                m.cellphone,
                m.name,
                COALESCE(ds.count, 0) AS count,
                COALESCE(ds.amount, 0) AS amount,
                COALESCE(ds.success_count, 0) AS success_count,
                COALESCE(ds.success_amount, 0) AS success_amount,
                COALESCE(ds.rate, 0) AS rate,
                COALESCE(of.payout_success_amount, 0) AS payout_success_amount
            FROM merchant m
            LEFT JOIN (
                SELECT o.merchant_id,
                    COUNT(o.id) AS count,
                    SUM(IF(o.amount > 0, o.amount, 0)) AS amount,
                    COUNT(IF(o.status > 2, 1, NULL)) AS success_count,
                    SUM(IF(o.status > 2, o.amount, 0)) AS success_amount,
                    CAST(COUNT(IF(o.status > 2, 1, NULL)) / IF(COUNT(o.id) = 0, 1, COUNT(o.id)) * 100 AS DECIMAL(14, 0)) AS rate
                FROM orders_ds o
                WHERE 1=1
        """
        
        if success_start and success_end:  # 检查 success_start 和 success_end 是否都不为空
            sql += "AND o.time_success BETWEEN %s AND %s "
            values += [
                success_start, success_end,
            ]


        # 如果 time_create 存在，则加入相应的查询条件
        if create_between:
            bt_key, create_start, create_end = await self.dict_to_between(create_between)
            sql += "AND o.time_create BETWEEN %s AND %s "
            values += [
                create_start, create_end,
            ]

        sql += """
                GROUP BY o.merchant_id
            ) ds ON ds.merchant_id = m.id
            LEFT JOIN (
                SELECT of.merchant_id,
                    SUM(IF(of.status = 4, of.amount, 0)) AS payout_success_amount
                FROM orders_df of
                WHERE 1=1
        """
        if success_start and success_end:  # 检查 success_start 和 success_end 是否都不为空
            sql += "AND of.time_success BETWEEN %s AND %s "
            values += [
                success_start, success_end,
            ]

        # 如果 time_create 存在，则加入相应的查询条件
        if create_between:
            bt_key, create_start, create_end = await self.dict_to_between(create_between)
            sql += "AND of.time_create BETWEEN %s AND %s "
            values += [
                create_start, create_end,
            ]

        sql += """
                GROUP BY of.merchant_id
            ) of ON of.merchant_id = m.id
        """

        if sub_merchant_ids:
            sql += ' WHERE m.id IN %s GROUP BY m.id'
            values += [tuple(sub_merchant_ids)]
        else:
            sql += ' WHERE m.id = %s GROUP BY m.id'
            values += [-1]  # 使用一个不匹配的 ID
        if data['order_field']:
            sql += 'order by {order_field} '.format(order_field=data['order_field'])
            if data['sort']:
                sql += data['sort']
        sql += ' limit %s offset %s'.format()
        values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)
        # print(sql)
        # print(values)
        total = await self.get_result_by_condition('merchant', ['count(id)'], condition)
        result = dict(code=20000, data=data_r, total=total['count(id)'], msg='获取成功')
        return await self.json_response(result)
