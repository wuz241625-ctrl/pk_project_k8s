import json
import asyncio
from typing import List, Optional

from application.lakshmi_api.base_ws import BaseHandler
from tornado import websocket
from tornado.ioloop import IOLoop
from datetime import datetime, timedelta, time

from application.lakshmi_api.models.user import User
from application.utils import StringUtils
from constants import RedisKeys
import global_resources
from tornado.options import define, options

class Websocket(BaseHandler, websocket.WebSocketHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis = global_resources.redis
        self.redis_pub = global_resources.redis_pub
        self.logger = global_resources.logger
        self.personal_channel = None
        self.public_channel_name = 'public_channel'
        self.public_channel = None
        self.personal_channel_name = None
        self.check_heartbeat = None
        self.current_user = None
        self.received_heartbeat = False
        self.message_handlers = dict(
            heartbeat=self.handle_heartbeat,
        )

    def check_origin(self, origin):
        return True

    async def open(self):
        try:
            self.logger.info("WebSocket 连接已建立，准备解析 token...")
            token = self.request.arguments.get('token')
            self.logger.info(f"原始 token 参数: {token}")

            if not token:
                self.logger.warning("未提供 token，关闭连接。")
                await self.write_message("no offer token，close session")
                self.close()
                return

            token = token[0].decode()
            self.logger.info(f"解析后的 token: {token}")
            if not token:
                await self.write_message("close session with some reason")
                self.close()
                return

            token = self.request.arguments.get('token')
            token = token[0].decode()
            with self.application.db_orm.sessionmaker() as session:
                self.logger.info("正在通过 token 查询用户信息...")

                self.current_user = session.query(User).filter_by(authentication_token=token).first()
            if not self.current_user:
                self.logger.warning(f"认证失败，未找到用户，token: {token}")
                await self.write_message("auth error")
                self.close()
                return
            else:
                self.logger.info(f"用户认证成功，用户ID: {self.current_user.id}")
                # 使用用户 ID 作为 key 存储连接
                user_id = self.current_user.id
                self.logger.info(f"准备使用用户ID {user_id} 作为连接标识")
                # 检查是否存在旧连接
                if await self.redis.hexists(RedisKeys.REDIS_WS_CLIENTS, user_id):
                    self.logger.info(f"检测到用户 {user_id} 已存在旧连接，准备发送断开通知")
                    # 通知旧连接关闭
                    await self.redis_pub.publish(f"user_channel_{user_id}",
                                                json.dumps({"type": "connection",
                                                            "content": "new connection established, closing this one"}))
                else:
                    self.logger.info(f"未检测到用户 {user_id} 的旧连接")
                # 存储连接信息
                connection_info = {
                    "connected_at": datetime.now().isoformat(),
                    "ip": self.request.remote_ip,
                    "user_agent": self.request.headers.get("User-Agent", "")
                }
                await self.redis.hset(RedisKeys.REDIS_WS_CLIENTS, user_id, json.dumps(connection_info))
                self.logger.info(f"用户 {user_id} 的连接信息已写入 Redis：{connection_info}")
                connected_count = await self.redis.hlen(RedisKeys.REDIS_WS_CLIENTS)
                self.logger.info(f"new client connect.userID: {user_id}, connected count: {connected_count}")

                # redis subscribe
                self.personal_channel_name = "user_channel_{}".format(self.current_user.id)
                
                self.logger.info(f"订阅用户私有频道：{self.personal_channel_name}")
                self.logger.info(f"订阅公共频道：{self.public_channel_name}")

                self.public_channel = (await self.redis_sub.subscribe(self.public_channel_name))[0]
                self.personal_channel = (await self.redis_sub.subscribe(self.personal_channel_name))[0]
                IOLoop.current().spawn_callback(self.redis_listener)
                self.logger.info("启动 Redis 消息监听器")
                def check_response():
                    if not self.received_heartbeat:
                        self.logger.warning(f"用户 {user_id} 心跳检测超时，关闭连接")
                        self.close()
                    else:
                        self.logger.info(f"用户 {user_id} 心跳正常")
                        self.received_heartbeat = False

                self.check_heartbeat = IOLoop.current().call_later(90, check_response)
                self.logger.info("已设置 90 秒的心跳检测")

                self.TRACE_ID = options.TRACE_ID
                self.RQ_ID = options.RQ_ID
                self.logger.info(f"初始化 TRACE_ID: {self.TRACE_ID}, RQ_ID: {self.RQ_ID}")
        except Exception as e:
            self.logger.exception(f"WebSocket 连接初始化异常: {e}")
            await self.write_message("internal server error")
            self.close()
    
    async def on_message(self, message):
        # options.TRACE_ID = self.TRACE_ID
        # options.RQ_ID = self.RQ_ID
        if hasattr(self, 'TRACE_ID'):
            options.TRACE_ID = self.TRACE_ID
        if hasattr(self, 'RQ_ID'):
            options.RQ_ID = self.RQ_ID
            
        # 获取当前用户ID和通道信息
        current_user_id = self.current_user.id if self.current_user else None
        current_channel = self.personal_channel_name  # 格式为 "user_channel_{user_id}"

        self.logger.info(
            f"public_channel: {self.public_channel_name},"
            f"personal_channel: {current_channel}, "
            f"user_id: {current_user_id}, "
            f"message type: {type(message)}, "
            f"receive socket message：{message}"
        )

        message_is_json = StringUtils.is_valid_json(message)
        if message_is_json:
            message_data = json.loads(message)
            message_type = message_data['type']
            message_content = message_data['content']
            handler = self.message_handlers.get(message_type)
            if handler:
                await handler(message_content)
            else:
                self.logger.warning(f"发现未处理的消息 message: {message}")
        else:
            if message == "close":
                await self.write_message("Message received: {}, and close this connect".format(message))
                self.close(34001, "收到客户端的关闭请求")
        self.TRACE_ID = options.TRACE_ID
        self.RQ_ID = options.RQ_ID

    def on_close(self):
        options.TRACE_ID = self.TRACE_ID
        options.RQ_ID = self.RQ_ID

        # 记录连接关闭的原因
        close_code = self.close_code
        close_reason = self.close_reason
        self.logger.info(
            f"WebSocket connection closed. connect.userID: {self.current_user.id if self.current_user else 'unknown'}, "
            f"Close Code: {close_code}, "
            f"Close Reason: {close_reason}"
        )

        # 从连接字典中移除
        if self.current_user:
            user_id = self.current_user.id

            async def cleanup():
                # 删除连接信息
                await self.redis.hdel(RedisKeys.REDIS_WS_CLIENTS, user_id)
                connected_count = await self.redis.hlen(RedisKeys.REDIS_WS_CLIENTS)
                self.logger.info(f"client close connect.userID: {user_id}, connected count: {connected_count}")

                # 取消订阅
                await self.redis_sub.unsubscribe(self.public_channel_name)
                if self.personal_channel_name is not None:
                    await self.redis_sub.unsubscribe(self.personal_channel_name)

            IOLoop.current().add_callback(cleanup)

        self.TRACE_ID = options.TRACE_ID
        self.RQ_ID = options.RQ_ID

    # 获取连接数的方法
    async def get_connected_clients_count(self) -> int:
        """获取当前连接数"""
        return await self.redis.hlen(RedisKeys.REDIS_WS_CLIENTS)

    # 获取指定用户连接信息
    async def get_client_by_user_id(self, user_id: int) -> Optional[dict]:
        """获取指定用户的连接信息"""
        connection_info = await self.redis.hget(RedisKeys.REDIS_WS_CLIENTS, str(user_id))
        if connection_info:
            return json.loads(connection_info)
        return None

    # 获取所有连接用户ID
    async def get_connected_user_ids(self) -> List[int]:
        """获取所有已连接的用户ID"""
        user_ids = await self.redis.hkeys(RedisKeys.REDIS_WS_CLIENTS)
        return [int(user_id) for user_id in user_ids]

    # 获取所有连接信息
    async def get_all_connections(self) -> dict:
        """获取所有连接信息"""
        connections = await self.redis.hgetall(RedisKeys.REDIS_WS_CLIENTS)
        return {k: json.loads(v) for k, v in connections.items()}

    async def handle_heartbeat(self, message_content) -> int:
        # vue will respond pong
        if message_content == 'ping':
            self.received_heartbeat = True
        return await self.redis_pub.publish(self.personal_channel_name,
                                            json.dumps({"type": "heartbeat", "content": 'pong'}))

    async def redis_listener(self):
        await asyncio.gather(
            self.personal_channel_listener(),
            self.public_channel_listener()
        )

    async def channel_listener(self, channel):
        while await channel.wait_message():
            message = await channel.get()
            if message is not None:
                # Decode the byte string into a string
                if message.decode('utf-8') == "disconnect_user":
                    self.close()
                else:
                    await self.write_message(message)

    async def personal_channel_listener(self):
        await self.channel_listener(self.personal_channel)

    async def public_channel_listener(self):
        await self.channel_listener(self.public_channel)
