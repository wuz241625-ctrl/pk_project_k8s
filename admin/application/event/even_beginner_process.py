import json

import tornado

from application.base import BaseHandler


# 获取
class getEventBeginnerProcess(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        sql_part = ''
        values = []
        condition, between = await self.split_between_condition(data['searchData'], 'create_at')
        partner_id = data['searchData'].get('partner_id')
        is_finished = data['searchData'].get('is_finished')

        if between or partner_id or is_finished or is_finished ==0:

            if between:
                sql_part = ' where '
                bt_key, bt_start, bt_end = await self.dict_to_between(between)
                sql_part += bt_key
                values += [bt_start, bt_end]

            if sql_part == '':
                if partner_id:
                    sql_part = ' where partner_id = %s '
                    values = [partner_id]
            else:
                if partner_id:
                    sql_part += ' and partner_id = %s '
                    values += [partner_id]

            if sql_part == '':
                if is_finished or is_finished ==0:
                    sql_part = ' where is_finished = %s '
                    values = [is_finished]
            else:
                if is_finished or is_finished ==0:
                    sql_part += ' and is_finished = %s '
                    values += [is_finished]

        # 获取所有数据总数
        sql = "select count(id) from prize_partner_beginner_tutorial_task_progress"
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0

        # 分页查询日志
        sql = 'select * from prize_partner_beginner_tutorial_task_progress'
        sql += sql_part + ' order by create_at desc '
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
