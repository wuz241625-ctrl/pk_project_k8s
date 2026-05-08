import base64
import os
import re
import secrets
import sys
import threading
import time
import uuid
import json
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
import aiohttp
import redis.asyncio as redis
import asyncio
import hashlib
import random
import logging
import simplejson
import traceback
from urllib.parse import quote, urlencode
from typing import List, Dict, Any
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler

# 将项目的主目录添加进系统path
root_dir = os.path.dirname(__file__)  # jobs/easypaisa
root_dir = os.path.dirname(root_dir)  # jobs
root_dir = os.path.dirname(root_dir)  # api根目录
sys.path.append(root_dir)
import config
conf = config.get_config()

# 程序名称（用于日志）
PROGRAM_NAME = 'update_payment_balance'
# 自定义日志记录器 - 添加程序名和函数名
class ProgramLogger(logging.Logger):
    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1):
        # 获取调用者的函数名
        import inspect
        frame = inspect.currentframe()
        # 向上查找3层调用栈来跳过logging相关的函数
        for _ in range(3):
            if frame is not None:
                frame = frame.f_back
        func_name = frame.f_code.co_name if frame is not None else 'unknown'

        # 添加程序名和函数名到消息前缀
        msg = f"[{PROGRAM_NAME}][{func_name}] {msg}"
        super()._log(level, msg, args, exc_info, extra, stack_info, stacklevel)

# 日志配置
LOG_LEVEL = logging.ERROR          # 日志级别
LOG_DIR   = './'                   # 日志目录
LOG_FILE  = f'{PROGRAM_NAME}.log'  # 日志文件名

# 注册自定义日志记录器
logging.setLoggerClass(ProgramLogger)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Handler 1：输出到控制台
console_handler = logging.StreamHandler()
console_handler.setLevel(LOG_LEVEL)

# Handler 2：输出到文件（按大小滚动，最大 10MB，保留 5 个备份）
file_handler = RotatingFileHandler(
    filename=os.path.join(LOG_DIR, LOG_FILE),
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=0,
    encoding='utf-8'
)
file_handler.setLevel(LOG_LEVEL)

# 统一格式
formatter = logging.Formatter(
    fmt='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# 挂载 handler
logger.addHandler(console_handler)
logger.addHandler(file_handler)

easypaisa_api_url = conf.get("easypaisa_api_url")
easypaisa_user_id = conf.get("easypaisa_user_id")
easypaisa_secret_key = conf.get("easypaisa_secret_key")
jazzcash_api_url = conf.get("jazzcash_api_url")
jazzcash_user_id = conf.get("jazzcash_user_id")
jazzcash_secret_key = conf.get("jazzcash_secret_key")

def makeEpRequestData(payload: dict):
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    sign = hashlib.md5((data + easypaisa_secret_key).encode()).hexdigest()
    data = {
        "user_id": easypaisa_user_id,
        "data": data,
        "sign": sign,
    }
    return data
# end

def makeJcbRequestData(payload: dict):
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    sign = hashlib.md5((data + jazzcash_secret_key).encode()).hexdigest()
    data = {
        "user_id": jazzcash_user_id,
        "data": data,
        "sign": sign,
    }
    return data
# end

class BalanceUpdateMonitor:
    def __init__(self, name):
        self.name = name
        self.hash_key = f"hash_{name}"
        self.set_key = f"set_{name}"
        self.lock_time = 30 # 操作锁的锁定时间
        self.logger = logger

        # 默认检查间隔配置（5分钟）
        self.check_interval = 300  # 5分钟检查一次

        # 连接redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, decode_responses=True)

    # ==================== EasyPaisa 自动代付监控相关方法 ====================

    async def get_online_ep_payments_from_db(self):
        """从数据库获取在线状态的ep payment账号"""
        import pymysql

        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT id, phone, account, name, bank_type, bank_type_id, partner_id, status, certified,
                               account_accno
                        FROM payment 
                        WHERE status = 1 
                          AND (bank_type = 97 OR bank_type_id = 97)
                          AND account_accno IS NOT NULL 
                          AND account_accno != ''
                        ORDER BY id
                    """

                    cur.execute(sql)
                    results = cur.fetchall()

                    self.logger.info(f"从数据库获取到 {len(results)} 个在线payment账号")
                    return results

            finally:
                connection.close()

        except Exception as e:
            self.logger.error(f"从数据库获取payment账号失败: {e}")
            return []

    async def get_online_jcb_payments_from_db(self):
        """从数据库获取在线状态的jcb payment账号"""
        import pymysql

        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            try:
                with connection.cursor() as cur:
                    sql = """
                        SELECT id, phone, account, name, bank_type, partner_id, status, certified,
                               account_accno
                        FROM payment 
                        WHERE status = 1 
                          AND certified = 1
                          AND bank_type = 98
                          AND account_accno IS NOT NULL 
                          AND account_accno != ''
                        ORDER BY id
                    """

                    cur.execute(sql)
                    results = cur.fetchall()

                    self.logger.info(f"从数据库获取到 {len(results)} 个在线payment账号")
                    return results

            finally:
                connection.close()

        except Exception as e:
            self.logger.error(f"从数据库获取payment账号失败: {e}")
            return []

    async def main(self):
        try:
            online_ep_payments = await self.get_online_ep_payments_from_db()
            online_jcb_payments = await self.get_online_jcb_payments_from_db()

            async def update_ep_balance(sem: asyncio.Semaphore, payment_id: str, phone: str, accno: str):
                async with sem:
                    try:
                        payload = {
                            "id": str(uuid.uuid4()),
                            "action": "queryBalance",
                            "payload": {
                                "account_id": phone,
                                "accno": accno,
                            }
                        }
                        async with aiohttp.ClientSession(
                            timeout=aiohttp.ClientTimeout(total=30),
                            connector=aiohttp.TCPConnector(ssl=False)
                        ) as session:
                            async with session.post(easypaisa_api_url, data=makeEpRequestData(payload)) as resp:
                                text = await resp.text()
                                logger.info(text)
                                res = simplejson.loads(text)
                                await self.redis.zadd("easypaisa_balance_sorted", {payment_id: float(res["data"]["body"]["totalbalance"])})
                    except Exception as e:
                        logger.info(f"ep {phone} 更新失败，下次再试:" + str(e))

            async def update_jcb_balance(sem: asyncio.Semaphore, payment_id: str, phone: str):
                async with sem:
                    try:
                        payload = {
                            "id": str(uuid.uuid4()),
                            "action": "queryBalance",
                            "payload": {
                                "account_id": phone,
                            }
                        }
                        async with aiohttp.ClientSession(
                            timeout=aiohttp.ClientTimeout(total=30),
                            connector=aiohttp.TCPConnector(ssl=False)
                        ) as session:
                            async with session.post(jazzcash_api_url, data=makeJcbRequestData(payload)) as resp:
                                text = await resp.text()
                                logger.error(text)
                                res = simplejson.loads(text)
                                await self.redis.zadd("jazzcash_balance_sorted", {payment_id: float(res["data"]["data"]["avaliableBalance"])})
                    except Exception as e:
                        logger.error(f"jcb {phone} 更新失败，下次再试:" + str(e))

            sem = asyncio.Semaphore(20)
            tasks = []
            for ep in online_ep_payments:
                logger.error("添加EP更新余额任务: %s %s %s", ep["id"], ep["phone"], ep["account_accno"])
                tasks.append(update_ep_balance(sem, ep["id"], ep["phone"], ep["account_accno"]))
            for jcb in online_jcb_payments:
                logger.error("添加JCB更新余额任务: %s %s", jcb["id"], jcb["phone"])
                tasks.append(update_jcb_balance(sem, jcb["id"], jcb["phone"]))

            random.shuffle(tasks)  # 随机摇匀避免顺序固定

            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
            except asyncio.TimeoutError:
                logger.error("单次任务超时，剩余任务已放弃")

        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('main过程错误： 错误详情：{}\n{}'.format(e, error_message))


# 主程序入口
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    try:
        logger.error(f"{'=' * 10}银行卡余额自动更新系统启动{'=' * 10}")
        monitor = BalanceUpdateMonitor("balance_update_monitor")
        # 定期输出日志统计（如果使用异步处理器）
        last_stats_time = time.time()

        # 主循环
        while True:
            start = time.time()
            try:
                loop.run_until_complete(monitor.main())
            except KeyboardInterrupt:
                logger.error("程序被用户中断")
                break
            except Exception as e:
                tb_str = traceback.format_exc()
                error_message = ''.join(tb_str)
                logger.error('main 循环程序运行错误： 错误详情：{}\n{}'.format(e, error_message))
            finally:
                elapsed = time.time() - start
                wait = max(0, 20 - int(elapsed))
                logger.error(f"任务耗时 {elapsed:.2f}s，等待 {wait:.2f}s 后再次执行")
                time.sleep(wait)
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logger.error('main 程序启动错误： 错误详情：{}\n{}'.format(e, error_message))
