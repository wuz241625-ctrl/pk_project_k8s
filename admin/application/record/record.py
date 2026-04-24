import decimal
import json
from datetime import datetime

import tornado

from application.base import BaseHandler
from application.message import msg


class getSysRecord(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        keys = ['code', 'record_type', 'amount', 'name', 'account', 'type', 'time_create', 'admin_id', 'remark']
        keys_count = ['amount']
        data_r, total, count = await self.get_result('sys_record', keys, keys_count, condition, between,
                                                     data['size'], data['page'])
        count_r = {'amount_out': decimal.Decimal(0), 'amount_in': decimal.Decimal(0), 'amount': decimal.Decimal(0)}
        for i in count:
            count_r['amount'] += i['amount']
            if i['amount'] > 0:
                count_r['amount_in'] += i['amount']
            else:
                count_r['amount_out'] += i['amount']
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)


class getBalanceRecord(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if (not condition or not condition['code']) and not between:
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        keys = ['code', 'admin_id', 'user_type', 'user_id', 'change_before', 'amount', 'change_after', 'time_create',
                'remark', 'record_type', 'merchant_code']
        # 如果是推广账号，则过滤出推广账号下的码商订单
        other_str = None
        if str(self.current_user['role_id']) == '19':
            tg_partners_ids = await self.get_partners_by_parent_id(self.current_user['parent_id'])
            other_str = 'user_id in ({}) and user_type=0'.format(tg_partners_ids)  # 此处只过滤出码商id的记录，无商户id数据
        data_r, total = await self.get_result('balance_record', keys, None, condition, between, data['size'],
                                              data['page'], other_str=other_str)
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


# class getBalancedfRecord(BaseHandler):
#     @tornado.web.authenticated
#     async def post(self):
#         data = json.loads(self.request.body)
#         if await self.is_null(data, ['size', 'page']):
#             return await self.json_response(data=msg[10007])
#         condition, between = await self.split_between_condition(data['serchData'], 'time_create')
#         keys = ['code', 'admin_id', 'merchant_id', 'partner_id', 'partner_id', 'change_before', 'amount',
#                 'change_after', 'time_create', 'remark', 'record_type']
#         data_r, total = await self.get_result('balance_record_df', keys, None, condition, between, data['size'],
#                                               data['page'])
#         result = dict(code=20000, data=data_r, total=total, msg='获取成功')
#         return await self.json_response(result)
