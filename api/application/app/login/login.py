import secrets
import string

import bcrypt
from aiomysql import DictCursor
from pymysql.converters import escape_string
from application.message import msg
from application.app.websocket import app


async def Login(self, action, data):
    if action == 'singIn':
        return await singIn(self, data)
    if action == 'singOut':
        return await singOut(self, data)
    if action == 'register':
        return await register(self, data)
    if action == 'forget':
        return await forget(self, data)
    if action == 'sendCode':
        return await sendCode(self, data)


async def singIn(self, data):
    # 获取参数
    if await self.is_null(data, ['cellphone', 'password']):
        return msg[10100]
    cellphone = escape_string(data.get('cellphone', None).strip())
    password = escape_string(data.get('password', None).strip())
    user = await self.get_result_by_condition('partner', ['id', 'cellphone', 'hash_login', 'status', 'type'],
                                              {"cellphone": cellphone})
    # 检查账号
    if not user:
        return msg[10201]
    # 检查密码
    if password:
        if not bcrypt.checkpw(password.encode('utf8'), user['hash_login'].encode('utf8')):
            return msg[10201]
    # 查看状态
    # 未激活也可以登录进行充值
    # if user['status'] == 0:
    #     return msg[10202]
    # token
    self.current_user = {'id': user['id']}
    self.token = await self.encode_token(user['id'])
    self.current_user['user_type'] = user['type']
    result = msg[10200]
    result['token'] = self.token
    result['user_type'] = self.current_user['user_type']
    app.user_socket[user['id']] = self
    self.logger.info('{id}连接了服务器'.format(id=user['id']))
    # 放置在hash中
    await self.redis.hset('login_partner', user['id'], self.token)
    return result


# 登出
async def singOut(self, data):
    self.token = None
    self.user_socket[self.current_user['id']] = None
    self.current_user = None


# 验证码
async def sendCode(self, data):
    if await self.is_null(data, ['cellphone']) or not data['cellphone'].isdigit():
        return msg[10100]
    if not await self.send_code(data['cellphone']):
        return msg[10103]
    return msg[10102]


# 注册
async def register(self, data):
    if await self.is_null(data, ['cellphone', 'vercode', 'password', 'name']):
        return msg[10100]
    cellphone = escape_string(data.get('cellphone', None).strip())
    vercode = escape_string(data.get('vercode', None).strip())
    password = escape_string(data.get('password', None).strip())
    name = escape_string(data.get('name', None).strip())
    # 校验验证码
    if not await self.redis.get('phonecode{cellphone}_{code}'.format(cellphone=cellphone, code=vercode)):
        return msg[10204]
    # 查找号码是否重复
    if await self.get_result_by_condition('partner', ['id'], {'cellphone': cellphone}):
        return msg[10203]
    # 生成密码
    hash_login = await self.password_create(password)
    hash_trade = await self.password_create('123456')
    async with self.application.db.acquire() as conn:
        async with conn.cursor(DictCursor) as cur:
            try:
                # 生成邀请码
                sql = """select id from partner where invitation_code=%s"""
                while True:
                    invitation_code = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
                    if not await cur.execute(sql, invitation_code):
                        break
                # 新增码商
                sql = """insert into partner (name,cellphone,hash_login,hash_trade,certified,invitation_code) value (%s,%s,%s,%s,%s,%s)"""
                value = [name, cellphone, hash_login, hash_trade, 1, invitation_code]
                if not await cur.execute(sql, value):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return msg[10206]
                # 新增关系树(自己)
                sql = """select id from partner where cellphone=%s"""
                if not await cur.execute(sql, data['cellphone']):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return msg[10206]
                _id = (await cur.fetchall())[0]['id']
                sql = """insert into partner_tree (parent,child,distance) value (%s,%s,%s)"""
                if not await cur.execute(sql, (_id, _id, 0)):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return msg[10206]
                # 新增关系树(父级)
                if 'invitation_code' in data.keys():
                    sql = """select id from partner where invitation_code=%s"""
                    if not await cur.execute(sql, data['invitation_code']):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return msg[10211]
                    _parent_id = (await cur.fetchall())[0]['id']
                    # 写入父级
                    sql = """update partner set pid=%s where id=%s"""
                    if not await cur.execute(sql, (_parent_id, _id)):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return msg[10206]
                    # 爷级
                    sql = """insert into partner_tree (parent,child,distance) value (%s,%s,%s)"""
                    parents = await self.get_results_by_condition('partner_tree', ['parent', 'distance'],
                                                                  {'child': _parent_id})
                    for i in parents:
                        if not await cur.execute(sql, (i['parent'], _id, i['distance'] + 1)):
                            await conn.rollback()
                            self.logger.warning(cur._last_executed)
                            return msg[10206]

            except Exception as e:
                self.logger.warning('注册异常={e}'.format(e=e))
                await conn.rollback()
                return msg[10206]
            else:
                await conn.commit()
                return msg[10205]


# 重置
async def forget(self, data):
    if await self.is_null(data, ['cellphone', 'vercode', 'password']):
        return msg[10100]
    cellphone = escape_string(data.get('cellphone', None).strip())
    vercode = escape_string(data.get('vercode', None).strip())
    password = escape_string(data.get('password', None).strip())
    # 校验验证码
    if not await self.redis.get('phonecode{cellphone}_{code}'.format(cellphone=cellphone, code=vercode)):
        return msg[10208]
    # 查找账号
    if not await self.get_result_by_condition('partner', ['id'], {'cellphone': cellphone}):
        return msg[10207]
    # 生成密码
    new_hash_login = await self.password_create(password)
    if not await self.update_result('partner', {'hash_login': new_hash_login}, {'cellphone': cellphone}):
        return msg[10210]
    return msg[10209]
