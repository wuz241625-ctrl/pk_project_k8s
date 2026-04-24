import json
import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getIp(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_result_by_condition('merchant', ['ip'], {'id': self.current_user['id']})
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


# 更新
class updateIp(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['google']):
            return await self.json_response(msg[10005])
        # 验证谷歌密钥
        r = await self.get_result_by_condition('merchant', ['gg_key'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['gg_key']):
            return await self.json_response(data=msg[10003])
        if not await self.update_result('merchant', {'ip': data['ipString']}, {'id': self.current_user['id']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)
