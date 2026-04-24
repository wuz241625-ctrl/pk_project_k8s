import json
from datetime import datetime
from decimal import Decimal

import tornado
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


def should_use_default_order_range(condition, between):
    if between:
        return False
    if not condition:
        return True
    return not any(condition.get(key) for key in ('code', 'merchant_code'))

# 获取代收订单
class getOrderDs(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if not between:
            condition, between = await self.split_between_condition(condition, 'time_success')
        if should_use_default_order_range(condition, between):
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        # 查找所有下级商户的 ID
        sub_merchant_ids = await get_all_sub_merchants(self.application.db, self.current_user['id'], self.logger)
        
        if not sub_merchant_ids:
            condition['merchant_id'] = 'id = -1'
        else:
            if 'merchant_id' in condition:
                merchant_id = condition['merchant_id']
                if not merchant_id:  # 如果 condition['merchant_id'] 为空
                    condition['merchant_id'] = str(sub_merchant_ids)
                elif merchant_id and merchant_id in map(str, sub_merchant_ids):  # 将 sub_merchant_ids 中的元素转换为字符串进行比较
                    condition['merchant_id'] = str([merchant_id])  # 保留单个匹配的 merchant_id
                else:  # 如果 merchant_id 不在 sub_merchant_ids 中
                    condition['merchant_id'] = 'id = -1'
            else:
                condition['merchant_id'] = str(sub_merchant_ids)
        keys = ['code', 'merchant_code', 'amount', 'status', 'channel_code', 'time_create', 'time_success', 'realpay', 'poundage', 'upi', 'utr']
        keys_count = ['amount', 'status']
        data_r, total, count = await self.get_result('orders_ds', keys, keys_count, condition, between,
                                                     data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': Decimal(0),
                   'processing_amount': Decimal(0)}
        for i in count:
            if i['status'] == 4:
                count_r['successOrder'] += 1
                count_r['amount'] += i['amount']
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
                count_r['processing_amount'] += i['amount']
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)


# 单笔代付
class addDf(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['amount', 'ifsc', 'payment_bank', 'payment_account', 'payment_name', 'google']):
            return await self.json_response(msg[10007])
        # 添加限时锁 当前用户3秒内同金额限一次
        busy_key = 'add_merchant_df_{merchant_id}_{amount}'.format(
            merchant_id=self.current_user['id'], amount=data['amount'])
        if await self.redis.exists(busy_key):
            return await self.json_response(msg[10013])
        await self.redis.set(busy_key, '1', 3)
        # 验证谷歌
        r = await self.get_result_by_condition('merchant', ['gg_key', 'mc_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        # 向API提交请求
        return self.write(await self.order_df(data, r['mc_key']))


# 批量代付
class addDfpl(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['orders', 'google']):
            return await self.json_response(msg[10007])
        # 验证谷歌
        r = await self.get_result_by_condition('merchant', ['gg_key', 'mc_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        # 向API提交请求
        fail = 0
        for i in data['orders']:
            try:
                df_r = await self.order_df(i, r['mc_key'])
                df_r = json.loads(df_r)
                if not df_r['code'] == 0:
                    fail += 1
                    continue
            except Exception as e:
                self.logger.warning('merchant_id={merchant_id},批量付款错误，e={e}'.format(merchant_id=self.current_user['id'],e=str(e)))
                continue
        result = dict(code=20000, data={'fail': fail}, msg='提交成功')
        return await self.json_response(result)


# 获取代付订单
class getOrderDf(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if not between:
            condition, between = await self.split_between_condition(condition, 'time_success')
        if should_use_default_order_range(condition, between):
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        # condition['merchant_id'] = self.current_user['id']
        # 查找所有下级商户的 ID 
        sub_merchant_ids = await get_all_sub_merchants(self.application.db, self.current_user['id'], self.logger)
        
        if not sub_merchant_ids:
            condition['merchant_id'] = 'id = -1'
        else:
            if 'merchant_id' in condition:
                merchant_id = condition['merchant_id']
                if not merchant_id:  # 如果 condition['merchant_id'] 为空
                    condition['merchant_id'] = str(sub_merchant_ids)
                elif merchant_id and merchant_id in map(str, sub_merchant_ids):  # 将 sub_merchant_ids 中的元素转换为字符串进行比较
                    condition['merchant_id'] = str([merchant_id])  # 保留单个匹配的 merchant_id
                else:  # 如果 merchant_id 不在 sub_merchant_ids 中
                    condition['merchant_id'] = 'id = -1'
            else:
                condition['merchant_id'] = str(sub_merchant_ids)
        # 动态添加 parent_id 条件，查询为空字符串的记录
        parent_id_condition = {'parent_id': "''"}  # 查询空字符串
        condition.update(parent_id_condition)
        keys = ['code', 'merchant_code', 'amount', 'status', 'ifsc', 'payment_bank', 'payment_account', 'payment_name',
                'time_create', 'time_success', 'realpay', 'poundage', 'payment_img','debit_account', 'utr']
        keys_count = ['amount', 'status']
        data_r, total, count = await self.get_result('orders_df', keys, keys_count, condition, between,
                                                     data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': Decimal(0),
                   'processing_amount': Decimal(0)}
        for i in count:
            if i['status'] == 4:
                count_r['successOrder'] += 1
                count_r['amount'] += i['amount']
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
                count_r['processing_amount'] += i['amount']
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)


# 提现
class addWithdraw(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['amount', 'address', 'google']):
            return await self.json_response(msg[10007])
        # 验证谷歌
        r = await self.get_result_by_condition('merchant', ['gg_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        merchant = await self.get_result_by_condition('merchant', ['balance'],
                                                      {'id': self.current_user['id'], 'status': 1})
        if not merchant:
            return await self.json_response(msg[10007])
        if merchant['balance'] < Decimal(data['amount']):
            return await self.json_response(msg[10010])
        if not await self.creat_withdraw(data):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='提交成功')
        return await self.json_response(result)

    # 创建订单并扣除代付余额
    async def creat_withdraw(self, data):
        amount = Decimal(data['amount'])
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    merchant_id = self.current_user['id']
                    # 生成订单
                    sql_insert = """insert into merchant_withdraw (code,amount,merchant_id,address) value (%s,%s,%s,%s)"""
                    code = await self.create_order_code('T')
                    if not await cur.execute(sql_insert, (code, amount, merchant_id, data['address'])):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return False
                    # 扣除余额
                    if not await self.change_amount(conn, cur, code, -amount, 2):
                        self.logger.warning(cur._last_executed)
                        return False
                except Exception as e:
                    self.logger.warning('merchant_id={merchant_id},非法数据={e}'.format(merchant_id=merchant_id, e=e))
                    await conn.rollback()
                    return False
                else:
                    await conn.commit()
                    return True


# 提现订单
class getWithdraw(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        condition, between = await self.split_between_condition(data['serchData'], 'time_accept')
        condition, between = await self.split_between_condition(condition, 'time_create')
        if (not condition or not condition.get('code')) and not between:
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        condition['merchant_id'] = self.current_user['id']
        keys = ['code', 'amount', 'status', 'time_create', 'time_success', 'address']
        data_r, total = await self.get_result('merchant_withdraw', keys, None, condition, between, data['size'],
                                              data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
