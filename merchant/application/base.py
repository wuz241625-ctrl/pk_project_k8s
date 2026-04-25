import hashlib
import json
import datetime
import logging
import random
import re
import traceback
import uuid
import ast

import bcrypt
import pyotp
import requests

import tornado.web

from decimal import Decimal
from aiomysql import DictCursor
from tornado.options import define, options

from application.client_ip import resolve_client_ip
from application.message import msg

# 定义全局 TRACE_ID
define('TRACE_ID', default=None, help='trace id')
define('RQ_ID', default=0, help='request id')
# 上一个TRACE_ID
class TraceIdFilter(logging.Filter):
    # 打印用法
    def __init__(self, trace_id=None):
        super().__init__()
        self.current_id = 0
        if trace_id:
            self.trace_id = trace_id
            options.TRACE_ID = trace_id
        else:
            self.trace_id = None

    def filter(self, record):
        record.trace_id = str(options.TRACE_ID)
        self.current_id += 1
        record.id = self.current_id
        return True

class BaseHandler(tornado.web.RequestHandler):
    # 预处理
    async def prepare(self):
        self.redis = self.application.redis
        self.logger = self.application.logger
        trace_id = str(uuid.uuid4().hex)
        self.logger.addFilter(TraceIdFilter(trace_id))
        # 检查IP
        if not await self.check_ip():
            return self.send_error(403, reason='ip:{ip} 禁止登录'.format(ip=await self.get_ip()))
        try:
            if self.request.body:
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
                user = await self.get_result_by_condition('merchant', ['id', 'name'], {'id': user_id})
                self.current_user = user
            else:
                # 未登录或已过期
                self.current_user = None
        except Exception as e:
            self.logger.exception(e)
            self.clear_cookie('id')
            return self.send_error(403)

    # 获取IP
    async def get_ip(self):
        ip = resolve_client_ip(self.request.headers, self.request.remote_ip)
        self.logger.info(
            '获取IP,host={host},remote_ip={remote_ip},client_ip={client_ip}'.format(
                host=self.request.host,
                remote_ip=self.request.remote_ip,
                client_ip=ip,
            )
        )
        return ip

    # 检查IP是否在白名单
    async def check_ip(self):
        ip = await self.get_ip()
        user_id = self.get_secure_cookie("user")
        if self.request.uri == '/login/singin':
            data = json.loads(self.request.body)
            r = await self.get_result_by_condition('merchant', ['ip'], {'cellphone': data['username']})
        elif user_id:
            r = await self.get_result_by_condition('merchant', ['ip'], {"id": user_id})
        else:
            return False
        if r and r['ip'] and not (r['ip'] == ip or ip in r['ip'].split(',')):
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

    # 设置cookie值
    async def set_my_cookie(self, k, v):
        self.set_secure_cookie(k, v, expires_days=1)

    # 组装查询key,进行分割
    @staticmethod
    async def list_keys(data):
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
    @staticmethod
    async def dict_to_between(data):
        key = " {key} between %s and %s".format(key=data['key'])
        start = data['start']
        end = data['end']
        return key, start, end

    # 组装查询key,返回 k1,k2,k3...  %s,%s,%s... 和 [val1,val2,val3...]
    @staticmethod
    async def dict_to_kv(data):
        d = {k: data[k] for k in sorted(data)}
        sql_key = ', '.join(k for k in d.keys())
        sql_place = ', '.join(["%s"] * len(data))
        sql_val = d.values()

        return sql_key, sql_place, sql_val

    # 组装查询条件格式，返回 k1=%s and k2=%s 和 [val1, val2]
    @staticmethod
    async def dict_to_and(data):
        d = {k: data[k] for k in sorted(data) if data[k] != ''}  # 移除值为空的键
        tmp_list = []
        vals = []

        for key, value in d.items():
            if isinstance(value, str) and value == "''":
                # 如果 value 是空字符串（即 "''"），手动加入条件 `key = ''`
                tmp_list.append(f"{key} = ''")
            else:
                if isinstance(value, str):
                    # 尝试解析字符串为列表
                    try:
                        parsed_value = ast.literal_eval(value)
                        if isinstance(parsed_value, list):
                            # 处理 IN 的情况
                            placeholders = ', '.join(['%s'] * len(parsed_value))
                            tmp_list.append(f"{key} IN ({placeholders})")
                            vals.extend(parsed_value)  # 将列表中的值加入到 vals 中
                            continue
                    except (ValueError, SyntaxError):
                        # 解析失败，继续处理为普通字符串
                        pass
            
                # 处理普通的 = 条件
                tmp_list.append(f"{key} = %s")
                vals.append(value)

        keys = ' AND '.join(tmp_list)
        return keys, vals

    # 组装查询条件格式，返回 k1=%s, k2=%s 和 [val1, val2]
    @staticmethod
    async def dict_to_equal(data):
        d = {k: data[k] for k in sorted(data)}
        tmp_list = []
        for i in d.keys():
            tmp_list.append("{key}=%s".format(key=i))
        sql_key = ', '.join(tmp_list)
        sql_val = d.values()
        return sql_key, sql_val

    # SQL 查询
    async def query(self, sql, *args):
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    if not await cur.execute(sql, args):
                        await conn.rollback()
                        return []
                    self._last_sql = cur._last_executed
                    r = await cur.fetchall()
                except Exception as e:
                    self.logger.exception(e)
                    await conn.rollback()
                    return []
                else:
                    await conn.commit()
                    return r

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
    # flag 需要特殊处理的标记标记  例如  code not like '%_%'
    async def get_result(self, table, keys, keys_count=None, condition=None, between=None, limit=None, offset=None,
                         order_by='desc', order_field='id', flag = False):
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

        
        if flag is True:
            # 修改 SQL 部分，避免转义错误
            #sql_part += " and code not like '%%\\\\_%%'"
            sql_part += " and not (`code` like '%%\\_%%' ESCAPE '\\\\' or BINARY `code` LIKE '%%z%%')"

        # 获取所有数据总数
        sql = "select count(id) from {table} ".format(table=table)
        sql += sql_part
        t = await self.query(sql, *values)
        if t:
            t = t[0]['count(id)']
        else:
            t = 0
        # 获取所有数据的指定key数据
        c = []
        if keys_count:
            sql = "select {keys} from {table} ".format(keys=await self.list_keys(keys_count), table=table)
            sql += sql_part
            c = await self.query(sql, *values)

        # 获取分页数据
        sql = "select {keys} from {table}  where id in (select id from {table} ".format(keys=await self.list_keys(keys),
                                                                                        table=table)
        order_by = ') order by {order_field} {sort} '.format(order_field=order_field, sort=order_by)
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
        sql = 'select {keys} from {table} where {condition}'.format(keys=key, table=table, condition=k)

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
        sql = 'select {keys} from {table}'.format(keys=key, table=table)

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
        sql = 'update {table} set {keys} where {condition}'.format(table=table, keys=key_update, condition=key_where)
        if await self.execute(sql, *val_update, *val_where):
            return True
        return False

    # 返回JSON
    async def json_response(self, data):
        self.set_header('Content-Type', 'application/json')
        output = json.dumps(data, cls=RewriteJsonEncoder)
        self.write(output)

    # 参数为空
    @staticmethod
    async def is_null(data, args):
        keys = data.keys()
        for i in args:
            if i not in keys or not data[i] and data[i] != 0:
                return True
        return False

    # 检查谷歌验证码
    @staticmethod
    async def check_googl_code(code, key):
        totp = pyotp.TOTP(key)
        if totp.verify(code):
            return True
        else:
            return False

    # 创建谷歌密钥
    @staticmethod
    async def create_gg_key():
        return pyotp.random_base32()

    # 生成随机字符串
    @staticmethod
    async def random_captcha_text(captcha_size=4):
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
    @staticmethod
    async def password_create(password):
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf8'), salt)
        return hashed

    # 创建订单号
    @staticmethod
    async def create_order_code(pre='R'):
        return pre + ''.join(str(datetime.datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))

    # 金额变动
    async def change_amount(self, conn, cur, code, amount, record_type):
        sql_update = """update merchant set balance=balance+%s where id = %s"""
        sql_select = """select balance from merchant where id = %s"""
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type) value (%s,%s,%s,%s,%s,%s,%s)"""
        try:
            if not await cur.execute(sql_select, self.current_user['id']):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            _before = (await cur.fetchall())[0]['balance']
            if not await cur.execute(sql_update, (amount, self.current_user['id'])):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            self.logger.info('执行更新{sql}'.format(sql=cur._last_executed))
            if not await cur.execute(sql_select, self.current_user['id']):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            _after = (await cur.fetchall())[0]['balance']

            if _after < 0:
                await conn.rollback()
                return False
            if not await cur.execute(sql_insert, (code, 1, self.current_user['id'], _before, amount, _after, record_type)):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            self.logger.info('增加记录{sql}'.format(sql=cur._last_executed))
            return True
        except Exception as e:
            self.logger.exception(e)
            await conn.rollback()
            return False

    # 代付下单
    async def order_df(self, data, mc_key):
        try:
            order_id = await self.create_order_code('MF')
            date_p = {'mer_id': self.current_user['id'], 'order_id': order_id, 'gateway': 1, 'amount': data['amount'],
                      'account': data['payment_account'], 'user': data['payment_name'], 'bank_code': data['ifsc'],
                      'bank': data['payment_bank'], 'notify': 'sys'}
            dataList = []
            for key in sorted(date_p):
                if date_p[key]:
                    dataList.append("%s=%s" % (key, date_p[key]))
            signdata = "&".join(dataList).strip() + "&key=" + mc_key.strip()
            md5 = hashlib.md5()
            md5.update(signdata.encode(encoding='UTF-8'))
            sign = md5.hexdigest().upper()
            date_p['sign'] = sign
            url = self.application.api_url + '/pay/df'
            r = requests.post(url, date_p, timeout=5, verify=False)
            # ret = json.loads(r.text)
            return r.text
            # return await self.json_response(ret)
        except Exception as e:
            self.logger.exception('下代付单异常{e}'.format(e=str(e)))
            return await self.json_response(msg[10011])


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
