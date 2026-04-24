import tornado.web
import json
from application.base import BaseHandler
from application.message import msg
import re

class GetDsdfLock(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_cache_result('sys_info', ['dsdf_lock'])

        if data_r['dsdf_lock']:
            data_r = json.loads(data_r['dsdf_lock'])
        else:
            data_r = {}
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)
    

class UpdateDsdfLock(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            required_fields = ['switch', 'start_time', 'end_time', 'google']
            for field in required_fields:
                if field not in data:
                    return await self.json_response(msg[10005])
                
            # 验证谷歌密钥
            r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
            if not await self.check_googl_code(data['google'], r['ggkey']):
                return await self.json_response(data=msg[10003])
            
            # 验证时间格式为时分
            time_pattern = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')
            if not time_pattern.match(data['start_time']) or not time_pattern.match(data['end_time']):
                return await self.json_response(msg[10005])

            # 将数据转换成json保存到sys_info.dsdf_lock中
            dsdf_lock_info = json.dumps({
                'switch': data['switch'],
                'start_time': data['start_time'],
                'end_time': data['end_time']
            })

            if not await self.update_result('sys_info', {'dsdf_lock': dsdf_lock_info}, {'id': 1}):
                return await self.json_response(msg[10007])
            # 延迟双删sys_info
            await self.delete_cache_result('sys_info', {'id': 1})
            
            await self.redis.setex('dsdf_lock_info', 3600, dsdf_lock_info)  # 设置缓存，过期时间为3600秒

            result = dict(code=20000, msg='更新成功')
            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10007])