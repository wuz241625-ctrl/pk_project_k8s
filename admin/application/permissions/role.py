import json
import tornado

from application.message import msg
from application.base import BaseHandler


# 获取权限列表
class getPermissions(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_by_condition('permissions', ['id', 'pid', 'name'], {"status": 1})
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)

# 获取当前用户权限列表
class getCurrentUserRolePermissions(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = []
        # 查询当前用户的角色
        admin_id = self.current_user['id']
        if admin_id == 1:
            data = await self.get_results_by_condition('permissions', ['id', 'pid', 'name'], {"status": 1})
        else :
            role_data = await self.get_result_by_condition('admin', ['id', 'role'], {"id": admin_id})

            if role_data:
                role_id = role_data['role']
                sql = '''select p.id, p.pid, p.name from permissions p 
                         left join roles r on FIND_IN_SET(p.id, r.permissions) > 0 
                        where r.id=%s and p.status=1
                        '''
                data = await self.query(sql, *[role_id])
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)


# 获取
class getRole(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_no_condition('roles', ['id','parent_id', 'key_name', 'name', 'permissions', 'description', 'encryption'])
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)

# 获取当前用户的角色
class getCurrentUserRole(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        # 查询当前用户的角色
        admin_id = self.current_user['id']
        data = []
        if admin_id == 1:
            data = await self.get_results_no_condition('roles', ['id','parent_id', 'key_name', 'name', 'permissions', 'description','encryption'])
        else :
            role_data = await self.get_result_by_condition('admin', ['id', 'role'], {"id": admin_id})

            if role_data:
                role_id = role_data['role']
                sql = 'select id, parent_id, key_name, name, permissions, description, encryption from roles where id=%s or parent_id=%s'
                data = await self.query(sql, *[role_id, role_id])
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)


# 添加
class addRole(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['key_name', 'name', 'permissions', 'description']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('roles', 'name', data['name']):
            return await self.json_response(msg[10008])
        if not await self.create_result('roles', data):
            return await self.json_response(msg[10004])
        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)


# 更新
class updateRole(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        self.logger.info("收到更新角色请求，开始解析 body 数据")
        data = json.loads(self.request.body)
        self.logger.info(f"解析后的数据: {data}")

        # 检查必要字段是否为空
        if await self.is_null(data, ['id', 'key_name', 'name', 'permissions', 'description']):
            self.logger.warning("缺少必要字段，返回错误")
            return await self.json_response(data=msg[10005])

        # 查询当前用户的角色
        self.logger.info(f"查询角色信息，id: {data['id']}")
        role_data = await self.get_result_by_condition('roles', ['id'], {"id": data['id']})
        
        if not role_data:
            self.logger.warning(f"未找到 id 为 {data['id']} 的角色，返回错误")
            return await self.json_response(msg[10007])

        self.logger.info(f"查询到的角色数据: {role_data}")

        # 检查父角色 ID 是否与自身 ID 相同（且角色 ID 不是 1）
        if role_data['id'] == data['parent_id'] and role_data['id'] != 1:
            self.logger.warning(f"角色 ID {role_data['id']} 不能设置自己为父级角色，返回错误")
            return await self.json_response(msg[10211])

        # 执行更新操作
        self.logger.info(f"尝试更新角色 id {data['id']} 的数据")
        if not await self.update_result('roles', data, {'id': data['id']}):
            self.logger.error(f"更新角色 id {data['id']} 失败")
            return await self.json_response(msg[10005])

        # 更新成功
        result = dict(code=20000, msg='更新成功')
        self.logger.info(f"角色 id {data['id']} 更新成功")
        return await self.json_response(result)


# 删除
class deleteRole(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']) or not await self.delete_result('roles', {'id': data['id']}):
            return await self.json_response(msg[10007])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)
