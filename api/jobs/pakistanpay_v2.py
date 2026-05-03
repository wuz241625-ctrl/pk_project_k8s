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
from contextlib import asynccontextmanager

import aiohttp
import redis
import asyncio
import hashlib
import random
import logging
import requests
import simplejson
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad,unpad
import traceback

import base64
import pymysql

from urllib.parse import quote, urlencode
from typing import List, Dict, Any
from logging.handlers import TimedRotatingFileHandler
from requests.adapters import HTTPAdapter
from response_logger import ResponseLogger

# API_URL = 'http://104.198.86.150:83'
# USER_ID = 'ba08c3c0e4f546ad92dd2c2e8542ca36'
# SECRET_KEY = 'ca45b35e132b46b9b68dd55f1ab077de'

# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from response_logger import ResponseLogger
import config
from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService
from application.lakshmi_api.enums.payment_login_progress import PaymentLoginProgress
from datetime import datetime

#easypaisa爬取账单，需要发送短信

# 改进的 TraceIDFilter 类 - 添加协程安全
class TraceIDFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self._local = threading.local()

    @property
    def trace_id(self):
        return getattr(self._local, 'trace_id', 'default')

    @trace_id.setter
    def trace_id(self, value):
        self._local.trace_id = value

    def filter(self, record):
        record.trace_id = self.trace_id
        # 添加协程ID用于区分不同的并发任务
        try:
            task = asyncio.current_task()
            if task:
                record.task_id = f"task_{id(task) % 10000:04d}"
            else:
                record.task_id = "sync"
        except RuntimeError:
            record.task_id = "sync"
        return True

# 配置高性能日志系统
def setup_high_performance_logging(use_async=False):
    """
    设置高性能日志系统

    Args:
        buffer_size: 缓冲区大小（字节），默认16KB
        flush_interval: 刷新间隔（秒），默认3秒
        use_async: 是否使用异步处理器，默认False
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # 日志格式
    date_format = "%Y-%m-%d %H:%M:%S"
    format_str = "%(asctime)s - [PID:%(process)d] [%(trace_id)s] [%(task_id)s] - %(levelname)s - %(message)s"
    formatter = logging.Formatter(format_str, date_format)

    # 创建 TraceIDFilter 实例
    trace_id_filter = TraceIDFilter()

    # 控制台处理器（不缓冲，实时输出）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(trace_id_filter)

    # 文件处理器（带缓冲）
    LOG_FILE = os.path.join(current_dir, f"easypaisa_{os.getpid()}.log")

    if use_async:
        # 简单处理器
        base_file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILE,
            when='midnight',
            interval=1,
            backupCount=10,
            encoding='utf-8',
            delay=False  # 立即创建文件
        )

        base_file_handler.setFormatter(formatter)
        base_file_handler.addFilter(trace_id_filter)

        # 包装为异步处理器
        file_handler = AsyncBatchLogHandler(
            base_file_handler,
            batch_size=50000,  # 50条日志一批
            flush_interval=5.0,  # 2秒强制刷新
            max_queue_size=10000
        )
    else:
        # 简单处理器
        file_handler = logging.handlers.TimedRotatingFileHandler(
            LOG_FILE,
            when='midnight',
            interval=1,
            backupCount=10,
            encoding='utf-8',
            delay=False  # 立即创建文件
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(trace_id_filter)

    # 配置主logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    # 清除现有的处理器（避免重复）
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    # 防止日志向上级传播
    logger.propagate = False

    return logger, trace_id_filter, file_handler


# 高性能缓冲日志处理器
class BufferedFileHandler(logging.handlers.TimedRotatingFileHandler):
    """带缓冲控制的文件处理器"""

    def __init__(self, filename, when='midnight', interval=1, backupCount=10,
                 encoding='utf-8', delay=True, buffer_size=8192, flush_interval=5.0):
        """
        初始化缓冲文件处理器

        Args:
            buffer_size: 缓冲区大小（字节），默认8KB
            flush_interval: 强制刷新间隔（秒），默认5秒
        """
        super().__init__(filename, when, interval, backupCount, encoding, delay)

        self.buffer_size = buffer_size  # 缓冲区大小
        self.flush_interval = flush_interval  # 强制刷新间隔
        self.buffer = []  # 日志缓冲区
        self.buffer_bytes = 0  # 当前缓冲区字节数
        self.last_flush_time = time.time()  # 上次刷新时间
        self.lock = threading.Lock()  # 线程锁

        # 启动定时刷新线程
        self._start_flush_timer()

    def _start_flush_timer(self):
        """启动定时刷新线程"""

        def flush_timer():
            while True:
                time.sleep(self.flush_interval)
                with self.lock:
                    if self.buffer and (time.time() - self.last_flush_time) >= self.flush_interval:
                        self._force_flush()

        timer_thread = threading.Thread(target=flush_timer, daemon=True)
        timer_thread.start()

    def emit(self, record):
        """处理日志记录"""
        try:
            with self.lock:
                # 格式化日志消息
                msg = self.format(record)
                msg_bytes = len(msg.encode('utf-8'))

                # 添加到缓冲区
                self.buffer.append(msg + '\n')
                self.buffer_bytes += msg_bytes

                # 检查是否需要刷新
                if self._should_flush():
                    self._force_flush()

        except Exception:
            self.handleError(record)

    def _should_flush(self):
        """判断是否应该刷新缓冲区"""
        # 缓冲区大小达到阈值
        if self.buffer_bytes >= self.buffer_size:
            return True

        # 时间间隔达到阈值
        if time.time() - self.last_flush_time >= self.flush_interval:
            return True

        # 缓冲区记录数过多（防止内存占用过大）
        if len(self.buffer) >= 1000:
            return True

        return False

    def _force_flush(self):
        """强制刷新缓冲区"""
        if not self.buffer:
            return

        try:
            # 确保文件已打开
            if self.stream is None:
                self.stream = self._open()

            # 写入所有缓冲的日志
            for log_line in self.buffer:
                self.stream.write(log_line)

            # 刷新到磁盘
            self.flush()

            # 清空缓冲区
            self.buffer.clear()
            self.buffer_bytes = 0
            self.last_flush_time = time.time()

        except Exception as e:
            # 如果写入失败，保留缓冲区内容，下次再试
            print(f"日志刷新失败: {e}")

    def flush(self):
        """刷新到磁盘"""
        if self.stream:
            self.stream.flush()
            # 强制同步到磁盘（可选）
            # os.fsync(self.stream.fileno())

    def close(self):
        """关闭处理器"""
        with self.lock:
            self._force_flush()
        super().close()

# 异步批量日志处理器（适用于超高并发）
class AsyncBatchLogHandler(logging.Handler):
    """异步批量日志处理器"""

    def __init__(self, target_handler, batch_size=100, flush_interval=2.0, max_queue_size=10000):
        """
        初始化异步批量日志处理器

        Args:
            target_handler: 目标日志处理器
            batch_size: 批量大小，默认100条
            flush_interval: 刷新间隔，默认2秒
            max_queue_size: 最大队列大小，默认10000
        """
        super().__init__()
        self.target_handler = target_handler
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_queue_size = max_queue_size

        self.log_queue = Queue(maxsize=max_queue_size)
        self.running = True
        self.worker_thread = None
        self.stats = {
            'total_logs': 0,
            'batches_written': 0,
            'queue_full_drops': 0
        }

        self._start_worker()

    def _start_worker(self):
        """启动工作线程"""

        def worker():
            batch = []
            last_flush_time = time.time()

            while self.running:
                try:
                    # 尝试获取日志记录
                    try:
                        record = self.log_queue.get(timeout=0.1)
                        if record is None:  # 停止信号
                            break
                        batch.append(record)
                    except Empty:
                        pass

                    current_time = time.time()

                    # 检查是否需要批量写入
                    should_flush = (
                            len(batch) >= self.batch_size or
                            (batch and current_time - last_flush_time >= self.flush_interval)
                    )

                    if should_flush and batch:
                        self._write_batch(batch)
                        batch.clear()
                        last_flush_time = current_time

                except Exception as e:
                    print(f"异步日志工作线程错误: {e}")

            # 处理剩余的日志
            if batch:
                self._write_batch(batch)

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()

    def _write_batch(self, batch):
        """批量写入日志"""
        try:
            for record in batch:
                self.target_handler.emit(record)

            # 强制刷新
            if hasattr(self.target_handler, 'flush'):
                self.target_handler.flush()

            self.stats['batches_written'] += 1

        except Exception as e:
            print(f"批量写入日志失败: {e}")

    def emit(self, record):
        """处理日志记录"""
        try:
            self.log_queue.put_nowait(record)
            self.stats['total_logs'] += 1
        except:
            # 队列满了，丢弃日志（避免阻塞）
            self.stats['queue_full_drops'] += 1

    def get_stats(self):
        """获取统计信息"""
        return {
            **self.stats,
            'queue_size': self.log_queue.qsize(),
            'is_running': self.running
        }

    def close(self):
        """关闭处理器"""
        self.running = False
        self.log_queue.put(None)  # 发送停止信号

        if self.worker_thread:
            self.worker_thread.join(timeout=5)

        super().close()

# 初始化日志系统
logger, trace_id_filter, file_handler = setup_high_performance_logging(use_async=True)     # 是否使用异步处理（根据需要调整）


conf = config.get_config()

# 配置参数
API_SERVER_DOMAIN = conf.get('ospay_api_host', 'http://localhost:9000')
API_URL = conf['easypaisa_api_url']
USER_ID = conf['easypaisa_user_id']
SECRET_KEY = conf['easypaisa_secret_key']
class BankLogin:
    def __init__(self, name):
        self.name = name
        self.list_key = f"list_{name}"
        self.hash_key = f"hash_{name}"
        self.set_key = f"set_{name}"
        self.if_callback_key = f"if_callback_{name}"  # 存放已经第一次采集或这已经回调过的账单,使用有序集合存放,分数为时间,在2分钟内不成功回调会自动再回调
        self.clean_if_callback_key_time = 60 * 60 * 24 * 60 # 清理 if_callback_key 中时间较久的utr ,避免已经回调过的utr数据量过大
        self.lock_time = 30 # 操作锁的锁定时间
        self.time_grab = 40  # 短时间频繁爬取
        self.time_grab2 = 10 * 60  # 长时间爬取
        self.order_time_out = 5 * 60
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
        self.internal_callback_host = (
            os.environ.get('API_INTERNAL_CALLBACK_HOST')
            or conf.get('internal_callback_host')
            or 'http://127.0.0.1:9000'
        )
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
        self.runtime_service = SyncEasyPaisaRuntimeService(self.redis)
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

    def get_payment_info(self, payment_id):
        """
        示例: 从数据库查询 payment 信息。
        """
        # 确保数据库连接存在
        if not self.db_connection or not self.db_connection.open:
            self.logger.error("数据库连接已关闭，尝试重新连接...")
            self.db_connection = self.check_db_connection()
            if not self.db_connection:
                return None

        with self.db_connection.cursor() as cur:
            try:
                sql_query = """
                    SELECT *
                    FROM payment 
                    WHERE id = %s
                """
                cur.execute(sql_query, (payment_id,))
                payment_info = cur.fetchone()
                
                if not payment_info:
                    self.logger.info(f"未找到ID为 {payment_id} 的信息。")
                    return None
                
                self.logger.info(f"成功查询到 payment 信息: {payment_info}")

                return payment_info.get('account_accno')
                    
            except Exception as e:
                self.logger.error(f"数据库查询失败: {e}", exc_info=True)
                self.db_connection.rollback()
                return None
            finally:
                self.db_connection.commit()

    def _runtime_manual_off(self, payment_id):
        try:
            runtime_service = getattr(self, "runtime_service", None)
            if runtime_service is None:
                runtime_service = SyncEasyPaisaRuntimeService(self.redis)
                self.runtime_service = runtime_service
            return runtime_service.is_manual_off(payment_id)
        except Exception as e:
            self.logger.error(f"检查 EasyPaisa manual-off 失败 payment_id={payment_id}: {e}", exc_info=True)
            return False

    def _runtime_health_order_paused(self, payment_id):
        try:
            runtime_service = getattr(self, "runtime_service", None)
            if runtime_service is None:
                runtime_service = SyncEasyPaisaRuntimeService(self.redis)
                self.runtime_service = runtime_service
            return runtime_service.is_order_health_paused(payment_id)
        except Exception as e:
            self.logger.error(f"检查 EasyPaisa health-pause 失败 payment_id={payment_id}: {e}", exc_info=True)
            return True

    def _read_payment_runtime_flags(self, payment_id):
        if not self.db_connection or not self.db_connection.open:
            self.logger.error("数据库连接已关闭，尝试重新连接...")
            self.db_connection = self.check_db_connection()
            if not self.db_connection:
                return None

        with self.db_connection.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT id, phone, status, certified, manual_status, channel
                    FROM payment
                    WHERE id = %s
                    """,
                    (payment_id,),
                )
                return cur.fetchone()
            except Exception as e:
                self.logger.error(f"查询 EasyPaisa runtime 状态失败 payment_id={payment_id}: {e}", exc_info=True)
                self.db_connection.rollback()
                return None
            finally:
                self.db_connection.commit()

    def payment_runtime_policy(self, payment_id, login_data=None):
        """返回采集 worker 写 runtime 前必须遵守的 DB/runtime 策略。"""
        payment = self._read_payment_runtime_flags(payment_id)
        if not payment:
            return "offline"

        try:
            status = int(payment.get("status") or 0)
            certified = int(payment.get("certified") or 0)
            manual_status = int(payment.get("manual_status") or 0)
        except Exception:
            self.logger.error(f"EasyPaisa payment 状态字段异常 payment_id={payment_id}: {payment}")
            return "offline"

        if status != 1:
            return "business_paused"
        if certified != 1:
            return "order_paused"
        if self._runtime_health_order_paused(payment_id):
            return "order_paused"
        if self._runtime_manual_off(payment_id):
            return "ds_dispatch_off"
        if manual_status == 1:
            return "ds_dispatch_off"
        return "dispatch_on"

    @staticmethod
    def _df_order_enabled_for_policy(policy):
        """代付只受全局接单资格影响，不受代收人工锁定影响。"""
        return policy in ("dispatch_on", "ds_dispatch_off")

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

    def _load_pre_login_entry(self, value, redis_key):
        if not value:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        try:
            return simplejson.loads(value)
        except Exception as e:
            self.logger.error(f"{redis_key} 解析 pre_login 数据失败: {e}")
            return None

    def _handle_pre_login_alias(self, redis_key, data):
        if not isinstance(data, dict) or data.get("kind") != "payment_id_alias":
            return False

        target_payment_id = str(data.get("target_payment_id") or "").strip()
        if not target_payment_id:
            self.redis.delete(redis_key)
            self.logger.warning(f"{redis_key} alias 缺少 target_payment_id，已删除残留 key")
            return True

        snapshot = self.runtime_service.read_snapshot(target_payment_id)
        target_online = bool(
            snapshot
            and (
                snapshot.get("session_phase") != "offline"
                or snapshot.get("online")
                or snapshot.get("dispatch_df")
                or snapshot.get("dispatch_ds")
                or snapshot.get("collect_enabled")
                or snapshot.get("df_order_enabled")
                or snapshot.get("ds_order_enabled")
            )
        )
        if target_online:
            self.logger.info(f"{redis_key} 是 payment_id_alias -> {target_payment_id}，跳过 jobs 扫描")
            return True

        self.redis.delete(redis_key)
        self.logger.info(f"{redis_key} 指向 {target_payment_id} 的 alias 已离线，已删除残留 key")
        return True

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
                policy = self.payment_runtime_policy(login_data['id'], login_data)
                channels = login_data.get('channels') or login_data.get('qr_channel') or login_data.get('channel')
                if policy == "offline":
                    self.runtime_service.force_offline(
                        login_data['id'],
                        phone=login_data.get('phone'),
                        source="pakistanpay_v2",
                        reason="payment_disabled",
                        channels=channels,
                    )
                    self.logger.error(f"{login_data['id']}, {self.list_key} DB已下线，拒绝重新上线采集")
                    return False
                df_order_enabled = self._df_order_enabled_for_policy(policy)
                self.runtime_service.mark_active_successful(
                    login_data['id'],
                    phone=login_data.get('phone'),
                    selected_accno=login_data.get('account_accno'),
                    selected_iban=login_data.get('account_iban') or login_data.get('IBAN'),
                    source="pakistanpay_v2",
                    online_ttl=660,
                    collect_enabled=True,
                    ds_order_enabled=policy == "dispatch_on",
                    df_order_enabled=df_order_enabled,
                    channels=channels,
                )
                if policy == "dispatch_on":
                    self.logger.info(f"{login_data['id']}, {self.list_key} 上线采集： {login_data['id']}")
                elif policy == "business_paused":
                    self.logger.info(f"{login_data['id']}, {self.list_key} 业务禁用：保留采集但关闭代收/代付派单")
                elif policy == "order_paused":
                    self.logger.info(f"{login_data['id']}, {self.list_key} 全局暂停接单：保留采集但关闭代收/代付派单")
                else:
                    self.logger.info(f"{login_data['id']}, {self.list_key} 保持采集和代付但关闭代收派单： {login_data['id']}")
                return True
            self.runtime_service.set_kickoff(
                login_data['id'],
                phone=login_data.get('phone'),
                ttl=60 * 20,
                source="pakistanpay_v2",
                reason="statement_worker_offline",
            )
            self.logger.error(f"{login_data['id']}, {self.list_key} 下线接单： {login_data['id']}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('on_off 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            return False

    @staticmethod
    def _is_transient_bill_error(bill_result):
        if not isinstance(bill_result, dict):
            return False
        error_code = str(bill_result.get('error_code', '')).strip()
        error_message = str(bill_result.get('error_message', '') or '')
        return error_code == '423' or '云机正忙查单' in error_message

    def _should_force_statement_worker_offline(self, bill_result):
        return not self._is_transient_bill_error(bill_result)

    def update_key(self, login_data):
        try:
            policy = self.payment_runtime_policy(login_data['id'], login_data)
            if policy == "offline":
                self.runtime_service.force_offline(
                    login_data['id'],
                    phone=login_data.get('phone'),
                    source="pakistanpay_v2",
                    reason="payment_disabled",
                    channels=login_data.get('channels') or login_data.get('qr_channel') or login_data.get('channel'),
                )
                return
            df_order_enabled = self._df_order_enabled_for_policy(policy)
            self.runtime_service.sync_collection_job_state(
                login_data,
                source="pakistanpay_v2",
                schedule_score=int(time.time()),
                collect_enabled=True,
                ds_order_enabled=policy == "dispatch_on",
                df_order_enabled=df_order_enabled,
            )
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('update_key() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def async_session_context(self):
        """异步会话上下文管理器"""
        session = None
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            session = aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(ssl=False, limit=100)
            )
            self.logger.info("创建临时异步会话")
            yield session
        finally:
            if session and not session.closed:
                await session.close()
                self.logger.info("关闭临时异步会话")

    '''
    1. **添加上下文管理器async_session_context： 方法负责创建和管理异步会话的生命周期 
    2. **临时会话模式**：每次请求都创建一个新的临时会话，请求完成后自动关闭
    3. **自动资源管理**：使用async with 确保会话在使用完毕后被正确关闭
    4. **消除状态依赖**：不再依赖实例变量 self._async_session，完全无状态化
    5. **事件循环兼容**：每个新的事件循环都会创建对应的新会话，彻底解决循环绑定问题
    如果使用会话实例变量，会可能绑定到旧的会话中，而旧的会话可能已经关闭，导致"Event loop is closed" 错误
    '''
    async def make_request(self, login_data,  method, url, headers=None, params=None, data=None, json_data=None, proxies=None):
        self.logger.info(
            '请求 {method} {url}, params:{params} data:{data} json_data:{json_data}  代理： {proxies}'.format(
                method=method, url=url, params=params, data=data, json_data=json_data, proxies=proxies))

        try:
            response = None

            # 使用临时会话
            async with self.async_session_context() as session:
                # 准备请求参数
                kwargs = {
                    'headers': headers or {},
                    'params': params,
                    'allow_redirects': True,
                    'ssl': False
                }

                # 设置代理
                if proxies:
                    proxy_url = proxies.get('http') or proxies.get('https')
                    if proxy_url:
                        kwargs['proxy'] = proxy_url

                if method.upper() == 'GET':
                    async with session.get(url, **kwargs) as resp:
                        response_text = await resp.text()
                        response = self._create_response_wrapper(resp, response_text)

                elif method.upper() == 'POST':
                    if data is not None:
                        kwargs['data'] = data
                    elif json_data is not None:
                        kwargs['json'] = json_data
                    # 如果data和json_data都为None，发送空POST请求

                    async with session.post(url, **kwargs) as resp:
                        response_text = await resp.text()
                        response = self._create_response_wrapper(resp, response_text)
                else:
                    response = None

            if response is not None:
                self.logger.info(f'请求 {method} {url}, params:{params}, data:{data} json_data:{json_data}, response: {response}, response.text: {response.text}')
            return response

        except asyncio.TimeoutError as e:
            self.logger.error(f"网络请求错误1： uid: {login_data['id']}; 错误详情:{e}")
            return None
        except aiohttp.ClientError as e:
            self.logger.error(f"网络请求错误2： uid: {login_data['id']}; 错误详情:{e}")
            return None
        except Exception as e:
            self.logger.error(f"网络请求错误3： uid: {login_data['id']}; 错误详情:{e}")
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{login_data["id"]}, make_request 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(login_data)}')
            return None

    def _create_response_wrapper(self, aiohttp_response, response_text):
        """创建响应包装器，模拟requests.Response的接口"""

        class AsyncResponseWrapper:
            def __init__(self, aiohttp_resp, text):
                self.status_code = aiohttp_resp.status
                self.headers = dict(aiohttp_resp.headers)
                self.text = text
                self.url = str(aiohttp_resp.url)
                self.reason = aiohttp_resp.reason

                # 创建一个模拟的request对象
                self.request = self._create_mock_request(aiohttp_resp)

                # 尝试解析JSON
                try:
                    self._json = simplejson.loads(text) if text else None
                except:
                    self._json = None

            def _create_mock_request(self, aiohttp_resp):
                """创建模拟的request对象"""

                class MockRequest:
                    def __init__(self, aiohttp_resp):
                        self.method = aiohttp_resp.method
                        self.url = str(aiohttp_resp.url)
                        self.headers = dict(aiohttp_resp.request_info.headers) if hasattr(aiohttp_resp, 'request_info') else {}

                return MockRequest(aiohttp_resp)

            def json(self):
                """返回JSON数据"""
                if self._json is not None:
                    return self._json
                return simplejson.loads(self.text)

            @property
            def content(self):
                """返回字节内容"""
                return self.text.encode('utf-8')

            @property
            def encoding(self):
                """返回编码信息"""
                return 'utf-8'

            @property
            def elapsed(self):
                """返回耗时信息（模拟）"""

                class MockElapsed:
                    def total_seconds(self):
                        return 0.0

                return MockElapsed()

            @property
            def history(self):
                """返回重定向历史（空列表）"""
                return []

            def __str__(self):
                return f"<AsyncResponse [{self.status_code}]>"

            def __repr__(self):
                return self.__str__()

        return AsyncResponseWrapper(aiohttp_response, response_text)

    async def retry_make_request(self, *args, **kwargs):
        res = await self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.info(f"make_request() second try, args: {args}, kwargs: {kwargs}")
            res = await self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.warning(f"make_request() 获取响应错误, args: {str(args)}, kwargs: {str(kwargs)}")
            return res
        return res

    # 获取列表中的所有元素
    def read_redis_list(self, key):
        # 使用 lrange 获取列表中的所有元素
        elements = self.redis.lrange(key, 0, -1)  # 0 表示第一个元素，-1 表示最后一个元素
        # 将字节字符串解码为普通字符串
        decoded_elements = [element.decode('utf-8') for element in elements]
        # 转换为集合（自动去重）
        element_set = set(decoded_elements)

        # # 打印列表中的元素
        # if elements:
        #     self.logger.info(f"列表 '{key}' 中的元素如下：")
        #     for i, element in enumerate(elements):
        #         # 将字节字符串解码为普通字符串
        #         self.logger.info(f"{i + 1}: {element.decode('utf-8')}")
        # else:
        #     self.logger.info(f"列表 '{key}' 为空或不存在")

        return element_set

    # 打印所有的缓存,比较耗性能,生产环境可注释掉
    def read_cache(self, source, login_data):
        self.logger.info(f"{login_data['id']}, source: {source} 开始读取业务缓存")
        try:
            cache_key_lock = f'{self.name}_operate_{login_data['id']}'
            cache_key_upi_active_payment = f'upi_active_payment:{login_data['id']}'
            cache_key_device = f'{self.name}_device'

            self.logger.info(f"{login_data['id']}, read_cache() key: {self.set_key}, 成员 {login_data['id']}, score: {self.redis.zscore(self.set_key, login_data['id'])}, ttl: {self.redis.ttl(self.set_key)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {self.hash_key}, 成员 {login_data['id']}, hash value: {self.redis.hget(self.hash_key, login_data['id'])}, ttl: {self.redis.ttl(self.hash_key)}")
            self.logger.info(f"{login_data['id']}, read_cache() key: {cache_key_lock}, value: {self.redis.get(cache_key_lock)}, ttl: {self.redis.ttl(cache_key_lock)}")
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

    def encrypt_message(self, data, login_data):
        """easypaisa消息编码 - 与PHP版本的enc方法一致"""
        try:
            # 使用与PHP相同的AES-128-ECB加密
            hex_key = "f89e2d511390414a91a89fc5e0f8f5e4"
            key = bytes.fromhex(hex_key)

            # 创建AES-ECB加密器
            cipher = AES.new(key, AES.MODE_ECB)

            # PKCS7填充并加密
            padded_data = pad(data.encode('utf-8'), AES.block_size)
            encrypted_data = cipher.encrypt(padded_data)

            # 转换为大写十六进制
            return encrypted_data.hex().upper()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('encrypt_message() 失败{}输入数据:{}\n{}\n{}'.format(e, data, error_message, simplejson.dumps(login_data)))
            return ""

    def decrypt_message(self, data, login_data):
        """easypaisa消息解码 - 与PHP版本的de方法一致"""
        try:
            # 使用与PHP相同的AES-128-ECB解密
            hex_key = "f89e2d511390414a91a89fc5e0f8f5e4"
            key = bytes.fromhex(hex_key)

            # 验证输入数据格式
            if not data or len(data) % 2 != 0:
                self.logger.warning(f"Invalid hex data: {data}，{simplejson.dumps(login_data)}")
                return ""

            # 从十六进制转换为字节
            try:
                encrypted_data = bytes.fromhex(data)
            except ValueError as e:
                self.logger.warning(f"Invalid hex format: {data}，error: {e}，{simplejson.dumps(login_data)}")
                return ""

            # 验证数据长度是否为16的倍数（AES block size）
            if len(encrypted_data) % 16 != 0:
                self.logger.warning(f"Data length {len(encrypted_data)} is not multiple of 16，{simplejson.dumps(login_data)}")
                return ""

            # 创建AES-ECB解密器
            cipher = AES.new(key, AES.MODE_ECB)
            decrypted_padded = cipher.decrypt(encrypted_data)

            # 移除PKCS7填充
            decrypted_data = unpad(decrypted_padded, AES.block_size)

            # 转换为UTF-8字符串
            result = decrypted_data.decode('utf-8')
            return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('decrypt_message() 失败{}输入数据:{}\n{}\n{}'.format(e, data, error_message, simplejson.dumps(login_data)))
            return ""

    def get_standard_headers(self, login_data):
        """Get standard headers for requests."""
        return {
            # 'User-Agent': 'okhttp/4.12.0',
            'User-Agent': f'Dalvik/2.1.0 (Linux; U; Android 13; {login_data['model']} Build/TQ3A.230901.001)',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'Content-Type': 'application/json; charset=UTF-8',
            'Authorization': login_data['authorization']
        }

    # 通知前端 原 call_api
    async def notify(self, url, publish_data, login_data):
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            }
            self.logger.info(f"url: {url}, publish_data: {publish_data}, headers: {headers}")
            res = await self.retry_make_request(login_data, "POST", url=url, headers=headers, params=None, data=publish_data, json_data=None, proxies=None)
            if res is None:
                self.logger.error(f"{login_data['id']}, 发送{self.list_key} 通知url：{json.dumps(publish_data)} 结果：None")
                return False
            if not 200 <= res.status_code < 300:
                self.logger.error(f"{login_data['id']}, 发送{self.list_key} 通知url：{simplejson.dumps(publish_data)} 结果：{res.text}")
                return False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('notify 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
            return False

    # 调用API接口 /order/Success 用以修改status状态 原 call_api_order_success
    def normalize_callback_base(self, host):
        base_domain = (host or '').strip().rstrip('/')
        if base_domain.endswith('/api'):
            base_domain = base_domain[:-4]
        return base_domain

    def get_order_success_url(self):
        internal_host = self.normalize_callback_base(getattr(self, 'internal_callback_host', None))
        if internal_host:
            return f"{internal_host}/order/Success"
        base_domain = self.normalize_callback_base(getattr(self, 'domain', None))
        return f"{base_domain}/order/Success"

    async def send(self, orders_send, login_data):
        result = {"is_success": False}
        try:
            url = self.get_order_success_url()
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            }
            self.logger.info(f"{login_data['id']},send()发起请求：{url}, headers: {headers}, data: {orders_send}")
            res = await self.retry_make_request(login_data, "POST", url=url, headers=headers, params=None, data=orders_send, json_data=None, proxies=None)
            if res is None:
                error_message = f"error:{login_data['id']}, send {self.list_key}, callback message：None"
                self.logger.error(error_message)
                result['error_message'] = error_message
                return result
            self.logger.info(f"{login_data['id']}, 发送{self.list_key}回调信息：{res.text}")
            _res = simplejson.loads(res.text)

            # 如果是10025 upi重复，则直接下线
            if 'type' in orders_send and orders_send['type'] == 'UPI' and _res['code'] == 10025:
                orders_send['id'] = orders_send['payment_id']
                # 通知监控一键下线
                _key3 = 'login_off_realtime_{}_{}'.format(self.name, orders_send['id'])
                self.redis.set(_key3, 1, 60)
                await self.sendMsg(login_data, 'push_payment_information', False, 'upi already exist')  # upi重复通知
                self.logger.info(f"{login_data['id']}, {self.list_key} 更新upi重复，下线:{login_data['id']}, 结果：{res.text}")

            if res and (_res['code'] == 100):
                result["is_success"] = True
                return result
            else:
                error_message = f"payment_id: {login_data['id']}, 请求{url}失败：{orders_send}"
                result["error_code"] = _res['code']
                result["error_message"] = error_message
                return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = f"send() 脚本运行错误: {e}\n{''.join(tb_str)}\n{simplejson.dumps(login_data)}"
            self.logger.error(error_message)
            result["error_message"] = error_message
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
        # PHP verifyPin 方法
        return {"is_success": True}
        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            url = "https://indusupiprd.indusind.com/upi/api/verifyAppPinWeb"
            requestMsg_str = f'{{"appPin":{{"atmCrdLength":0,"credentialDataLength":0,"credentialDataValue":"{login_data['pinCode']}","otpCrdLength":0}},"deviceInfo":{{"androidId":"{login_data['androidId']}","app_gen_id":"{login_data['serv_gen_id']}","appName":"com.mgs.induspsp","appVersionCode":"59","appVersionName":"3.3.32","bluetoothMac":"00:00:00:00:00:00","capability":"5200000200010004000639292929292","deviceId":"{login_data['androidId']}","deviceType":"MOB","fcmToken":"{login_data['fcmToken']}","geoCode":"{login_data['geoCode']}","ip":"192.168.0.115","location":"{login_data['location']}","mobileNo":"{login_data['phone']}","os":"Android13","regId":"NA","relayButton":"Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU\u003d","safetyNetId":"{self.safetyNetId()}","selectedSimSlot":0,"simId":"{login_data['androidId']}2","wifiMac":"02:00:00:00:00:00"}},"requestInfo":{{"pspId":"10001","pspRefNo":"{self.safetyNetId()}"}}}}'
            requestMsg_hex = self.encrypt_message(requestMsg_str, login_data)
            payload = f'{{"pspId":"10001","requestMsg":"{requestMsg_hex}"}}'
            payload = simplejson.loads(payload)
            headers = self.get_standard_headers(login_data)
            self.logger.info(f"{login_data['id']}, grabUpi(), 发起请求：{url}, headers: {headers}, data: {payload}, proxies: {login_data['socks_ip']}")
            response = await self.retry_make_request(login_data, "POST", url=url, headers=headers, params=None, data=None, json_data=payload, proxies=login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{login_data['id']}, grabUpi() 方法响应失败")
                return result
            if not 200 <= response.status_code < 400:
                self.logger.error(f"{login_data['id']}, grabUpi() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                return result

            self.logger.info(f"{login_data['id']}, grabUpi() 方法 响应: {response.text}")
            response_data = response.json()
            response_data_decrypted = self.decrypt_message(response_data['resp'], login_data)
            self.logger.info(f"{login_data['id']}, grabUpi() 方法 解密之后响应: {response_data_decrypted}")
            response_data_decrypted = simplejson.loads(response_data_decrypted)

            result['error_code'] = response_data_decrypted['status']
            result['error_message'] = response_data_decrypted['statusDesc']

            if response_data_decrypted['status'] != "S":
                self.logger.error(f"payment_id: {login_data['id']}, grabUpi() ,提交PIN码错误: {response_data_decrypted}")
                return result

            try:
                linked_accounts_keys = []
                for i in response_data_decrypted['vpaAccountDetails']:
                    if i['virtualAddress']:
                        linked_accounts_keys.append(i['virtualAddress'])
            except Exception as e:
                self.logger.error(f"payment_id: {login_data['id']}, grabUpi() ,获取upi错误: {response_data_decrypted}")
                result['error_code'] = 'error'
                result['error_message'] = 'upi error'
                return result

            upi_list = [] if 'upi_list' not in login_data else login_data['upi_list']
            for upi in linked_accounts_keys:
                self.logger.info(f"payment_id: {login_data['id']}, get_upi() ,获取upi成功,upi: {upi}")
                if upi not in upi_list:
                    upi_list.append(upi)
            upi = linked_accounts_keys[0]  # 只获取第一个的upi
            # upi有更新时
            if 'upi' in login_data and upi != login_data['upi']:
                login_data['upi_remarks'] = f"{login_data['upi']} change to another upi:{upi}."
                self.logger.info(f"{login_data['id']}, get_upi(),upi更改,upi: {upi}")
            login_data['upi'] = upi
            login_data['upi_list'] = upi_list
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'grabUpi() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(login_data)}')
            result['error_message'] = error_message
        return result

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
            account_selected = self.get_payment_info(payment_id)
            payload = {"id": str(uuid.uuid4()), "action": "queryBill", "payload": {"account_id": account_id, "accno": account_selected}}
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
                        transactionHistoryList = response_data.get('data', {}).get('body', {}).get('transactionHistory', [])
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

    # 检测交易是否已回调过的, 原 is_transaction_synced
    def if_callback(self, utr: str, login_data) -> bool:
        """检测交易是否已回调过的"""
        # 判断有序集合中是否存在元素
        if self.redis.zscore(self.if_callback_key, f"{login_data['id']}_{utr}") is not None:
            # 已经回调过
            return True
        else:
            return False

    # 将账单记录标记为已回调过的,原 mark_transaction_synced
    def mark_transaction_callback(self, utr: str, login_data):
        self.redis.zadd(self.if_callback_key, {f"{login_data['id']}_{utr}": int(time.time())})

    async def callback_transaction(self, utr: str, mapped_trans: Dict, login_data) -> bool:
        callback_success = await self.transaction_callback(mapped_trans, login_data)
        if callback_success:
            self.mark_transaction_callback(utr, login_data)
            return True
        self.logger.error(f"easypaisa {login_data['id']}, 交易 {utr} 回调失败，不写入已回调标记")
        return False

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
                    self.logger.warning(f"{login_data['id']} UPI 临时失败，保留采集 worker 并继续账单采集")
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

            self.logger.info(f"easypaisa {login_data['id']} 爬取账单：")
            # 开始爬取账单
            getBills = await self.getBills(login_data)
            self.logger.info(f"easypaisa {login_data['id']},getBills(),返回数据, {getBills}")
            # 增加对返回结果的细致判断
            # 如果返回501，则重新登录
            self.logger.info(f"easypaisa {login_data['id']} 当前接口返回数据 {getBills} , code: {getBills.get('error_code', 'N/A')}")
            if isinstance(getBills, dict) and getBills.get('error_code') == 501:
                self.logger.error(f"easypaisa {login_data['id']} 抓取流水返回501错误，重新登录。")
                return 'logout'
            # 如果爬取失败（返回False），则下线
            elif isinstance(getBills['is_success'], bool) and getBills['is_success'] is False:
                self.logger.warning(f"easypaisa {login_data['id']} 抓取流水失败，保留当前采集态并等待短间隔重试。")
                login_data[f"last_grab_failed_{login_data['id']}"] = True
                self.logger.info(f"easypaisa 抓单失败，为 payment_id {login_data['id']} 标记失败状态，下次强制60秒重试")
                return False
            else:
                key = f"last_grab_failed_{login_data['id']}"
                if key in login_data:
                    del login_data[key]
                self.logger.info(f"easypaisa 抓单成功，清除 payment_id {login_data['id']} 的失败标记")

            # if getBills['is_success'] is False:
            #     self.logger.error(f"{login_data['id']},grabstatement(),爬取账单失败1, {getBills}")
            #     # 下线接单
            #     self.on_off(login_data, 0)
            #     login_data['time'] = int(time.time()) - self.time_grab2 + 1 * 60  # 更新时间，爬取upi失败后，约1分钟爬取一次，加快爬取，在限制次数下尝试多次不成功则退出
            #     login_data['remarks'] = "Failed to obtain bills."
            #     return False

            login_data['try_count'] = 0
            # self.logger.info(f"爬取账单，原始数据 {getBills}")
            self.logger.info(f"easypaisa 爬取账单，成功 {login_data['id']}")
            # 抓取交易记录为空
            if 'transaction_history_list' not in getBills or not getBills['transaction_history_list']:
                # 首次爬取之后设置为非首次爬取
                login_data['if_first_time'] = False
                self.logger.info(f"easypaisa {login_data['id']} 爬取账单为空：" + simplejson.dumps(login_data))
                # {"status":"S","encKey":"f89e2d511390414a91a89fc5e0f8f5e4","statusDesc":"SUCCESS","requestInfo":{"pspId":0,"pspRefNo":"INDB742A50521DD24A81B20C0B9AF7"},"isMerchant":false}
                return True

            # 开始检测哪些账单需要回调,根据utr来确认唯一性
            counter = 0
            for transaction in getBills['transaction_history_list']:
                self.logger.info(f"easypaisa grabstatement {login_data['id']} 数据抓取成功")
                self.logger.info(f"easypaisa {counter}:  transaction： {transaction}")
                utr = transaction['orderNo']
                if 'appTransaction' not in transaction or transaction['appTransaction'] != True:
                    self.logger.error(f"easypaisa {login_data['id']}, 状态不为成功 {utr}")
                    continue
                if if_first_time:
                    # 首次爬取账单, 将账单记录标记为已回调过的
                    self.mark_transaction_callback(utr, login_data)
                    self.logger.info(f"easypaisa {login_data['id']}, 首次爬取账单, 将账单记录标记为已回调过的 {utr} 已回调过，跳过")
                    continue
                # 检查是否已回调
                if self.if_callback(utr, login_data):
                    self.logger.info(f"easypaisa {login_data['id']}, 交易 {utr} 已回调过，跳过")
                    continue
                self.logger.info(f"easypaisa {login_data['id']}, 准备回调交易 {utr}")

                # 数据封装
                detail_dto = transaction.get('historyDetailRspDTO', {})
                self.logger.info(f"easypaisa 交易流水获取: Transaction {counter}:{utr}。")
                counter += 1
                account_id = login_data.get('phone', '')
                self.logger.info(f"easypaisa 交易流水获取: account_id {account_id}。")
                # 第一优先级：fromFri 包含 923499681697 -> 出款
                # 第二优先级：gatherNo 不等于 03499681697 -> 出款（受益人不是自己）
                # 默认：入款
                account_no_full = detail_dto.get('fromFri', '')
                # 获取 gatherNo 并为其设置默认值为 None
                gatherNo_full = detail_dto.get('gatherNo', None)
            
                # 默认设置为入款
                df_flag = False
                # 将 account_id 标准化为不带前缀的格式
                if account_id.startswith('0'):
                    account_id = account_id[1:]
                # 如果您的 account_id 可能会是 92 开头，也进行相应处理
                elif account_id.startswith('92'):
                    account_id = account_id[2:]

                    
                # 优先级1: 如果 fromFri 包含自己的手机号，则判定为出款  account_id是码绑定的手机号
                if account_id in detail_dto.get('fromFri', ''):
                    self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代付Y1】手机号 {account_id} 存在于 fromFri。")
                    df_flag = True
                else:
                    # 优先级2: 如果 gatherNo 不包含自己的手机号，则判定为出款
                    if gatherNo_full and account_id not in gatherNo_full:
                        self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代付Y2】手机号 {account_id} 不存在于 gatherNo, {gatherNo_full}。")
                        df_flag = True
                    elif gatherNo_full:
                        self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代收N3】手机号 {account_id} 存在于 gatherNo, {gatherNo_full}。")
                        df_flag = False
                    else:
                        # 如果 gatherNo 为 None，则默认处理为入款
                        self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代收N4】gatherNo 为 None，默认处理为入款。")
                        df_flag = False
            
                from_fri = detail_dto.get('fromFri', '')
                # 检查 account_id 是否不在 from_fri 中，并且 'MSISDN' 是否在 from_fri 中  →入款
                if account_id not in from_fri and 'MSISDN' in from_fri:
                    self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代收Y1】手机号 {account_id} 存在于 fromFri。")
                    df_flag = False

                # 调用 get_payment_info 方法获取账户信息
                payment_id = login_data['id']
                account_accno = self.get_payment_info(payment_id)
                self.logger.info(f"easypaisa 子账号取得: account_accno {account_accno}。")

                if '/MSISDN' in from_fri:
                    # 用手机号判断
                    if account_id in from_fri:
                        df_flag = True   # 出款
                    else:
                        df_flag = False  # 代收

                elif '/MM' in from_fri:
                    # 用银行账号ID判断
                    if account_accno in from_fri:
                        df_flag = True   # 出款
                    else:
                        df_flag = False  # 代收


                # 20251010 根据群对接巴基斯坦支付api  调整
                # "accountNo": "03423313388",
                # 判断这个如果是自己手机号码就是出款，不是自己手机号码就是入款  && 获取收款账号也是accountno
                # if account_id in detail_dto.get('accountNo', ''):
                #     df_flag = True
                # else:
                #     df_flag = False

                if df_flag:
                    txn_type = 'PAY'
                else:
                    txn_type = 'CREDIT'
            
                extOrderNo = detail_dto.get('extOrderNo', '')
                self.logger.info(f"easypaisa grabstatement【收入类别】数据编号 {counter} 当前流水号: {extOrderNo}， 收入类别 {txn_type}")
            
                txn_status = 'SUCCESS' if transaction.get('appTransaction') else 'FAILED'
                
                fromFri = detail_dto.get('accountNo', '')

                # 去掉前缀 0 或 92
                normalized = fromFri

                # 去掉前导 92（巴基斯坦国际码）
                while normalized.startswith("92"):
                    normalized = normalized[2:]

                # 去掉所有前导 0
                while normalized.startswith("0"):
                    normalized = normalized[1:]

                self.logger.info(f"easypaisa normalized={normalized}=========detail_dto==={detail_dto}==")

                extracted_number = normalized

                # if df_flag:
                #     # 提取 accountNo 字符串
                #     extracted_number = detail_dto.get('accountNo', '')
                #     # 使用切片从字符串末尾提取最后 10 位  移除处理
                #     # if account_no:
                #     #     extracted_number = account_no[-10:]
                #     # else:
                #     #     extracted_number = None
                # else:
                #     # 提取 fromFri 字符串
                #     # fromFri = detail_dto.get('fromFri', '')
                #     fromFri = detail_dto.get('accountNo', '')
                #     extracted_number = None
                #     print('fromFri=============================================',fromFri)
            
                #     # 优化后的正则表达式，能同时匹配有斜杠和没有斜杠的情况
                #     match = re.search(r'FRI:(?:92|0)?(\d+)(?:/|$)', fromFri)
            
                #     if match:
                #         # match.group(1) 将捕获括号内的数字部分
                #         extracted_number = match.group(1)
            
                #         # 如果提取到了号码，可以进一步标准化，比如去掉国家代码
                #         if extracted_number.startswith('92'):
                #             extracted_number = extracted_number[2:]
            
                #         self.logger.info(f"grabstatement 提取到的手机号是: {extracted_number}")
                #     else:
                #         extracted_number = extOrderNo
                #         self.logger.info(f"未能从 fromFri 字段中提取到手机号。{extracted_number}")
                    # extracted_number = f"{extracted_number},extOrderNo={extOrderNo}"
                
                gatherNo = detail_dto.get('gatherNo') or ''
                self.logger.info(f"easypaisa gatherNo原始值 ========={gatherNo}============================")

                normalized = gatherNo.strip()  # 防止空格

                # 如果以 AC 开头（不区分大小写）
                if normalized.upper().startswith("AC"):
                    normalized = normalized[2:]

                payeeAccountNo = normalized
                self.logger.info(f"easypaisa payeeAccountNo =============={payeeAccountNo}=======")

                mapped_trans = {
                    'txnType': txn_type,
                    'txnAmount': transaction.get('amount', 0.0)+detail_dto.get('fee', 0),
                    'custRefNo': extracted_number,
                    'txnStatus': txn_status,
                    'txnNote': transaction.get('busTypeName', ''),
                    'accountNo': extracted_number,
                    'payeeAccountNo': payeeAccountNo,
                    'payeeIfsc': '',
                    'tradeTime': transaction.get('tradeTime', ''),
                    'extOrderNo': extOrderNo,
                    'fee': detail_dto.get('fee', 0),
                    'appTransaction': transaction.get('appTransaction', False)
                }
                # 回调
                self.logger.info(f"easypaisa grabstatement 数据编号{counter}封装后的数据: mapped_trans {mapped_trans} 。")
                await self.callback_transaction(utr, mapped_trans, login_data)
                counter += 1
            # 首次爬取之后设置为非首次爬取
            login_data['if_first_time'] = False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('easypaisa grabstatement() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(login_data)))
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
                self.redis.delete(_key2)
                self.logger.warning(f"{self.list_key} 发现旧 login_off 标记，仅清理标记并按 runtime 策略继续采集:" + simplejson.dumps(login_data))

            # 通知监控一键下线
            _key3 = 'login_off_realtime_{}_{}'.format(self.name, login_data['id'])
            login_off = self.redis.get(_key3)
            if login_off:  # 直接下线
                # 删除标识在线的key
                self.redis.delete(_key1)
                self.redis.delete(_key2)
                self.redis.delete(_key3)
                # 登出
                self.logger.error(f"{self.list_key} 通知监控一键下线，登出:" + simplejson.dumps(login_data))
                await self.login_off(login_data)
                return 'logout'

            grabstatement = False
            #  如果有相关的key，按短时间爬取一次，如果没有，则按长时间一次
            crawl_frequently = self.redis.get('crawl_frequently_{}'.format(login_data['id']))
            # 【核心修改】：抓单失败后强制走60秒短间隔
            self.logger.info(f"login_data==检测=={login_data}")
            if login_data.get(f"last_grab_failed_{login_data['id']}", False):
                _time_grab = 60
                self.logger.info(f"检测到 payment_id {login_data['id']} 上次抓单失败，强制使用60秒短间隔")
            elif crawl_frequently or ('try_count' in login_data and login_data['try_count'] > 0):
                # 有相关的key或者有重试的，都按指定的最短时间爬取一次
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
                    login_data['last_grab_failed'] = True   # ← 关键！打上失败标记
                    self.logger.info(f"抓单失败，标记 last_grab_failed=True，下次强制60秒重试")
                else:
                    login_data.pop('last_grab_failed', None)  # 成功就清除标记
                # # 增加重试次数的逻辑，现在包含对501错误的判断
                # if (isinstance(grabstatement, bool) and grabstatement is False) or (isinstance(grabstatement, dict) and grabstatement.get('status_code') == 501):
                #     # 只有在抓取流水失败（返回False）或者返回501错误时，才增加try_count
                #     login_data['try_count'] = 1 if 'try_count' not in login_data else login_data['try_count'] + 1
                #     self.logger.info(f"{login_data['id']} 抓取流水失败或返回501，当前重试次数: {login_data['try_count']}")

                if isinstance(grabstatement, str) and grabstatement == 'logout':
                    self.redis.delete(_key1)
                    self.redis.delete(_key2)
                    self.redis.delete(_key3)
                    self.logger.error(f"{self.list_key} 需要登出，交由上层统一 login_off:" + simplejson.dumps(login_data))
                    return 'logout'

                if 'count' in login_data and login_data['try_count'] > self.try_count_limit:
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

    def safetyNetId(self):
        """生成安全网络ID"""
        str_uuid = str(uuid.uuid4()).replace('-', '')
        return "INDB" + str_uuid.upper()[:26]

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

    # 清理 if_callback_key 中时间较久的utr ,避免已经回调过的utr数据量过大
    def clean_if_callback_key(self):
        # 设定时间阈值
        threshold = int(time.time()) - self.clean_if_callback_key_time
        # 移除有序集合if_callback_key中，所有时间戳早于threshold的成员
        removed_count = self.redis.zremrangebyscore(self.if_callback_key, '-inf', threshold)
        self.logger.info(f" {self.if_callback_key} 移除过期的utr数据： {removed_count} 个")
        # 后面可添加清理 f'{self.name}_device' 相关的hash key数据

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
        self.logger.info(f"easypaisa verify_and_handle_abnormal_payout 异常订单数据: {order_data}")
        receive_account = order_data.get('account_id', '')
        amount = order_data.get('amount', '')
        time_created = order_data.get('time_created', '')
        account_id = login_data.get('phone', '')
        if not receive_account or not amount or not time_created:
            self.logger.error(f"easypaisa verify_and_handle_abnormal_payout 异常订单数据无效: {order_data}")
            return
        # 初始化或增加 try_count
        if 'try_count' not in login_data:
            login_data['try_count'] = 0
        try:
            # 调用 getBills 方法
            bill_result = await self.getBills(login_data)
            self.logger.info(f"easypaisa verify_and_handle_abnormal_payout {login_data['id']}, verify_and_handle_abnormal_payout 爬取账单, {bill_result}")
            if bill_result['is_success'] is False:
                self.logger.error(f"easypaisa verify_and_handle_abnormal_payout {login_data['id']}, verify_and_handle_abnormal_payout 爬取账单失败, {bill_result}")
                # 增加对返回结果的细致判断
                # 如果返回501，则重新登录
                self.logger.info(f"easypaisa verify_and_handle_abnormal_payout {login_data['id']} 当前接口返回数据 {bill_result} , code: {bill_result.get('error_code', 'N/A')}")
                if isinstance(bill_result, dict) and bill_result.get('error_code') == 501:
                    self.logger.error(f"easypaisa {login_data['id']} 抓取流水返回501错误，重新登录。")
                    return 'logout'
                # 如果爬取失败（返回False），则下线
                elif isinstance(bill_result['is_success'], bool) and bill_result['is_success'] is False:
                    self.logger.warning(f"easypaisa {login_data['id']} 异常补核抓取流水失败，保留当前采集态。")
                    return False

            transaction_history = bill_result.get('transaction_history_list', [])
            #  爬取交易记录：{transaction_history} 移除
            self.logger.info(f"easypaisa verify_and_handle_abnormal_payout {receive_account}, {order_data}, 记录数量 {len(transaction_history)}")
            matched = False
            counter = 1
            for trans in transaction_history:
                self.logger.info(f"easypaisa verify_and_handle_abnormal_payout {login_data['id']} 数据抓取成功")
                detail_dto = trans.get('historyDetailRspDTO', {})

                self.logger.info(f"easypaisa verify_and_handle_abnormal_payout 交易流水获取: Transaction {counter}:{detail_dto}。")
                utr = trans['orderNo']
                counter += 1
                # 检查是否已回调
                if self.if_callback(utr, login_data):
                    self.logger.info(f"easypaisa {login_data['id']}, 交易 {utr} 已回调过，跳过")
                    continue
                # {trans}移除
                self.logger.info(f"easypaisa {login_data['id']}, 准备回调交易 {utr}")
                # 第一优先级：fromFri 包含 923499681697 -> 出款
                # 第二优先级：gatherNo 不等于 03499681697 -> 出款（受益人不是自己）
                # 默认：入款
                account_no_full = detail_dto.get('fromFri', '')
                # 获取 gatherNo 并为其设置默认值为 None
                gatherNo_full = detail_dto.get('gatherNo', None)

                # 默认设置为入款
                df_flag = False  
                account_id = login_data.get('phone', '')
                # 将 account_id 标准化为不带前缀的格式
                if account_id.startswith('0'):
                    account_id = account_id[1:]
                # 如果您的 account_id 可能会是 92 开头，也进行相应处理
                elif account_id.startswith('92'):
                    account_id = account_id[2:]
                
                # 优先级1: 如果 fromFri 包含自己的手机号，则判定为出款  account_id是码绑定的手机号
                if account_id in detail_dto.get('fromFri', ''):
                    self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代付Y1】手机号 {account_id} 存在于 fromFri。")
                    df_flag = True
                else:
                    # 优先级2: 如果 gatherNo 不包含自己的手机号，则判定为出款
                    if gatherNo_full and account_id not in gatherNo_full:
                        self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代付Y2】手机号 {account_id} 不存在于 gatherNo, {gatherNo_full}。")
                        df_flag = True
                    elif gatherNo_full:
                        self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代收N3】手机号 {account_id} 存在于 gatherNo, {gatherNo_full}。")
                        # df_flag = False
                    else:
                        # 如果 gatherNo 为 None，则默认处理为入款
                        self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代收N4】gatherNo 为 None，默认处理为入款。")
                        # df_flag = False
            
                from_fri = detail_dto.get('fromFri', '')
                # 检查 account_id 是否不在 from_fri 中，并且 'MSISDN' 是否在 from_fri 中  →入款
                if account_id not in from_fri and 'MSISDN' in from_fri:
                    self.logger.info(f"easypaisa grabstatement 交易流水获取: Transaction {counter}:【流水标记代收Y1】手机号 {account_id} 存在于 fromFri。")
                    # df_flag = False

                # 调用 get_payment_info 方法获取账户信息
                payment_id = login_data['id']
                account_accno = self.get_payment_info(payment_id)
                self.logger.info(f"easypaisa 子账号取得: account_accno {account_accno}。")

                if '/MSISDN' in from_fri:
                    # 用手机号判断
                    if account_id in from_fri:
                        df_flag = True   # 出款
                    else:
                        pass
                        # df_flag = False  # 代收

                elif '/MM' in from_fri:
                    # 用银行账号ID判断
                    if account_accno in from_fri:
                        df_flag = True   # 出款
                    else:
                        pass
                        # df_flag = False  # 代收

                # 20251010 根据群对接巴基斯坦支付api  调整
                # "accountNo": "03423313388",
                # 判断这个如果是自己手机号码就是出款，不是自己手机号码就是入款  && 获取收款账号也是accountno
                # if account_id in detail_dto.get('accountNo', ''):
                #     df_flag = True
                # else:
                #     df_flag = False
                if not df_flag:
                    continue

                # === 新增：风控检查 payment_id_failed ===
                try:
                    # 获取交易发生时间（从 '2025-11-13T10:50:12' 格式转换）
                    trans_time_str = detail_dto.get('tradeTime', '')
                    # 注意：如果时间格式不确定，需要更健壮的解析，这里假设格式是固定的
                    # trans_time = datetime.strptime(trans_time_str, '%Y-%m-%dT%H:%M:%S')
                    trans_time = datetime.strptime(trans_time_str, '%Y-%m-%dT%H:%M:%S')

                    # failed_time = datetime.fromtimestamp(time_created)
                    # ********** 关键修改处 **********
                    # time_created 现在是 '2025-11-21 14:15:08' 字符串，使用 strptime 解析
                    failed_time = datetime.strptime(time_created, '%Y-%m-%d %H:%M:%S')
                    # ********************************

                    self.logger.info(f"easypaisa {login_data['id']}, 交易 {utr}: 失败标记时间: {failed_time}，交易时间: {trans_time}。")
                    # 1.只比对  异常订单发生的那一刻的后面的 账单   10.00发生的这一笔异常订单  只比对10.00点 往后的账单
                    if trans_time <= failed_time:
                        # 记录因风控逻辑跳过
                        self.logger.info(f"easypaisa {login_data['id']}, 交易 {utr}: 【风控跳过：交易时间早于失败标记时间】 失败标记时间: {failed_time}，交易时间: {trans_time}。")
                        continue
                        
                except Exception as e:
                    self.logger.error(f"easypaisa 处理 payment_id_failed 检查时发生异常: {e}")
                    pass
                # === 新增风控检查结束 ===

                from_fri = detail_dto.get('fromFri', '')
                # 检查 account_id 是否不在 from_fri 中，并且 'MSISDN' 是否在 from_fri 中  →入款
                # if account_id not in from_fri and 'MSISDN' in from_fri:
                #     self.logger.info(f"verify_and_handle_abnormal_payout 交易流水获取: Transaction {counter}:【流水标记代收Y1】手机号 {account_id} 存在于 fromFri。")
                #     df_flag = False
        
                gatherNo = detail_dto.get('gatherNo') or ''
                self.logger.info(f"easypaisa gatherNo原始值 ========={gatherNo}============================")

                normalized = gatherNo.strip()  # 防止空格

                # 如果以 AC 开头（不区分大小写）
                if normalized.upper().startswith("AC"):
                    normalized = normalized[2:]

                payeeAccountNo = normalized
                self.logger.info(f"easypaisa payeeAccountNo =============={payeeAccountNo}=======")

                if receive_account in payeeAccountNo and trans.get('amount') == amount and df_flag:
                    matched = True
                    self.logger.info(f"{account_id}, {amount}订单在账单中已找到，触发回调处理")
                    # 根据 accountNo 判断交易类型
                    txn_type = 'PAY'
                    # 根据 appTransaction 判断交易状态
                    txn_status = 'SUCCESS' if trans.get('appTransaction') else 'FAILED'
                    # 构造 mapped_trans 与 get_grabstatement 一致
                    if df_flag:
                        # 提取 accountNo 字符串
                        account_no = detail_dto.get('accountNo', '')
                        # 使用切片从字符串末尾提取最后 10 位  这个处理移除
                        # if account_no:
                        #     extracted_number = account_no[-10:]
                        # else:
                        #     extracted_number = None
                                
                        mapped_trans = {
                        'txnType': txn_type,
                        'txnAmount': trans.get('amount', 0.0)+detail_dto.get('fee', 0),
                        'custRefNo': account_no,
                        'txnStatus': txn_status,
                        'txnNote': trans.get('busTypeName', ''),
                        'accountNo': account_no,
                        'payeeAccountNo': payeeAccountNo,
                        'payeeIfsc': '',
                        'tradeTime': trans.get('tradeTime', ''),
                        'extOrderNo': detail_dto.get('extOrderNo', ''),
                        'fee': detail_dto.get('fee', 0),
                        'appTransaction': trans.get('appTransaction', False)
                        }
                    # 调用 transaction_callback
                    await self.callback_transaction(utr, mapped_trans, login_data)
                    self.logger.info(f"easypaisa 成功处理了第 {counter} 条记录。") # 添加这一行
                    counter += 1
                    break
            if not matched:
                self.logger.error(f"{account_id}, {amount}订单未匹配，标记异常")
                order_data['status'] = 'abnormal_unmatched'
                # 确保 ABNORMAL_PAYOUTS_KEY 是已定义的常量 Todo
                # self.redis.hset(ABNORMAL_PAYOUTS_KEY, utr, simplejson.dumps(order_data))
                # await self.reallocate_order(order_data)
        except Exception as e:
            tb_str = traceback.format_exc()
            self.logger.error(f"easypaisa {account_id}, verify_and_handle_abnormal_payout 错误: {e}\n{tb_str}")


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
                ABNORMAL_PAYOUTS_KEY = f"payment_id_failed:{_id}"  # 修改为 payment_id_failed:* 格式
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

                        abnormal_result = await self.verify_and_handle_abnormal_payout(login_data, converted_order_data)
                        if abnormal_result == 'logout':
                            res = 'logout'
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
                    # 对检测短信是否发送的时间有要求, 必须放到前面
                    # if login_data['status'] == 'wait_client_send_sms':
                    #     self.redis.zadd(self.set_key, {login_data['id']: 0})
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
            # 生成新的trace_id
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"

            # 1 先检查pre_login_*中的相关数据，查看是否已经有成功的
            pre_lgoin_keys = f"pre_login_{self.name}_*"
            keys = self.redis.keys(pre_lgoin_keys)
            self.logger.info(f"待抓取账单: {pre_lgoin_keys}，共获取到 {len(keys)} 个待处理pre_lgoin_keys：{keys}")

            for key in keys:
                _id = key.decode()
                self.logger.info(f"当前正在处理: {_id}")

                # 获取 key 对应的 value（json string）
                value = self.redis.get(_id)
                if not value:
                    self.logger.warning(f"{_id} 对应值为空，跳过处理")
                    continue

                data = self._load_pre_login_entry(value, _id)
                if not data:
                    continue
                if self._handle_pre_login_alias(_id, data):
                    continue

                _lock = self.get_lock(_id)
                if not _lock:
                    self.logger.warning(f"{_id} 未获取到锁，跳过")
                    continue

                value = self.redis.get(_id)
                if not value:
                    self.logger.warning(f"{_id} 对应值为空，跳过处理")
                    self.del_lock(_id, _lock)
                    continue

                data = self._load_pre_login_entry(value, _id)
                if not data:
                    self.del_lock(_id, _lock)
                    continue
                if self._handle_pre_login_alias(_id, data):
                    self.del_lock(_id, _lock)
                    continue
                if self.redis.hexists(self.hash_key, data['id']):
                    # 如果有，则抛弃 删除pre_login*
                    self.redis.delete(_id)
                    self.logger.error(f" {self.hash_key} {data['id']} 已存在数据！")
                else:
                    # 如果没有则放置在hash和有序集合
                    # if data.get("status") == "loginSuccessful":
                    # 将status值转为小写后再进行判断
                    status = data.get("status")
                    if status and status.lower() == "activesuccessful":
                        self.logger.info(f"{_id} {data['real_payment_id']}登录成功，推进至抓账单阶段")
                        data['status'] = "grabstatement"
                        data['id'] = data['real_payment_id']
                        policy = self.payment_runtime_policy(data['id'], data)
                        if policy == "offline":
                            self.runtime_service.force_offline(
                                data['id'],
                                phone=data.get('phone'),
                                source="pakistanpay_v2",
                                reason="payment_disabled",
                                channels=data.get('channels') or data.get('qr_channel') or data.get('channel'),
                            )
                            self.redis.delete(_id)
                            self.del_lock(_id, _lock)
                            continue
                        self.runtime_service.sync_collection_job_state(
                            data,
                            source="pakistanpay_v2",
                            schedule_score=0,
                            collect_enabled=True,
                            ds_order_enabled=policy == "dispatch_on",
                            df_order_enabled=self._df_order_enabled_for_policy(policy),
                        )
                        self.logger.info(f"已将 {data['id']} {data['real_payment_id']}推入 hash_key: {self.hash_key} 和 zset: {self.set_key}")
                        # 删除pre_login*
                        self.redis.delete(_id)
                        self.logger.info(f"已删除当前用户账单 {_id}，{data['real_payment_id']}已经进入处理中")
                    else:
                        self.logger.info(f"⏩ {_id} {data.get('real_payment_id')} 状态为 {data.get('status')}，跳过")

                self.del_lock(_id, _lock)

            # 2 处理有序集合数据 - 使用分片和并发处理
            self.read_zset(self.set_key)

            # 从有序集合中，获取10S外的成员，增加获取数量以支持多进程分片
            zrangebyscore_max = int(time.time()) - 10
            # 增加获取数量，考虑多进程分片的情况
            batch_size = 200  # 原来是100，现在增加到200
            members = self.redis.zrangebyscore(self.set_key, 0, zrangebyscore_max, 0, batch_size)

            if not members:
                self.logger.info(f"{self.set_key} min:0, max:{zrangebyscore_max} set中没有数据")
                # 清理 if_callback_key 中时间较久的utr ,避免已经回调过的utr数据量过大
                self.clean_if_callback_key()
                time.sleep(2)
                return

            # 根据进程数量分配members
            allocated_members = self.get_process_allocated_members(members)

            if not allocated_members:
                self.logger.info(f"进程 {os.getpid()} 没有分配到需要处理的数据")
                time.sleep(2)
                return

            # 使用协程并发处理分配的members
            try:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # 并发处理，每个进程最多20个并发
                loop.run_until_complete(self.process_members_concurrent(allocated_members, concurrent_limit=20))

            except Exception as e:
                self.logger.error(f"并发处理失败: {e}")

            finally:
                # 关闭事件循环
                if loop and not loop.is_closed():
                    loop.close()

        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('main过程错误： 错误详情：{}\n{}'.format(e, error_message))


# 主程序入口
if __name__ == "__main__":
    try:
        logger.info(f"{'=' * 10}easypaisa协议启动{'=' * 10}")
        bank = BankLogin("easypaisa")
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
