import json

import tornado

from application.base import BaseHandler


# 获取
class getEventLogs(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        sql_part = ''
        values = []
        condition, between = await self.split_between_condition(data['searchData'], 'created_at')
        prize_id = data['searchData'].get('prize_id')
        user_id = data['searchData'].get('user_id')

        if between or prize_id or user_id:

            if between:
                sql_part = ' where '
                bt_key, bt_start, bt_end = await self.dict_to_between(between)
                sql_part += bt_key
                values += [bt_start, bt_end]

            if sql_part == '':
                if prize_id:
                    sql_part = ' where prize_id = %s '
                    values = [prize_id]
            else:
                if prize_id:
                    sql_part += ' and prize_id = %s '
                    values += [prize_id]

            if sql_part == '':
                if user_id:
                    sql_part = ' where user_id = %s '
                    values = [user_id]
            else:
                if user_id:
                    sql_part += ' and user_id = %s '
                    values += [user_id]


        # 添加 prize_title 的查询条件（精确匹配）
        if 'prize_title' in data['searchData'] and data['searchData']['prize_title']:
            prize_title = data['searchData']['prize_title']
            if sql_part:
                sql_part += ' and '
            else:
                sql_part = ' where '
            sql_part += 'prize_title = %s'
            values.append(prize_title)

        # 获取所有数据总数
        sql = "select count(id) from prize_earn_log"
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0

        # 分页查询日志
        sql = 'select * from prize_earn_log'
        sql += sql_part + ' order by created_at desc '
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
