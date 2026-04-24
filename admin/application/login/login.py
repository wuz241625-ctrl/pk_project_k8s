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
            self.user = await self.get_result_by_condition('admin',
                                                           ['id', 'account', 'name', 'hash_login', 'role', 'ggkey',
                                                            'status'], {"account": username})
            # 检查密码
            if not self.user or not bcrypt.checkpw(password.encode('utf8'), self.user['hash_login'].encode('utf8')):
                return await self.json_response(data=msg[10001])
            # 查看状态
            if self.user['status'] == 0:
                return await self.json_response(data=msg[10002])

            # # 检查谷歌验证码
            if not await self.check_googl_code(googlecode, self.user['ggkey']):
                return await self.json_response(data=msg[10003])
            # 设置cookie
            await self.set_my_cookie('user', str(self.user['id']))
            self.xsrf_token.decode('utf8')
            await self.add_operate(1, self.user['id'])

            result = dict(code=20000, msg='登录成功')
            # 查询用户权限，获取默认跳转地址
            role = await self.get_result_by_condition('roles',['id','permissions'], {"id": self.user['role']})
            if role :
                sql = '''
                    select id, pid, name from permissions 
                    where id not in (select pid from permissions)
                    and id in ({permissions})
                    order by id asc limit 1; 
                '''.format(permissions=role['permissions'])
                data = await self.query(sql)
                if data :
                    result = dict(code=20000, data=data[0], msg='登录成功')

            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10000])


# 获取用户信息
class getUserInfo(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        # 记录请求开始日志
        self.logger.info(" getUserInfo 接口请求开始")
        try:
            # 记录当前用户信息
            self.logger.info(f" 当前用户信息: {self.current_user}")
            # 组装返回结果
            result = dict(code=20000, data=self.current_user, msg='获取成功')
            # 记录返回的数据
            self.logger.info(f" getUserInfo 请求成功，返回数据: {result}")
            return await self.json_response(result)

        except Exception as e:
            # 捕获异常并记录详细错误日志
            self.logger.error(f" getUserInfo 接口错误: {e}", exc_info=True)
            # 记录异常时返回的数据
            result = dict(code=50000, msg="服务器内部错误")
            self.logger.warning(f" getUserInfo 返回错误信息: {result}")
            return await self.json_response(result)


# 获取路由列表
class getRoutes(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        sql = """select id, pid, name from permissions where status=1 and id in ({permissions})""" \
            .format(permissions=self.current_user['permissions'])
        data = await self.query(sql)
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)


# 登出
class singOut(BaseHandler):
    async def post(self):
        self.clear_cookie('id')
        result = dict(code=20000, msg='退出成功')
        return await self.json_response(result)
