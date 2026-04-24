import json
import tornado
from datetime import datetime

from application.base import BaseHandler
from application.message import msg


# 获取
class getEvent(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        serch_data = data.get('serchData', {})

        sql_part = ''
        values = []

        title = serch_data.get('title', '')  # Use .get() to avoid KeyError
        if title:
            title = '%' + title + '%'
            sql_part = " where title like %s"
            values += [title]

        # 获取所有数据总数
        sql = "select count(id) from prize_setting"
        sql += sql_part
        total = await self.query(sql, *values)
        if total:
            total = total[0]['count(id)']
        else:
            total = 0

        # 分页查询
        sql = 'select * from prize_setting'
        sql += sql_part + ' order by created_at desc '
        if data['size'] and data['page'] > -1:
            sql += 'limit %s offset %s'
            values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)

# 添加
class addevent(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        # 检查必需字段是否为空
        if await self.is_null(data, ['title', 'content', 'type', 'participant', 'status', 'begin_at', 'end_at']):
            return await self.json_response(data=msg[10004])

        # 检查标题是否已存在
        if await self.is_exits('prize_setting', 'title', data['title']):
            return await self.json_response(msg[10008])

        # 若添加抽奖活动，检查是否已有启用的抽奖活动
        if data['type'] == 0:
            sql = 'select id from prize_setting where type = 0 and status = 1'
            r = await self.query(sql)
            if r:
                return await self.json_response(msg[10224])

        # 设置创建时间
        data['created_at'] = datetime.now()
        data['updated_at'] = datetime.now()
        # 插入数据
        if not await self.create_result('prize_setting', data):
            return await self.json_response(msg[10004])
        # 返回成功消息
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)

# 更新
class updateevent(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if 'status' not in data and await self.is_null(data,
                                                       ['id', 'status']):
            return await self.json_response(data=msg[10005])
        data['updated_at'] = datetime.now()

        # 获取当前 prize_setting 记录的 type
        sql_get_type = 'SELECT type FROM prize_setting WHERE id = %s'
        type_result = await self.query(sql_get_type, data['id'])

        if not type_result:
            return await self.json_response(data=msg[10005])

        # 提取 type 值
        prize_type = type_result[0]['type']

        # 若添加抽奖活动，检查是否已有启用的抽奖活动
        if prize_type == 0:
            sql = 'select id from prize_setting where type = 0 and status = 1 and id != {id}'.format(id=data['id'])
            r = await self.query(sql)
            if r:
                return await self.json_response(msg[10223])

        if not await self.update_result('prize_setting', data, {'id': data['id']}):
            return await self.json_response(msg[10005])
        result = dict(code=20000, msg='更新成功')
        return await self.json_response(result)

# 删除
class deleteevent(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('prize_setting', {'id': data['id']}):
            return await self.json_response(msg[10006])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)

