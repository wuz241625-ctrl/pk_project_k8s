import decimal
import json
import asyncio
import sys
from decimal import Decimal

import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getAppsz(BaseHandler):
    @tornado.web.authenticated
    async def post(self):

        data_r = await self.get_cache_result('sys_info', ['app_info'])

        if data_r['app_info']:
            data_r = json.loads(data_r['app_info'])
        else:
            data_r = {}
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


class getWeight(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_results_no_condition('payment_weight', ['id,value,weight,payment_numbers,type,time_updated'])
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

class updateWeight(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['data', 'google']):
            return await self.json_response(msg[10005])
        # 验证谷歌密钥
        r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
        if not await self.check_googl_code(data['google'], r['ggkey']):
            return await self.json_response(data=msg[10003])
        for i in data['data']:
            sql = "update payment_weight set weight=%s, time_updated=NOW() where id=%s"
            if not await self.execute(sql, i['weight'], i['id']):
                self.logger.error(str(self.current_user['id']) + ' 写入payment_weight记录异常' + json.dumps(i))
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)

# 更新
class updateAppsz(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            if await self.is_null(data, ['name', 'versionCode', 'version', 'fileUrl', 'download', 'isForce', 'describe', 'isSilence', 'packageType','domainName','customerService', 'google']):
                return await self.json_response(msg[10005])
            # if Decimal(data['versionCode']) <= Decimal(0):
            #     return await self.json_response(msg[10005])
            if data['isForce'] not in [0,1]:
                return await self.json_response(msg[10005])
            if data['isSilence'] not in [0,1]:
                return await self.json_response(msg[10005])
            if data['packageType'] not in [0,1]:
                return await self.json_response(msg[10005])
            # 验证谷歌密钥
            r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
            if not await self.check_googl_code(data['google'], r['ggkey']):
                return await self.json_response(data=msg[10003])

            # 将数据转换成json保存到sys_info.app_info中
            app_info = await self.get_cache_result('sys_info', ['app_info'], {'id': 1})

            # 如果原信息非空，将原信息转换成json格式，然后更新
            if not app_info:
                app_info = json.loads(app_info['app_info'])
                app_info['name'] = data['name']
                app_info['versionCode'] = data['versionCode']
                app_info['version'] = data['version']
                app_info['fileUrl'] = data['fileUrl']
                app_info['download'] = data['download']
                app_info['isForce'] = data['isForce']
                app_info['describe'] = data['describe']
                app_info['isSilence'] = data['isSilence']
                app_info['packageType'] = data['packageType']
                app_info['domainName'] = data['domainName']
                app_info['customerService'] = data['customerService']
                app_info = json.dumps(app_info)
            else:
            # 直接写入
            # 去除谷歌验证
                data.pop('google')
                app_info = json.dumps(data)
            if not await self.update_result('sys_info', {'app_info': app_info}, {'id': 1}):
                return await self.json_response(msg[10007])
            # 延迟双删sys_info
            await self.delete_cache_result('sys_info', {'id': 1})
            result = dict(code=20000, msg='更新成功')
            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10007])

