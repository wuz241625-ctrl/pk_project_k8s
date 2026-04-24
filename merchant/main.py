import asyncio
import io
import sys
import trace
import uuid

import aiomysql
from redis import asyncio as aioredis
import tornado
import traceback
from tornado.options import define, options
import logging
from logging.handlers import TimedRotatingFileHandler

from application.base import TraceIdFilter
from config import get_config
from router import urls

conf = get_config()

define('port', default='8000', help="run on the given port")
define("logfile", default="merchant.log", help="log file")


class TraceFilter(logging.Filter):
    def __init__(self, name=''):
        super().__init__(name)

    def filter(self, record):
        # 捕获当前调用堆栈
        stack = traceback.format_stack()
        trace_info = ''.join(stack)

        record.trace_info = trace_info
        return True

class Application(tornado.web.Application):
    def __init__(self, db, redispool, logger):
        self.db = db
        self.redis = redispool
        self.logger = logger
        self.api_url = conf['api_url']
        handlers = urls
        settings = dict(
            xsrf_cookies=False,
            cookie_secret=conf['cookie_key'],
            debug=conf['debug'],
            keep_days=7,
        )
        super(Application, self).__init__(handlers, **settings)


async def main():
    tornado.options.parse_command_line()
    loop = asyncio.get_event_loop()
    try:
        # 日志
        log_file = 'logs/' + options.logfile
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        fh = TimedRotatingFileHandler(log_file, when='MIDNIGHT', backupCount=30)

        datefmt = '%Y-%m-%d %H:%M:%S'
        format_str = '[trace_id: %(trace_id)s] [id:%(id)s] %(asctime)s  %(levelname)s %(filename)s  [line: %(lineno)d] %(message)s'
        formatter = logging.Formatter(format_str, datefmt)
        fh.setFormatter(formatter)
        fh.addFilter(TraceIdFilter())
        logger.addHandler(fh)
        # redis连接池
        redis = aioredis.from_url('redis://%s' % conf['redis_host'], encoding="utf-8", decode_responses=True)
        async with await aiomysql.create_pool(
                host=conf['mysql_host'],
                port=3306,
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8',
                autocommit=False,
                maxsize=100,
                minsize=10
        ) as db:
            app = Application(db, redis, logger)
            app.listen(options.port, xheaders=True)
            # In this demo the server will simply run until interrupted
            # with Ctrl-C, but if you want to shut down more gracefully,
            # call shutdown_event.set().
            shutdown_event = tornado.locks.Event()
            await shutdown_event.wait()
    except Exception as e:
        print(e)
        traceback.print_exc()


if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    tornado.ioloop.IOLoop.current().run_sync(main)
