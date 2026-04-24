import json
import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getIp(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['name']):
            return await self.json_response(msg[10007])
        data_r = await self.get_cache_result('sys_info', [data['name']], {'id': 1})
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


# 更新
class updateIp(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['google', 'name', 'ipString']):
            return await self.json_response(msg[10005])
        # 验证谷歌密钥
        r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['ggkey']):
            return await self.json_response(data=msg[10003])
        # 判断是否包含 127.0.0.*
        if data['name'] == 'api_ip_b' and any(ip.strip().startswith("127.0.0.") for ip in data['ipString'].split(",")):
            # print("❌ 禁止添加，包含 127.0.0.* 段的 IP")
            return await self.json_response(msg[10225])  # 返回对应的错误信息
        # else:
        #     print("✅ 允许添加")
        if not await self.update_result('sys_info', {data['name']: data['ipString']}, {'id': 1}):
            return await self.json_response(msg[10007])
        # 延迟双删sys_info
        await self.delete_cache_result('sys_info', {'id': 1})
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)
