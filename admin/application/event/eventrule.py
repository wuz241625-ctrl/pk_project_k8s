import json
import tornado
from datetime import datetime

from application.base import BaseHandler
from application.message import msg


# 获取
class getEventrule(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        # Check if 'serchData' exists in the data
        serch_data = data.get('serchData', {})
        sql_part = ''
        values = []

        title = serch_data.get('title', '')  # Use .get() to avoid KeyError
        if title:
            title = '%' + title + '%'
            sql_part = " where title like %s"
            values += [title]

        # 获取所有数据总数
        sql = "select count(id) from prize_setting_detail"
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0

        # 分页查询
        sql = 'select * from prize_setting_detail'
        sql += sql_part + ' order by created_at desc '
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        eventList = await self.get_results_no_condition('prize_setting',
                                                        ['id', 'title', 'content', 'type', 'participant', 'pic',
                                                         'created_at', 'status', 'begin_at', 'end_at'])

        result = dict(code=20000, data=data_r, total=total, eventList=eventList, msg='获取成功')
        return await self.json_response(result)


# 添加
class addeventrule(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, 
                              ['prize_id', 'title', 'money', 'ratio', 'status']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('prize_setting_detail', 'title', data['title']):
            return await self.json_response(msg[10008])

        event = await self.get_result_by_condition('prize_setting',['id', 'title', 'content', 'type'],{'id': data['prize_id']})
        if not event:
            self.logger.warning('未找到对应的活动')
            return await self.json_response(msg[10004])
        
        # 若为 满赠 活动，检查活动触发下限和上限
        if event.get('type') == 1 or event.get('type') == 2:
            if await self.is_null(data,['prize_limit_min', 'prize_limit_max']):
                return await self.json_response(data=msg[10004])
            # 验证新增的数据上下限是否和活动下其他记录冲突
            if float(data.get('prize_limit_min')) >= float(data.get('prize_limit_max')):
                return await self.json_response(data=msg[10222])

            # 检查下限冲突
            query = '''
                select id from prize_setting_detail
                where prize_limit_min <= %s and prize_limit_max > %s and prize_id= %s
            '''
            count = await self.query(query,*[data.get('prize_limit_min'),data.get('prize_limit_min'),data.get('prize_id')])
            if count :
                return await self.json_response(data=msg[10222])
            # 检查上限冲突
            count = await self.query(query, *[data.get('prize_limit_max'), data.get('prize_limit_max'),data.get('prize_id')])
            if count :
                return await self.json_response(data=msg[10222])
            # 检查上下限把老规则包进去的情况
            query = '''
                select id from prize_setting_detail
                where prize_limit_min >= %s and prize_limit_max < %s and prize_id= %s
            '''
            count = await self.query(query, *[data.get('prize_limit_min'), data.get('prize_limit_max'), data.get('prize_id')])
            if count:
                return await self.json_response(data=msg[10222])
        else :
            data['prize_limit_min'] = None
            data['prize_limit_max'] = None
            
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()
        if not await self.create_result('prize_setting_detail', data):
            return await self.json_response(msg[10004])
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)


# 更新
class updateeventrule(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if 'status' not in data and await self.is_null(data, 
                                                       [['id', 'status']]):
            return await self.json_response(data=msg[10005])

        event = await self.get_result_by_condition('prize_setting', ['id', 'title', 'content', 'type'],
                                                   {'id': data['prize_id']})
        if not event:
            self.logger.warning('未找到对应的活动')
            return await self.json_response(msg[10004])

        # 若为 满赠 活动，检查活动触发下限和上限
        if event.get('type') == 1 or event.get('type') == 2:
            # 未传prize_limit_min和 prize_limit_max ，视为修改状态，不检查上限下限
            if not  await self.is_null(data, ['prize_limit_min', 'prize_limit_max']):
                # 验证新增的数据上下限是否和活动下其他记录冲突
                if float(data.get('prize_limit_min')) >= float(data.get('prize_limit_max')):
                    return await self.json_response(data=msg[10222])

                # 检查下限冲突
                query = '''
                            select id from prize_setting_detail
                            where prize_limit_min <= %s and prize_limit_max > %s and prize_id= %s and id != %s 
                        '''
                count = await self.query(query,
                                         *[data.get('prize_limit_min'), data.get('prize_limit_min'), data.get('prize_id'),data.get('id')])
                if count:
                    return await self.json_response(data=msg[10222])
                # 检查上限冲突
                count = await self.query(query,
                                         *[data.get('prize_limit_max'), data.get('prize_limit_max'), data.get('prize_id')])
                if count:
                    return await self.json_response(data=msg[10222])
                # 检查上下限把老规则包进去的情况
                query = '''
                            select id from prize_setting_detail
                            where prize_limit_min >= %s and prize_limit_max < %s and prize_id= %s and id != %s 
                        '''
                count = await self.query(query,
                                         *[data.get('prize_limit_min'), data.get('prize_limit_max'), data.get('prize_id'),data.get('id')])
                if count:
                    return await self.json_response(data=msg[10222])
        else:
            data['prize_limit_min'] = None
            data['prize_limit_max'] = None
        
        data['updated_at'] = datetime.now()
        if not await self.update_result('prize_setting_detail', data, {'id': data['id']}):
            return await self.json_response(msg[10005])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)


# 删除
class deleteeventrule(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('prize_setting_detail', {'id': data['id']}):
            return await self.json_response(msg[10006])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)

