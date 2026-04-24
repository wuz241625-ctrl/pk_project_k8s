import json
import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        merchant_channle = await self.get_results_by_condition('merchant_channel', ['code', 'rate'], {'merchant_id': self.current_user['id']})
        if not merchant_channle:
            return await self.json_response(data=msg[10007])
        keys = ['code', 'name', 'amount_min', 'amount_max', 'amount_fixed', 'fixed', 'status']
        data_r, total = await self.get_result('channel', keys, condition={'status': 1}, limit=data['size'], offset=data['page'])
        _data_r = []
        for i in data_r:
            _filter = list(filter(lambda m: m['code'] == i['code'], merchant_channle))
            if _filter:
                i['rate'] = _filter[0]['rate']
                _data_r.append(i)
        result = dict(code=20000, data=_data_r, total=total, msg='获取成功')
        return await self.json_response(result)
