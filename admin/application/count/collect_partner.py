import json
from datetime import datetime,timedelta

from application.base import BaseHandler

# async def get_count(collect_partner_list):
#     data_r = []
#     ids = []
#     for collect_partner in collect_partner_list:
#         collect_partner_ = json.loads(collect_partner)
#         if collect_partner_.get('ids'):
#             ids.append(collect_partner_['ids'])
#         data_r.append(collect_partner_)
#     return data_r,ids

class getCollect(BaseHandler):
    async def post(self):
        collect_partner_list = await self.redis.lrange("collect_partner_balance_lv", 0, -1)
        self.logger.info(f'缓存的所有数据：{collect_partner_list}')
        # data_r ,ids = await get_count(collect_partner_list)
        data_r = []
        filters_data_list = await self.get_results_by_condition('sys_settings', ['value'], {'name': 'partner_balance_statistics'})
        self.logger.info(f'查询到条件数据：{filters_data_list}')
        if len(filters_data_list) > 0:
            current_time = datetime.now()
            filters_data = json.loads(filters_data_list[0]["value"])
            data_select = filters_data['data_select']
            data_select_list = sorted([int(bound.strip()) for bound in str(data_select).split(',') if bound])
            interval_time = int(filters_data['interval_time'])
            self.logger.info(f'选择数据条件：{data_select_list}间隔时间:{interval_time}')
            for data_select in data_select_list:
                for collect_part in collect_partner_list:
                    collect_partner_ = json.loads(collect_part)
                    data_time = datetime.strptime(collect_partner_.get('time'), "%Y-%m-%d %H:%M:%S")
                    time_difference = current_time.timestamp() - data_time.timestamp()
                    if time_difference >= data_select*60*60 and time_difference <= (data_select)*60*60+interval_time*60:
                        if data_select == 0:
                            collect_partner_['time'] = f'now({collect_partner_.get('time')})'
                        else:
                            collect_partner_['time'] = f'{data_select} hours ago({collect_partner_.get('time')})'
                        data_r.append(collect_partner_)
                        break
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)
