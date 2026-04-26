import asyncio
import os
import sys
import threading

import aiomysql
import ipdb
from redis import asyncio as aioredis
import aioredis as aioredis_ws
import tornado
import traceback
from tornado.options import define, options
import logging
from logging.handlers import TimedRotatingFileHandler

from application.base import TraceIdFilter
from application.phonepe import redissub
from config import get_config
from router import urls
from router_lakshmi import prefixed_urls
from tornado_sqlalchemy import SQLAlchemy
from sqlalchemy.engine.url import URL
from constants import RedisKeys
import global_resources
conf = get_config()
define('port', default='9000', help="run on the given port")
define("logfile", default="api.log", help="log file")
ipip = ipdb.City('ipipfree.ipdb')


class Application(tornado.web.Application):
    def __init__(self, db, db_orm, redispool, redis_pub, redis_sub, logger):
        self.db = db
        self.db_orm = db_orm
        self.redis = redispool
        self.redis_pub = redis_pub
        self.redis_sub = redis_sub
        self.logger = logger
        self.pay_url = conf['pay_url']
        self.order_token_key = conf['key_order']
        self.secret_key = conf['secret_key']
        self.ipip = ipip
        handlers = urls + prefixed_urls
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "template"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=False,
            debug=conf['debug'],
            keep_days=7,
            autoreload=conf['autoreload']
        )
        super(Application, self).__init__(handlers, **settings)

    async def _init_business(self):
        # 启动时一些redis之类易失缓存的初始化工作
        # 注意多进程时这个函数会被多次执行，因此需要兼容可反复执行的初始化操作
        notice_domain_api_list_key = 'notice_domain_api_list'
        notice_domain_api_list = await self.redis.get(notice_domain_api_list_key)
        if not notice_domain_api_list:
            default_notice_host = conf.get('ospay_api_host', '').strip()
            if default_notice_host:
                await self.redis.set(notice_domain_api_list_key, default_notice_host)
                self.logger.info('API启动初始化工作：通知回调域名已写入缓存：{}'.format(default_notice_host))

        target_payment_key = 'target_payment_key'
        async with self.db.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT target_payment FROM merchant "
                    "WHERE target_payment IS NOT NULL AND target_payment != '';"
                )
                target_payment_list = await cur.fetchall()
        target_payment_set = set()
        for row in target_payment_list:
            for single_id in row['target_payment'].split(','):
                if single_id.strip():
                    target_payment_set.add(single_id)
        target_payment_str = ','.join(target_payment_set)
        await self.redis.set(target_payment_key, target_payment_str)
        self.logger.info('API启动初始化工作：商户指定码已更新缓存：{}'.format(target_payment_str))



async def main():
    tornado.options.parse_command_line()
    # loop = asyncio.get_event_loop()
    try:
        # 日志
        log_file = 'logs/' + options.logfile
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        fh = TimedRotatingFileHandler(log_file, when='MIDNIGHT', backupCount=30, encoding='utf-8')
        sh = logging.StreamHandler()

        datefmt = '%Y-%m-%d %H:%M:%S'
        format_str = '[trace_id: %(trace_id)s] [id:%(id)s] [PID: %(process)d] %(asctime)s  %(levelname)s %(filename)s  [line: %(lineno)d] %(message)s'
        formatter = logging.Formatter(format_str, datefmt)
        fh.setFormatter(formatter)
        sh.setFormatter(formatter)
        fh.addFilter(TraceIdFilter())
        logger.addHandler(fh)
        logger.addHandler(sh)

        logger.info(f"{'=' * 10}服务启动{'=' * 10}")

        # redis连接池
        redis = aioredis.from_url('redis://%s' % conf['redis_host'], encoding="utf-8", decode_responses=True)
        # redis启动后，删除旧的 websocket 连接信息
        await redis.delete(RedisKeys.REDIS_WS_CLIENTS)

        redis_pub = await aioredis_ws.create_redis((conf['redis_host'], 6379))
        redis_sub = await aioredis_ws.create_redis((conf['redis_host'], 6379))
        
        db_orm = SQLAlchemy()
        db_orm.configure(
            url=URL(
                drivername='mysql+pymysql',
                username=conf['mysql_user'],
                password=conf['mysql_password'],
                port=3306,
                host=conf['mysql_host'],
                database=conf['mysql_database'],
                query={'charset': 'utf8'}
            ),
            engine_options={
                "pool_size": 20,
                "max_overflow": 10,
                "echo": True,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
                "connect_args": {
                    "connect_timeout": 60,
                    "read_timeout": 30,
                    "write_timeout": 30,
                }
            }
        )
        global_resources.redis = redis
        global_resources.db_orm = db_orm
        global_resources.redis_pub = redis_pub
        global_resources.redis_sub = redis_sub
        global_resources.logger = logger
        async with await aiomysql.create_pool(
                host=conf['mysql_host'],
                port=3306,
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8',
                autocommit=False,
                maxsize=100,
                minsize=10,
                pool_recycle=3600,
                connect_timeout=60
        ) as db:
            app = Application(db, db_orm, redis, redis_pub, redis_sub, logger)
            await app._init_business()  # 做一些业务级别的启动初始化工作
            app.listen(options.port, xheaders=True)
            shutdown_event = tornado.locks.Event()
            await shutdown_event.wait()
    except Exception:
        traceback.print_exc()


if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # 订阅
    thread_loop = asyncio.new_event_loop()
    t = threading.Thread(target=redissub.main, args=(thread_loop,))
    t.daemon = True
    t.start()
    tornado.ioloop.IOLoop.current().run_sync(main)
