import json
import tornado

from application.base import BaseHandler
from application.message import msg


# 获取
class getMember(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = []
        admin_id = self.current_user['id']
        if admin_id == 1:
            data = await self.get_results_no_condition('admin', ['id', 'account', 'name', 'role', 'ggkey', 'status',
                                                                 'parent_id', 'time_update', 'time_create'])
        else:
            role_data = await self.get_result_by_condition('admin', ['id', 'role'], {"id": admin_id})

            if role_data:
                role_id = role_data['role']
                sql = '''select a.id, a.account, a.name,a.role,a.ggkey,a.name,a.status,a.parent_id,a.time_update,a.time_create from admin a 
                         left join roles r on r.id = a.role
                        where r.id=%s or  r.parent_id=%s
                        '''
                data = await self.query(sql, *[role_id, role_id])
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)


# 添加
class addMember(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['account', 'name', 'role']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('admin', 'account', data['account']):
            return await self.json_response(msg[10008])
        data = json.loads(self.request.body)
        data['ggkey'] = await self.create_gg_key()
        data['hash_login'] = await self.password_create(data['password'])
        del data['password']
        if not await self.create_result('admin', data):
            return await self.json_response(msg[10004])
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)


# 更新
class updateMember(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        self.logger.info("收到请求，开始解析 body 数据")
        data = json.loads(self.request.body)
        self.logger.info(f"解析后的数据: {data}")

        if 'status' not in data and await self.is_null(data, ['id', 'account', 'name', 'role']):
            self.logger.warning("缺少 status，且 id、account、name、role 为空，返回错误")
            return await self.json_response(data=msg[10005])

        if 'password' in data:
            self.logger.info("检测到 password 字段，进行密码哈希转换")
            data['hash_login'] = await self.password_create(data['password'])
            del data['password']
            self.logger.info("密码转换完成，原始 password 已删除")

        self.logger.info(f"准备更新数据: {data}")
        if not await self.update_result('admin', data, {'id': data['id']}):
            self.logger.error("更新数据库失败")
            return await self.json_response(msg[10005])

        result = dict(code=20000, msg='更新成功')
        self.logger.info("更新成功，返回结果")
        return await self.json_response(result)

# 删除
class deleteMember(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('admin', {'id': data['id']}):
            return await self.json_response(msg[10006])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)


# 重置谷歌
class resetGgkey(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(msg[10007])
        ggkey = await self.create_gg_key()
        if not await self.update_result('admin', {'ggkey': ggkey}, {'id': data['id']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='重置成功')
        return await self.json_response(result)
