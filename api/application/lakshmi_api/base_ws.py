import aioredis
import tornado.web
import jwt
import datetime
from config import get_config
from application.client_ip import resolve_client_ip
from application.lakshmi_api.models import User
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
        self.redis_sub = self.application.redis_sub
        self.redis_pub = self.application.redis_pub
        self.secret_key = self.application.secret_key
        self.logger = self.application.logger
        self.redis = self.application.redis
        self.db_orm = self.application.db_orm

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
