import decimal
import json
import secrets
import string
import time
import uuid
from datetime import datetime, timedelta
from aiomysql import DictCursor

import tornado

from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg
import os
import csv
import re
import pandas as pd
import math
import bcrypt

from application.system import operationLog


def payment_bank_type(payment_row):
    return str((payment_row or {}).get('bank_type_id') or (payment_row or {}).get('bank_type') or '')


def is_easypaisa_payment(payment_row):
    return payment_bank_type(payment_row) == '97'


def is_jazzcash_payment(payment_row):
    return payment_bank_type(payment_row) == '98'


def is_mysql_final_state_payment(payment_row):
    return payment_bank_type(payment_row) in {'97', '98'}


def _as_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def payment_wallet_status_select_key(table):
    return 'a.wallet_status' if table == 'payment' else '0 AS wallet_status'


def payment_business_status_select_keys(table):
    if table == 'payment':
        return ['a.collection_status', 'a.payout_status']
    return ['0 AS collection_status', '0 AS payout_status']


def easypaisa_reset_account_fields_sql():
    return (
        "update payment set account_accno=NULL, account_iban=NULL, account_entire=NULL, "
        "wallet_status=0, collection_status=0, payout_status=0 where id=%s"
    )


def easypaisa_business_status_from_config(wallet_status, status, certified, manual_status):
    business_enabled = (
        _as_int(wallet_status) == 1
        and _as_int(status) == 1
        and _as_int(certified) == 1
    )
    return {
        'collection_status': 1 if business_enabled and _as_int(manual_status) == 0 else 0,
        'payout_status': 1 if business_enabled else 0,
    }


def monitor_status_update_fields(payment_row, monitor_status):
    return {}


def batch_disable_payment_update_sql(payment_count):
    return """update payment set certified=0,status=0,collection_status=0,payout_status=0 where id in ({ids})""".format(
        ids=','.join(['%s'] * payment_count)
    )


def wallet_job_hash_key(bank_name):
    return f"hash_{bank_name}"


def wallet_job_set_key(bank_name):
    return f"set_{bank_name}"


async def reset_easypaisa_redis_state(redis_client, payment_id, channels=None):
    payment_id = str(payment_id)
    delete_keys = [
        f"pre_login_easypaisa_{payment_id}",
        f"login_on_easypaisa_{payment_id}",
    ]
    deleted_keys = await redis_client.delete(*delete_keys)
    removed_job_hash = await redis_client.hdel("hash_easypaisa", payment_id)
    removed_job_set = await redis_client.zrem("set_easypaisa", payment_id)

    return {
        "deleted_keys": deleted_keys,
        "removed_job_hash": removed_job_hash,
        "removed_job_set": removed_job_set,
    }


async def reset_wallet_job_queue(redis_client, bank_name, payment_id):
    payment_id = str(payment_id)
    delete_keys = [
        f"pre_login_{bank_name}_{payment_id}",
        f"login_on_{bank_name}_{payment_id}",
        f"login_off_{bank_name}_{payment_id}",
    ]
    deleted_keys = await redis_client.delete(*delete_keys)
    removed_job_hash = await redis_client.hdel(wallet_job_hash_key(bank_name), payment_id)
    removed_job_set = await redis_client.zrem(wallet_job_set_key(bank_name), payment_id)
    return {
        "deleted_keys": deleted_keys,
        "removed_job_hash": removed_job_hash,
        "removed_job_set": removed_job_set,
    }


def apply_payment_wallet_status_fields(payment_row):
    if not is_mysql_final_state_payment(payment_row):
        return payment_row

    wallet_status = _as_int(payment_row.get('wallet_status'))
    collection_status = _as_int(payment_row.get('collection_status'))
    payout_status = _as_int(payment_row.get('payout_status'))

    payment_row['online_status'] = 1 if wallet_status == 1 else 0
    payment_row['online_df'] = 1 if payout_status == 1 else 0
    payment_row['online_ds'] = 1 if collection_status == 1 else 0
    return payment_row


def apply_wallet_final_status_fields(payment_row):
    return apply_payment_wallet_status_fields(payment_row)


# 增加
class addPartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['cellphone', 'name']):
            return await self.json_response(data=msg[10004])
        if await self.is_exits('partner', 'cellphone', data['cellphone']):
            return await self.json_response(msg[10008])
        # 默认密码
        password_hash = await self.password_create('123456')
        data['hash_login'] = password_hash
        data['hash_trade'] = password_hash
        data['certified'] = 1
        if 'ds_min' in data.keys() and 'ds_max' in data.keys():
            dsMin = Decimal(0) if data['ds_min'] == '' else Decimal(data['ds_min'])
            dsMax = Decimal(0) if data['ds_max'] == '' else Decimal(data['ds_max'])
            if dsMin < Decimal(0):
                return await self.json_response(msg[10038])
            if dsMax < Decimal(0):
                return await self.json_response(msg[10039])
            if (dsMin != 0 or dsMax != 0) and dsMin > dsMax:
                return await self.json_response(msg[10040])
        identifier = await self.acquire_lock('migrate_partner', 10, 60)
        if not identifier:
            return await self.json_response(data=msg[10217])
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 生成邀请码
                    sql = """select id from partner where invitation_code=%s"""
                    while True:
                        invitation_code = ''.join(
                            secrets.choice(string.ascii_letters + string.digits) for _ in range(8))
                        if not await cur.execute(sql, invitation_code):
                            break
                    pid = None
                    if 'pid' in data.keys():
                        pid = data['pid'].strip()
                        if data['pid'].strip() == '':
                            data['pid'] = None
                    data['invitation_code'] = invitation_code
                    # 新增码商
                    k, p, v = await self.dict_to_kv(data)
                    sql = """ insert into partner ({keys}) values ({vals})""".format(keys=k, vals=p)
                    if not await cur.execute(sql, (*v,)):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return await self.json_response(data=msg[10004])
                    # 查询ID
                    sql = """select id from partner where cellphone = %s"""
                    if not await cur.execute(sql, data['cellphone']):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return await self.json_response(data=msg[10004])
                    partner_id = (await cur.fetchall())[0]['id']
                    # 新增关系树
                    sql = """insert into partner_tree (parent,child,distance) values (%s,%s,%s)"""
                    if not await cur.execute(sql, (partner_id, partner_id, 0)):
                        await conn.rollback()
                        self.logger.warning(cur._last_executed)
                        return await self.json_response(data=msg[10004])

                    # 新增关系树(父级)
                    if pid:

                        sql = """select id from partner where id=%s"""

                        if not await cur.execute(sql, pid):
                            await conn.rollback()
                            self.logger.warning(cur._last_executed)
                            return await self.json_response(data=msg[10211])
                        _parent_id = (await cur.fetchall())[0]['id']
                        # 爷级
                        sql = """insert into partner_tree (parent,child,distance) value (%s,%s,%s)"""
                        parents = await self.get_results_by_condition('partner_tree', ['parent', 'distance'],{'child': _parent_id})
                        for i in parents:
                            if not await cur.execute(sql, (i['parent'], partner_id, i['distance'] + 1)):
                                await conn.rollback()
                                self.logger.warning(cur._last_executed)
                                return await self.json_response(data=msg[10206])
                except Exception as e:
                    await conn.rollback()
                    self.logger.exception(e)
                    return await self.json_response(data=msg[10004])
                else:
                    await conn.commit()
                finally:
                    # 无论中间代码是否出错，最后要确保释放锁
                    await self.release_lock('migrate_partner', identifier)
        result = dict(code=20000, msg='新增成功')
        return await self.json_response(result)

# 获取
class getPartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        return await self.get_partner_page(data)

    async def get_partner_page(self, data):
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        betweens = []
        if between:
            between['key'] = f'a.{between["key"]}'
            betweens.append(between)

        tg_partners_ids = ''
        if str(self.current_user['role_id']) == '19':
            tg_partners_ids = await self.get_partners_by_parent_id(self.current_user['parent_id'])

        online_ds_partner = []
        online_df_partner = []
        online_sql_part = ''
        online_ids = []
        online = condition.pop('online', None)
        if online in [0,1,2]:
            time_accept = condition.pop('time_accept', None)
            if time_accept and len(time_accept):
                ordersBetween = {'key': 'time_accept', 'start': time_accept[0], 'end':  time_accept[1] }
            else:
                ordersBetween = {'key': 'time_accept', 'start': datetime.now() - timedelta(hours=2), 'end': datetime.now()}
            bt_key, bt_start, bt_end = await self.dict_to_between(ordersBetween)

            if online in [0,1]:
                if str(self.current_user['role_id']) == '19':
                    sql = """ SELECT partner_id FROM orders_ds where partner_id in ({partner_ids}) and status >0 and {bt_key} GROUP BY partner_id""".format(
                        partner_ids=tg_partners_ids, bt_key=bt_key)
                else:
                    sql = """ SELECT partner_id FROM orders_ds where partner_id > 0 and status >0 and {bt_key} GROUP BY partner_id""".format(bt_key=bt_key)

                orders_ds = await self.query(sql,bt_start, bt_end)
            # 使用列表解析获取orders_ds中"partner_id"的值
                online_ds_partner = [d["partner_id"] for d in orders_ds if "partner_id" in d]

            if online in [0, 2]:
                if str(self.current_user['role_id']) == '19':
                    sql = """ SELECT partner_id FROM orders_df where partner_id in ({partner_ids}) and status >0 and {bt_key} GROUP BY partner_id""".format(
                        partner_ids=tg_partners_ids, bt_key=bt_key)
                else:
                    sql = """ SELECT partner_id FROM orders_df where partner_id > 0 and status >0 and {bt_key} GROUP BY partner_id""".format(bt_key=bt_key)
                orders_df = await self.query(sql,bt_start, bt_end)
                # 使用列表解析获取orders_df中"partner_id"的值
                online_df_partner = [d["partner_id"] for d in orders_df if "partner_id" in d]
            # 转换列表为集合并计算他们的并集
            # 转换返回的集合为列表
            online_ids = list(set(online_ds_partner).union(online_df_partner))
            # 获取在线码商
            if online_ids and len(online_ids):
                online_sql_part = ' a.id in ({online_ids})'.format(online_ids=','.join(['%s'] * len(online_ids)))
            else: # 没有在线数据直接返回空
                result = dict(code=20000, data=[], total=0, new_partner=0,online_ds_partner=len(online_ds_partner), online_df_partner=len(online_df_partner),online_partner=len(online_ids), msg='获取成功')
                return await self.json_response(result)

        # 用户输入的值可能是类似 "500-1000", "1000-2000" 这样的格式
        amount_range_new = condition.pop('amount_range_new', None)
        if amount_range_new:
            amount_range_new = amount_range_new.strip().split("-")
            if len(amount_range_new) == 2:
                lower_limit = amount_range_new[0].strip()
                upper_limit = amount_range_new[1].strip()
                betweens.append({ "key": "a.balance", "start": lower_limit, "end": upper_limit })
        query_map = {}
        left_join_on = ''
        if str(self.current_user.get('role_id')) == '19':
            query_map[f'b.parent'] = self.current_user.get('parent_id')

        top_partner_id = condition.pop('top_partner_id', None)
        if top_partner_id:
            left_join_on += f'b.child=a.id'
            query_map[f'b.parent'] = top_partner_id
        else:
            left_join_on += 'b.id=(SELECT id FROM partner_tree WHERE child=a.id ORDER BY distance DESC LIMIT 1)'

        table = f"partner a LEFT JOIN partner_tree b ON {left_join_on}"
        order_by = 'DESC'
        order_field = 'a.id'
        if data.get("sort") and data.get("order_field"):
            # 如果 `sort` 和 `order_field` 都有值，则传递它们
            order_by = data["sort"]
            order_field = f'a.{data["order_field"]}'
        keys = ['a.id', 'a.cellphone', 'a.name', 'a.balance', 'a.balance_frozen', 'a.balance_deposit', 'a.vip', 'a.pid',
                'a.certified', 'a.status', 'a.time_create', 'a.type', 'a.ds_min', 'a.ds_max', 'a.invitation_code',
                'a.banned', 'b.parent AS top_partner_id']
        for k in condition.keys():
            query_map[f'a.{k}'] = condition.get(k)
        data_r, total = await self.get_page(
            table, keys, None, query_map, betweens,
            data["size"], data["page"],
            order_by, order_field,  # 传递排序参数
            other_str='', other_value=[],
            online_str=online_sql_part, online_value=online_ids
        )

        # 查询角色的所有权限name
        role_permissions_sql = f"select name from permissions where status = 1 and id in ({self.current_user['permissions']})"
        role_permission_names_json = await self.query(role_permissions_sql)
        # 字典对象 转 集合
        role_permission_names = set(value for dictionary in role_permission_names_json for value in dictionary.values())
        # 集合中匹配目标，只有管理员才能看
        if ("禁止查看码商手机号" in role_permission_names):
            for i in range(len(data_r)):
                data_r[i]['cellphone'] = '******'
        if str(self.current_user['role_id']) == '19':
            sql_count = """select count(id) as count from partner where id in ({partner_ids}) and time_create > curdate()""".format(partner_ids=tg_partners_ids)
        else:
            sql_count = """select count(id) as count from partner where time_create > curdate()"""

        new_partner = await self.query(sql_count)
        new_partner = new_partner[0]['count'] if new_partner else 0

        if 0 == data["size"]:
            log = operationLog.OperationLog(self.current_user['id'], '码商列表', operationLog.EventType.DOWNLOAD)
            log.event_result = operationLog.EventResult.SUCCESS
            log.event_desc = '码商列表数据导出'
            log.request_path = self.request.path
            log.event_content = json.dumps(data)
            log.user_ip = self.request.remote_ip
            log.utype = operationLog.UserType.ADMIN
            await self.create_result(operationLog.TABLE, operationLog.class_to_json(log))

        result = dict(code=20000, data=data_r, total=total, new_partner=new_partner, online_ds_partner=len(online_ds_partner), online_df_partner=len(online_df_partner), online_partner=len(online_ids), msg='获取成功')
        return await self.json_response(result)

class exportPartner(getPartner):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        return await self.get_partner_page(data)


# 获取顶级码商的所有下级
class getMigrate(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        partner_list = []
        _partner_list = dict()
        count = 1
        while True:
            sql = "select * from partner_tree  where distance =1"
            child_list = []
            if count == 1:
                child_list = [data['id']]
            for i in _partner_list:
                child_list.append(i['child'])
            if not child_list:
                break
            _child_ids = ','.join(map(str, child_list))
            sql += ' and parent in ({child_ids})'.format(child_ids=_child_ids)
            _partner_list = await self.query(sql)
            if _partner_list:
                for i in _partner_list:
                    partner_list.append(i)
            count += 1
        tree = self.construct_tree(partner_list)
        result = dict(code=20000, data=tree, msg='获取成功')
        return await self.json_response(result)

    def construct_tree(self,data):
        # 创建所有节点
        nodes = {item['child']: {'label': f'{item["distance"]}级 {item["child"]}'}
                 for item in data}

        # 创建父节点到子节点的映射
        parent_child_mapping = {}
        for item in data:
            if item['parent'] in nodes and item['child'] in nodes:
                nodes[item['parent']].setdefault('children', []).append(nodes[item['child']])
                parent_child_mapping[item['child']] = item['parent']

        # 使用递归函数，根据节点的祖先列表更新 'distance' 和 'label'
        def update_node(node, distance=1, ancestor_list=None):
            if ancestor_list is None:
                ancestor_list = [node['label'].split()[-1]]
            node['label'] = '{}级 {}'.format(
                distance, '-'.join(str(i) for i in ancestor_list))
            for child in node.get('children', []):
                update_node(child, distance + 1, ancestor_list + [child['label'].split()[-1]])

        # 找到根节点并更新所有节点
        root_nodes = [node for node_id, node in nodes.items() if node_id not in parent_child_mapping]
        for root_node in root_nodes:
            update_node(root_node)

        return root_nodes

# 迁移码商
class migratePartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        identifier = await self.acquire_lock('migrate_partner', 1, 60)
        if not identifier:
            return await self.json_response(data=msg[10217])
        try:
            if await self.is_null(data, ['migrationId','id']):
                return await self.json_response(data=msg[10005])
            sql = "select * from partner  where id ={id} ".format(id=data['migrationId'])
            migrationPartnerInfo = await self.query(sql)
            if not migrationPartnerInfo:
                return await self.json_response(data=msg[10216])
            sql = "select * from partner  where id ={id} ".format(id=data['id'])
            partnerInfo = await self.query(sql)
            if not partnerInfo:
                return await self.json_response(data=msg[10034])

            # 查询迁移码商所有上级
            sql = "select * from partner_tree  where child ={child} ".format(child=data['migrationId'])
            migrationPartnerTreeSuperiorInfo = await self.query(sql)

            # 查询当前码商所有下级
            sql = "select * from partner_tree  where parent ={parent} ".format(parent=data['id'])
            partnerTreeSubordinateInfo = await self.query(sql)

            # 查询当前码商所有上级
            sql = "select * from partner_tree  where child ={child}".format(child=data['id'])
            partnerTreeSuperiorInfo = await self.query(sql)

            migrationPartnerIds = []  # 当前码商所有下级
            orderPartnerIds = []  # 当前码商和下俩层码商
            #  删除当前码商其他上级的层级关系和当前码商下级的所有当前码商父节点的层级关系
            partnerTreeDelete = []
            for i in partnerTreeSuperiorInfo:
                if i['distance'] == 0:
                    continue
                partnerTreeDelete.append(i)  # 当前码商其他上级的层级关系
                for j in partnerTreeSubordinateInfo:
                    if j['distance'] == 0:
                        continue
                    delete = {'parent': i['parent'],'child': j['child']}
                    partnerTreeDelete.append(delete)  # 当前码商下级的所有当前码商父节点的层级关系
            #  迁移码商的所有父级节点也需要更新当前码商和所有下级的层级关系
            partnerTreeInsert = []
            for i in migrationPartnerTreeSuperiorInfo:
                if i['distance'] == 0:
                    continue
                for j in partnerTreeSubordinateInfo:
                    insert = {'parent': i['parent'],'child': j['child'],'distance': j['distance']+i['distance']+1}
                    partnerTreeInsert.append(insert)  # 当前码商和所有下级的层级关系

            for i in partnerTreeSubordinateInfo:
                if i['distance'] < 2:
                    orderPartnerIds.append(i['child'])
                migrationPartnerIds.append(i['child'])
                insert = {'parent': data['migrationId'], 'child': i['child'], 'distance': i['distance'] + 1}
                partnerTreeInsert.append(insert)  # 当前码商和所有下级的层级关系

            # 当前码商不允许迁移到自己的下级去
            if int(data['migrationId']) in migrationPartnerIds:
                return await self.json_response(data=msg[10215])

            # _migrationPartnerIds = ','.join(map(str, migrationPartnerIds))
            # # 查询有哪些上级
            # sql = """select * from partner_tree  where child = %s"""
            # partnerInfo = await self.query(sql, partnerInfo[0]['parent'])

            # 当前码商和下俩层码商如果一个小时内有订单不能迁移
            _orderPartnerIds = ','.join(map(str, orderPartnerIds))
            sql = "select * from orders_ds  where partner_id in( {_orderPartnerIds} ) and status in(1,2,3) and date_add(time_create, interval 1 hour) > now() limit 1".format(_orderPartnerIds=_orderPartnerIds)
            orderPartnerInfo = await self.query(sql)
            if len(orderPartnerInfo) > 0:
                return await self.json_response(data=msg[10212])


            # 更新层级关系
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 修改迁移码商上级id
                        partner_sql_update = 'update partner set pid= %s where id = %s'
                        if not await cur.execute(partner_sql_update, (data['migrationId'], data['id'])):
                            self.logger.warning('修改迁移码商上级id失败{sql}'.format(sql=self._last_sql))
                            await conn.rollback()
                            return await self.json_response(data=msg[10213])
                        # 删除原有层级码商id
                        for i in partnerTreeDelete:
                            partner_tree_sql_delete = """delete from partner_tree where parent = %s and child = %s """
                            if not await cur.execute(partner_tree_sql_delete, (i['parent'], i['child'])):
                                self.logger.warning('迁移码商{id}至{migrationId}，删除原有层级码商id失败parent{parent}child{child_id}'.format(id=data['id'], migrationId=data['migrationId'], parent=i['parent'],child_id=i['child']))
                                await conn.rollback()
                                return await self.json_response(data=msg[10213])
                        # 迁移层级码商
                        for i in partnerTreeInsert:
                            partner_tree_sql_insert = """insert into partner_tree (parent,child,distance) values (%s,%s,%s)"""
                            if not await cur.execute(partner_tree_sql_insert, (i['parent'],i['child'],i['distance'])):
                                self.logger.warning('迁移码商{id}至{migrationId}，迁移层级码商失败{child_id}'.format(id=data['id'], migrationId=data['migrationId'], child_id=i['child']))
                                await conn.rollback()
                                return await self.json_response(data=msg[10213])
                    except Exception as e:
                        await conn.rollback()
                        self.logger.exception(e)
                        return await self.json_response(data=msg[10213])
                    else:
                        await conn.commit()
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10213])
        finally:
            # 无论中间代码是否出错，最后要确保释放锁
            await self.release_lock('migrate_partner', identifier)
        self.logger.info('迁移码商{id}至{migrationId}，迁移成功'.format(id=data['id'], migrationId=data['migrationId']))
        result = dict(code=20000, msg='迁移码商{id}至{migrationId}，迁移成功'.format(id=data['id'], migrationId=data['migrationId']))
        return await self.json_response(result)


# 更新
class updatePartner(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if 'status' not in data and await self.is_null(data, ['id', 'cellphone', 'name']):
            return await self.json_response(data=msg[10005])
        if 'password' in data:
            data['hash_login'] = await self.password_create(data['password'])
            del data['password']

        if 'cellphone' in data.keys() and '*' in data['cellphone']:
            del data['cellphone']

        partner_info = """select vip,balance_deposit,balance from partner where id=%s"""
        partner_info = await self.query(partner_info, data['id'])
        if not partner_info:
            return await self.json_response(data=msg[10034])
        partner_info = partner_info[0]
        if 'ds_min' in data.keys() and 'ds_max' in data.keys():
            dsMin = Decimal(0) if data['ds_min'] == '' else Decimal(data['ds_min'])
            dsMax = Decimal(0) if data['ds_max'] == '' else Decimal(data['ds_max'])
            if dsMin < Decimal(0):
                return await self.json_response(msg[10038])
            if dsMax < Decimal(0):
                return await self.json_response(msg[10039])
            if (dsMin != 0 or dsMax != 0) and dsMin > dsMax:
                return await self.json_response(msg[10040])
        # 手动变动余额、冻结余额、押金
        if 'changeBalance' in data:
            partner_id = data['id']
            changeBalace = data['changeBalance']
            balance_type = changeBalace['changeBalanceType']
            amount = Decimal(changeBalace['changeAmount'])
            # 锁
            busy_key = 'edit_partner_balance_busy_{merchant_id}'.format(merchant_id=partner_id)
            if await self.redis.exists(busy_key):
                return await self.json_response(msg[10010])
            await self.redis.set(busy_key, '1', 10)
            # 执行变动
            if await self.change_balance_sd(amount, balance_type, 'partner', partner_id, changeBalace['remark']):
                self.logger.warning('变动码商成功:金额{amount},码商{partner_id}, 操作人{admin},data{data}'.format(amount=amount, partner_id=partner_id, admin=self.current_user['id'], data=data))
                del data['changeBalance']
            else:
                self.logger.error('变动码商失败:金额{amount},码商{partner_id}, 操作人{admin}'.format(amount=amount, partner_id=partner_id, admin=self.current_user['id']))
                return await self.json_response(msg[10012])

        if 'status' in data.keys():
            if data['status'] not in [0, 1]:
                self.logger.error('冻结/冻结码商错误，码商{id}, 操作人{admin}， status{status}'.format(id=data['id'], admin=self.current_user['id'], status=data['status']))
                return await self.json_response(msg[10007])
            # 冻结
            if data['status'] == 0:
                if not await self.update_result('partner', data, {'id': data['id']}):
                    self.logger.error('冻结码商异常，码商{id}, 操作人{admin}'.format(id=data['id'], admin=self.current_user['id']))
                    return await self.json_response(msg[10007])
                self.logger.warning('冻结码商成功，码商{id}, 操作人{admin},data{data}'.format(id=data['id'], admin=self.current_user['id'], data=data))
            # 激活
            if data['status'] == 1:
                # 激活必须检测押金是否符合等级
                sql_select_vip = """select vip,conditions,deposit_ratio from vip"""
                vips = await self.query(sql_select_vip)
                if not vips:
                    self.logger.warning('激活码商失败，vip信息不存在，码商{id}, 操作人{admin}'.format(id=data['id'], admin=self.current_user['id']))
                    return await self.json_response(msg[10007])
                # partnerBalance = 0
                # for i in vips:
                #     if i['vip'] == partner_info['vip']:
                #         # 获取去除保证金后的余额
                #         partnerBalance = await self.removeDeposit(partner_info['balance'], i['conditions'], i['deposit_ratio'])
                #         break
                #
                # if partnerBalance < 1:
                #     self.logger.warning('激活码商失败，码商押金不够，码商{id}, 操作人{admin}'.format(id=data['id'], admin=self.current_user['id']))
                #     msg[10035]['message'] += '金额：' + str(partnerBalance)
                #     return await self.json_response(msg[10035])

                if not await self.update_result('partner', data, {'id': data['id']}):
                    self.logger.error('激活码商异常，码商{id}, 操作人{admin}'.format(id=data['id'], admin=self.current_user['id']))
                    return await self.json_response(msg[10007])
                self.logger.warning('激活码商成功，码商{id}, 操作人{admin},data{data}'.format(id=data['id'], admin=self.current_user['id'], data=data))

        if 'type' in data.keys():
            # 设置外部/内部码商
            if data['type'] not in [0, 1]:
                self.logger.error('设置码商类型错误，码商{id}, 操作人{admin}， type{type}'.format(id=data['id'], admin=self.current_user['id'], type=type))
                return await self.json_response(msg[10007])
            self.logger.warning('设置码商类型成功，码商{id}, 操作人{admin}， data{data}'.format(id=data['id'], admin=self.current_user['id'], data=data))
        if 'vip' in data.keys():
            data['vip'] = data['vip'] if isinstance(data['vip'], int) else int(data['vip'])
            if data['vip'] < 1 or data['vip'] > 13:
                self.logger.error('设置码商vip等级错误，码商:{id}, 操作人:{admin}， vip:{vip}'.format(
                    id=data['id'], admin=self.current_user['id'], vip=data['vip']))
                return await self.json_response(msg[10007])

        if 'banned' in data.keys() and str(data['banned']) == '1':
            # 修改token，用户登录信息即失效
            data['authentication_token'] = str(uuid.uuid4())

        # 原始密码（可以根据需要替换成任何字符串）
        hash_login = data.get('hash_login', '')
        hash_trade = data.get('hash_trade', '')
        is_inner = data.get('type', '')

        # 判断是否为 bcrypt 哈希格式的字符串
        if is_inner == 0:
            # 处理 hash_login
            if hash_login and (not hash_login.startswith(('$2a$', '$2b$', '$2y$')) or len(hash_login) != 60):
                # 如果 hash_login 不是一个 bcrypt 哈希值，生成新的哈希
                data['hash_login'] = bcrypt.hashpw(hash_login.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                self.logger.info(f"Generated new hash_login:{hash_login}")
            else:
                self.logger.info(f"Existing hash_login:{hash_login}")

            # 处理 hash_trade
            if hash_trade and (not hash_trade.startswith(('$2a$', '$2b$', '$2y$')) or len(hash_trade) != 60):
                # 如果 hash_trade 不是一个 bcrypt 哈希值，生成新的哈希
                data['hash_trade'] = bcrypt.hashpw(hash_trade.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                self.logger.info(f"Generated new hash_trade:{hash_trade}")
            else:
                self.logger.info(f"Existing hash_trade:{hash_trade}")
        else:
            # 如果 is_inner 不是 1，移除 hash_trade
            if 'hash_login' in data:
                del data['hash_login']
            if 'hash_trade' in data:
                del data['hash_trade']

        await self.update_result('partner', data, {'id': data['id']})
        result = dict(code=20000, msg='修改成功')
        return await self.json_response(result)


# 码商排序
class getPartnerRank(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        userId = self.current_user['id']
        getPartnerRankUserId = 'getPartnerRank_{userId}'.format(userId=userId)
        if await self.redis.get(getPartnerRankUserId):
            return await self.json_response(data=msg[10041])
        await self.redis.set(getPartnerRankUserId, 1, 30)
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if not between:
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        sql = """select p.id,p.cellphone,p.name,p.balance,count(o.id) as count,sum(if(o.amount>0,o.amount,0)) as amount,
                count(if(o.status>2,1,null)) as success_count,sum(if(o.status>2,o.amount,0)) as success_amount,
                cast(count(if(o.status>2,1,null))/if(count(o.id)=0,1,count(o.id)) * 100 as decimal(14,0)) as rate
                from partner p left join orders_ds o on o.partner_id=p.id and o.time_create between %s and %s"""
        bt_key, bt_start, bt_end = await self.dict_to_between(between)
        values = [bt_start, bt_end]
        if condition and condition['channel_code']:
            sql += ' and o.channel_code=%s'
            values += [condition['channel_code']]
        sql += ' group by p.id'
        if data['order_field']:
            sql += ' order by {order_field} '.format(order_field=data['order_field'])
            if data['sort']:
                sql += data['sort']
        sql += ' limit %s offset %s'.format()
        values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)
        total = await self.get_result_no_condition('partner', ['count(id)'])
        result = dict(code=20000, data=data_r, total=total['count(id)'], msg='获取成功')
        return await self.json_response(result)

# 获取
class getPayment(BaseHandler):
    async def _mysql_final_state_ids_for_table(self, table):
        rows = await self.query(f"select id from {table} where bank_type in (97, 98) or bank_type_id in (97, 98)")
        return {str(row["id"]) for row in rows or []}

    async def _mysql_final_state_status_ids(self, table, kind):
        if table != 'payment':
            return set()
        formula = (
            "collection_status = 1"
            if kind == "ds"
            else "payout_status = 1"
        )
        rows = await self.query(
            f"""
            select id
            from payment
            where (bank_type in (97, 98) or bank_type_id in (97, 98))
              and {formula}
            """
        )
        return {str(row["id"]) for row in rows or []}

    @staticmethod
    def _normalize_redis_members(values):
        normalized = set()
        for value in values:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            normalized.add(str(value))
        return normalized

    async def _merged_online_ids(self, table, runtime_kind):
        return await self._mysql_final_state_status_ids(table, runtime_kind)

    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        data_r = []
        total = 0

        table = 'payment_d' if data['is_del'] else 'payment'
        keys = ['a.id', 'a.partner_id', 'b.status AS partner_status','b.type AS type', 'a.bank_type', 'a.upi', 'a.amount_top', 'a.sys_balance', 'a.balance', 'a.account', 'a.name',
                'a.ifsc', 'a.account_type', 'a.gmail', 'a.gmail_pw', 'a.time_create', 'a.certified', 'a.status', 'a.manual_status', 'a.priority_collection', 'a.channel', 'a.net_id', 'a.net_trade_pw', 'a.net_pw', 'a.phone', 'a.bank_type_id', 'a.account_accno', payment_wallet_status_select_key(table)] + payment_business_status_select_keys(table)
        sql_part = ''
        values = []

        if condition:
            for k in list(condition.keys()):
                if not condition[k] and condition[k] != 0:
                    condition.pop(k)
        if condition:
            sql_part += ' where '
            # 在线离线的筛选
            if not await self.is_null(condition, ['collect']):
                collect = condition['collect']
                del condition['collect']
                online_ids = await self._merged_online_ids(table, "ds")
                ids = await self.list_keys(online_ids) if online_ids else 0
                if not ids:
                    ids = 0
                sql_part += 'id {collect} in ({ids}) {condition} '.format(collect='' if collect else 'not', ids=ids,
                                                                          condition='and' if condition else '')
            if not await self.is_null(condition, ['pay']):
                pay = condition['pay']
                del condition['pay']
                online_ids = await self._merged_online_ids(table, "df")
                ids = await self.list_keys(online_ids) if online_ids else 0
                if not ids:
                    ids = 0
                sql_part += 'id {pay} in ({ids}) {condition} '.format(pay='' if pay else 'not', ids=ids,
                                                                      condition='and' if condition else '')
        if condition:
            where_key, where_val = await self.dict_to_and(condition)
            sql_part += ' {keys} '.format(keys=where_key)
            values += where_val

        # 如果是推广账号，则过滤出推广账号下的码商订单
        if str(self.current_user['role_id']) == '19':
            tg_partners_ids = await self.get_partners_by_parent_id(self.current_user['parent_id'])
            if sql_part == '':
                sql_part = ' where partner_id in ({})'.format(tg_partners_ids)
            else:
                sql_part += ' and partner_id in ({})'.format(tg_partners_ids)

        # 获取所有数据总数
        sql = "select count(id) from {table} ".format(table=table)
        sql += sql_part
        t = await self.query(sql, *values)
        if t:
            t = t[0]['count(id)']
        else:
            t = 0
        # 获取分页数据
        sql = "select {keys} from {table} a LEFT JOIN partner b ON a.partner_id = b.id where a.id in (select id from {table} ".format(
            keys=await self.list_keys(keys),
            table=table)

        if "order_field" in data.keys():
            order_by = ') order by {order_field} {sort} '.format(order_field=data['order_field'], sort=data['sort'])
        else:
            order_by =")"
        sql += sql_part + order_by
        limit = data['size']
        offset = data['page']
        if limit and offset > -1:
            sql += 'limit %s offset %s'
            values += [limit, (offset - 1) * limit]
        r = await self.query(sql, *values)
        if r:
            data_r = r
            total = t
        online_ds_ids = await self._merged_online_ids(table, "ds")
        online_df_ids = await self._merged_online_ids(table, "df")
        count_r = {
            'online_ds': len(online_ds_ids),
            'online_df': len(online_df_ids)
        }
        login_on = dict({
            97:'easypaisa',
            98:'jazzcash'
        })

        # 查询角色的所有权限name
        role_permissions_sql = f"select name from permissions where status = 1 and id in ({self.current_user['permissions']})"
        role_permission_names_json = await self.query(role_permissions_sql)
        # 字典对象 转 集合
        role_permission_names = set(value for dictionary in role_permission_names_json for value in dictionary.values())

        self.application.logger.info(f"Role: {self.current_user['role']}, role_permission_names{role_permission_names}")

        first_logged = False  # 标记是否已打印第一条有效记录
        for i in data_r:
            upi = i.get("upi", "") or ""  # 确保 upi 不是 None
            # 集合中匹配目标
            if not ("upi查看权限" in role_permission_names):
                self.application.logger.info(f"Role: {self.current_user['role']}, 没有 upi查看权限")
                # 计算需要隐藏的前6位
                visible_length = min(6, len(upi))
                # 用星号替换前6位，后面部分保持不变
                i["upi"] = "*" * visible_length + upi[visible_length:]

                # 只打印第一条 upi 不为空的记录
                if not first_logged and i["upi"]:
                    self.application.logger.info(f"Role: {self.current_user['role']}, First record: {i}")
                    first_logged = True  # 设置标记，防止后续记录再被打印
            else:
                self.application.logger.info(f"Role: {self.current_user['role']}, 有 upi查看权限")
            # i['bank_type'] = int(i['bank_type'])
            sql = """select count(if(status>2,id,null)) as count_s, count(if(status<0,id,null)) as count_f
                        from orders_ds where payment_id=%s and time_create > curdate() """
            order = (await self.query(sql, i['id']))[0]
            i['rate'] = int(
                order['count_s'] / (order['count_s'] + order['count_f']) * 100 if order['count_s'] > 0 else 0)
            i['online_ds'] = 0
            i['online_df'] = 0
            # 采集状态
            i['online_status'] = 0
            bank_type_id = 97 if is_easypaisa_payment(i) else int(i.get('bank_type_id') or i['bank_type'])
            if bank_type_id in login_on.keys():
                if is_mysql_final_state_payment(i):
                    apply_payment_wallet_status_fields(i)
                elif await self.redis.get('login_on_{bank}_{id}'.format(bank=login_on[bank_type_id], id=i['id'])):
                    i['online_status'] = 1

            # 手机在线状态
            i['online_mobile_status'] = 0
            # 获取当前的 monitor_status 值并将其赋值给 i['monitor_status']
            i['monitor_status'] = 1
            ttl = await self.redis.ttl(f'monitor_payment_online_{i["id"]}')
            # print('ttl===',ttl)
            # 检查 key 是否不存在或已过期
            if ttl <= 0:
                i['monitor_status'] = 0
            
            # 🔥 查询 EasyPaisa 限额数据（新增）
            i['easypaisa_limits'] = None
            try:
                limits_json = await self.redis.hget('easypaisa_limits_hash', str(i['id']))
                if limits_json:
                    if isinstance(limits_json, bytes):
                        limits_json = limits_json.decode('utf-8')
                    i['easypaisa_limits'] = json.loads(limits_json)
                    self.logger.error(f"[限额查询] 账号 {i['id']} 获取到 EasyPaisa 限额数据: {i['easypaisa_limits']}")
            except Exception as e:
                self.logger.warning(f"获取账号 {i['id']} EasyPaisa 限额数据失败: {e}")
                # 失败时保持 None，不影响返回
            
            # 🔥 查询 JazzCash 限额数据（新增）
            i['jazzcash_limits'] = None
            try:
                limits_json = await self.redis.hget('jazzcash_limits_hash', str(i['id']))
                if limits_json:
                    if isinstance(limits_json, bytes):
                        limits_json = limits_json.decode('utf-8')
                    i['jazzcash_limits'] = json.loads(limits_json)
                    self.logger.info(f"[限额查询] 账号 {i['id']} 获取到 JazzCash 限额数据")
            except Exception as e:
                self.logger.warning(f"获取账号 {i['id']} JazzCash 限额数据失败: {e}")
                # 失败时保持 None，不影响返回
            
            # 🔥 查询实时余额数据 - 只使用Redis余额，无数据时设为None
            # 策略：先查 EasyPaisa，再查 JazzCash，哪个有数据就用哪个
            try:
                payment_id = i['id']
                redis_balance = None
                
                # 先尝试从 EasyPaisa Redis 获取余额
                easypaisa_balance = await self.redis.zscore('easypaisa_balance_sorted', payment_id)
                if easypaisa_balance is not None:
                    redis_balance = easypaisa_balance
                    self.logger.info(f"[余额查询] 账号 {payment_id} 从EasyPaisa Redis获取余额: {redis_balance}")
                
                # 如果 EasyPaisa 没有，再尝试从 JazzCash Redis 获取余额
                if redis_balance is None:
                    jazzcash_balance = await self.redis.zscore('jazzcash_balance_sorted', payment_id)
                    if jazzcash_balance is not None:
                        redis_balance = jazzcash_balance
                        self.logger.info(f"[余额查询] 账号 {payment_id} 从JazzCash Redis获取余额: {redis_balance}")
                
                # 🔥 只使用Redis余额，无数据时设为None
                if redis_balance is not None:
                    i['balance'] = float(redis_balance)
                    i['sys_balance'] = float(redis_balance)
                else:
                    # Redis无数据，设为None（前端显示为空或"--"）
                    i['balance'] = None
                    i['sys_balance'] = None
                    self.logger.debug(f"[余额查询] 账号 {payment_id} Redis无余额数据，设置为None")
                    
            except Exception as e:
                self.logger.warning(f"获取账号 {i['id']} Redis余额失败: {e}")
                # 异常时也设为None
                i['balance'] = None
                i['sys_balance'] = None
        
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)


# 更新
class updatePaymentMonitorStatus(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id', 'monitor_status', 'channel']):
            return await self.json_response(data=msg[10004])
        payment_id = data['id']  # Assuming 'id' corresponds to the payment ID
        monitor_status = data['monitor_status']
        channel = data['channel'].split(',')

        # EasyPaisa/JazzCash 状态展示只读 MySQL 最终态
        payment_info = await self.get_result_by_condition(
            'payment',
            ['bank_type', 'bank_type_id', 'wallet_status', 'status', 'certified', 'manual_status', 'collection_status'],
            {'id': payment_id},
        )
        is_final_state_payment = is_mysql_final_state_payment(payment_info)

        if monitor_status == 1:
            # Set the Redis key with a 300 seconds expiration
            await self.redis.setex(f'monitor_payment_online_{payment_id}', 300, "active")  # Store an appropriate value
            if is_final_state_payment:
                update_fields = monitor_status_update_fields(payment_info, monitor_status)
                if update_fields:
                    await self.update_result('payment', update_fields, {'id': payment_id})

        elif monitor_status == 0:
            # Delete the key
            await self.redis.delete(f'monitor_payment_online_{payment_id}')
            if is_final_state_payment:
                update_fields = monitor_status_update_fields(payment_info, monitor_status)
                if update_fields:
                    await self.update_result('payment', update_fields, {'id': payment_id})

        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)

class syncPaymentToMerchant():
    # target_payment存储的是以,分割的payment id
    active_channel_merchants_sql = """
        select DISTINCT merchant.id, merchant.target_payment 
        from merchant inner join merchant_channel on merchant.id = merchant_channel.merchant_id 
        where merchant_channel.code = 1004 and merchant_channel.status = 1
    """

    @classmethod
    def parse_target_payments(cls, target_payments):
        return [] if (target_payments is None or target_payments.strip() == "") else target_payments.split(',')
    
    @classmethod
    async def update_merchant(cls, db, merchant_id, target_payment):
        async with db.acquire() as conn:
            async with conn.cursor() as cur:
                update_sql = """
                        UPDATE merchant
                        SET target_payment = %s
                        WHERE id = %s limit 1
                    """
                try:
                    rows_affected = await cur.execute(update_sql, (target_payment, merchant_id))
                except Exception as e:
                        await conn.rollback()
                        return (False, 0)
                else:
                    await conn.commit()
                    return (True, rows_affected)

    @classmethod
    async def query_merchants(cls, query_sql, query_params, db, logger):
        try:
            async with db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    await cur.execute(query_sql, query_params)
                    merchants = await cur.fetchall()
        except Exception as e:
            logger.warning(f"收款资料时同步到商户失败,查询商户时发生错误: {str(e)}")
            return None
        return merchants

    @classmethod
    async def update_merchants(cls, action, merchants, payment_id, db, logger):
        for merchant in merchants:
            target_payments = cls.parse_target_payments(merchant['target_payment'])
            if action == 'add':
                target_payments.append(payment_id)
            elif action == 'remove' and payment_id in target_payments:
                    target_payments.remove(payment_id)
            else:
                continue
            target_payments_joined = ','.join(sorted(set(target_payments)))
            success, _ = await cls.update_merchant(db, merchant['id'], target_payments_joined)
            if success:
                logger.info((
                    f"收款资料同步到商户成功 action: {action}, payment_id: {payment_id} "
                    f"merchant id: {merchant['id']}, target_payment: new {target_payments_joined} old: {merchant['target_payment']}"))
            else:
                logger.warning((
                    f"收款资料时同步到商户失败 action: {action}, payment_id: {payment_id} "
                    f"merchant id: {merchant['id']}, target_payment: {merchant['target_payment']}"))
    
    @classmethod
    async def sync(cls, action, payment_id, db, logger):
        """
        action: add or remove
        payment_id: payment id
        """
        payment_id = str(payment_id)
        merchants = await cls.query_merchants(cls.active_channel_merchants_sql, (), db, logger)
        if merchants is None:
            return False
        await cls.update_merchants(action, merchants, payment_id, db, logger)
        return True

# 禁用启用码
class updatePayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10007])
        old_payment = await self.get_result_by_condition(
            'payment',
            [
                'upi', 'status', 'channel', 'certified', 'manual_status',
                'wallet_status', 'collection_status', 'payout_status',
                'bank_type_id', 'bank_type', 'phone'
            ],
            {'id': data['id']},
        )
        if not old_payment:
            return await self.json_response(msg[10007])
        # 20241104 hide
        # if not await self.is_null(data, ['channel']):
            # 检测是否存在此channel
            # r = await self.get_result_by_condition('channel', ['id'], {'code': data['channel']})
            # if not r:
            #     return await self.json_response(msg[10221])
        if not await self.is_null(data, ['correction']):
            sql = """update payment set sys_balance=balance where id=%s"""
            if not await self.execute(sql, data['id']):
                return await self.json_response(msg[10007])
        else:
            upi = str(data.get('upi', '')).strip()
            is_ep_payment = (
                str(data.get('selectedBankType') or '') == '97'
                or is_easypaisa_payment(old_payment)
            )
            payment_data = {
                key: value for key, value in {
                    'bank_type': data.get('selectedBankType'),
                    'account_type': data.get('selectedAccountType'),
                    'upi': upi,
                    'ifsc': data.get('ifsc'),
                    'account': data.get('account'),
                    'name': data.get('name'),
                    'net_id': data.get('net_id'),
                    'net_pw': data.get('net_pw'),
                    'net_trade_pw': data.get('net_trade_pw'),
                    'phone': data.get('phone'),
                    'gmail': data.get('gmail'),
                    'gmail_pw': data.get('gmail_pw'),
                    'partner_id': data.get('partner_id'),
                    'bank_type_id': data.get('selectedBankType'),
                    'channel': data.get('channel'),
                    'status': data.get('status'),
                    'certified': data.get('certified'),
                    'priority_collection': data.get('priority_collection'),
                    'manual_status': data.get('manual_status'),
                    'amount_top': data.get('amount_top'),
                }.items() if value is not None and value != ''
            }
            manual_status_only_update = False
            if is_ep_payment:
                next_status = _as_int(data.get('status', old_payment.get('status')))
                next_certified = _as_int(data.get('certified', old_payment.get('certified')))
                next_manual_status = _as_int(data.get('manual_status', old_payment.get('manual_status')))
                next_wallet_status = _as_int(old_payment.get('wallet_status'))
                if 'status' in data or 'certified' in data:
                    payment_data.update(
                        easypaisa_business_status_from_config(
                            next_wallet_status,
                            next_status,
                            next_certified,
                            next_manual_status,
                        )
                    )
                if 'manual_status' in data and 'status' not in data and 'certified' not in data:
                    payment_data['collection_status'] = easypaisa_business_status_from_config(
                        next_wallet_status,
                        next_status,
                        next_certified,
                        next_manual_status,
                    )['collection_status']
                    manual_status_only_update = set(payment_data.keys()).issubset(
                        {'manual_status', 'collection_status'}
                    )

            # 验证 upi 唯一性
            if upi:      
                # 获取 upi 字段
                old_upi = old_payment.get('upi')

                # 仅当 upi 被修改时检查唯一性
                if upi != old_upi:
                    exists = await self.get_result_by_condition(
                        'payment',
                        ['id'],
                        {'upi': upi}
                    )
                    if exists:
                        return await self.json_response(msg[10227])  # "UPI 已存在"

            if manual_status_only_update:
                manual_collection_status = payment_data.get('collection_status', 0)
                sql = """
                    update payment
                    set manual_status=%s, collection_status=%s
                    where id=%s limit 1
                """
                async with self.application.db.acquire() as conn:
                    async with conn.cursor(DictCursor) as cur:
                        await cur.execute(
                            sql,
                            (next_manual_status, manual_collection_status, data['id']),
                        )
                    await conn.commit()
            elif not await self.update_result('payment', payment_data, {'id': data['id']}):
                return await self.json_response(msg[10007])
        if 'status' in data.keys():
            channels = syncPaymentToMerchant.parse_target_payments(old_payment['channel'])
            if data['status'] == 0:
                # 禁用时同步到商户
                if "1004" in channels:
                    await syncPaymentToMerchant.sync("remove", data['id'], self.application.db, self.logger)
            if data['status'] == 1:
                # 启用时同步到商户
                if "1004" in channels:
                    await syncPaymentToMerchant.sync("add", data['id'], self.application.db, self.logger)

        if 'manual_status' in data.keys():
            if data['manual_status'] == 0:
                # 人工锁解锁，去除相关key
                _key = "orders_ds_limit_{payment_id}".format(payment_id=data['id'])
                await self.redis.delete(_key)
        if 'priority_collection' in data.keys():
            if data['priority_collection'] == 1:
                # 优先派单限时2个小时，后自动返回普通派单
                _key = "priority_collection_{payment_id}".format(payment_id=data['id'])
                await self.redis.set(_key, 1, 2*60*60)
        
        payment_status = data['status'] if data.get('status') is not None else old_payment['status']
        if 'channel' in data and payment_status == 1:
            new_channels = syncPaymentToMerchant.parse_target_payments(data['channel'])
            old_channels = syncPaymentToMerchant.parse_target_payments(old_payment['channel'])
            has_1004_in_old = "1004" in old_channels
            has_1004_in_new = "1004" in new_channels
            if has_1004_in_new and not has_1004_in_old:
                # 1004 渠道被添加，同步到商户
                await syncPaymentToMerchant.sync("add", data['id'], self.application.db, self.logger)
            elif not has_1004_in_new and has_1004_in_old:
                # 1004 渠道被移除，同步到商户
                await syncPaymentToMerchant.sync("remove", data['id'], self.application.db, self.logger)
            else:
                pass

        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)
class addpayment(BaseHandler):
        @tornado.web.authenticated
        async def post(self):
            data = json.loads(self.request.body)
            if not await self.is_exits('partner', 'id', data.get('partner_id', 0)):
                return await self.json_response(msg[10034])

            #验证upi的唯一性
            upi = str(data.get('upi', '')).strip()
            if upi:
                if await self.is_exits('payment', 'upi', data.get('upi')):
                    return await self.json_response(msg[10227])

            payment_data = {
                'bank_type': data['selectedBankType'],
                'account_type': data['selectedAccountType'],
                'upi': upi,
                'ifsc': data.get('ifsc', ''),
                'account': data.get('account', ''),
                'name': data.get('name', ''),
                'net_id': data.get('net_id', 0),
                'net_pw': data.get('net_pw', ''),
                'net_trade_pw': data.get('net_trade_pw', ''),
                'phone': data.get('phone', ''),
                'gmail': data.get('gmail', ''),
                'gmail_pw': data.get('gmail_pw', ''),
                'partner_id': data.get('partner_id', 0),
                'sys_balance': 0.00,  # 使用默认值
                'balance': 0.00,      # 使用默认值
                'certified': 1,       # 使用默认值
                'status': 0,          # 使用默认值
                'manual_status': 0,   # 使用默认值
                'bank_type_id': data['selectedBankType'],
                'priority_collection': 0,  # 使用默认值
                'upi_list': None,     # 使用默认值
                'weight': 1,          # 使用默认值
                'balance_limit': 0.0000,   # 使用默认值
                'channel': data.get('channel', ''),
            }
            if not await self.create_result('payment', payment_data):
                return await self.json_response(data=msg[10004])
            result = dict(code=20000, msg='添加成功')
            return await self.json_response(result)

class getChannel(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_no_condition('channel', ['id', 'code', 'name'])
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)

# 删除
class deletePayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10006])
        condition = {'id': data['id']}
        del_data = await self.get_result_by_condition('payment', ['*'], condition)
        channels = syncPaymentToMerchant.parse_target_payments(del_data['channel'])
        if data['is_del']:  # 永久删除
            if not await self.delete_result('payment_d', condition):
                return await self.json_response(msg[10006])
        else:  # 放入已删除
            del del_data['time_create']
            if await self.create_result('payment_d', del_data):
                if not await self.delete_result('payment', condition):
                    return await self.json_response(msg[10006])
            else:
                return await self.json_response(msg[10006])
        if "1004" in channels:
            await syncPaymentToMerchant.sync("remove", data['id'], self.application.db, self.logger)
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)


class getBank_type(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = await self.get_results_no_condition('bank_type', ['id', 'name'])
        result = dict(code=20000, data=data, msg='获取成功')
        return await self.json_response(result)


# 获取
class getBank_recoed(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        # 处理 UTR 的模糊查询
        utr_value = data['serchData'].get('utr', '').strip()
        if not between and (not condition or not condition['code']):
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        other_str = None
        if str(self.current_user['role_id']) == '19':
            tg_partners_ids = await self.get_partners_by_parent_id(self.current_user['parent_id'])
            other_str = 'partner_id in ({})'.format(tg_partners_ids)
        if utr_value:
            condition = {"utr LIKE": f"%{utr_value}%"}  # 这样能支持模糊查询
            # condition = {"utr": utr_value}


        data_r, total = await self.get_result('bank_record', ['*'], None, condition, between, data['size'],
                                              data['page'], other_str=other_str)

        # 查询角色的所有权限name
        role_permissions_sql = f"select name from permissions where status = 1 and id in ({self.current_user['permissions']})"
        role_permission_names_json = await self.query(role_permissions_sql)
        # 字典对象 转 集合
        role_permission_names = set(value for dictionary in role_permission_names_json for value in dictionary.values())
        self.application.logger.info(f"Role: {self.current_user['role']}, role_permission_names{role_permission_names}")
        if not ("utr查看权限" in role_permission_names):
            self.application.logger.info(f"Role: {self.current_user['role']}, 没有 utr查看权限")
            first_logged = False  # 标记是否已打印第一条有效记录
            for record in data_r:
                utr = record.get("utr", "") or ""  # 确保 utr 不是 None
                callback = record.get("callback", 0)  # 获取 callback，默认值为 0
                if callback == 0 and isinstance(utr, str) and len(utr) > 8:
                    # 计算要隐藏的长度
                    record["utr"] = utr[:4] + "****" + utr[8:]
                    # 只打印第一条 utr 不为空的记录
                    if not first_logged and utr:
                        self.application.logger.info(f"Role: {self.current_user['role']}, First record: {record}")
                        first_logged = True  # 设置标记，防止后续记录再被打印
        else:
            self.application.logger.info(f"Role: {self.current_user['role']}, 有 utr查看权限")

        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)


class addBank_recoed(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        # 锁
        busy_key = 'add_bankrecord_{}'.format(self.current_user['id'])
        if not await self.redis.setnx(busy_key, 1):
            return await self.json_response(data=msg[10010])
        self.logger.info(f"addBank_recoed: {self.current_user['id']}")
        await self.redis.expire(busy_key, 10)
        if await self.is_null(data, ['payment_id', 'amount', 'utr']):
            return await self.json_response(data=msg[10004])
        # 通过payment_id查询码商id
        payment = await self.get_result_by_condition('payment', ['partner_id'], {'id': data['payment_id']})
        if not payment['partner_id']:
            return await self.json_response(data=msg[10004])
        data['partner_id'] = payment['partner_id']
        if len(data['utr']) < 10 or not data['utr'].isdigit():
            return await self.json_response(data=msg[10004])
        trans_id = data.get('trans_id')
        if trans_id:
            if await self.is_exits('bank_record', 'trans_id', data['trans_id']):
                return await self.json_response(data=msg[10018])
        data['admin_id'] = self.current_user['id']
        data['trade_type'] = 1 if Decimal(data['amount']) > Decimal(0) else 0
        self.logger.info(f"addBank_recoed 封装数据: {data}")
        if not await self.create_result('bank_record', data):
            return await self.json_response(data=msg[10004])
        result = dict(code=20000, msg='新增成功')
        # 代收回调
        code = await self.order_success_ds(data)
        if code:
            result = dict(code=20000, msg='新增回调成功')
        return await self.json_response(result)

    # 代收完成
    async def order_success_ds(self, data):
        # 查找订单
        sql_select_order = """select * from orders_ds where utr=%s and amount=%s and status in (-1,1,2) and 
                            date_add(time_create, interval 30 minute) > now() """
        # 获取码商
        sql_select_partner = """select partner_id,upi from payment where id=%s"""
        # 商户代理费率
        sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant 
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join 
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
        # 码商代理费率
        sql_select_rates_partner = """select rates from channel where code=%s"""
        # 更新系统余额
        sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
        # 更新订单
        sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,
                                        payment_id=%s,utr=%s,time_success=%s,status=3,upi=%s,trans_id=%s where code=%s and status in (-1,1,2) limit 1"""
        # 更新记录
        sql_update_bank_record = """update bank_record set callback=1,order_code=%s where utr=%s limit 1"""

        trans_id = data.get('trans_id')
        if trans_id:
            sql_select_order_f = sql_select_order + "  AND (CASE WHEN trans_id IS NOT NULL AND trans_id != '' THEN trans_id = %s ELSE 1=1 END) "
            _order = await self.query(
                sql_select_order_f,
                data['utr'],                      # utr
                Decimal(data['amount']),          # amount
                data['trans_id']                  # trans_id
            )
            self.logger.info(f'sql_select_order_f: {sql_select_order_f}')
        else:
            _order = await self.query(
                sql_select_order,
                data['utr'],                      # utr
                Decimal(data['amount'])           # amount
            )
            self.logger.info(f'sql_select_order: {sql_select_order}')

        self.logger.info(f'order: {_order}')
        if not _order:
            return False
        # 使用锁，5s使用自旋锁, 防止取消的同时回调
        count_circle = 0
        while True:
            busy_key = 'order_success_busy_{code}'.format(code=_order[0]['code'])
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                break
            if count_circle >= 25:
                self.logger.warning('code:{}有其他进程正在处理中'.format(_order[0]['code']))
                return await self.json_response(msg[10010])
            time.sleep(0.2)
            count_circle = count_circle + 1

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                code = None
                try:
                    # 查询订单
                    trans_id = data.get('trans_id')
                    if trans_id:
                        sql_select_order += " AND (CASE WHEN trans_id IS NOT NULL AND trans_id != '' THEN trans_id = %s ELSE 1=1 END)"
                        if not await cur.execute(sql_select_order, (data['utr'], Decimal(data['amount']), data['trans_id'])):
                            return False
                    else:
                        if not await cur.execute(sql_select_order, (data['utr'], Decimal(data['amount']))):
                            return False
                    order = (await cur.fetchall())[0]
                    self.logger.info(f'order: {order}')
                    code = order['code']
                    amount = order['amount']
                    payment_id = data['payment_id']
                    # 码商查询
                    if not await cur.execute(sql_select_partner, data['payment_id']):
                        await conn.rollback()
                        return False
                    _payment = (await cur.fetchall())[0]
                    partner_id = _payment['partner_id']
                    # 补扣码商(非自身订单、过期订单)
                    if not order['partner_id'] == partner_id or order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0):
                            return False
                    # 非自身订单并且未过期退款给旧码商
                    if not order['partner_id'] == partner_id and not order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount,
                                                         code, 0):
                            return False
                    # 增加商户余额
                    if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'],
                                                     code, 0):
                        return False
                    # 商户代理费用
                    earn_merchant = Decimal(0)
                    if order['earn_merchant'] > 0:
                        if not await cur.execute(sql_select_rates_merchant,
                                                 (order['merchant_id'], order['channel_code'])):
                            await conn.rollback()
                            return False
                        merchant_rates = (await cur.fetchall())
                        for k, v in enumerate(merchant_rates):
                            if not k == 0:
                                _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                                if _amount < 0:
                                    await conn.rollback()
                                    return False
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    return False
                                earn_merchant += _amount
                    # 增加码商佣金
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'],
                                                     code,
                                                     3):
                        return False
                    # 增加码商代理佣金
                    earn_partner = order['earn_partner_self']
                    if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                        await conn.rollback()
                        return False
                    rates = (await cur.fetchall())[0]['rates'].split(',')
                    _partner_id = partner_id
                    for i in range(len(rates)):
                        partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                        if not partner['pid']:
                            break
                        _partner_id = partner['pid']
                        _amount = amount * Decimal(rates[i])
                        if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                            return False
                        earn_partner += _amount
                    # 系统盈利
                    earn_system = order['poundage'] - earn_merchant - earn_partner
                    if earn_system < 0:
                        await conn.rollback()
                        return False
                    # 修改卡系统余额
                    if not await cur.execute(sql_update_payment, (amount, payment_id)):
                        await conn.rollback()
                        return False
                    # 修改记录
                    if not await cur.execute(sql_update_bank_record, (code, data['utr'])):
                        await conn.rollback()
                        return False
                    # 修改订单状态
                    time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if not await cur.execute(sql_update_order,
                                             (earn_merchant, earn_partner, earn_system, partner_id,
                                              payment_id, data['utr'], time_now, _payment['upi'], trans_id, code)):
                        await conn.rollback()
                        return False
                    self.logger.info('更新订单状态%s' % cur._last_executed)
                except Exception as e:
                    await conn.rollback()
                    if code:
                        self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                        await self.update_result('bank_record', {'code': code}, {'utr', data['utr']})
                    else:
                        self.logger.warning('确认码={code}无订单,异常={e}'.format(code=data['utr'], e=e))
                    return False
                else:
                    await conn.commit()
                    await self.redis.publish('order_notify', code)
                    return code

class delBank_recoed(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10004])

        results = []
        # 确保 data['id'] 是列表
        record_ids = data['id'] if isinstance(data['id'], list) else [data['id']]
        for record_id in record_ids:
            bank_record = await self.get_result_by_condition('bank_record', ['id', 'utr', 'invalid', 'trans_id'], {'id': record_id})
            if not bank_record or bank_record.get('invalid') == 1:
                results.append({'id': record_id, 'status': 'not found or already invalid'})
                continue
            update_data = {
                'utr': f"{bank_record['utr']}_{bank_record['id']}",
                'invalid': 1,
                'memo': data['memo'] if data['memo'] else '更新 UTR 和失效状态'  # 直接使用传入的 memo 参数
            }

            # 3. 处理 trans_id 逻辑
            current_trans_id = bank_record.get('trans_id')
            if current_trans_id:
                update_data['trans_id'] = f"{current_trans_id}_{bank_record['id']}"

            success = await self.update_result('bank_record', update_data, {'id': record_id, 'callback': 0})
            if success:
                results.append({'id': record_id, 'status': 'success'})
            else:
                results.append({'id': record_id, 'status': 'update failed'})

        result = dict(code=20000, msg='删除成功', results=results)
        return await self.json_response(result)

class uploadBankStatement(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        """
        上传银行对账单文件，并根据传递的参数保存文件。
        """
        try:
            files = self.request.files
            arguments = self.request.arguments

            # 校验文件和参数
            if not files or len(files) > 1 or not arguments:
                return await self.json_response(msg[10007])  # 上传文件错误

            # 检查上传的文件
            if files.get('file'):
                file_info = files['file'][0]
                original_filename = file_info.filename
                filename_without_extension = os.path.splitext(original_filename)[0].lower()
                file_extension = os.path.splitext(original_filename)[1].lower()  # 保留原始扩展名

                # 校验扩展名
                allowed_extensions = ['.csv', '.xls', '.xlsx']  # 可根据需要扩展支持的文件类型
                if file_extension not in allowed_extensions:
                    return await self.json_response(msg[10007])  # 不支持的文件类型

                # 动态生成保存路径
                code = arguments.get('code', [b''])[0].decode('utf-8')  # 获取参数中的 code
                sanitized_code = code.replace(' ', '_')  # 替换空格，防止路径问题
                save_filename = f"{filename_without_extension}_{sanitized_code}".lower()
                full_path_filename = f"static/upload/bank_statement/{save_filename}{file_extension}"
                directory = os.path.dirname(full_path_filename)

                # 检查并创建目录
                if not os.path.exists(directory):
                    os.makedirs(directory)

                # 保存文件
                with open(full_path_filename, 'wb') as f:
                    f.write(file_info.body)

                # 返回成功响应
                return await self.json_response(msg[20000])  # 上传成功

            else:
                return await self.json_response(msg[10007])  # 未找到文件

        except Exception as e:
            # 异常处理并记录日志
            self.logger.exception(f"Error during file upload: {str(e)}")
            return await self.json_response(msg[10007])  # 上传失败

class handleClearBalance(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        """
        批量清空指定用户 ID 的余额（调用 change_balance，不修改其逻辑）
        """
        try:
            request_data = json.loads(self.request.body)
            user_ids = request_data.get("id", [])  # 期望格式：{"id": [51762, 51761]}

            if not user_ids or not isinstance(user_ids, list):
                return await self.json_response({"code": 400, "message": "参数错误，id 应该是列表"})

            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        await conn.begin()  # **开启事务**

                        for user_id in user_ids:
                            # **使用 Redis 锁，避免并发冲突**
                            busy_key = f"clear_balance_busy_{user_id}"
                            count_circle = 0
                            while True:
                                if await self.redis.setnx(busy_key, 1):
                                    await self.redis.expire(busy_key, 10)  
                                    break
                                if count_circle >= 25:  
                                    self.logger.warning(f"用户 {user_id} 清空余额被其他进程占用")
                                    continue
                                time.sleep(0.2)
                                count_circle += 1

                            # 查询用户余额
                            sql_select = "SELECT balance FROM partner WHERE id = %s"
                            await cur.execute(sql_select, (user_id,))
                            user = await cur.fetchone()

                            if not user:
                                self.logger.warning(f"用户 {user_id} 不存在，跳过")
                                continue  

                            balance = Decimal(user["balance"])

                            if balance <= 0:
                                self.logger.info(f"用户 {user_id} 余额已是 {balance}，无需清空")
                                continue  

                            # **使用 change_balance 清空余额**
                            success = await self.change_balance(
                                conn, cur, "partner", user_id, -balance,  
                                code="clear_balance", record_type=8, remark="清空余额"
                            )

                            if success:
                                self.logger.info(f"成功清空用户 {user_id} 余额")
                            else:
                                self.logger.error(f"清空用户 {user_id} 余额失败")
                                continue

                        await conn.commit()  # **提交事务**
                        result = dict(code=20000, msg='余额清空成功')
                        return await self.json_response(result)

                    except Exception as e:
                        await conn.rollback()  # **事务回滚**
                        self.logger.exception(f"清空余额时发生错误: {str(e)}")
                        result = dict(code=50000, msg="服务器内部错误")
                        return await self.json_response(result)

        except json.JSONDecodeError:
            result = dict(code=50000, msg="请求格式错误")
            return await self.json_response(result)
        except Exception as e:
            self.logger.exception(f"清空余额时发生未知错误: {str(e)}")
            result = dict(code=50000, msg="服务器内部错误")
            return await self.json_response(result)

class importBankRecord(BaseHandler):
    def __init__(self, *args, **kwargs):
        # 后续需要解析的方法可在此添加：
        # '银行名': '解析方法',
        self.bank_handle_map = {
            'CANARA BANK': self.extract_carana_data,
            'IDBI BANK': self.extract_idbi_data,
            'CENTRAL BANK': self.extract_central_data,
            'BOM BANK': self.extract_bom_data,
            'EQUITAS': self.extract_equitas_data,
            'INDIAN BANK': self.extract_indian_data,
            'FEDERAL BANK': self.extract_federal_data,
            'CGGB BANK': self.extract_cggb_data,
            'KVB BANK': self.extract_kvb_data,
            'KGB BANK': self.extract_kgb_data,
            'BOM PAYTM': self.extract_bompaytm_data,
            'CITY UNION BANK': self.extract_city_union_data,
            'JK BANK': self.extract_jk_bank_data,
            'KARNATAKA BANK': self.extract_karnataka_bank_data,
            'DHAN BANK': self.extract_dhan_bank_data,
            'BOB BANK': self.extract_bob_bank_data,
            'BOI BANK': self.extract_boi_bank_data,
            'TMB BANK': self.extract_tmb_bank_data,
            'PSB BANK': self.extract_psb_bank_data,
            'PAYTM 内部回调': self.extract_paytm_bank_data,
            'JANA BANK': self.extract_jana_bank_data,
            'IOB BANK': self.extract_iob_bank_data,
            'AU BANK': self.extract_au_bank_data
        }
        super().__init__(*args, **kwargs)
    @staticmethod
    async def extract_carana_data(self, uploaded_name):
        """
        最终返回内容为字典组成的列表:
        [
        {'code': '订单code1', 'debit_account': '回执账号1', 'utr': '回执utr1'},
        {'code': '订单code2', 'debit_account': '回执账号2', 'utr': '回执utr2'},
        ......
        ]
        """
        remark_field = 'Description'
        utr_field = 'Cheque No.'
        debit_field = 'Debit'
        credit_field = 'Credit'

        # 要查找的字段名
        required_fields = [remark_field, utr_field, debit_field,credit_field]
        results = []
        uploaded_name = uploaded_name.lower()
        with open("static/upload/bank_statement/{}".format(uploaded_name), mode='r', newline='', encoding='utf-8') as f:
            # 创建 CSV 阅读器
            reader = csv.reader(f)

            rows = list(reader)
            # 查找标题行
            header = None
            for i, row in enumerate(rows):
                if any(field in row for field in required_fields):
                    header = row
                    break
            if header is None:
                self.logger.error('没有找到包含所需字段的标题行,文件名:{uploaded_name}'.format(uploaded_name=uploaded_name))
                raise ValueError("没有找到包含所需字段的标题行。")

            utr_index = header.index(utr_field)
            remark_index = header.index(remark_field)
            debit_index = header.index(debit_field)
            credit_index = header.index(credit_field)

            # 匹配确认码的正则表达式
            pattern = r'/([A-Za-z0-9]{5})//'
            # 读取数据
            for row in rows[i + 1:]:  # 从标题行之后开始读取
                debit = row[debit_index].strip('="').replace(',', '')
                credit = row[credit_index].strip('="').replace(',', '')
                content = row[remark_index].strip('"')
                utr = row[utr_index].strip('="')
                # 跳过手续费记录处理
                if content == 'ATM / IMPS Transaction Charges':
                    continue

                # 跳过无utr的记录
                if utr == '':
                    continue

                if debit != '' and float(debit) > 0:
                    results.append(
                        {
                            'utr': utr,
                            'content': content,
                            'trade_type': 2,
                            'amount': -float(debit)
                        }
                    )
                else:
                    # 匹配确认码
                    valid_code = ''
                    match = re.search(pattern, content)
                    if match:
                        code = match.group(1)  # 提取匹配的代码
                        if len(code) == 5:  # 检查是否是5位字符
                            valid_code = code

                    results.append(
                        {
                            'utr': utr,
                            'content': content,
                            'trade_type': 1,
                            'amount': 0 if credit == '' else float(credit),
                            'code': valid_code
                        }
                    )
        return results

    @staticmethod
    async def extract_idbi_data(self, uploaded_name):
        """
        解析 IDBI 银行账户对账单文件 (.xls)。
        返回的内容为字典列表：
        [
            {'utr': '回执UTR', 'content': '描述内容', 'trade_type': 交易类型, 'amount': 金额, 'code': '订单代码'},
            ......
        ]
        """
        remark_field = 'Description'  # 确保字段名称是正确的
        crdr_field = 'CR/DR'
        amount_field = 'Amount (INR)'

        required_fields = [remark_field, crdr_field, amount_field]
        results = []

        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"开始解析文件：{file_path}")

        try:
            # 读取 Excel 文件，预读取数据
            df = pd.read_excel(file_path, header=None)
            self.logger.info(f"Excel 文件成功加载，前 5 行数据：\n{df.head()}")

            # 查找包含标题字段的行
            header_fields = [remark_field, amount_field]
            header_row_index = None
            for i, row in df.iterrows():
                if all(field in row.astype(str).values for field in header_fields):
                    header_row_index = i
                    self.logger.info(f"找到标题行，索引：{header_row_index}, 内容：{row.values}")
                    break

            if header_row_index is None:
                raise ValueError("无法找到包含所有标题字段的行，无法确定表头位置。")

            # 使用找到的表头索引重新读取 Excel 文件
            df = pd.read_excel(file_path, header=header_row_index)
            self.logger.info(f"文件重新加载完成，表头为：{df.columns.tolist()}")

            # 丢弃第一列空白列
            df = df.iloc[:, 1:]
            self.logger.info(f"丢弃第一列空白列后数据：\n{df.head()}")

            # 获取并匹配字段
            actual_columns = [col.strip() for col in df.columns]
            field_map = {}
            for field in required_fields:
                match = next((col for col in actual_columns if col.lower() == field.lower()), None)
                field_map[field] = match

            missing_fields = [field for field, match in field_map.items() if match is None]
            if missing_fields:
                raise ValueError(f"文件缺少必要字段：{', '.join(missing_fields)}。实际字段名：{', '.join(df.columns)}")

            remark_field = field_map[remark_field]
            crdr_field = field_map[crdr_field]
            amount_field = field_map[amount_field]
            self.logger.info(f"字段映射完成：{field_map}")

            utr_pattern = r'UPI/([0-9]+)'

            # 遍历每一行数据
            for _, row in df.iterrows():
                description = str(row[remark_field]).strip()
                description = re.sub(r'\s+', ' ', description).replace('\n', ' ').replace('\r', ' ')
                crdr = str(row[crdr_field]).strip()
                amount_str = str(row[amount_field]).strip().replace(',', '')

                if not amount_str:
                    self.logger.debug(f"跳过无金额记录，行内容：{row}")
                    continue

                amount = float(amount_str) if crdr == 'Cr.' else -float(amount_str)
                trade_type = 1 if crdr == 'Cr.' else 2

                utr_match = re.search(utr_pattern, description)
                if utr_match:
                    utr = utr_match.group(1)
                else:
                    self.logger.debug(f"跳过无 UTR 记录，描述：{description}")
                    continue

                results.append({
                    'utr': utr,
                    'content': description,
                    'trade_type': trade_type,
                    'amount': amount,
                    'code': ''  # 订单代码留空
                })

        except Exception as e:
            self.logger.error(f"解析文件时出错：{str(e)}，文件实际字段：{df.columns.tolist() if 'df' in locals() else '文件读取失败'}")
            raise ValueError(f"解析文件失败：{str(e)}")

        self.logger.info(f"解析完成，共提取 {len(results)} 条记录")
        # 反转列表
        results = results[::-1]
        return results


    @staticmethod
    async def extract_central_data(self, uploaded_name):
        """
        解析 central 银行账户对账单文件 (.xls)。
        返回的内容为字典列表：
        [
            {'utr': '回执UTR', 'content': '描述内容', 'trade_type': 交易类型, 'amount': 金额, 'code': '订单代码'},
            ......
        ]
        """
        # 定义需要的字段
        remark_field = 'Account Description'  # 描述字段
        debit_field = 'Debit'
        credit_field = 'Credit'
        amount_field = 'Amount (INR)'  # 根据实际情况调整

        required_fields = [remark_field, debit_field, credit_field]
        results = []

        # 将文件名转换为小写
        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"开始解析文件：{file_path}")

        # 检查文件是否存在
        if not os.path.exists(file_path):
            self.logger.error(f"文件不存在：{file_path}")
            raise ValueError(f"文件不存在：{file_path}")

        try:
            # 预读取 Excel 文件，查找标题行
            df_pre = pd.read_excel(file_path, header=None)
            self.logger.info(f"Excel 文件成功加载，前 5 行数据：\n{df_pre.head()}")

            # 查找包含所有标题字段的行
            header_row_index = None
            for i, row in df_pre.iterrows():
                row_values = row.astype(str).str.strip().tolist()
                if all(field in row_values for field in required_fields):
                    header_row_index = i
                    self.logger.info(f"找到标题行，索引：{header_row_index}, 内容：{row_values}")
                    break

            if header_row_index is None:
                raise ValueError("无法找到包含所有标题字段的行，无法确定表头位置。")

            # 使用找到的表头索引重新读取 Excel 文件
            df = pd.read_excel(file_path, header=header_row_index)
            self.logger.info(f"文件重新加载完成，表头为：{df.columns.tolist()}")

            # 获取并匹配字段
            actual_columns = [col.strip() for col in df.columns]
            field_map = {}
            for field in required_fields:
                match = next((col for col in actual_columns if col.lower() == field.lower()), None)
                field_map[field] = match

            missing_fields = [field for field, match in field_map.items() if match is None]
            if missing_fields:
                raise ValueError(f"文件缺少必要字段：{', '.join(missing_fields)}。实际字段名：{', '.join(df.columns)}")

            remark_field = field_map[remark_field]
            debit_field = field_map[debit_field]
            credit_field = field_map[credit_field]
            self.logger.info(f"字段映射完成：{field_map}")

            # 定义正则表达式
            utr_pattern = r'UPI/([0-9]+)'
            code_pattern = r'RRN\s+\d+/(.*?)_'  # 提取 '8VgMz' 部分
            # print("数据形状：", df.shape)
            # print("数据列名：", df.columns.tolist())

            # 遍历每一行数据
            for idx, row in df.iterrows():
                # 提取并打印描述、借方和贷方字段的值
                description = str(row[remark_field]).strip()
                debit_str = str(row[debit_field]).strip().replace(',', '')
                credit_str = str(row[credit_field]).strip().replace(',', '')

                # print(f"处理第 {idx} 行：描述='{description}', Debit='{debit_str}', Credit='{credit_str}'")

                # 确定金额
                if debit_str:
                    try:
                        amount = -float(debit_str)
                        trade_type = 2  # Debit
                        # print(f"行 {idx} 为 Debit，金额={amount}")
                    except ValueError:
                        # print(f"行 {idx} 的 Debit 金额格式错误：'{debit_str}'")
                        continue
                elif credit_str:
                    try:
                        amount = float(credit_str)
                        trade_type = 1  # Credit
                        # print(f"行 {idx} 为 Credit，金额={amount}")
                    except ValueError:
                        # print(f"行 {idx} 的 Credit 金额格式错误：'{credit_str}'")
                        continue
                else:
                    print(f"行 {idx} 无 Debit 和 Credit 金额，跳过")
                    continue

                # 假设 UTR 或类似的参考码通常出现在 `RRN` 后，类似 'RRN 495267866470'
                utr_pattern = r"RRN\s*(\d+)"  # 匹配以 'RRN' 开头，后跟一串数字

                # 在描述中查找匹配的 UTR
                utr_match = re.search(utr_pattern, description)

                # 提取 UTR 或参考码
                utr = utr_match.group(1) if utr_match else ''

                # 判断是否成功提取到 UTR
                if not utr:
                    # print(f"行 {idx} 未找到 UTR，描述='{description}'，跳过")
                    continue
                # else:
                #     print(f"行 {idx} 提取到 UTR: '{utr}'")

                # 假设订单代码（或标识符）出现在 `/` 后，第一个字母数字组合
                code_pattern = r"/([A-Za-z0-9]+)"  # 匹配斜杠后跟着的字母和数字组合

                # 在描述中查找匹配的订单代码
                code_match = re.search(code_pattern, description)

                # 假设订单代码（或标识符）出现在 `/` 后，并且在 `_` 前
                code_pattern = r"/([A-Za-z0-9]+)(?=_)"  # 匹配斜杠后，直到遇到下划线的字母数字组合

                # 在描述中查找匹配的订单代码
                code_match = re.search(code_pattern, description)

                # 提取订单代码
                order_code = code_match.group(1) if code_match else ''
                # if not order_code:
                #     print(f"行 {idx} 未找到订单代码，描述='{description}'")
                # else:
                #     print(f"行 {idx} 提取到订单代码: '{order_code}'")


                # 记录结果
                results.append({
                    'utr': utr,
                    'content': description,
                    'trade_type': trade_type,
                    'amount': amount,
                    'code': order_code  # 订单代码
                })

                # 打印记录结果
                # print(f"行 {idx} 结果: {results[-1]}")

            # 输出最终的结果
            # print("所有结果：")
            # for result in results:
            #     print(result)


            self.logger.info(f"解析完成，共提取 {len(results)} 条记录")
            return results

        except Exception as e:
            # 如果 df 已经定义，打印其列名；否则，打印文件读取失败
            df_columns = df.columns.tolist() if 'df' in locals() else '文件读取失败'
            self.logger.error(f"解析文件时出错：{str(e)}，文件实际字段：{df_columns}")
            raise ValueError(f"解析文件失败：{str(e)}")

    @staticmethod
    async def extract_bom_data(self, uploaded_name):
        """
        解析 BOM BANK 上传的回执 Excel 文件，返回字典列表：
        [
            {'debit_account': '回执账号', 'utr': '回执utr', 'account': '收款账号', 'ifsc': '银行IFSC'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()

        # 定义列名称，使用图片中的实际列名
        utr_field = 'Cheque/Reference No'
        remark_field = 'Particulars'
        debit_field = 'Debit'
        credit_field = 'Credit'
        type_field = 'Type'

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"

        # 要查找的标题字段
        header_fields = [type_field,remark_field, utr_field, debit_field,credit_field]
        # 预读取整个文件内容
        df = pd.read_excel(file_path, header=None)

        # 查找包含所有标题字段的行
        header_row_index = None
        for i, row in df.iterrows():
            # 将行内容转成字符串并检查是否包含所有标题字段
            if all(field in row.astype(str).values for field in header_fields):
                header_row_index = i
                break

        try:
            # 读取 Excel 文件，跳过标题之前的行数
            data = pd.read_excel(file_path, header=header_row_index)
            results = []
            for i, row in data.iterrows():

                _type = row.get(type_field)
                utr_raw = row.get(utr_field)
                utr = str(utr_raw).split('.')[0] if pd.notna(utr_raw) else None

                # 跳过IMPS类型数据不处理
                if _type == 'IMPS':
                    continue

                # 跳过无utr的记录
                if utr == '' or pd.isna(utr):
                    continue

                utr = str(utr)
                debit = str(row.get(debit_field)).strip().replace(",", "").replace(" ", "")
                content = str(row.get(remark_field)).strip()
                credit = str(row.get(credit_field)).strip().replace(",", "").replace(" ", "")

                if pd.isna(credit) and pd.isna(debit) :
                    continue

                if debit != '' and float(debit) > 0:
                    results.append(
                        {
                            'utr': utr,
                            'content': content,
                            'trade_type': 2,
                            'amount': -float(debit)
                        }
                    )
                else:
                    # 匹配确认码
                    pattern = re.compile(re.escape(utr) + r"([a-zA-Z0-9]{5})\b")
                    valid_code = ''
                    match = re.search(pattern, content)
                    if match:
                        code = match.group(1)  # 提取匹配的代码
                        if len(code) == 5:  # 检查是否是5位字符
                            valid_code = code

                    results.append(
                        {
                            'utr': utr,
                            'content': content,
                            'trade_type': 1,
                            'amount': 0 if credit == '' else float(credit),
                            'code': valid_code
                        }
                    )
            # ** 打印最终结果**
            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results

        except Exception as e:
            print(f"读取文件时发生错误: {e}")
            return []
        
    @staticmethod
    async def extract_equitas_data(self, uploaded_name):
        """
        解析 Equitas 银行账户对账单文件 (.xls)。
        返回的内容为字典列表：
        [
            {'utr': '回执UTR', 'content': '描述内容', 'trade_type': 交易类型, 'amount': 金额, 'code': '订单代码'},
            ...... 
        ]
        """

        # 定义需要的字段
        remark_field = 'Narration'  # 描述字段
        debit_field = 'Withdrawal INR'
        credit_field = 'Deposit INR'
        amount_field = 'ClosingBalance INR'  # 根据实际情况调整
        required_fields = [remark_field, debit_field, credit_field]

        alt_remark_field = 'Narration'  # 描述字段
        alt_debit_field = 'Withdrawal'
        alt_credit_field = 'Deposit'
        alt_required_fields = [alt_remark_field, alt_debit_field, alt_credit_field]
        results = []

        # 将文件名转换为小写
        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"开始解析文件：{file_path}")

        # 检查文件是否存在
        if not os.path.exists(file_path):
            self.logger.error(f"文件不存在：{file_path}")
            raise ValueError(f"文件不存在：{file_path}")

        try:
            # 预读取 Excel 文件，查找标题行
            df_pre = pd.read_excel(file_path, header=None, engine="openpyxl")
            self.logger.info(f"Excel 文件成功加载，前 10 行数据：\n{df_pre.head(10)}")

            # 查找包含所有标题字段的行
            header_row_index = None
            for i, row in df_pre.iterrows():
                # 标准化：去掉多余空格、换行符，并转为小写
                row_values = row.astype(str).str.strip().str.replace("\n", " ").str.lower().tolist()
                # 同样对 required_fields 执行标准化
                normalized_required_fields = [field.lower().replace("\n", " ").strip() for field in required_fields]
                # 检查是否包含所有必需字段
                if all(field in row_values for field in normalized_required_fields):
                    header_row_index = i
                    self.logger.info(f"找到标题行，索引：{header_row_index}, 内容：{row_values}")
                    break

                # 同样对 alt_required_fields 执行标准化
                normalized_alt_required_fields = [field.lower().replace("\n", " ").strip() for field in alt_required_fields]
                # 检查是否包含所有备用字段
                if all(field in row_values for field in normalized_alt_required_fields):
                    header_row_index = i
                    self.logger.info(f"使用备用字段找到标题行，索引：{header_row_index}, 内容：{row_values}")
                    remark_field = alt_remark_field
                    debit_field = alt_debit_field
                    credit_field = alt_credit_field
                    required_fields = alt_required_fields
                    break

            if header_row_index is None:
                raise ValueError("无法找到包含所有标题字段的行，无法确定表头位置。")

            if header_row_index is None:
                # 打印未匹配字段信息
                for i, row in df_pre.iterrows():
                    self.logger.error(f"文件第 {i} 行内容：{row.astype(str).str.strip().tolist()}")
                raise ValueError("无法找到包含所有标题字段的行，无法确定表头位置。")

            # 读取数据时指定表头行
            df = pd.read_excel(file_path, header=header_row_index)
            self.logger.info(f"文件重新加载完成，表头为：{df.columns.tolist()}")

            # 去除列标题中的换行符和空格
            df.columns = df.columns.str.replace('\n', ' ').str.strip()

            # 获取并匹配字段
            actual_columns = [col.strip() for col in df.columns]
            field_map = {}
            for field in required_fields:
                match = next((col for col in actual_columns if field.lower() in col.lower()), None)
                field_map[field] = match

            missing_fields = [field for field, match in field_map.items() if match is None]
            if missing_fields:
                raise ValueError(f"文件缺少必要字段：{', '.join(missing_fields)}。实际字段名：{', '.join(df.columns)}")

            # 处理数据行
            for idx, row in df.iterrows():
                code = ''
                narration = str(row[field_map[remark_field]]).strip().replace('\n', '')
                withdrawal_str = str(row[field_map[debit_field]]).strip().replace(',', '')
                deposit_str = str(row[field_map[credit_field]]).strip().replace(',', '')
                # 只会有 withdrawal_str 或 deposit_str 其中之一有效
                if withdrawal_str and withdrawal_str != '-':
                    try:
                        amount = -float(withdrawal_str)  # 提款为负金额
                        if math.isnan(amount):  # 如果金额是 NaN，使用 deposit_str
                            if deposit_str:  # 如果 deposit_str 有效
                                amount = float(deposit_str)  # 取 deposit_str 作为金额
                                # print(f"行 {idx} 为 Credit（从存款转为取款），金额={amount}")
                                trade_type = 1  # Credit (Deposit)
                            else:
                                continue  # 如果 deposit_str 也无效，跳过
                        else:
                            # print(f"行 {idx} 为 Debit，金额={amount}")
                            trade_type = 2  # Debit (Withdrawal)
                    except ValueError:
                        continue  # 如果转换失败，跳过
                elif deposit_str:
                    try:
                        amount = float(deposit_str)  # 存款为正金额
                        if math.isnan(amount):  # 如果金额是 NaN，跳过
                            continue
                        # print(f"行 {idx} 为 Credit，金额={amount}")
                        trade_type = 1  # Credit (Deposit)
                    except ValueError:
                        continue  # 如果转换失败，跳过
                else:
                    continue  # 如果两个条件都不满足，跳过

                # 提取 UTR 信息
                utr_pattern = r'UPI REF NO (\d+)'  # 根据实际格式提取 UTR
                utr_match = re.search(utr_pattern, narration)
                utr = utr_match.group(1) if utr_match else ''


                # 使用正则表达式提取目标字段
                match = re.search(r"-(?!HEAD OFFICE)([A-Z]+)-", narration)

                # 检查是否匹配成功
                if match:
                    code = match.group(1)

                if math.isnan(amount):  # 如果金额是 NaN
                    continue
                if not utr or not utr.strip():  # 如果 utr 是空值或仅包含空格，跳过
                    continue
                
                if trade_type == 2:
                    self.logger.info(f"忽略出款数据")
                    continue
                # 创建结果
                results.append({
                    'utr': utr,
                    'content': narration,
                    'trade_type': trade_type,
                    'amount': amount,
                    'code': code
                })

            self.logger.info(f"解析完成，共提取 {len(results)} 条记录")
            return results

        except Exception as e:
            self.logger.error(f"解析文件时出错：{str(e)}")
            raise ValueError(f"解析文件失败：{str(e)}")

    @staticmethod
    async def extract_indian_data(self, uploaded_name):
        """
        解析 iNDEIAN BANK 上传的回执 Excel&&Csv 文件，返回字典列表：
        [
            {'amount': '回执金额', 'utr': '回执utr', 'content': '内容',‘trade_type’：‘交易类型’},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        
        # 定义目标标题字段，全部小写（目标字段本身不含空格）
        target_fields = ["description", "debit amount", "credit amount"]
        
        file_ext = os.path.splitext(uploaded_name)[-1]
        
        try:
            # 先不指定表头读取整个文件
            if file_ext == '.csv':
                with open(file_path, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                    sample = f.read(1024)
                    f.seek(0)
                    try:
                        dialect = csv.Sniffer().sniff(sample)
                    except csv.Error:
                        dialect = csv.excel
                    df = pd.read_csv(f, header=None, delimiter=dialect.delimiter)
            elif file_ext in ['.xls', '.xlsx']:
                df = pd.read_excel(file_path, header=None)
            else:
                raise ValueError("不支持的文件格式，请上传 Excel 或 CSV 文件。")
            
            self.logger.info("初始读取的前10行：")
            self.logger.info(df.head(10))
            
            # -------------------------------
            # 动态查找包含所有目标字段的行（对单元格做 strip 和 lower 处理，去除右侧空格）
            header_row_index = None
            for i, row in df.iterrows():
                # 对当前行的每个单元格做 strip() 和 lower() 处理
                row_processed = [str(cell).strip().lower() for cell in row.values]
                # 检查当前行是否包含所有目标字段
                if all(target_field in row_processed for target_field in target_fields):
                    header_row_index = i
                    break
            
            if header_row_index is None:
                raise ValueError("文件中未找到包含所有指定标题字段的表头行。")
            
            self.logger.info(f"动态定位到的表头行索引：{header_row_index}")
            
            # -------------------------------
            # 重新读取文件，指定表头行
            if file_ext == '.csv':
                with open(file_path, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                    df = pd.read_csv(f, header=header_row_index, delimiter=dialect.delimiter)
            else:
                df = pd.read_excel(file_path, header=header_row_index)
            
            # 去除列名前后的空格
            df.columns = [str(c).strip() for c in df.columns]
            self.logger.info("重新读取后 DataFrame 的表头：", df.columns.tolist())
            
            # -------------------------------
            # 数据解析逻辑
            results = []
            # 根据实际情况调整正则（此处示例使用 UPI/xxxx 格式匹配）
            utr_pattern = r'UPI/(\d+)'
            
            for _, row in df.iterrows():
                # 获取字段值并清除左右空格
                debit_val = str(row.get("Debit Amount", "")).strip().replace(",", "").replace(" ", "")
                credit_val = str(row.get("Credit Amount", "")).strip().replace(",", "").replace(" ", "")
                content = str(row.get("Description", "")).strip()
                
                # 如果两个金额字段均为空，则跳过该行
                if (not debit_val or pd.isna(debit_val)) and (not credit_val or pd.isna(credit_val)):
                    continue
                
                # 尝试匹配 UTR
                utr_match = re.search(utr_pattern, content)
                utr = utr_match.group(1) if utr_match else ""
                if not utr:
                    continue  # 根据需要是否跳过
                
                try:
                    if debit_val.replace('.', '', 1).isdigit() and float(debit_val) > 0:
                        results.append({
                            'utr': utr,
                            'content': content,
                            'trade_type': 2,  # 2 表示支出
                            'amount': -float(debit_val)
                        })
                    elif credit_val.replace('.', '', 1).isdigit() and float(credit_val) > 0:
                        results.append({
                            'utr': utr,
                            'content': content,
                            'trade_type': 1,  # 1 表示收入
                            'amount': float(credit_val)
                        })
                except ValueError as ve:
                    self.logger.info(f"金额转换错误，跳过该行: {row}, 错误: {ve}")
                    continue
            
            self.logger.info(f"Number of results processed: {len(results)}")
            return results
        
        except Exception as e:
            self.logger.info(f"读取文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_federal_data(self, uploaded_name):
        """
        解析 Federal Bank 上传的回执 Excel 文件，返回字典列表：
        [
            {'date': '交易日期', 'amount': '回执金额', 'utr': '回执utr', 'content': '内容', 'trade_type': '交易类型'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 尝试使用的列名称规则（优先使用第一组列名，如果找不到，则使用第二组）
        date_field = 'Date'
        particulars_field = 'Particulars'
        withdrawals_field = 'Withdrawals'
        deposits_field = 'Deposits'

        # 第二组备用列名
        date_field_alt = 'Tran Date'
        particulars_field_alt = 'Particulars'
        withdrawals_field_alt = 'Withdrawal'
        deposits_field_alt = 'Deposit'

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # 要查找的标题字段
        header_fields = [date_field, particulars_field, withdrawals_field, deposits_field]
        header_fields_alt = [date_field_alt, particulars_field_alt, withdrawals_field_alt, deposits_field_alt]

        # 预读取整个文件内容
        try:
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.info(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # 查找包含所有标题字段的行
        header_row_index = None
        for i, row in df.iterrows():
            # 将行内容转成字符串并检查是否包含所有标题字段
            if all(field in row.astype(str).values for field in header_fields):
                header_row_index = i
                break

        # 如果没有找到原始列名，则尝试备用列名
        if header_row_index is None:
            for i, row in df.iterrows():
                if all(field in row.astype(str).values for field in header_fields_alt):
                    header_row_index = i
                    break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 文件，跳过标题之前的行数
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info("表头字段：", list(data.columns))

            results = []

            for i, row in data.iterrows():
                # 提取各列数据
                date = str(row.get(date_field, row.get(date_field_alt))).strip()
                particulars = str(row.get(particulars_field, row.get(particulars_field_alt))).strip()
                withdrawals = str(row.get(withdrawals_field, row.get(withdrawals_field_alt))).strip()
                deposits = str(row.get(deposits_field, row.get(deposits_field_alt))).strip()

                self.logger.info(f"正在处理第 {i} 行数据: ")
                self.logger.info(f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # 去除金额字段中的逗号
                withdrawals = withdrawals.replace(",", "").replace(" ", "") if withdrawals else ""
                deposits = deposits.replace(",", "").replace(" ", "") if deposits else ""

                # 将金额转换为数字（浮动型数据）
                try:
                    withdrawals = float(withdrawals) if withdrawals else 0
                    deposits = float(deposits) if deposits else 0
                except ValueError as e:
                    self.logger.error(f"处理第 {i} 行数据时发生转换错误: {e}")
                    continue

                self.logger.info(f"正在处理第 {i} 行数据: ")
                self.logger.info(f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # 跳过无收入、支出的无用数据
                if (withdrawals == 0) and (deposits == 0):
                    self.logger.info("该行无有效收入或支出，跳过")
                    continue

                # 正则表达式匹配 UTR 编号
                utr_pattern = r'UPI.*?(\d+)'
                utr_match = re.search(utr_pattern, particulars)
                utr = utr_match.group(1) if utr_match else ''

                self.logger.info(f"提取的 UTR: {utr}")

                # 如果无法提取 UTR，则跳过
                if utr == '' or pd.isna(utr):
                    self.logger.info("无法提取到有效的 UTR，跳过")
                    continue

                # 判断交易类型和金额
                if withdrawals != '' and not pd.isna(withdrawals) and float(withdrawals) > 0:
                    self.logger.info(f"这是支出交易，金额为: {withdrawals}")
                    results.append(
                        {
                            # 'date': date,
                            'utr': utr,
                            'content': particulars,
                            'trade_type': 2,  # 支出
                            'amount': -float(withdrawals)
                        }
                    )
                elif deposits != '' and not pd.isna(deposits) and float(deposits) > 0:
                    self.logger.info(f"这是收入交易，金额为: {deposits}")
                    results.append(
                        {
                            # 'date': date,
                            'utr': utr,
                            'content': particulars,
                            'trade_type': 1,  # 收入
                            'amount': float(deposits)
                        }
                    )

            self.logger.info("解析完成，结果如下：")
            for result in results:
                self.logger.info(result)

            return results

        except Exception as e:
            self.logger.info(f"处理文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_cggb_data(self, uploaded_name):
        """
        解析 CGGB Bank 上传的回执 Excel 文件，返回字典列表：
        [
            {'utr': '回执utr', 'content': '内容', 'trade_type': '交易类型', 'amount': '回执金额', 'code': '确认码'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # 新的标题字段（CGGB Bank）
        date_field = 'Tran. Date'
        particulars_field = 'Tran. Particulars'
        withdrawals_field = 'Debit in ₹'
        deposits_field = 'Credit in ₹'

        # 要查找的标题字段
        header_fields = [date_field, particulars_field, withdrawals_field, deposits_field]

        try:
            # 预读取整个文件内容
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # 查找包含所有标题字段的行
        header_row_index = None
        for i, row in df.iterrows():
            if all(field in row.astype(str).values for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 文件，跳过标题之前的行数
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info("表头字段：", list(data.columns))

            results = []

            for i, row in data.iterrows():
                # 提取各列数据
                date = str(row.get(date_field)).strip() if row.get(date_field) else ''
                particulars = str(row.get(particulars_field)).strip() if row.get(particulars_field) else ''
                withdrawals = str(row.get(withdrawals_field)).strip() if row.get(withdrawals_field) else ''
                deposits = str(row.get(deposits_field)).strip() if row.get(deposits_field) else ''

                self.logger.info(f"正在处理第 {i} 行数据: ")
                self.logger.info(f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # 处理确认码
                confirmation_code = ''
                confirmation_code_pattern = r'([^/]+)$'  # 提取最后一个 `/` 后面的部分
                match = re.search(confirmation_code_pattern, particulars)
                if match:
                    confirmation_code = match.group(1)
                    if len(confirmation_code) != 5:
                        confirmation_code = ''  # 如果确认码长度不是 5 位，返回空

                self.logger.info(f"提取的确认码: {confirmation_code}")

                # 清理金额数据
                withdrawals = withdrawals.replace(' ', '').replace(',', '').strip()
                deposits = deposits.replace(' ', '').replace(',', '').strip()

                try:
                    withdrawals = float(withdrawals) if withdrawals else 0
                    deposits = float(deposits) if deposits else 0
                except ValueError:
                    withdrawals = 0
                    deposits = 0

                self.logger.info(f"处理后的金额数据: Withdrawals: {withdrawals}, Deposits: {deposits}")

                # 跳过无收入、支出的无用数据
                if (withdrawals == 0) and (deposits == 0):
                    self.logger.info("该行无有效收入或支出，跳过")
                    continue

                # 正则表达式匹配 UTR 编号
                utr_pattern = r'UPI.*?(\d+)'
                utr_match = re.search(utr_pattern, particulars)
                utr = utr_match.group(1) if utr_match else ''

                self.logger.info(f"提取的 UTR: {utr}")

                # 如果无法提取 UTR，则跳过
                if utr == '' or pd.isna(utr):
                    self.logger.info("无法提取到有效的 UTR，跳过")
                    continue

                # 判断交易类型和金额
                if withdrawals > 0:
                    self.logger.info(f"这是支出交易，金额为: {withdrawals}")
                    results.append(
                        {
                            'utr': utr,
                            'content': particulars,
                            'trade_type': 2,  # 支出
                            'amount': -withdrawals,
                            'code': confirmation_code  # 确认码
                        }
                    )
                elif deposits > 0:
                    self.logger.info(f"这是收入交易，金额为: {deposits}")
                    results.append(
                        {
                            'utr': utr,
                            'content': particulars,
                            'trade_type': 1,  # 收入
                            'amount': deposits,
                            'code': confirmation_code  # 确认码
                        }
                    )

            self.logger.info("解析完成，结果如下：")
            for result in results:
                self.logger.info(result)

            return results

        except Exception as e:
            self.logger.error(f"处理文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_kvb_data(self, uploaded_name):
        """
        解析 KVB Bank 上传的回执 CSV 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额', 'code': '确认码'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # KVB Bank 的列字段
        date_field = 'Transaction Date'
        description_field = 'Description'
        debit_field = 'Debit'
        credit_field = 'Credit'
        # 需要查找的列
        target_fields = ['transaction date', 'value date', 'branch', 'cheque no.', 'description', 'debit', 'credit', 'balance']
        try:
            cleaned_file = f"static/upload/bank_statement/{uploaded_name}new"

            with open(file_path, "r", encoding="utf-8") as infile, open(cleaned_file, "w", encoding="utf-8", newline="") as outfile:
                reader = csv.reader(infile)
                writer = csv.writer(outfile)

                for row in reader:
                    if len(row) == 8:  # 你的表头有 8 列
                        writer.writerow(row)  # 只保留格式正确的行

            self.logger.info("清理完成，已保存为 cleaned_file.csv")

            # **1️⃣ 读取文件，检查前 20 行**
            with open(cleaned_file, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                sample = f.read(1024)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample)
                except csv.Error:
                    dialect = csv.excel
                df = pd.read_csv(cleaned_file, header=None, delimiter=dialect.delimiter)
        except Exception as e:
            self.logger.info(f"❌ 读取 CSV 文件时发生错误: {e}")
        self.logger.info("初始读取的前10行：")
        self.logger.info(df.head(10))
        
        # -------------------------------
        # 动态查找包含所有目标字段的行（对单元格做 strip 和 lower 处理，去除右侧空格）
        header_row_index = None
        for i, row in df.iterrows():
            # 对当前行的每个单元格做 strip() 和 lower() 处理
            row_processed = [str(cell).strip().lower() for cell in row.values]
            
            # 打印当前处理的行
            self.logger.info(f"Row {i}: {row_processed}")
            
            # 检查当前行是否包含所有目标字段
            match_status = [target_field in row_processed for target_field in target_fields]
            
            # 打印匹配状态
            self.logger.info(f"Matching status: {match_status}")
            if all(match_status):
                header_row_index = i
                self.logger.info(f"Header row found at index: {header_row_index}")
                break
        if header_row_index is None:
            raise ValueError("文件中未找到包含所有指定标题字段的表头行。")
        
        self.logger.info(f"动态定位到的表头行索引：{header_row_index}")
        
        self.logger.info("预览文件内容（前5行）：")
        # self.logger.info(df.head())
        self.logger.info(f"表头行索引: {header_row_index}")
        try:
            # 重新读取 CSV，跳过无关行
            with open(cleaned_file, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                data = pd.read_csv(f, header=header_row_index, delimiter=dialect.delimiter)
            self.logger.info("根据表头重新读取文件成功")
            results = []
            for i, row in data.iterrows():
                # 提取数据并去除空格
                date = str(row.get(date_field, "")).strip()
                description = str(row.get(description_field, "")).strip()
                debit = str(row.get(debit_field, "0")).replace(",", "").replace(" ", "").strip()
                credit = str(row.get(credit_field, "0")).replace(",", "").replace(" ", "").strip()

                self.logger.info(f"正在处理第 {i} 行数据: ")
                self.logger.info(f"Date: {date}, Description: {description}, Debit: {debit}, Credit: {credit}")

                # 1️⃣ 提取最后一个 `-` 之后的字符
                match = re.search(r'-(\w+)$', description)

                confirmation_code = match.group(1) if match else ""

                self.logger.info(f"提取的确认码: {confirmation_code}")

                # 处理金额
                debit = debit.replace(",", "").strip()
                credit = credit.replace(",", "").strip()

                try:
                    debit = float(debit) if debit else 0
                    credit = float(credit) if credit else 0
                except ValueError:
                    debit = 0
                    credit = 0

                self.logger.info(f"处理后的金额数据: Debit: {debit}, Credit: {credit}")

                # 跳过无交易的行
                if debit == 0 and credit == 0:
                    self.logger.info("该行无有效收入或支出，跳过")
                    continue

                # 提取 UTR 编号（假设规则：匹配 UPI 后的数字）
                utr = ""
                utr_match = re.search(r'UPI.*?(\d+)', description)
                if utr_match:
                    utr = utr_match.group(1)

                self.logger.info(f"提取的 UTR: {utr}")

                # 如果没有 UTR，则跳过
                if not utr:
                    self.logger.info("无法提取到有效的 UTR，跳过")
                    continue

                # 判断交易类型
                if debit > 0:
                    self.logger.info(f"这是支出交易，金额: {debit}")
                    results.append({
                        'utr': utr,
                        'content': description,
                        'trade_type': 2,  # 支出
                        'amount': -debit,
                        'code': confirmation_code
                    })
                elif credit > 0:
                    self.logger.info(f"这是收入交易，金额: {credit}")
                    results.append({
                        'utr': utr,
                        'content': description,
                        'trade_type': 1,  # 收入
                        'amount': credit,
                        'code': confirmation_code
                    })

            self.logger.info("解析完成，结果如下：")
            for result in results:
                self.logger.info(result)

            return results

        except Exception as e:
            self.logger.error(f"处理文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_kgb_data(self, uploaded_name):
        """
        解析 KGB Bank 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额', 'code': '确认码'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"

        try:
            # 预读取整个文件内容
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        # 保存到一个新的 Excel 文件
        new_file_path = 'new_kgb_ds_file.xls'
        with pd.ExcelWriter(new_file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

        df = pd.read_excel(new_file_path, sheet_name='Sheet1')

        # ** 找到表头所在行**
        header_row_index = None
        for i, row in df.iterrows():
            if row.iloc[6] == 'Particulars':
                header_row_index = i
                break
        self.logger.info(f" header_row_index: {header_row_index}")
        if header_row_index is None:
            self.logger.error(" 未找到表头，文件格式可能错误")
            return []

        self.logger.info(f" 读取文件成功: {uploaded_name}")

        self.logger.info(f" 识别到表头，行号: {header_row_index}")

        # 重新读取新保存的文件
        data = pd.read_excel(new_file_path, sheet_name='Sheet1', header=header_row_index)

        results = []

        for _, row in data.iterrows():
            # ** 读取备注（memo）**
            memo = str(row.iloc[6]).strip() if pd.notna(row.iloc[6]) else ""

            # ** 处理金额（withdrawal、deposit），如果 NaN 则赋值 0**
            withdrawal = str(row.iloc[19]).replace(",", "").replace(" ", "").strip() if pd.notna(row.iloc[19]) else "0"
            deposit = str(row.iloc[20]).replace(",", "").replace(" ", "").strip() if pd.notna(row.iloc[20]) else "0"

            # ** 转换金额格式**
            try:
                withdrawal = float(withdrawal) if withdrawal else 0
                deposit = float(deposit) if deposit else 0
            except ValueError:
                withdrawal = 0
                deposit = 0

            # ** 提取 UTR 号码**
            utr = ""
            utr_match = re.search(r'UPI.*?(\d+)', memo)  # 仅匹配 UPI 交易的 UTR
            if utr_match:
                utr = utr_match.group(1)

            if not utr:
                print(" 跳过无 UTR 的交易")
                continue  # 没有 UTR，跳过当前行

            # ** 确定交易类型**
            if withdrawal > 0:
                trade_type = 2  # 支出
                amount = -withdrawal
            elif deposit > 0:
                trade_type = 1  # 收入
                amount = deposit
            else:
                continue  # 没有金额，跳过

            # ** 存储结果**
            results.append({
                'utr': utr,
                'content': memo,  # 备注信息
                'trade_type': trade_type,
                'amount': amount
            })

        # ** 打印最终结果**
        for res in results:
            self.logger.info(f"排序前: {res}")
        results.reverse()  # 🔁 将列表反转，达到倒置目的
        for res in results:
            self.logger.info(f"排序后: {res}")

        self.logger.info(f" 解析完成，共 {len(results)} 条交易记录")
        return results

    @staticmethod
    async def extract_bompaytm_data(self, uploaded_name):
        """
        解析 BOM PAYTM 上传的回执 CSV 文件，返回符合条件的交易数据：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额', 'code': '确认码'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        try:
            # ** 读取 CSV 文件**
            with open(file_path, mode='r', encoding='utf-8', errors='ignore', newline='') as f:
                df = pd.read_csv(f)

            self.logger.info("文件读取成功，预览前 5 行数据：")
            self.logger.info(df.head())
            df_sorted = df.sort_values(by='Updated_Date', ascending=True)

            results = []
            for i, row in df_sorted.iterrows():
                # 提取相关字段
                bank_transaction_id = str(row.get('Bank_Transaction_ID', '')).replace("'", "").strip()
                Amount = str(row.get('Amount', '0')).replace(",", "").replace(" ", "").strip()
                updated_date = str(row.get('Updated_Date', '')).replace("'", "").strip()

                self.logger.info(f"处理第 {i} 行: UTR={bank_transaction_id}, Amount={Amount}")

                # 确保 UTR 存在
                if not bank_transaction_id:
                    self.logger.info("没有找到有效的 UTR，跳过该行")
                    continue

                # 处理金额
                try:
                    Amount = float(Amount)
                except ValueError:
                    self.logger.info("无法解析 Settled_Amount，跳过该行")
                    continue

                # **跳过 UTR 为空（NaN）的行**
                if not bank_transaction_id or bank_transaction_id.lower() == "nan":
                    self.logger.info(f"第 {i} 行 UTR 为空，跳过")
                    continue

                # 只处理 Amount > 0 的交易
                if Amount > 0:
                    self.logger.info(f"该交易属于代收交易（收入），金额: {Amount}")
                    results.append({
                        'utr': bank_transaction_id,
                        'trade_type': 1,  # 1 表示收入
                        'amount': Amount
                    })
                else:
                    self.logger.info("该交易不是代收交易，跳过")

            self.logger.info("解析完成，结果如下：")
            self.logger.info("解析完成，最终解析结果（部分）：")
            self.logger.info(results[:5])  # 只打印部分数据以避免日志过长

            return results

        except Exception as e:
            self.logger.error(f"处理文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_city_union_data(self, uploaded_name):
        """
        解析 CITY UNION BANK 上传的回执 xls 文件，返回符合条件的交易数据：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额', 'ifsc': 'ifsc'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        try:
            raw_df = pd.read_excel(file_path, header=None, dtype=str)

            # 前置信息行数不确定，动态定位关键行，DATE表头为首行，表后首个空行为结束
            header_row = raw_df[raw_df[0].str.contains('DATE', na=False)].index[0]
            data_start = header_row
            data_end = raw_df[raw_df[0].str.contains('TOTAL', na=False)].index[0] - 2

            self.logger.info(f"正在处理文件: {uploaded_name}")

            # 重建数据表
            columns = ['DATE', 'content', 'CHEQUE NO', 'amount_out', 'amount_in', 'BALANCE']
            df = pd.read_excel(file_path,
                               skiprows=data_start,
                               nrows=data_end - data_start,
                               names=columns,
                               parse_dates=['DATE'],
                               date_parser=lambda x: datetime.strptime(x, '%d/%m/%Y'),
                               converters={
                                   'amount_out': lambda x: abs(float(x)) if str(x).strip() else 0,
                                   'amount_in': lambda x: abs(float(x)) if str(x).strip() else 0,
                                   'BALANCE': lambda x: abs(float(x)) if str(x).strip() else 0
                               })
            # 过滤交易类型为收款的
            df['trade_type'] = df.apply(
                lambda r: '1' if r.amount_in > 0 else '2',
                axis=1
            )
            df = df[df['trade_type'] == '1']
            df['amount'] = df.apply(
                lambda r: r.amount_in if r.amount_in > 0 else 0,
                axis=1
            )
            # 剔除非UPI的数据,提取utr
            df = df[df['content'].str.contains(r'UPI', case=False)]
            df['utr'] = df.apply(
                lambda r: re.search(r'(?i)(UPI)[^0-9]*(\d{10,12})', r.content).group(2)
                if re.search(r'UPI', r.content) else None, axis=1)
            ifsc = raw_df[raw_df[0].str.contains('IFSC', na=False)].iloc[0][0].split(': ')[1]
            df['ifsc'] = ifsc if ifsc else ''
            results = df[['utr', 'content', 'trade_type', 'amount', 'ifsc']].to_dict(orient='records')

            self.logger.info("解析完成，结果如下：")
            self.logger.info("解析完成，最终解析结果（部分）：")
            self.logger.info(results[:5])  # 只打印部分数据以避免日志过长

            return results

        except Exception as e:
            self.logger.error(f"处理文件时发生错误: {e}")
            return []

    @staticmethod
    async def extract_jk_bank_data(self, uploaded_name):
        """
        解析 JK Bank 上传的回执 Excel 文件，返回字典列表：
        [
            {'utr': '交易编号', 'content': '交易备注', 'trade_type': '交易类型', 'amount': '交易金额', 'code': '确认码'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **JK Bank 对应的表头**
        date_field = 'Transaction Date'  # 交易日期
        particulars_field = 'Transaction Remarks'  # 交易备注
        withdrawals_field = 'Withdrawal(INR)'  # 支出金额
        deposits_field = 'Deposit(INR)'  # 存入金额
        utr_field = 'Transaction Ref No'  # 交易编号 (UTR)

        # 目标表头列表
        header_fields = [date_field, particulars_field, withdrawals_field, deposits_field, utr_field]

        if file_path.endswith('.xls') or file_path.endswith('.xlsx'):
            try:
                # 读取 Excel
                df = pd.read_excel(file_path, header=None)
                # **查找表头行索引**
                header_row_index = None
                for i, row in df.iterrows():
                    if all(field in row.astype(str).values for field in header_fields):
                        header_row_index = i
                        break

                if header_row_index is None:
                    self.logger.info("未能找到有效的表头，请检查文件格式！")
                    return []
                self.logger.info(f"表头行索引: {header_row_index}")
                df = pd.read_excel(file_path, header=header_row_index)
                df = df.loc[:, ~df.columns.str.contains('Unnamed')]
                self.logger.info('文件已成功读取')
            except Exception as e:
                self.logger.error(f"读取文件时发生错误: {e}")
                return []
        elif file_path.endswith('.csv'):
            header_row_index = None
            try:
                with open(file_path, 'r') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if all(field in row for field in header_fields):
                            header_row_index = reader.line_num - 1
                            break
                if header_row_index is None:
                    self.logger.info('未能找到有效的表头，请检查文件格式！')
                    return []
                df = pd.read_csv(file_path, header=header_row_index, dtype=object, skip_blank_lines=False)
                df = df.loc[:, ~df.columns.str.contains('Unnamed')]
                self.logger.info('文件已成功读取')
            except Exception as e:
                self.logger.error(f'读取文件时发生错误: {e}')
                return []

        #预览
        self.logger.info("预览内容（前5行）：")
        self.logger.info(df.head())
        try:
            results = []
            for i, row in df.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(particulars_field, '')).strip()
                withdrawals = str(row.get(withdrawals_field, '')).strip()
                deposits = str(row.get(deposits_field, '')).strip()
                utr = str(row.get(utr_field, '')).strip()

                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue


                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}, UTR: {utr}")

                # **格式化金额**
                withdrawals = withdrawals.replace(',', '').replace(' ', '').strip()
                deposits = deposits.replace(',', '').replace(' ', '').strip()

                try:
                    withdrawals = float(withdrawals) if withdrawals else 0
                    deposits = float(deposits) if deposits else 0
                except ValueError:
                    withdrawals = 0
                    deposits = 0

                self.logger.info(f"处理后的金额数据: Withdrawals: {withdrawals}, Deposits: {deposits}")

                utr_pattern = r'UPI/[A-Z]+/(\d+)'
                match = re.search(utr_pattern, particulars)
                utr = match.group(1) if match else ''

                # **跳过无金额交易**
                if withdrawals == 0 and deposits == 0:
                    self.logger.info("该行无有效收入或支出，跳过")
                    continue

                # **构造返回结果**
                if withdrawals > 0:
                    trade_type = 2  # 支出
                    amount = -withdrawals
                else:
                    trade_type = 1  # 收入
                    amount = deposits

                results.append(
                    {
                        'utr': utr,
                        'content': particulars,
                        'trade_type': trade_type,
                        'amount': amount
                    }
                )

            # self.logger.info("解析完成，结果如下：")
            # for result in results:
            #     self.logger.info(result)
            # ** 打印最终结果**
            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")

            return results

        except Exception as e:
            self.logger.error(f"处理文件时发生错误: {e}")
            return []
        
    
    
    @staticmethod
    async def extract_karnataka_bank_data(self, uploaded_name):
        """
        解析 Karnataka Bank 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        file_path = f"static/upload/bank_statement/{uploaded_name}"

        try:
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        new_file_path = 'new_karnataka_ds_file.xls'
        with pd.ExcelWriter(new_file_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Sheet1', index=False)

        # 读取保存后的文件
        data = pd.read_excel(new_file_path, sheet_name='Sheet1')

        results = []

        for _, row in data.iterrows():
            # 解析列（假设格式为：Date | Description | Debit | Balance）
            date = str(row[2]).strip() if pd.notna(row[2]) else ""
            memo = str(row[5]).strip() if pd.notna(row[5]) else ""

            debit = str(row[11]).replace(",", "").replace(" ", "").strip() if pd.notna(row[11]) else "0"
            credit = str(row[13]).replace(",", "").replace(" ", "").strip() if pd.notna(row[13]) else "0"  # 若无显式 Credit 列，设为 0
            # balance = str(row[13]).replace(",", "").replace(" ", "").strip() if pd.notna(row[13]) else "0"

            try:
                debit = float(debit) if debit else 0
                credit = float(credit) if credit else 0
            except ValueError:
                debit = 0
                credit = 0

            # ✅ 打印当前行数据（或用 self.logger.info 替代 print）
            self.logger.info(f"[Date: {date} | Memo: {memo} | Debit: {debit} | Credit: {credit}")

            # 提取 UTR
            utr = ""
            utr_match = re.search(r'UPI[:：]?(\d+)', memo)
            if utr_match:
                utr = utr_match.group(1)

            if not utr:
                self.logger.info(f"跳过无 UTR 的交易: {memo}")
                continue

            # 判断交易类型
            if debit > 0:
                trade_type = 2  # 支出
                amount = -debit
            elif credit > 0:
                trade_type = 1  # 收入
                amount = credit
            else:
                continue  # 跳过无金额

            results.append({
                'utr': utr,
                'content': memo,
                'trade_type': trade_type,
                'amount': amount
            })

        # 输出处理结果
        for res in results:
            self.logger.info(f"排序前: {res}")
        results.reverse()
        for res in results:
            self.logger.info(f"排序后: {res}")

        self.logger.info(f"解析完成，共 {len(results)} 条交易记录")
        return results

    @staticmethod
    async def extract_dhan_bank_data(self, uploaded_name):
        """
        解析 DHAN BANK 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f'正在处理文件: {uploaded_name}')

        # 文件路径
        file_path = f'static/upload/bank_statement/{uploaded_name}'
        self.logger.info(f'文件路径: {file_path}')

        # **DHAN Bank 对应的表头**
        date_field = 'Txn Date (DD/MM/YYYY)'  # 交易日期
        deposits_field = 'Txn Amount'  # 存入金额
        utr_field = 'Description'  # 交易编号 (UTR)

        # 目标表头列表
        header_fields = [date_field, deposits_field, utr_field]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info('文件已成功读取')
        except Exception as e:
            self.logger.error(f'读取文件时发生错误: {e}')
            return []

        self.logger.info('预览文件内容（前5行）：')
        self.logger.info(df.head())

        header_row_index = None
        for i, row in df.iterrows():
            if all(field in row.astype(str).values for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info('未能找到有效的表头，请检查文件格式！')
            return []

        self.logger.info(f'表头行索引: {header_row_index}')

        try:
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info('根据表头重新读取文件成功')
            self.logger.info(f'表头字段：{list(data.columns)}')

            results = []
            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                deposits = str(row.get(deposits_field, '')).strip()
                utr_content = str(row.get(utr_field, '')).strip()
                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f'第 {i} 行 Date 为空，跳过')
                    continue

                self.logger.info(f'处理第 {i} 行数据')
                self.logger.info(f'Date: {date}, UTR: {utr_content} Deposits: {deposits}')

                utr_match = re.search(r'UPI TXN: /(\d+)', utr_content)
                utr = utr_match.group(1) if utr_match else None
                if utr is None:
                    self.logger.info(f'跳过无 UTR 的交易: {utr_content}')
                    continue

                amount_match = re.search(r'([\d,]+\.\d{2})', deposits)
                amount = Decimal(amount_match.group(1).replace(',', '')) if amount_match else Decimal(0)
                if amount == Decimal(0):
                    self.logger.info(f'跳过无金额的交易: utr: {utr}, Txn Amount: {deposits}')
                    continue

                results.append({
                    "utr": utr,
                    "amount": amount,
                    "content": utr_content,
                    "trade_type": 1  # 固定为1（UPI交易）
                })
            
            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []


    @staticmethod
    async def extract_bob_bank_data(self, uploaded_name):
        """
        解析 BOB BANK 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **JK Bank 对应的表头**
        date_field = 'TRAN DATE'  # 交易日期
        particulars_field = 'NARRATION'  # 交易备注
        withdrawals_field = 'WITHDRAWAL(DR)'  # 支出金额
        deposits_field = 'DEPOSIT(CR)'  # 存入金额

        # 目标表头列表
        header_fields = [date_field, particulars_field, withdrawals_field, deposits_field]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # **查找表头行索引**
        header_row_index = None
        for i, row in df.iterrows():
            if all(field in row.astype(str).values for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 数据（跳过标题行）
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info("表头字段：", list(data.columns))

            results = []

            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(particulars_field, '')).strip()
                withdrawals = str(row.get(withdrawals_field, '')).strip()
                deposits = str(row.get(deposits_field, '')).strip()

                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(
                    f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # **格式化金额**
                withdrawals = withdrawals.replace(',', '').replace(' ', '').strip()
                deposits = deposits.replace(',', '').replace(' ', '').strip()

                try:
                    withdrawals = float(withdrawals) if withdrawals else 0
                    deposits = float(deposits) if deposits else 0
                except ValueError:
                    withdrawals = 0
                    deposits = 0

                self.logger.info(f"处理后的金额数据: Withdrawals: {withdrawals}, Deposits: {deposits}")

                utr_pattern = r'UPI/(\d+)'
                match = re.search(utr_pattern, particulars)
                utr = match.group(1) if match else ''

                # **跳过无金额交易**
                if withdrawals == 0 and deposits == 0:
                    self.logger.info("该行无有效收入或支出，跳过")
                    continue

                # **构造返回结果**
                if withdrawals > 0:
                    trade_type = 2  # 支出
                    amount = -withdrawals
                else:
                    trade_type = 1  # 收入
                    amount = deposits

                results.append(
                    {
                        'utr': utr,
                        'content': particulars,
                        'trade_type': trade_type,
                        'amount': amount
                    }
                )

            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")

            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @staticmethod
    async def extract_boi_bank_data(self, uploaded_name):
        """
        解析 BOI BANK 上传的 CSV 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f'正在处理文件: {uploaded_name}')

        file_path = f'static/upload/bank_statement/{uploaded_name}'
        self.logger.info(f'文件路径: {file_path}')

        # **BOI Bank 对应的表头**
        date_field = 'Date'  # 交易日期
        deposits_field = 'Credit'  # 存入金额
        withdrawals_field = 'Debit'  # 支出金额
        utr_field = 'Remarks'  # 交易编号 (UTR)

        header_fields = [date_field, deposits_field, withdrawals_field, utr_field]
        header_row_index = None

        try:
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if all(field in row for field in header_fields):
                        header_row_index = reader.line_num - 1
                        break
            if header_row_index is None:
                self.logger.info('未能找到有效的表头，请检查文件格式！')
                return []
            df = pd.read_csv(file_path, skiprows=header_row_index, header=0, dtype=object)
            self.logger.info('文件已成功读取')
        except Exception as e:
            self.logger.error(f'读取文件时发生错误: {e}')
            return []
        
        self.logger.info('预览文件内容（前5行）：')
        self.logger.info(df.head())
        self.logger.info(f'表头行索引: {header_row_index}')

        try:
            self.logger.info(f'表头字段：{list(df.columns)}')

            results = []
            for i, row in df.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                deposits = row.get(deposits_field, '')
                withdrawals = row.get(withdrawals_field, '')
                utr_content = str(row.get(utr_field, '')).strip()
                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f'第 {i} 行 Date 为空，跳过')
                    continue

                self.logger.info(f'处理第 {i} 行数据')
                self.logger.info(f'Date: {date}, UTR: {utr_content} Deposits: {deposits} Withdrawals: {withdrawals}')

                utr_match = re.search(r'(?:^IMPSUAIB\/|^UPI\/)(\d+)', utr_content)
                utr = utr_match.group(1) if utr_match else None
                if utr is None:
                    self.logger.info(f'跳过无 UTR 的交易: {utr_content}')
                    continue
                
                deposits = Decimal(0) if pd.isna(deposits) else Decimal(deposits.replace(',', ''))
                withdrawals =  Decimal(0) if pd.isna(withdrawals) else Decimal(withdrawals.replace(',', ''))
                if deposits == Decimal(0) and withdrawals == Decimal(0):
                    self.logger.info(f'跳过无金额的交易: utr: {utr}, deposits: {deposits} withdrawals: {withdrawals}')
                    continue

                if withdrawals > 0:
                    trade_type = 2  # 支出
                    amount = -withdrawals
                else:
                    trade_type = 1  # 收入
                    amount = deposits

                results.append({
                    "utr": utr,
                    "amount": amount,
                    "content": utr_content,
                    "trade_type": trade_type
                })

            for res in results:
                self.logger.info(f"{res}")
            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @staticmethod
    async def extract_tmb_bank_data(self, uploaded_name):
        """
        解析 TMB BANK 上传的 CSV 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f'正在处理文件: {uploaded_name}')
        file_path = f'static/upload/bank_statement/{uploaded_name}'
        self.logger.info(f'文件路径: {file_path}')

        #表头
        date_field = 'Txn. date'  # 交易日期
        deposits_field = 'Credit'  # 存入金额
        withdrawals_field = 'Debit'  # 支出金额
        utr_field = 'Transaction Remarks'  # 交易编号 (UTR)
        header_fields = [date_field, deposits_field, withdrawals_field, utr_field]
        header_row_index = None

        try:
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if all(field in row for field in header_fields):
                        header_row_index = reader.line_num - 1
                        break
            if header_row_index is None:
                self.logger.info('未能找到有效的表头，请检查文件格式！')
                return []
            df = pd.read_csv(file_path, header=header_row_index, dtype=object, skip_blank_lines=False)
            df = df.loc[:, ~df.columns.str.contains('Unnamed')]
            self.logger.info('文件已成功读取')
        except Exception as e:
            self.logger.error(f'读取文件时发生错误: {e}')
            return []
        
        self.logger.info(f'表头行索引: {header_row_index}')
        self.logger.info(f'表头字段：{list(df.columns)}')
        self.logger.info('预览文件内容（前5行）：')
        self.logger.info(df.head())

        try:
            results = []
            for i, row in df.iterrows():
                date = str(row.get(date_field, '')).strip()
                deposits = row.get(deposits_field, '')
                withdrawals = row.get(withdrawals_field, '')
                utr_content = str(row.get(utr_field, '')).strip()
                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f'第 {i} 行 Date 为空，跳过')
                    continue

                self.logger.info(f'处理第 {i} 行数据')
                self.logger.info(f'Date: {date}, UTR: {utr_content} Deposits: {deposits} Withdrawals: {withdrawals}')

                utr_match = re.search(r'^UPI\/(\d+)', utr_content)
                utr = utr_match.group(1) if utr_match else None
                if utr is None:
                    self.logger.info(f'跳过无UTR或非目标的交易: {utr_content}')
                    continue
                
                deposits = Decimal(0) if pd.isna(deposits) else Decimal(deposits.replace(',', ''))
                withdrawals =  Decimal(0) if pd.isna(withdrawals) else Decimal(withdrawals.replace(',', ''))
                if deposits == Decimal(0) and withdrawals == Decimal(0):
                    self.logger.info(f'跳过无金额的交易: utr: {utr}, deposits: {deposits} withdrawals: {withdrawals}')
                    continue

                if withdrawals > 0:
                    trade_type = 2  # 支出
                    amount = -withdrawals
                else:
                    trade_type = 1  # 收入
                    amount = deposits

                results.append({
                    "utr": utr,
                    "amount": amount,
                    "content": utr_content,
                    "trade_type": trade_type
                })

            for res in results:
                self.logger.info(f"{res}")
            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @staticmethod
    async def extract_psb_bank_data(self, uploaded_name):
        """
        解析 PSB BANK 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径 (assuming the file is in this static directory)
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **PSB Bank 对应的表头**
        date_field = 'Transaction Date'  # 交易日期
        particulars_field = 'Remarks'  # 交易备注
        withdrawals_field = 'Withdraw'  # 支出金额
        deposits_field = 'Deposit'  # 存入金额

        # 目标表头列表
        header_fields = [date_field, particulars_field, withdrawals_field, deposits_field]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # **查找表头行索引**
        header_row_index = None
        for i, row in df.iterrows():
            # Convert all row values to string for consistent searching
            row_values_str = row.astype(str).values
            if all(field in row_values_str for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 数据（跳过标题行）
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info(f"表头字段：{list(data.columns)}")

            results = []

            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(particulars_field, '')).strip()
                withdrawals = str(row.get(withdrawals_field, '')).strip()
                deposits = str(row.get(deposits_field, '')).strip()

                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)) or not date: # Added check for empty string after strip
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(
                    f"Date: {date}, Particulars: {particulars}, Withdrawals: {withdrawals}, Deposits: {deposits}")

                # **格式化金额**
                withdrawals = withdrawals.replace(',', '').replace(' ', '').strip()
                deposits = deposits.replace(',', '').replace(' ', '').strip()

                # **格式化金额**
                # 清理金额字符串：移除逗号和空格，并去除两端空白
                withdrawals_str_cleaned = withdrawals.replace(',', '').replace(' ', '').strip()
                deposits_str_cleaned = deposits.replace(',', '').replace(' ', '').strip()

                try:
                    # 如果字符串是 '-' 或空，则设为 0.0，否则尝试转换为浮点数
                    withdrawals = float(withdrawals_str_cleaned) if withdrawals_str_cleaned and withdrawals_str_cleaned != '-' else 0.0
                    deposits = float(deposits_str_cleaned) if deposits_str_cleaned and deposits_str_cleaned != '-' else 0.0
                except ValueError:
                    # 如果转换失败（例如，字符串格式不正确），则设为 0.0 并记录警告
                    self.logger.warning(f"无法解析金额数据. Withdrawals: '{withdrawals_str_cleaned}', Deposits: '{deposits_str_cleaned}'. 设置为 0.")
                    withdrawals = 0.0
                    deposits = 0.0

                self.logger.info(f"处理后的金额数据: Withdrawals: {withdrawals}, Deposits: {deposits}")

                # **提取 UTR**
                utr_pattern = r'UPI/CR/(\d+)'
                match = re.search(utr_pattern, particulars)
                utr = match.group(1) if match else ''

                # **跳过无金额交易**
                if withdrawals == 0 and deposits == 0:
                    self.logger.info("该行无有效收入或支出，跳过")
                    continue

                # **构造返回结果**
                if withdrawals > 0:
                    trade_type = 2  # 支出
                    amount = -withdrawals
                else:
                    trade_type = 1  # 收入
                    amount = deposits

                results.append(
                    {
                        'utr': utr,
                        'content': particulars,
                        'trade_type': trade_type,
                        'amount': amount
                    }
                )

            for res in results:
                self.logger.info(f"排序前: {res}")
            # results.reverse()  # 🔁 将列表反转，达到倒置目的 (assuming data is reverse chronological in Excel)
            # for res in results:
            #     self.logger.info(f"排序后: {res}")

            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []
        
    
    @staticmethod
    async def extract_paytm_bank_data(self, uploaded_name):
        """
        解析 Paytm 上传的 CSV 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'merchant_unique_ref': '商户唯一参考号', 'transaction_type': '交易类型', 'amount': '金额', ...},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f'正在处理文件: {uploaded_name}')
        file_path = f'static/upload/bank_statement/{uploaded_name}'
        self.logger.info(f'文件路径: {file_path}')

        # 定义表头字段
        date_field = 'Transaction_Date'  # 交易日期
        amount_field = 'Amount'  # 金额
        utr_field = 'Bank_Transaction_ID'  # 交易编号 (UTR)
        status_field = 'Status'  # 状态
        merchant_ref_field = 'Merchant_Ref_ID'  # 商户参考号
        header_fields = [date_field, amount_field, utr_field, status_field, merchant_ref_field]

        header_row_index = None

        try:
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                for row in reader:
                    if all(field in row for field in header_fields):
                        header_row_index = reader.line_num - 1
                        break
            if header_row_index is None:
                self.logger.info('未能找到有效的表头，请检查文件格式！')
                return []
            df = pd.read_csv(file_path, header=header_row_index, dtype=object, skip_blank_lines=False)
            df = df.loc[:, ~df.columns.str.contains('Unnamed')]
            self.logger.info('文件已成功读取')
        except Exception as e:
            self.logger.error(f'读取文件时发生错误: {e}')
            return []
        
        self.logger.info(f'表头行索引: {header_row_index}')
        self.logger.info(f'表头字段：{list(df.columns)}')
        self.logger.info('预览文件内容（前5行）：')
        self.logger.info(df.head())

        try:
            results = []
            for i, row in df.iterrows():
                # 获取字段内容
                date = str(row.get(date_field, '')).strip()
                amount = row.get(amount_field, '')
                utr_content = str(row.get(utr_field, '')).strip()
                utr = utr_content.replace("'", "") if utr_content else None
                status = str(row.get(status_field, '')).strip()
                merchant_ref = str(row.get(merchant_ref_field, '')).strip()

                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)):
                    self.logger.info(f'第 {i} 行 Date 为空，跳过')
                    continue

                self.logger.info(f'处理第 {i} 行数据')
                self.logger.info(f'Date: {date}, UTR: {utr}, Amount: {amount}, Status: {status}, Merchant Ref: {merchant_ref}')

                # 转换金额字段
                amount = Decimal(0) if pd.isna(amount) else Decimal(amount.replace(',', ''))
                if amount == Decimal(0):
                    self.logger.info(f'跳过无金额的交易: utr: {utr}, amount: {amount}')
                    continue


                # Check if utr is NaN
                if pd.isna(utr) or utr == "" or utr == "nan":
                    self.logger.info(f'第 {i} 行 UTR 为空，跳过')
                    continue

                results.append({
                    "utr": utr,
                    "amount": amount,
                    "content": utr,
                    "trade_type": 1
                })
            # ** 打印最终结果**
            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results

            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @staticmethod
    async def extract_jana_bank_data(self, uploaded_name):
        """
        解析 JANA BANK 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径 (assuming the file is in this static directory)
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **PSB Bank 对应的表头**
        date_field = 'Transaction Date'  # 交易日期
        particulars_field = 'Description'  # 交易备注
        reference_no = 'Reference No' # utr
        transaction_amount = 'Transaction Amount(in Rs)' #交易金额

        # 目标表头列表
        header_fields = [date_field, particulars_field, reference_no,transaction_amount]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # **查找表头行索引**
        header_row_index = None
        for i, row in df.iterrows():
            # Convert all row values to string for consistent searching
            row_values_str = row.astype(str).values
            if all(field in row_values_str for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 数据（跳过标题行）
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info(f"表头字段：{list(data.columns)}")

            results = []

            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(particulars_field, '')).strip()
                reference_no = str(row.get(reference_no, '')).strip()
                tran_amount = str(row.get(transaction_amount, '')).strip()
                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)) or not date: # Added check for empty string after strip
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(f"Date: {date}, Particulars: {particulars}, transaction_amount: {transaction_amount}")

                # **提取 UTR**
                utr_pattern = r'UPI/CR/(\d+)'
                match = re.search(utr_pattern, particulars)
                utr = match.group(1) if match else ''
                if not utr:
                    self.logger.info(f"第 {i} 行 没有采集到正确的utr，跳过")
                    continue

                # **格式化金额**
                tran_amount = tran_amount.replace(',', '').replace(' ', '').strip()
                try:
                    # 如果字符串是 '-' 或空，则设为 0.0，否则尝试转换为浮点数
                    tran_amount = float(tran_amount) if tran_amount and tran_amount != '-' else 0.0
                except ValueError:
                    # 如果转换失败（例如，字符串格式不正确），则设为 0.0 并记录警告
                    self.logger.warning(f"无法解析金额数据. transaction_amount: '{tran_amount}'. 设置为 0.")
                    tran_amount = 0.0

                self.logger.info(f"处理后的金额数据: transaction_amount: {tran_amount}")

                # **跳过无金额交易**
                if tran_amount == 0:
                    self.logger.info(f"第 {i} 行,该行无有效收入，跳过")
                    continue

                results.append(
                    {
                        'utr': utr,
                        'content': particulars,
                        'trade_type': 1,
                        'amount': tran_amount
                    }
                )

            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的 (assuming data is reverse chronological in Excel)
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @staticmethod
    async def extract_iob_bank_data(self, uploaded_name):
        """
        解析 IOB BANK 上传的 XLS 文件，返回字典列表：
        [
            {'utr': 'UTR值', 'content': '交易描述', 'trade_type': '交易类型', 'amount': '金额'},
            ...
        ]
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径 (assuming the file is in this static directory)
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **IOB Bank 对应的表头**
        # date_field = 'Date'  # 交易日期
        date_field = 'Value Date'  # 交易日期
        # chq_no = 'Chq No'  #
        narration = 'Narration'  # 摘要
        # cod = 'Cod'  # 交易金额
        # debit = 'Debit'  # 交易金额
        credit = 'Credit'  # 交易金额
        # balance = 'Balance'  # 余额

        # 目标表头列表
        header_fields = [date_field, narration, credit]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前5行）：")
        self.logger.info(df.head())

        # **查找表头行索引**
        header_row_index = None
        for i, row in df.iterrows():
            # Convert all row values to string for consistent searching
            row_values_str = row.astype(str).values
            if all(field in row_values_str for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 数据（跳过标题行）
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            self.logger.info(f"表头字段：{list(data.columns)}")

            results = []

            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(narration, '')).strip()
                # reference_no = str(row.get(reference_no, '')).strip()
                tran_amount = str(row.get(credit, '')).strip()
                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)) or not date:  # Added check for empty string after strip
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(f"Date: {date}, narration: {particulars}, credit: {credit}")

                # **提取 UTR**
                utr_pattern = r'UPI/(\d+)/CR'
                match = re.search(utr_pattern, particulars)
                utr = match.group(1) if match else ''
                if not utr:
                    self.logger.info(f"第 {i} 行 没有采集到正确的utr，跳过")
                    continue

                # **格式化金额**
                tran_amount = tran_amount.replace(',', '').replace(' ', '').strip()
                try:
                    # 如果字符串是 '-' 或空，则设为 0.0，否则尝试转换为浮点数
                    tran_amount = float(tran_amount) if tran_amount and tran_amount != '-' else 0.0
                except ValueError:
                    # 如果转换失败（例如，字符串格式不正确），则设为 0.0 并记录警告
                    self.logger.warning(f"无法解析金额数据. credit: '{tran_amount}'. 设置为 0.")
                    tran_amount = 0.0

                self.logger.info(f"处理后的金额数据: credit: {tran_amount}")

                # **跳过无金额交易**
                if tran_amount == 0:
                    self.logger.info(f"第 {i} 行,该行无有效收入，跳过")
                    continue

                results.append(
                    {
                        'utr': utr,
                        'content': particulars,
                        'trade_type': 1,
                        'amount': tran_amount
                    }
                )

            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的 (assuming data is reverse chronological in Excel)
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @staticmethod
    async def extract_au_bank_data(self, uploaded_name):
        """
        解析 AU BANK 上传的 XLS 文件，返回字典列表：
        """
        uploaded_name = uploaded_name.lower()
        self.logger.info(f"正在处理文件: {uploaded_name}")

        # 文件路径 (assuming the file is in this static directory)
        file_path = f"static/upload/bank_statement/{uploaded_name}"
        self.logger.info(f"文件路径: {file_path}")

        # **AU Bank 对应的表头**
        date_field = 'Transaction  Date'  # 交易日期
        narration = 'Description/Narration'  # 摘要
        credit = 'Credit (₹)'  # 交易金额

        # 目标表头列表
        header_fields = [date_field, narration, credit]

        try:
            # 读取 Excel
            df = pd.read_excel(file_path, header=None)
            self.logger.info("文件已成功读取")
        except Exception as e:
            self.logger.error(f"读取文件时发生错误: {e}")
            return []

        self.logger.info("预览文件内容（前15行）：")
        # self.logger.info(df.head(15))

        # **查找表头行索引**
        header_row_index = None
        for i, row in df.iterrows():
            # Convert all row values to string for consistent searching
            row_values_str = row.astype(str).values
            if all(field in row_values_str for field in header_fields):
                header_row_index = i
                break

        if header_row_index is None:
            self.logger.info("未能找到有效的表头，请检查文件格式！")
            return []

        self.logger.info(f"表头行索引: {header_row_index}")

        try:
            # 读取 Excel 数据（跳过标题行）
            data = pd.read_excel(file_path, header=header_row_index)
            self.logger.info("根据表头重新读取文件成功")
            # self.logger.info(f"表头字段：{list(data.columns)}")

            results = []

            for i, row in data.iterrows():
                # 提取字段
                date = str(row.get(date_field, '')).strip()
                particulars = str(row.get(narration, '')).strip()
                tran_amount = str(row.get(credit, '')).strip()
                # **跳过 Date 为空的行**
                if pd.isna(row.get(date_field)) or not date:  # Added check for empty string after strip
                    self.logger.info(f"第 {i} 行 Date 为空，跳过")
                    continue

                self.logger.info(f"处理第 {i} 行数据")
                self.logger.info(f"Date: {date}, narration: {particulars}, credit: {tran_amount}")

                if not particulars.startswith("RTS"):
                    self.logger.info(f"第 {i} 行 不是代收数据，跳过")
                    continue

                # **提取 UTR**
                utr_pattern = r'^\d{11,12}$'
                for content in particulars.split(' '):
                    content = content.strip()
                    match = re.search(utr_pattern, content)
                    utr = match.group(0) if match else ''
                    if utr:
                        break

                if not utr:
                    self.logger.info(f"第 {i} 行 没有采集到正确的utr，跳过")
                    continue

                # **格式化金额**
                tran_amount = tran_amount.replace(',', '').replace(' ', '').strip()
                try:
                    # 如果字符串是 '-' 或空，则设为 0.0，否则尝试转换为浮点数
                    tran_amount = float(tran_amount) if tran_amount and tran_amount != '-' else 0.0
                except ValueError:
                    # 如果转换失败（例如，字符串格式不正确），则设为 0.0 并记录警告
                    self.logger.warning(f"无法解析金额数据. credit: '{tran_amount}'. 设置为 0.")
                    tran_amount = 0.0

                self.logger.info(f"处理后的金额数据: credit: {tran_amount}")

                # **跳过无金额交易**
                if tran_amount == 0:
                    self.logger.info(f"第 {i} 行,该行无有效收入，跳过")
                    continue

                results.append(
                    {
                        'utr': utr,
                        'content': particulars,
                        'trade_type': 1,
                        'amount': tran_amount
                    }
                )

            for res in results:
                self.logger.info(f"排序前: {res}")
            results.reverse()  # 🔁 将列表反转，达到倒置目的 (assuming data is reverse chronological in Excel)
            for res in results:
                self.logger.info(f"排序后: {res}")
            return results
        except Exception as e:
            self.logger.error(f'处理文件时发生错误: {e}')
            return []

    @tornado.web.authenticated
    async def post(self):
        try:
            data = json.loads(self.request.body)
            filename = data.get('filename')
            payment_id = data.get('payment_id')
            random_code = data.get('random_code')
            # 锁
            busy_key = 'import_bank_record_{}'.format(self.current_user['id'])
            if not await self.redis.setnx(busy_key, 1):
                self.logger.error('用户导入请求过于频繁，,user_id:{user_id}'.format(user_id=self.current_user['id']))
                return await self.json_response(data=msg[10010])
            await self.redis.expire(busy_key, 10)
            if await self.is_null(data, ['payment_id', 'filename']):
                self.logger.error( '请求参数缺失字段,data:{data}'.format(data=data))
                return await self.json_response(data=msg[10004])
            name, file_format = filename.rsplit('.', 1)
            uploaded_file_name = '{}_{}.{}'.format(name, random_code, file_format)
            # print('uploaded_file_name====', uploaded_file_name)
            # results = await self.extract_carana_data(self, uploaded_file_name)
            # 通过payment_id查询码商id
            payment = await self.get_result_by_condition('payment', ['partner_id'], {'id': payment_id})
            if await self.is_null(payment, ['partner_id']):
                self.logger.error('payment中缺失"partner_id"字段,请检查payment信息,payment_id:{payment_id}'.format(payment_id=payment_id))
                return await self.json_response(data=msg[10004])

            bank_sql = 'select bank.id,bank.name from bank_type bank \
                            left join payment p on p.bank_type_id = bank.id \
                            where p.id = {payment_id} limit 1'.format(payment_id=payment_id)
            bank_type_results = await self.query(bank_sql)
            if len(bank_type_results) == 0:
                self.logger.error('无法找到payment的所属银行信息,请检查payment信息,payment_id:{payment_id}'.format(payment_id=payment_id))
                return await self.json_response(data=msg[10004])

            bank_type = bank_type_results[0]
            if bank_type:
                bank_name = bank_type.get('name')
                # 调用解析方法
                handle_file_func = self.bank_handle_map.get(bank_name)
                if handle_file_func:
                    results = await handle_file_func(self, uploaded_file_name)
                    # 打印记录数
                    self.logger.info(f"Number of results processed: {len(results)}")

                    # 打印详细记录
                    self.logger.info(f"Results: {results}")
                else:
                    self.logger.error('此银行没有添加解析批量上传回执的方法： {}'.format(bank_name))
                    return await self.json_response(msg[10007])
                # if bank_name != 'CANARA BANK':
                #     self.logger.error('导入银行流水暂时仅支持CANARA BANK'.format(
                #         payment_id=payment_id))
                #     return await self.json_response(data=msg[10004])
            else:
                return await self.json_response(data=msg[10004])

            # 增加导入数据过滤，(导入数据的顺序是按时间正序排序，仅导入最新数据之后的数据)
            # 查询最新的 bank_record 记录
            last_bank_record_sql = f'select * from bank_record where payment_id={payment_id} order by id desc limit 1'.format(payment_id=payment_id)
            self.logger.info(f"查询最新 bank_record 记录: {last_bank_record_sql}")

            bank_record_results = await self.query(last_bank_record_sql)
            self.logger.info(f"查询结果: {bank_record_results}")

            # 若存在最新记录，则从最新记录后导入，若找不到最新记录则为初次导入，不处理
            if len(bank_record_results) > 0:
                last_bank_record = bank_record_results[0]
                last_bank_record_utr = last_bank_record.get('utr')
                self.logger.info(f"最新 bank_record 记录的 UTR: {last_bank_record_utr}")

                # 判断本次 results 数据中是否包含最新 UTR
                is_exits_utr = any(data['utr'] == last_bank_record_utr for data in results)
                self.logger.info(f"最新 UTR 是否在本次数据中: {is_exits_utr}")

                # 判断最新utr此次是否再次导入，若是再次导入，则仅处理此utr之后的数据
                if is_exits_utr:
                    for index, data in enumerate(results):
                        if data['utr'] == last_bank_record_utr:
                            self.logger.info(f"找到匹配的最新 UTR，位置: {index}，UTR: {data['utr']}")
                            # 从最新utr的下一条数据始处理
                            results = results[index + 1:]  # 返回最新utr之后的所有数据
                            self.logger.info(f"截取最新 UTR 之后的数据，剩余待处理数据: {results}")
                            break

            for file_data in results:
                # 定义 UTR 锁的键名和过期时间
                UTR_LOCK_PREFIX = "utr_submission_lock:"
                UTR_LOCK_EXPIRY_SECONDS = 10 # 锁的有效期，10秒

                utr = file_data['utr']
                utr_lock_key = f'{UTR_LOCK_PREFIX}{utr}'

                # 尝试一次性获取锁，失败则立即放弃
                got_utr_lock = await self.redis.setnx(utr_lock_key, 1)

                if got_utr_lock:
                    # 成功获取锁，设置过期时间
                    await self.redis.expire(utr_lock_key, UTR_LOCK_EXPIRY_SECONDS)
                    self.logger.info(f"成功获取 UTR: {utr} 的锁.")
                    
                    # 成功获取锁后，进入 try-finally 块确保锁被释放
                    try:
                        file_data['bank_name'] = bank_name
                        file_data['partner_id'] = payment['partner_id']
                        if await self.is_exits('bank_record', 'utr', file_data['utr']):
                            self.logger.error('导入bank_record异常,utr:{utr}重复'.format(utr=file_data['utr']))
                            continue
                        file_data['admin_id'] = self.current_user['id']
                        file_data['payment_id'] = payment_id

                        # 代收回调, 代付不需要回调
                        if file_data.get('amount') > 0 :
                            r = await self.success_ds(file_data)
                            
                            if r['code'] == 99 :
                                ew_code = await self.create_order_code('EW')  # 额外流水号
                                async with self.application.db.acquire() as conn:
                                    async with conn.cursor(DictCursor) as cur:
                                        if not await self.change_balance(conn, cur, 'partner', payment['partner_id'],
                                                                        -Decimal(file_data['amount']), ew_code, 0):
                                            self.logger.warning('utr:{}扣除商户余额失败'.format(file_data['utr']))
                                            await conn.rollback()
                                        else:
                                            file_data['ew_code'] = ew_code
                                            file_data['if_ew'] = '1'
                                            await conn.commit()
                            if r['code'] == 100:
                                file_data['callback'] = 1
                                file_data['order_code'] = r['order']

                        del file_data['bank_name']

                        if not await self.create_result('bank_record', file_data):
                            self.logger.error('导入bank_record异常,创建记录失败,utr:{utr}'.format(utr=file_data['utr']))
                            continue
                            
                    except Exception as e:
                        self.logger.error(f"处理 UTR:{file_data['utr']} 时发生错误: {e}", exc_info=True)
                    finally:
                        # 锁的释放逻辑已移除。锁将依赖于 10 秒后自动过期。
                        pass

        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg[10007])

        return await self.json_response(dict(code=20000, msg='导入成功'))

    # 代收确认
    async def success_ds(self, data):
        condition = 'utr'
        if "code" in data.keys() and data['code']:
            if len(data['code']) == 5:
                condition = 'auth_code'
        # 根据确认码或UTR查找订单
        sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) and 
                                date_add(time_create, interval 180 minute) > now() order by id limit 1""".format(
            condition)
        # 商户代理费率
        sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant 
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join 
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
        # 码商代理费率
        sql_select_rates_partner = """select rates from channel where code=%s"""
        # 更新系统余额
        sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
        # 更新订单
        sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,payment_id=%s,
                            utr=%s,time_success=%s,status=3,upi=%s where code=%s and status in (-1,1,2) limit 1"""

        # 根据收款资料id查询
        sql_select_payment = """select * from payment where id=%s order by id limit 1"""

        self.logger.info(f"开始处理订单回调，收到数据: {data}")

        # _order = await self.query(sql_select_order,
        #                           *(Decimal(data['amount']), data['code'] if condition != 'utr' else data['utr']))
        amount = Decimal(data['amount'])
        has_decimal = amount % 1 != 0  # 判断金额是否为小数
        rounded_amount = 0.00
        if has_decimal:
            amount_tmp = Decimal(amount)
            rounded_amount = amount_tmp.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            self.logger.info(f"[订单匹配] 金额 {amount} 含小数 {rounded_amount}，使用更严格规则匹配订单（按 payment_id + 时间）")
            sql_select_order = """
                SELECT * FROM orders_ds 
                WHERE amount=%s AND payment_id=%s AND status IN (-1,1,2) 
                AND date_add(time_create, interval 180 minute) > now() 
                ORDER BY id DESC LIMIT 1
            """
            self.logger.info(f"[订单匹配] 执行 SQL: {sql_select_order.strip()} 参数: 金额={rounded_amount} / {rounded_amount}, payment_id={data['payment_id']}")
            _order = await self.query(sql_select_order, rounded_amount, data['payment_id'])
        else:
            self.logger.info(f"[订单匹配] 金额 {amount} 为整数，使用默认规则（{condition} 匹配）")
            self.logger.info(f"[订单匹配] 执行 SQL: {sql_select_order.strip()} 参数: 金额={amount}, 匹配字段={condition}, 值={data['code'] if condition != 'utr' else data['utr']}")
            _order = await self.query(sql_select_order,
                amount, data['code'] if condition != 'utr' else data['utr'])
            
        if not _order:
            if not condition == 'utr':  # 如果查询不到，重新按utr查询
                self.logger.warning('utr:{}Not Order not found'.format(data['utr']))
                sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) and 
                                            date_add(time_create, interval 180 minute) > now() order by id limit 1""".format(
                    'utr')
                _order = await self.query(sql_select_order, *(Decimal(data['amount']), data['utr']))
            if not _order:
                self.logger.warning('utr:{}Not Order not found k2'.format(data['utr']))
                return dict(code=99, msg='Order not found')

        qr_id = data['payment_id']
        pt_id = data['partner_id']
        _payment = await self.query(sql_select_payment, qr_id)
        if not _payment:
            return dict(code=99, msg='Payment not found')
        # 使用锁，5s使用自旋锁, 防止取消的同时回调
        count_circle = 0
        while True:
            busy_key = 'order_success_busy_{code}'.format(code=_order[0]['code'])
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                break
            if count_circle >= 25:
                self.logger.warning(
                    'utr:{utr}Do not operate frequently {code}'.format(utr=data['utr'], code=_order[0]['code']))
                return dict(code=99, msg='Do not operate frequently')
            time.sleep(0.2)
            count_circle = count_circle + 1

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    amount = Decimal(data['amount'])
                    original_amount = amount  # 保存原始小数金额用于清理
                    partner_id = int(pt_id)
                    # 查找订单
                    if has_decimal:
                        self.logger.info(f"[订单匹配] 金额 {amount} 含小数，使用更严格规则匹配订单（按 payment_id + 时间）")
                        sql_select_order = """
                            SELECT * FROM orders_ds 
                            WHERE amount=%s AND payment_id=%s AND status IN (-1,1,2) 
                            AND date_add(time_create, interval 180 minute) > now() 
                            ORDER BY id DESC LIMIT 1
                        """
                        self.logger.info(f"[订单匹配] 执行 SQL: {sql_select_order.strip()} 参数: 金额={rounded_amount}, payment_id={data['payment_id']}")
                        # 执行 SQL 查询
                        result = await self.query(sql_select_order, rounded_amount, data['payment_id'])

                        if not result:
                            self.logger.warning('utr:{}Not Order not found2（小数金额）'.format(data['utr']))
                            return dict(code=99, msg='Order not found')
                        # 获取第一条记录
                        order = result[0]
                        code = order['code']
                        amount = order['original_amount'] or amount
                    else:
                        if not await cur.execute(sql_select_order,
                                                (amount, data['code'] if condition != 'utr' else data['utr'])):
                            if not condition == 'utr':  # 如果查询不到，重新按utr查询
                                sql_select_order = """select * from orders_ds where amount=%s and {}=%s and status in (-1,1,2) order by id limit 1""".format(
                                    'utr')
                                if not await cur.execute(sql_select_order, (amount, data['utr'])):
                                    self.logger.warning('utr:{}Not Order not found2'.format(data['utr']))
                                    return dict(code=99, msg='Order not found')
                            else:
                                self.logger.warning('utr:{}Not Order not found'.format(data['utr']))
                                return dict(code=99, msg='Order not found')
                        order = (await cur.fetchall())[0]
                        code = order['code']
                        amount = order['original_amount'] or amount

                    # 打印中文日志
                    self.logger.info(f"code: {code}, 原始充值金额: {amount}")

                    # 去掉小数部分（向下取整）
                    amount = amount.to_integral_value(rounding=ROUND_DOWN)

                    # 打印中文日志
                    self.logger.info(f"code: {code}, 去除小数部分后金额: {amount}")

                    # 补扣码商(非自身订单、过期订单)
                    if not order['partner_id'] == partner_id or order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0, ):
                            self.logger.warning('utr:{}Failed to deduct partner balance'.format(data['utr']))
                            return dict(code=99, msg='Failed to deduct partner balance')
                    # 非自身订单并且未过期退款给旧码商
                    if not order['partner_id'] == partner_id and not order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount, code, 0):
                            self.logger.warning('utr:{}Failed to add old partner balance'.format(data['utr']))
                            return dict(code=99, msg='Failed to add old partner balance')
                    # 增加商户余额
                    if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'],
                                                     code, 0):
                        self.logger.warning('utr:{}Failed to add merchant balance'.format(data['utr']))
                        return dict(code=99, msg='Failed to add merchant balance')
                    # 商户代理费用
                    earn_merchant = Decimal(0)
                    if order['earn_merchant'] > 0:
                        if not await cur.execute(sql_select_rates_merchant,
                                                 (order['merchant_id'], order['channel_code'])):
                            await conn.rollback()
                            self.logger.warning('utr:{}Not found merchant agent'.format(data['utr']))
                            return dict(code=99, msg='Not found merchant agent')
                        merchant_rates = (await cur.fetchall())
                        for k, v in enumerate(merchant_rates):
                            if not k == 0 and v['rate']:
                                _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                                if _amount < 0:
                                    await conn.rollback()
                                    self.logger.warning('utr:{}Merchant agent rate error'.format(data['utr']))
                                    return dict(code=99, msg='Merchant agent rate error')
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    self.logger.warning(
                                        'utr:{}Failed to add merchant agent balance'.format(data['utr']))
                                    return dict(code=99, msg='Failed to add merchant agent balance')
                                earn_merchant += _amount
                    # 增加码商佣金
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code,
                                                     3):
                        await conn.rollback()
                        self.logger.warning('utr:{}Failed to add partner balance'.format(data['utr']))
                        return dict(code=99, msg='Failed to add partner balance')

                    # 增加码商代理佣金
                    earn_partner = order['earn_partner_self']
                    if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                        self.logger.warning('utr:{}Partner rates error'.format(data['utr']))
                        return dict(code=99, msg='Partner rates error')
                    rates = (await cur.fetchall())[0]['rates'].split(',')
                    _partner_id = partner_id
                    for i in range(len(rates)):
                        partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                        if not partner['pid']:
                            break
                        _partner_id = partner['pid']
                        _amount = amount * Decimal(rates[i])
                        if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                            self.logger.warning('utr:{}Failed to add partner agent balance'.format(data['utr']))
                            return dict(code=99, msg='Failed to add partner agent balance')
                        earn_partner += _amount
                    # 系统盈利
                    earn_system = order['poundage'] - earn_merchant - earn_partner
                    if earn_system < 0:
                        await conn.rollback()
                        self.logger.warning('utr:{}Rate exception'.format(data['utr']))
                        return dict(code=99, msg='Rate exception')
                    # 修改卡系统余额
                    if not await cur.execute(sql_update_payment, (amount, qr_id)):
                        await conn.rollback()
                        self.logger.warning('utr:{}Update payment system balance error'.format(data['utr']))
                        return dict(code=99, msg='Update payment system balance error')
                    # 修改订单状态
                    time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    self.logger.info(f"执行更新查询: {sql_update_order}, 参数: 商户盈利: {earn_merchant}, 码商盈利: {earn_partner}, 系统盈利: {earn_system}, 码商ID: {partner_id}, 支付ID: {qr_id}, UTR: {data['utr']}, 当前时间: {time_now}, 支付UPI: {_payment[0]['upi']}, 订单号: {code}")
                    rows_affected = await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id,
                                                                qr_id, data['utr'], time_now, _payment[0]['upi'],
                                                                code))
                    if not rows_affected:
                        await conn.rollback()
                        self.logger.warning('utr:{}Update order error'.format(data['utr']))
                        self.logger.warning(f"UTR: {data['utr']}，订单更新失败，影响行数: {rows_affected}")
                        return dict(code=99, msg='Update order error')
                    self.logger.info('更新订单状态: %s, UTR: %s' % (cur._last_executed, data['utr']))
                    self.logger.info(f"UTR: {data['utr']}，订单更新成功，影响行数: {rows_affected}")
                except Exception as e:
                    self.logger.warning('确认订单失败, code={code}, utr={utr}, 异常={e}'.format(code=code, utr=data['utr'], e=e))
                    await conn.rollback()
                    return dict(code=99, msg='Order exception')
                else:
                    await conn.commit()
                    self.logger.info(f"事务提交成功，UTR: {data['utr']}")
                    """
                    成功回调后的清理函数
                    在 success_ds 函数中调用
                    """
                    try:
                        amount = original_amount
                        amount_key = f'decimal_amount:{amount:.2f}'
                        cleanup_key = f'decimal_cleanup:{amount:.2f}'
                        
                        # 从 List 中删除成功的 payment_id
                        removed_count = await self.redis.lrem(amount_key, 1, qr_id)
                        if removed_count > 0:
                            self.logger.info(f'成功回调后清理: 从 {amount_key} 中删除 {qr_id}')
                        
                        # 从 Hash 中删除对应记录（使用payment_id+金额作为释放时间控制键）
                        await self.redis.hdel(cleanup_key, qr_id)
                        release_key = f"{payment_id}:{amount:.2f}"
                        await self.redis.hdel('payment_release_time', release_key)
                        
                        self.logger.info(f'成功回调清理完成: payment_id={qr_id}, amount={amount}')
                        
                    except Exception as e:
                        self.logger.exception(f'成功回调清理失败: {e}')
                    # 加入回调
                    publish_result = await self.redis.publish('order_notify', code)
                    self.logger.info('订单通知已发布到 Redis，订单号: %s, UTR: %s, 发布结果: %s' % (code, data['utr'], publish_result))
                    return dict(code=100, msg='Callback Success:{}'.format(code), order=code)

# 创建转账订单
class createTransfer(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['partner_id', 'amount', 'to_partner_id']):
            return await self.json_response(data=msg[10004])
        if data['partner_id'] == data['to_partner_id']:
            return await self.json_response(data=msg[10004])
        amount = Decimal(data['amount'])
        partner = await self.get_result_by_condition('partner', ['hash_trade'], {'id': data["partner_id"], 'status': 1})
        to_partner = await self.get_result_by_condition('partner', ['hash_trade'], {'id': data['to_partner_id']})
        if not partner:
            self.logger.warning("创建转账，码商 {partner} 不存在,操作人 {admin}".format(partner=data["partner_id"], admin=self.current_user['id']))
            return await self.json_response(msg[10034])
        if not to_partner:
            self.logger.warning("创建转账，接受码商 {partner} 不存在,操作人 {admin}".format(partner=data['to_partner_id'], admin=self.current_user['id']))
            return await self.json_response(msg[10034])
        code = await self.create_order_code('Z')
        remark = str(self.current_user['id']) + '管理操作：' + str(data['partner_id']) + " ：转账至" + str(data['to_partner_id']) + " 附：" + data['remark']
        data_new = dict(code=code, partner_id=data['partner_id'], to_partner_id=data['to_partner_id'], amount=amount, admin_id=self.current_user['id'], remark=remark)
        # 先预扣码商资金
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    k, p, v = await self.dict_to_kv(data_new)
                    sql = "insert into {table} ({keys}) values ({vals})".format(table='transfer', keys=k, vals=p)
                    if not await cur.execute(sql, (*v,)):
                        await conn.rollback()
                        self.logger.warning('创建转账异常={code}, 操作人 {admin}'.format(code=code, admin=self.current_user['id']))
                        return await self.json_response(data=msg[10007])
                    if not await self.change_balance(conn, cur, 'partner', data_new['partner_id'], -data_new['amount'], code, 8, "转账至：" + str(data['to_partner_id'])):
                        self.logger.warning('创建转账异常={code}, 余额变动错误, 操作人 {admin}'.format(code=code, admin=self.current_user['id']))
                        await conn.rollback()
                        return await self.json_response(msg[10007])
                except Exception as e:
                    self.logger.warning('创建转账异常={code},非法数据={e}'.format(code=code, e=e))
                    await conn.rollback()
                    return await self.json_response(msg[10007])
                else:
                    await conn.commit()
                    self.logger.warning('创建转账成功={code}, {note}'.format(code=code, note=remark))

        result = dict(code=20000, msg='添加成功')
        return await self.json_response(result)

# 获取码商转账订单
class getTransfer(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)

        condition, time_create_between = await self.split_between_condition(data['serchData'], 'time_create')
        condition, time_success_between = await self.split_between_condition(condition, 'time_success')
        between = None
        if time_create_between:
            between = time_create_between
        if not between:
            between = time_success_between

        if not condition or not condition['code'] and not between:
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}

        keys_count = ['amount', 'status']
        data_r, total, count = await self.get_result('transfer', ['*'], keys_count, condition, between, data['size'], data['page'])
        count_r = {'failOrder': 0, 'successOrder': 0, 'processing': 0, 'amount': decimal.Decimal(0), 'processing_amount': decimal.Decimal(0)}
        for i in count:
            if i['status'] == 2:
                count_r['successOrder'] += 1
                count_r['amount'] += i['amount']
            elif i['status'] == -1:
                count_r['failOrder'] += 1
            else:
                count_r['processing'] += 1
                count_r['processing_amount'] += i['amount']
        result = dict(code=20000, data=data_r, total=total, count=count_r, msg='获取成功')
        return await self.json_response(result)

# 处理码商转账订单
class handleTransfer(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        code = data['code']
        del data['code']

        # 获取锁，10秒内锁定
        code_lock_key = "handleTransfer_" + code
        code_lock = await self.redis.setnx(code_lock_key, 1)
        if not code_lock:
            return await self.json_response(msg[10032])
        await self.redis.expire(code_lock_key, 10)

        order = await self.get_result_by_condition('transfer', ['code', 'amount', 'status', 'partner_id', 'to_partner_id'], {'code': code, 'status': 1})
        if not order:
            return await self.json_response(msg[10032], code_lock_key)

        # 驳回
        if data['status'] == -1:
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], order['amount'], code, 8, "驳回转账"):
                            self.logger.warning('转账驳回异常={code}, 余额变动错误'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                        if not await self.update_result('transfer', {'status': -1}, {'code': code}):
                            self.logger.warning('转账驳回异常={code}, 更新订单出错'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                    except Exception as e:
                        self.logger.warning('转账驳回异常={code},非法数据={e}'.format(code=code, e=e))
                        await conn.rollback()
                        return await self.json_response(msg[10007], code_lock_key)
                    else:
                        await conn.commit()
                        self.logger.info('码商转账，驳回成功{code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
        # 确认
        if data['status'] == 2:
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        if not await self.change_balance(conn, cur, 'partner', order['to_partner_id'], order['amount'], code, 8, "转账来自：" + str(order['partner_id'])):
                            self.logger.warning('转账确认异常={code}, 余额变动错误'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                        if not await self.update_result('transfer', {'status': 2, 'time_success': datetime.now()}, {'code': code}):
                            self.logger.warning('转账确认异常={code}, 更新订单出错'.format(code=code))
                            await conn.rollback()
                            return await self.json_response(msg[10007], code_lock_key)
                    except Exception as e:
                        self.logger.warning('转账确认异常={code},非法数据={e}'.format(code=code, e=e))
                        await conn.rollback()
                        return await self.json_response(msg[10007], code_lock_key)
                    else:
                        await conn.commit()
                        self.logger.info('码商转账，确认成功{code}, 操作人{admin}'.format(code=code, admin=self.current_user['id']))
        result = dict(code=20000, msg='成功')
        return await self.json_response(result, code_lock_key)


# 重置下线
class resettingPayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        user_id = self.current_user['id']
        if await self.is_null(data, ['id']):
            self.logger.info('管理员id:{id},收款资料重置检查id为空:{data}'.format(id=user_id,data=json.dumps(data)))
            return await self.json_response(msg[10006])
         # 获取通道信息
        payment = await self.get_result_by_condition('payment', ['channel', 'bank_type', 'bank_type_id'], {'id': data['id']})
        if payment is None or 'channel' not in payment:
            self.logger.error(f'管理员id:{user_id}, 获取通道信息失败: {data}')
            return await self.json_response(msg[10014])

        # 将所有通道存储到 self.qr_channels 列表中
        qr_channels = payment['channel'].split(',')
        if is_easypaisa_payment(payment):
            await self.execute(easypaisa_reset_account_fields_sql(), data['id'])
            reset_result = await reset_easypaisa_redis_state(self.redis, data['id'], qr_channels)
            self.logger.info(f"管理员id:{user_id}, EasyPaisa重置采集队列完成:{reset_result}")
        elif is_jazzcash_payment(payment):
            reset_result = await reset_wallet_job_queue(self.redis, 'jazzcash', data['id'])
            self.logger.info(f"管理员id:{user_id}, JazzCash重置采集队列完成:{reset_result}")
        result = dict(code=20000, msg='重置成功')
        return await self.json_response(result)

# 批量收款资料下线
class batchDisablePayment(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        user_id = self.current_user['id']
        if await self.is_null(data, ['id']):
            self.logger.info('管理员id:{id},收款资料批量禁用检查bank id为空:{data}'.format(id=user_id, data=json.dumps(data)))
            return await self.json_response(msg[10006])
        payments = await self.get_results_by_condition('payment', ['id','status'], {'bank_type': data['id']})
        if not payments:
            self.logger.info('管理员id:{id},收款资料批量禁用查询payment没有bank_type为:{data}的'.format(id=user_id, data=json.dumps(data['id'])))
            return await self.json_response(data=msg[10004])
        ids = []
        for payment in payments:
            ids.append(payment['id'])
        sql_update = batch_disable_payment_update_sql(len(ids))
        if not await self.execute(sql_update, *ids):
            return await self.json_response(msg[10007])
        sql_update = """update bank_type set status=0 where id = {id} """.format(
            id=data['id'])
        await self.execute(sql_update)
        result = dict(code=20000, msg='批量禁用成功')
        return await self.json_response(result)

# 银行管理修改状态
class updateBankTypeStatus(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10007])
        if 'status' in data.keys():
            if not await self.update_result('bank_type', data, {'id': data['id']}):
                return await self.json_response(msg[10007])

        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)

# 银行管理修改状态Setting
class updateBankTypeStatusSetting(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10007])
        if 'status' in data.keys():
            if not await self.update_result('bank_type_setting', data, {'id': data['id']}):
                return await self.json_response(msg[10007])

            # 查询原始记录是否存在
            original = await self.get_result_by_condition('bank_type_setting', {"*"}, {"id": data['id']})
            if not original:
                return await self.json_response(msg[10007])

            # 处理更新后逻辑
            status = data['status']
            # 从原始记录中取值
            bank_id = original['bank_id']
            max_count = original['max_count']
            max_sec = original['max_sec']

            redis_max_count_key = f"send_orders_max_count_{bank_id}"
            redis_max_sec_key = f"send_orders_max_sec_{bank_id}"

            if status == 0:
                await self.redis.delete(redis_max_count_key)
                self.logger.info(f"Deleted Redis key: {redis_max_count_key}")

                await self.redis.delete(redis_max_sec_key)
                self.logger.info(f"Deleted Redis key: {redis_max_sec_key}")

            elif status == 1:
                await self.redis.set(redis_max_count_key, max_count)
                self.logger.info(f"Set Redis key: {redis_max_count_key} = {max_count}")

                await self.redis.set(redis_max_sec_key, max_sec)
                self.logger.info(f"Set Redis key: {redis_max_sec_key} = {max_sec}")

        result = dict(code=20000, msg='操作成功')
        return await self.json_response(result)

# 银行管理查询
class getBankType(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_accept')
        whereSql = ''
        if 'status' in condition.keys() and condition['status'] != '':
            whereSql = 'where bt.status = {value} '.format(value=condition['status'])
        limit = "limit {size} offset {page}".format(size=data['size'],page=(data['page'] - 1)* data['size'])
        if not between:
            between = {'key': 'time_accept', 'start': datetime.now() - timedelta(hours=2), 'end': datetime.now()}
        bt_key, bt_start, bt_end = await self.dict_to_between(between)
        bt_key = " and {bt_key}".format(bt_key=bt_key)
        orders = None
        if 'online' in condition.keys() and condition['online'] != '':
            if condition['online'] == 1:
                orders = 'orders_ds'
            if condition['online'] == 2:
                orders = 'orders_df'
        data_r = []
        if orders:
            sql = """SELECT bt.id,bt.name,bt.url,bt.type,bt.status, COUNT(DISTINCT od.payment_id) as payment_count_in_orders_ds FROM bank_type bt LEFT JOIN payment p ON bt.id = p.bank_type LEFT JOIN {orders} od ON p.id = od.payment_id and od.`status` > 0 {bt_key} {whereSql} GROUP BY bt.id order by payment_count_in_orders_ds desc {limit}""".format(orders=orders,bt_key=bt_key,whereSql=whereSql,limit=limit)
            data_r = await self.query(sql, bt_start, bt_end)
        else:
            sql = """SELECT bt.id,bt.name,bt.url,bt.type,bt.status FROM bank_type bt {whereSql} {limit}""".format(whereSql=whereSql,limit=limit)
            data_r = await self.query(sql)
        sql_count = """select count(id) as count from bank_type """
        newBankType = await self.query(sql_count)
        result = dict(code=20000, data=data_r, total=newBankType[0]['count'],newBankType=newBankType[0]['count'], msg='获取成功')
        return await self.json_response(result)
    
# 银行管理查询Setting
class getBankTypeSetting(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])

        condition = data.get('serchData', {})
        where_clauses = []
        params = []

        # 状态筛选
        if 'status' in condition and condition['status'] != '':
            where_clauses.append("status = %s")
            params.append(condition['status'])

        # name 模糊查询
        if 'bankName' in condition and condition['bankName'].strip():
            where_clauses.append("name LIKE %s")
            params.append(f"%{condition['bankName'].strip()}%")

        # 拼接 WHERE 子句
        where_sql = ' '
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # 分页
        limit = "LIMIT %s OFFSET %s"
        params.append(data['size'])
        params.append((data['page'] - 1) * data['size'])

        # SQL 查询（带 JOIN）
        sql = f"""
            SELECT *
            FROM bank_type_setting
            {where_sql}
            ORDER BY id DESC
            {limit}
        """

        # 查询数据
        data_r = await self.query(sql, *params)
        sql_count = """select count(id) as count from bank_type_setting """
        newBankType = await self.query(sql_count)
        # 构建返回结果
        result = {'code': 20000,'data': data_r, 'total': newBankType[0]['count'], 'msg': '获取成功'}
        return await self.json_response(result)


# 银行新增
class addBankType(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['url', 'name', 'url', 'type']):
            return await self.json_response(data=msg[10004])
        await self.create_result('bank_type', data)
        result = dict(code=20000, msg='新增成功')
        return await self.json_response(result)

# 银行新增Setting
class addBankTypeSetting(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['bank_id', 'max_count', 'max_sec', 'status']):
            return await self.json_response(data=msg[10004])
        bank_id = data['bank_id']
        max_count = data['max_count']
        max_sec = data['max_sec']
        
        sql_check = "SELECT name, type FROM bank_type_setting WHERE bank_id = %s"
        result = await self.query(sql_check, bank_id)
        if result:
            self.logger.info(f'所选银行数据已经存在: {data}')
            return await self.json_response(data=msg[10008])
        
        # 校验 bank_type 是否存在 且 type != 0
        sql_check = "SELECT name, type FROM bank_type WHERE id = %s"
        result = await self.query(sql_check, bank_id)
        if not result:
            self.logger.info(f'所选银行不存在: {data}')
            return await self.json_response(data=msg[10237])
        if result[0]['type'] == 0:
            self.logger.info(f'内部银行不能设置: {data}')
            return await self.json_response(data=msg[10237])

        # 把 bank_type.name 写入 data.name
        data['name'] = result[0]['name']
        data['type'] = result[0]['type']
        data.pop('id', None)
        
        # 更新数据库
        await self.create_result('bank_type_setting', data)

        # # 分开存储
        # await self.redis.set(f"send_orders_max_count_{bank_id}", max_count)
        # await self.redis.set(f"send_orders_max_sec_{bank_id}", max_sec)

        status = data['status']

        redis_max_count_key = f"send_orders_max_count_{bank_id}"
        redis_max_sec_key = f"send_orders_max_sec_{bank_id}"

        if status == 0:
            await self.redis.delete(redis_max_count_key)
            self.logger.info(f"Deleted Redis key: {redis_max_count_key}")
            
            await self.redis.delete(redis_max_sec_key)
            self.logger.info(f"Deleted Redis key: {redis_max_sec_key}")

        elif status == 1:
            await self.redis.set(redis_max_count_key, max_count)
            self.logger.info(f"Set Redis key: {redis_max_count_key} = {max_count}")
            
            await self.redis.set(redis_max_sec_key, max_sec)
            self.logger.info(f"Set Redis key: {redis_max_sec_key} = {max_sec}")

        result = dict(code=20000, msg='新增成功')
        return await self.json_response(result)

# 银行更新
class updateBankType(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['url', 'name', 'url', 'type']):
            return await self.json_response(data=msg[10004])
        await self.update_result('bank_type', data, {'id': data['id']})
        result = dict(code=20000, msg='修改成功')
        return await self.json_response(result)

# 银行更新Setting
class updateBankTypeSetting(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['bank_id', 'id', 'max_count', 'max_sec', 'status']):
            return await self.json_response(data=msg[10004])

        bank_id = data['bank_id']
        max_count = data['max_count']
        max_sec = data['max_sec']
        record_id = data['id']

        # 获取当前记录的旧 bank_id
        sql_old = "SELECT bank_id FROM bank_type_setting WHERE id = %s"
        old_record = await self.query(sql_old, record_id)

        if old_record:
            old_bank_id = old_record[0]['bank_id']
            redis_old_count_key = f"send_orders_max_count_{old_bank_id}"
            redis_old_sec_key = f"send_orders_max_sec_{old_bank_id}"

            #  删除旧 Redis key
            await self.redis.delete(redis_old_count_key)
            await self.redis.delete(redis_old_sec_key)
            self.logger.info(f"Deleted OLD Redis keys for bank_id {old_bank_id}: {redis_old_count_key}, {redis_old_sec_key}")

        sql_check = "SELECT name, type FROM bank_type_setting WHERE bank_id = %s AND id != %s"
        result = await self.query(sql_check, bank_id, record_id)
        self.logger.info(f'当前数据记录数==============={len(result)}')
        # 判断返回的记录数量是否大于 1
        if result:
            self.logger.info(f'所选银行数据已存在多条记录，不允许编辑: {result}')
            return await self.json_response(data=msg[10008])

        # 校验 bank_type 是否存在 且 type != 0
        sql_check = "SELECT name, type FROM bank_type WHERE id = %s"
        result = await self.query(sql_check, bank_id)
        if not result:
            self.logger.info(f'所选银行不存在: {data}')
            return await self.json_response(data=msg[10237])
        if result[0]['type'] == 0:
            self.logger.info(f'内部银行不能设置: {data}')
            return await self.json_response(data=msg[10237])

        # 把 bank_type.name 写入 data.name
        data['name'] = result[0]['name']
        data['type'] = result[0]['type']

        # 更新数据库
        await self.update_result('bank_type_setting', data, {'id': data['id']})

        status = data['status']

        redis_max_count_key = f"send_orders_max_count_{bank_id}"
        redis_max_sec_key = f"send_orders_max_sec_{bank_id}"

        if status == 0:
            await self.redis.delete(redis_max_count_key)
            self.logger.info(f"Deleted Redis key: {redis_max_count_key}")
            
            await self.redis.delete(redis_max_sec_key)
            self.logger.info(f"Deleted Redis key: {redis_max_sec_key}")

        elif status == 1:
            await self.redis.set(redis_max_count_key, max_count)
            self.logger.info(f"Set Redis key: {redis_max_count_key} = {max_count}")
            
            await self.redis.set(redis_max_sec_key, max_sec)
            self.logger.info(f"Set Redis key: {redis_max_sec_key} = {max_sec}")


        result = dict(code=20000, msg='修改成功')
        return await self.json_response(result)


# 银行删除
class deleteBankType(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['id']):
            return await self.json_response(data=msg[10006])
        condition = {'id': data['id']}
        if data['is_del']:  # 永久删除
            if not await self.delete_result('bank_type', condition):
                return await self.json_response(msg[10006])
        result = dict(code=20000, msg='删除成功')
        return await self.json_response(result)

# 银行排名
class getBankRank(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        userId = self.current_user['id']
        getBankRankUserId = 'getBankRank_{userId}'.format(userId=userId)
        if await self.redis.get(getBankRankUserId):
            return await self.json_response(data=msg[10042])
        await self.redis.set(getBankRankUserId, 1, 10)
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'time_create')
        if not between:
            between = {'key': 'time_create', 'start': datetime.today().date(), 'end': datetime.now()}
        sql = """SELECT bt.name,COUNT(o.id) AS count, SUM(IF(o.amount > 0, o.amount, 0)) AS amount,COUNT(IF(o.status > 2, 1, NULL)) AS success_count,SUM(IF(o.status > 2, o.amount, 0)) AS success_amount,CAST(COUNT(IF(o.status > 2, 1, NULL)) / IF(COUNT(o.id) = 0, 1, COUNT(o.id)) * 100 AS DECIMAL(14,0)) AS rate FROM payment AS p LEFT JOIN bank_type AS bt ON bt.id = p.bank_type LEFT JOIN orders_ds AS o ON o.payment_id = p.id and o.time_create between %s and %s"""
        bt_key, bt_start, bt_end = await self.dict_to_between(between)
        values = [bt_start, bt_end]
        if condition and condition['channel_code']:
            sql += ' and o.channel_code=%s'
            values += [condition['channel_code']]
        sql += ' group by p.bank_type'
        if data['order_field']:
            sql += ' order by {order_field} '.format(order_field=data['order_field'])
            if data['sort']:
                sql += data['sort']
        sql += ' limit %s offset %s'.format()
        values += [data['size'], (data['page'] - 1) * data['size']]
        data_r = await self.query(sql, *values)
        total = await self.query('SELECT COUNT(DISTINCT bank_type) AS total FROM payment')
        result = dict(code=20000, data=data_r, total=total[0]['total'], msg='获取成功')
        return await self.json_response(result)

# 取消限制派单
class cancelLimit(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        try:
            if await self.is_null(data, ['id']):
                return await self.json_response(data=msg[10006])
            hours = 2 * 3600
            if 'hours' in data.keys() and data['hours']:
                hours = int(decimal.Decimal(data['hours']) * 3600)
            if hours == 0:
                await self.redis.delete('cancel_send_orders_limit_{id}'.format(id=data['id']))
            else:
                await self.redis.delete('send_orders_ds_limit_{id}'.format(id=data['id']))
                await self.redis.set('cancel_send_orders_limit_{id}'.format(id=data['id']), hours, hours)
            result = dict(code=20000, msg='更新成功')
        except Exception as e:
            result = dict(code=1, message='更新失败')
            self.logger.warning('cancelLimit异常={id},非法数据={e}'.format(id=data['id'], e=e))
        return await self.json_response(result)


# 获取短信列表
class GetSms(BaseHandler):
    @tornado.web.authenticated
    async def post(self):
        data = json.loads(self.request.body)
        if await self.is_null(data, ['size', 'page']):
            return await self.json_response(data=msg[10007])
        condition, between = await self.split_between_condition(data['serchData'], 'created')
        data_r, total = await self.get_result('sms_record', ['*'], None, condition, between, data['size'],
                                              data['page'])
        result = dict(code=20000, data=data_r, total=total, msg='获取成功')
        return await self.json_response(result)
