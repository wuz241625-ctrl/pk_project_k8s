from datetime import datetime, timedelta
from sqlalchemy import and_, or_
import json

from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.models.message import Message
from application.lakshmi_api.models.user_message import UserMessage

async def clear_user_message_cache(redis_client, user_id):
    """
    清除用户消息相关的所有缓存
    """
    pattern = f"user_messages:{user_id}:*"
    keys = await redis_client.keys(pattern)
    if keys:
        await redis_client.delete(*keys)

class MessageService:
    @staticmethod
    async def create_message(session, redis_client, from_id, to_ids, subject, content, msg_type=1):
        """
        创建新消息
        """
        to_id_str = ','.join(map(str, to_ids)) if to_ids else None
        
        message = Message(
            from_id=from_id,
            to_id=to_id_str,
            type=msg_type,
            subject=subject,
            content=content,
            send_time=datetime.now(),
            status=2  # 直接设置为已发送
        )
        
        session.add(message)
        session.flush()  # 获取消息ID

        # 构建消息数据
        notification_data = {
            'id': message.id,
            'subject': subject,
            'content': content,
            'send_time': message.send_time.strftime('%Y-%m-%d %H:%M:%S'),
            'type': msg_type,
            'user_meg_status': 0
        }

        # 构建websocket消息格式
        ws_message = {
            'type': 'new_message',
            'data': notification_data
        }
        
        # 根据接收者类型发送到不同的通道
        if to_id_str is None:
            # 发送给所有用户
            await redis_client.publish('public_channel', json.dumps(ws_message))
        else:
            # 发送给指定用户
            for user_id in to_ids:
                channel_name = f'user_channel_{user_id}'
                await redis_client.publish(channel_name, json.dumps(ws_message))

        # 清除相关用户的消息缓存
        if to_ids:
            # 如果是指定用户的消息，只清除这些用户的缓存
            for user_id in to_ids:
                await clear_user_message_cache(redis_client, user_id)
        else:
            # 如果是全员消息，需要清除所有用户的消息缓存
            pattern = "user_messages:*"
            keys = await redis_client.keys(pattern)
            if keys:
                await redis_client.delete(*keys)
        
        return message

class GetUserMessages(BaseHandler):
    @handle_errors
    async def get(self):
        """获取用户消息列表"""
        await self.authenticate_current_user()
        
        page = int(self.get_query_argument('page', '1'))
        size = int(self.get_query_argument('size', '10'))
        
        # 尝试从Redis获取缓存
        cache_key = f"user_messages:{self.current_user.id}:p{page}:s{size}"
        cached_data = await self.redis.get(cache_key)
        
        if cached_data:
            self.write(json.loads(cached_data))
            return
            
        with self.db_orm.sessionmaker() as session:
            # 首先通过左连接查询消息和用户消息状态
            base_query = session.query(Message, UserMessage).outerjoin(
                    UserMessage,
                    and_(
                        UserMessage.msg_id == Message.id,
                        UserMessage.user_id == self.current_user.id
                    )
                ).filter(
                    and_(
                        or_(
                            Message.to_id.is_(None),  # 全员消息
                            Message.to_id.like(f'%{self.current_user.id}%')  # 包含当前用户ID的消息
                        ),
                        or_(
                            UserMessage.status.is_(None),  # 未设置状态
                            UserMessage.status != -1
                        ),
                        Message.status == 2
                    )
                )
            
            # 获取总数
            total = base_query.count()
            
            # 分页查询消息
            results = base_query.order_by(Message.id.desc())\
                .offset((page - 1) * size)\
                .limit(size)\
                .all()
            
            # 构建返回数据
            message_list = []
            for msg, user_msg in results:
                user_meg_status = user_msg.status if user_msg else 0  # 如果没有用户消息状态记录，则默认为未读
                message_list.append({
                    'id': msg.id,
                    'subject': msg.subject,
                    'content': msg.content,
                    'send_time': msg.send_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'type': msg.type,
                    'user_meg_status': user_meg_status
                })
            
            response_data = {
                'data': {
                    'messages': message_list,
                    'total': total,
                    'page': page,
                    'size': size
                }
            }
            
            # 设置缓存，过期时间5分钟
            await self.redis.setex(
                cache_key,
                timedelta(minutes=5),
                json.dumps(response_data)
            )
            
            self.write(response_data)

class MarkMessageRead(BaseHandler):
    @handle_errors
    async def post(self):
        """标记消息为已读"""
        await self.authenticate_current_user()
        
        msg_ids = self.get_body_argument('msg_ids')  # 接收消息ID列表字符串
        try:
            msg_id_list = [int(id) for id in msg_ids.split(',')]  # 转换为整数列表
        except ValueError:
            raise ApiError('Invalid message ids format')
        
        with self.db_orm.sessionmaker() as session:
            # 检查消息是否存在且用户有权限读取
            messages = session.query(Message).filter(Message.id.in_(msg_id_list)).all()
            if not messages:
                raise ApiError('Messages not found')
            
            # 验证权限并收集有效的消息ID
            valid_msg_ids = []
            for message in messages:
                if message.to_id is None or str(self.current_user.id) in message.to_id.split(','):
                    valid_msg_ids.append(message.id)
            
            if not valid_msg_ids:
                raise ApiError('No permission to read these messages')
            
            # 检查消息是否已被删除并从有效ID中剔除
            deleted_user_messages = session.query(UserMessage).filter(
                and_(
                    UserMessage.msg_id.in_(valid_msg_ids),
                    UserMessage.user_id == self.current_user.id,
                    UserMessage.status == -1  # 检查是否有已删除的消息
                )
            ).all()
            
            if deleted_user_messages:
                deleted_msg_ids = [um.msg_id for um in deleted_user_messages]
                valid_msg_ids = [msg_id for msg_id in valid_msg_ids if msg_id not in deleted_msg_ids]
            
            # 批量更新或创建用户消息状态
            for msg_id in valid_msg_ids:
                user_message = session.query(UserMessage).filter(
                    and_(
                        UserMessage.msg_id == msg_id,
                        UserMessage.user_id == self.current_user.id
                    )
                ).first()
                
                if not user_message:
                    user_message = UserMessage(
                        msg_id=msg_id,
                        user_id=self.current_user.id,
                        status=1
                    )
                    session.add(user_message)
                else:
                    user_message.status = 1
            
            session.commit()
            
            # 使用公共方法清除缓存
            await clear_user_message_cache(self.redis, self.current_user.id)
            
            self.write({'message': 'success'})

class DeleteUserMessage(BaseHandler):
    @handle_errors
    async def post(self):
        """删除消息"""
        await self.authenticate_current_user()
        
        msg_ids = self.get_body_argument('msg_ids')  # 接收消息ID列表字符串
        try:
            msg_id_list = [int(id) for id in msg_ids.split(',')]  # 转换为整数列表
        except ValueError:
            raise ApiError('Invalid message ids format')
        
        with self.db_orm.sessionmaker() as session:
            # 检查消息是否存在
            messages = session.query(Message).filter(Message.id.in_(msg_id_list)).all()
            if not messages:
                raise ApiError('Messages not found')
            
            # 验证权限并收集有效的消息ID
            valid_msg_ids = []
            for message in messages:
                if message.to_id is None or str(self.current_user.id) in message.to_id.split(','):
                    valid_msg_ids.append(message.id)
            
            if not valid_msg_ids:
                raise ApiError('No permission to delete these messages')
            
            # 批量更新或创建用户消息状态
            for msg_id in valid_msg_ids:
                user_message = session.query(UserMessage).filter(
                    and_(
                        UserMessage.msg_id == msg_id,
                        UserMessage.user_id == self.current_user.id
                    )
                ).first()
                
                if not user_message:
                    user_message = UserMessage(
                        msg_id=msg_id,
                        user_id=self.current_user.id,
                        status=-1
                    )
                    session.add(user_message)
                else:
                    user_message.status = -1
            
            session.commit()
            
            # 使用公共方法清除缓存
            await clear_user_message_cache(self.redis, self.current_user.id)
            
            self.write({'message': 'success'}) 

class MarkAllMessageRead(BaseHandler):
    @handle_errors
    async def post(self):
        """标记所有消息为已读"""
        await self.authenticate_current_user()
        
        with self.db_orm.sessionmaker() as session:
            # 查询所有未读的有效消息
            unread_messages = session.query(Message).outerjoin(
                UserMessage,
                and_(
                    UserMessage.msg_id == Message.id,
                    UserMessage.user_id == self.current_user.id
                )
            ).filter(
                and_(
                    or_(
                        Message.to_id.is_(None),  # 全员消息
                        Message.to_id.like(f'%{self.current_user.id}%')  # 包含当前用户ID的消息
                    ),
                    UserMessage.status.is_(None)  # 未设置状态的消息
                )
            ).all()
            
            if not unread_messages:
                self.write({
                    'message': 'success',
                    'data': {
                        'processed_count': 0
                    }
                })
                return
            
            # 批量更新或创建用户消息状态
            processed_count = 0
            for message in unread_messages:
                user_message = session.query(UserMessage).filter(
                    and_(
                        UserMessage.msg_id == message.id,
                        UserMessage.user_id == self.current_user.id
                    )
                ).first()
                
                if not user_message:
                    user_message = UserMessage(
                        msg_id=message.id,
                        user_id=self.current_user.id,
                        status=1
                    )
                    session.add(user_message)
                else:
                    user_message.status = 1
                processed_count += 1
            
            session.commit()
            
            # 清除缓存
            await clear_user_message_cache(self.redis, self.current_user.id)
            
            self.write({
                'message': 'success',
                'data': {
                    'processed_count': processed_count
                }
            }) 

class GetMessageDetail(BaseHandler):
    @handle_errors
    async def get(self):
        """获取指定消息详情并标记为已读"""
        await self.authenticate_current_user()
        
        # 从查询参数获取消息ID
        message_id = self.get_query_argument('msg_id', None)
        if not message_id:
            raise ApiError('Message id is required')
            
        try:
            message_id = int(message_id)
        except ValueError:
            raise ApiError('Invalid message id format')
        
        with self.db_orm.sessionmaker() as session:
            # 查询消息
            message = session.query(Message).filter(Message.id == message_id).first()
            if not message:
                raise ApiError('Message not found')
            
            # 验证权限
            if message.to_id and str(self.current_user.id) not in message.to_id.split(','):
                raise ApiError('No permission to read this message')
            
            # 检查消息状态
            user_message = session.query(UserMessage).filter(
                and_(
                    UserMessage.msg_id == message_id,
                    UserMessage.user_id == self.current_user.id
                )
            ).first()
            
            if user_message and user_message.status == -1:
                raise ApiError('Cannot read deleted message')
            
            # 标记为已读
            if not user_message:
                user_message = UserMessage(
                    msg_id=message_id,
                    user_id=self.current_user.id,
                    status=1
                )
                session.add(user_message)
            elif user_message.status != 1:
                user_message.status = 1
            
            session.commit()
            
            # 清除缓存
            await clear_user_message_cache(self.redis, self.current_user.id)
            
            # 返回消息详情
            self.write({
                'data': {
                    'id': message.id,
                    'subject': message.subject,
                    'content': message.content,
                    'send_time': message.send_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'type': message.type,
                    'user_meg_status': 1  # 已读
                }
            }) 