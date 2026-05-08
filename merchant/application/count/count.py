import json
from datetime import datetime

import tornado

from application.base import BaseHandler
from application.message import msg
from application.timezone import display_today_between


# 统计
class getCount(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['type', 'serchData']):
            return msg[10007]
        
        table = 'orders_ds where' if data['type'] == 'ds' else 'orders_df where parent_id = \'\' and'
        
        sql = """select count(id) as count, ifnull(sum(amount), 0) as amount, ifnull(sum(if(status>2,poundage,0)), 0) as poundage, 
                    count(if(status>2,id,null)) as count_s, ifnull(sum(if(status>2,amount,0)), 0) as amount_s, 
                    count(if(status<0,id,null)) as count_f, ifnull(sum(if(status<0,amount,0)), 0) as amount_f 
                    from {table} time_create between %s and %s and merchant_id=%s""".format(table=table)
        data['serchData'].append(self.current_user['id'])
        data_r = (await self.query(sql, *data['serchData']))[0]
        data_r['rate'] = data_r['count_s']/(data_r['count_s']+data_r['count_f']) * 100 if data_r['count_s'] > 0 else 0
        # 获取商户余额
        sql = """select balance, balance_frozen from merchant where id=%s"""
        r = await self.query(sql, self.current_user['id'])
        if not r:
            return await self.json_response(msg[10012])
        r = r[0]
        data_r['balance'] = r['balance']
        data_r['balance_frozen'] = r['balance_frozen']
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


# 7日数据统计
class getCountOneW(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['type', 'datatype']):
            return msg[10007]
        
        table = 'orders_ds where' if data['type'] == 'ds' else 'orders_df where parent_id = \'\' and'
        
        sql_str = {
            'count': 'count(id)',
            'amount': 'ifnull(sum(amount), 0)',
            'count_s': 'count(if(status>2,id,null))',
            'amount_s': 'ifnull(sum(if(status>2,amount,0)), 0)',
            'count_f': 'count(if(status<0,id,null))',
            'amount_f': 'ifnull(sum(if(status<0,amount,0)), 0)',
            'poundage': 'ifnull(sum(if(status>2,poundage,0)), 0)',
            'rate': 'count(if(status>2,id,null)) as count_s,count(if(status<0,id,null))',
        }
        sql = """select {sql_str} as number, datediff(curdate(), time_create) as days from {table} merchant_id=%s and 
                    time_create >= curdate()-interval 7 day and time_create < curdate() group by days
                    """.format(sql_str=sql_str[data['datatype']], table=table)
        r = await self.query(sql, self.current_user['id'])
        if data['datatype'] == 'rate':
            for i in r:
                i['number'] = i['count_s']/(i['number']+i['count_s']) * 100 if i['count_s'] > 0 else 0
        data_r = [0, 0, 0, 0, 0, 0, 0]
        for i in r:
            data_r[7-i['days']] = i['number']
        result = dict(code=20000, data=data_r, msg='获取成功')
        return await self.json_response(result)


class getBalanceRecord(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if (not condition or not condition.get('code')) and not between:
            between = display_today_between('time_create')
        condition['user_type'] = 1
        condition['user_id'] = self.current_user['id']
        # flag 需要特殊处理的标记标记  例如  code not like '%_%'
        keys = ['code', 'change_before', 'amount', 'change_after', 'time_create', 'record_type', 'merchant_code']
        data_r, total = await self.get_result('balance_record', keys, condition=condition, between=between, limit=data['size'],
                                              offset=data['page'], order_by='desc', order_field='id', flag = True)
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
