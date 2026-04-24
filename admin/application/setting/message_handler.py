import json
from datetime import datetime
import tornado
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg

class AddMessage(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        required_fields = ['type', 'subject', 'content']
        for field in required_fields:
            if not data.get(field):
                return await self.json_response(msg[10007])
        
        message = {
            'to_id': data.get('to_id') if data.get('to_id') else None,  # 空字符串转为None，表示全员
            'from_id': self.current_user['id'],
            'type': data['type'],
            'subject': data['subject'],
            'content': data['content'],
            'send_time': datetime.now(),
            'status': 1,  # 1待发送
            'created_at': datetime.now()
        }

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    k, p, v = await self.dict_to_kv(message)
                    sql = f"INSERT INTO message ({k}) VALUES ({p})"
                    await cur.execute(sql, (*v,))
                    message_id = cur.lastrowid
                    await conn.commit()
                    return await self.json_response(dict(code=20000, msg='消息创建成功', data=message_id))
                except Exception as e:
                    await conn.rollback()
                    return await self.json_response(msg[10007])

class DeleteMessage(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if not data.get('id'):
            return await self.json_response(msg[10007])
            
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 删除消息
                    sql = "DELETE FROM message WHERE id = %s"
                    await cur.execute(sql, (data['id'],))
                    
                    # 删除相关的用户消息记录
                    sql = "DELETE FROM user_message WHERE msg_id = %s"
                    await cur.execute(sql, (data['id'],))
                    
                    await conn.commit()
                    
                    # 清除所有用户的消息缓存
                    pattern = "user_messages:*"
                    keys = await self.redis.keys(pattern)
                    if keys:
                        await self.redis.delete(*keys)
                        
                    return await self.json_response(dict(code=20000, msg='消息删除成功'))
                except Exception as e:
                    await conn.rollback()
                    return await self.json_response(msg[10007])

class GetMessages(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        page = int(data.get('page', 1))
        size = int(data.get('size', 10))
        
        sql_where = []
        values = []
        
        if data.get('searchData'):
            search_data = data['searchData']
            
            # 处理时间范围条件
            condition, between = await self.split_between_condition(search_data, 'send_time')
            if between:
                bt_key, bt_start, bt_end = await self.dict_to_between(between)
                sql_where.append(bt_key)
                values.extend([bt_start, bt_end])
            
            # 处理标题模糊查询
            if search_data.get('subject'):
                sql_where.append('subject LIKE %s')
                values.append(f'%{search_data["subject"]}%')
        
        where_clause = " WHERE " + " AND ".join(sql_where) if sql_where else ""
        
        # 获取总数
        count_sql = f"SELECT COUNT(*) as total FROM message {where_clause}"
        total = await self.query(count_sql, *values)
        total = total[0]['total'] if total else 0
        
        # 分页查询
        sql = f"""
            SELECT * FROM message 
            {where_clause}
            ORDER BY send_time DESC 
            LIMIT %s OFFSET %s
        """
        values.extend([size, (page - 1) * size])
        
        messages = await self.query(sql, *values)
        
        result = dict(code=20000, data=messages, total=total, msg='获取成功')
        return await self.json_response(result)

class PublishMessage(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if not data.get('id'):
            return await self.json_response(msg[10007])
            
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 获取消息详情
                    sql = "SELECT * FROM message WHERE id = %s AND from_id = %s"
                    await cur.execute(sql, (data['id'], self.current_user['id']))
                    message = await cur.fetchone()
                    if not message:
                        return await self.json_response(msg[10007])
                    
                    # 更新消息状态为已发送
                    sql = "UPDATE message SET status = 2 WHERE id = %s"
                    if not await cur.execute(sql, (data['id'],)):
                        return await self.json_response(msg[10007])

                    # 构建通知数据
                    notification = {
                        'id': message.get('id'),
                        'subject': message.get('subject'),
                        'content': message.get('content'),
                        'send_time': message.get('send_time').strftime('%Y-%m-%d %H:%M:%S'),
                        'type': message.get('type'),
                        'user_meg_status': 0
                    }
                    notification_data = {
                        'type': 'new_message',
                        'data': notification
                    }
                    
                    # 根据接收者发布到不同的通道
                    if message['to_id']:
                        # 发送给指定用户
                        for user_id in message['to_id'].split(','):
                            channel = f'user_channel_{user_id}'
                            await self.redis.publish(channel, json.dumps(notification_data))
                    else:
                        # 发送给所有用户
                        channel = 'public_channel'
                        await self.redis.publish(channel, json.dumps(notification_data))
                    
                    # 清除相关用户的消息缓存
                    if message['to_id']:
                        user_ids = [int(uid) for uid in message['to_id'].split(',')]
                    else:
                        # 全员消息，获取所有redis中已有缓存的用户
                        pattern = "user_messages:*:p*:s*"
                        keys = await self.redis.keys(pattern)
                        user_ids = set()
                        for key in keys:
                            user_id = key.split(':')[1]
                            try:
                                user_ids.add(int(user_id))
                            except (ValueError, IndexError):
                                continue
                    
                    # 清除每个用户的消息缓存
                    for user_id in user_ids:
                        pattern = f"user_messages:{user_id}:p*:s*"
                        keys = await self.redis.keys(pattern)
                        if keys:
                            await self.redis.delete(*keys)

                    await conn.commit()
                    return await self.json_response(dict(code=20000, msg='消息发布成功'))
                except Exception as e:
                    await conn.rollback()
                    self.logger.exception(e)
                    return await self.json_response(msg[10007])

class UpdateMessage(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if not data.get('id'):
            return await self.json_response(msg[10007])
            
        required_fields = ['type', 'subject', 'content']
        for field in required_fields:
            if not data.get(field):
                return await self.json_response(msg[10007])
                
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 检查消息是否存在且属于当前用户
                    sql = "SELECT status FROM message WHERE id = %s AND from_id = %s"
                    await cur.execute(sql, (data['id'], self.current_user['id']))
                    result = await cur.fetchone()
                    
                    if not result:
                        return await self.json_response(msg[10007])
                    
                    # 检查消息是否已发布
                    if result['status'] == 2:
                        return await self.json_response(msg[10007])
                    
                    # 更新消息
                    update_data = {
                        'to_id': data.get('to_id') if data.get('to_id') else None,  # 空字符串转为None，表示全员
                        'type': data['type'],
                        'subject': data['subject'],
                        'content': data['content'],
                    }
                    
                    # 构建更新SQL
                    update_parts = []
                    values = []
                    for key, value in update_data.items():
                        update_parts.append(f"{key} = %s")
                        values.append(value)
                    values.append(data['id'])  # WHERE条件的参数
                    
                    sql = f"UPDATE message SET {', '.join(update_parts)} WHERE id = %s"
                    if not await cur.execute(sql, tuple(values)):
                        return await self.json_response(msg[10007])
                        
                    await conn.commit()
                    return await self.json_response(dict(code=20000, msg='消息修改成功'))
                except Exception as e:
                    await conn.rollback()
                    return await self.json_response(msg[10007])