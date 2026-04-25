from decimal import Decimal
from random import random
import json

import tornado.web
import jwt
import datetime

from sqlalchemy import text

from application.client_ip import resolve_client_ip
from application.lakshmi_api.models import User, BalanceRecord
from config import get_config
from tornado.options import define, options
import uuid

conf = get_config()


class ApiError(Exception):
    pass


class ApiInfo(Exception):
    pass


class BearerTokenError(Exception):
    pass


class BaseHandler(tornado.web.RequestHandler):
    def initialize(self):
        options.RQ_ID = 0
        options.TRACE_ID = str(uuid.uuid4().hex)

    def set_default_headers(self) -> None:
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS, PUT, PATCH')
        self.set_header('Access-Control-Allow-Headers',
                        'Origin, X-Requested-With, Content-Type, Accept, x-csrftoken, Authorization, Pragma, cache-control, expires')
        self.set_header('Access-Control-Max-Age', '360000')
        self.set_header('Content-Type', 'application/json')

    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()

    async def prepare(self):
        self.secret_key = self.application.secret_key
        self.redis = self.application.redis
        self.logger = self.application.logger
        self.db_orm = self.application.db_orm
        self.redis_pub = self.application.redis_pub
        self.redis_sub = self.application.redis_sub

    async def check_ip_access_frequency(self, max_requests, window_seconds):
        """
        检查ip访问频率
        max_requests: 最大请求次数
        window_seconds: 时间窗口（秒）
        """
        client_ip = await self.get_ip()
        rate_limit_key = f"rate_limit_{client_ip}"

        count = await self.redis.incr(rate_limit_key)
        if count == 1:
            # 设置过期时间窗口
            await self.redis.expire(rate_limit_key, window_seconds)

        if count > max_requests:
            self.logger.warning('IP {} 请求频繁，已被限制请求'.format(client_ip))
            self.set_status(403)
            await self.finish()

    async def check_user_access_frequency(self, max_requests, window_seconds):
        """
        检查用户访问频率，需调用前置方法： await self.authenticate_current_user()
        max_requests: 最大请求次数
        window_seconds: 时间窗口（秒）
        """
        rate_limit_key = f"rate_limit_user_{self.current_user.id}"
        count = await self.redis.incr(rate_limit_key)
        if count == 1:
            # 设置过期时间窗口
            await self.redis.expire(rate_limit_key, window_seconds)

        if count > max_requests:
            self.logger.warning('用户 {} 请求频繁，已被限制请求'.format(self.current_user.id))
            return False
        return True

    def on_finish(self):
        pass

    async def get_ip(self) -> object:
        return resolve_client_ip(self.request.headers, self.request.remote_ip)

    async def encode_jwt_token(self, value, days=30):
        dic = {
            'exp': datetime.datetime.now() + datetime.timedelta(days=days),
            'id': value
        }
        return jwt.encode(dic, self.secret_key)

    # 解码token
    async def decode_jwt_token(self, token):
        result = jwt.decode(token, self.secret_key, 'HS256')
        return result['exp'], result['id']

    @property
    async def get_bearer_token(self):
        authorization_header = self.request.headers.get('Authorization')
        if authorization_header:
            parts = authorization_header.split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                return parts[1]
            else:
                return None

    async def async_get_current_user(self):
        token = await self.get_bearer_token
        if token:
            with self.db_orm.sessionmaker() as session:
                partner = session.query(User).filter_by(authentication_token=token).first()
                if partner:
                    return partner
                else:
                    return None
        return None

    def get_current_user(self, token=None):
        if token:
            with self.db_orm.sessionmaker() as session:
                partner = session.query(User).filter_by(authentication_token=token).first()
                if partner:
                    return partner
                else:
                    return None
        return None

    async def authenticate_current_user(self):
        token = await self.get_bearer_token
        with self.db_orm.sessionmaker() as session:
            self.current_user = session.query(User).filter_by(authentication_token=token).first()

        if token is None or self.current_user is None:
            raise BearerTokenError

    def get_query_argument(self, name, default=None, strip=True):
        arg_value = super().get_query_argument(name, default=default, strip=strip)
        return None if arg_value == "" else arg_value

    def set_value_to_integer(self, key, default_value):
        value = self.request.arguments.get(key)
        if value is not None:
            value = value[0].decode()
        return int(value) if (value and value.isdigit()) else default_value

    async def validate_user_active(self):
        if self.current_user.status == 0:
            raise ApiError("Please contact customer Service to ACTIVE your account")

    @staticmethod
    async def is_null(data, args):
        keys = data.keys()
        for i in args:
            if i not in keys or not data[i] and data[i] != 0:
                return True
        return False

    # 余额变动
    async def change_balance(self, session, table, user_id, amount, code, record_type, remark=None, merchant_code=None):
        sql_update = text('update {table} set balance=balance + :amount where id = :user_id'.format(table=table))
        sql_select =  text("""select balance{other} from {table} where id = :user_id""".format(table=table,
                                                                                   other=',vip' if table == 'partner' else ''))
        sql_insert = text("""insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s)""")
        sql_select_vip = text("""select vip,conditions from vip""")
        sql_update_vip = text("""update partner set vip=:vip where id = :user_id""")
        sql_select_orders = text("""SELECT  merchant_code FROM orders_df WHERE code = '{code}' UNION SELECT merchant_code  FROM orders_ds WHERE code = '{code}'""".format(
            code=code))
        try:
            _before = session.execute(sql_select, {'user_id': user_id}).fetchone()
            if not _before:
                await session.rollback()
                # self.logger.warning(cur._last_executed)
                return False
            if not session.execute(sql_update, {'amount': amount, 'user_id': user_id}):
                await session.rollback()
                # self.logger.warning(cur._last_executed)
                return False
            # self.logger.info('更改金额{sql}'.format(sql=cur._last_executed))
            user = session.execute(sql_select, {'user_id': user_id}).fetchone()
            if not user:
                await session.rollback()
                # self.logger.warning(cur._last_executed)
                return False
            partner_balance = 0
            _after = user[0]
            if Decimal(_after) < partner_balance:
                await session.rollback()
                return False
            user_type = 0 if table == 'partner' else 1
            self.logger.info('查询商户订单号{merchant_code}'.format(merchant_code=merchant_code))
            if merchant_code is None:
                merchant_code = session.execute(sql_select_orders).fetchone()

            # 保存balance_record
            new_balance_record = BalanceRecord(
                serial_number=code,
                user_id=user_id,
                user_type=user_type,
                change_before=_before[0],
                amount=amount,
                change_after=_after,
                record_type=record_type,
                remark=remark,
                merchant_code=merchant_code
            )
            session.add(new_balance_record)

            # self.logger.info('新增流水{sql}'.format(sql=cur._last_executed))
            # vip
            if table == 'partner' and amount > Decimal(0):
                _vip = 0
                # _deposit = 0
                vips = session.execute(sql_select_vip).fetchall()
                if not vips:
                    session.rollback()
                    # self.logger.warning(cur._last_executed)
                    return False

                for i in vips:
                    if _after >= i[1]:
                        _vip = i[0]
                    #     _deposit = i['conditions'] * Decimal(0.2)
                    # else:
                    #     break
                # _if_deposit = False
                if int(_vip) > user[1]:
                    # _deposit = _deposit.quantize(Decimal('.0000'))
                    if int(_vip) > user[1]:  # 余额够升级时
                        if not session.execute(sql_update_vip, {'vip': _vip, 'user_id': user_id}):
                            await session.rollback()
                            self.logger.warning('{user_id}改变VIP失败'.format(user_id=user_id))
                            return False
            return True
        except Exception as e:
            self.logger.exception(e)
            session.rollback()
            return False

    
    # 创建编码
    def create_code(PRE='R'):
        return PRE + ''.join(str(datetime.now().timestamp()).split('.')) + str(random.randint(1000, 9999))

    # 检查代收代付是否对账锁定 ， 锁定为True，未锁定为False
    async def check_dsdf_lock(self):
        # 从redis中查询dsdf_lock_info键
        lock_info = await self.redis.get('dsdf_lock_info')
        
        if not lock_info:
            # 如果redis中没有，查询sys_info表的dsdf_lock字段
            with self.db_orm.sessionmaker() as session:
                result = session.execute(
                    text('SELECT dsdf_lock FROM sys_info WHERE id = :id'),
                    {'id': 1}
                ).fetchone()
                if result:
                    lock_info = result[0]
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

            # 获取当前时间的小时和分钟
            current_time = datetime.datetime.now().time()

            # 判断是否开启锁定
            if switch and (start_time <= current_time < end_time):
                return True  # 当前时间被锁定
        return False  # 当前时间未被锁定

    async def log_user_and_ip(self, log_str):
        """
        打印接口的操作日志：包括请求方法，请求路径，请求用户id，请求用户ip
        注意： 前置方法 await self.authenticate_current_user() 调用后才能使用此方法
        """
        user_ip = await self.get_ip()
        self.logger.info(
            "[%s] (%s), %s operate log user_id: %s user_ip: %s",
            self.request.method, self.request.uri, log_str, self.current_user.id, user_ip
        )
