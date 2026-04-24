import json
from application.message import msg
import datetime
from application.base import BaseHandler

class filtersAddOrUpdate(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['bound','num','interval_time','data_select']):
            self.logger.info('必填参数为空')
            return await self.json_response(msg[10007])
        filters_data_sql = """select `value` from sys_settings where name = 'partner_balance_statistics' limit 1"""
        filters_data = await self.query(filters_data_sql)
        if not filters_data:
            data_r = {
                'name': 'partner_balance_statistics',
                'value': json.dumps(data)
            }
            if await self.create_result('sys_settings',data_r):
                result = dict(code=20000, msg='操作成功')
            else:
                return await self.json_response(msg[10007])
        else:
            data_r = {
                'value': json.dumps(data)
            }
            if await self.update_result('sys_settings',data_r,{'name':'partner_balance_statistics'}):
                result = dict(code=20000, msg='操作成功')
            else:
                return await self.json_response(msg[10007])
        return await self.json_response(result)

class filtersDel(BaseHandler):
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            self.logger.info('必填参数为空')
            return await self.json_response(msg[10007])
        if await self.delete_result('filters_data',data):
            result = dict(code=20000, msg='操作成功')
        else:
            return await self.json_response(msg[10007])
        return await self.json_response(result)

class getFilters(BaseHandler):
    async def post(self):
        filters_data_sql = """select `value` from sys_settings where name = 'partner_balance_statistics' limit 1"""
        data_r = await self.query(filters_data_sql)
        if data_r:
            data_r = json.loads(data_r[0]['value'])
            result = dict(code=20000, data=[data_r], msg='获取成功')
        else:
            self.logger.info('未查询到规则信息')
            return await self.json_response(msg[10007])
        return await self.json_response(result)