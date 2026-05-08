import json
from datetime import datetime
from decimal import Decimal

import tornado
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg
from application.timezone import display_today_between


# 增加
class addMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['cellphone', 'name']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('merchant', 'cellphone', data['cellphone']):
            return await self.json_response(msg[10008])
        data['hash_login'] = await self.password_create('88888888')
        data['gg_key'] = await self.create_gg_key()
        data['mc_key'] = data['mc_key'] = await self.create_api_key()
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
                    sql = """insert into merchant_tree (parent,child,distance) values (%s,%s,%s)"""
                    if not await cur.execute(sql, (merchant_id, merchant_id, 0)):
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
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        keys = ['id', 'cellphone', 'name', 'balance', 'balance_frozen', 'pid', 'target_payment', 'target_payment', 'ip', 'ip_df', 'decimal_amt_flag', 'notify_callback_type',
                'gg_key', 'mc_key', 'status', 'status_df', 'rate_df', 'fee_df', 'time_create', 'amount_fixed', 'amount_fixed_max', 'ds_on', 'ds_black_ips', 'ds_userid_on', 'ds_black_userids']
        data_r, total = await self.get_result('merchant', keys, None, condition, between, data['size'], data['page'], data['sort'], data['order_field'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


# 更新
class updateMerchant(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if 'status' not in data and await self.is_null(data, ['cellphone', 'name']):
            return await self.json_response(data=msg[10005])
        if 'password' in data:
            data['hash_login'] = await self.password_create(data['password'])
            del data['password']
        # 手动变动余额
        if 'changeBalance' in data:
            merchant_id = data['id']
            changeBalace = data['changeBalance']
            balance_type = changeBalace['changeBalanceType']
            amount = Decimal(changeBalace['changeAmount'])
            # 锁
            busy_key = 'edit_merchant_balance_busy_{merchant_id}_{amount}'.format(merchant_id=merchant_id,
                                                                                  amount=amount)
            if await self.redis.exists(busy_key):
                return await self.json_response(msg[10010])
            await self.redis.set(busy_key, '1', 10)
            # 执行变动
            if await self.change_balance_sd(amount, balance_type, 'merchant', merchant_id, changeBalace['remark']):
                del data['changeBalance']
            else:
                return await self.json_response(msg[10005])

        merchant_info = await self.query("SELECT target_payment FROM merchant where id = %s", data['id'])
        old_target_payment = merchant_info[0]['target_payment']

        await self.update_result('merchant', data, {'id': data['id']})

        # 设置默认值
        data.setdefault('target_payment', '')

        # 更严谨的非空判断
        if data['target_payment'] != old_target_payment:
            self.logger.info('商户指定码已更新，派单链路将直接读取 MySQL merchant.target_payment')
        result = dict(code=20000, msg='修改成功')
        return await self.json_response(result)


# 获取通道
class getMerchatChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10004])
        sql = """select c.code,c.name,m.merchant_id,m.rate,m.otherpay,m.is_force,m.target_channel,m.status 
                from channel c left join merchant_channel m on c.code=m.code and m.merchant_id=%s where c.status =1"""
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
        # 获取自己通道
        sql = """select c.code,c.rates,c.rate,m.* from channel c left join merchant_channel m on c.code=m.code and m.merchant_id=%s where c.status =1"""
        channels = await self.query(sql, data['id'])
        # 获取父级
        r = await self.get_result_by_condition('merchant', ['pid'], {'id': data['id']})
        pid = r['pid']
        for i in data['merchant_channel']:
            for j in channels:
                if i['code'] == j['code']:
                    if i['status'] and i['rate']:
                        # 判断商户费率是否高于通道总费率
                        rate = Decimal(i['rate'])
                        if rate < sum(list(map(Decimal, j['rates'].split(',')))) + j['rate']:
                            return await self.json_response(data=msg[10013])
                        # 判断商户费率是否低于上级
                        if pid:
                            r = await self.get_result_by_condition('merchant_channel', ['rate'],
                                                                   {'merchant_id': pid, 'code': i['code']})
                            if not r['rate'] or r['rate'] > rate:
                                return await self.json_response(data=msg[10013])
                        del i['name']
                        if not i['otherpay']:
                            i['otherpay'] = None
                        if not i['target_channel']:
                            i['target_channel'] = None
                        # 判断是否为新开通道
                        if j['id']:
                            await self.update_result('merchant_channel', i, {'id': j['id']})
                        else:
                            i['merchant_id'] = data['id']
                            if not await self.create_result('merchant_channel', i):
                                return await self.json_response(data=msg[10005])
                    elif j['status']:
                        # 关闭
                        await self.update_result('merchant_channel', {'status': 0}, {'id': j['id']})

        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


# 重置谷歌
class resetGgkey(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10005])
        if 'type' in data.keys() and data['type'] == 'mc_key':
            mc_key = ggkey = await self.create_api_key()
            if not await self.update_result('merchant', {'mc_key': mc_key}, {'id': data['id']}):
                return await self.json_response(data=msg[10005])
        else:
            ggkey = await self.create_gg_key()
            if not await self.update_result('merchant', {'gg_key': ggkey}, {'id': data['id']}):
                return await self.json_response(data=msg[10005])
        result = dict(code=20000, data=ggkey, msg='重置成功')
        return await self.json_response(result)


# 码商排序
class getMerchantRank(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if not between:
            between = display_today_between('time_create')
        sql = """select m.id,m.cellphone,m.name,m.balance,count(o.id) as count,sum(o.amount) as amount,
                count(if(o.status>0,1,null)) as success_count,sum(if(o.status>0,o.amount,0)) as success_amount,
                cast(count(if(o.status>2,1,null))/if(count(o.id)=0,1,count(o.id)) * 100 as decimal(14,0)) as rate
                from merchant m left join orders_ds o on o.merchant_id=m.id and o.time_create between %s and %s"""
        bt_key, bt_start, bt_end = await self.dict_to_between(between)
        values = [bt_start, bt_end]
        if condition and condition['channel_code']:
            sql += ' and o.channel_code=%s'
            values += [condition['channel_code']]
        sql += ' group by m.id'
        if data['order_field']:
            sql += ' order by {order_field} '.format(order_field=data['order_field'])
            if data['sort']:
                sql += data['sort']
        sql += ' limit %s offset %s'.format()
        values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)
        total = await self.get_result_no_condition('merchant', ['count(id)'])
        result = dict(code=20000, data=data_r, total=total['count(id)'], msg='获取成功')
        return await self.json_response(result)


# 商户成功率
class getMerchantSuccessRate(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        # 添加全局时限 15秒
        busy_key = 'get_merchant_success_rate'
        if await self.redis.exists(busy_key):
            return await self.json_response(msg[10010])
        await self.redis.set(busy_key, '1', 15)

        condition, _ = await self.split_between_condition(data['serchData'], None)

        sql = """SELECT m.id, m.cellphone, m.name, m.balance,
               count(case when o.status > 2 and o.time_create >= date_sub(now(), interval 15 minute) then 1 end) as success_count_15m,
              sum(case when o.status > 2 and o.time_create >= date_sub(now(), interval 15 minute) then o.amount else 0 end) as success_amount_15m,
              coalesce(
                cast(
                  count(case when o.status > 2 and o.time_create >= date_sub(now(), interval 15 minute) then 1 end) /
                  nullif(count(case when o.time_create >= date_sub(now(), interval 15 minute) then 1 end), 0) * 100 as decimal(14, 0)
                ), 0) as rate_15m,
              count(case when o.status > 2 and o.time_create >= date_sub(now(), interval 30 minute) then 1 end) as success_count_30m,
              sum(case when o.status > 2 and o.time_create >= date_sub(now(), interval 30 minute) then o.amount else 0 end) as success_amount_30m,
              coalesce(
                cast(
                  count(case when o.status > 2 and o.time_create >= date_sub(now(), interval 30 minute) then 1 end) /
                  nullif(count(case when o.time_create >= date_sub(now(), interval 30 minute) then 1 end), 0) * 100 as decimal(14, 0)
                ), 0) as rate_30m,
              count(case when o.status > 2 and o.time_create >= date_sub(now(), interval 60 minute) then 1 end) as success_count_60m,
              sum(case when o.status > 2 and o.time_create >= date_sub(now(), interval 60 minute) then o.amount else 0 end) as success_amount_60m,
              coalesce(
                cast(
                  count(case when o.status > 2 and o.time_create >= date_sub(now(), interval 60 minute) then 1 end) /
                  nullif(count(case when o.time_create >= date_sub(now(), interval 60 minute) then 1 end), 0) * 100 as decimal(14, 0)
                ), 0) as rate_60m
        FROM merchant m 
        LEFT JOIN orders_ds o ON o.merchant_id = m.id and o.time_create between date_sub(now(), interval 60 minute) and now()"""

        values = []
        total_condition = dict()  # 添加筛选时，应同时添加参数筛选总数
        if condition and condition['id']:
            sql += ' where m.id=%s'
            values += [condition['id']]
            total_condition['id'] = condition['id']
        sql += ' group by m.id'
        if data['order_field']:
            sql += ' order by {order_field} '.format(order_field=data['order_field'])
            if data['sort']:
                sql += data['sort']
        sql += ' limit %s offset %s'
        values += [data['size'], (data['page'] - 1) * data['size']]
        query_data_list = await self.query(sql, *values)
        if total_condition:
            total = await self.get_result_by_condition('merchant', ['count(id)'], total_condition)
        else:
            total = await self.get_result_no_condition('merchant', ['count(id)'])

        result = dict(code=20000, data=query_data_list, total=total['count(id)'], msg='获取成功')
        return await self.json_response(result)
