import asyncio
import hashlib
import json
import datetime
import logging
import math
import random
import re
import time
import uuid
import bcrypt
import pyotp
import requests
import sys
import sysconfig

import os

import simplejson
import tornado.web
import traceback

from decimal import Decimal
from aiomysql import DictCursor
from tornado.options import define, options
from application.client_ip import resolve_client_ip, sanitize_request_body
from application.message import msg
from config import get_config

conf = get_config()
# 定义全局 TRACE_ID
define('TRACE_ID', default=None, help='trace id')
define('RQ_ID', default=0, help='request id')


class TraceIdFilter(logging.Filter):
    # 打印用法
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def filter(self, record):
        record.trace_id = options.TRACE_ID

        options.RQ_ID += 1
        record.id = options.RQ_ID
        return True

class BaseHandler(tornado.web.RequestHandler):
    def initialize(self):
        options.RQ_ID = 0
        options.TRACE_ID = str(uuid.uuid4().hex)

    # 预处理
    async def prepare(self):
        self.redis = self.application.redis
        self.logger = self.application.logger
        if not self.logger.filters:
            self.logger.addFilter(TraceIdFilter())
        # 检查IP (开发环境暂时注释)
        if not await self.check_ip():
            return self.send_error(403, reason='ip:{ip} 禁止登录'.format(ip=await self.get_ip()))
        try:
            if self.request.body and not self.request.files:
                data = json.loads(self.request.body)
                if not self.check_arguments(data):
                    return self.send_error(419)
        except Exception as e:
            self.logger.exception(e)
            return self.send_error(419)

        # 如果已登陆，则获取信息并检查权限
        try:
            user_id = self.get_secure_cookie("user")
            if user_id:
                sql = """select a.id as id, a.name as name, a.parent_id as parent_id, r.id as role_id, r.name as role, r.encryption as encryption,permissions from admin a inner join roles r 
                            on r.id=a.role where a.id=%s"""
                value = [user_id]
                user = (await self.query(sql, *value))[0]
                self.current_user = user
                # 检查权限
                if not await self.check_auth(user['permissions']):
                    return self.send_error(403, reason='该账号无此权限，请联系主管')
            else:
                # 未登录或已过期
                self.current_user = None
        except Exception as e:
            self.logger.exception(e)
            self.clear_cookie('id')
            return self.send_error(403)

    # 获取IP
    async def get_ip(self):
        return resolve_client_ip(self.request.headers, self.request.remote_ip)

    # 获取IP
    def _get_ip(self):
        return resolve_client_ip(self.request.headers, self.request.remote_ip)

    # 请求日志
    def _request_summary(self):
        user_id = self.current_user['id'] if self.current_user else 0
        _request = sanitize_request_body(self.request.body, has_files=bool(self.request.files))
        return "%s %s (%s@%s) %s" % (
            self.request.method,
            self.request.uri,
            str(user_id),
            self._get_ip(),
            _request
        )

    # 检查IP是否在白名单
    async def check_ip(self):
        ip = await self.get_ip()
        r = await self.get_cache_result('sys_info', ['sys_ip_w'], {"id": 1})
        if r['sys_ip_w'] and ip not in r['sys_ip_w'].split(','):
            return False
        return True

    # 检查非法字符
    def check_arguments(self, data):
        pattern = r"[~`!@#$%^&*()_+-={}\[\]\\|:;\"',<>?/]"
        for v in data:
            if isinstance(v, dict) or isinstance(v, list):  # 如果是json或者数组则继续
                self.check_arguments(v)
            else:
                if re.search(v, pattern):
                    self.logger.warning('非法参数,url={url},非法数据={v}'.format(url=self.request.path, v=v))
                    return False
        return True

    # 检查权限
    async def check_auth(self, permissions):
        permissionid = await self.get_result_by_condition('permissions', ['id'],{"path": str(self.request.path), 'status': 1})
        if not permissionid or str(permissionid['id']) in permissions:
            return True
        return False

    # 设置cookie值
    async def set_my_cookie(self, k, v):
        self.set_secure_cookie(k, v, expires_days=1)
    
    # 👇 可共用的告警格式构建函数（建议单独放 utilities 模块）
    async def build_sql_alert_message(self, sql, args, cost_ms, rowcount=0, line_info='', level='严重预警', name='【ospay】 慢查询告警'):
        # 示例使用
        bot_token = conf['BOT_TOKEN']
        chat_id = conf['GROUP_ID']
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        message = {
            "bot_token": bot_token,
            "chat_id": chat_id,
            "text": f"""⚠️ *{name}*
            *告警等级:* {level}
            *告警时间:* {now}
            *执行用户:* {self.get_secure_cookie("user") or 'unknown'}
            *调用位置:* `{line_info}`
            *查询耗时:* {cost_ms:.2f} ms
            *影响行数:* {rowcount}
            *args:* `{args}`
            *trace_id:* `{options.TRACE_ID or '-'}`
            *接口名称:* `{self.__class__.__name__}`
            *查询语句:*
            ```sql
            {sql}
            ```""",
        }
        
        # 👇 推送到 Redis 队列
        redis_key = "slow_query_alerts"
        await self.redis.publish(redis_key, json.dumps(message))
        return message

    # SQL 查询
    async def query(self, sql, *args):
        # 获取完整调用堆栈
        stack = traceback.extract_stack()
        line_info = self.get_business_stack_info()
        start = time.time()
        rowcount = 0

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    if not await cur.execute(sql, args):
                        await conn.rollback()
                        return []
                    rowcount = cur.rowcount
                    self._last_sql = cur._last_executed
                    r = await cur.fetchall()
                except Exception as e:
                    self.logger.exception(e)
                    # self.logger.warning(f"SQL Error: {self._last_sql}")
                    
                    stack_trace = traceback.format_exc()
                    error_info = {
                        'error_type': type(e).__name__,
                        'error_message': str(e),
                        'stack_trace': stack_trace,
                    }
                    self.logger.warning(f"sQL Error: {self._last_sql}, Exception: {json.dumps(error_info, indent=4)}")
                    await conn.rollback()
                    return []
                else:
                    await conn.commit()
                    return r
                finally:
                    cost_ms = (time.time() - start) * 1000
                    if cost_ms > conf['SQL_TIMEOUT']:
                        await self.build_sql_alert_message(
                            sql, args, cost_ms, rowcount, line_info
                        )

    def get_business_stack_info(self):
        """
        获取当前调用栈中最接近的业务代码位置（排除标准库、第三方库、Tornado等）。
        返回格式示例：'/path/to/file.py:123 → some_code_line'
        """
        stack = traceback.extract_stack()
        line_info = "未知调用位置"

        stdlib_path = sysconfig.get_paths()['stdlib'].lower()

        for frame in reversed(stack):
            filepath = os.path.normpath(frame.filename).lower()
            filename = os.path.basename(filepath)

            # 排除规则
            if (
                'site-packages' in filepath or
                'tornado' in filepath or
                filename == 'base.py' or
                filepath.startswith(stdlib_path)
            ):
                continue

            # 命中业务代码帧
            code_line = frame.line.strip() if frame.line else ''
            line_info = f"{frame.filename}:{frame.lineno} → {code_line}"
            break

        return line_info
    
    # 组装查询key,进行分割
    async def list_keys(self, data):
        return ','.join(data)

    # 区分between 和condition
    @staticmethod
    async def split_between_condition(data, key):
        if key in data and data[key]:
            between = {'key': key, 'start': data[key][0], 'end': data[key][1]}
            del data[key]
            return data, between
        return data, None

    # 组装查询，返回between
    async def dict_to_between(self, data):
        key = " {key} between %s and %s".format(key=data['key'])
        start = data['start']
        end = data['end']
        return key, start, end

    # 组装查询key,返回 k1,k2,k3...  %s,%s,%s... 和 [val1,val2,val3...]
    async def dict_to_kv(self, data):
        d = {k: data[k] for k in sorted(data)}
        sql_key = ', '.join(k for k in d.keys())
        sql_place = ', '.join(["%s"] * len(data))
        sql_val = d.values()

        return sql_key, sql_place, sql_val

    # 组装查询条件格式，返回 k1=%s and k2=%s 和 [val1, val2]
    async def dict_to_and_bak(self, data):
        d = {k: data[k] for k in sorted(data)}
        tmp_list = []
        for i in d.keys():
            tmp_list.append("{key}=%s".format(key=i))
        keys = ' and '.join(tmp_list)
        vals = d.values()
        return keys, vals
    
    async def dict_to_and(self, data):
        d = {k: data[k] for k in sorted(data)}
        tmp_list = []
        vals = []

        for k, v in d.items():
            if " LIKE" in k:  # 处理 LIKE 语句
                tmp_list.append(f"{k} %s")
            else:
                tmp_list.append(f"{k}=%s")
            vals.append(v)

        keys = ' and '.join(tmp_list)
        return keys, vals


    # 组装查询条件格式，返回 k1=%s, k2=%s 和 [val1, val2]
    async def dict_to_equal(self, data):
        d = {k: data[k] for k in sorted(data)}
        tmp_list = []
        for i in d.keys():
            tmp_list.append("{key}=%s".format(key=i))
        sql_key = ', '.join(tmp_list)
        sql_val = d.values()
        return sql_key, sql_val

    # SQL 执行
    async def execute(self, sql, *args):
        """SQL 执行"""
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    if not await cur.execute(sql, args):
                        await conn.rollback()
                        return False
                    self._last_sql = cur._last_executed
                except Exception as e:
                    self.logger.exception(e)
                    await conn.rollback()
                    return False
                else:
                    await conn.commit()
                    return True

    # 分页查询
    async def get_result(self, table, keys, keys_count=None, condition=None, between=None, limit=None, offset=None,
                         order_by='desc', order_field='id', other_str=None, other_value=[], online_str=None, online_value=[]):
        sql_part = ''
        values = []

        if condition:
            for k in list(condition.keys()):
                if not condition[k] and condition[k] != 0:
                    condition.pop(k)
        if condition or between:
            sql_part += ' where '
        if condition:
            where_key, where_val = await self.dict_to_and(condition)
            sql_part += ' {keys} '.format(keys=where_key)
            values += where_val
        if between:
            bt_key, bt_start, bt_end = await self.dict_to_between(between)
            if condition:
                sql_part += " and " + bt_key
            else:
                sql_part += bt_key
            values += [bt_start, bt_end]

        if other_str:
            if sql_part:
                sql_part += ' and ' + other_str
            else:
                sql_part += ' where ' + other_str
            if other_value:
                values.extend(other_value)
        if online_str:
            if sql_part:
                sql_part += ' and ' + online_str
            else:
                sql_part += ' where ' + online_str
            if online_value:
                values.extend(online_value)

        # 获取调用位置
        line_info = self.get_business_stack_info()
        
        # 获取所有数据总数
        sql = "select count(id) from {table} ".format(table=table)
        sql += sql_part
        start = time.time()
        t = await self.query(sql, *values)
        duration = (time.time() - start) * 1000
        if duration > conf['SQL_TIMEOUT']:
            await self.build_sql_alert_message(sql, values, duration, 0, line_info)
        if t:
            t = t[0]['count(id)']
        else:
            t = 0
        # 获取所有数据的指定key数据
        c = []
        if keys_count:
            sql = "select {keys} from {table} ".format(keys=await self.list_keys(keys_count), table=table)
            sql += sql_part
            start = time.time()
            c = await self.query(sql, *values)
            duration = (time.time() - start) * 1000
            if duration > conf['SQL_TIMEOUT']:
                await self.build_sql_alert_message(sql, values, duration, len(c), line_info)

        # 获取分页数据
        sql = "select {keys} from {table}  where id in (select id from {table} ".format(keys=await self.list_keys(keys),
                                                                                        table=table)
        order_by = ') order by {order_field} {sort} '.format(order_field=order_field, sort=order_by)
        sql += sql_part + order_by
        if limit and offset > -1:
            sql += 'limit %s offset %s'
            values += [limit, (offset - 1) * limit]
        start = time.time()
        r = await self.query(sql, *values)
        duration = (time.time() - start) * 1000
        if duration > conf['SQL_TIMEOUT']:
            await self.build_sql_alert_message(sql, values, duration, len(r) if r else 0, line_info)

        if keys_count:
            return r, t, c
        if r:
            return r, t
        return [], 0

    # get_result方法优化后的方法 用户获取分页数据
    async def get_page(self, table, keys, keys_count=None, condition=None, betweens=None, limit=None, offset=None,
                         order_by='desc', order_field='id', other_str=None, other_value=[], online_str=None, online_value=[]):
        sql_part = ''
        values = []

        if condition:
            for k in list(condition.keys()):
                if not condition[k] and condition[k] != 0:
                    condition.pop(k)
        if condition:
            where_key, where_val = await self.dict_to_and(condition)
            sql_part += 'AND {keys} '.format(keys=where_key)
            values += where_val
        if betweens and len(betweens):
            for between in betweens:
                bt_key, bt_start, bt_end = await self.dict_to_between(between)
                sql_part += f' AND {bt_key}'
                values += [bt_start, bt_end]

        if other_str:
            sql_part += ' AND ' + other_str
            if other_value:
                values.extend(other_value)
        if online_str:
            sql_part += ' AND ' + online_str
            if online_value:
                values.extend(online_value)

        # 获取所有数据总数
        sql = "select count(*) from {table} where 1=1 ".format(table=table)
        sql += sql_part

        t = await self.query(sql, *values)
        if t:
            t = t[0]['count(*)']
        else:
            t = 0
        # 获取所有数据的指定key数据
        c = []
        if keys_count:
            sql = "select {keys} from {table} where 1=1 ".format(keys=await self.list_keys(keys_count), table=table)
            sql += sql_part
            c = await self.query(sql, *values)
        # 获取分页数据
        sql = "select {keys} from {table} where 1=1 ".format(keys=await self.list_keys(keys), table=table)
        order_by = ' order by {order_field} {sort} '.format(order_field=order_field, sort=order_by)
        sql += sql_part + order_by
        if limit and offset > -1:
            sql += 'limit %s offset %s'
            values += [limit, (offset - 1) * limit]
        r = await self.query(sql, *values)

        if keys_count:
            return r, t, c
        if r:
            return r, t
        return [], 0

    # 条件查询(返回首结果)
    async def get_result_by_condition(self, table, keys, condition):
        key = await self.list_keys(keys)
        k, v = await self.dict_to_and(condition)
        sql = """select {keys} from {table} where {condition} order by id desc limit 1""".format(keys=key, table=table, condition=k)

        r = await self.query(sql, *v)

        if r:
            return r[0]
        else:
            return dict()

    # 条件查询(返回结果集)
    async def get_results_by_condition(self, table, keys, condition):
        key = await self.list_keys(keys)
        k, v = await self.dict_to_and(condition)
        sql = 'select {keys} from {table} where {condition}'.format(keys=key, table=table, condition=k)

        r = await self.query(sql, *v)

        if r:
            return r
        else:
            return []

    # 直接查询(返回首结果)
    async def get_result_no_condition(self, table, keys):
        key = await self.list_keys(keys)
        sql = """select {keys} from {table} order by id desc limit 1""".format(keys=key, table=table)

        r = await self.query(sql)
        if r:
            return r[0]
        else:
            return dict()

    # 直接查询(返回结果集)
    async def get_results_no_condition(self, table, keys):
        key = await self.list_keys(keys)
        sql = 'select {keys} from {table}'.format(keys=key, table=table)

        r = await self.query(sql)
        if r:
            return r

        return []

    # 创建
    async def create_result(self, table, data):
        k, p, v = await self.dict_to_kv(data)
        sql = "insert into {table} ({keys}) values ({vals})".format(table=table, keys=k, vals=p)
        if await self.execute(sql, *v):
            return True
        return False

    # 检查是否存在
    async def is_exits(self, table, filed, where):
        sql = 'select id from {table} where {filed} = %s'.format(table=table, filed=filed)
        r = await self.query(sql, where)
        if r:
            return True
        else:
            return False

    # 更新
    async def update_result(self, table, data, condition):
        key_update, val_update = await self.dict_to_equal(data)
        key_where, val_where = await self.dict_to_and(condition)
        sql = 'update {table} set {keys} where {condition} limit 1'.format(table=table, keys=key_update, condition=key_where)
        if await self.execute(sql, *val_update, *val_where):
            return True
        return False

    # 删除
    async def delete_result(self, table, condition):
        key_where, val_where = await self.dict_to_and(condition)
        sql = 'delete from {table} where {condition}'.format(table=table, condition=key_where)

        if await self.execute(sql, *val_where):
            return True
        return False

    # 返回JSON
    async def json_response(self, data, key=None):
        if key:
            await self.redis.delete(key)
        self.set_header('Content-Type', 'application/json')
        output = json.dumps(data, cls=RewriteJsonEncoder)
        self.write(output)

    # 参数为空(排除0)
    @staticmethod
    async def is_null(data, args):
        keys = data.keys()
        for i in args:
            if i not in keys or not data[i] and data[i] != 0:
                return True
        return False

    # 检查谷歌验证码
    async def check_googl_code(self, code, key):
        totp = pyotp.TOTP(key)
        if totp.verify(code):
            return True
        else:
            return False

    # 创建谷歌密钥
    async def create_gg_key(self):
        return pyotp.random_base32()

    # 生成随机字符串
    async def random_captcha_text(self, captcha_size=4):
        number = ['3', '4', '6', '7', '8', '9']
        alphabet = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'k', 'm', 'n', 'p', 'q', 't', 'u',
                    'v', 'w', 'x', 'y']
        ALPHABET = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'U',
                    'V', 'W', 'X', 'Y', 'Z']

        char_set = number + alphabet + ALPHABET
        captcha_text = ''
        for i in range(captcha_size):
            c = random.choice(char_set)
            captcha_text += c
        return captcha_text

    # 创建商户密钥
    async def create_api_key(self):
        m = hashlib.new('md5')
        salt = await self.random_captcha_text(6)
        ss = uuid.uuid4().bytes.hex()

        m.update((ss + salt).encode('utf8'))
        return m.hexdigest()

    # 创建密码
    async def password_create(self, password):
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf8'), salt)
        return hashed

    # 创建订单号
    async def create_order_code(self, PRE='R'):
        return PRE + ''.join(str(datetime.datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))

    # 余额变动
    async def change_balance_sd(self, amount, balance_type, user_type, user_id, remark):
        # 获取流水类型
        record_types = {'balance_frozen': 4, 'balance_deposit': 5, 'balance': 6}
        record_type = record_types[balance_type]
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 冻结或押金
                    if not balance_type == 'balance':
                        sql_update = """update {table} set {balance_type}={balance_type}+%s where id = %s""".format(
                            table=user_type, balance_type=balance_type)
                        if not await cur.execute(sql_update, (amount, user_id)):
                            await conn.rollback()
                            self.logger.warning('{user_id}改变冻结或押金失败'.format(user_id=user_id))
                            return False
                        sql_select = """select {balance_type} from {table} where id = %s""".format(table=user_type, balance_type=balance_type)
                        if not await cur.execute(sql_select, user_id):
                            await conn.rollback()
                            self.logger.warning('{user_id}获取冻结余额失败'.format(user_id=user_id))
                            return False
                        if (await cur.fetchall())[0][balance_type] < Decimal(0):
                            await conn.rollback()
                            self.logger.warning('{user_id}冻结或押金不足'.format(user_id=user_id))
                            return False
                        amount = -amount

                    # 余额变动
                    code = await self.create_order_code(PRE='BD')
                    if not await self.change_balance(conn, cur, user_type, user_id, amount, code, record_type, remark):
                        return False
                except Exception as e:
                    await conn.rollback()
                    self.logger.exception(e)
                    return False
                else:
                    await conn.commit()
                    return True

    # 金额变动
    async def change_balance(self, conn, cur, table, user_id, amount, code=None, record_type=None, remark=None):
        sql_update = """update {table} set balance=balance+%s where id = %s""".format(table=table)
        sql_select = """select balance{other} from {table} where id = %s""".format(table=table, other=',vip' if table == 'partner' else '')
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,
                            record_type,admin_id,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        sql_select_vip = """select vip,conditions from vip"""
        sql_update_vip = """update partner set vip=%s where id = %s"""
        sql_select_orders = """SELECT  merchant_code FROM orders_df WHERE code = '{code}' UNION SELECT merchant_code  FROM orders_ds WHERE code = '{code}'""".format(code=code)
        # sql_select_vip_one = """select vip,conditions,deposit_ratio from vip where vip=%s"""
        try:
            if not await cur.execute(sql_select, user_id):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            _before = (await cur.fetchall())[0]['balance']
            if not await cur.execute(sql_update, (amount, user_id)):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            self.logger.info('更改金额{sql}'.format(sql=cur._last_executed))
            if not await cur.execute(sql_select, user_id):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            user = (await cur.fetchall())[0]
            partnerBalance = 0
            # 获取未修改前VIP等级信息
            # if not await cur.execute(sql_select_vip_one, (user['vip'])):
            #     await conn.rollback()
            #     self.logger.warning(cur._last_executed)
            #     return False
            # vip = (await cur.fetchall())[0]
            # # 获取去除保证金后的余额
            # partnerBalance = await self.removeDeposit(_before, vip['conditions'], vip['deposit_ratio'])
            _after = user['balance']

            if _after < partnerBalance:
                await conn.rollback()
                return False
            user_type = 0 if table == 'partner' else 1
            merchant_code = None
            if await cur.execute(sql_select_orders):
                merchant_code = (await cur.fetchall())[0]['merchant_code']

            if not await cur.execute(sql_insert, (code, user_type, user_id, _before, amount, _after, record_type, self.current_user['id'], remark, merchant_code)):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            self.logger.info('新增流水{sql}'.format(sql=cur._last_executed))
            # vip
            if table == 'partner' and amount > Decimal(0):
                _vip = 0
                # _deposit = Decimal(0)
                if not await cur.execute(sql_select_vip):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return False
                vips = await cur.fetchall()
                for i in vips:
                    if _after >= i['conditions']:
                        _vip = i['vip']
                    #     _deposit = Decimal(i['conditions']) * Decimal(0.2)
                    # else:
                    #     break
                # _if_deposit = False
                if int(_vip) >= user['vip']:
                    # _deposit = _deposit.quantize(Decimal('.0000'))
                    if int(_vip) > user['vip']:  # 余额够升级时
                        if not await cur.execute(sql_update_vip, (_vip, user_id)):
                            await conn.rollback()
                            self.logger.warning('{user_id}改变VIP失败'.format(user_id=user_id))
                            return False
                        # 改变vip之后，需要将余额减去
                        # if not await self.change_balance(conn, cur, 'partner', user_id, user['balance_deposit']-_deposit, code, 5):
                        #     self.logger.warning('{user_id}余额转押金失败'.format(user_id=user_id))
                        #     return False
                        # _if_deposit = True
                    # else: # 余额够平级时
                    #     if _deposit != user['balance_deposit'] and not record_type == 5:
                    #         _if_deposit = True
                    #         if not await self.change_balance(conn, cur, 'partner', user_id, user['balance_deposit']-_deposit, code, 5):
                    #             self.logger.warning('{user_id}余额转押金失败'.format(user_id=user_id))
                    #             return False
                    #         # 增加押金
                    #         sql_update = """update {table} set balance_deposit=balance_deposit+%s where id = %s""".format(table=table)
                    #         if not await cur.execute(sql_update, (-(user['balance_deposit']-_deposit), user_id)):
                    #             await conn.rollback()
                    #             self.logger.warning('{user_id}增加押金失败'.format(user_id=user_id))
                    #             return False
                # 实时转码商保证金（余额不够平级和升级时）
                # if _if_deposit is False:
                #     _balance_deposit = 0
                #     for i in vips:
                #         if i['vip'] == user['vip']:
                #             _balance_deposit = i['conditions'] * Decimal(0.2) - user['balance_deposit']
                #             _balance_deposit = _balance_deposit.quantize(Decimal('.0000'))
                #             break
                #     if _balance_deposit > 0 and user['balance'] >= _balance_deposit and not record_type == 5:
                #         if not await self.change_balance(conn, cur, 'partner', user_id, -_balance_deposit, code, 5):
                #             self.logger.warning('{user_id}实时余额转押金失败'.format(user_id=user_id))
                #             return False
                #         # 增加押金
                #         sql_update = """update {table} set balance_deposit=balance_deposit+%s where id = %s""".format(table=table)
                #         if not await cur.execute(sql_update, (_balance_deposit, user_id)):
                #             await conn.rollback()
                #             self.logger.warning('{user_id}实时增加押金失败'.format(user_id=user_id))
                #             return False

            return True
        except Exception as e:
            self.logger.exception(e)
            await conn.rollback()
            return False

    # 计算去除押金后余额
    async def removeDeposit(self, amount, conditions, depositRatio):
        amount = Decimal(amount)
        conditions = Decimal(conditions)
        depositRatio = Decimal(depositRatio) / Decimal(100)
        return amount - conditions * depositRatio

    # 下单
    async def order(self, order_type, data):
        try:
            data['amount'] = float(data['amount'])
            data['merchant_id'] = 0
            data['gateway'] = 0 if order_type == 'df' else 1001
            data['callback'] = 0
            data['notify'] = 0
            mc_key = (await self.get_result_by_condition('merchant', ['mc_key'], {'id': 0}))['mc_key']
            dataList = []
            for key in sorted(data):
                if data[key]:
                    dataList.append("%s=%s" % (key, data[key]))
            signdata = "&".join(dataList).strip() + "&key={key}".format(key=mc_key)
            md5 = hashlib.md5()
            md5.update(signdata.encode(encoding='UTF-8'))
            sign = md5.hexdigest().upper()
            data['sign'] = sign
            url = self.application.api_url + '/api/pay'
            if order_type == 'df':
                url += 'df'
            json_data = json.dumps(data)
            r = requests.post(url, json_data, timeout=5, verify=False)
            ret = json.loads(r.text)
            if ret['code'] == 0:
                return True
            return False
        except Exception as e:
            return False

    # 增加日志
    async def add_operate(self, o_type, admin_id=None):
        if not o_type == 1:
            admin_id = self.current_user['id']
        data = {'type': o_type, 'admin_id': admin_id, 'ip': await self.get_ip()}
        if not await self.create_result('operate', data):
            self.logger.warning('记录操作日志失败，管理员ID{id}'.format(id=self.current_user['id']))

    async def get_partners(self, top_partner):
        # 查询所有层次的partner_id
        sql = 'select child from partner_tree where parent = %s'
        _top_partner = await self.query(sql, top_partner)
        top_partner = []
        for i in _top_partner:
            top_partner.append(str(i['child']))
        return top_partner

    async def get_partners_by_parent_id(self, parent_id):
        """通过parent_id获取码商id"""
        tg_partners = await self.query(
            """select child from partner_tree where parent = %s""",
            *[parent_id]
        )
        tg_partners_ids = ','.join([str(partner['child']) for partner in tg_partners])
        return tg_partners_ids

    # 获取锁acquire_loc
    async def acquire_lock(self, lockname, acquire_timeout=10, lock_timeout=10):
        identifier = str(uuid.uuid4())  # random identifier
        lockname = 'lock:' + lockname
        lock_timeout = int(math.ceil(lock_timeout))

        end = time.time() + acquire_timeout
        while time.time() < end:
            if await self.redis.set(lockname, identifier, ex=lock_timeout, nx=True):
                return identifier
            time.sleep(.001)
        return False

    # 释放锁release_lock
    async def release_lock(self, lockname, identifier):
        pipe = await self.redis.pipeline(True)
        lockname = 'lock:' + lockname

        while True:
            try:
                await pipe.watch(lockname)
                if await pipe.get(lockname) == identifier:
                    pipe.multi()
                    await pipe.delete(lockname)
                    await pipe.execute()
                    return True
                await pipe.unwatch()
                break
            except await self.redis.exceptions.WatchError:
                pass
        return False

    # 判断时间范围是否满足要求
    async def calculate_date_diff(self, start_date, end_date,days=31):
        date_format = "%Y-%m-%d %H:%M:%S"
        if isinstance(start_date,str):
            start_date = datetime.datetime.strptime(start_date, date_format)
        else:
            start_date = datetime.datetime.strptime(start_date.strftime(date_format), date_format)
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, date_format)
        else:
            end_date = datetime.datetime.strptime(end_date.strftime(date_format),date_format)

        diff = end_date - start_date
        return diff.days>days

    async def delete_cache_result(self, table, condition):
        """更新指定数据时，进行延迟双删"""
        # 获取id，默认为1
        info_id = condition.get('id', 1)
        # 获取id，根据表名和id组成redis键
        redis_key = f'cache_info_{table}_{info_id}'
        # 进行延迟双删
        await self.redis.delete(redis_key)
        await asyncio.sleep(2)
        await self.redis.delete(redis_key)
        self.logger.info(f'已删除"{table}"缓存数据, 条件： {str(condition)}')

    async def get_cache_result(self, table, keys, condition=None):
        """
        获取缓存数据，未获取到的数据查询数据库后存入缓存
        condition必传入id 或 不传默认为1
        """
        if not condition:
            condition = {'id': 1}

        redis_key = f'cache_info_{table}_{condition["id"]}'
        data_info = await self.redis.get(redis_key)
        if data_info:
            data_info = simplejson.loads(data_info, parse_float=Decimal)
        else:
            data_info = await self.get_result_by_condition(table, ['*'], condition)
            await self.redis.set(redis_key, simplejson.dumps(data_info))
            self.logger.info(f'缓存数据已更新： {table} {condition}')

        data_info = data_info if keys == ['*'] else {key: data_info[key] for key in keys}
        return data_info

    async def update_cache_result(self, table, condition=None):
        """
        更新缓存数据，强制查询数据库后存入缓存
        condition必传入id 或 不传默认为1
        """
        if not condition:
            condition = {'id': 1}

        redis_key = f'cache_info_{table}_{condition["id"]}'
        data_info = await self.get_result_by_condition(table, ['*'], condition)
        await self.redis.set(redis_key, simplejson.dumps(data_info))
        self.logger.info(f'缓存数据已更新： {table} {condition}')


class RewriteJsonEncoder(json.JSONEncoder):
    """重写json类，为了解决datetime类型的数据无法被json格式化"""

    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, datetime.date):
            return obj.strftime("%Y-%m-%d")
        elif isinstance(obj, Decimal):
            return str(obj)
        elif hasattr(obj, 'isoformat'):
            # 处理日期类型
            return obj.isoformat()
        else:
            return json.JSONEncoder.default(self, obj)
