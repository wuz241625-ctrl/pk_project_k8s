import json
import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getInfo(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_result_by_condition('merchant', ['mc_key', 'rate_df', 'fee_df', 'balance', 'balance_frozen'],
                                                    {'id': self.current_user['id']})
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


# 查看
class checkGg(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['google']):
            return await self.json_response(data=msg[10007])

        r = await self.get_result_by_condition('merchant', ['gg_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        result = dict(code=20000, data=r['gg_key'], msg='验证码正确')
        return await self.json_response(result)


# 更新
class resetGg(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['google']):
            return await self.json_response(data=msg[10005])
        r = await self.get_result_by_condition('merchant', ['gg_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        ggkey = await self.create_gg_key()
        if not await self.update_result('merchant', {'gg_key': ggkey}, {'id': self.current_user['id']}):
            return await self.json_response(data=msg[10005])
        result = dict(code=20000, msg='重置成功')
        return await self.json_response(result)


# 更新
class resetPw(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['new_password', 'google']):
            return await self.json_response(data=msg[10005])
        # 验证谷歌密钥
        r = await self.get_result_by_condition('merchant', ['gg_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        hash_login = await self.password_create(data['new_password'])
        if not await self.update_result('merchant', {'hash_login': hash_login}, {'id': self.current_user['id']}):
            return await self.json_response(data=msg[10005])
        result = dict(code=20000, msg='重置成功')
        return await self.json_response(result)
