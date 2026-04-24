import decimal
import json
from decimal import Decimal

import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getVip(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_results_no_condition('vip', ['*'])
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


# 更新
class updateVip(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['vip', 'conditions', 'ds_min', 'ds_max', 'df_min', 'df_max', 'top_card']):
            return await self.json_response(msg[10005])
        if not data['deposit_ratio'] or data['deposit_ratio'] == "0":
            data['deposit_ratio'] = 20
        # 保证金比例判断
        if Decimal(data['deposit_ratio']) < Decimal(1):
            return await self.json_response(msg[10037])
        if Decimal(data['deposit_ratio']) > Decimal(99):
            return await self.json_response(msg[10037])

        if not await self.update_result('vip', data, {'vip': data['vip']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)
