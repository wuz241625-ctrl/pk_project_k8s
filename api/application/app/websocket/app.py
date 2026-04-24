import json
import datetime
import traceback

from tornado import websocket
from tornado.ioloop import IOLoop

from application.app.agent import agent
from application.base import BaseHandler, RewriteJsonEncoder
from application.app.home import home
from application.app.issue import issue
from application.app.login import login
from application.message import msg
from application.app.my import my

user_socket = dict()


# 登入
class Websocket(BaseHandler, websocket.WebSocketHandler):
    token = None

    def check_origin(self, origin: str):
        return True

    async def open(self, *args: str, **kwargs: str):
        try:
            token = self.request.arguments['token'][0]
        except Exception:
            return
        try:
            # 验证token
            exp, user_id = await self.decode_token(token.decode('utf-8'))
            if datetime.datetime.now() > datetime.datetime.fromtimestamp(int(exp)):
                return await self.write_message(json.dumps(msg[10101]))
            user = await self.get_result_by_condition('partner', ['status', 'type'], {'id': user_id})
            # if not user or user['status'] == 0:
            # 未激活也可以登录进行充值
            if not user:
                return await self.write_message(json.dumps(msg[10101]))
            # if user_socket[user_id] and not user_socket[user_id].token == token:
            #     return await self.write_message(json.dumps(msg[10101]))

            # self.token = await self.encode_token(user_id)
            self.token = str(token, 'utf-8')
            user_socket[user_id] = self
            result = msg[10200]
            result['token'] = self.token
            self.current_user = {'id': user_id}
            self.current_user['user_type'] = user['type']
            self.logger.info('{id}连接了服务器'.format(id=user_id))
        except Exception:
            await self.write_message(json.dumps(msg[10100]))

    async def on_message(self, message):
        try:
            if hasattr(self, 'token') and hasattr(self, 'current_user') and self.current_user and 'id' in self.current_user.keys():
                _token = await self.redis.hget('login_partner', self.current_user['id'])
                if not self.token == _token:
                    self.token = None
                    user_socket[self.current_user['id']] = None
                    self.current_user = None
                    return await self.write_message(json.dumps(msg[10101], cls=RewriteJsonEncoder))
        except Exception as e:
            self.logger.exception("on_message", traceback.print_exc())
            return
        try:
            message_data = json.loads(message)
            if message_data['type']:
                action = message_data['type'].split('.')
                data = message_data['data']
                if data and not await self.is_valid_data(data):
                    return await self.write_message(json.dumps(msg[10100]))
                msg_r = msg[10100]
                if action[0] == 'login':  # 登陆
                    msg_r = await login.Login(self, action[1], data)
                if action[0] == 'home':  # 主页
                    msg_r = await home.Home(self, action[1], data)
                if action[0] == 'issue':  # 代付
                    msg_r = await issue.Issue(self, action[1], data)
                if action[0] == 'agent':  # 代理
                    msg_r = await agent.Agent(self, action[1], data)
                if action[0] == 'my':  # 我的
                    msg_r = await my.My(self, action[1], data)
                return await self.write_message(json.dumps(msg_r, cls=RewriteJsonEncoder))
                # # 已支付通知
                # # 超时通知
                # msgs = await self.redis.keys('msg_timeout_{partner_id}'.format(partner_id=self.current_user['id']))
                # if msgs:
                #     await self.write_message(json.dumps(msg[10313]))  # 发送消息
                #     for i in msgs:
                #         await self.redis.delete(i)  # 移除消息
                # # 代付新订单通知
        except Exception as e:
            self.logger.exception(e)
            await self.write_message(json.dumps(msg[10100]))

    def on_close(self):
        if self.current_user and self.current_user['id']:
            self.logger.info('{id}断开了服务器'.format(id=self.current_user['id']))
            IOLoop.current().add_callback(self.clear_data)

    # 清除
    async def clear_data(self):
        await issue.grabOrder(self, {'status': 0})
        # 清除socket
        if self.current_user['id'] in user_socket:
            del user_socket[self.current_user['id']]

