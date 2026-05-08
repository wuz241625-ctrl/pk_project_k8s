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
import redis
import asyncio
import hashlib
import random
import logging
import requests
import simplejson
import traceback

import base64
import pymysql

from datetime import datetime

from typing import List, Dict, Any
from logging.handlers import TimedRotatingFileHandler
from requests.adapters import HTTPAdapter

# API_URL = 'http://104.198.86.150:83'
# USER_ID = 'ba08c3c0e4f546ad92dd2c2e8542ca36'
# SECRET_KEY = 'ca45b35e132b46b9b68dd55f1ab077de'

# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)

from response_logger import ResponseLogger
import config
from application.payment_eligibility import can_collect_statement, can_dispatch_df, can_dispatch_ds
from application.lakshmi_api.enums.payment_login_progress import PaymentLoginProgress
from jobs.common.logging_setup import ProgramLogger, TraceIDFilter, setup_high_performance_logging

#jazzcash爬取账单，需要发送短信

# 初始化日志系统
PROGRAM_NAME = 'jazzcashpay_v2'
logger, trace_id_filter, file_handler = setup_high_performance_logging(PROGRAM_NAME, use_async=True)



conf = config.get_config()

# 配置参数
API_SERVER_DOMAIN = getattr(conf, 'ospay_api_host', 'http://localhost:9000')
API_URL = conf['jazzcash_api_url']
USER_ID = conf['jazzcash_user_id']
SECRET_KEY = conf['jazzcash_secret_key']
class BankLogin:
    def __init__(self, name):
        self.name = name
        self.list_key = f"list_{name}"
        self.hash_key = f"hash_{name}"
        self.set_key = f"set_{name}"
        self.lock_time = 30 # 操作锁的锁定时间
        self.time_grab = 40  # 短时间频繁爬取
        self.time_grab2 = 10 * 60  # 长时间爬取
        self.order_time_out = 5 * 60
        self.statement_ds_window_seconds = 7 * 60
        self.statement_df_window_seconds = 10 * 60
        self.statement_df_probe_interval = 2 * 60
        self.check_client_send_sms_time_out = 90  # 等待发送短信的最长时间
        self.try_sendOTP_limit = 3  # 最大尝试发送OTP的次数
        self.try_verify_otp_limit = 2  # 最大尝试验证OTP的次数
        self.try_device_check_limit = 3  # 最大尝试device_check的次数
        self.try_send_sms_limit = 3  # 最大尝试获取短信内容的次数
        self.try_verify_sms_limit = 3  # 最大尝试验证短信的次数
        self.try_count_limit = 10 # 爬取最大重试次数，超过则直接下线
        self.try_upi_limit = 10  # 最大尝试爬取upi的次数，(爬取upi失败还可以爬取账单)-----
        self.order_grab_time_out = 4 * 60 * 60  # 检测爬取的账单时间是否在规定范围内，不是则舍弃
        self.upi_time = 5 * 60  # 隔多久爬取一次upi
        self.domain = API_SERVER_DOMAIN # 接口域名
        self.session = requests.Session()
        self.logger = logger
        self.response_logger = ResponseLogger(logger) # 打印的请求的全部过程日志，包括请求头和返回头等
        self.id = None # 多协程并发，会混用，暂弃用
        self.login_data = None # 多协程并发，会混用，暂弃用
        self.local_mock = False
        # 如果使用异步日志处理器，可以定期检查状态
        self.log_handler = file_handler

        # 连接redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        # 新增: 初始化数据库连接
        self.db_connection = self.check_db_connection()

    def check_db_connection(self):
            """
            检查并返回pymysql数据库连接。
            """
            try:
                connection = pymysql.connect(
                    host=conf['mysql_host'],
                    user=conf['mysql_user'],
                    password=conf['mysql_password'],
                    db=conf['mysql_database'],
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )
                self.logger.info("数据库连接成功")
                return connection
            except Exception as e:
                self.logger.error(f"数据库连接失败: {e}", exc_info=True)
                return None

    def fetch_wallet_collection_rows(self, limit=500):
        if not hasattr(self, "db_connection"):
            return []
        if not getattr(self, "db_connection", None) or not self.db_connection.open:
            self.logger.error("数据库连接已关闭，尝试重新连接...")
            self.db_connection = self.check_db_connection()
            if not self.db_connection:
                return []

        with self.db_connection.cursor() as cur:
            try:
                sql = """
                    SELECT id, phone, partner_id, upi, channel, net_trade_pw
                    FROM payment
                    WHERE wallet_status = 1
                      AND (bank_type = 98 OR bank_type = '98' OR bank_type_id = 98)
                    LIMIT {limit}
                """.format(limit=int(limit))
                cur.execute(sql)
                return cur.fetchall() or []
            except Exception as e:
                self.logger.error(f"查询 JazzCash wallet_status 采集账号失败: {e}", exc_info=True)
                self.db_connection.rollback()
                return []
            finally:
                self.db_connection.commit()

    @staticmethod
    def _first_channel(channel):
        channel = str(channel or "").replace(" ", "")
        if not channel:
            return ""
        return channel.split(",")[0]

    def _wallet_collection_login_data(self, row, existing=None):
        data = existing if isinstance(existing, dict) else {}
        payment_id = row.get("id")
        data.update({
            "id": payment_id,
            "real_payment_id": payment_id,
            "status": "grabstatement",
            "phone": row.get("phone"),
            "partner_id": row.get("partner_id"),
            "upi": row.get("upi"),
            "net_trade_pw": row.get("net_trade_pw"),
            "channel": row.get("channel"),
            "channels": row.get("channel"),
            "qr_channel": self._first_channel(row.get("channel")),
        })
        return data

    def sync_mysql_wallet_collection_accounts(self):
        self.logger.info("JazzCash 已切换为 MySQL 订单窗口调度，不再同步旧 hash/set 采集投影")
        return 0

    def _read_payment_final_state_flags(self, payment_id):
        if not self.db_connection or not self.db_connection.open:
            self.logger.error("数据库连接已关闭，尝试重新连接...")
            self.db_connection = self.check_db_connection()
            if not self.db_connection:
                return None

        with self.db_connection.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, phone, wallet_status, collection_status, payout_status,
                           status, certified, manual_status, channel
                    FROM payment
                    WHERE id = %s
                    """,
                    (payment_id,),
                )
                return cur.fetchone()
            except Exception as e:
                self.logger.error(f"查询 JazzCash MySQL 最终态失败 payment_id={payment_id}: {e}", exc_info=True)
                self.db_connection.rollback()
                return None
            finally:
                self.db_connection.commit()

    def payment_final_state_policy(self, payment_id, login_data=None):
        payment = self._read_payment_final_state_flags(payment_id)
        if not payment:
            return "offline"
        if not can_collect_statement(payment):
            return "offline"

        try:
            ds_enabled = can_dispatch_ds(payment)
            df_enabled = can_dispatch_df(payment)
        except Exception:
            self.logger.error(f"JazzCash payment 状态字段异常 payment_id={payment_id}: {payment}")
            return "offline"

        if ds_enabled and df_enabled:
            return "dispatch_on"
        if ds_enabled and not df_enabled:
            return "df_dispatch_off"
        if not ds_enabled and df_enabled:
            return "ds_dispatch_off"
        return "order_paused"

    def _ensure_db_connection(self):
        if not hasattr(self, "db_connection"):
            return False
        if not getattr(self, "db_connection", None) or not self.db_connection.open:
            self.logger.error("数据库连接已关闭，尝试重新连接...")
            self.db_connection = self.check_db_connection()
        return bool(getattr(self, "db_connection", None))

    def _fetch_rows(self, sql, params=None):
        if not self._ensure_db_connection():
            return []
        with self.db_connection.cursor() as cur:
            try:
                cur.execute(sql, params or ())
                rows = cur.fetchall() or []
                self.db_connection.commit()
                return rows
            except Exception as e:
                self.db_connection.rollback()
                self.logger.error(f"JazzCash MySQL 查询失败: {e}; sql={sql}", exc_info=True)
                return []

    def _fetch_one(self, sql, params=None):
        if not self._ensure_db_connection():
            return None
        with self.db_connection.cursor() as cur:
            try:
                cur.execute(sql, params or ())
                row = cur.fetchone()
                self.db_connection.commit()
                return row
            except Exception as e:
                self.db_connection.rollback()
                self.logger.error(f"JazzCash MySQL 查询失败: {e}; sql={sql}", exc_info=True)
                return None

    def fetch_due_statement_payment_ids(self, limit=200):
        rows = self._fetch_rows(
            """
            SELECT DISTINCT id
            FROM (
                SELECT p.id
                FROM payment p
                JOIN orders_ds od ON od.payment_id = p.id
                WHERE p.wallet_status = 1
                  AND (p.bank_type = 98 OR p.bank_type = '98' OR p.bank_type_id = 98)
                  AND od.status IN (1, 2)
                  AND od.utr IS NOT NULL
                  AND od.utr <> ''
                  AND od.time_create >= DATE_SUB(NOW(), INTERVAL 7 MINUTE)
                UNION
                SELECT p.id
                FROM payment p
                JOIN orders_df ofd ON ofd.payment_id = p.id
                WHERE p.wallet_status = 1
                  AND (p.bank_type = 98 OR p.bank_type = '98' OR p.bank_type_id = 98)
                  AND ofd.status = 2
                  AND ofd.time_accept IS NOT NULL
                  AND ofd.time_accept >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
            ) due_payment
            LIMIT {limit}
            """.format(limit=int(limit))
        )
        payment_ids = []
        for row in rows:
            payment_id = row.get("id")
            if payment_id in [None, ""]:
                continue
            payment_ids.append(str(payment_id))
        return payment_ids

    def fetch_due_statement_scan_context(self, payment_id):
        context = {"payment_id": payment_id, "ds_orders": [], "df_orders": [], "has_due": False, "interval": 60}
        context["ds_orders"] = self._fetch_rows(
            """
            SELECT code, payment_id, partner_id, amount, time_create
            FROM orders_ds
            WHERE payment_id = %s
              AND status IN (1, 2)
              AND utr IS NOT NULL
              AND utr <> ''
              AND time_create >= DATE_SUB(NOW(), INTERVAL 7 MINUTE)
            ORDER BY id DESC
            LIMIT 20
            """,
            (payment_id,),
        )
        context["df_orders"] = self._fetch_rows(
            """
            SELECT code, payment_id, partner_id, amount, time_accept, payment_account, utr
            FROM orders_df
            WHERE payment_id = %s
              AND status = 2
              AND time_accept IS NOT NULL
              AND time_accept >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
            ORDER BY id DESC
            LIMIT 20
            """,
            (payment_id,),
        )
        context["has_due"] = bool(context["ds_orders"] or context["df_orders"])
        context["interval"] = self.statement_df_probe_interval if context["df_orders"] and not context["ds_orders"] else 60
        return context

    def fetch_statement_account_context(self, payment_id):
        row = self._fetch_one(
            """
            SELECT id, phone, partner_id, upi, channel, net_trade_pw
            FROM payment
            WHERE id = %s
              AND wallet_status = 1
              AND (bank_type = 98 OR bank_type = '98' OR bank_type_id = 98)
            LIMIT 1
            """,
            (payment_id,),
        )
        if not row:
            self.logger.info(f"JazzCash {payment_id} MySQL 无可用采集账号上下文，跳过账单查询")
            return None
        account_context = dict(row)
        account_context["id"] = str(payment_id)
        account_context["real_payment_id"] = str(payment_id)
        account_context["status"] = "grabstatement"
        account_context["channels"] = account_context.get("channel")
        account_context["qr_channel"] = self._first_channel(account_context.get("channel"))
        return account_context

    def reserve_due_statement_scan_context(self, context):
        reserved = dict(context)
        reserved_df_orders = []
        for order in context.get("df_orders", []):
            code = order.get("code")
            if not code:
                continue
            lock_key = f"payout_unknown_probe_lock:{self.name}:{code}"
            if self.redis.setnx(lock_key, 1):
                self.redis.expire(lock_key, self.statement_df_probe_interval)
                reserved_df_orders.append(order)
            else:
                self.logger.info(f"JazzCash 代付未知订单 {code} 两分钟探测锁未释放，跳过本轮账单观测")
        reserved["df_orders"] = reserved_df_orders
        reserved["has_due"] = bool(reserved.get("ds_orders") or reserved_df_orders)
        return reserved

    def acquire_statement_wallet_lock(self, payment_id, ttl):
        lock_key = f"statement_scan_lock:{self.name}:{payment_id}"
        if not self.redis.setnx(lock_key, 1):
            self.logger.info(f"JazzCash {payment_id} 账单爬取锁未释放，跳过本轮")
            return False
        self.redis.expire(lock_key, ttl)
        return True

    async def process_statement_payment_id_async(self, payment_id):
        context = self.fetch_due_statement_scan_context(payment_id)
        context = self.reserve_due_statement_scan_context(context)
        if not context.get("has_due"):
            self.logger.info(f"JazzCash {payment_id} 没有待确认订单，跳过账单查询")
            return False

        account_context = self.fetch_statement_account_context(payment_id)
        if not account_context:
            return False

        if not self.acquire_statement_wallet_lock(payment_id, max(60, int(context.get("interval") or 60))):
            return False

        payment_mock = self.redis.get(f"payment_mock:{payment_id}") or self.redis.get(f"payment_mock:{account_context['id']}")
        if payment_mock:
            self.local_mock = True

        self.logger.info(
            f"JazzCash MySQL账单调度处理 payment_id={payment_id}, "
            f"ds_orders={len(context.get('ds_orders') or [])}, df_orders={len(context.get('df_orders') or [])}"
        )
        return await self.grabstatement(account_context, if_first_time=False)

    async def process_statement_payment_ids_concurrent(self, payment_ids: List[str], concurrent_limit: int = 20):
        if not payment_ids:
            return

        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(payment_id):
            async with semaphore:
                return await self.process_statement_payment_id_async(payment_id)

        start_time = time.time()
        results = await asyncio.gather(
            *(process_with_semaphore(payment_id) for payment_id in payment_ids),
            return_exceptions=True,
        )
        end_time = time.time()
        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(
            f"进程 {os.getpid()} JazzCash MySQL账单候选并发处理完成: "
            f"总数 {len(payment_ids)}, 成功 {success_count}, 失败 {len(results) - success_count}, "
            f"异常 {error_count}, 耗时 {end_time - start_time:.2f}秒"
        )

    def sync_job_projection(self, login_data, schedule_score=None):
        payment_id = login_data.get('real_payment_id') or login_data.get('id')
        if payment_id in [None, ""]:
            raise ValueError("sync_job_projection requires payment id")
        projected = dict(login_data)
        projected['id'] = payment_id
        projected['real_payment_id'] = payment_id
        projected['status'] = 'grabstatement'
        self.logger.info(f"{payment_id} JazzCash 旧 hash/set 投影已退役，本次不写入 Redis 调度队列")
        return projected

    def get_log_stats(self):
        """获取日志统计信息（如果使用异步处理器）"""
        """获取日志统计信息"""
        if hasattr(self.log_handler, 'get_stats'):
            return self.log_handler.get_stats()
        elif hasattr(self.log_handler, 'buffer'):
            return {
                'buffer_size': len(self.log_handler.buffer),
                'buffer_bytes': getattr(self.log_handler, 'buffer_bytes', 0),
                'is_running': not getattr(self.log_handler, '_shutdown', False)
            }
        return None

    def init_function(self, exist_logger):
        """初始化函数"""
        try:
            self.session = requests.Session()
            self.session.mount('http://', HTTPAdapter(max_retries=1))
            self.session.mount('https://', HTTPAdapter(max_retries=1))
            self.logger = exist_logger
            # 打印的请求的全部过程日志，包括请求头和返回头等
            self.response_logger = ResponseLogger(exist_logger)
            # 检测是否联通，如果断联需重新连接
            self.local_mock = False
            self.check_redis_connection()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('init_function 脚本运行错误{}\n{}\n'.format(e, error_message))

    def check_redis_connection(self):
        """检查Redis连接"""
        try:
            redis_response = self.redis.ping()
            if not redis_response:
                self.logger.info(f"bank: {self.name},Redis服务未能ping通,3秒后重新连接")
                self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        except Exception as e:
            self.logger.info(f"bank: {self.name},Redis 连接失败,3秒后重试: {e}")
            time.sleep(2)
            self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.check_redis_connection()  # 递归尝试，不恢复连接不进行下一步

    def get_proxies(self):
        return {}
        try:
            _indian_socks_ip = self.redis.get(f'indian_socks_ip_{self.name}')
            if not _indian_socks_ip:
                self.logger.error(f'无 indian_socks_ip_{self.name}')
                return False
            _indian_socks_ip = _indian_socks_ip.decode().split(',')
            _indian_socks_ip = [item for item in _indian_socks_ip if item.strip()]
            proxy = random.choice(_indian_socks_ip)
            proxies = {
                'http': proxy if proxy.startswith('socks5://') else 'socks5://{}'.format(proxy),
                'https': proxy if proxy.startswith('socks5://') else 'socks5://{}'.format(proxy)
            }
            return proxies
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_proxies 脚本运行错误{}\n{}'.format(e, error_message))
            return False

    # 检测代理是否在有效库里
    def check_proxy(self, login_data):
        try:
            _indian_socks_ip = self.redis.get(f'indian_socks_ip_{self.name}')
            if not _indian_socks_ip:
                self.logger.error(f'check_proxy（） 无 indian_socks_ip_{self.name}')
                return False
            _indian_socks_ip = _indian_socks_ip.decode().split(',')
            _indian_socks_ip = [item for item in _indian_socks_ip if item.strip()]
            for i in _indian_socks_ip:
                proxies = {
                    'http': i if i.startswith('socks5://') else 'socks5://{}'.format(i),
                    'https': i if i.startswith('socks5://') else 'socks5://{}'.format(i)
                }
                if proxies == login_data['socks_ip']:
                    self.logger.info(f'check_proxy（） 代理ip仍有效 indian_socks_ip_{self.name}')
                    return proxies
            self.logger.error(f'check_proxy（） 代理ip无效，更新 indian_socks_ip_{self.name}')
            return self.get_proxies()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_proxies 脚本运行错误{}\n{}'.format(e, error_message))
            return False

    def get_lock(self, _id):
        try:
            # 获取锁
            busy_key = '{}_operate_{}'.format(self.name, _id)
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value) # 返回 0 已存在, 1 不存在且设置成功
            if not _lock:
                # 防止死锁
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{_id}, {busy_key} 剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"{_id}, 死锁并删除 {_value}")
                return False
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(f"{_id},{busy_key} 加锁时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, error_message))
            return False

    def del_lock(self, _id, value):
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, _id)
            self.logger.info(f"准备删除Lock {busy_key}")
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(busy_key)
                self.logger.info(f"删除Lock {busy_key}, result: {result}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('del_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, error_message))
            return False

    async def login_off(self, login_data):
        try:
            # 删除hash和set，退出
            self.redis.zrem(self.set_key, login_data['id'])
            self.redis.hdel(self.hash_key, login_data['id'])
            self.redis.delete(f'upi_active_payment:{login_data['id']}') # 结束upi激活的流程
            self.redis.hdel(f'{self.name}_device', login_data['id']) # 删除hash里面的设备值，防止下一次会发送短信失败
            await self.sendMsg('push_payment_information', False, 'Login failed and exit')  # 退出登录进行通知(通知payment状态信息)
            self.on_off(login_data, 0)  # 下线接单
            await self.callbackStatus(login_data)  # 回调status,置payment_id的status为0
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('login_off 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))

    def on_off(self, login_data, _on=1):
        self.logger.info(f"{login_data['id']} on_off(_on={_on}) 处理上下线")
        try:
            if _on == 1:
                self.logger.info(f"{login_data['id']}, {self.list_key} 上线采集：MySQL最终态控制代收/代付资格")
                return True
            self.logger.error(f"{login_data['id']}, {self.list_key} 下线采集：MySQL最终态控制代收/代付资格")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('on_off 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            return False

    def update_key(self, login_data):
        payment_id = login_data.get('id')
        try:
            if payment_id and self.payment_final_state_policy(payment_id, login_data) == "offline":
                self.redis.hdel(self.hash_key, payment_id)
                self.redis.zrem(self.set_key, payment_id)
                self.logger.warning(f"{payment_id} DB wallet_status 已关闭，已清理 JazzCash 旧采集投影")
                return login_data
        except Exception as e:
            self.logger.error(f"{payment_id} JazzCash 旧采集投影清理检查失败: {e}", exc_info=True)
        self.logger.info(
            f"{payment_id} JazzCash 已切换为 MySQL 订单窗口调度，"
            "不再写入 hash_jazzcash/set_jazzcash 旧投影"
        )
        return login_data



    # 打印所有的缓存,比较耗性能,生产环境可注释掉
    def read_cache(self, source, login_data):
        self.logger.info(f"{login_data['id']}, source: {source} 开始读取业务缓存")
        try:
            cache_key_lock = f'{self.name}_operate_{login_data['id']}'
            cache_key_login_on = f'login_on_{self.name}_{login_data['id']}'
            cache_key_upi_active_payment = f'upi_active_payment:{login_data['id']}'
            cache_key_device = f'{self.name}_device'

            self.logger.info(f"{login_data['id']}, read_cache() key: {self.set_key}, 成员 {login_data['id']}, score: {self.redis.zscore(self.set_key, login_data['id'])}, ttl: {self.redis.ttl(self.set_key)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {self.hash_key}, 成员 {login_data['id']}, hash value: {self.redis.hget(self.hash_key, login_data['id'])}, ttl: {self.redis.ttl(self.hash_key)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_lock}, value: {self.redis.get(cache_key_lock)}, ttl: {self.redis.ttl(cache_key_lock)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_login_on}, value: {self.redis.get(cache_key_login_on)}, ttl: {self.redis.ttl(cache_key_login_on)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_upi_active_payment}, value: {self.redis.get(cache_key_upi_active_payment)}, ttl: {self.redis.ttl(cache_key_upi_active_payment)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {self.hash_key}, 成员 {login_data['id']}, hash value: {self.redis.hget(cache_key_device, login_data['id'])}, ttl: {self.redis.ttl(cache_key_device)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('read_cache 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))

    # 打印集合中所有的元素,生产环境可注释掉
    def read_zset(self, key):
        # 获取有序集合中的所有元素及其分数
        # withscores=True 表示返回元素及其分数
        elements_with_scores = self.redis.zrange(key, 0, -1, withscores=True)
        # 将元素和分数存储到字典中
        result_dict = {element.decode(): score for element, score in elements_with_scores}
        self.logger.info(f"read_zset() zset key: {key},共{len(result_dict)}个 value: {result_dict}")

    # 原 call_api_server
    async def sendMsg(self, login_data, type: str = "", status=False, value=None):
        self.logger.info(f"type: {type}, status: {status}, value: {value}")
        try:
            if type in [
                'get_transaction_history',
                'sync_a_transaction_record',
                PaymentLoginProgress.SEND_SMS_CHECK.name.lower(),
                PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(),
                PaymentLoginProgress.GET_PROFILE.name.lower(),
                PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(),
            ]:
                url = self.domain + '/v1/websocket/payment_protocol_status_notify'

                publish_data = {
                    'type': type,
                    'is_success': status,
                    'payment_id': login_data['id'],
                    'error_code': value.get("error_code", "") if isinstance(value, dict) else "",
                    'error_msg': value.get("error_message", "") if isinstance(value, dict) else (
                        value if isinstance(value, str) else ""),
                }

                return await self.notify(url, publish_data, login_data)

            elif type == 'send_otp':
                if status:
                    # OTP发送成功的通知
                    url = self.domain + '/v1/websocket/push_upi_opt_success'
                    publish_data = {
                        'id': login_data['id']
                    }
                else:
                    # OTP发送失败
                    url = self.domain + '/v1/websocket/push_upi_opt_fail'
                    publish_data = {
                        'id': login_data['id'],
                        'error_message': value
                    }
                return await self.notify(url, publish_data, login_data)

            elif type == 'push_payment_information':
                # 通知payment状态
                url = self.domain + '/v1/websocket/push_payment_information'
                publish_data = {
                    'id': login_data['id']
                }
                if not await self.notify(url, publish_data, login_data):
                    return False
                url = self.domain + '/v1/websocket/push_message_to_user'
                publish_data = {
                    'id': login_data['partner_id'],
                    'message': value
                }
                return await self.notify(url, publish_data, login_data)

            elif type == 'push_message_to_user':
                url = self.domain + '/v1/websocket/push_message_to_user'
                publish_data = {
                    'id': login_data['partner_id'],
                    'message': value
                }
                return await self.notify(url, publish_data, login_data)

            elif type == 5:
                url = self.domain + '/v1/websocket/payment_bind_upi_success'
                if status == 0:
                    url = self.domain + '/v1/websocket/push_cancel_payment_get_upi'
                publish_data = {
                    'id': login_data['id']
                }
                return await self.notify(url, publish_data, login_data)

            elif type == 'get_send_sms_info':
                url = self.domain + '/v1/websocket/get_send_sms_info'

                publish_data = {
                    'payment_id': login_data['id']
                }

                if status is True:
                    publish_data['to_phone'] = value['receive_sms_number']
                    publish_data['content'] = value['receive_sms_content']
                else:
                    publish_data['error_code'] = value['error_code']
                    publish_data['error_msg'] = value['error_message']

                return await self.notify(url, publish_data, login_data)

            return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('sendMsg 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            return False

    async def _post_url(self, url, data, login_data):
        """Direct aiohttp POST with retry once on failure."""
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30),
                    connector=aiohttp.TCPConnector(ssl=False)
                ) as session:
                    async with session.post(url, data=data, headers=headers) as resp:
                        if 200 <= resp.status < 300:
                            text = await resp.text()
                            return text
            except Exception as e:
                self.logger.error(f"网络请求错误: uid: {login_data['id']}; {e}")
            if attempt == 0:
                await asyncio.sleep(0.5)
        return None

    # 通知前端 原 call_api
    async def notify(self, url, publish_data, login_data):
        try:
            self.logger.info(f"url: {url}, publish_data: {publish_data}")
            text = await self._post_url(url, publish_data, login_data)
            if text is None:
                self.logger.error(f"{login_data['id']}, 发送{self.list_key} 通知url：{json.dumps(publish_data)} 结果：None")
                return False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('notify 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            return False

    # 调用API接口 /order/Success 用以修改status状态 原 call_api_order_success
    async def send(self, orders_send, login_data):
        result = {"is_success": False}
        try:
            url = self.domain + '/order/Success'
            self.logger.info(f"{login_data['id']},send()发起请求：{url}, data: {orders_send}")
            text = await self._post_url(url, orders_send, login_data)
            if text is None:
                error_message = f"error:{login_data['id']}, send {self.list_key}, callback message：None"
                self.logger.error(error_message)
                result['error_message'] = error_message
                return result
            self.logger.info(f"{login_data['id']}, 发送{self.list_key}回调信息：{text}")
            _res = simplejson.loads(text)

            # 如果是10025 upi重复，则直接下线
            if 'type' in orders_send and orders_send['type'] == 'UPI' and _res['code'] == 10025:
                orders_send['id'] = orders_send['payment_id']
                await self.sendMsg(login_data, 'push_payment_information', False, 'upi already exist')
                await self.login_off(login_data)
                self.logger.info(f"{login_data['id']}, {self.list_key} 更新upi重复，下线:{login_data['id']}, 结果：{text}")

            if _res['code'] == 100:
                result["is_success"] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('send 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
        return result

    # 用以修改payment_id的status状态 原 set_payment_status0
    async def callbackStatus(self, login_data):
        try:
            self.logger.info(f"callbackStatus: {login_data}")
            # status状态修改
            orders_send = {
                'type': 'status',
                'bank_name': self.name,
                'payment_id': login_data['id'],
                'partner_id': login_data['partner_id'],
                'status': 0,
                'remarks': login_data.get('remarks')
            }
            # 记录发送前的日志
            self.logger.info(f"payment_id: {login_data['id']} 正在尝试发送状态更新请求: {simplejson.dumps(orders_send)}")

            if_send = await self.send(orders_send, login_data)
            # 记录第一次发送后的日志
            self.logger.info(f"payment_id: {login_data['id']} 第一次状态更新请求返回: {simplejson.dumps(if_send)}")

            if if_send['is_success'] is False:
                # time.sleep(0.5)
                await asyncio.sleep(0.5)
                if_send = await self.send(orders_send, login_data)
            if if_send['is_success'] is True:
                self.logger.info(f"payment_id: {login_data['id']}, status状态修改成功：{simplejson.dumps(orders_send)}")
            else:
                self.logger.info(f"payment_id: {login_data['id']}, status状态修改失败：{simplejson.dumps(orders_send)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{login_data['id']}, callbackStatus 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(login_data)}')
            return False

    # 获取upi 原get_upi
    async def grabUpi(self, login_data):
        # 当前 JazzCash 采集不再走旧 Indus UPI 查询流程，保持成功让账单采集继续。
        return {"is_success": True}

    # 抓取账单 原 transaction_history
    async def getBills(self, login_data):
        if self.local_mock:
            return {"is_success": True}

        self.logger.info(f"payment_id: {login_data['id']}, getBills")
        result = {"is_success": False}
        try:
            account_id = login_data.get('phone', '')
            if not account_id:
                self.logger.error(f"{login_data['id']}, 无有效的account_id，无法查询账单")
                return result
            payment_id = login_data['id']
            if not payment_id:
                self.logger.error("回调数据中缺少 payment_id。")
                return result

            # 调用 get_payment_info 方法获取账户信息
            # account_selected = self.get_payment_info(payment_id)
            payload = {"id": str(uuid.uuid4()), "action": "queryBill", "payload": {"account_id": account_id}}
            payload_str = json.dumps(payload, separators=(',', ':'))
            data_base64 = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
            sign_str = data_base64 + SECRET_KEY
            sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
            request_data = {'user_id': USER_ID, 'data': data_base64, 'sign': sign}
            # 详细的请求前日志
            self.logger.info("--- 请求详情 ---")
            self.logger.info(f"请求域名: {API_URL}")
            self.logger.info(f"Payload JSON: {payload_str}")
            self.logger.info(f"Base64 编码: {data_base64}")
            self.logger.info(f"签名字符串: {sign_str}")
            self.logger.info(f"签名: {sign}")
            self.logger.info(f"请求数据 (FormBody 字典): {request_data}")
            self.logger.info("-------------------\n")
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(API_URL, data=request_data) as response:
                        # 检查HTTP状态码
                        if response.status != 200:
                            self.logger.error(f"{login_data['id']}, queryBill API请求失败，HTTP状态码: {response.status}")
                            self.logger.error(f"响应内容（原始文本）:\n{await response.text()}")
                            result['error_code'] = response.status
                            result['error_message'] = await response.text()
                            return result
                        # 检查Content-Type
                        content_type = response.headers.get('Content-Type', '')
                        if 'application/json' not in content_type:
                            self.logger.error(f"{login_data['id']}, API响应非JSON格式，Content-Type: {content_type}")
                            self.logger.error(f"响应内容（原始文本）:\n{await response.text()}")
                            result['error_code'] = 'invalid_content_type'
                            result['error_message'] = f"非JSON格式，Content-Type: {content_type}"
                            return result
                        response_data = await response.json()
                        self.logger.info(f"--- API响应成功 ---")
                        self.logger.info(json.dumps(response_data, indent=4, ensure_ascii=False))
                        # 检查API返回的业务码
                        if response_data.get('code') != 200:
                            self.logger.error(f"{login_data['id']}, queryBill失败: {response_data.get('msg')}")
                            result['error_code'] = response_data.get('code')
                            result['error_message'] = response_data.get('msg')
                            # if response_data.get('code') in [423]:
                            #     await asyncio.sleep(2)
                            #     return await self.getBills(login_data)
                            return result
                        # transactionHistoryList = response_data.get('data', {}).get('body', {}).get('transactionHistory', [])
                        transactionHistoryList = response_data.get('data', {}).get('data', [])
                        self.logger.info(f"{login_data['id']}, 爬取交易记录：{transactionHistoryList}")
                        if not transactionHistoryList:
                            result['transaction_history_list'] = []
                        else:
                            # 按照交易时间正序排序 可不用排序
                            # transactionHistoryList = sorted(
                            # transactionHistoryList,
                            # key=lambda x: datetime.strptime(x['trnDate'], '%d-%m-%Y %I:%M:%S %p')
                            # )
                            result['transaction_history_list'] = transactionHistoryList
                        result['is_success'] = True
                except aiohttp.ClientError as e:
                    self.logger.error(f"{login_data['id']}, 请求失败: {e}")
                    result['error_message'] = str(e)
                    return result
                except json.JSONDecodeError as e:
                    self.logger.error(f"{login_data['id']}, API响应JSON解析失败: {e}")
                    result['error_message'] = str(e)
                    return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{login_data['id']}, getBills() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(login_data)}')
            result['error_message'] = error_message
        return result

    # 爬取账单和upi
    async def grabstatement(self, login_data, if_first_time=False):
        try:
            login_data['time'] = int(time.time())
            login_data['count'] = 1 if 'count' not in login_data else login_data['count'] + 1

            #  爬取upi
            if 'upi_time' not in login_data or login_data['upi_time'] + self.upi_time < int(time.time()):
                # if 'upi_time' not in login_data: # 暂时只爬取一次
                grabUpi = await self.grabUpi(login_data)
                if grabUpi['is_success'] is False:
                    # time.sleep(0.5)
                    await asyncio.sleep(0.5)
                    grabUpi = await self.grabUpi(login_data)
                if grabUpi['is_success'] is False:
                    login_data['upi_try'] = 1 if 'upi_try' not in login_data else login_data['upi_try'] + 1
                    self.logger.info(f"{login_data['id']} 爬取upi失败：" + simplejson.dumps(login_data))
                    self.on_off(login_data, 0)
                    # login_data['upi_try_fail'] = 1  # 标定是否upi爬取失败
                    login_data['upi_time'] = int(time.time()) - 4 * 60  # 更新时间，否则爬取失败会一直爬取，约1分钟爬取一次
                    login_data['time'] = int(time.time()) - self.time_grab2 + 1 * 60  # 更新时间，爬取upi失败后，约1分钟爬取一次，加快爬取，在限制次数下尝试多次不成功则退出
                    login_data['remarks'] = "Failed to obtain UPI."
                    # return False  # 爬取upi失败也要爬取账单
                # else:
                    # 发回upi, 写入upi 这个不需要的移除UPI 20250919
                    # orders_send = {
                    #     'type': 'UPI',
                    #     'bank_name': self.name,
                    #     'payment_id': login_data['id'],
                    #     'partner_id': login_data['partner_id'],
                    #     # 'upi': login_data['upi'],
                    #     # 'upi_list': login_data['upi_list'],
                    #     'upi': login_data.get('upi'),
                    #     'upi_list': login_data.get('upi_list'),
                    #     'remarks': login_data.get('upi_remarks')
                    # }
                    # if_send = await self.send(orders_send, login_data)
                    # if if_send['is_success'] is False:
                    #     # time.sleep(0.5)
                    #     await asyncio.sleep(0.5)
                    #     if_send = await self.send(orders_send, login_data)
                    # if if_send['is_success'] is False:
                    #     self.on_off(login_data, 0)
                    #     self.logger.error(f"{login_data['id']} 发送upi失败：" + simplejson.dumps(login_data))
                    #     # return False
                    # self.logger.info(f"{login_data['id']} 发送upi成功：{grabUpi}")
                    # login_data['upi_time'] = int(time.time())
                    # login_data['upi_try'] = 0
                    # login_data.pop('upi_try_fail', None)

            self.logger.info(f"{login_data['id']} 爬取账单：")
            # 开始爬取账单
            getBills = await self.getBills(login_data)
            self.logger.info(f"{login_data['id']},getBills(),返回数据, {getBills}")
            # 增加对返回结果的细致判断
            # 如果返回501，则重新登录
            self.logger.info(f"{login_data['id']} 当前接口返回数据 {getBills} , code: {getBills.get('error_code', 'N/A')}")
            if isinstance(getBills, dict) and getBills.get('error_code') == 501:
                self.logger.error(f"{login_data['id']} 抓取流水返回501错误，重新登录。")
                await self.login_off(login_data)
                return 'logout'
            # 如果爬取失败（返回False），则下线
            elif isinstance(getBills['is_success'], bool) and getBills['is_success'] is False:
                self.logger.error(f"{login_data['id']} 抓取流水失败（非501），下线该payment ID。")
                self.on_off(login_data, 0)
                login_data[f"last_grab_failed_{login_data['id']}"] = True
                self.logger.info(f"抓单失败，为 payment_id {login_data['id']} 标记失败状态，下次强制60秒重试")
            else:
                key = f"last_grab_failed_{login_data['id']}"
                if key in login_data:
                    del login_data[key]
                self.logger.info(f"抓单成功，清除 payment_id {login_data['id']} 的失败标记")
            # if getBills['is_success'] is False:
            #     self.logger.error(f"{login_data['id']},grabstatement(),爬取账单失败1, {getBills}")
            #     # 下线接单
            #     self.on_off(login_data, 0)
            #     login_data['time'] = int(time.time()) - self.time_grab2 + 1 * 60  # 更新时间，爬取upi失败后，约1分钟爬取一次，加快爬取，在限制次数下尝试多次不成功则退出
            #     login_data['remarks'] = "Failed to obtain bills."
            #     return False

            login_data['try_count'] = 0
            self.logger.info(f"爬取账单，原始数据 {getBills}")
            self.logger.info(f"爬取账单，成功 {login_data['id']}")
            # 抓取交易记录为空
            if 'transaction_history_list' not in getBills or not getBills['transaction_history_list']:
                # 首次爬取之后设置为非首次爬取
                login_data['if_first_time'] = False
                self.logger.info(f"{login_data['id']} 爬取账单为空：" + simplejson.dumps(login_data))
                # {"status":"S","encKey":"f89e2d511390414a91a89fc5e0f8f5e4","statusDesc":"SUCCESS","requestInfo":{"pspId":0,"pspRefNo":"INDB742A50521DD24A81B20C0B9AF7"},"isMerchant":false}
                return True

            # 开始检测哪些账单需要回调,根据utr来确认唯一性
            counter = 0
            for transaction in getBills['transaction_history_list']:
                self.logger.info(f"grabstatement {login_data['id']} 数据抓取成功")
                self.logger.info(f"transaction： {transaction}")
                utr = transaction['TRANS_ID']
                # if 'appTransaction' not in transaction or transaction['appTransaction'] != True:
                #     self.logger.error(f"{login_data['id']}, 状态不为成功 {utr}, {transaction}")
                #     continue
                if if_first_time:
                    self.logger.info(f"{login_data['id']}, 首次爬取账单跳过历史流水 {utr}")
                    continue
                self.logger.info(f"{login_data['id']}, 准备回调交易 {utr}, {transaction}")

                # --- 交易类型判断和账户ID标准化 ---
                account_id = login_data.get('phone', '') # 例如: '03710910652'

                # 将 account_id 标准化为不带前缀的格式 (例如: '3710910652')
                normalized_account_id = account_id
                if normalized_account_id.startswith('0'):
                    normalized_account_id = normalized_account_id[1:]
                elif normalized_account_id.startswith('92'):
                    normalized_account_id = normalized_account_id[2:]

                # 检查是否包含 92 前缀（例如: '923710910652'）
                full_account_id_92 = '92' + normalized_account_id

                # 交易字段直接从 transaction 中获取 (假设 detail_dto 已被废弃或简化)
                # 针对 queryBill 响应结构：
                trx_id = transaction.get('TRANS_ID', 'N/A')
                ac_from = transaction.get('AC_FROM', '')
                ac_to = transaction.get('AC_TO', '')
                amount_debited = transaction.get('AMOUNT_DEBITED', '0')
                amount_credited = transaction.get('AMOUNT_CREDITED', '0')
                fee = transaction.get('FEE', '0')
                ext_order_no = transaction.get('DESCRIPTION', '') # 暂用 DESCRIPTION 作为订单号或备注

                self.logger.info(f"交易流水获取: Transaction {trx_id} | AC_FROM: {ac_from} | AC_TO: {ac_to} | Normalized ID: {normalized_account_id} | Full ID: {full_account_id_92}")

                # 默认设置为入款 (CREDIT)
                df_flag = False
                # 提取用于匹配的后九位数字
                # full_account_id_92 足够长 (至少9位)
                match_suffix = full_account_id_92[-9:]

                # 提取 ac_from 和 ac_to 的后九位数字
                # 使用切片 [-9:] 确保只取后九位进行匹配
                ac_from_suffix = ac_from[-9:] if isinstance(ac_from, str) and len(ac_from) >= 9 else ac_from
                ac_to_suffix = ac_to[-9:] if isinstance(ac_to, str) and len(ac_to) >= 9 else ac_to

                # 优化后的判断逻辑
                if ac_from_suffix == match_suffix:
                    # AC_FROM 是自己 -> 出款 (PAY/DF)
                    self.logger.info(f"grabstatement 交易流水获取: Transaction {counter} {trx_id}: 【流水标记代付Y】AC_FROM 匹配后缀 {ac_from_suffix}。")
                    df_flag = True
                elif ac_to_suffix == match_suffix:
                    # AC_TO 是自己 -> 入款 (CREDIT/DS)
                    self.logger.info(f"grabstatement 交易流水获取: Transaction {counter} {trx_id}: 【流水标记代收N】AC_TO 匹配后缀 {ac_to_suffix}。")
                    df_flag = False
                else:
                    # 理论上 JazzCash 流水总有一个方向是自己，如果都不是，视为异常或无法识别的内部交易，默认按入款处理 (保守策略)
                    self.logger.warning(f"grabstatement 交易流水获取: Transaction {counter} {trx_id}: 无法识别交易方向，AC_FROM/AC_TO 后缀均不匹配。默认标记为入款。")
                    df_flag = False

                # --- 交易类型和金额处理 ---
                if df_flag:
                    txn_type = 'PAY'
                    # 出款金额: Debit 金额 + Fee (需要将字符串转为 Decimal 或 float)
                    try:
                        txn_amount = float(amount_debited)
                    except ValueError:
                        txn_amount = 0.0

                    # # 出款时，对方是收款方 (BENEFICIARY_MSISDN 或 ACCOUNT_NUMBER)
                    # cust_ref_no = transaction.get('BENEFICIARY_MSISDN') or transaction.get('ACCOUNT_NUMBER')
                    # 出款时，对方是收款方 (取自 CONTEXT_DATA 中的 ACCOUNT_NUMBER)
                    receive_account = transaction.get('CONTEXT_DATA', {}).get('ACCOUNT_NUMBER', '')

                    # ---------- 格式处理 (ACCOUNT_NUMBER) ----------
                    if isinstance(receive_account, str):
                        receive_account = receive_account.strip()

                        # 检查是否以 '92' 开头
                        if receive_account.startswith('92'):
                            # 1. 如果以 '92' 开头，去掉开头的 '92'
                            receive_account = receive_account[2:]
                            # 2. 在处理后的 receive_account 前面加上一个 '0'
                            receive_account = '0' + receive_account
                        # else: 如果不以 '92' 开头，则不进行处理，保持原样（但仍执行了 strip()）

                    payee_account_no = receive_account

                    # ---------- 逻辑：如果 payee_account_no 为空，获取 BENEFICIARY_MSISDN 并处理 ----------
                    if not payee_account_no:
                        # 重新获取 BENEFICIARY_MSISDN 赋值给 receive_account
                        receive_account = transaction.get('CONTEXT_DATA', {}).get('BENEFICIARY_MSISDN', '')

                        # 对新获取的 receive_account 同样进行格式处理
                        if isinstance(receive_account, str):
                            receive_account = receive_account.strip()

                            # 检查是否以 '92' 开头
                            if receive_account.startswith('92'):
                                # 1. 如果以 '92' 开头，去掉开头的 '92'
                                receive_account = receive_account[2:]
                                # 2. 在处理后的 receive_account 前面加上一个 '0'
                                receive_account = '0' + receive_account

                        # 再次赋值给 payee_account_no
                        payee_account_no = receive_account

                    # 最终 payee_account_no 包含了所需的值

                    # 入款时，对方是付款方 (INITIATOR_MSISDN)--对应是付款的账号
                    cust_ref_no = transaction.get('INITIATOR_MSISDN', '')
                    # ---------- 格式处理 ----------
                    if isinstance(cust_ref_no, str):
                        cust_ref_no = cust_ref_no.strip()
                        if cust_ref_no.startswith('92'):
                            # 1. 如果以 '92' 开头，去掉开头的 '92'
                            cust_ref_no = cust_ref_no[2:]
                            # 2. 在处理后的 cust_ref_no 前面加上一个 '0'
                            cust_ref_no = '0' + cust_ref_no
                        # else: 如果不以 '92' 开头，则不进行任何处理，保持原样（但仍执行了 strip()）
                    # ---------- 新增逻辑：提取最终结果的后九位 ----------
                    if isinstance(cust_ref_no, str) and cust_ref_no:
                        cust_ref_no = cust_ref_no[-9:]
                else:
                    txn_type = 'CREDIT'
                    # 入款金额: Credit 金额
                    try:
                        txn_amount = float(amount_credited)
                    except ValueError:
                        txn_amount = 0.0

                    # 入款时，对方是付款方 (INITIATOR_MSISDN)
                    cust_ref_no = transaction.get('INITIATOR_MSISDN', '')
                    payee_account_no = full_account_id_92 # 自己的账户

                    # ---------- 格式处理 ----------
                    if isinstance(cust_ref_no, str):
                        cust_ref_no = cust_ref_no.strip()
                        if cust_ref_no.startswith('92') and len(cust_ref_no) > 10:
                            cust_ref_no = cust_ref_no[2:]
                        elif cust_ref_no.startswith('0') and len(cust_ref_no) > 10:
                            cust_ref_no = cust_ref_no[1:]

                # --- 状态和日志 ---
                txn_status = 'SUCCESS' # queryBill 成功返回的记录通常是成功交易

                self.logger.info(f"grabstatement【收入类别】数据编号 {trx_id} 交易方向: {txn_type}， 关联方/收款方: {cust_ref_no}")

                # --- 映射到通用结构 ---
                mapped_trans = {
                    'txnType': txn_type,
                    # 统一使用计算后的金额
                    'txnAmount': txn_amount,
                    # custRefNo: 出款是对方账号/手机，入款是对方手机
                    'custRefNo': cust_ref_no,
                    'txnStatus': txn_status,
                    'txnNote': transaction.get('DESCRIPTION', ''), # 描述/备注
                    'accountNo': cust_ref_no, # 兼容字段，可以重复使用 custRefNo
                    'payeeAccountNo': payee_account_no, # 区分自己账户或对方账户
                    'payeeIfsc': transaction.get('bankCode', ''), # 使用 bankCode 作为 IFSC/Bank Info
                    'tradeTime': transaction.get('TRX_DTTM', ''), # 交易时间
                    'extOrderNo': trx_id,
                    'fee': float(fee), # 手续费
                }
                # 回调
                self.logger.info(f"grabstatement 数据编号{counter}封装后的数据: mapped_trans {mapped_trans} 。")
                await self.transaction_callback(mapped_trans, login_data)
                counter += 1
            # 首次爬取之后设置为非首次爬取
            login_data['if_first_time'] = False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('grabstatement() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            # 更新集合和hash里的值
            self.update_key(login_data)
            return False

    # 爬取账单和upi 原 get_profile
    async def get_grabstatement(self, login_data):
        # return True  # 测试异常代付订单注释掉下面逻辑
        try:
            # 添加判断在线的key
            _key1 = 'login_on_{}_{}'.format(self.name, login_data['id'])
            self.redis.setex(_key1, 11 * 60, 1)

            # 通知监控下线
            _key2 = 'login_off_{}_{}'.format(self.name, login_data['id'])
            login_off = self.redis.get(_key2)
            if login_off:  # 180分钟之后才真正下线
                # if int(login_off) + 180*60 < int(time.time()):
                #     # 删除标识在线的key
                #     self.redis.delete(_key1)
                #     self.redis.delete(_key2)
                #     self.logger.error(f"{self.list_key} 180分钟之后通知监控下线，登出:" + simplejson.dumps(login_data))
                #     self.login_off()
                #     return 'logout'
                # 下线接单
                self.on_off(login_data, 0)

            grabstatement = False
            # 【核心修改】：抓单失败后强制走60秒短间隔
            self.logger.info(f"login_data==检测=={login_data}")
            if login_data.get(f"last_grab_failed_{login_data['id']}", False):
                _time_grab = 60
                self.logger.info(f"检测到 payment_id {login_data['id']} 上次抓单失败，强制使用60秒短间隔")
            elif 'try_count' in login_data and login_data['try_count'] > 0:
                # 有重试计数的按指定的最短时间爬取一次
                _time_grab = self.time_grab
                self.logger.info(f"条件满足，选择最短爬取间隔: {_time_grab} 秒")

            else:
                _time_grab = self.time_grab2
                self.logger.info(f"条件不满足，选择最长爬取间隔: {_time_grab} 秒")
            self.logger.info(f"--- 当前爬取间隔 (_time_grab) 已确定为: {_time_grab} 秒 ---")

            # 2. 检查是否满足时间间隔条件
            self.logger.info("--- 检查是否满足时间间隔条件 ---")
            current_time = int(time.time())
            last_request_time = login_data.get('time', 0)
            required_time = current_time - _time_grab

            # 将 Unix 时间戳转换为可读的日期格式
            last_request_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_request_time))
            current_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))
            required_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(required_time))

            # self.logger.info(f"上次请求时间: {last_request_time_str}")
            self.logger.info(f"当前时间 - 间隔要求: {current_time_str} - {_time_grab}秒 = {required_time_str}")

            if 'count' not in login_data or last_request_time < required_time:
                self.logger.info("条件满足，准备执行 grabstatement 方法...")
                # 判断是否存在if_first_time且为False
                self.logger.info("--- 检查 if_first_time 标志 ---")
                if login_data.get('if_first_time') is False:
                    self.logger.info("if_first_time 为 False，调用 grabstatement(login_data)")
                    grabstatement = await self.grabstatement(login_data)
                else:
                    self.logger.info("if_first_time 为 True，调用 grabstatement(login_data, if_first_time=True)")
                    grabstatement = await self.grabstatement(login_data, if_first_time=True)
                self.logger.info(f"grabstatement 方法返回结果: {grabstatement}")
                # 在请求返回后立即记录时间戳
                request_finish_time = int(time.time())
                request_finish_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(request_finish_time))
                self.logger.info(f"grabstatement 请求实际完成时间: {request_finish_time_str}")

                if isinstance(grabstatement, bool) and grabstatement is False:
                    login_data['try_count'] = 1 if 'try_count' not in login_data else login_data['try_count'] + 1
                # # 增加重试次数的逻辑，现在包含对501错误的判断
                # if (isinstance(grabstatement, bool) and grabstatement is False) or (isinstance(grabstatement, dict) and grabstatement.get('status_code') == 501):
                #     # 只有在抓取流水失败（返回False）或者返回501错误时，才增加try_count
                #     login_data['try_count'] = 1 if 'try_count' not in login_data else login_data['try_count'] + 1
                #     self.logger.info(f"{login_data['id']} 抓取流水失败或返回501，当前重试次数: {login_data['try_count']}")

                if (isinstance(grabstatement, str) and grabstatement == 'logout') or ('count' in login_data and login_data['try_count'] > self.try_count_limit):
                    # 删除标识在线的key
                    self.redis.delete(_key1)
                    self.redis.delete(_key2)
                    self.redis.delete(_key3)
                    # 登出
                    self.logger.error(f"{self.list_key} try_count太多，登出:" + simplejson.dumps(login_data))
                    await self.login_off(login_data)
                    return 'logout'
            else:
                self.logger.info("时间间隔条件不满足，跳过 grabstatement 方法的调用。")
            # 爬取upi失败次数过多
            # if 'upi_try' in login_data and login_data['upi_try'] > self.try_upi_limit:
            #     # 删除标识在线的key
            #     self.redis.delete(_key1)
            #     self.redis.delete(_key2)
            #     self.redis.delete(_key3)
            #     # 登出
            #     # login_data['upi_try_fail'] = 1 # 标定是否upi爬取太多失败次数
            #     self.logger.error(f"{self.list_key} upi_try太多，登出:" + simplejson.dumps(login_data))
            #     await self.login_off(login_data)
            #     return 'logout'

            login_off = self.redis.get(_key2)
            if not login_off and isinstance(grabstatement, bool) and grabstatement is True:
                self.on_off(login_data)
                # if 'login_if' not in login_data:
                #     self.sendMsg('push_payment_information', True, 'Login success')  # 登录成功通知
                #     login_data['login_if'] = 1

            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_grabstatement 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            # 更新集合和hash里的值
            self.update_key(login_data)
            return False

    # 原 sync_transaction 回调账单
    async def transaction_callback(self, transaction: Dict, login_data) -> bool:
        self.logger.info(f"{login_data['id']}, transaction_callback(), 开始回调 transaction: {transaction}")
        try:
            if transaction['txnType'] not in ['CREDIT', 'PAY']:
                self.logger.error(f"{login_data['id']}, transaction_callback() 失败,不支持的交易类型: {transaction}")
                return False
            if transaction['txnType'] == 'PAY':
                transaction['txnType'] = 'DEBIT'
            account = transaction.get("payeeAccountNo",'')
            ifsc = transaction.get("payeeIfsc",'')

            orders_send = {
                'type': 'New',
                'bank_name': self.name,
                'payment_id': login_data['id'],
                'partner_id': login_data['partner_id'],
                'amount': transaction['txnAmount'],
                'utr': transaction['custRefNo'],
                'trade_type': transaction['txnType'],
                'status': transaction['txnStatus'],
                'remarks': transaction['txnNote'],
                'ifsc': str(ifsc).upper(),
                'account': account,
                'fee': transaction['fee'],
                'trans_id': transaction['extOrderNo'],
            }
            if_send = await self.send(orders_send, login_data)
            if if_send['is_success'] is False:
                # time.sleep(0.5)
                await asyncio.sleep(0.5)
                if_send = await self.send(orders_send, login_data)
            if if_send['is_success'] is True:
                self.logger.info(f"{login_data['id']}, transaction_callback 成功：{simplejson.dumps(orders_send)}")
                return True
            else:
                self.logger.info(f"{login_data['id']}, transaction_callback 失败：{simplejson.dumps(orders_send)}")
                return False
        except Exception as e:
            self.logger.error(f"回调交易记录失败 {transaction['approvalRefNum']}: {str(e)}")
            return False

    # 添加多进程分片和并发处理方法
    def get_active_processes_count(self):
        """获取当前活跃进程数量"""
        try:
            # 注册当前进程
            process_key = f"active_processes_{self.name}"
            current_process_id = f"{process_key}:{os.getpid()}"
            self.redis.setex(current_process_id, 30, int(time.time()))

            # 获取所有活跃进程
            active_processes = self.redis.keys(f"{process_key}:*")

            # 提取并排序PID，确保一致性
            pids = []
            for key in active_processes:
                try:
                    pid = int(key.decode().split(':')[-1])
                    pids.append(pid)
                except:
                    continue

            pids.sort()
            current_pid = os.getpid()

            total_processes = len(pids)
            current_index = pids.index(current_pid) if current_pid in pids else 0

            return total_processes, current_index
        except Exception as e:
            self.logger.error(f"获取活跃进程失败: {e}")
            return 1, 0

    def get_process_allocated_members(self, members: List[bytes]) -> List[bytes]:
        """基于进程ID分片分配members"""
        if not members:
            return []

        total_processes, current_index = self.get_active_processes_count()

        if total_processes <= 1:
            return members

        # 使用一致性哈希分配members
        allocated_members = []
        for member in members:
            member_id = member.decode()
            # 使用MD5哈希确保相同member总是分配给同一进程
            hash_value = int(hashlib.md5(member_id.encode()).hexdigest(), 16)
            assigned_index = hash_value % total_processes

            if assigned_index == current_index:
                allocated_members.append(member)

        self.logger.info(f"进程 {os.getpid()} (索引:{current_index}/{total_processes}) "
                         f"从 {len(members)} 个成员中分配到 {len(allocated_members)} 个")

        return allocated_members

    async def verify_and_handle_abnormal_payout(self, login_data, order_data):
        self.logger.info(f"verify_and_handle_abnormal_payout 异常订单数据: {order_data}")
        receive_account = order_data.get('account_id', '')
        amount = order_data.get('amount', '')
        time_created = order_data.get('time_created', '')
        if not receive_account or not amount or not time_created:
            self.logger.error(f"verify_and_handle_abnormal_payout 异常订单数据无效: {order_data}")
            return
        # 初始化或增加 try_count
        if 'try_count' not in login_data:
            login_data['try_count'] = 0
        try:
            # 调用 getBills 方法
            bill_result = await self.getBills(login_data)
            self.logger.info(f"verify_and_handle_abnormal_payout {login_data['id']}, verify_and_handle_abnormal_payout 爬取账单, {bill_result}")
            if bill_result['is_success'] is False:
                self.logger.error(f"verify_and_handle_abnormal_payout {login_data['id']}, verify_and_handle_abnormal_payout 爬取账单失败, {bill_result}")
                # 增加对返回结果的细致判断
                # 如果返回501，则重新登录
                self.logger.info(f"verify_and_handle_abnormal_payout {login_data['id']} 当前接口返回数据 {bill_result} , code: {bill_result.get('error_code', 'N/A')}")
                if isinstance(bill_result, dict) and bill_result.get('error_code') == 501:
                    self.logger.error(f"{login_data['id']} 抓取流水返回501错误，重新登录。")
                    await self.login_off(login_data)
                    return 'logout'
                # 如果爬取失败（返回False），则下线
                elif isinstance(bill_result['is_success'], bool) and bill_result['is_success'] is False:
                    self.logger.error(f"{login_data['id']} 抓取流水失败（非501），下线该payment ID。")
                    self.on_off(login_data, 0)

            transaction_history = bill_result.get('transaction_history_list', [])
            self.logger.info(f"verify_and_handle_abnormal_payout {receive_account}, 爬取交易记录：{transaction_history}")
            matched = False
            counter = 1
            for trans in transaction_history:
                self.logger.info(f"verify_and_handle_abnormal_payout {login_data['id']} 数据抓取成功")
                detail_dto = trans

                self.logger.info(f"verify_and_handle_abnormal_payout 交易流水获取: Transaction {counter}:{detail_dto}。")
                utr = trans['TRANS_ID']
                self.logger.info(f"{login_data['id']}, 准备回调交易 {utr}, {trans}")
                # 数据封装
                self.logger.info(f"交易流水获取: Transaction {counter}:{trans.get('TRANS_ID')}。")
                account_id = login_data.get('phone', '')

                # --- 1. 账户ID标准化 ---
                df_flag = False
                normalized_account_id = account_id
                # 将 account_id 标准化为不带前缀的格式
                if normalized_account_id.startswith('0'):
                    normalized_account_id = normalized_account_id[1:]
                # 如果您的 account_id 可能会是 92 开头，也进行相应处理
                elif normalized_account_id.startswith('92'):
                    normalized_account_id = normalized_account_id[2:]

                # 构造 JazzCash 流水中的标准手机号格式 (带 92 前缀)
                full_account_id_92 = '92' + normalized_account_id

                # --- 2. 交易方向判断（核心修正） ---
                ac_from = trans.get('AC_FROM', '')
                ac_to = trans.get('AC_TO', '')

                # 提取用于匹配的后九位数字
                # full_account_id_92 足够长 (至少9位)
                match_suffix = full_account_id_92[-9:]

                # 提取 ac_from 和 ac_to 的后九位数字
                # 使用切片 [-9:] 确保只取后九位进行匹配
                ac_from_suffix = ac_from[-9:] if isinstance(ac_from, str) and len(ac_from) >= 9 else ac_from
                ac_to_suffix = ac_to[-9:] if isinstance(ac_to, str) and len(ac_to) >= 9 else ac_to

                # 优化后的判断逻辑
                if ac_from_suffix == match_suffix:
                    # AC_FROM 是自己 -> 出款 (PAY/DF)
                    self.logger.info(f"grabstatement 交易流水获取: Transaction {counter}: 【流水标记代付Y】AC_FROM 匹配后缀 {ac_from_suffix}。")
                    df_flag = True
                elif ac_to_suffix == match_suffix:
                    # AC_TO 是自己 -> 入款 (CREDIT/DS)
                    self.logger.info(f"grabstatement 交易流水获取: Transaction {counter}: 【流水标记代收N】AC_TO 匹配后缀 {ac_to_suffix}。")
                    df_flag = False
                else:
                    # 理论上 JazzCash 流水总有一个方向是自己，如果都不是，视为异常或无法识别的内部交易，默认按入款处理 (保守策略)
                    self.logger.warning(f"grabstatement 交易流水获取: Transaction {counter}: 无法识别交易方向，AC_FROM/AC_TO 后缀均不匹配。默认标记为入款。")
                    df_flag = False

                if not df_flag:
                    # 如果不是代付（出款），且您只关心代付流水，则跳过
                    continue

                # --- 3. 代付匹配和数据封装 ---

                # 提取交易金额：出款使用 AMOUNT_DEBITED (总扣款金额)
                try:
                    transaction_amount = float(trans.get('AMOUNT_DEBITED', 0))
                except ValueError:
                    transaction_amount = 0.0

                receive_account_1 = trans.get('CONTEXT_DATA', {}).get('ACCOUNT_NUMBER', '')

                # ---------- 格式处理 (ACCOUNT_NUMBER) ----------
                if isinstance(receive_account_1, str):
                    receive_account_1 = receive_account_1.strip()

                    # 检查是否以 '92' 开头
                    if receive_account_1.startswith('92'):
                        # 1. 如果以 '92' 开头，去掉开头的 '92'
                        receive_account_1 = receive_account_1[2:]
                        # 2. 在处理后的 receive_account 前面加上一个 '0'
                        receive_account_1 = '0' + receive_account_1
                    # else: 如果不以 '92' 开头，则不进行处理，保持原样（但仍执行了 strip()）

                payee_account_no = receive_account_1

                # ---------- 逻辑：如果 payee_account_no 为空，获取 BENEFICIARY_MSISDN 并处理 ----------
                if not payee_account_no:
                    # 重新获取 BENEFICIARY_MSISDN 赋值给 receive_account
                    receive_account_1 = trans.get('CONTEXT_DATA', {}).get('BENEFICIARY_MSISDN', '')

                    # 对新获取的 receive_account 同样进行格式处理
                    if isinstance(receive_account_1, str):
                        receive_account_1 = receive_account_1.strip()

                        # 检查是否以 '92' 开头
                        if receive_account_1.startswith('92'):
                            # 1. 如果以 '92' 开头，去掉开头的 '92'
                            receive_account_1 = receive_account_1[2:]
                            # 2. 在处理后的 receive_account 前面加上一个 '0'
                            receive_account_1 = '0' + receive_account_1

                    # 再次赋值给 payee_account_no
                    payee_account_no = receive_account_1

                # 最终 payee_account_no 包含了所需的值

                # 入款时，对方是付款方 (INITIATOR_MSISDN)--对应是付款的账号
                cust_ref_no = trans.get('INITIATOR_MSISDN', '')
                # ---------- 格式处理 ----------
                if isinstance(cust_ref_no, str):
                    cust_ref_no = cust_ref_no.strip()
                    if cust_ref_no.startswith('92'):
                        # 1. 如果以 '92' 开头，去掉开头的 '92'
                        cust_ref_no = cust_ref_no[2:]
                        # 2. 在处理后的 cust_ref_no 前面加上一个 '0'
                        cust_ref_no = '0' + cust_ref_no
                    # else: 如果不以 '92' 开头，则不进行任何处理，保持原样（但仍执行了 strip()）


                # ---------- 新增逻辑：提取最终结果的后九位 ----------
                if isinstance(cust_ref_no, str) and cust_ref_no:
                    cust_ref_no = cust_ref_no[-9:]
                extracted_number = receive_account_1

                # ❗ 修正匹配逻辑：使用金额匹配，且确保是出款（df_flag已判断）
                # if df_flag and transaction_amount == amount: # 假设外部 amount 是期望匹配的总扣款金额
                # if transaction_amount == amount: # ❗ 由于上面已经 if not df_flag continue，此处只需匹配金额
                self.logger.info(f"条件打印 = receive_account : {receive_account}, extracted_number : {extracted_number}, transaction_amount : {transaction_amount}, amount : {amount}, df_flag : {df_flag}")
                if receive_account in extracted_number and transaction_amount == amount and df_flag:
                    matched = True
                    self.logger.info(f"{full_account_id_92}, {amount}订单在账单中已找到，触发回调处理")

                    # === 新增：风控检查 payment_id_failed_jazzcash ===
                    try:
                        # 获取交易发生时间（从 '2025-11-13T10:50:12' 格式转换）
                        trans_time_str = detail_dto.get('TRX_DTTM', '')
                        # 注意：如果时间格式不确定，需要更健壮的解析，这里假设格式是固定的
                        # trans_time = datetime.strptime(trans_time_str, '%Y-%m-%dT%H:%M:%S')
                        # trans_time = datetime.strptime(trans_time_str, '%Y-%m-%dT%H:%M:%S')
                        trans_time = datetime.strptime(trans_time_str, '%Y-%m-%d %H:%M:%S.%f')

                        # failed_time = datetime.fromtimestamp(time_created)
                        # ********** 关键修改处 **********
                        # time_created 现在是 '2025-11-21 14:15:08' 字符串，使用 strptime 解析
                        failed_time = datetime.strptime(time_created, '%Y-%m-%d %H:%M:%S')
                        # ********************************

                        self.logger.info(f"{login_data['id']}, 交易 {utr}: 失败标记时间: {failed_time}，交易时间: {trans_time}。")
                        # 1.只比对  异常订单发生的那一刻的后面的 账单   10.00发生的这一笔异常订单  只比对10.00点 往后的账单
                        if trans_time <= failed_time:
                            # 记录因风控逻辑跳过
                            self.logger.info(f"{login_data['id']}, 交易 {utr}: 【风控跳过：交易时间早于失败标记时间】 失败标记时间: {failed_time}，交易时间: {trans_time}。")
                            continue

                    except Exception as e:
                        self.logger.error(f"处理 payment_id_failed_jazzcash 检查时发生异常: {e}")
                        pass
                    # === 新增风控检查结束 ===

                    txn_type = 'PAY'
                    txn_status = 'SUCCESS' # QueryBill 成功返回的记录通常是成功交易

                    # 构造 mapped_trans
                    mapped_trans = {
                        'txnType': txn_type,
                        'txnAmount': transaction_amount,
                        # custRefNo 和 accountNo 字段指向收款方
                        'custRefNo': cust_ref_no,
                        'txnStatus': txn_status,
                        'txnNote': trans.get('DESCRIPTION', ''),
                        'accountNo': extracted_number,
                        # payeeAccountNo 指向自己的账户（代付方）
                        'payeeAccountNo': extracted_number,
                        # payeeIfsc 使用 bankCode
                        'payeeIfsc': trans.get('bankCode', ''),
                        'tradeTime': trans.get('TRX_DTTM', ''),
                        # extOrderNo 使用 TRANS_ID (流水号)
                        'extOrderNo': trans.get('TRANS_ID', ''),
                        'fee': float(trans.get('FEE', 0)),
                        'appTransaction': True
                    }
                    # 调用 transaction_callback
                    await self.transaction_callback(mapped_trans, login_data)
                    self.logger.info(f"成功处理了第 {counter} 条记录。") # 添加这一行
                    counter += 1
                    break
            if not matched:
                self.logger.error(f"{receive_account}, {amount}订单未匹配，标记异常")
                order_data['status'] = 'abnormal_unmatched'
                # 确保 ABNORMAL_PAYOUTS_KEY 是已定义的常量 Todo
                # self.redis.hset(ABNORMAL_PAYOUTS_KEY, utr, simplejson.dumps(order_data))
                # await self.reallocate_order(order_data)
        except Exception as e:
            tb_str = traceback.format_exc()
            self.logger.error(f"{receive_account}, verify_and_handle_abnormal_payout 错误: {e}\n{tb_str}")


    async def process_single_member_async(self, member: bytes) -> bool:
        """异步处理单个member"""
        try:
            _id = member.decode()

            # 读取缓存，确定是否本地模拟
            payment_mock = self.redis.exists(f"payment_mock:{_id}")
            if payment_mock:
                # 标记本次为本地模拟
                self.local_mock = True

            login_data_str = self.redis.hget(self.hash_key, _id)
            if not login_data_str:
                self.logger.error(f"{self.hash_key} {_id} 不存在数据！从set列表{self.set_key}中删除")
                self.redis.zrem(self.set_key, _id)
                return False

            self.logger.info(f"进程 {os.getpid()} 处理 member[{member}], hash_key: {self.hash_key}")

            # 存在hash数据，则开始登录或者爬取账单等
            self.logger.info(f"{_id},尝试获取锁")
            # 尝试获取锁
            _lock = self.get_lock(_id)
            if not _lock:
                self.logger.warning(f"{_id},未获取到锁！")
                return False

            try:
                self.logger.info(f"{_id}, 获取到锁: {_lock}")

                # 设置当前处理的数据  将数据作为参数传递，而不是依赖实例属性，避免self属性混用
                login_data = simplejson.loads(login_data_str.decode())

                # 获取代理IP
                proxy = self.get_proxies()
                # if not proxy:
                #     self.logger.error(f"{self.list_key} {_id} 无代理！")
                #     return False

                # 检测是否需要换代理
                if 'socks_ip' not in login_data or not login_data['socks_ip']:
                    login_data['socks_ip'] = proxy
                if 'socks_ip' in login_data and login_data['socks_ip']:
                    login_data['socks_ip'] = self.check_proxy(login_data)

                self.logger.info(f"{_id}, hash_key: {self.hash_key}, login_data: {login_data}")

                # 业务逻辑处理
                res = None
                self.logger.info(f"process_single_member_async ： {login_data}")
                if login_data['status'] == 'grabstatement':
                    res = await self.get_grabstatement(login_data)
                    self.logger.info(f"{login_data['id']}, get_grabstatement() res {type(res)}： {res}")
                # 检查并处理与当前 member 相关的异常代付
                ABNORMAL_PAYOUTS_KEY = f"payment_id_failed_jazzcash:{_id}"  # 修改为 payment_id_failed_jazzcash:* 格式
                order_data_str = self.redis.get(ABNORMAL_PAYOUTS_KEY)
                self.logger.info(f'======order_data_str========{order_data_str}')
                if order_data_str:
                    order_data = simplejson.loads(order_data_str.decode())
                    self.logger.info(f'======order_data========{order_data}')
                    self.logger.info(f"process_single_member_async===={order_data.get('payment_id')}==={login_data['id']}=={login_data}==============================")
                    # if str(order_data.get('payment_id')) == str(login_data['id']):
                    self.logger.info(f"{_id}, 发现与当前 member 相关的失败订单: {ABNORMAL_PAYOUTS_KEY}")
                    try:
                        # 转换 order_data 格式以兼容 verify_and_handle_abnormal_payout
                        converted_order_data = {
                            'account_id': order_data.get('payment_account', login_data.get('payment_account', '')),  # 从 login_data 获取 备注这个是收款手机号
                            'amount': order_data.get('amount', 0.0),
                            'time_created': order_data.get('time_created', '')
                        }

                        await self.verify_and_handle_abnormal_payout(login_data, converted_order_data)
                        self.redis.delete(ABNORMAL_PAYOUTS_KEY)
                        self.logger.info(f"{_id}, 失败订单 {ABNORMAL_PAYOUTS_KEY} 处理完成并移除")
                    except Exception as e:
                        self.logger.error(f"{_id}, 处理失败订单 {ABNORMAL_PAYOUTS_KEY} 失败: {e}")

                # 状态检查
                # if login_data['status'] not in ['sendOTP', 'grabOTP', 'device_check', 'send_sms', 'wait_client_send_sms', 'verify_sms', 'grabstatement']:
                if login_data['status'] not in ['grabstatement']:
                    self.logger.error(f"{login_data['id']}, {self.list_key} {_id} status存在问题，舍去！")
                    await self.login_off(login_data)
                    self.read_cache(f'async_main() status error', login_data)
                    return False

                # 处理结果
                if isinstance(res, str) and res == 'logout':
                    self.logger.error(f"{login_data['id']}, {self.list_key} {_id} 登出，删除相关的hash和set中的值")
                    await self.login_off(login_data)
                    self.read_cache(f'async_main() logout', login_data)
                    return False
                else:
                    self.update_key(login_data)
                    # 旧 hash/set 调度已退役；账单采集由 MySQL 订单窗口触发。
                    self.read_cache(f'async_main() True', login_data)
                    return True

            finally:
                # 删除锁
                self.del_lock(_id, _lock)
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f"process_single_member_async 异步处理成员 {member} 失败: {e} 错误详情：{error_message}")
            return False

    async def process_members_concurrent(self, members: List[bytes], concurrent_limit: int = 20):
        """并发处理members"""
        if not members:
            return

        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(member):
            async with semaphore:
                return await self.process_single_member_async(member)

        # 创建所有任务
        tasks = [process_with_semaphore(member) for member in members]

        # 并发执行
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        # 统计结果
        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))

        self.logger.info(f"进程 {os.getpid()} 并发处理完成: "
                         f"总数 {len(members)}, 成功 {success_count}, 失败 {len(results) - success_count}, "
                         f"异常 {error_count}, 耗时 {end_time - start_time:.2f}秒")

    def main(self):
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"
            due_payment_ids = self.fetch_due_statement_payment_ids(limit=200)
            self.logger.info(f"JazzCash MySQL账单调度扫描完成: due_payment_ids={len(due_payment_ids)}")

            if not due_payment_ids:
                self.logger.info("JazzCash MySQL账单调度没有待处理 payment_id")
                time.sleep(2)
                return

            members = [str(payment_id).encode() for payment_id in due_payment_ids]
            allocated_members = self.get_process_allocated_members(members)
            allocated_payment_ids = [member.decode() for member in allocated_members]

            if not allocated_payment_ids:
                self.logger.info(f"进程 {os.getpid()} 没有分配到需要处理的数据")
                time.sleep(2)
                return

            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    self.process_statement_payment_ids_concurrent(allocated_payment_ids, concurrent_limit=20)
                )
            except Exception as e:
                self.logger.error(f"JazzCash MySQL账单候选并发处理失败: {e}")
            finally:
                if loop and not loop.is_closed():
                    loop.close()

        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('main过程错误： 错误详情：{}\n{}'.format(e, error_message))


# 主程序入口
if __name__ == "__main__":
    try:
        logger.info(f"{'=' * 10}jazzcash协议启动{'=' * 10}")
        bank = BankLogin("jazzcash")
        # 定期输出日志统计（如果使用异步处理器）
        last_stats_time = time.time()

        # 主循环
        while True:
            try:
                bank.init_function(logger)
                bank.main()

                # 每分钟输出一次日志统计
                current_time = time.time()
                if current_time - last_stats_time >= 60:
                    stats = bank.get_log_stats()
                    if stats:
                        logger.info(f"日志统计: {stats}")
                    last_stats_time = current_time
            except KeyboardInterrupt:
                logger.info("程序被用户中断")
                break
            except Exception as e:
                tb_str = traceback.format_exc()
                error_message = ''.join(tb_str)
                logger.error('main 循环程序运行错误： 错误详情：{}\n{}'.format(e, error_message))
                # 插入redis，防止非主逻辑内的出错
                bank.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            finally:
                time.sleep(2)
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message = ''.join(tb_str)
        logger.error('main 程序启动错误： 错误详情：{}\n{}'.format(e, error_message))
    finally:
        # 确保日志正确关闭
        if hasattr(file_handler, 'close'):
            file_handler.close()
