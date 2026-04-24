import tornado.web
from config import get_config
from application.lakshmi_api.models import User
from tornado.options import define, options
import uuid

conf = get_config()

ALLOWED_ORIGINS = conf['websocket_api_allow_host']


class WebsocketBaseHandler(tornado.web.RequestHandler):
    def initialize(self):
        options.RQ_ID = 0
        options.TRACE_ID = str(uuid.uuid4().hex)

    def set_default_headers(self) -> None:
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Credentials', 'true')
        self.set_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS, PUT, PATCH')
        self.set_header('Access-Control-Allow-Headers',
                        'Origin, X-Requested-With, Content-Type, Accept, x-csrftoken, Authorization, Pragma, '
                        'cache-control, expires')
        self.set_header('Access-Control-Max-Age', '360000')
        self.set_header('Content-Type', 'application/json')

    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()

    async def prepare(self):
        origin = self.request.headers.get('Host')
        if origin not in ALLOWED_ORIGINS:
            self.send_error(403)

        self.redis_pub = self.application.redis_pub
        self.redis_sub = self.application.redis_sub
        self.secret_key = self.application.secret_key
        self.logger = self.application.logger
        self.redis = self.application.redis
        self.db_orm = self.application.db_orm

    def on_finish(self):
        pass

    def get_current_user(self, token=None):
        if token:
            with self.db_orm.sessionmaker() as session:
                partner = session.query(User).filter_by(authentication_token=token).first()
                if partner:
                    return partner
                else:
                    return None
        return None

    def get_query_argument(self, name, default=None, strip=True):
        arg_value = super().get_query_argument(name, default=default, strip=strip)
        return None if arg_value == "" else arg_value

    def set_value_to_integer(self, key, default_value):
        value = self.request.arguments.get(key)
        if value is not None:
            value = value[0].decode()
        return int(value) if (value and value.isdigit()) else default_value

    def _get_params(self, keys):
        params = {}
        for key in keys:
            params[key] = self.get_body_argument(key, default=None)
        return params
