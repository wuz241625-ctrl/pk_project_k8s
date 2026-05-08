import hashlib
import json
import logging
import os

import simplejson
import datetime
import time
import random
import re
import uuid
import html
import urllib.parse
import sysconfig
import traceback

from config import get_config
from decimal import Decimal

import bcrypt
import jwt
import requests
import tornado.web
from aiomysql import DictCursor
from application.client_ip import resolve_client_ip
from application.message import msg
from itsdangerous import URLSafeTimedSerializer
from itsdangerous.exc import SignatureExpired, BadTimeSignature
from application.pxfilter import XssHtml
from tornado.options import define, options


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

    # 跨域
    def set_default_headers(self) -> None:
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS, PUT, PATCH')
        self.set_header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, x-csrftoken, Authorization')
        self.set_header('Access-Control-Max-Age', '360000')

    def options(self):
        pass

    # 预处理，获取current_user
    async def prepare(self):
        self.redis = self.application.redis
        self.logger = self.application.logger
        if not self.logger.filters:
            self.logger.addFilter(TraceIdFilter())
        self.data_table = dict(code=0, msg='', count=0, data=[])
        self.order_token_key = self.application.order_token_key
        self.secret_key = self.application.secret_key
        if not await self.check_ip():
            return self.send_error(403, reason='ip{ip}禁止访问'.format(ip=await self.get_ip()))

        # if not self.request.path == '/files/upload':
        #     try:
        #         if self.request.body:
        #             data = json.loads(self.request.body)
        #             if not self.check_arguments(data):
        #                 return self.send_error(419)
        #     except Exception as e:
        #         self.logger.exception(e)
        #         return self.send_error(msg[10001])
        merchant_pay_links = await self.redis.get('merchant_pay_links')
        if merchant_pay_links:
            self.application.pay_url = random.choice(merchant_pay_links.split(','))
        else:
            self.application.pay_url = conf['pay_url']

    # 获取IP
    async def get_ip(self):
        return resolve_client_ip(self.request.headers, self.request.remote_ip)

    def _get_ip(self):
        return resolve_client_ip(self.request.headers, self.request.remote_ip)

    # 检查IP
    async def check_ip(self):
        ip = await self.get_ip()
        r = await self.get_cache_result('sys_info', ['api_ip_b'], {"id": 1})
        if r and ip in r['api_ip_b'].split(','):
            return False
        return True

    @staticmethod
    async def check_different(data1, data2, args):
        for i in args:
            if not data1[i] == data2[i]:
                return False
        return True

    @staticmethod
    async def check_different_new(data1, data2, args):
        def safe_unescape(value):
            """ 仅进行 HTML 和 URL 反转义 """
            if not isinstance(value, str):
                return value
            return html.unescape(urllib.parse.unquote(value))  # 先反转义 HTML，再反转义 URL

        def safe_escape(value):
            """ 再进行 HTML 和 URL 转义 """
            if not isinstance(value, str):
                return value
            return urllib.parse.quote(html.escape(value))  # 先转义 HTML，再转义 URL

        for i in args:
            value1 = safe_unescape(data1.get(i, ""))
            value2 = safe_unescape(data2.get(i, ""))

            # 同时检查正向和反向转换后的值是否匹配
            if value1 != value2 and safe_escape(value1) != safe_escape(value2):
                return False

        return True

    async def get_escaped_argument(self, key, default=None):
        parser = XssHtml()
        parser.feed(self.get_argument(key, default))
        parser.close()
        return parser.getHtml()

    # 检查参数合规
    @staticmethod
    async def is_valid_key(data, args):
        keys = data.keys()
        for i in keys:
            if i not in args:
                return False
        return True

    # 检查空参数
    @staticmethod
    async def is_null(data, args):
        keys = data.keys()
        for i in args:
            if i not in keys or not data[i] and data[i] != 0:
                return True
        return False

    # 检查数据合法
    @staticmethod
    async def is_valid_data(data):
        pattern = r"[~`!@#$%^&*()_+-={}\[\]\\|:;\"',<>?/]"
        for i in data:
            if re.search(i, pattern):
                return False
        return True

    # 发送验证码
    async def send_code(self, cellphone):
        url = "https://www.fast2sms.com/dev/bulkV2"
        code = random.randint(1000, 9999)
        key = 'phonecode{cellphone}_{code}'.format(cellphone=cellphone, code=code)
        await self.redis.set(key, 1, 300)
        try:
            payload = "variables_values={code}&route=otp&numbers={cellphone}".format(code=code, cellphone=cellphone)
            headers = {
                'authorization': "dXLrW3tkRSimIqvT0HhBfxnueAFDwa6jUYbGy2EcV1gMNZKQplDqd1GK8NU6QRWYlOwIjr9zCB4omPL5",
                'Content-Type': "application/x-www-form-urlencoded",
                'Cache-Control': "no-cache",
            }
            r = requests.post(url, data=payload, headers=headers, timeout=5)
            ret = json.loads(r.text)
            if ret['message'] == ['SMS sent successfully.']:
                return True
        except Exception as e:
            self.logger.exception(e)
            return False

    # 清除当前用户的接单
    async def clear_active(self, partner_id):
        return None

    # 生成token
    async def encode_token(self, partner_id):
        dic = {
            'exp': datetime.datetime.now() + datetime.timedelta(days=7),
            'id': partner_id
        }
        return jwt.encode(dic, self.secret_key)

    # 解码token
    async def decode_token(self, token):
        r = jwt.decode(token, self.secret_key, 'HS256')
        user_id = r['id']
        exp = r['exp']
        return exp, user_id

    # 生成订单token
    async def token_generate(self, order_code):
        s = URLSafeTimedSerializer(self.order_token_key)
        string = s.dumps(order_code)
        return string

    # 解码订单token
    async def token_decode(self, token, max_age=300, return_timestamp=False):
        s = URLSafeTimedSerializer(self.order_token_key)
        try:
            if return_timestamp:
                data = s.loads(token, max_age=max_age, return_timestamp=True)
                return data[0], data[1]  # payload + timestamp
            else:
                return s.loads(token, max_age=max_age)
        except SignatureExpired:
            return 10016
        except BadTimeSignature:
            return 10016
        except Exception:
            return 10017

    # 组装查询key,进行分割
    async def list_keys(self, data):
        return ','.join(data)

    # 区分between 和condition
    async def split_between_condition(self, data, key):
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
    async def dict_to_and(self, data):
        d = {k: data[k] for k in sorted(data)}
        tmp_list = []
        for i in d.keys():
            tmp_list.append("{key}=%s".format(key=i))
        keys = ' and '.join(tmp_list)
        vals = d.values()
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

    # SQL 查询
    async def query(self, sql, *args):
        # 获取完整调用堆栈
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
                    await conn.rollback()
                    return []
                else:
                    await conn.commit()
                    return r
                finally:
                    cost_ms = (time.time() - start) * 1000
                    if cost_ms > self.get_sql_timeout():
                        await self.build_sql_alert_message(
                            sql, args, cost_ms, rowcount, line_info
                        )

    # 分页查询
    async def get_result(self, table, keys, condition=None, offset=None, limit=10, order_by='desc', order_field='id'):
        sql = 'select {keys} from {table}'.format(keys=await self.list_keys(keys), table=table)
        values = []
        if condition:
            for k in list(condition.keys()):
                if not condition[k] and condition[k] != 0:
                    condition.pop(k)
        if condition:
            where_key, where_val = await self.dict_to_and(condition)
            sql += ' where {keys}'.format(keys=where_key)
            values += where_val

        sql += ' order by {order_field} {sort}'.format(order_field=order_field, sort=order_by)
        if limit and offset >= 0:
            sql += ' limit %s offset %s'
            values += [limit, offset]

        r = await self.query(sql, *values)
        if r:
            return r
        return []

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

    # 删除
    async def delete_result(self, table, condition):
        key_where, val_where = await self.dict_to_and(condition)
        sql = 'delete from {table} where {condition}'.format(table=table, condition=key_where)

        if await self.execute(sql, *val_where):
            return True
        return False

    # 返回JSON
    async def json_response(self, data):
        self.set_header('Content-Type', 'application/json')
        output = json.dumps(data, cls=RewriteJsonEncoder)
        # output = simplejson.dumps(data)
        self.write(output)

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
    @staticmethod
    async def password_create(password):
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf8'), salt)
        return hashed

    # 设置cookie值
    async def set_my_cookie(self, k, v):
        self.set_secure_cookie(k, v, expires_days=1)

    # 设置xsrf
    async def set_xsrf(self):
        return self.xsrf_token

    # 遍历检查数据
    def check_arguments(self, data):
        for v in data:
            if isinstance(v, dict) or isinstance(v, list):  # 如果是json或者数组则继续
                self.check_arguments(v)
            else:
                if not self.check_argument(v):
                    self.logger.warning('非法参数,url={url},非法数据={v}'.format(url=self.request.path, v=v))
                    return False
        return True

    # 检查数据值
    def check_argument(self, str_value):
        string = """\\'"<>&="""
        for i in string:
            if i in str_value:
                return False
        return True

    # 创建订单号
    async def create_order_code(self, PRE='R'):
        return PRE + ''.join(str(datetime.datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))

    # 余额变动
    async def change_balance(self, conn, cur, table, user_id, amount, code, record_type, remark=None, merchant_code=None):
        sql_update = 'update {table} set balance=balance + %s where id = %s'.format(table=table)
        sql_select = """select balance{other} from {table} where id = %s""".format(table=table, other=',vip' if table == 'partner' else '')
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
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
            # if table == 'partner':
            #     # 获取未修改前VIP等级信息
            #     if not await cur.execute(sql_select_vip_one, (user['vip'])):
            #         await conn.rollback()
            #         self.logger.warning(cur._last_executed)
            #         return False
            #     vip = (await cur.fetchall())[0]
            #     # 获取去除保证金后的余额
            #     partnerBalance = await self.removeDeposit(_before, vip['conditions'], vip['deposit_ratio'])
            _after = user['balance']
            if Decimal(_after) < partnerBalance:
                await conn.rollback()
                return False
            user_type = 0 if table == 'partner' else 1
            self.logger.info('查询商户订单号{merchant_code}'.format(merchant_code=merchant_code))
            if merchant_code == None:
                if await cur.execute(sql_select_orders):
                    merchant_code = (await cur.fetchall())[0]['merchant_code']
                self.logger.info('查询商户订单号{sql}'.format(sql=cur._last_executed))
            if not await cur.execute(sql_insert, (code, user_type, user_id, _before, amount, _after, record_type, remark,merchant_code)):
                await conn.rollback()
                self.logger.warning(cur._last_executed)
                return False
            self.logger.info('新增流水{sql}'.format(sql=cur._last_executed))
            # vip
            if table == 'partner' and amount > Decimal(0):
                _vip = 0
                # _deposit = 0
                if not await cur.execute(sql_select_vip):
                    await conn.rollback()
                    self.logger.warning(cur._last_executed)
                    return False
                vips = await cur.fetchall()
                for i in vips:
                    if _after >= i['conditions']:
                        _vip = i['vip']
                    #     _deposit = i['conditions'] * Decimal(0.2)
                    # else:
                    #     break
                # _if_deposit = False
                if int(_vip) > user['vip']:
                    # _deposit = _deposit.quantize(Decimal('.0000'))
                    if int(_vip) > user['vip']:# 余额够升级时
                        if not await cur.execute(sql_update_vip, (_vip, user_id)):
                            await conn.rollback()
                            self.logger.warning('{user_id}改变VIP失败'.format(user_id=user_id))
                            return False
                        # 改变vip之后，需要将余额减去
                        # if not await self.change_balance(conn, cur, 'partner', user_id, user['balance_deposit'] - _deposit, code, 5):
                        #     self.logger.warning('{user_id}余额转押金失败'.format(user_id=user_id))
                        #     return False
                        # _if_deposit = True
                    # else: # 余额够平级时
                    #     if _deposit != user['balance_deposit'] and not record_type == 5:
                    #         _if_deposit = True
                    #         if not await self.change_balance(conn, cur, 'partner', user_id, user['balance_deposit'] - _deposit, code, 5):
                    #             self.logger.warning('{user_id}余额转押金失败'.format(user_id=user_id))
                    #             return False
                    #         # 增加押金
                    #         sql_update = """update {table} set balance_deposit=balance_deposit+%s where id = %s""".format(table=table)
                    #         if not await cur.execute(sql_update, (-(user['balance_deposit'] - _deposit), user_id)):
                    #             await conn.rollback()
                    #             self.logger.warning('{user_id}增加押金失败'.format(user_id=user_id))
                    #             return False
                # 实时转码商保证金（余额不够平级和升级时）
                # if  _if_deposit == False:
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

    def _request_summary(self):
        user_id = 0
        if self.current_user:
            if 'user_id' in self.current_user.keys():
                user_id = self.current_user['user_id']
            else:
                user_id = self.current_user['id']
        return "%s %s (%s@%s) %s" % (
            self.request.method,
            self.request.uri,
            str(user_id),
            self._get_ip(),
            self.request.protocol + '://' + self.request.host,
        )
    
    async def check_dsdf_lock(self):
        """ 检查代收代付是否对账锁定 ， 锁定为True，未锁定为False """
        # 从redis中查询dsdf_lock_info键
        lock_info = await self.redis.get('dsdf_lock_info')
        
        if not lock_info:
            # 如果redis中没有，查询sys_info表的dsdf_lock字段
            r = await self.get_cache_result('sys_info', ['dsdf_lock'], {"id": 1})
            if r and 'dsdf_lock' in r:
                lock_info = r['dsdf_lock']
                # 更新redis
                await self.redis.set('dsdf_lock_info', lock_info, 3600)

        if lock_info:
            lock_data = json.loads(lock_info)
            switch = lock_data.get('switch', False)
            start_time_str = lock_data.get('start_time', "00:00")
            end_time_str = lock_data.get('end_time', "24:00")

            # 解析开始时间和结束时间
            start_time = datetime.datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.datetime.strptime(end_time_str, "%H:%M").time()

            # 获取当前时间
            current_time = datetime.datetime.now().time()

            # 判断是否开启锁定
            if switch and (start_time <= current_time < end_time):
                return True  # 当前时间被锁定
        return False  # 当前时间未被锁定

    async def build_sql_alert_message(self, sql, args, cost_ms, rowcount=0, line_info='', level='严重预警', name='【ospay_api】 慢查询告警'):
        bot_token = conf['BOT_TOKEN']
        chat_id = conf['GROUP_ID']
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        message = {
            "bot_token": bot_token,
            "chat_id": chat_id,
            "text": f"""⚠️ *{name}*
            *告警等级:* {level}
            *告警时间:* {now}
            *执行ip:* {self._get_ip()}
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

    def get_sql_timeout(self):
        # 避免没配置引起错误，默认一个较大的阈值(ms)
        if 'SQL_TIMEOUT' not in conf:
            default_timeout = 100 * 1000
            self.logger.warning(f'SQL_TIMEOUT not in conf, use default {default_timeout}')
            return default_timeout
        return conf['SQL_TIMEOUT']

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
            if keys != ['*'] and any(key not in data_info for key in keys):
                self.logger.info(f'缓存数据缺少字段，准备刷新： {table} {condition} {keys}')
                data_info = None
        if not data_info:
            data_info = await self.get_result_by_condition(table, ['*'], condition)
            await self.redis.set(redis_key, simplejson.dumps(data_info))
            self.logger.info(f'缓存数据已更新： {table} {condition}')

        data_info = data_info if keys == ['*'] else {key: data_info[key] for key in keys}
        return data_info

    
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
