import json
import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getPayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        keys = {'id', 'account', 'name', 'type', 'bank', 'ifsc', 'admin_id', 'time_create', 'status'}
        data_r, total = await self.get_result('sys_payment', keys, None, data['serchData'], None, data['size'],
                                              data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


# 添加
class addPayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['account', 'name', 'bank', 'ifsc']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('sys_payment', 'account', data['account']):
            return await self.json_response(msg[10008])
        data['admin_id'] = self.current_user['id']
        if not await self.create_result('sys_payment', data):
            return await self.json_response(msg[10004])
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)


# 更新
class updatePayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'status']):
            return await self.json_response(data=msg[10004])
        if not await self.update_result('sys_payment', data, {'id': data['id']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)


# 删除
class deletePayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('sys_payment', {'id': data['id']}):
            return await self.json_response(msg[10006])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)
