import decimal
import json
import asyncio
import sys
from decimal import Decimal

import tornado

from application.base import BaseHandler
from application.message import msg


# 获取


#getDfDiscount
class getDfDiscount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_cache_result('sys_info', ['range_df'])
        if data_r['range_df']:
            data_r = json.loads(data_r['range_df'])
        else:
            data_r = {}
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

#updateDfDiscount
class updateDfDiscount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)

            # 检查isOpen1-6是否为0或1
            for i in range(1, 7):
                if data['isOpen' + str(i)] not in [0, 1]:
                    return await self.json_response(msg[10005])

            # 验证谷歌密钥
            r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
            if not await self.check_googl_code(data['google'], r['ggkey']):
                return await self.json_response(data=msg[10003])

            # 将数据转换成json保存到sys_info.app_info中
            range_df = await self.get_cache_result('sys_info', ['range_df'], {'id': 1})

            # 如果原信息非空，将原信息转换成json格式，然后更新
            if not range_df:
                range_df = json.loads(range_df['range_df'])
                # 判断本次是否更新isOpen1-6
                for i in range(1, 7):
                    if 'isOpen' + str(i) in data:
                        range_df['isOpen' + str(i)] = data['isOpen' + str(i)]
                # 判断本次是否更新rangemin1-6
                for i in range(1, 7):
                    if 'rangeMin' + str(i) in data:
                        range_df['rangemin' + str(i)] = data['rangemin' + str(i)]
                # 判断本次是否更新rangemax1-6
                for i in range(1, 7):
                    if 'rangeMax' + str(i) in data:
                        range_df['rangemax' + str(i)] = data['rangemax' + str(i)]
                #         disprice1-6
                for i in range(1, 7):
                    if 'disprice' + str(i) in data:
                        range_df['disprice' + str(i)] = data['disprice' + str(i)]
                range_ds = json.dumps(range_df)
            else:
            # 直接写入
            # 去除谷歌验证
                data.pop('google')
                range_ds = json.dumps(data)
            if not await self.update_result('sys_info', {'range_df': range_ds}, {'id': 1}):
                return await self.json_response(msg[10007])
            # 延迟双删sys_info
            await self.delete_cache_result('sys_info', {'id': 1})
            result = dict(code=20000, msg='更新成功')
            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10007])


#getUsdtDfDiscount
class getUsdtDfDiscount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data_r = await self.get_cache_result('sys_info', ['range_usdt_df'])
        if data_r['range_usdt_df']:
            data_r = json.loads(data_r['range_usdt_df'])
        else:
            data_r = {}
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)

class updateUsdtDfdiscount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)

            # 检查isOpen1-6是否为0或1
            for i in range(1, 7):
                if data['isOpen' + str(i)] not in [0, 1]:
                    return await self.json_response(msg[10005])

            # 验证谷歌密钥
            r = await self.get_result_by_condition('admin', ['ggkey'], {"id": self.current_user['id']})
            if not await self.check_googl_code(data['google'], r['ggkey']):
                return await self.json_response(data=msg[10003])

            # 将数据转换成json保存到sys_info.app_info中
            range_usdt_df = await self.get_cache_result('sys_info', ['range_usdt_df'], {'id': 1})

            # 如果原信息非空，将原信息转换成json格式，然后更新
            if not range_usdt_df:
                range_usdt_df = json.loads(range_usdt_df['range_usdt_df'])
                # 判断本次是否更新isOpen1-6
                for i in range(1, 7):
                    if 'isOpen' + str(i) in data:
                        range_usdt_df['isOpen' + str(i)] = data['isOpen' + str(i)]
                # 判断本次是否更新rangemin1-6
                for i in range(1, 7):
                    if 'rangeMin' + str(i) in data:
                        range_usdt_df['rangemin' + str(i)] = data['rangemin' + str(i)]
                # 判断本次是否更新rangemax1-6
                for i in range(1, 7):
                    if 'rangeMax' + str(i) in data:
                        range_usdt_df['rangemax' + str(i)] = data['rangemax' + str(i)]
                #         disprice1-6
                for i in range(1, 7):
                    if 'disprice' + str(i) in data:
                        range_usdt_df['disprice' + str(i)] = data['disprice' + str(i)]
                range_ds = json.dumps(range_usdt_df)
            else:
            # 直接写入
            # 去除谷歌验证
                data.pop('google')
                range_ds = json.dumps(data)
            if not await self.update_result('sys_info', {'range_usdt_df': range_ds}, {'id': 1}):
                return await self.json_response(msg[10007])
            # 延迟双删sys_info
            await self.delete_cache_result('sys_info', {'id': 1})
            result = dict(code=20000, msg='更新成功')
            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10007])