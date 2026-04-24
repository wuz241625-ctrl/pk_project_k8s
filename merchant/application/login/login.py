import json
import bcrypt
import tornado
from pymysql.converters import escape_string
from application.base import BaseHandler
from application.message import msg


# 登入
class singIn(BaseHandler):
    async def post(self):
        try:
            # 获取并解析数据
            data = json.loads(self.request.body)
            # 检查参数丢失
            if await self.is_null(data, ['username', 'password', 'googlecode']):
                return await self.json_response(data=msg[10002])
            # 除去空格
            username = escape_string(data.get('username', None).strip())
            password = escape_string(data.get('password', None).strip())
            googlecode = escape_string(data.get('googlecode', None).strip())
            # 查找账号
            self.user = await self.get_result_by_condition('merchant',
                                                           ['id', 'cellphone', 'name', 'hash_login', 'gg_key',
                                                            'status'], {"cellphone": username})
            # 检查密码
            if not self.user or not bcrypt.checkpw(password.encode('utf8'), self.user['hash_login'].encode('utf8')):
                return await self.json_response(data=msg[10001])

            # 查看状态
            if self.user['status'] == 0:
                return await self.json_response(data=msg[10002])

            # # 检查谷歌验证码
            if not await self.check_googl_code(googlecode, self.user['gg_key']):
                return await self.json_response(data=msg[10003])
            # 设置cookie
            await self.set_my_cookie('user', str(self.user['id']))
            self.xsrf_token.decode('utf8')
            result = dict(code=20000, msg='登录成功')
            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10000])


# 获取用户信息
class getUserInfo(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        result = dict(code=20000, data=self.current_user, msg='获取成功')
        return await self.json_response(result)


# 登出
class singOut(BaseHandler):
    async def post(self):
        self.clear_cookie('id')
        result = dict(code=20000, msg='退出成功')
        return await self.json_response(result)
