"""
EasyPaisa自动代付系统
补充order_push.py中的Redis防护机制
"""
import os
import sys
import time
import uuid
import json
import secrets
import hashlib
import asyncio
import threading
import redis
import pymysql
from datetime import datetime, timedelta
from decimal import Decimal
from queue import Queue, Empty
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
import logging
import logging.handlers
from logging.handlers import TimedRotatingFileHandler
import traceback
import aiohttp
import simplejson

# 将项目的主目录添加进系统path
root_dir = os.path.dirname(__file__)  # jobs/easypaisa
root_dir = os.path.dirname(root_dir)  # jobs
root_dir = os.path.dirname(root_dir)  # api根目录
sys.path.append(root_dir)

from config import get_config
from application.websocket import callback
from jobs.easypaisa.scheduling_state import (
    EMERGENCY_STOP,
    NO_AVAILABLE_ACCOUNTS,
    NO_ORDERS,
    classify_round_state,
    should_return_account_to_pool,
)
from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

# ========== 日志系统 ==========
# 程序名称（用于日志）
PROGRAM_NAME = 'auto_payout'

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

# 注册自定义日志记录器
logging.setLoggerClass(ProgramLogger)

# TraceIDFilter 类 - 添加协程安全
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
    LOG_FILE = os.path.join(current_dir, f"easypaisa_auto_payout_{os.getpid()}.log")

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


conf = get_config()

# ========== 常量定义 ==========

# EasyPaisa API配置参数
EASYPAISA_API_URL = getattr(conf, 'easypaisa_api_url', 'http://34.150.42.92:83')
EASYPAISA_USER_ID = getattr(conf, 'easypaisa_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
EASYPAISA_SECRET_KEY = getattr(conf, 'easypaisa_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')


# ========== EasyPaisa自动代付系统 ==========
class EasyPaisaAutoPayout:
    def __init__(self, name):
        self.name = name
        # Redis键名定义
        self.list_key = f"list_{name}"
        self.hash_key = f"hash_{name}"
        self.set_key = f"set_{name}"
        
        # 系统配置参数
        self.lock_time = 120  # 操作锁的锁定时间（秒） - 修改为120秒以适配60秒转账API超时

        # 系统组件
        self.logger = logger
        self.local_mock = False  # 本地模拟标志
        self.log_handler = file_handler
        

        # 连接Redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        self.runtime_service = SyncEasyPaisaRuntimeService(self.redis)
        
        # 会议决策：异常当成功处理（已内置到逻辑中）
        
        # 系统配置
        self.concurrent_limit = 20
        
        # 新增：Redis键名配置
        self.REDIS_KEYS = {
            'easypaisa_online_df': 'payment_online_df',           # EasyPaisa在线代付账号集合（复用项目标准键名）
            'easypaisa_active_df': 'payment_active_df',           # EasyPaisa活跃代付账号列表（复用项目标准键名）
            'easypaisa_balance_sorted_set': 'easypaisa_balance_sorted',  # EasyPaisa余额有序集合
            'easypaisa_balance_prefix': 'easypaisa_balance:',       # EasyPaisa余额缓存前缀（兼容性保留）
            'easypaisa_account_used_prefix': 'easypaisa_account_used:',  # 账号使用记录前缀（支持动态冷却期）
            'easypaisa_release_time': 'easypaisa_release_time',     # EasyPaisa账号释放时间Hash
            'easypaisa_failures': 'easypaisa_failures',             # EasyPaisa失败记录Hash（统一存储）
            'easypaisa_emergency_stop': 'easypaisa_emergency_stop', # 紧急停机标记
            'grab_df_prefix': 'grab_df_',                           # 订单锁前缀
            'easypaisa_account_lock_prefix': 'easypaisa_account_lock:', # 账号锁前缀
            'payment_id_lock_prefix': 'payment_id_lock:',           # Payment ID锁前缀
            'payment_id_failed_prefix': 'payment_id_failed:',       # Payment ID失败锁前缀(简单冷却标记)
            'easypaisa_order_cooldown_hash': 'easypaisa_order_cooldown',  # 订单冷却期Hash表
            'easypaisa_order_cooldown_config': 'easypaisa_order_cooldown_config'  # 订单冷却期配置（支持动态配置）
        }
        
        # 幽灵账号缓存（进程级，5分钟过期）
        self._invalid_payment_cache = {}  # {payment_id: expire_timestamp}

        # 操作日志记录开关
        self.operation_logs_enabled = True
        self._verify_operation_logs_table()
        
        # 兼容 success_df 函数需要的属性
        self.qr_id = None  # 当前处理的 payment_id，在调用 success_df 前需要设置
    
    def get_log_stats(self):
        """获取日志统计信息（如果使用异步处理器）"""
        if hasattr(self.log_handler, 'get_stats'):
            return self.log_handler.get_stats()
        elif hasattr(self.log_handler, 'buffer'):
            return {
                'buffer_size': len(self.log_handler.buffer),
                'buffer_bytes': getattr(self.log_handler, 'buffer_bytes', 0),
                'is_running': not getattr(self.log_handler, '_shutdown', False)
            }
        return None
    
    # ========== 从BaseHandler复制的核心方法（同步版本） ==========
    
    def get_cache_result(self, table, keys, condition=None):
        """获取缓存数据（复制自BaseHandler.get_cache_result，同步版本）"""
        try:
            if not condition:
                condition = {'id': 1}
            
            redis_key = f'cache_info_{table}_{condition["id"]}'
            data_info = self.redis.get(redis_key)
            
            if data_info:
                # 缓存命中
                data_info = simplejson.loads(data_info, parse_float=Decimal)
                self.logger.info(f"缓存命中: {redis_key}")
            else:
                # 缓存未命中，查询数据库
                data_info = {}
                try:
                    # 创建临时数据库连接
                    connection = pymysql.connect(
                        host=conf['mysql_host'],
                        user=conf['mysql_user'],
                        password=conf['mysql_password'],
                        db=conf['mysql_database'],
                        charset='utf8mb4',
                        cursorclass=pymysql.cursors.DictCursor
                    )
                    
                    try:
                        # 构建WHERE条件 (对于sys_info表，默认查询id=1)
                        where_conditions = []
                        where_values = []
                        for key, value in condition.items():
                            where_conditions.append(f"{key} = %s")
                            where_values.append(value)
                        
                        where_clause = " AND ".join(where_conditions)
                        sql = f"SELECT * FROM {table} WHERE {where_clause}"
                        
                        with connection.cursor() as cur:
                            cur.execute(sql, where_values)
                            result = cur.fetchone()
                            if result:
                                data_info = result
                                # 存入缓存
                                self.redis.set(redis_key, simplejson.dumps(data_info))
                                self.logger.info(f"缓存数据已更新： {table} {condition}")
                    finally:
                        connection.close()
                        
                except Exception as e:
                    self.logger.error(f"查询缓存数据失败: table={table}, condition={condition}, error={e}")
                    data_info = {}
            
            # 返回指定字段
            if data_info:
                data_info = data_info if keys == ['*'] else {key: data_info[key] for key in keys if key in data_info}
            
            return data_info
            
        except Exception as e:
            self.logger.error(f"获取缓存数据失败: table={table}, keys={keys}, condition={condition}, error={e}")
            return {}
    
    def _format_sql(self, cur, sql, params=None):
        """格式化SQL用于日志显示（兼容PyMySQL版本）"""
        try:
            # PyMySQL 1.4.6+ 使用 mogrify 方法
            if hasattr(cur, 'mogrify') and params is not None:
                return cur.mogrify(sql, params).decode() if isinstance(cur.mogrify(sql, params), bytes) else cur.mogrify(sql, params)
            elif hasattr(cur, '_last_executed') and cur._last_executed:
                # 兼容老版本或aiomysql
                return cur._last_executed
            else:
                # 简单的参数替换（仅用于日志显示）
                if params:
                    formatted_sql = sql
                    for param in params:
                        formatted_sql = formatted_sql.replace('%s', repr(param), 1)
                    return formatted_sql
                return sql
        except Exception as e:
            # 如果格式化失败，返回原始SQL和参数
            return f"{sql} [参数: {params}]"

    def change_balance(self, conn, cur, table, user_id, amount, code, record_type, remark=None, merchant_code=None):
        """余额变更方法（复制自BaseHandler.change_balance，同步版本）"""
        sql_update = f'update {table} set balance=balance + %s where id = %s'
        sql_select = f"select balance{',vip' if table == 'partner' else ''} from {table} where id = %s"
        sql_insert = """insert into balance_record (code,user_type,user_id,change_before,amount,change_after,record_type,remark,merchant_code) value (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        sql_select_vip = "select vip,conditions from vip"
        sql_update_vip = "update partner set vip=%s where id = %s"
        sql_select_orders = f"SELECT merchant_code FROM orders_df WHERE code = '{code}' UNION SELECT merchant_code FROM orders_ds WHERE code = '{code}'"
        
        try:
            # 步骤1: 获取变更前余额
            params_1 = (user_id,)
            self.logger.info(f"步骤1: 准备查询{table}用户{user_id}的变更前余额")
            self.logger.info(f"执行SQL: {sql_select} 参数: {params_1}")
            if not cur.execute(sql_select, params_1):
                self.logger.error(f"步骤1失败: 查询变更前余额执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_select, params_1)}")
                return False
            
            user_before = (cur.fetchall())[0]
            balance_before = user_before['balance']
            self.logger.info(f"步骤1成功: 变更前余额={balance_before}")
            
            # 步骤2: 更新余额
            params_2 = (amount, user_id)
            self.logger.info(f"步骤2: 准备更新{table}用户{user_id}余额，变更金额={amount}")
            self.logger.info(f"执行SQL: {sql_update} 参数: {params_2}")
            if not cur.execute(sql_update, params_2):
                self.logger.error(f"步骤2失败: 更新余额执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_update, params_2)}")
                return False
            
            self.logger.info(f"步骤2成功: 更改金额{self._format_sql(cur, sql_update, params_2)}")
            
            # 步骤3: 获取变更后余额
            params_3 = (user_id,)
            self.logger.info(f"步骤3: 准备查询{table}用户{user_id}的变更后余额")
            self.logger.info(f"执行SQL: {sql_select} 参数: {params_3}")
            if not cur.execute(sql_select, params_3):
                self.logger.error(f"步骤3失败: 查询变更后余额执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_select, params_3)}")
                return False
            
            user_after = (cur.fetchall())[0]
            balance_after = user_after['balance']
            self.logger.info(f"步骤3成功: 变更后余额={balance_after}")
            
            # 步骤4: 检查余额是否足够（码商最低余额为0）
            partner_balance = 0
            if Decimal(balance_after) < partner_balance:
                self.logger.error(f"步骤4失败: 余额不足，user_id={user_id}, balance_after={balance_after}, 最低要求={partner_balance}")
                return False
            self.logger.info(f"步骤4成功: 余额检查通过")
            
            # 步骤5: 确定用户类型
            user_type = 0 if table == 'partner' else 1
            self.logger.info(f"步骤5: 用户类型确定为 {user_type} ({'码商' if user_type == 0 else '商户'})")
            
            # 步骤6: 获取商户订单号
            self.logger.info(f"步骤6: 处理商户订单号，当前merchant_code={merchant_code}")
            if merchant_code is None:
                self.logger.info(f"执行SQL: {sql_select_orders}")
                if cur.execute(sql_select_orders):
                    orders_result = (cur.fetchall())[0]
                    merchant_code = orders_result['merchant_code']
                    self.logger.info(f"步骤6成功: 查询商户订单号{self._format_sql(cur, sql_select_orders, None)}")
                    self.logger.info(f"获取到merchant_code={merchant_code}")
                else:
                    self.logger.info(f"步骤6: 未找到merchant_code，保持为None")
            else:
                self.logger.info(f"步骤6: merchant_code已存在，无需查询")
            
            # 步骤7: 插入流水记录
            params_7 = (code, user_type, user_id, balance_before, amount, balance_after, record_type, remark, merchant_code)
            self.logger.info(f"步骤7: 准备插入流水记录")
            self.logger.info(f"执行SQL: {sql_insert}")
            self.logger.info(f"参数: {params_7}")
            if not cur.execute(sql_insert, params_7):
                self.logger.error(f"步骤7失败: 插入流水记录执行失败")
                self.logger.error(f"失败SQL: {self._format_sql(cur, sql_insert, params_7)}")
                return False
            
            self.logger.info(f"步骤7成功: 新增流水{self._format_sql(cur, sql_insert, params_7)}")
            
            # 步骤8: VIP 等级更新（仅对码商且金额为正数）
            if table == 'partner' and amount > Decimal(0):
                self.logger.info(f"步骤8: 开始处理VIP等级更新")
                _vip = 0
                self.logger.info(f"执行SQL: {sql_select_vip}")
                if not cur.execute(sql_select_vip):
                    self.logger.error(f"步骤8失败: 查询VIP等级失败")
                    self.logger.error(f"失败SQL: {self._format_sql(cur, sql_select_vip, None)}")
                    return False
                vips = cur.fetchall()
                self.logger.info(f"查询到{len(vips)}个VIP等级配置")
                
                for i in vips:
                    if balance_after >= i['conditions']:
                        _vip = i['vip']
                
                self.logger.info(f"VIP等级计算: 当前余额={balance_after}, 应达到VIP={_vip}, 原VIP={user_before['vip']}")
                
                if int(_vip) > user_before['vip']:
                    self.logger.info(f"需要升级VIP: {user_before['vip']} -> {_vip}")
                    self.logger.info(f"执行SQL: {sql_update_vip} 参数: ({_vip}, {user_id})")
                    params_vip = (_vip, user_id)
                    if not cur.execute(sql_update_vip, params_vip):
                        self.logger.error(f"步骤8失败: {user_id}改变VIP失败")
                        self.logger.error(f"失败SQL: {self._format_sql(cur, sql_update_vip, params_vip)}")
                        return False
                    self.logger.info(f"步骤8成功: VIP等级已更新为{_vip}")
                else:
                    self.logger.info(f"步骤8: VIP等级无需更新")
            else:
                self.logger.info(f"步骤8: 跳过VIP更新（table={table}, amount={amount}）")
            
            self.logger.info(f"🎉 全部步骤完成: 用户{user_id}余额从{balance_before}变更为{balance_after}（变更{amount}）")
            return True
            
        except Exception as e:
            import traceback
            self.logger.error(f"🚨 异常发生: {type(e).__name__}: {e}")
            self.logger.error(f"参数: table={table}, user_id={user_id}, amount={amount}, code={code}, record_type={record_type}, remark={remark}, merchant_code={merchant_code}")
            self.logger.error(f"异常堆栈:\n{traceback.format_exc()}")
            try:
                self.logger.error(f"尝试获取最后执行的SQL...")
            except:
                self.logger.error(f"无法获取最后执行的SQL")
            return False
    
    def handle_payout_success(self, connection, cur, order_data, result):
        """处理代付成功逻辑（复制success_df的核心功能）"""
        try:
            amount = Decimal(order_data['amount'])
            order_code = order_data['code']
            
            # 注意：主流程已经获取了订单锁，这里不需要重复获取
            
            # 1. 订单类型判断（复制success_df逻辑）
            # 1=常规订单，2=拆单主单，3=拆单子单
            order_type = -1
            if not order_data.get('is_split') and not order_data.get('parent_id'):
                order_type = 1  # 常规订单
            if order_data.get('is_split') and not order_data.get('parent_id'):
                order_type = 2  # 拆单主单
            if order_data.get('parent_id'):
                order_type = 3  # 拆单子单
            
            self.logger.info(f"[{order_code}] 订单类型: {order_type} (1=常规, 2=拆单主单, 3=拆单子单)")
            
            # 2. 扣商户余额（过期订单，复制success_df逻辑）
            # #328 & 382, 主单不会走这个逻辑，子单不会直接影响商户金额
            if order_type in [1]:
                if order_data.get('status') in [-1, -2]:
                    self.logger.info(f"[{order_code}] 准备扣除商户 {order_data['merchant_id']} 过期订单金额 {order_data['realpay']}。")
                    if not self.change_balance(connection, cur, 'merchant', order_data['merchant_id'], -order_data['realpay'], order_code, 0):
                        return False
            
            # 3. 商户代理费用计算（复制success_df逻辑）
            # #328 & 382, 主单不会走这个逻辑，子单不会直接影响商户金额
            earn_merchant = Decimal(0)
            if order_type in [1] and order_data.get('earn_merchant', 0) > Decimal(0):
                sql_select_rates = """select id,rate_df from (select @orgId id, (select rate_df from merchant where id=@orgId) rate_df,
                                    (select @orgId:=pid from merchant where id=@orgId) pid from 
                                    (select @orgId:=%s) vars,merchant) t where id is not null order by pid desc"""
                if not cur.execute(sql_select_rates, (order_data['merchant_id'],)):
                    self.logger.error(f"未找到商户{order_data['merchant_id']}的代理费率信息")
                    return False
                merchant_prates = cur.fetchall()
                
                for k, v in enumerate(merchant_prates):
                        if not k == 0 and v['rate_df']:
                            _amount = amount * (merchant_prates[k - 1]['rate_df'] - v['rate_df'])
                            if _amount == 0:
                                self.logger.info(
                                    '代付订单{code}没有代付费用差,上级商户{id}费率{rate_df} ,本级商户{id2}费率{rate_df2}'.format(
                                        code=order_code, 
                                        id=merchant_prates[k - 1]['id'],
                                        rate_df=merchant_prates[k - 1]['rate_df'], 
                                        id2=v['id'],
                                        rate_df2=v['rate_df']
                                    ))
                                continue
                            if _amount < 0:
                                self.logger.error(f"商户代理费率错误: _amount={_amount}, 上级费率={merchant_prates[k - 1]['rate_df']}, 当前费率={v['rate_df']}")
                                return False
                            self.logger.info(f"[{order_code}] 准备为商户代理 {v['id']} 增加佣金 {_amount}。")
                            if not self.change_balance(connection, cur, 'merchant', v['id'], _amount, order_code, 3):
                                return False
                            earn_merchant += _amount
            
            # 4. 码商余额（复制success_df逻辑）
            # #328 & 382，主单不会走这个逻辑
            if order_type in [1, 3]:
                partner_id = order_data['partner_id']
                
                # 码商代付金额
                self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加代付金额 {amount}。")
                if not self.change_balance(connection, cur, 'partner', partner_id, amount, order_code, 1):
                    return False
            
            # 5. 码商佣金（复制success_df逻辑）
            # #328 & 382, 主单 & 子单 不会走这个逻辑
            if order_type in [1]:
                partner_id = order_data['partner_id']
                earn_partner_self = order_data.get('earn_partner_self', 0)
                if earn_partner_self > 0:
                    self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加佣金 {earn_partner_self}。")
                    if not self.change_balance(connection, cur, 'partner', partner_id, earn_partner_self, order_code, 3):
                        return False
            
            # 6. 代付优惠计算（复制success_df逻辑）
            # #328 & 382, 主单 & 子单 不会走这个逻辑  
            disprice = Decimal(0)
            if order_type in [1]:
                cache_result = self.get_cache_result('sys_info', ['range_df'])
                range_df = cache_result.get('range_df') if cache_result else None
                
                if range_df:
                    import json
                    range_df = json.loads(range_df)
                    for i in range(1, 7):
                        if range_df.get('isOpen' + str(i)) == 1:
                            rangemin = Decimal(range_df.get('rangemin' + str(i), 0))
                            rangemax = Decimal(range_df.get('rangemax' + str(i), 0))
                            if rangemin <= amount <= rangemax:
                                disprice = Decimal(range_df.get('disprice' + str(i), 0))
                                self.logger.info(f'代付优惠 disprice:{disprice} rangemin:{rangemin} rangemax:{rangemax} amount:{amount} merchant_id:{order_data["merchant_id"]}')
                                break
                
                # 代付优惠入库
                if disprice > 0:
                    partner_id = order_data['partner_id']
                    self.logger.info(f"[{order_code}] 准备为码商 {partner_id} 增加代付优惠 {disprice}。")
                    if not self.change_balance(connection, cur, 'partner', partner_id, disprice, order_code, 10):
                        return False
            
            # 7. 更新系统余额
            sql_update_payment = "UPDATE payment SET sys_balance=sys_balance+%s WHERE id=%s"
            cur.execute(sql_update_payment, (-amount, self.qr_id))
            self.logger.info(f"更新支付账户{self.qr_id}系统余额: {self._format_sql(cur, sql_update_payment, (-amount, self.qr_id))}")
            
            # 8. 更新订单信息（状态status=3已在转账成功时更新）
            # 获取付款手机号用于更新utr字段（如果之前未更新）
            payer_phone = result.get('payer_phone', '')
            if not payer_phone:
                self.logger.warning(f"订单{order_code}未获取到付款手机号，utr字段保持原值")
            else:
                self.logger.info(f"订单{order_code}付款手机号: {payer_phone}")
            
            # 🔥 优化：只更新earn_merchant字段，status=3已在转账成功时更新
            sql_update = "UPDATE orders_df SET earn_merchant=%s WHERE code=%s"
            cur.execute(sql_update, (earn_merchant, order_code))
            self.logger.info(f'更新订单商户佣金{self._format_sql(cur, sql_update, (earn_merchant, order_code))}')
            
            # 9. 重新接单（复制success_df逻辑）
            if self.qr_id and self.return_df_account_to_active_queue(self.qr_id):
                self.logger.info(f"代付账户{self.qr_id}重新进入活跃轮询队列")
            
            # 10. Redis通知
            self.redis.publish('order_df_notify', order_code)
            
            self.logger.info(f'订单{order_code}代付成功处理完成')
            
            # 11.新增：标记冷却期成功
            self.mark_order_cooldown_success(order_code)
            
            return True
            
        except Exception as e:
            self.logger.error(f'订单{order_code}success处理异常: {e}')
            self.logger.error(traceback.format_exc())
            return False
    
    def reject_order_with_refund(self, order_data: Dict, connection, reason: str, 
                                 selected_account: Dict) -> Dict:
        """
        驳回订单并退回商户余额
        
        ⚠️ 重要说明：
        1. 此函数不会提交或回滚事务，由调用方统一管理事务
        2. 此函数不会放回账号到活跃列表，由调用方在commit成功后执行
        
        前置条件（由调用方保证）：
        - status 一定是 1（刚从0更新为1）
        - order_type 一定是 1（常规订单）
        - selected_account 一定存在
        - 调用方已在同一事务中更新了 payment_id
        
        返回：
        - {'success': False, 'reject': True, 'message': ...} 驳回操作完成（待提交）
        - {'success': False, 'reject': False, 'message': ...} 驳回操作失败
        """
        order_code = order_data['code']
        # 截断 remark 避免超过数据库字段长度（按字节计算，balance_record.remark 为 varchar(64)）
        # 直接使用 reason（通常是 API 返回的 msg），保留更多有用信息
        max_remark_bytes = 64
        
        # 按字节截断 reason
        reason_bytes = reason.encode('utf-8')
        if len(reason_bytes) > max_remark_bytes:
            # 截断并确保不会在多字节字符中间切断
            sys_remark = reason_bytes[:max_remark_bytes].decode('utf-8', errors='ignore')
            # 清理末尾不完整的括号或标点
            sys_remark = sys_remark.rstrip('(:：')
        else:
            sys_remark = reason
        
        self.logger.warning(f'⚠️ 开始驳回订单: {order_code}, 原因: {reason}')
        
        try:
            cur = connection.cursor()
            
            # 1. 查询流水记录（只查商户流水，status=1时还没有码商流水）
            sql_select_record = """
                SELECT amount, user_type, user_id 
                FROM balance_record 
                WHERE code=%s AND user_type=1
            """
            cur.execute(sql_select_record, (order_code,))
            mer_records = cur.fetchall()
            
            self.logger.info(f'订单{order_code}商户流水记录: {len(mer_records)}条')
            
            # 2. 退回商户余额（status=1，码商还没实际付款，只退商户）
            for record in mer_records:
                if not self.change_balance(
                    connection, cur, 'merchant', record['user_id'], 
                    -record['amount'],  # 反向操作
                    order_code, 
                    record_type=9,  # 9=代付驳回
                    remark=sys_remark
                ):
                    self.logger.error(f'订单{order_code}退回商户{record["user_id"]}余额失败')
                    # 不回滚，由调用方决定
                    return {'success': False, 'reject': False, 'message': 'Refund failed'}
                self.logger.info(f'订单{order_code}已退回商户{record["user_id"]}金额: {record["amount"]}')
            
            # 3. 更新订单状态为-2（驳回）
            sql_update_cancel = """
                UPDATE orders_df 
                SET status = -2, sys_remark = %s
                WHERE code = %s AND status = 1
                LIMIT 1
            """
            cur.execute(sql_update_cancel, (sys_remark, order_code))
            affected_rows = cur.rowcount
            
            if affected_rows == 0:
                self.logger.warning(f'订单{order_code}状态不是1，驳回更新失败')
                # 不回滚，由调用方决定
                return {'success': False, 'reject': False, 'message': 'Status update failed'}
            
            self.logger.info(f'✅ 订单{order_code}驳回操作已完成（待提交），status: 1→-2')
            
            return {
                'success': False,
                'reject': True,  # 标记为驳回
                'message': f'Order rejected: {reason}'
            }
            
        except Exception as e:
            self.logger.exception(f'驳回订单{order_code}异常: {e}')
            # 不回滚，由调用方决定
            return {'success': False, 'reject': False, 'message': f'Exception: {str(e)}'}
    
    def _verify_operation_logs_table(self):
        """验证操作日志表是否存在"""
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8mb4'
            )
            
            with connection.cursor() as cur:
                cur.execute("SHOW TABLES LIKE 'easypaisa_operation_logs'")
                result = cur.fetchone()
                
                if not result:
                    self.logger.warning("⚠️ easypaisa_operation_logs表不存在，操作日志功能将被禁用")
                    self.operation_logs_enabled = False
                else:
                    self.logger.info("✅ easypaisa_operation_logs表验证成功")
                    self.operation_logs_enabled = True
                    
        except Exception as e:
            self.logger.error(f"验证操作日志表失败: {e}")
            self.operation_logs_enabled = False
        finally:
            if 'connection' in locals():
                connection.close()
    
    def log_operation(self, operation_type: str, **kwargs):
        """记录EasyPaisa操作日志到数据库
        
        Args:
            operation_type: 操作类型
            **kwargs: 其他参数，包括：
                - order_code: 订单号
                - from_payment_id: 转出方payment_id  
                - from_account_number: 转出方EasyPaisa手机号
                - to_account_number: 转入账号
                - to_account_name: 收款人姓名
                - to_bank_code: 银行代码
                - to_bank_name: 银行名称
                - transfer_type: 转账类型
                - amount: 金额
                - transaction_id: 交易ID
                - status: 状态
                - api_request: API请求数据
                - api_response: API响应数据
                - api_endpoint: API端点
                - request_uuid: 请求UUID
                - error_code: 错误代码
                - error_message: 错误信息
                - process_time: 处理耗时
                - trace_id: 链路追踪ID
        """
        if not self.operation_logs_enabled:
            # 表不存在时，只记录到文件日志
            self.logger.debug(f"操作日志(仅文件): {operation_type} - {kwargs.get('order_code', '')} - {kwargs.get('status', '')}")
            return
        
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8mb4',
                autocommit=True  # 日志记录使用自动提交
            )
            
            with connection.cursor() as cur:
                sql = """
                    INSERT INTO easypaisa_operation_logs (
                        from_payment_id, from_account_number,
                        to_account_number, to_account_name, to_bank_code, to_bank_name,
                        order_code, operation_type, transfer_type, amount, currency,
                        transaction_id, reference_number, status,
                        before_balance, after_balance,
                        api_request, api_response, api_endpoint, request_uuid,
                        error_code, error_message, process_time, retry_count,
                        ip_address, user_agent, server_process_id, trace_id, process_log
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """
                
                # 从API响应中提取requestId作为transaction_id（安全处理）
                transaction_id = kwargs.get('transaction_id')  # 先取原有的transaction_id
                
                # 安全地尝试从API响应中提取requestId
                try:
                    api_response = kwargs.get('api_response')
                    if api_response and isinstance(api_response, dict):
                        data = api_response.get('data')
                        if data and isinstance(data, dict):
                            request_id = data.get('requestId')
                            if request_id and isinstance(request_id, str) and request_id.strip():
                                transaction_id = request_id.strip()  # 使用API响应中的requestId
                except Exception as e:
                    # 如果提取requestId出错，继续使用原有的transaction_id，不影响主流程
                    self.logger.debug(f"提取requestId时出错，使用原有transaction_id: {e}")
                
                # 序列化JSON数据
                api_request_json = None
                api_response_json = None
                
                if kwargs.get('api_request'):
                    try:
                        api_request_json = json.dumps(kwargs['api_request'], ensure_ascii=False)
                    except Exception:
                        api_request_json = str(kwargs['api_request'])
                
                if kwargs.get('api_response'):
                    try:
                        api_response_json = json.dumps(kwargs['api_response'], ensure_ascii=False)
                    except Exception:
                        api_response_json = str(kwargs['api_response'])
                
                # 获取trace_id
                trace_id = kwargs.get('trace_id') or getattr(trace_id_filter, 'trace_id', 'default')
                
                cur.execute(sql, (
                    kwargs.get('from_payment_id'),                      # from_payment_id
                    kwargs.get('from_account_number'),                  # from_account_number
                    kwargs.get('to_account_number'),                    # to_account_number
                    kwargs.get('to_account_name'),                      # to_account_name
                    kwargs.get('to_bank_code'),                         # to_bank_code
                    kwargs.get('to_bank_name'),                         # to_bank_name
                    kwargs.get('order_code'),                           # order_code
                    operation_type,                                      # operation_type
                    kwargs.get('transfer_type'),                        # transfer_type
                    float(kwargs['amount']) if kwargs.get('amount') else None,  # amount
                    kwargs.get('currency', 'PKR'),                      # currency
                    transaction_id,                                     # transaction_id (使用requestId)
                    kwargs.get('reference_number'),                     # reference_number
                    kwargs.get('status', 'pending'),                    # status
                    float(kwargs['before_balance']) if kwargs.get('before_balance') else None,  # before_balance
                    float(kwargs['after_balance']) if kwargs.get('after_balance') else None,    # after_balance
                    api_request_json,                                    # api_request
                    api_response_json,                                   # api_response
                    kwargs.get('api_endpoint'),                         # api_endpoint
                    kwargs.get('request_uuid'),                         # request_uuid
                    kwargs.get('error_code'),                           # error_code
                    kwargs.get('error_message'),                        # error_message
                    int(kwargs['process_time']) if kwargs.get('process_time') else None,  # process_time
                    kwargs.get('retry_count', 0),                       # retry_count
                    kwargs.get('ip_address', '127.0.0.1'),              # ip_address
                    kwargs.get('user_agent'),                           # user_agent
                    os.getpid(),                                         # server_process_id
                    trace_id,                                            # trace_id
                    kwargs.get('process_log')                           # process_log
                ))
                
                # 记录日志信息
                if transaction_id:
                    self.logger.debug(f"✅ 操作日志已记录: {operation_type} - {kwargs.get('order_code', '')} - {kwargs.get('status', '')} - transaction_id: {transaction_id}")
                else:
                    self.logger.debug(f"✅ 操作日志已记录: {operation_type} - {kwargs.get('order_code', '')} - {kwargs.get('status', '')}")
                
                return
                
        except Exception as e:
            # 日志记录失败不应该影响主业务，只记录到文件日志
            self.logger.warning(f"记录操作日志失败: {e}")
            return
        finally:
            if 'connection' in locals():
                connection.close()
    
    def log_complete_transaction(self, order_data: dict, account_info: dict, api_request: dict, 
                               api_response: dict, status: str, error_message: str = None, 
                               transaction_id: str = None, start_time: float = None, 
                               before_balance: float = None, after_balance: float = None,
                               process_details: dict = None):
        """记录完整的交易记录（一笔交易一条记录）
        
        Args:
            order_data: 订单数据
            account_info: 账号信息
            api_request: API请求数据
            api_response: API响应数据
            status: 交易状态 (success, failed, account_invalid, exception, etc.)
            error_message: 错误信息
            transaction_id: 交易ID
            start_time: 开始时间
            before_balance: 转账前余额
            after_balance: 转账后余额
        """
        process_time = int((time.time() - start_time) * 1000) if start_time else None
        
        # 提取转入方信息
        to_account = order_data.get('payment_account', '')
        to_name = order_data.get('payment_name', '')
        ifsc_code = order_data.get('ifsc', '')
        
        # 判断转账类型
        is_pakistan_mobile = self._is_pakistan_mobile_number(to_account)
        if is_pakistan_mobile and ifsc_code.lower() == 'easypaisa':
            transfer_type = "EasyPaisa同行转账"
            operation_type = "transfer_same_bank"
            to_bank_code = "EASYPAISA"
            to_bank_name = "EasyPaisa"
        else:
            transfer_type = "跨行转账到银行卡"
            operation_type = "transfer_cross_bank"
            to_bank_code = ifsc_code
            to_bank_name = self._get_bank_name_by_ifsc(ifsc_code) if ifsc_code else None
        
        # 提取错误代码
        error_code = None
        if api_response and api_response.get('code'):
            error_code = str(api_response.get('code', ''))
        
        # 构建完整的流程日志
        process_log_json = None
        if process_details:
            try:
                from datetime import datetime
                
                # 辅助函数：安全转换数值类型为JSON可序列化的格式
                def safe_numeric(value):
                    """安全转换数值类型，处理Decimal等不可JSON序列化的类型"""
                    if value is None:
                        return None
                    if isinstance(value, Decimal):
                        return float(value)
                    if isinstance(value, (int, float)):
                        return value
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return str(value)
                
                def _calculate_safe_balance_change(after_balance, before_balance):
                    """安全计算余额变化，避免类型错误"""
                    try:
                        if after_balance is None or before_balance is None:
                            return None
                        
                        # 确保两个值都转换为Decimal类型进行计算
                        after_decimal = Decimal(str(after_balance)) if not isinstance(after_balance, Decimal) else after_balance
                        before_decimal = Decimal(str(before_balance)) if not isinstance(before_balance, Decimal) else before_balance
                        
                        balance_change = after_decimal - before_decimal
                        return float(balance_change)
                    except (ValueError, TypeError, Decimal.InvalidOperation) as e:
                        self.logger.warning(f"计算余额变化失败: after_balance={after_balance} ({type(after_balance)}), before_balance={before_balance} ({type(before_balance)}), error={e}")
                        return None
                
                def safe_dict(data):
                    """递归安全转换字典中的所有Decimal类型"""
                    if data is None:
                        return None
                    if isinstance(data, dict):
                        return {k: safe_dict(v) for k, v in data.items()}
                    elif isinstance(data, (list, tuple)):
                        return [safe_dict(item) for item in data]
                    elif isinstance(data, Decimal):
                        return float(data)
                    else:
                        return data
                
                self.logger.debug("开始构建process_log...")
                process_log = {
                    'order_code': order_data.get('code'),
                    'process_start': process_details.get('process_start_time', datetime.now().isoformat()),
                    'total_duration_ms': process_details.get('total_duration_ms', 0),
                    
                    # 业务流程步骤
                    'order_received': {
                        'timestamp': process_details.get('order_received_time', datetime.now().isoformat()),
                        'status': 'success',
                        'details': {
                            'order_code': order_data.get('code'),
                            'amount': safe_numeric(order_data.get('amount')),
                            'to_account': order_data.get('payment_account'),
                            'to_name': order_data.get('payment_name'),
                            'to_bankcode': order_data.get('payment_bankcode')
                        }
                    },
                    
                    'risk_check': {
                        'timestamp': process_details.get('risk_check_time', datetime.now().isoformat()),
                        'status': process_details.get('risk_check_status', 'success'),
                        'details': safe_dict(process_details.get('risk_check_details', {}))
                    },
                    
                    'account_selection': {
                        'timestamp': process_details.get('account_selection_time', datetime.now().isoformat()),
                        'status': process_details.get('account_selection_status', 'success'),
                        'details': {
                            'selected_account': account_info.get('phone'),
                            'payment_id': account_info.get('payment_id'),
                            'selection_criteria': process_details.get('account_selection_criteria', 'auto')
                        }
                    },
                    
                    'before_balance_check': {
                        'timestamp': process_details.get('before_balance_time', datetime.now().isoformat()),
                        'status': process_details.get('before_balance_status', 'success'),
                        'details': {
                            'balance': safe_numeric(before_balance),
                            'api_response_time': process_details.get('before_balance_duration', 0)
                        },
                        'error': process_details.get('before_balance_error')
                    },
                    
                    'transfer_api_call': {
                        'timestamp': process_details.get('transfer_api_time', datetime.now().isoformat()),
                        'status': status,
                        'details': {
                            'api_endpoint': api_request.get('action') if api_request else '',
                            'request_uuid': api_request.get('id') if api_request else '',
                            'transfer_type': transfer_type,
                            'api_response_code': api_response.get('code') if api_response else None,
                            'api_duration_ms': process_details.get('api_duration_ms', 0)
                        },
                        'error': error_message if status != 'success' else None
                    },
                    
                    'after_balance_check': {
                        'timestamp': process_details.get('after_balance_time', datetime.now().isoformat()),
                        'status': process_details.get('after_balance_status', 'success'),
                        'details': {
                            'balance': safe_numeric(after_balance),
                            'balance_change': _calculate_safe_balance_change(after_balance, before_balance)
                        },
                        'error': process_details.get('after_balance_error')
                    },
                    
                    'lock_release': {
                        'timestamp': process_details.get('lock_release_time', datetime.now().isoformat()),
                        'status': process_details.get('lock_release_status', 'success'),
                        'details': safe_dict(process_details.get('lock_release_details', {}))
                    },
                    
                    'final_status': {
                        'timestamp': datetime.now().isoformat(),
                        'status': status,
                        'details': {
                            'transaction_id': transaction_id,
                            'final_result': status,
                            'error_message': error_message,
                            'transfer_type': transfer_type,
                            'before_balance': safe_numeric(before_balance),
                            'after_balance': safe_numeric(after_balance)
                        }
                    },
                    
                    # 统计信息
                    'summary': {
                        'total_steps': 8,
                        'success_steps': len([k for k, v in {
                            'order_received': 'success',
                            'risk_check': process_details.get('risk_check_status', 'success'),
                            'account_selection': process_details.get('account_selection_status', 'success'),
                            'before_balance_check': process_details.get('before_balance_status', 'success'),
                            'transfer_api_call': status,
                            'after_balance_check': process_details.get('after_balance_status', 'success'),
                            'lock_release': process_details.get('lock_release_status', 'success'),
                            'final_status': status
                        }.items() if v == 'success']),
                        'final_status': status
                    }
                }
                
                # 序列化前的详细检查和日志
                self.logger.debug("准备序列化process_log...")
                self.logger.debug(f"before_balance类型: {type(before_balance)}, 值: {before_balance}")
                self.logger.debug(f"after_balance类型: {type(after_balance)}, 值: {after_balance}")
                self.logger.debug(f"order_amount类型: {type(order_data.get('amount'))}, 值: {order_data.get('amount')}")
                
                # 检查process_log中的关键数值字段
                for section_name, section in process_log.items():
                    if isinstance(section, dict) and 'details' in section:
                        details = section['details']
                        for key, value in details.items():
                            if value is not None and isinstance(value, Decimal):
                                self.logger.warning(f"发现未转换的Decimal类型: {section_name}.details.{key} = {value} (类型: {type(value)})")
                
                process_log_json = json.dumps(process_log, ensure_ascii=False, separators=(',', ':'))
                self.logger.debug("process_log序列化成功")
                
            except Exception as e:
                # 详细的错误诊断
                self.logger.error(f"构建流程日志失败: {e}")
                self.logger.error(f"错误类型: {type(e).__name__}")
                
                # 逐个检查可能导致序列化失败的字段
                problematic_fields = []
                
                # 检查主要数值字段
                for field_name, field_value in [
                    ('before_balance', before_balance),
                    ('after_balance', after_balance), 
                    ('order_amount', order_data.get('amount')),
                    ('total_duration_ms', process_details.get('total_duration_ms') if process_details else None)
                ]:
                    if field_value is not None:
                        field_type = type(field_value).__name__
                        self.logger.error(f"字段检查 - {field_name}: {field_value} (类型: {field_type})")
                        if isinstance(field_value, Decimal):
                            problematic_fields.append(f"{field_name}=Decimal({field_value})")
                
                # 检查process_details中的字段
                if process_details:
                    for key, value in process_details.items():
                        if value is not None and isinstance(value, Decimal):
                            problematic_fields.append(f"process_details.{key}=Decimal({value})")
                            self.logger.error(f"process_details中的Decimal字段: {key} = {value}")
                
                error_details = f"构建流程日志失败: {str(e)}"
                if problematic_fields:
                    error_details += f" | 可能的问题字段: {', '.join(problematic_fields)}"
                
                process_log_json = json.dumps({'error': error_details}, ensure_ascii=False)
        
        # 记录完整的交易信息
        self.log_operation(
            operation_type=operation_type,
            order_code=order_data.get('code'),
            from_payment_id=account_info.get('payment_id'),
            from_account_number=account_info.get('phone'),
            to_account_number=to_account,
            to_account_name=to_name,
            to_bank_code=to_bank_code,
            to_bank_name=to_bank_name,
            transfer_type=transfer_type,
            amount=order_data.get('amount'),
            transaction_id=transaction_id,
            status=status,
            before_balance=before_balance,  # 转账前余额
            after_balance=after_balance,    # 转账后余额
            api_request=api_request,
            api_response=api_response,
            api_endpoint=api_request.get('action', '') if api_request else '',
            request_uuid=api_request.get('id', '') if api_request else '',
            error_code=error_code,
            error_message=error_message,
            process_time=process_time,
            retry_count=order_data.get('retry_count', 0),  # 添加重试次数
            process_log=process_log_json  # 添加流程日志
        )
    
    
    def _is_pakistan_mobile_number(self, phone_number: str) -> bool:
        """判断是否为巴基斯坦手机号"""
        if not phone_number:
            return False
        
        # 移除所有非数字字符
        clean_number = ''.join(filter(str.isdigit, phone_number))
        
        # 巴基斯坦手机号特征：
        # - 以92开头（国际格式）或者03开头（本地格式）
        # - 总长度通常是11位（本地）或13位（国际）
        return (
            (clean_number.startswith('92') and len(clean_number) == 13) or
            (clean_number.startswith('03') and len(clean_number) == 11)
        )
    
    def _get_bank_name_by_ifsc(self, ifsc_code: str) -> str:
        """根据IFSC代码获取银行名称"""
        if not ifsc_code:
            return None
        
        # 简单的银行代码映射，可以根据需要扩展
        bank_mapping = {
            'HBL': 'Habib Bank Limited',
            'NBP': 'National Bank of Pakistan', 
            'MCB': 'Muslim Commercial Bank',
            'UBL': 'United Bank Limited',
            'ABL': 'Allied Bank Limited',
            'EASYPAISA': 'EasyPaisa',
            'JAZZCASH': 'JazzCash'
        }
        
        # 提取前3-4位作为银行代码
        bank_code = ifsc_code[:4].upper()
        for code, name in bank_mapping.items():
            if bank_code.startswith(code):
                return name
        
        return f'Bank ({ifsc_code})'  # 未知银行，返回代码

    def init_function(self, exist_logger):
        """初始化函数"""
        try:

            self.logger = exist_logger
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
                self.logger.info("Redis服务未能ping通，重新连接")
                self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        except Exception as e:
            self.logger.info(f"Redis连接失败，重试: {e}")
            time.sleep(2)
            self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.check_redis_connection()



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

    # update_key() 方法已删除 - EasyPaisa业务不需要此功能

    @asynccontextmanager
    async def async_session_context(self, timeout=30):
        """异步会话上下文管理器
        
        Args:
            timeout: 超时时间（秒），默认30秒
        """
        session = None
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            session = aiohttp.ClientSession(
                timeout=timeout_obj,
                connector=aiohttp.TCPConnector(ssl=False, limit=100)
            )
            self.logger.info(f"创建临时异步会话（超时: {timeout}秒）")
            yield session
        finally:
            if session and not session.closed:
                await session.close()
                self.logger.info("关闭临时异步会话")

    async def make_request(self, login_data, method, url, headers=None, params=None, data=None, json_data=None, timeout=30):
        self.logger.info(
            '请求 {method} {url}, params:{params} data:{data} json_data:{json_data}'.format(
                method=method, url=url, params=params, data=data, json_data=json_data))

        try:
            response = None

            # 使用临时会话
            async with self.async_session_context(timeout=timeout) as session:
                # 准备请求参数
                kwargs = {
                    'headers': headers or {},
                    'params': params,
                    'allow_redirects': True,
                    'ssl': False
                }

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
            self.logger.error(f"网络请求超时： uid: {login_data['id']}, URL: {url}, 超时时间: {timeout}秒")
            return None
        except aiohttp.ClientError as e:
            self.logger.error(f"网络连接错误： uid: {login_data['id']}, URL: {url}, 错误类型: {type(e).__name__}, 详情: {e}")
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

            def _create_mock_request(self, aiohttp_resp):
                """创建模拟的request对象"""
                class MockRequest:
                    def __init__(self, resp):
                        self.url = str(resp.url)
                        self.method = resp.method
                        self.headers = dict(resp.request_info.headers) if hasattr(resp, 'request_info') else {}
                return MockRequest(aiohttp_resp)

            def json(self):
                """解析JSON响应"""
                try:
                    import json
                    return json.loads(self.text)
                except:
                    return None

            def __str__(self):
                return f"<AsyncResponse [{self.status_code}]>"

            def __repr__(self):
                return self.__str__()

        return AsyncResponseWrapper(aiohttp_response, response_text)

    async def retry_make_request_query(self, *args, **kwargs):
        """查询请求方法 - 失败时重试一次"""
        res = await self.make_request(*args, **kwargs)
        
        # 如果返回None或HTTP状态码不成功，重试一次
        if res is None or not (200 <= res.status_code < 300):
            status_info = f"状态码:{res.status_code}" if res else "返回None"
            self.logger.warning(f"第一次查询请求失败({status_info})，准备重试")
            self.logger.info(f"make_request() second try, args: {args}, kwargs: {kwargs}")
            
            # 重试一次
            res = await self.make_request(*args, **kwargs)
            
            # 记录重试结果
            if res is None:
                self.logger.warning(f"第二次查询请求仍失败（返回None），不再重试")
            elif not (200 <= res.status_code < 300):
                self.logger.warning(f"第二次查询请求仍失败（状态码:{res.status_code}），不再重试")
        
        return res

    async def retry_make_request(self, *args, **kwargs):
        """HTTP请求方法 - 不重试，直接返回结果"""
        res = await self.make_request(*args, **kwargs)
        
        # 如果返回None（网络异常：TimeoutError/ClientError/Exception），直接返回
        if res is None:
            self.logger.warning(f"网络请求失败（超时或连接错误），不重试")
            return None
        
        # 如果HTTP状态码不成功，也直接返回，不重试
        if not (200 <= res.status_code < 300):
            self.logger.warning(f"HTTP状态码异常: {res.status_code}，不重试，直接返回")
        
        return res

    # 添加多进程分片和并发处理方法
    def get_active_processes_count(self):
        """获取当前活跃进程数量"""
        try:
            # 注册当前进程 (auto_payout专用键，避免与monitor进程冲突)
            process_key = "active_processes_auto_payout"
            current_process_id = f"{process_key}:{os.getpid()}"
            self.redis.setex(current_process_id, 30, int(time.time()))

            # 获取所有auto_payout活跃进程（现在有独立键名，不会与monitor冲突）
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
        
        # 🔍 调试信息：显示活跃进程列表
        active_processes = self.redis.keys("active_processes_auto_payout:*")
        active_pids = []
        for key in active_processes:
            try:
                pid = int(key.decode().split(':')[-1])
                active_pids.append(pid)
            except:
                continue
        active_pids.sort()
        self.logger.info(f"🔍 调试 - 活跃进程PIDs: {active_pids}, 当前PID: {os.getpid()}")
        
        for member in members:
            member_id = member.decode()
            # 使用MD5哈希确保相同member总是分配给同一进程
            hash_value = int(hashlib.md5(member_id.encode()).hexdigest(), 16)
            assigned_index = hash_value % total_processes
            
            # 🔍 调试信息：显示每个订单的分配结果
            self.logger.info(f"🔍 调试 - 订单{member_id}: hash={hash_value}, assigned_index={assigned_index}, current_index={current_index}")

            if assigned_index == current_index:
                allocated_members.append(member)

        self.logger.info(f"进程 {os.getpid()} (索引:{current_index}/{total_processes}) "
                         f"从 {len(members)} 个成员中分配到 {len(allocated_members)} 个")

        return allocated_members





    async def process_members_concurrent(self, dispatched_pairs: List[tuple] = None,
                                          members: List[bytes] = None, concurrent_limit: int = 20):
        """
        并发处理订单。
        预分配模式：dispatched_pairs = [(account, [orders]), ...]
        旧模式兼容：members = [b"code_amount", ...], concurrent_limit
        Returns: (success_count, total_count)
        """
        # 预分配模式
        if dispatched_pairs:
            async def process_account_orders(account, orders):
                """一个账号串行处理其所有订单，每单完成后检查冷却期"""
                account_success = 0
                pid = account['payment_id']
                try:
                    for i, order in enumerate(orders):
                        # 非首单时检查账号是否已进入冷却期（通过闭包访问外层 self）
                        if i > 0 and not self.check_account_release_time(pid):
                            self.logger.info(
                                f"账号{pid}已进入冷却期，停止处理，"
                                f"剩余{len(orders) - i}个订单留给下轮"
                            )
                            break
                        order_msg = f"{order['code']}_{order['amount']}"
                        try:
                            result = await self.process_single_order_async(order_msg, pre_selected_account=account)
                            if result is True:
                                account_success += 1
                        except Exception as e:
                            self.logger.error(f"订单{order['code']}处理异常: {e}")
                finally:
                    self.return_account_to_active_list(account)
                return account_success

            tasks = [process_account_orders(account, orders) for account, orders in dispatched_pairs]
            total_count = sum(len(orders) for _, orders in dispatched_pairs)

            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start_time

            success_count = sum(r for r in results if isinstance(r, int))
            error_count = sum(1 for r in results if isinstance(r, Exception))

            self.logger.info(
                f"进程{os.getpid()} 并发处理完成: "
                f"总数 {total_count}, 成功 {success_count}, "
                f"失败 {total_count - success_count}, 异常 {error_count}, "
                f"账号数 {len(dispatched_pairs)}, 耗时 {elapsed:.2f}秒"
            )
            return (success_count, total_count)

        # 旧模式兼容
        if not members:
            return (0, 0)

        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(member):
            async with semaphore:
                order_message = member.decode()
                return await self.process_single_order_async(order_message)

        tasks = [process_with_semaphore(member) for member in members]
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))

        self.logger.info(
            f"进程{os.getpid()} 并发处理完成: "
            f"总数 {len(members)}, 成功 {success_count}, "
            f"失败 {len(results) - success_count}, 异常 {error_count}, "
            f"耗时 {elapsed:.2f}秒"
        )
        return (success_count, len(members))

    # on_off() 方法已删除 - EasyPaisa自动代付不需要账号上下线管理

    def main(self):
        """主处理循环——预分配调度模式"""
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"

            # 紧急停机检查
            emergency_stop = self.redis.get("easypaisa_emergency_stop")
            if emergency_stop is not None and emergency_stop != b"0" and emergency_stop != "0":
                self.logger.warning(f"检测到紧急停机状态（值：{emergency_stop}）")
                return (0, EMERGENCY_STOP)

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # 1. 获取待处理订单
                orders = loop.run_until_complete(self.get_pending_orders_by_time())
                if not orders:
                    self.logger.info("暂无待处理订单")
                    return (0, NO_ORDERS)

                self.logger.info(f"数据库轮询发现 {len(orders)} 个待处理订单")

                # 2. 按进程分片（保持多进程兼容）
                members = [f"{order['code']}_{order['amount']}".encode() for order in orders]
                allocated_members = self.get_process_allocated_members(members)

                if not allocated_members:
                    self.logger.info(f"进程{os.getpid()} 没有分配到订单")
                    return (0, NO_ORDERS)

                # 3. 还原为 order 字典
                allocated_codes = set()
                for m in allocated_members:
                    code = m.decode().split('_')[0]
                    allocated_codes.add(code)
                allocated_orders = [o for o in orders if o['code'] in allocated_codes]

                # 4. 预分配：获取可用账号
                available_accounts = loop.run_until_complete(
                    self.get_real_available_accounts(allocated_orders)
                )

                if not available_accounts:
                    self.logger.warning(f"预分配：无可用账号，{len(allocated_orders)}个订单等待下轮")
                    return (0, NO_AVAILABLE_ACCOUNTS)

                # 5. 分配订单到账号
                dispatched_pairs = self.dispatch_orders_to_accounts(allocated_orders, available_accounts)

                if not dispatched_pairs:
                    self.logger.warning("预分配：分配结果为空")
                    return (0, NO_AVAILABLE_ACCOUNTS)

                # 6. 并发处理
                success_count, total_count = loop.run_until_complete(
                    self.process_members_concurrent(dispatched_pairs=dispatched_pairs)
                )

                return (success_count, total_count)

            except Exception as e:
                self.logger.error(f"预分配处理失败: {e}")
                return (0, NO_AVAILABLE_ACCOUNTS)
            finally:
                if loop and not loop.is_closed():
                    loop.close()

        except Exception as e:
            tb_str = traceback.format_exc()
            logging.error(f'main过程错误: {e}\n{tb_str}')
            return (0, NO_AVAILABLE_ACCOUNTS)

    async def get_pending_orders_by_time(self) -> List[Dict]:
        """获取按时间排序的待处理订单 (保持现有业务逻辑)"""
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                database=conf['mysql_database'],
                charset='utf8mb4',
                autocommit=False
            )
            
            with connection.cursor() as cur:
                sql = """
                    SELECT code, amount, payment_id, payment_account, payment_name, remark, time_create, retry_count
                    FROM orders_df 
                    WHERE status = 0 
                      AND time_create >= DATE_SUB(NOW(), INTERVAL 3 DAY)
                    ORDER BY time_create ASC
                    LIMIT 100
                """
                
                cur.execute(sql)
                rows = cur.fetchall()
                
                orders = []
                for row in rows:
                    orders.append({
                        'code': row[0],
                        'amount': float(row[1]),
                        'payment_id': row[2],
                        'payment_account': row[3],
                        'payment_name': row[4],
                        'remark': row[5],
                        'time_create': row[6],
                        'retry_count': row[7]
                    })
                
                self.logger.info(f"从数据库获取到 {len(orders)} 个待处理订单")
                
                # 🔥 新增：批量过滤冷却期内的订单
                if orders:
                    filtered_orders = self.filter_cooldown_orders(orders)
                    cooldown_count = len(orders) - len(filtered_orders)
                    if cooldown_count > 0:
                        self.logger.info(f"过滤掉 {cooldown_count} 个冷却期内的订单，剩余 {len(filtered_orders)} 个可处理")
                    
                    # 余额预检已移到 main() 的 get_real_available_accounts 中
                    return filtered_orders
                else:
                    return orders
                
        except Exception as e:
            self.logger.error(f"获取待处理订单失败: {e}")
            return []
        finally:
            if 'connection' in locals():
                connection.close()



    def init_function_v2(self, exist_logger):
        """初始化函数"""
        try:

            
            # 重新设置logger
            self.logger = exist_logger
            
            # 检测是否联通，如果断联需重新连接
            self.check_redis_connection()
            
            self.logger.debug("init_function 初始化完成")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('init_function 脚本运行错误{}\n{}\n'.format(e, error_message))


    
    # ========== Redis防护机制 ==========

    def _runtime_service(self):
        runtime_service = getattr(self, "runtime_service", None)
        if runtime_service is None:
            runtime_service = SyncEasyPaisaRuntimeService(self.redis)
            self.runtime_service = runtime_service
        return runtime_service

    def is_df_order_online(self, payment_id) -> bool:
        snapshot = self._runtime_service().read_snapshot(payment_id)
        if not snapshot:
            return False
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        df_enabled = bool(snapshot.get("df_order_enabled")) if "df_order_enabled" in snapshot else bool(snapshot.get("dispatch_df"))
        return bool(snapshot.get("online") and collect_enabled and df_enabled)

    def return_df_account_to_active_queue(self, payment_id) -> bool:
        if not self.is_df_order_online(payment_id):
            return False
        self.redis.lrem(self.REDIS_KEYS['easypaisa_active_df'], 0, payment_id)
        self.redis.rpush(self.REDIS_KEYS['easypaisa_active_df'], payment_id)
        return True
    
    async def check_account_online_status(self, payment_id: str) -> bool:
        """
        防护机制1: 检查账号在线状态 - API优先，Redis同步
        现在使用 payment_id 作为参数，内部查询手机号调用 API
        """
        try:
            # 通过payment_id查询手机号
            payment_info = self.get_phone_by_payment_id(payment_id)
            if not payment_info or not payment_info.get('phone'):
                self.logger.warning(f"无法获取payment_id {payment_id} 的手机号信息，账号不可用")
                # 无法获取手机号时，直接返回False，不使用降级方案
                # redis_online = self.redis.sismember(self.REDIS_KEYS['easypaisa_online_df'], payment_id)
                # return bool(redis_online)
                return False
            
            phone = payment_info['phone']
            self.logger.debug(f"payment_id {payment_id} 对应手机号: {phone}")
            
            # 策略1: 先通过API实时验证账号状态（使用手机号）
            api_result = await self._check_account_online_via_api(phone)
            
            if api_result is not None:
                # API检查成功后仍以 runtime snapshot 的 DF 派单资格为准。
                runtime_df_online = self.is_df_order_online(payment_id)
                
                if api_result:
                    # API显示在线
                    if not runtime_df_online:
                        self.logger.warning(f"账号payment_id:{payment_id} phone:{phone} API显示在线但runtime DF不可派单，跳过处理")
                        return False  # 返回False表示账号不可用
                    else:
                        self.logger.debug(f"账号payment_id:{payment_id} phone:{phone} API确认在线，runtime DF可派单")
                else:
                    # API显示离线
                    if runtime_df_online:
                        self._runtime_service().pause_order_dispatch(
                            payment_id,
                            phone=phone,
                            source="auto_payout_api_offline",
                        )
                        self.logger.warning(f"账号payment_id:{payment_id} phone:{phone} API检查离线，已通过runtime暂停派单")
                    else:
                        self.logger.debug(f"账号payment_id:{payment_id} phone:{phone} API确认离线，runtime已不可派单")
                
                return api_result
            else:
                runtime_df_online = self.is_df_order_online(payment_id)
                self.logger.warning(f"账号payment_id:{payment_id} phone:{phone} API检查失败，降级使用runtime DF状态: {runtime_df_online}")
                return runtime_df_online
                
        except Exception as e:
            self.logger.error(f"检查账号payment_id:{payment_id}在线状态失败: {e}")
            # 异常时也降级使用Redis状态
            try:
                return self.is_df_order_online(payment_id)
            except:
                return False
    
    async def _check_account_online_via_api(self, account_id: str) -> Optional[bool]:
        """
        通过EasyPaisa API实时检查账号在线状态
        
        Returns:
            True: 在线
            False: 离线  
            None: API检查失败
        """
        try:
            # 构建isLogined请求
            import uuid
            request_uuid = str(uuid.uuid4())
            
            inner_payload = {
                "id": request_uuid,
                "action": "isLogined",
                "payload": {
                    "account_id": account_id
                }
            }
            
            self.logger.info(f"账号{account_id} 开始API在线状态检查，请求UUID: {request_uuid}")
            
            # 调用API查询方法
            response = await self._call_easypaisa_api_query(inner_payload, account_id)
            
            # 打印完整的API响应
            self.logger.info(f"账号{account_id} isLogined API响应: {response}")
            
            if response:
                code = response.get('code')
                data = response.get('data')
                msg = response.get('msg', '')
                
                # 打印具体的code和data值
                self.logger.info(f"账号{account_id} API响应解析: code={code}, data={data}, msg={msg}")
                
                if code == 200 and data is True:
                    self.logger.info(f"账号{account_id} API检查结果：在线")
                    return True
                elif code == 403 or data is False:
                    self.logger.info(f"账号{account_id} API检查结果：离线")
                    return False
                else:
                    self.logger.warning(f"账号{account_id} API返回未知状态: code={code}, data={data}, msg={msg}")
                    return None
            else:
                self.logger.warning(f"账号{account_id} API检查无响应")
                return None
                
        except Exception as e:
            self.logger.error(f"账号{account_id} API在线状态检查异常: {e}")
            return None
    
    def _is_pakistan_mobile_number(self, account_number: str) -> bool:
        """
        判断是否为巴基斯坦手机号（EasyPaisa账号格式）
        
        巴基斯坦手机号格式：
        - 以 03 开头
        - 总共11位数字
        - 格式：03XXXXXXXXX
        """
        if not account_number:
            return False
            
        # 移除所有非数字字符
        clean_number = ''.join(filter(str.isdigit, account_number))
        
        # 检查格式：11位数字，以03开头
        if len(clean_number) == 11 and clean_number.startswith('03'):
            self.logger.debug(f"账号{account_number} 识别为巴基斯坦手机号")
            return True
        
        self.logger.debug(f"账号{account_number} 识别为银行账号（长度:{len(clean_number)}, 开头:{clean_number[:2] if len(clean_number) >= 2 else clean_number}）")
        return False
    
    def get_phone_by_payment_id(self, payment_id, connection=None):
        """通过payment_id查询手机号和相关信息"""
        import time
        start_time = time.time()

        own_connection = False
        try:
            if connection is None:
                own_connection = True
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
                        SELECT phone, account, name, bank_type, bank_type_id, partner_id, status, certified,
                               account_accno
                        FROM payment
                        WHERE id = %s AND status = 1
                          AND certified = 1
                          AND (bank_type = 97 OR bank_type_id = 97)
                    """
                    cur.execute(sql, payment_id)
                    result = cur.fetchone()
                    query_time = time.time() - start_time

                    if result:
                        self.logger.info(f"[AutoPayout] payment_id={payment_id} 查询成功, 耗时: {query_time:.3f}s")
                        return result
                    else:
                        # 检查是否存在但状态不符合条件
                        check_sql = "SELECT status, certified, manual_status FROM payment WHERE id = %s"
                        cur.execute(check_sql, payment_id)
                        check_result = cur.fetchone()
                        if check_result:
                            self.logger.warning(f"[AutoPayout] payment_id={payment_id} 不可用: status={check_result['status']}, certified={check_result['certified']}, manual_status={check_result.get('manual_status')}, 耗时: {query_time:.3f}s")
                        else:
                            self.logger.warning(f"[AutoPayout] payment_id={payment_id} 不存在, 耗时: {query_time:.3f}s")
                        return None
            finally:
                if own_connection:
                    connection.close()

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"[AutoPayout] 查询payment_id={payment_id} 失败: {e}, 耗时: {total_time:.3f}s")
            return None
    
    def get_account_from_active_list(self) -> Optional[Dict]:
        """
        防护机制2: 从活跃列表轮询获取账号，返回包含payment_id和phone的字典
        参考order_push.py第58行：payment_id = rds.lpop(list_name)
        """
        try:
            payment_id_bytes = self.redis.lpop(self.REDIS_KEYS['easypaisa_active_df'])
            if payment_id_bytes:
                payment_id = payment_id_bytes.decode()
                
                # 🔥 查询数据库获取手机号
                payment_info = self.get_phone_by_payment_id(payment_id)
                if payment_info and payment_info.get('phone'):
                    account_info = {
                        'payment_id': payment_id,          # 数字ID：532128
                        'phone': payment_info['phone'],    # 手机号：03499681697
                        'account': payment_info.get('account', ''),
                        'name': payment_info.get('name', ''),
                        'bank_type': payment_info.get('bank_type', ''),
                        'partner_id': payment_info.get('partner_id'),
                        'account_accno': payment_info.get('account_accno'),  # 🔥 修改：账号号码（必送）
                    }
                    self.logger.debug(f"从活跃列表获取账号: payment_id={payment_id}, phone={payment_info['phone']}")
                    return account_info
                else:
                    self.logger.error(f"无法获取payment_id {payment_id} 的手机号信息")
                    return None
            return None
        except Exception as e:
            self.logger.error(f"从活跃列表获取账号失败: {e}")
            return None
    
    def return_account_to_active_list(self, account_info):
        """
        防护机制3: 将账号重新加入活跃列表
        参考order_push.py第88-90行的逻辑
        """
        try:
            # 支持传入字典或payment_id字符串
            if isinstance(account_info, dict):
                payment_id = account_info['payment_id']
                phone = account_info.get('phone', 'UNKNOWN')
            else:
                payment_id = str(account_info)
                phone = 'UNKNOWN'
            
            # 只有 runtime snapshot 仍允许 DF 派单时才重新加入活跃列表。
            if self.return_df_account_to_active_queue(payment_id):
                self.logger.debug(f"账号payment_id:{payment_id} phone:{phone} 重新加入活跃列表")
        except Exception as e:
            self.logger.error(f"账号重新加入活跃列表失败: {e}, account_info: {account_info}")
    
    # async def check_account_concurrent_orders(self, payment_id: str) -> bool:
    #     """
    #     防护机制4: 检查账号是否有并发处理中的订单
    #     参考order_push.py第80-82行
    #     注释原因：已有payment_id_lock机制防止并发，此检查重复
    #     """
    #     try:
    #         connection = pymysql.connect(
    #             host=conf['mysql_host'],
    #             user=conf['mysql_user'],
    #             password=conf['mysql_password'],
    #             db=conf['mysql_database'],
    #             charset='utf8mb4',
    #             cursorclass=pymysql.cursors.DictCursor
    #         )
    #         
    #         try:
    #             with connection.cursor() as cur:
    #                 # 检查是否有处理中的订单（状态1或2）且重试次数小于4
    #                 sql = """
    #                     SELECT code FROM orders_df 
    #                     WHERE payment_id = %s AND status IN (1, 2) AND retry_count < 4
    #                     LIMIT 1
    #                 """
    #                 count = cur.execute(sql, payment_id)
    #                 if count > 0:
    #                     existing_order = cur.fetchone()
    #                     self.logger.warning(f"账号payment_id:{payment_id} 已有处理中订单: {existing_order['code']}")
    #                     return False
    #                 return True
    #         finally:
    #             connection.close()
    #             
    #     except Exception as e:
    #         self.logger.error(f"检查账号payment_id:{payment_id} 并发订单失败: {e}")
    #         return True  # 检查失败时放行
    
    async def check_account_amount_limits(self, payment_id: str, amount: Decimal) -> Dict:
        """
        防护机制5: 检查账号的金额限制和接单限额
        改用payment表现有的限额字段，如果字段为0或空则不控制
        balance_limit：单笔最高金额限制
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
            
            try:
                with connection.cursor() as cur:
                    # ===== 旧代码：查询全局风控配置参数 (已注释) =====
                    # sql = """
                    #     SELECT min_amount, max_amount, daily_total_amount as daily_limit_amount, daily_order_count as daily_limit_count
                    #     FROM auto_payout_risk_config 
                    #     WHERE id = 1
                    # """
                    # cur.execute(sql)
                    # account_limits = cur.fetchone()
                    # 
                    # if not account_limits:
                    #     return {'passed': False, 'reason': 'risk_config_not_found'}
                    
                    # ===== 新代码：查询payment表现有的限额字段（包括接单限额） =====
                    sql = """
                        SELECT amount_top, balance_limit
                        FROM payment 
                        WHERE id = %s
                    """
                    cur.execute(sql, payment_id)
                    payment_info = cur.fetchone()
                    
                    if not payment_info:
                        return {'passed': False, 'reason': 'payment_not_found'}
                    
                    # ===== 旧代码：检查单笔金额限制 (已注释，payment表无对应字段) =====
                    # if amount < Decimal(str(account_limits.get('min_amount', 0))):
                    #     return {'passed': False, 'reason': 'amount_too_small'}
                    # 
                    # if amount > Decimal(str(account_limits.get('max_amount', 999999))):
                    #     return {'passed': False, 'reason': 'amount_too_large'}
                    
                    # ===== 单笔金额限制：payment表无对应字段，跳过检查 =====
                    
                    # 检查今日额度限制
                    today_sql = """
                        SELECT COUNT(*) as today_count, COALESCE(SUM(amount), 0) as today_amount
                        FROM orders_df 
                        WHERE payment_id = %s 
                          AND DATE(time_create) = CURDATE()
                          AND status IN (3, 4)
                    """
                    cur.execute(today_sql, payment_id)
                    today_stats = cur.fetchone()
                    
                    # ===== 旧代码：使用全局配置的限制 (已注释) =====
                    # daily_limit_count = account_limits.get('daily_limit_count', 999999)
                    # daily_limit_amount = account_limits.get('daily_limit_amount', 999999999)
                    # 
                    # if today_stats['today_count'] >= daily_limit_count:
                    #     return {'passed': False, 'reason': 'daily_count_exceeded'}
                    # 
                    # if Decimal(str(today_stats['today_amount'])) + amount > Decimal(str(daily_limit_amount)):
                    #     return {'passed': False, 'reason': 'daily_amount_exceeded'}
                    
                    # ===== 新代码：使用payment表现有字段 (0或空不控制) =====
                    # 每日金额限制：使用 amount_top 字段
                    amount_top = payment_info.get('amount_top') or 0
                    
                    # 每日金额限制：只有设置了大于0的值才检查
                    if amount_top and amount_top > 0:
                        if Decimal(str(today_stats['today_amount'])) + amount > Decimal(str(amount_top)):
                            return {'passed': False, 'reason': 'daily_amount_exceeded'}
                    
                    # 接单限额检查：单笔最高金额限制
                    balance_limit = payment_info.get('balance_limit') or 0
                    
                    # 如果 balance_limit 设置了大于0的值，检查订单金额是否超限
                    if balance_limit and balance_limit > 0:
                        if amount > Decimal(str(balance_limit)):
                            return {
                                'passed': False, 
                                'reason': 'balance_limit_exceeded',
                                'amount': amount,
                                'balance_limit': balance_limit,
                                'message': f'订单金额{amount}超过接单限额{balance_limit}'
                            }
                    
                    # 每日次数限制：payment表无对应字段，跳过检查
                    
                    return {'passed': True}
                    
            finally:
                connection.close()
                
        except Exception as e:
            self.logger.error(f"检查账号payment_id:{payment_id}金额限制失败: {e}")
            return {'passed': True}  # 检查失败时放行
    
    def check_account_release_time(self, account_id: str) -> bool:
        """
        防护机制6: 检查账号释放时间
        参考callback.py中的payment_release_time机制
        """
        try:
            release_key = f"easypaisa_release:{account_id}"
            release_time_str = self.redis.hget(self.REDIS_KEYS['easypaisa_release_time'], release_key)
            
            if release_time_str:
                release_time = datetime.fromisoformat(release_time_str.decode())
                if datetime.now() < release_time:
                    self.logger.debug(f"账号{account_id}仍在释放期内，释放时间: {release_time}")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"检查账号{account_id}释放时间失败: {e}")
            return True
    
    def set_account_release_time(self, account_id: str, release_seconds: int = None):
        """
        设置账号释放时间
        
        Args:
            account_id: 账号ID
            release_seconds: 释放时间（秒），如果为None则从配置读取
        """
        try:
            # 如果没有指定时间，从配置读取
            if release_seconds is None:
                try:
                    config_str = self.redis.get("easypaisa_paymentid_cooldown_seconds")
                    if config_str:
                        release_seconds = int(config_str.decode() if isinstance(config_str, bytes) else config_str)
                        self.logger.debug(f"账号释放时间使用配置: {release_seconds}秒")
                    else:
                        release_seconds = 300  # 默认5分钟
                        self.logger.debug(f"账号释放时间使用默认值: {release_seconds}秒")
                except Exception as e:
                    self.logger.error(f"读取冷却配置失败: {e}，使用默认值300秒")
                    release_seconds = 300
            
            release_key = f"easypaisa_release:{account_id}"
            release_time = datetime.now() + timedelta(seconds=release_seconds)
            self.redis.hset(
                self.REDIS_KEYS['easypaisa_release_time'], 
                release_key, 
                release_time.isoformat()
            )
            self.logger.debug(f"设置账号{account_id}释放时间: {release_time} ({release_seconds}秒)")
        except Exception as e:
            self.logger.error(f"设置账号{account_id}释放时间失败: {e}")
    
    # ========== 失败记录管理（统一Hash存储） ==========
    
    def record_payment_failure(self, payment_id: str, amount: Decimal, 
                              to_account: str, reason: str, order_code: str):
        """
        记录失败信息到统一Hash
        
        Args:
            payment_id: 支付账号ID
            amount: 订单金额
            to_account: 收款账号
            reason: 失败原因
            order_code: 订单号
        
        Redis结构:
            Hash: easypaisa_failures
            Field: {payment_id}:{timestamp}
            Value: JSON包含失败详情
        """
        try:
            import time
            
            timestamp = int(time.time())
            field = f"{payment_id}:{timestamp}"
            
            failure_info = {
                'payment_id': payment_id,
                'amount': float(amount),
                'to_account': to_account,
                'reason': reason,
                'order_code': order_code,
                'timestamp': timestamp
            }
            
            # 存储到统一Hash
            self.redis.hset(
                self.REDIS_KEYS['easypaisa_failures'],
                field,
                json.dumps(failure_info, ensure_ascii=False)
            )
            
            self.logger.info(
                f"记录失败: payment_id={payment_id}, "
                f"金额={amount}, 收款账号={to_account}, 原因={reason}"
            )
            
        except Exception as e:
            self.logger.error(f"记录失败信息失败: {e}")
    
    def check_duplicate_failure(self, payment_id: str, amount: Decimal, 
                                to_account: str, time_window: int = 1200) -> dict:
        """
        检查时间窗口内是否有相同金额和收款账号的失败
        
        Args:
            payment_id: 支付账号ID
            amount: 订单金额
            to_account: 收款账号
            time_window: 时间窗口（秒），默认1200=20分钟
        
        Returns:
            {
                'has_duplicate': bool,  # 是否有重复
                'duplicate_count': int,  # 重复次数
                'last_failure_time': int,  # 最后一次失败时间
                'failures': list  # 所有匹配的失败记录
            }
        """
        try:
            import time
            
            current_time = int(time.time())
            cutoff_time = current_time - time_window
            
            # 扫描该payment_id的所有失败记录
            pattern = f"{payment_id}:*"
            cursor = 0
            matching_failures = []
            expired_fields = []
            
            # 添加调试日志
            self.logger.error(f"开始检查重复失败: payment_id={payment_id}, amount={amount}, to_account={to_account}, time_window={time_window}秒")
            
            while True:
                cursor, fields = self.redis.hscan(
                    self.REDIS_KEYS['easypaisa_failures'],
                    cursor,
                    match=pattern,
                    count=100
                )
                
                # 添加调试日志
                if fields:
                    self.logger.error(f"扫描到{len(fields)}条记录，pattern={pattern}")
                
                for field, value in fields.items():
                    field_str = field.decode() if isinstance(field, bytes) else field
                    
                    # 解析时间戳
                    parts = field_str.split(':')
                    if len(parts) >= 2:
                        try:
                            field_timestamp = int(parts[1])
                            
                            # 检查是否过期
                            if field_timestamp < cutoff_time:
                                expired_fields.append(field)
                                continue
                            
                            # 解析失败信息
                            value_str = value.decode() if isinstance(value, bytes) else value
                            failure_info = json.loads(value_str)
                            
                            # 添加调试日志
                            self.logger.error(f"检查记录: field={field_str}, amount={failure_info['amount']}, to_account={failure_info['to_account']}")
                            
                            # 检查金额和收款账号是否匹配
                            amount_match = abs(failure_info['amount'] - float(amount)) < 0.01
                            account_match = failure_info['to_account'] == to_account
                            
                            # 添加调试日志
                            self.logger.error(f"匹配结果: amount_match={amount_match} ({failure_info['amount']} vs {amount}), account_match={account_match} ({failure_info['to_account']} vs {to_account})")
                            
                            if amount_match and account_match:
                                matching_failures.append(failure_info)
                                self.logger.error(f"找到匹配的失败记录！")
                                
                        except (ValueError, json.JSONDecodeError) as e:
                            self.logger.error(f"解析失败记录错误: {field_str}, {e}")
                
                if cursor == 0:
                    break
            
            # 清理过期记录
            if expired_fields:
                self.redis.hdel(self.REDIS_KEYS['easypaisa_failures'], *expired_fields)
                self.logger.debug(f"清理{len(expired_fields)}条过期失败记录")
            
            return {
                'has_duplicate': len(matching_failures) > 0,
                'duplicate_count': len(matching_failures),
                'last_failure_time': max([f['timestamp'] for f in matching_failures]) if matching_failures else None,
                'failures': matching_failures
            }
            
        except Exception as e:
            self.logger.error(f"检查重复失败错误: {e}")
            return {
                'has_duplicate': False,
                'duplicate_count': 0,
                'last_failure_time': None,
                'failures': []
            }
    
    # ========== 账号使用记录相关方法（支持动态冷却期） ==========
    
    def record_account_usage(self, payment_id: str):
        """记录账号使用，支持动态冷却期配置"""
        try:
            import time
            usage_key = f"{self.REDIS_KEYS['easypaisa_account_used_prefix']}{payment_id}"
            current_time = int(time.time())
            
            # 从Redis读取动态配置的冷却时间，如果没有配置则使用默认5分钟
            try:
                cooldown_seconds_str = self.redis.get("easypaisa_paymentid_cooldown_seconds")
                if cooldown_seconds_str:
                    cooldown_seconds = int(cooldown_seconds_str.decode() if isinstance(cooldown_seconds_str, bytes) else cooldown_seconds_str)
                    self.logger.info(f"使用动态冷却期配置: {cooldown_seconds}秒")
                else:
                    cooldown_seconds = 300  # 默认5分钟
                    self.logger.info(f"使用默认冷却期: {cooldown_seconds}秒")
            except Exception as config_e:
                cooldown_seconds = 300  # 读取配置失败时使用默认值
                self.logger.warning(f"读取冷却期配置失败，使用默认值300秒: {config_e}")
            
            # 设置动态冷却期
            self.redis.setex(usage_key, cooldown_seconds, current_time)
            cooldown_minutes = cooldown_seconds / 60
            self.logger.info(f"记录账号{payment_id}使用时间: {current_time}, 冷却期: {cooldown_minutes:.1f}分钟")
            
        except Exception as e:
            self.logger.error(f"记录账号{payment_id}使用失败: {e}")

    def is_account_recently_used(self, payment_id: str) -> bool:
        """检查账号是否在冷却期内使用过（支持动态配置）"""
        try:
            usage_key = f"{self.REDIS_KEYS['easypaisa_account_used_prefix']}{payment_id}"
            return self.redis.exists(usage_key)
            
        except Exception as e:
            self.logger.error(f"检查账号{payment_id}使用记录失败: {e}")
            return False  # 检查失败时假设未使用过

    def get_account_last_usage_time(self, payment_id: str) -> Optional[int]:
        """获取账号最后使用时间（可选，用于调试）"""
        try:
            usage_key = f"{self.REDIS_KEYS['easypaisa_account_used_prefix']}{payment_id}"
            usage_time_str = self.redis.get(usage_key)
            
            if usage_time_str:
                return int(usage_time_str.decode())
            return None
            
        except Exception as e:
            self.logger.error(f"获取账号{payment_id}使用时间失败: {e}")
            return None
    
    # ========== 有序集合余额相关方法 ==========
    
    def get_top_balance_accounts(self, min_balance: Decimal = Decimal('1000'), count: int = 50, connection=None) -> List[Dict]:
        """从有序集合获取余额最高的账号列表，带幽灵缓存过滤"""
        try:
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']

            if not self.redis.exists(balance_sorted_set):
                self.logger.warning(f"有序集合 {balance_sorted_set} 不存在")
                return []

            # 多取一些补偿幽灵账号
            fetch_count = count * 2
            accounts_with_balance = self.redis.zrevrangebyscore(
                balance_sorted_set, "+inf", float(min_balance),
                start=0, num=fetch_count, withscores=True
            )

            if not accounts_with_balance:
                self.logger.info(f"有序集合中无余额>={min_balance}的账号")
                return []

            # 清理过期缓存
            now = time.time()
            expired = [k for k, v in self._invalid_payment_cache.items() if v < now]
            for k in expired:
                del self._invalid_payment_cache[k]

            # 过滤幽灵缓存
            filtered = []
            cached_skip = 0
            for payment_id_bytes, balance in accounts_with_balance:
                pid = payment_id_bytes.decode() if isinstance(payment_id_bytes, bytes) else str(payment_id_bytes)
                if pid in self._invalid_payment_cache:
                    cached_skip += 1
                    continue
                filtered.append((pid, balance))
                if len(filtered) >= count:
                    break

            if cached_skip > 0:
                self.logger.info(f"幽灵缓存过滤: 跳过{cached_skip}个已知无效账号")

            # 创建或复用 MySQL 连接验证账号
            own_conn = False
            if connection is None:
                own_conn = True
                connection = pymysql.connect(
                    host=conf['mysql_host'], user=conf['mysql_user'],
                    password=conf['mysql_password'], db=conf['mysql_database'],
                    charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor
                )

            try:
                result_accounts = []
                invalid_count = 0

                for pid, balance in filtered:
                    payment_info = self.get_phone_by_payment_id(pid, connection=connection)
                    if payment_info and payment_info.get('phone'):
                        result_accounts.append({
                            'payment_id': pid,
                            'phone': payment_info['phone'],
                            'partner_id': payment_info.get('partner_id'),
                            'account': payment_info.get('account'),
                            'name': payment_info.get('name'),
                            'account_accno': payment_info.get('account_accno'),
                            'balance': Decimal(str(balance)),
                            'priority': int(balance)
                        })
                    else:
                        # 加入幽灵缓存，5分钟后重试
                        self._invalid_payment_cache[pid] = time.time() + 300
                        invalid_count += 1

                self.logger.info(f"从有序集合获取 {len(result_accounts)} 个有效账号（检查{len(filtered)}个，无效{invalid_count}个，缓存跳过{cached_skip}个）")
                return result_accounts
            finally:
                if own_conn:
                    connection.close()

        except Exception as e:
            self.logger.error(f"从有序集合获取高余额账号失败: {e}")
            return []

    def get_account_balance_from_sorted_set(self, payment_id: str) -> Optional[Decimal]:
        """从有序集合获取账号余额"""
        try:
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']
            balance = self.redis.zscore(balance_sorted_set, payment_id)
            return Decimal(str(balance)) if balance is not None else None
        except Exception as e:
            self.logger.error(f"从有序集合获取账号{payment_id}余额失败: {e}")
            return None
    
    async def get_available_accounts(self, amount: Decimal, target_account: str = None) -> List[Dict]:
        """
        账号获取：双策略方案，加入20分钟使用间隔筛选
        
        策略1: 优先从有序集合获取高余额账号（按余额降序）
        策略2: 如果策略1未找到，fallback到活跃列表逐个检查
        
        Args:
            amount: 转账金额
            target_account: 目标收款账号，用于过滤相同账号
        """
        available_accounts = []
        back_key = []  # 需要重新加入活跃列表的账号
        
        # 统计各种检查结果
        check_stats = {
            'sorted_set_attempts': 0,
            'active_list_attempts': 0,
            'total_attempted': 0,
            'offline_count': 0,
            'release_time_count': 0,
            'duplicate_failure_count': 0,        # 检测到重复失败的账号数
            'payment_id_locked_count': 0,        # payment_id已被锁定的账号数
            'concurrent_orders_count': 0,
            'amount_limit_count': 0,
            'balance_limit_exceeded_count': 0,   # 接单限额超限的账号数
            'same_account_count': 0,             # 收付款账号相同的数量
            'insufficient_balance_count': 0,
            'no_balance_cache_count': 0,
            'recently_used_count': 0,
            'available_count': 0
        }
        
        try:
            self.logger.info(f"======== 开始EasyPaisa账号筛选（双策略+使用间隔） ========")
            self.logger.info(f"筛选条件: 金额要求 >= {amount}")
            
            # 🔥 策略1: 优先从有序集合获取高余额账号
            self.logger.info(f"策略1: 从有序集合获取高余额账号（余额>={amount}）")
            high_balance_accounts = self.get_top_balance_accounts(min_balance=amount, count=20)
            
            if high_balance_accounts:
                self.logger.info(f"从有序集合获取到 {len(high_balance_accounts)} 个高余额账号")
                
                # 对高余额账号进行防护检查（跳过余额检查）
                passed_accounts = []
                
                for account_info in high_balance_accounts:
                    payment_id = account_info['payment_id']
                    phone = account_info['phone']
                    balance = account_info['balance']
                    
                    check_stats['sorted_set_attempts'] += 1
                    check_stats['total_attempted'] += 1

                    self.logger.debug(f"检查高余额账号: payment_id:{payment_id} phone:{phone} 余额:{balance}")
                    
                    # 🔥 新增：检查收付款账号是否相同
                    if target_account and phone == target_account:
                        self.logger.warning(f"账号{payment_id} - 付款账号与收款账号相同 [{phone}]，跳过")
                        check_stats['same_account_count'] += 1
                        continue
                    
                    # 检查1: 在线状态
                    if not await self.check_account_online_status(payment_id):
                        check_stats['offline_count'] += 1
                        self.logger.debug(f"账号{payment_id} -不在线，跳过")
                        continue
                    
                    # 检查2: 释放时间
                    if not self.check_account_release_time(payment_id):
                        check_stats['release_time_count'] += 1
                        self.logger.debug(f"账号{payment_id} -在释放期内，跳过")
                        continue
                    
                    # 🔥 检查3: 重复订单检测（直接查询Hash表）
                    self.logger.debug(f"准备检查重复订单: payment_id={payment_id}, target_account={target_account}, amount={amount}")
                    if target_account:
                        # 有收款账号，执行精确的重复检测
                        duplicate_check = self.check_duplicate_failure(
                            payment_id=payment_id,
                            amount=amount,
                            to_account=target_account,
                            time_window=1200  # 20分钟
                        )
                        
                        if duplicate_check['has_duplicate']:
                            # ❌ 检测到重复，跳过此账号
                            check_stats['duplicate_failure_count'] += 1
                            self.logger.error(
                                f"⚠️ 账号{payment_id}重复订单检测: "
                                f"20分钟内已失败{duplicate_check['duplicate_count']}次 "
                                f"(金额:{amount}, 收款:{target_account})，跳过"
                            )
                            continue
                        else:
                            # ✅ 没有重复，继续使用
                            self.logger.error(
                                f"账号{payment_id}未检测到重复订单，继续使用"
                            )
                    else:
                        # 收款账号为空，无法做重复检测，记录日志后继续
                        self.logger.error(
                            f"账号{payment_id}收款账号为空，跳过重复检测"
                        )
                    
                    # 检查4: 并发订单 (已注释，由payment_id_lock机制处理)
                    # if not await self.check_account_concurrent_orders(payment_id):
                    #     check_stats['concurrent_orders_count'] += 1
                    #     self.logger.debug(f"账号{payment_id} -并发订单超限，跳过")
                    #     continue
                    
                    # 🔥 新增：payment_id 锁检查（防止选中已被其他进程占用的账号）
                    lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
                    if self.redis.exists(lock_key):
                        check_stats['payment_id_locked_count'] += 1
                        self.logger.debug(f"账号{payment_id} -payment_id已被锁定，跳过")
                        continue
                    
                    # 检查5: 金额限制和接单限额
                    amount_check = await self.check_account_amount_limits(payment_id, amount)
                    if not amount_check['passed']:
                        if amount_check['reason'] == 'balance_limit_exceeded':
                            check_stats['balance_limit_exceeded_count'] += 1
                            self.logger.debug(f"账号{payment_id} -接单限额检查: {amount_check['reason']}，跳过")
                        else:
                            check_stats['amount_limit_count'] += 1
                            self.logger.debug(f"账号{payment_id} -金额限制: {amount_check['reason']}，跳过")
                        continue
                    
                    # 🔥 余额检查已通过（从有序集合获取时已确保余额足够）
                    # 通过基础检查的账号
                    passed_accounts.append(account_info)
                    self.logger.info(f"✅ 账号{payment_id}通过基础检查")
                
                # 🔥 新增：20分钟使用间隔筛选
                if passed_accounts:
                    self.logger.info(f"开始20分钟使用间隔筛选，候选账号数: {len(passed_accounts)}")
                    
                    # 筛选出20分钟内未使用的账号
                    unused_accounts = []
                    recently_used_accounts = []
                    
                    for account_info in passed_accounts:
                        payment_id = account_info['payment_id']
                        
                        if self.is_account_recently_used(payment_id):
                            # 获取使用时间用于日志
                            last_usage = self.get_account_last_usage_time(payment_id)
                            if last_usage:
                                import time
                                minutes_ago = (time.time() - last_usage) / 60
                                self.logger.debug(f"账号{payment_id} -在20分钟内使用过({minutes_ago:.1f}分钟前)，暂时排除")
                            else:
                                self.logger.debug(f"账号{payment_id} -在20分钟内使用过，暂时排除")
                            recently_used_accounts.append(account_info)
                            check_stats['recently_used_count'] += 1
                        else:
                            self.logger.debug(f"账号{payment_id} -20分钟内未使用，可优先选择")
                            unused_accounts.append(account_info)
                    
                    # 🔥 关键逻辑：如果有未使用的账号，优先使用；否则使用最近使用的账号
                    if unused_accounts:
                        self.logger.info(f"✅ 选择20分钟内未使用的账号: {len(unused_accounts)}个可选")
                        available_accounts.append(unused_accounts[0])  # 选择第一个（余额最高的）
                        selected_account = unused_accounts[0]
                        check_stats['available_count'] += 1
                        self.logger.info(f"🎯 最终选择账号: payment_id={selected_account['payment_id']} phone={selected_account['phone']}, 余额={selected_account['balance']} (20分钟内未使用)")
                    else:
                        self.logger.warning(f"⚠️ 所有账号都在20分钟内使用过，选择最近使用的账号")
                        if recently_used_accounts:
                            available_accounts.append(recently_used_accounts[0])  # 选择第一个（余额最高的）
                            selected_account = recently_used_accounts[0]
                            check_stats['available_count'] += 1
                            self.logger.info(f"🎯 最终选择账号: payment_id={selected_account['payment_id']} phone={selected_account['phone']}, 余额={selected_account['balance']} (虽然20分钟内使用过，但无其他选择)")
            
            # 🔥 策略2: fallback到活跃列表（如果策略1未找到）
            if not available_accounts:
                self.logger.info(f"策略2: 有序集合未找到可用账号，fallback到活跃列表方式")
                
                # 保持原有逻辑，但优化余额检查
                for attempt in range(10):  # 减少尝试次数，因为前面已经尝试过高余额账号
                    account_info = self.get_account_from_active_list()
                    
                    if not account_info:
                        self.logger.info(f"活跃列表为空，停止查找")
                        break
                    
                    check_stats['active_list_attempts'] += 1
                    check_stats['total_attempted'] += 1
                    
                    payment_id = account_info['payment_id']
                    phone = account_info['phone']
                    
                    self.logger.info(f"第{attempt + 1}次尝试: 检查账号 payment_id:{payment_id} phone:{phone}")
                    
                    # 🔥 新增：检查收付款账号是否相同
                    if target_account and phone == target_account:
                        self.logger.warning(f"账号{payment_id} - 付款账号与收款账号相同 [{phone}]，跳过")
                        check_stats['same_account_count'] += 1
                        continue
                    
                    # 执行完整的防护检查
                    # 检查1: 在线状态
                    if not await self.check_account_online_status(payment_id):
                        check_stats['offline_count'] += 1
                        self.logger.debug(f"账号{payment_id} -不在线，跳过")
                        continue
                    
                    # 检查2: 释放时间
                    if not self.check_account_release_time(payment_id):
                        check_stats['release_time_count'] += 1
                        self.logger.debug(f"账号{payment_id} -在释放期内，重新入队")
                        back_key.append(account_info)
                        continue
                    
                    # 🔥 检查3: 重复订单检测（直接查询Hash表）
                    self.logger.debug(f"准备检查重复订单: payment_id={payment_id}, target_account={target_account}, amount={amount}")
                    if target_account:
                        # 有收款账号，执行精确的重复检测
                        duplicate_check = self.check_duplicate_failure(
                            payment_id=payment_id,
                            amount=amount,
                            to_account=target_account,
                            time_window=1200  # 20分钟
                        )
                        
                        if duplicate_check['has_duplicate']:
                            # ❌ 检测到重复，重新入队
                            check_stats['duplicate_failure_count'] += 1
                            self.logger.error(
                                f"⚠️ 账号{payment_id}重复订单检测: "
                                f"20分钟内已失败{duplicate_check['duplicate_count']}次 "
                                f"(金额:{amount}, 收款:{target_account})，重新入队"
                            )
                            back_key.append(account_info)
                            continue
                        else:
                            # ✅ 没有重复，继续使用
                            self.logger.error(
                                f"账号{payment_id}未检测到重复订单，继续使用"
                            )
                    else:
                        # 收款账号为空，无法做重复检测，记录日志后继续
                        self.logger.error(
                            f"账号{payment_id}收款账号为空，跳过重复检测"
                        )
                    
                    # 检查4: 并发订单 (已注释，由payment_id_lock机制处理)
                    # if not await self.check_account_concurrent_orders(payment_id):
                    #     check_stats['concurrent_orders_count'] += 1
                    #     self.logger.debug(f"账号{payment_id} -并发订单超限，重新入队")
                    #     back_key.append(account_info)
                    #     continue
                    
                    # 🔥 新增：payment_id 锁检查（防止选中已被其他进程占用的账号）
                    lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
                    if self.redis.exists(lock_key):
                        check_stats['payment_id_locked_count'] += 1
                        self.logger.debug(f"账号{payment_id} -payment_id已被锁定，重新入队")
                        back_key.append(account_info)
                        continue
                    
                    # 检查5: 金额限制
                    amount_check = await self.check_account_amount_limits(payment_id, amount)
                    if not amount_check['passed']:
                        check_stats['amount_limit_count'] += 1
                        self.logger.debug(f"账号{payment_id} -金额限制: {amount_check['reason']}，重新入队")
                        back_key.append(account_info)
                        continue
                    
                    # 🔥 余额检查：优先从有序集合获取
                    balance = self.get_account_balance_from_sorted_set(payment_id)
                    if balance is None:
                        # 有序集合没有，尝试原有缓存
                        balance_key = f"{self.REDIS_KEYS['easypaisa_balance_prefix']}{payment_id}"
                        cached_balance = self.redis.get(balance_key)
                        if cached_balance:
                            balance = Decimal(cached_balance.decode())
                        else:
                            # 重新获取余额
                            self.logger.debug(f"账号{payment_id} -余额缓存不存在，尝试重新获取")
                            balance_result = await self.fetch_balance_from_api(account_info)
                            
                            if balance_result and balance_result.get('success'):
                                balance = Decimal(str(balance_result['balance']))
                                # 同时更新传统缓存和有序集合
                                self.redis.setex(balance_key, 300, str(balance))
                                balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']
                                self.redis.zadd(balance_sorted_set, {payment_id: float(balance)})
                                # self.redis.expire(balance_sorted_set, 300)  # 已注释：不设置过期，数据永久保存
                                self.logger.info(f"✅ 账号{payment_id} - 重新获取余额成功: {balance}")
                            else:
                                check_stats['no_balance_cache_count'] += 1
                                error_msg = balance_result.get('error', '获取余额失败') if balance_result else '获取余额失败'
                                self.logger.warning(f"账号{payment_id} - 重新获取余额失败: {error_msg}，重新入队")
                                back_key.append(account_info)
                                continue
                    
                    if balance >= amount:
                        # 检查20分钟使用间隔
                        if self.is_account_recently_used(payment_id):
                            check_stats['recently_used_count'] += 1
                            self.logger.debug(f"账号{payment_id} -20分钟内使用过，重新入队")
                            back_key.append(account_info)
                            continue
                        
                        check_stats['available_count'] += 1
                        account_info.update({
                            'balance': balance,
                            'priority': int(balance)
                        })
                        available_accounts.append(account_info)
                        self.logger.info(f"✅ 找到可用账号: payment_id={payment_id} phone={phone}, 余额: {balance}")
                        break
                    else:
                        check_stats['insufficient_balance_count'] += 1
                        self.logger.debug(f"账号{payment_id} -余额不足（{balance} < {amount}），重新入队")
                        back_key.append(account_info)
            
            # 如果两个策略都未找到可用账号，记录详细原因
            if not available_accounts:
                self.logger.warning(f"❌ 两个策略都未找到可用账号")
                if not high_balance_accounts:
                    self.logger.error(f"🚨 有序集合中无余额>={amount}的账号，可能原因:")
                    self.logger.error(f"   1. Monitor系统未运行或数据同步延迟")
                    self.logger.error(f"   2. 所有账号余额都低于要求金额{amount}")
                    self.logger.error(f"   3. 有序集合key '{self.REDIS_KEYS['easypaisa_balance_sorted_set']}' 不存在或已过期")
                else:
                    self.logger.error(f"🚨 有序集合有{len(high_balance_accounts)}个高余额账号，但都不满足其他条件:")
                    self.logger.error(f"   - 离线账号: {check_stats['offline_count']}")
                    self.logger.error(f"   - 释放期账号: {check_stats['release_time_count']}")
                    self.logger.error(f"   - 重复失败账号: {check_stats['duplicate_failure_count']}")
                    self.logger.error(f"   - payment_id已锁定: {check_stats['payment_id_locked_count']}")
                    self.logger.error(f"   - 并发超限账号: {check_stats['concurrent_orders_count']}")
                    self.logger.error(f"   - 金额限制账号: {check_stats['amount_limit_count']}")
                    self.logger.error(f"   - 接单限额超限: {check_stats['balance_limit_exceeded_count']}")
                    self.logger.error(f"   - 收付款相同账号: {check_stats['same_account_count']}")
                    self.logger.error(f"   - 20分钟内使用过: {check_stats['recently_used_count']}")
                    self.logger.error(f"   - 余额不足账号: {check_stats['insufficient_balance_count']}")
                    self.logger.error(f"   - 无缓存账号: {check_stats['no_balance_cache_count']}")
                    
                self.logger.error(f"活跃列表尝试情况: {check_stats['active_list_attempts']}次尝试")
            
            # 将不符合条件的账号重新加入活跃列表
            if back_key:
                self.logger.info(f"重新入队账号处理: 共{len(back_key)}个账号")
                for account_info in back_key:
                    self.return_account_to_active_list(account_info)
                    payment_id = account_info['payment_id']
                    phone = account_info.get('phone', 'UNKNOWN')
                    self.logger.info(f"账号payment_id:{payment_id} phone:{phone} 已重新入队到活跃列表")
            
            # 输出详细统计
            self.logger.info(f"======== EasyPaisa账号筛选完成 ========")
            self.logger.info(f"筛选统计:")
            self.logger.info(f"  📊 有序集合尝试: {check_stats['sorted_set_attempts']}")
            self.logger.info(f"  📊 活跃列表尝试: {check_stats['active_list_attempts']}")
            self.logger.info(f"  📊 总尝试账号数: {check_stats['total_attempted']}")
            self.logger.info(f"  ❌ 离线账号数: {check_stats['offline_count']}")
            self.logger.info(f"  ⏰ 释放期账号数: {check_stats['release_time_count']}")
            self.logger.info(f"  ⚠️ 重复失败账号数: {check_stats['duplicate_failure_count']}")
            self.logger.info(f"  🔒 payment_id已锁定数: {check_stats['payment_id_locked_count']}")
            self.logger.info(f"  🔄 并发超限账号数: {check_stats['concurrent_orders_count']}")
            self.logger.info(f"  💰 金额限制账号数: {check_stats['amount_limit_count']}")
            self.logger.info(f"  🚫 接单限额超限数: {check_stats['balance_limit_exceeded_count']}")
            self.logger.info(f"  🔁 收付款相同账号数: {check_stats['same_account_count']}")
            self.logger.info(f"  💸 余额不足账号数: {check_stats['insufficient_balance_count']}")
            self.logger.info(f"  💾 无缓存账号数: {check_stats['no_balance_cache_count']}")
            self.logger.info(f"  🕐 20分钟内使用过: {check_stats['recently_used_count']}")
            self.logger.info(f"  ✅ 可用账号数: {check_stats['available_count']}")
            self.logger.info(f"  🔄 重新入队数: {len(back_key)}")
            
            if available_accounts:
                self.logger.info(f"🎯 筛选结果: 成功找到{len(available_accounts)}个可用账号")
            else:
                self.logger.info(f"⚠️ 筛选结果: 暂无可用账号")
            
            return available_accounts
            
        except Exception as e:
            self.logger.error(f"======== EasyPaisa账号筛选异常 ========")
            self.logger.error(f"异常详情: {e}")
            self.logger.error(f"异常时统计:")
            self.logger.error(f"  已检查账号数: {check_stats['total_attempted']}")
            self.logger.error(f"  有序集合尝试: {check_stats['sorted_set_attempts']}")
            self.logger.error(f"  活跃列表尝试: {check_stats['active_list_attempts']}")
            self.logger.error(f"  待重新入队数: {len(back_key)}")
            
            # 异常时也要将账号重新入队
            if back_key:
                self.logger.info(f"异常处理: 重新入队{len(back_key)}个账号")
                for account_info in back_key:
                    self.return_account_to_active_list(account_info)
                    payment_id = account_info['payment_id']
                    phone = account_info.get('phone', 'UNKNOWN')
                    self.logger.info(f"异常处理: 账号payment_id:{payment_id} phone:{phone}已重新入队")
            
            self.logger.error(f"🚨 筛选结果: 因异常返回空列表")
            return []
    

    # ========== 原有的锁机制保持不变 ==========
    
    def get_lock(self, order_code):
        """获取订单锁（保持原有逻辑）"""
        try:
            busy_key = f'{self.REDIS_KEYS["grab_df_prefix"]}{order_code}'
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value)
            if not _lock:
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{order_code}, {busy_key} 剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"{order_code}, 死锁并删除 {_value}")
                return False
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(f"{order_code},{busy_key} 加锁时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            self.logger.error(f'get_lock 脚本运行错误{order_code}\n{e}')
            return False

    def del_lock(self, order_code, value):
        """删除锁（保持原有逻辑）"""
        try:
            busy_key = f'{self.REDIS_KEYS["grab_df_prefix"]}{order_code}'
            self.logger.info(f"准备删除Lock {busy_key}, 期望value: {value}")
            _lock = self.redis.get(busy_key)
            if _lock:
                current_value = _lock.decode()
                if current_value == value:
                    result = self.redis.delete(busy_key)
                    self.logger.info(f"✅ 删除Lock成功 {busy_key}, result: {result}")
                else:
                    self.logger.warning(f"⚠️ Lock值不匹配！订单{order_code} 期望value: {value}, 实际value: {current_value}, 订单可能被其他进程处理")
            else:
                self.logger.warning(f"⚠️ Lock已不存在: {busy_key}, 订单{order_code}的锁可能提前过期或被清理")
            return True
        except Exception as e:
            self.logger.error(f'del_lock 脚本运行错误{order_code}\n{e}')
            return False
    
    def get_payment_id_lock(self, payment_id):
        """获取payment_id锁 - 确保每个payment_id只能处理一个订单"""
        try:
            # 🔥 防护：检查payment_id是否有效
            if payment_id is None or payment_id == '':
                self.logger.error(f"Payment ID 无效: {payment_id}，拒绝处理")
                return False
            
            # 🔥 注释：失败冷却期的精确检查已移到账号筛选阶段（get_available_accounts）
            # 在筛选阶段已经通过 check_duplicate_failure() 做了精确的重复订单检测
            # 如果账号能通过筛选到这里，说明：
            #   1. 不在冷却期，或者
            #   2. 虽在冷却期但不是重复订单（失败的是其他订单）
            # 因此这里不再重复检查，避免误判
            # 
            # failed_key = f'{self.REDIS_KEYS["payment_id_failed_prefix"]}{payment_id}'
            # if self.redis.exists(failed_key):
            #     self.logger.warning(f"Payment ID {payment_id} 在失败冷却期内，拒绝处理")
            #     return False
            
            # 获取payment_id处理锁
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(lock_key, _value)
            
            if not _lock:
                # 防止死锁 
                _ttl = self.redis.ttl(lock_key)
                self.logger.info(f"Payment ID {payment_id} 锁剩余时间 {_ttl}s")
                if _ttl and int(_ttl) > 300:  # 5分钟超时
                    self.redis.delete(lock_key)
                    self.logger.error(f"Payment ID {payment_id} 死锁并删除")
                return False
            
            # 设置5分钟超时
            self.redis.expire(lock_key, 300)
            self.logger.info(f"Payment ID {payment_id} 获取锁成功，value: {_value}")
            return _value
            
        except Exception as e:
            self.logger.error(f'获取payment_id锁失败: {e}')
            return False
    
    def del_payment_id_lock(self, payment_id, value):
        """删除payment_id锁"""
        try:
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{payment_id}'
            _lock = self.redis.get(lock_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(lock_key)
                self.logger.info(f"删除Payment ID锁 {lock_key}, result: {result}")
            return True
        except Exception as e:
            self.logger.error(f'删除payment_id锁失败: {e}')
            return False
    
    def update_account_balance_after_transfer(self, payment_id: str, transfer_amount: Decimal):
        """
        转账成功后更新Redis中的账号余额（仅扣减金额）
        
        Args:
            payment_id: 账号ID
            transfer_amount: 转账金额（正数）
        
        Returns:
            bool: 更新成功返回True，失败返回False
        """
        try:
            # 1. 更新有序集合中的余额（使用 ZINCRBY 原子操作扣减）
            balance_sorted_set = self.REDIS_KEYS['easypaisa_balance_sorted_set']
            new_balance = self.redis.zincrby(balance_sorted_set, -float(transfer_amount), payment_id)
            
            # 如果余额变为负数，设置为0（但不移除）
            if new_balance is not None and float(new_balance) < 0:
                self.redis.zadd(balance_sorted_set, {payment_id: 0})
                self.logger.info(f"账号{payment_id}余额扣减后为负({new_balance})，已设置为0")
                new_balance = 0
            
            # 2. 更新普通缓存的余额（不设置过期时间，由monitor负责）
            balance_key = f"{self.REDIS_KEYS['easypaisa_balance_prefix']}{payment_id}"
            cached_balance = self.redis.get(balance_key)
            
            if cached_balance:
                old_balance = Decimal(cached_balance.decode())
                new_balance_value = old_balance - transfer_amount
                # 如果扣减后为负数，设置为0
                if new_balance_value < 0:
                    new_balance_value = Decimal('0')
                # 直接SET，不设置过期时间
                self.redis.set(balance_key, str(new_balance_value))
                self.logger.info(f"账号{payment_id}余额已扣减: -{transfer_amount}, 新余额: {new_balance_value}")
            else:
                self.logger.info(f"账号{payment_id}普通缓存无余额记录，仅更新有序集合")
            
            return True
            
        except Exception as e:
            self.logger.error(f"更新账号{payment_id}余额失败: {e}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            return False
    
    async def fetch_balance_from_api(self, account_info):
        """
        从API重新获取账号余额（参考easypaisa_monitor.py的实现）
        当Redis缓存不存在时调用此方法
        """
        import base64
        import hashlib
        import uuid
        import json
        import time
        
        try:
            payment_id = account_info['payment_id']
            phone = account_info.get('phone')
            
            # 检查必要信息
            if not phone:
                return {
                    'success': False,
                    'error': f'账号{payment_id}缺少手机号信息'
                }
            
            # account_accno为余额查询必送参数
            account_accno = account_info.get('account_accno')
            if not account_accno:
                return {
                    'success': False,
                    'error': f'账号{payment_id}缺少account_accno字段，无法查询余额'
                }
            
            # 构造payload数据
            payload_data = {
                "account_id": phone,  # 手机号
                "accno": account_accno  # 必送的账号参数
            }
            self.logger.info(f"payment_id {payment_id} 余额查询，account_id={phone}, accno={account_accno}")
            
            # 构造内层payload（按照EasyPaisa文档格式）
            inner_payload = {
                "id": str(uuid.uuid4()),  # 生成UUID
                "action": "queryBalance",
                "payload": payload_data
            }
            
            # 构造FormBody格式（按照EasyPaisa文档）- 安全序列化
            try:
                data_b64 = base64.b64encode(json.dumps(inner_payload).encode()).decode()
            except TypeError as e:
                # 如果有Decimal类型导致序列化失败，使用安全转换
                self.logger.warning(f"余额查询JSON序列化失败，使用安全转换: {e}")
                
                def safe_convert(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: safe_convert(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple)):
                        return [safe_convert(item) for item in obj]
                    else:
                        return obj
                
                safe_payload = safe_convert(inner_payload)
                data_b64 = base64.b64encode(json.dumps(safe_payload).encode()).decode()
            
            # 计算MD5签名（使用全局配置）
            secret_key = EASYPAISA_SECRET_KEY
            user_id = EASYPAISA_USER_ID
            api_url = EASYPAISA_API_URL
            
            if not all([secret_key, user_id, api_url]):
                return {
                    'success': False,
                    'error': 'EasyPaisa API配置不完整'
                }
            
            sign_string = data_b64 + secret_key
            sign = hashlib.md5(sign_string.encode()).hexdigest()
            
            form_data = {
                'user_id': user_id,
                'data': data_b64,
                'sign': sign
            }
            
            self.logger.info(f"🔄 为账号{payment_id}({phone})重新获取余额")
            
            # 发起API请求
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            
            start_time = time.time()
            
            # 使用aiohttp发起异步请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers=headers,
                    data=form_data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_time = time.time() - start_time
                    
                    if not 200 <= response.status < 300:
                        return {
                            'success': False,
                            'error': f'HTTP错误: {response.status}',
                            'response_time': response_time
                        }
                    
                    # 解析响应
                    result = await response.json()
                    
                    if result.get('code') == 200:
                        # 根据EasyPaisa文档，余额在 data.body.totalbalance 字段
                        data = result.get('data', {})
                        body = data.get('body', {}) if isinstance(data, dict) else {}
                        balance = body.get('totalbalance', result.get('totalbalance', result.get('balance', 0)))
                        
                        self.logger.info(f"✅ 账号{payment_id}({phone})余额获取成功: {balance}")
                        
                        return {
                            'success': True,
                            'balance': balance,
                            'response_time': response_time,
                            'data': result
                        }
                    elif result.get('code') == 501:
                        # 501 AccountInvalid - 账号无效
                        error_msg = result.get('msg', result.get('message', '账号无效(501)'))
                        
                        return {
                            'success': False,
                            'error': error_msg,
                            'response_time': response_time,
                            'should_offline': True
                        }
                    else:
                        return {
                            'success': False,
                            'error': result.get('msg', result.get('message', 'API返回错误')),
                            'response_time': response_time
                        }
                        
        except Exception as e:
            self.logger.error(f"重新获取账号{payment_id}余额异常: {e}")
            
            return {
                'success': False,
                'error': str(e),
                'response_time': 0
            }

    
    def set_payment_id_failed(self, payment_id, reason="处理失败", order_data=None, status=1):
        """设置payment_id失败状态 - 20分钟冷却期
        
        Args:
            payment_id: Payment ID
            reason: 失败原因
            order_data: 完整订单数据（可选）
            status: 状态类型 - 1: 真正失败, 2: 按成功处理, 3: 系统异常
        """
        try:
            import time
            
            # 从Redis读取动态配置的冷却时间（与正常使用冷却共用配置）
            #try:
            #    cooldown_seconds_str = self.redis.get("easypaisa_paymentid_cooldown_seconds")
            #    if cooldown_seconds_str:
            #        cooldown_seconds = int(cooldown_seconds_str.decode() if isinstance(cooldown_seconds_str, bytes) else cooldown_seconds_str)
            #        self.logger.info(f"Payment ID失败冷却期使用动态配置: {cooldown_seconds}秒")
            #    else:
            #        cooldown_seconds = 30  # 默认30秒（与正常使用冷却一致）
            #        self.logger.info(f"Payment ID失败冷却期使用默认值: {cooldown_seconds}秒")
            #except Exception as config_e:
            #    cooldown_seconds = 30  # 读取配置失败时使用默认值
            #    self.logger.warning(f"读取Payment ID失败冷却期配置失败，使用默认值30秒: {config_e}")
            
            # 安全转换数值类型为JSON可序列化格式
            def safe_numeric(value):
                """安全转换数值类型，处理Decimal等不可JSON序列化的类型"""
                if value is None:
                    return None
                if isinstance(value, Decimal):
                    return float(value)
                if isinstance(value, (int, float)):
                    return value
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return str(value)
            
            failed_key = f'{self.REDIS_KEYS["payment_id_failed_prefix"]}{payment_id}'
            
            # 构造JSON格式的Value
            failed_info = {
                'payment_id': payment_id,
                'reason': reason,
                'created_time': time.time(),
                'expire_time': time.time() + 1200,  # 20分钟后过期
                'status': status
                #'cooldown_seconds': cooldown_seconds  # 记录实际冷却时间
            }
            
            # 如果有订单数据，添加到JSON中
            if order_data:
                failed_info.update({
                    'order_code': order_data.get('code'),
                    'amount': safe_numeric(order_data.get('amount')),  # 安全转换金额
                    'payment_account': order_data.get('payment_account'),
                    'name': order_data.get('name'),
                    'bank_code': order_data.get('bank_code'),
                    'time_created': str(order_data.get('time_accept', '')),
                    'user_id': order_data.get('user_id'),
                    'channel_id': order_data.get('channel_id')
                })
            
            # 设置20分钟冷却期，Value为JSON格式
            self.redis.setex(failed_key, 1200, json.dumps(failed_info, ensure_ascii=False))  # 1200秒 = 20分钟
            
            self.logger.info(f"Payment ID {payment_id} 设置失败冷却期20分钟: {reason}")
            
            # 使用动态冷却期，Value为JSON格式
            #self.redis.setex(failed_key, cooldown_seconds, json.dumps(failed_info, ensure_ascii=False))
            
            # 日志显示实际冷却时间
            #cooldown_minutes = cooldown_seconds / 60
            #self.logger.info(f"Payment ID {payment_id} 设置失败冷却期{cooldown_minutes:.1f}分钟({cooldown_seconds}秒): {reason}")
            #if order_data:
            #   self.logger.info(f"存储订单信息: {order_data.get('code')} - {order_data.get('amount')}")
            
            return True
        except Exception as e:
            self.logger.error(f'设置payment_id失败状态失败: {e}')
            return False

    # ========== 订单冷却期管理机制 ==========
    
    def is_order_in_cooldown(self, order_code: str) -> bool:
        """检查订单是否在冷却期内"""
        try:
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            cooldown_info_str = self.redis.hget(hash_key, order_code)
            
            if cooldown_info_str:
                cooldown_info = json.loads(cooldown_info_str.decode())
                current_time = time.time()
                
                if current_time < cooldown_info['expire_time']:
                    # 仍在冷却期内
                    remaining_minutes = (cooldown_info['expire_time'] - current_time) / 60
                    self.logger.info(f"订单{order_code}在冷却期内，剩余{remaining_minutes:.1f}分钟: {cooldown_info['reason']}")
                    return True
                else:
                    # 冷却期已过期，标记为可处理状态，但不删除记录
                    if cooldown_info.get('status') != 'expired':
                        cooldown_info['status'] = 'expired'
                        self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))
                        self.logger.info(f"订单{order_code}冷却期已过期，标记为可处理状态（等级{cooldown_info.get('cooldown_level', 0)}）")
                    return False
            
            return False
        except Exception as e:
            self.logger.error(f"检查订单{order_code}冷却期异常: {e}")
            return False  # 异常时允许处理
    
    def set_order_cooldown(self, order_code: str, payment_id: str, reason: str, 
                          order_data: dict, status: int = 1):
        """设置订单冷却期（支持累加）
        
        Args:
            payment_id: payment_id，如果没有可用账号可传入None或"no_account"
            status: 1=明确失败, 2=按成功处理, 3=超限异常按成功处理
        """
        try:
            import time
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            current_time = time.time()
            
            # 尝试获取现有记录
            existing_info_str = self.redis.hget(hash_key, order_code)
            
            if existing_info_str:
                # 存在历史记录，累加冷却等级
                existing_info = json.loads(existing_info_str.decode())
                cooldown_level = existing_info.get('cooldown_level', 0) + 1
                total_failures = existing_info.get('total_failures', 0) + 1
                failure_history = existing_info.get('failure_history', [])
                first_failure_time = existing_info.get('first_failure_time', current_time)
            else:
                # 首次失败
                cooldown_level = 1
                total_failures = 1
                failure_history = []
                first_failure_time = current_time
            
            # 计算冷却时间
            if status == 3:  # 超限异常按成功处理，不设置实际冷却期
                cooldown_minutes = 0
                expire_time = current_time  # 立即过期，不影响后续处理
            else:
                cooldown_minutes = self.calculate_cooldown_minutes(cooldown_level)
                expire_time = current_time + (cooldown_minutes * 60)
            
            # 添加到失败历史
            failure_history.append({
                "time": current_time,
                "reason": reason,
                "cooldown_minutes": cooldown_minutes,
                "retry_count": order_data.get('retry_count', 0)
            })
            
            # 限制历史记录数量（避免无限增长）
            if len(failure_history) > 10:
                failure_history = failure_history[-10:]
            
            # 处理payment_id为None的情况（如没有可用账号）
            safe_payment_id = payment_id if payment_id is not None else "no_account"
            
            cooldown_info = {
                'order_code': order_code,
                'payment_id': safe_payment_id,
                'reason': reason,
                'created_time': current_time,
                'expire_time': expire_time,
                'cooldown_level': cooldown_level,
                'cooldown_minutes': cooldown_minutes,
                'total_failures': total_failures,
                'last_failure_time': current_time,
                'first_failure_time': first_failure_time,
                'failure_history': failure_history,
                'status': 'max_retry_final' if status == 3 else 'active',  # active=冷却中, max_retry_final=超限终结
                'order_amount': float(order_data.get('amount', 0)),
                'current_retry_count': order_data.get('retry_count', 0),
                'record_type': status  # 1=明确失败, 2=按成功处理, 3=超限异常按成功处理
            }
            
            # 存储到Hash表
            self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))
            
            if status == 3:
                self.logger.info(f"订单{order_code}超限终结记录: 等级{cooldown_level}, 总失败{total_failures}次, payment_id={safe_payment_id}, 仅用于统计: {reason}")
            else:
                self.logger.info(f"订单{order_code}设置冷却期: 等级{cooldown_level}, 时长{cooldown_minutes}分钟, 总失败{total_failures}次, payment_id={safe_payment_id}: {reason}")
            
        except Exception as e:
            self.logger.error(f"设置订单{order_code}冷却期异常: {e}")


    def calculate_cooldown_minutes(self, level: int) -> int:
        """根据冷却等级计算时间（支持动态配置，不限等级数量）
        
        规则：
        - 如果 level 在配置范围内，使用对应配置
        - 如果 level 超过配置数量，使用最后一个配置的时间（循环冷却）
        - 读取配置失败时使用默认值
        
        配置变更影响：
        - 已在冷却期的订单：不受影响（expire_time已固定）
        - 下一次失败的订单：使用新配置
        - 等级超出旧配置时：受新配置影响（如4级→6级，第5次失败会用新的等级5配置）
        """
        try:
            # 从 Redis 读取配置
            import json
            config_key = self.REDIS_KEYS.get('easypaisa_order_cooldown_config')
            
            if config_key:
                config_str = self.redis.get(config_key)
                
                if config_str:
                    # 处理 bytes 类型（Redis 可能返回 bytes 或 str）
                    if isinstance(config_str, bytes):
                        config_str = config_str.decode('utf-8')
                    
                    config = json.loads(config_str)
                    levels_config = config.get('levels', [])
                    
                    if levels_config:
                        # 查找匹配的等级配置
                        for level_config in levels_config:
                            if level_config['level'] == level:
                                minutes = level_config['minutes']
                                self.logger.info(f"[订单冷却期] 使用配置: 等级{level} = {minutes}分钟")
                                return minutes
                        
                        # 🔥 关键：超过最大等级，使用最后一个配置（支持无限等级）
                        max_configured_level = max([lc['level'] for lc in levels_config])
                        if level > max_configured_level:
                            last_config = levels_config[-1]  # 获取最后一个配置
                            minutes = last_config['minutes']
                            self.logger.info(
                                f"[订单冷却期] 等级{level}超过配置范围(最大{max_configured_level})，"
                                f"使用最后一级配置: {minutes}分钟"
                            )
                            return minutes
        
        except json.JSONDecodeError as e:
            self.logger.warning(f"[订单冷却期] JSON解析失败，使用默认值: {e}")
        except Exception as e:
            self.logger.warning(f"[订单冷却期] 读取配置失败，使用默认值: {e}")
        
        # 🔥 默认值（向后兼容）- 使用统一逻辑
        default_levels = [
            {"level": 1, "minutes": 30},
            {"level": 2, "minutes": 120},
            {"level": 3, "minutes": 360},
            {"level": 4, "minutes": 1440}
        ]
        
        # 查找匹配的默认等级
        for default_level in default_levels:
            if default_level['level'] == level:
                self.logger.info(f"[订单冷却期] 使用默认配置: 等级{level} = {default_level['minutes']}分钟")
                return default_level['minutes']
        
        # 超出默认配置范围，使用最后一个默认值（统一逻辑）
        last_default_minutes = default_levels[-1]['minutes']
        self.logger.info(f"[订单冷却期] 等级{level}超出默认范围，使用最后一级默认值: {last_default_minutes}分钟")
        return last_default_minutes

    def mark_order_cooldown_success(self, order_code: str):
        """标记订单成功处理，更新冷却记录状态"""
        try:
            import time
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            cooldown_info_str = self.redis.hget(hash_key, order_code)
            
            if cooldown_info_str:
                # 订单有失败历史，更新状态为成功
                cooldown_info = json.loads(cooldown_info_str.decode())
                cooldown_info['status'] = 'success'
                cooldown_info['success_time'] = time.time()
                
                # 更新记录状态，但不删除（用于统计分析）
                self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))
                
                self.logger.info(f"订单{order_code}成功处理，更新冷却记录状态为success（等级{cooldown_info.get('cooldown_level', 0)}）")
            else:
                # 订单没有失败历史（正常情况），无需冷却记录
                self.logger.debug(f"订单{order_code}成功处理，无失败历史记录（正常情况）")
        except Exception as e:
            self.logger.error(f"标记订单{order_code}成功状态异常: {e}")


    def is_known_failure_reason(self, message: str) -> bool:
        """判断是否为明确的失败原因"""
        if not message:
            return False
            
        # API错误码（明确的失败原因，除了402都是明确失败）
        api_error_codes = [
            'code=401',  # SessionInvalid - 账号Session失效
            'code=403',  # CheckParam - 业务被拒绝，检查传入参数
            'code=423',  # ServerBusy - 云机正忙
            'code=500',  # Error - 服务器业务错误
            'code=501',  # AccountInvalid - 账号异常，可能锁号
            'code=503'   # NetworkError - 服务器网络问题
            # 注意：code=402不在此列表中，因为它按成功处理，不需要冷却期
        ]
        
        # 传统的失败原因模式
        known_patterns = [
            '余额不足', 'insufficient balance', 'low balance',
            '账号错误', 'invalid account', 'account not found',
            '账户被锁', 'account locked', 'account suspended',
            '超出限额', 'limit exceeded', 'amount limit',
            '账号异常', 'account error', 'account problem',
            '暂无可用账号', 'no available account', 'no account available',  # 系统资源问题
            '账号锁定失败', 'account lock failed', 'lock failed',           # 并发竞争问题
            '风控拦截', 'risk control', 'risk blocked'                      # 风控问题
        ]
        
        message_lower = message.lower()
        
        # 检查API错误码
        if any(code.lower() in message_lower for code in api_error_codes):
            return True
            
        # 检查传统失败原因
        return any(pattern.lower() in message_lower for pattern in known_patterns)

    async def get_real_available_accounts(self, orders: List[Dict]) -> List[Dict]:
        """
        获取当前真正可用的账号列表，供预分配调度使用。
        包含所有防护检查：在线、释放时间、锁、金额限制、使用间隔。
        """
        if not orders:
            return []

        min_amount = min(Decimal(str(o['amount'])) for o in orders)
        self.logger.info(f"预分配：获取可用账号，最小订单金额={min_amount}")

        # 从 sorted set 获取高余额账号（幽灵缓存已在此方法内过滤）
        raw_accounts = self.get_top_balance_accounts(min_balance=min_amount, count=50)
        if not raw_accounts:
            self.logger.warning("预分配：无余额满足要求的账号")
            return []

        # 逐项检查
        available = []
        skip_stats = {'offline': 0, 'release': 0, 'locked': 0, 'amount_limit': 0, 'recently_used': 0}

        for account in raw_accounts:
            pid = account['payment_id']

            # 在线检查
            if not await self.check_account_online_status(pid):
                skip_stats['offline'] += 1
                continue

            # 释放时间检查
            if not self.check_account_release_time(pid):
                skip_stats['release'] += 1
                continue

            # payment_id 锁检查（Redis EXISTS 只读探测）
            lock_key = f'{self.REDIS_KEYS["payment_id_lock_prefix"]}{pid}'
            if self.redis.exists(lock_key):
                skip_stats['locked'] += 1
                continue

            # 金额限制检查
            amount_check = await self.check_account_amount_limits(pid, min_amount)
            if not amount_check.get('passed', True):
                skip_stats['amount_limit'] += 1
                continue

            # 20分钟使用间隔检查
            if self.is_account_recently_used(pid):
                skip_stats['recently_used'] += 1
                continue

            available.append(account)

        self.logger.info(
            f"预分配：从{len(raw_accounts)}个候选中筛出{len(available)}个可用账号 "
            f"(离线:{skip_stats['offline']}, 释放期:{skip_stats['release']}, "
            f"已锁:{skip_stats['locked']}, 限额:{skip_stats['amount_limit']}, "
            f"近期使用:{skip_stats['recently_used']})"
        )
        return available

    def dispatch_orders_to_accounts(self, orders: List[Dict], accounts: List[Dict]) -> List[tuple]:
        """
        按金额降序 + 虚拟余额扣减分配订单到账号。
        大额订单优先分给余额最充足的账号，每次分配后扣减虚拟余额。
        Returns: List[(account_dict, [order_dict, ...])]
        """
        if not accounts or not orders:
            return []

        # 订单按金额降序（大额优先分配）
        orders_sorted = sorted(orders, key=lambda o: Decimal(str(o['amount'])), reverse=True)

        # 账号按余额降序，维护虚拟余额（Decimal 精度）
        accounts_sorted = sorted(accounts, key=lambda a: a.get('balance', 0), reverse=True)
        virtual_balances = {a['payment_id']: Decimal(str(a.get('balance', 0))) for a in accounts_sorted}
        buckets = {a['payment_id']: {'account': a, 'orders': []} for a in accounts_sorted}
        unassigned = []

        for order in orders_sorted:
            amount = Decimal(str(order['amount']))
            # 找虚拟余额最充足且足够的账号
            best_pid = None
            best_remaining = Decimal('-1')
            for a in accounts_sorted:
                pid = a['payment_id']
                remaining = virtual_balances[pid]
                if remaining >= amount and remaining > best_remaining:
                    best_pid = pid
                    best_remaining = remaining
            if best_pid:
                buckets[best_pid]['orders'].append(order)
                virtual_balances[best_pid] -= amount
            else:
                unassigned.append(order)

        if unassigned:
            self.logger.info(f"预分配：{len(unassigned)}个订单因余额不足未分配，留给下轮")

        result = [(v['account'], v['orders']) for v in buckets.values() if v['orders']]

        for account, assigned_orders in result:
            self.logger.info(
                f"预分配：账号{account['payment_id']}"
                f"(余额{account.get('balance','?')}→虚拟剩余{virtual_balances[account['payment_id']]}) "
                f"分配{len(assigned_orders)}个订单"
            )

        return result

    def filter_cooldown_orders(self, orders: List[Dict]) -> List[Dict]:
        """批量过滤冷却期内的订单"""
        if not orders:
            return orders
            
        try:
            import time
            hash_key = self.REDIS_KEYS['easypaisa_order_cooldown_hash']
            current_time = time.time()
            filtered_orders = []
            cooldown_details = []
            
            # 批量获取所有订单的冷却信息
            order_codes = [order['code'] for order in orders]
            
            # 使用Redis pipeline提高批量查询性能
            pipe = self.redis.pipeline()
            for order_code in order_codes:
                pipe.hget(hash_key, order_code)
            
            cooldown_results = pipe.execute()
            
            # 检查每个订单的冷却状态
            for i, order in enumerate(orders):
                order_code = order['code']
                cooldown_info_str = cooldown_results[i]
                
                if cooldown_info_str:
                    try:
                        cooldown_info = json.loads(cooldown_info_str.decode())
                        
                        # 超限终结记录不参与冷却期检查
                        if cooldown_info.get('status') == 'max_retry_final':
                            # 这些记录仅用于统计，不影响订单处理
                            pass
                        elif current_time < cooldown_info['expire_time']:
                            # 仍在冷却期内，跳过此订单
                            remaining_minutes = (cooldown_info['expire_time'] - current_time) / 60
                            cooldown_details.append({
                                'order_code': order_code,
                                'remaining_minutes': remaining_minutes,
                                'reason': cooldown_info.get('reason', '未知'),
                                'level': cooldown_info.get('cooldown_level', 0)
                            })
                            continue
                        else:
                            # 冷却期已过期，标记为可处理状态（批量更新）
                            if cooldown_info.get('status') != 'expired':
                                cooldown_info['status'] = 'expired'
                                self.redis.hset(hash_key, order_code, json.dumps(cooldown_info, ensure_ascii=False))
                    
                    except (json.JSONDecodeError, KeyError) as e:
                        # JSON解析错误，删除异常记录，允许处理
                        self.logger.warning(f"订单{order_code}冷却期记录格式异常，删除记录: {e}")
                        self.redis.hdel(hash_key, order_code)
                
                # 添加到可处理订单列表
                filtered_orders.append(order)
            
            # 记录冷却期详情（debug级别）
            if cooldown_details:
                for detail in cooldown_details:
                    self.logger.debug(f"订单{detail['order_code']}在冷却期内({detail['remaining_minutes']:.1f}分钟)，等级{detail['level']}: {detail['reason']}")
            
            return filtered_orders
            
        except Exception as e:
            # Redis访问异常时，返回原始订单列表（降级处理）
            self.logger.error(f"批量检查订单冷却期异常，返回原始订单列表: {e}")
            return orders

    async def acquire_account_lock(self, account_id: str, order_code: str) -> Optional[str]:
        """获取账号锁"""
        try:
            lock_key = f"{self.REDIS_KEYS['easypaisa_account_lock_prefix']}{account_id}"
            lock_value = f"{order_code}_{secrets.token_hex(8)}"
            
            if self.redis.setnx(lock_key, lock_value):
                self.redis.expire(lock_key, 300)  # 5分钟
                self.logger.info(f"账号{account_id}锁获取成功: {lock_value}")
                return lock_value
            else:
                self.logger.debug(f"账号{account_id}锁获取失败")
                return None
                
        except Exception as e:
            self.logger.error(f"获取账号{account_id}锁失败: {e}")
            return None

    def release_account_lock(self, account_id: str, lock_value: str):
        """释放账号锁"""
        try:
            lock_key = f"{self.REDIS_KEYS['easypaisa_account_lock_prefix']}{account_id}"
            current_value = self.redis.get(lock_key)
            if current_value and current_value.decode() == lock_value:
                self.redis.delete(lock_key)
                self.logger.info(f"账号{account_id}锁释放成功")
        except Exception as e:
            self.logger.error(f"释放账号{account_id}锁失败: {e}")

    # ========== 风控控制器 ==========
    async def check_payout_risk(self, order_data: Dict) -> Dict:
        """风控检查"""
        try:
            # 检查紧急停机
            emergency_stop = self.redis.get(self.REDIS_KEYS['easypaisa_emergency_stop'])
            if emergency_stop == b"1" or emergency_stop == "1":
                return {'passed': False, 'reason': 'emergency_stop', 'message': '系统紧急停机'}
            
            amount = Decimal(str(order_data['amount']))
            
            # 基础金额检查
            if amount < Decimal('0.1'):    # 单笔少于0.1
                return {'passed': False, 'reason': 'amount_too_small', 'message': '单笔金额过小'}
            
            # 检查系统负载
            active_orders_key = 'easypaisa_active_orders_count'
            active_count = self.redis.get(active_orders_key)
            if active_count and int(active_count.decode()) > 100:  # 超过100个活跃订单
                return {'passed': False, 'reason': 'system_overload', 'message': '系统负载过高'}
            
            return {'passed': True}
            
        except Exception as e:
            self.logger.error(f"风控检查异常: {e}")
            return {'passed': True, 'message': '风控检查异常，放行处理'}

    # ========== 调度引擎 ==========
    
    async def prepare_account_and_locks(self, order_data: Dict) -> Dict:
        """
        为订单准备账号并获取必要的锁
        
        参数：
            order_data: 订单数据
            
        返回：
            {
                'success': True/False,
                'selected_account': {...},  # 成功时返回
                'order_lock_value': '...',  # 成功时返回
                'account_lock': '...',      # 成功时返回
                'payment_id_lock_value': '...',  # 成功时返回
                'account_id': '...',        # 成功时返回
                'payment_id': '...',        # 成功时返回
                'message': '...'
            }
        """
        order_code = order_data['code']
        amount = Decimal(str(order_data['amount']))
        target_account = order_data.get('payment_account', '')
        
        # 初始化变量，用于异常时的清理
        selected_account = None
        order_lock_value = None
        account_lock = None
        payment_id_lock_value = None
        account_id = None
        payment_id = None
        
        try:
            # 1. 获取可用账号
            self.logger.info(f"订单{order_code} 开始选择可用账号，金额: {amount}")
            accounts = await self.get_available_accounts(amount, target_account)

            # ===================== 新增代付专卡专户过滤开始 =====================
            # 新增代付专卡专用
            # 如果订单有指定需要用的出款账户，则从accounts中只挑选指定的专户。如果不指定则从广泛匹配号列表移除全局专卡专户登记的银行卡
            target_payment_filtered_accounts = []
            if order_data['target_payment']:
                target_payment_filtered_accounts = [account for account in accounts if account['payment_id'] in order_data['target_payment'].split(',')]
            else:
                target_payment_key: str = (self.redis.get("target_payment_key") or b"").decode()
                target_payment_filtered_accounts = [account for account in accounts if account['payment_id'] not in target_payment_key.split(',')]
            accounts = target_payment_filtered_accounts
            # ===================== 新增代付专卡专户过滤结束 =====================

            if not accounts:
                return {
                    'success': False,
                    'message': f'订单{order_code} 暂无可用账号'
                }
            
            # 2. 选择最优账号
            selected_account = accounts[0]
            account_id = selected_account['phone']
            payment_id = selected_account['payment_id']
            
            self.logger.info(
                f"订单{order_code} 选择账号: {account_id}, "
                f"payment_id: {payment_id}, 余额: {selected_account.get('balance', 'N/A')}"
            )
            
            # 🔥 3. 获取订单锁（有可用账号后才获取）
            order_lock_value = self.get_lock(order_code)
            if not order_lock_value:
                self.return_account_to_active_list(selected_account)
                return {
                    'success': False,
                    'message': f'订单{order_code} 未抢到订单锁'
                }
            
            self.logger.info(f"订单{order_code} 成功获取订单锁")
            
            # 4. 获取账号锁
            account_lock = await self.acquire_account_lock(account_id, order_code)
            if not account_lock:
                # 账号锁失败，释放订单锁
                self.del_lock(order_code, order_lock_value)
                self.return_account_to_active_list(selected_account)
                return {
                    'success': False,
                    'message': f'订单{order_code} 账号{account_id}被锁定'
                }
            
            self.logger.info(f"订单{order_code} 成功获取账号锁: {account_id}")
            
            # 5. 获取 payment_id 锁
            payment_id_lock_value = self.get_payment_id_lock(payment_id)
            if not payment_id_lock_value:
                # payment_id 锁定失败，释放订单锁和账号锁
                self.release_account_lock(account_id, account_lock)
                self.del_lock(order_code, order_lock_value)
                self.return_account_to_active_list(selected_account)
                return {
                    'success': False,
                    'message': f'订单{order_code} Payment ID {payment_id} 锁定失败'
                }
            
            self.logger.info(f"订单{order_code} 成功获取 payment_id 锁: {payment_id}")
            
            # 6. 成功返回
            return {
                'success': True,
                'selected_account': selected_account,
                'order_lock_value': order_lock_value,
                'account_lock': account_lock,
                'payment_id_lock_value': payment_id_lock_value,
                'account_id': account_id,
                'payment_id': payment_id
            }
            
        except Exception as e:
            self.logger.error(f"订单{order_code} 准备账号和锁失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
            # 🔥 异常时释放已获取的锁（倒序释放）
            if payment_id_lock_value and payment_id:
                try:
                    self.del_payment_id_lock(payment_id, payment_id_lock_value)
                    self.logger.info(f"订单{order_code} 异常时释放 payment_id 锁")
                except Exception as lock_e:
                    self.logger.error(f"释放 payment_id 锁失败: {lock_e}")
            
            if account_lock and account_id:
                try:
                    self.release_account_lock(account_id, account_lock)
                    self.logger.info(f"订单{order_code} 异常时释放账号锁")
                except Exception as lock_e:
                    self.logger.error(f"释放账号锁失败: {lock_e}")
            
            if order_lock_value:
                try:
                    self.del_lock(order_code, order_lock_value)
                    self.logger.info(f"订单{order_code} 异常时释放订单锁")
                except Exception as lock_e:
                    self.logger.error(f"释放订单锁失败: {lock_e}")
            
            # 把账号放回活跃列表
            if selected_account:
                try:
                    self.return_account_to_active_list(selected_account)
                    self.logger.info(f"订单{order_code} 异常时账号已放回活跃列表")
                except Exception as list_e:
                    self.logger.error(f"账号放回活跃列表失败: {list_e}")
            
            return {
                'success': False,
                'message': f'准备账号异常: {str(e)}'
            }
    
    async def process_payout_order(self, order_data: Dict, connection=None, selected_account: Dict = None) -> Dict:
        """代付订单处理"""
        order_code = order_data['code']
        amount = Decimal(str(order_data['amount']))
        
        self.logger.info(f"开始处理代付订单: {order_code}, 金额: {amount}")
        
        # 🔥 使用外部传入的账号
        account_id = selected_account['phone']
        payment_id = selected_account['payment_id']
        
        try:
            # 1. 风控检查
            risk_result = await self.check_payout_risk(order_data)
            if not risk_result['passed']:
                return {
                    'success': False,
                    'message': f"风控拦截: {risk_result.get('message', risk_result['reason'])}"
                }
            
            # 🔥 以下代码已移到 process_single_order_async 中执行
            # # 2. 获取可用账号 (传入收款账号用于过滤)
            # target_account = order_data.get('payment_account', '')
            # accounts = await self.get_available_accounts(amount, target_account)
            # if not accounts:
            #     # 没有可用账号时，等待下次轮询处理
            #     self.logger.info(f"订单 {order_code} 暂无可用账号，等待下次轮询")
            #     return {
            #         'success': False,
            #         'message': '暂无可用账号，等待下次轮询',
            #         'retry': True
            #     }
            # 
            # # 3. 选择最优账号
            # selected_account = accounts[0]
            # account_id = selected_account['phone']
            # 
            # # 4. 获取账号锁
            # account_lock = await self.acquire_account_lock(account_id, order_code)
            # if not account_lock:
            #     # 账号被锁定，将账号重新入队
            #     self.return_account_to_active_list(selected_account)
            #     return {
            #         'success': False,
            #         'message': f'账号{account_id}被锁定，已重新排队',
            #         'payment_id': selected_account.get('payment_id'),
            #         'partner_id': selected_account.get('partner_id')
            #     }
            # 
            # # 5. 获取payment_id锁（在账号锁之后）
            # payment_id = selected_account['payment_id']
            # payment_id_lock_value = self.get_payment_id_lock(payment_id)
            # if not payment_id_lock_value:
            #     # payment_id锁定失败，释放账号锁并重新入队
            #     self.release_account_lock(account_id, account_lock)
            #     self.return_account_to_active_list(selected_account)
            #     return {
            #         'success': False,
            #         'message': f'Payment ID {payment_id} 锁定失败，已重新排队',
            #         'payment_id': payment_id,
            #         'partner_id': selected_account.get('partner_id')
            #     }
            
            try:
                # 6. 执行EasyPaisa转账
                transfer_result = await self._execute_easypaisa_transfer(order_data, selected_account)
                
                if transfer_result and transfer_result['success']:
                    # 🔥 转账成功，记录账号使用时间（动态冷却期）
                    self.record_account_usage(selected_account['payment_id'])
                    
                    # 转账成功后立即扣减Redis余额
                    self.update_account_balance_after_transfer(
                        payment_id=selected_account['payment_id'],
                        transfer_amount=amount
                    )
                    
                    # 转账成功，设置账号释放时间（从配置读取）
                    self.set_account_release_time(selected_account['payment_id'])
                    if should_return_account_to_pool(preallocated_mode=selected_account.get('preallocated_mode', False)):
                        self.return_account_to_active_list(selected_account)
                    
                    return {
                        'success': True,
                        'message': '转账成功',
                        'transaction_id': transfer_result.get('transaction_id'),
                        'account_used': account_id,
                        'payment_id': selected_account['payment_id'],
                        'partner_id': selected_account.get('partner_id'),  # 新增：返回partner_id供外部使用
                        'payer_phone': transfer_result.get('payer_phone'),
                        'selected_account': selected_account  # 新增：返回完整账户信息供外部使用
                    }
                elif transfer_result is None:
                    # Python异常（如连接异常、JSON解析错误等）按成功处理
                    self.set_account_release_time(selected_account['payment_id'])  # 从配置读取释放时间
                    if should_return_account_to_pool(preallocated_mode=selected_account.get('preallocated_mode', False)):
                        self.return_account_to_active_list(selected_account)
                    
                    return {
                        'success': False,  # 🔥 修复: 不是真正成功
                        'treat_as_success': False, 
                        'message': 'Python异常，按成功处理避免重复代付',
                        'account_used': account_id,
                        'payment_id': selected_account['payment_id'],
                        'partner_id': selected_account.get('partner_id')
                    }
                else:
                    # 转账失败，根据错误码区分处理
                    message = transfer_result.get('message', '')
                    error_code = transfer_result.get('code')
                    is_reject = transfer_result.get('reject', False)
                    
                    self.set_account_release_time(selected_account['payment_id'])  # 从配置读取释放时间
                    if should_return_account_to_pool(preallocated_mode=selected_account.get('preallocated_mode', False)):
                        self.return_account_to_active_list(selected_account)
                    
                    # 🔥 驳回情况：直接返回，由外层处理
                    if is_reject:
                        return transfer_result  # 直接返回驳回结果，包含 reject=True
                    
                    # ✅ code=402 (转账失败) 特殊处理：放回订单池重试
                    if error_code == 402:
                        return {
                            'success': False,
                            'treat_as_success': True,  # 放回订单池
                            'message': f"EasyPaisa转账失败(code=402-Connection Failed)，放回订单池重试: {message}",
                            'account_used': account_id,
                            'payment_id': selected_account['payment_id'],
                            'partner_id': selected_account.get('partner_id')
                        }
                    else:
                        # 其他错误码按失败处理，status=2（待确认），不放回订单池
                        return {
                            'success': False,
                            'treat_as_success': False,
                            'message': f"API失败(code={error_code})，按失败处理: {message}",
                            'account_used': account_id,
                            'payment_id': selected_account['payment_id'],
                            'partner_id': selected_account.get('partner_id')
                        }
                        
            finally:
                # 注意：锁的释放统一在外层 process_single_order_async 的 finally 块中处理
                # 这里不需要释放锁，避免引用外层作用域的变量
                pass
                
        except asyncio.TimeoutError:
            # 会议决策：超时当成功处理
            self.logger.warning(f"订单{order_code}API超时，按成功处理")
            
            # 记录操作日志（早期异常 - 超时）
            try:
                # 如果selected_account未定义，使用默认值
                account_info = locals().get('selected_account', {'phone': 'unknown', 'payment_id': None})
                self.log_complete_transaction(
                    order_data, 
                    account_info, 
                    {}, 
                    {}, 
                    "early_exception_timeout", 
                    error_message="订单处理超时，按成功处理避免重复代付", 
                    start_time=time.time(),
                    before_balance=None, 
                    process_details={'exception_type': 'asyncio.TimeoutError', 'exception_stage': 'process_payout_order'}
                )
            except Exception as log_e:
                self.logger.warning(f"记录超时异常日志失败: {log_e}")
            
            # 获取selected_account信息（如果存在）
            if 'selected_account' in locals():
                return {
                    'success': False,
                    'treat_as_success': False,  # 超时不确定是否成功，设为待确认状态
                    'message': 'API超时，设为待确认状态待人工核实',
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id')
                }
            else:
                # selected_account未定义说明异常发生在账号选择之前，没有payment_id
                return {
                    'success': False,
                    'treat_as_success': False,  # 超时不确定是否成功，设为待确认状态
                    'message': 'API超时，设为待确认状态待人工核实'
                }
        except Exception as e:
            # 会议决策：异常当成功处理
            self.logger.error(f"订单{order_code}处理异常: {e}")
            
            # 记录操作日志（早期异常 - 通用异常）
            try:
                # 如果selected_account未定义，使用默认值
                account_info = locals().get('selected_account', {'phone': 'unknown', 'payment_id': None})
                self.log_complete_transaction(
                    order_data, 
                    account_info, 
                    {}, 
                    {}, 
                    "early_exception", 
                    error_message=f"订单处理异常，按成功处理避免重复代付: {str(e)}", 
                    start_time=time.time(),
                    before_balance=None, 
                    process_details={'exception_type': type(e).__name__, 'exception_stage': 'process_payout_order', 'exception_detail': str(e)}
                )
            except Exception as log_e:
                self.logger.warning(f"记录处理异常日志失败: {log_e}")
            
            # 获取selected_account信息（如果存在）
            if 'selected_account' in locals():
                return {
                    'success': False,
                    'treat_as_success': True,
                    'message': f'处理异常，按成功处理避免重复代付: {str(e)}',
                    'payment_id': selected_account['payment_id'],
                    'partner_id': selected_account.get('partner_id')
                }
            else:
                # selected_account未定义说明异常发生在账号选择之前，没有payment_id
                return {
                    'success': False,
                    'treat_as_success': True,
                    'message': f'处理异常，按成功处理避免重复代付: {str(e)}'
                }

    async def _execute_easypaisa_transfer(self, order_data: Dict, account_info: Dict) -> Optional[Dict]:
        """执行EasyPaisa转账 - 调用真实API"""
        # account_info 已经是完整的账号信息，包含 payment_id, phone, balance 等
        # 设置默认变量以防止NameError
        start_time = time.time()
        inner_payload = {}
        before_balance = None
        process_details = {}
        
        try:
            order_code = order_data['code']
            amount = str(order_data['amount'])
            to_account = order_data.get('payment_account', '')  # 目标账号
            payment_name = order_data.get('payment_name', '')  # 收款人姓名
            ifsc_code = order_data.get('ifsc', '')  # IFSC银行代码
            
            # 从传入的账号信息中获取数据（在早期获取，避免后续使用时未定义）
            payment_id = account_info.get('payment_id')
            phone_number = account_info.get('phone')
            
            # 判断是否为巴基斯坦手机号（EasyPaisa账号）
            is_pakistan_mobile = self._is_pakistan_mobile_number(to_account)

            # 根据账号类型确定转账方式和bankcode
            if is_pakistan_mobile and ifsc_code.lower() == 'easypaisa':
                # EasyPaisa同行转账，不需要bankcode
                to_bankcode = ''
                transfer_type = "EasyPaisa同行转账"
            else:
                # 跨行转账到银行卡，使用ifsc作为bankcode
                to_bankcode = ifsc_code
                transfer_type = "跨行转账到银行卡"
            
            # 记录流程开始时间和详细信息
            process_start_time = time.time()
            process_details = {
                'process_start_time': datetime.fromtimestamp(process_start_time).isoformat(),
                'order_received_time': datetime.fromtimestamp(process_start_time).isoformat(),
                'account_selection_time': datetime.now().isoformat(),
                'account_selection_status': 'success',
                'account_selection_criteria': 'auto_selected'
            }
            
            self.logger.info(f"开始执行EasyPaisa转账:")
            self.logger.info(f"  订单号: {order_code}")
            self.logger.info(f"  转出账号: {phone_number} (EasyPaisa钱包)")
            self.logger.info(f"  转入账号: {to_account}")
            self.logger.info(f"  账号类型判断: {'巴基斯坦手机号' if is_pakistan_mobile else '银行账号'}")
            self.logger.info(f"  收款人姓名: {payment_name}")
            self.logger.info(f"  转账金额: {amount}")
            self.logger.info(f"  转账类型: {transfer_type}")
            self.logger.info(f"  银行代码: {to_bankcode if to_bankcode else '无需bankcode'}")
            
            # 记录风险检查（这里简化为成功）
            process_details.update({
                'risk_check_time': datetime.now().isoformat(),
                'risk_check_status': 'success',
                'risk_check_details': {
                    'amount_check': 'passed',
                    'account_check': 'passed',
                    'frequency_check': 'passed'
                }
                        })
            
                        # 生成请求UUID
            request_uuid = str(uuid.uuid4())
            self.logger.info(f"  请求UUID: {request_uuid}")
            
            # 记录转账尝试开始时间
            start_time = time.time()
            
            self.logger.info(f"  账号信息: payment_id={payment_id}, phone={phone_number}")
            
            # 获取转账前余额
            before_balance = None
            balance_start_time = time.time()
            process_details['before_balance_time'] = datetime.now().isoformat()
            
            try:
                if account_info and account_info.get('payment_id'):
                    balance_result = await self.fetch_balance_from_api(account_info)
                    balance_duration = int((time.time() - balance_start_time) * 1000)
                    
                    if balance_result and balance_result.get('success'):
                        before_balance = balance_result.get('balance')
                        self.logger.info(f"  转账前余额: {before_balance}")
                        
                        process_details.update({
                            'before_balance_status': 'success',
                            'before_balance_duration': balance_duration
                        })
                    else:
                        error_msg = balance_result.get('error', '未知错误') if balance_result else 'API调用失败'
                        self.logger.warning(f"  无法获取转账前余额: {error_msg}")
                        
                        process_details.update({
                            'before_balance_status': 'failed',
                            'before_balance_error': error_msg,
                            'before_balance_duration': balance_duration
                        })
                else:
                    error_msg = '账号信息不完整'
                    self.logger.warning(f"  账号信息不完整，跳过余额查询")
                    
                    process_details.update({
                        'before_balance_status': 'skipped',
                        'before_balance_error': error_msg
                    })
            except Exception as e:
                error_msg = str(e)
                self.logger.warning(f"  获取转账前余额异常: {e}")
                before_balance = None
                balance_duration = int((time.time() - balance_start_time) * 1000)
                
                process_details.update({
                    'before_balance_status': 'exception',
                    'before_balance_error': error_msg,
                    'before_balance_duration': balance_duration
                })
            
            # 判断转账类型：EasyPaisa同行转账 vs 跨行转账
            if to_bankcode:
                # 跨行转账到银行卡
                action = "transferToCard"
                payload_data = {
                    "account_id": phone_number,  # 保持使用手机号作为account_id
                    "bankcode": to_bankcode,
                    "to_accno": to_account,
                    "amount": amount,
                    "remark": order_code  # 使用订单号作为备注
                }
                
                # account_accno为转账必送参数
                account_accno = account_info.get('account_accno')
                if not account_accno:
                    error_msg = f'账号{payment_id}缺少account_accno字段，无法执行跨行转账'
                    self.logger.error(error_msg)
                    # 记录错误日志并返回失败
                    self.log_complete_transaction(
                        order_data, account_info, {}, {}, 
                        "account_config_error", 
                        error_message=error_msg,
                        start_time=start_time, 
                        before_balance=before_balance,
                        process_details=process_details
                    )
                    return {'success': False, 'message': error_msg}

                payload_data["from_accno"] = account_accno
                self.logger.info(f"跨行转账使用account_accno: {account_accno}")
                
                self.logger.info(f"转账类型: 跨行转账 (transferToCard)")
            else:
                # EasyPaisa同行转账
                action = "transferToAcc"
                payload_data = {
                    "account_id": phone_number,  # 保持使用手机号作为account_id
                    "to_accno": to_account,
                    "amount": amount,
                    "remark": order_code  # 使用订单号作为备注
                }
                
                # account_accno为转账必送参数
                account_accno = account_info.get('account_accno')
                if not account_accno:
                    error_msg = f'账号{payment_id}缺少account_accno字段，无法执行同行转账'
                    self.logger.error(error_msg)
                    # 记录错误日志并返回失败
                    self.log_complete_transaction(
                        order_data, account_info, {}, {}, 
                        "account_config_error", 
                        error_message=error_msg,
                        start_time=start_time, 
                        before_balance=before_balance,
                        process_details=process_details
                    )
                    return {'success': False, 'message': error_msg}

                payload_data["from_accno"] = account_accno
                self.logger.info(f"同行转账使用account_accno: {account_accno}")
                
                self.logger.info(f"转账类型: EasyPaisa同行转账 (transferToAcc)")
            
            # 构建内层payload
            inner_payload = {
                "id": request_uuid,
                "action": action,
                "payload": payload_data
            }
            
            self.logger.info(f"API请求载荷: {inner_payload}")
            
            # 调用真实EasyPaisa API
            self.logger.info(f"开始调用EasyPaisa API...")
            
            api_start_time = time.time()
            process_details['transfer_api_time'] = datetime.now().isoformat()
            
            # 🔥 转账API使用60秒超时
            api_result = await self._call_easypaisa_api(inner_payload, phone_number, timeout=60)
            
            api_duration = int((time.time() - api_start_time) * 1000)
            process_details['api_duration_ms'] = api_duration
            
            # 记录API完整响应
            self.logger.info(f"EasyPaisa API响应: {api_result}")
            
            if api_result:
                code = api_result.get('code')
                msg = api_result.get('msg', '')
                data = api_result.get('data', {})
                
                self.logger.info(f"API响应解析: code={code}, msg={msg}, data={data}")
                
                if code == 200:
                    # 提取 orderStatus 判断实际状态
                    order_status = None
                    
                    # 尝试从不同路径提取 orderStatus
                    if data and isinstance(data, dict):
                        body = data.get('body', {})
                        if isinstance(body, dict):
                            # 优先从 body.orderStatus 获取
                            order_status = body.get('orderStatus')
                            
                            # 如果没有，从 body.data.orderStatus 获取
                            if not order_status:
                                body_data = body.get('data', {})
                                if isinstance(body_data, dict):
                                    order_status = body_data.get('orderStatus')
                    
                    self.logger.info(f"API返回 code=200, orderStatus={order_status}")
                    
                    # 提取交易ID（所有情况都需要）
                    transaction_id = self._extract_transaction_id(api_result, action)
                    
                    # 根据 orderStatus 判断处理方式
                    if order_status == "P":
                        # ========== orderStatus = P (处理中/待确认) ==========
                        self.logger.info(f"转账处理中(orderStatus=P)，订单将设为确认中状态(status=2)")
                        
                        # 添加处理中状态的流程信息
                        process_details.update({
                            'lock_release_time': datetime.now().isoformat(),
                            'lock_release_status': 'success',
                            'lock_release_details': {
                                'account_lock_released': True,
                                'payment_id_lock_released': True,
                                'release_reason': 'order_status_pending'
                            },
                            'order_status': 'P',
                            'order_status_meaning': 'pending',
                            'total_duration_ms': int((time.time() - process_start_time) * 1000)
                        })
                        
                        # 记录完整的交易记录（处理中）
                        self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                    "failed", transaction_id=transaction_id, start_time=start_time,
                                                    before_balance=before_balance, 
                                                    error_message="EasyPaisa转账pending，请人工确认",
                                                    process_details=process_details)
                        
                        # 返回失败，但标记为待确认状态
                        return {
                            'success': False,           # 不是最终成功
                            'treat_as_success': False,  # 不按成功处理，将设为status=2等待后续查询
                            'transaction_id': transaction_id,
                            'message': f'EasyPaisa转账处理中(orderStatus=P)，设为待确认状态: {msg}',
                            'payer_phone': phone_number,
                            'order_status': 'P'
                        }
                    
                    else:
                        # ========== orderStatus = S (成功) 或其他状态 ==========
                        self.logger.info(f"转账成功(orderStatus={order_status})! 交易ID: {transaction_id}")
                        
                        # 计算转账后余额（优化：避免额外API调用）
                        after_balance = None
                        process_details['after_balance_time'] = datetime.now().isoformat()
                        
                        if before_balance is not None:
                            try:
                                # 直接用转账金额计算转账后余额
                                after_balance = Decimal(str(before_balance)) - Decimal(str(amount))
                                
                                # 记录余额变化信息
                                try:
                                    before_balance_decimal = Decimal(str(before_balance)) if not isinstance(before_balance, Decimal) else before_balance
                                    balance_change = float(after_balance - before_balance_decimal)
                                except (ValueError, TypeError, Decimal.InvalidOperation) as e:
                                    self.logger.warning(f"计算余额变化失败: after_balance={after_balance} ({type(after_balance)}), before_balance={before_balance} ({type(before_balance)}), error={e}")
                                    balance_change = -float(amount)  # 使用转账金额作为余额变化
                                
                                self.logger.info(f"  转账后余额: {after_balance} (计算得出)")
                                self.logger.info(f"  余额变化: {balance_change}")
                                
                                process_details.update({
                                    'after_balance_status': 'calculated',
                                    'calculation_method': 'before_balance - amount'
                                })
                                
                            except Exception as e:
                                error_msg = f"计算转账后余额失败: {e}"
                                self.logger.warning(f"  {error_msg}")
                                after_balance = None
                                process_details.update({
                                    'after_balance_status': 'calculation_failed',
                                    'after_balance_error': error_msg
                                })
                        else:
                            error_msg = '转账前余额为空，无法计算转账后余额'
                            self.logger.warning(f"  {error_msg}")
                            process_details.update({
                                'after_balance_status': 'skipped',
                                'after_balance_error': error_msg
                            })
                        
                        # 添加成功时的流程信息
                        process_details.update({
                            'lock_release_time': datetime.now().isoformat(),
                            'lock_release_status': 'success',
                            'lock_release_details': {
                                'account_lock_released': True,
                                'payment_id_lock_released': True
                            },
                            'order_status': order_status or 'unknown',
                            'total_duration_ms': int((time.time() - process_start_time) * 1000)
                        })
                        
                        # 记录完整的交易记录（成功）
                        self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                    "success", transaction_id=transaction_id, start_time=start_time,
                                                    before_balance=before_balance, after_balance=after_balance,
                                                    process_details=process_details)
                        
                        return {
                            'success': True,
                            'transaction_id': transaction_id,
                            'message': f'EasyPaisa转账成功: {msg}',
                            'payer_phone': phone_number,  # 新增：付款手机号，用于更新orders_df.utr字段
                            'order_status': order_status or 'S'
                        }
                elif code == 402:
                    # PaymentFail - 转账失败，可以重试
                    # 🔥 特殊处理：检查 msgCd=CIO41915，需要驳回订单
                    msg_cd = None
                    if data and isinstance(data, dict):
                        # 尝试从 data 直接获取 msgCd
                        msg_cd = data.get('msgCd')
                        
                        # 如果没有，尝试从 body 获取
                        if not msg_cd:
                            body = data.get('body', {})
                            if isinstance(body, dict):
                                msg_cd = body.get('msgCd')
                    
                    self.logger.warning(f"转账失败(可重试): code={code}, msgCd={msg_cd}, msg={msg}")
                    
                    # 🔥 特定 msgCd 需要驳回订单
                    reject_msg_codes = ['CIO41915', 'URM00000', 'PWM80422']
                    if msg_cd in reject_msg_codes:
                        self.logger.error(f"⚠️ 检测到需驳回订单的错误码: msgCd={msg_cd}")
                        
                        # 记录失败的交易
                        self.log_complete_transaction(
                            order_data, account_info, inner_payload, api_result, 
                            f"rejected_{msg_cd.lower()}", 
                            error_message=f"msgCd={msg_cd}: {msg}", 
                            start_time=start_time,
                            before_balance=before_balance, 
                            process_details=process_details
                        )
                        
                        # 🔥 不再直接调用驳回函数，只返回驳回标记，由外层统一处理事务
                        return {
                            'success': False,
                            'reject': True,  # 标记需要驳回
                            'reject_reason': msg,  # 直接使用 API 返回的 msg 内容
                            'message': f'Detected rejection error: msgCd={msg_cd}, {msg}'
                        }
                    
                    # 其他 code=402 情况继续按原逻辑处理（可重试）
                    self.logger.warning(f"转账失败(可重试): {msg}")
                    
                    # 添加失败时的流程信息
                    process_details.update({
                        'lock_release_time': datetime.now().isoformat(),
                        'lock_release_status': 'success',
                        'lock_release_details': {
                            'account_lock_released': True,
                            'payment_id_lock_released': True,
                            'release_reason': 'transfer_failed'
                        },
                        'total_duration_ms': int((time.time() - process_start_time) * 1000)
                    })
                    
                    # 记录完整的交易记录（失败）
                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                "failed", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 失败时只有转账前余额
                    
                    return {
                        'success': False,
                        'message': f'EasyPaisa转账失败: {msg}',
                        'can_retry': True,
                        'code': code
                    }
                elif code == 501:
                    # AccountInvalid - 账号异常（包括2小时冷却期），立即下线
                    self.logger.error(f"账号异常或冷却期: {msg}")
                    
                    # 添加账号异常时的流程信息
                    process_details.update({
                        'lock_release_time': datetime.now().isoformat(),
                        'lock_release_status': 'success',
                        'lock_release_details': {
                            'account_lock_released': True,
                            'payment_id_lock_released': True,
                            'release_reason': 'account_invalid'
                        },
                        'total_duration_ms': int((time.time() - process_start_time) * 1000)
                    })
                    
                    # 记录完整的交易记录（账号异常）
                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                "account_invalid", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 账号异常时只有转账前余额
                    
                    return {
                        'success': False,
                        'message': f'EasyPaisa账号异常或冷却期: {msg}',
                        'account_invalid': True
                    }
                elif code == 423:
                    # ServerBusy - 服务器忙，可重试
                    self.logger.warning(f"服务器忙碌: {msg}")
                    
                    # 记录完整的交易记录（服务器忙碌）
                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                "server_busy", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 服务器忙碌时只有转账前余额
                    
                    return {
                        'success': False,
                        'message': f'EasyPaisa服务器忙碌: {msg}',
                        'can_retry': True,
                        'code': code
                    }
                elif code == 403:
                    # CheckParam - 参数错误
                    self.logger.error(f"参数错误: {msg}")
                    
                    # 记录完整的交易记录（参数错误）
                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                "param_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 参数错误时只有转账前余额
                    
                    return {
                        'success': False,
                        'message': f'EasyPaisa参数错误: {msg}',
                        'can_retry': False,
                        'code': code
                    }
                elif code in [500, 503]:
                    # Error - 服务器严重错误 (500: 业务错误, 503: 服务不可用)
                    self.logger.error(f"服务器严重错误: {msg}")
                    
                    # 记录完整的交易记录（服务器严重错误）
                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                "server_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 服务器错误时只有转账前余额
                    
                    return {
                        'success': False,
                        'message': f'EasyPaisa服务器错误: {msg}',
                        'can_retry': False,
                        'code': code
                    }
                else:
                    # 其他未知错误码
                    self.logger.error(f"未知错误码: code={code}, msg={msg}")
                    
                    # 记录完整的交易记录（未知错误）
                    self.log_complete_transaction(order_data, account_info, inner_payload, api_result, 
                                                "unknown_error", error_message=msg, start_time=start_time,
                                                before_balance=before_balance, process_details=process_details)  # 未知错误时只有转账前余额
                    
                    return {
                        'success': False,
                        'message': f'EasyPaisa未知错误: {msg}',
                        'can_retry': True,
                        'code': code
                    }
            else:
                self.logger.error("EasyPaisa API无响应（网络异常或超时）")
                
                # 记录完整的交易记录（API无响应）
                self.log_complete_transaction(order_data, account_info, inner_payload, {}, 
                                            "api_no_response", error_message="API无响应（网络异常）", start_time=start_time,
                                            before_balance=before_balance, process_details=process_details)  # API无响应时只有转账前余额
                
                return {
                    'success': False,
                    'message': 'EasyPaisa API无响应（网络异常或超时）',
                    'can_retry': False,
                    'code': -1  # 使用-1表示客户端网络异常（不会和API返回冲突）
                }

        except Exception as e:
            self.logger.error(f"EasyPaisa转账异常: {e}")
            
            # 记录完整的交易记录（异常）
            account_info = account_info if 'account_info' in locals() else {'phone': 'unknown', 'payment_id': 'unknown'}
            start_time = start_time if 'start_time' in locals() else time.time()
            inner_payload = inner_payload if 'inner_payload' in locals() else {}
            before_balance = before_balance if 'before_balance' in locals() else None
            process_details = process_details if 'process_details' in locals() else {}
            self.log_complete_transaction(order_data, account_info, inner_payload, {}, 
                                        "exception", error_message=str(e), start_time=start_time,
                                        before_balance=before_balance, process_details=process_details)  # 异常时只有转账前余额
            
            return None
    
    async def _call_easypaisa_api_query(self, inner_payload: Dict, account_id: str, timeout: int = 30) -> Optional[Dict]:
        """调用EasyPaisa API的底层方法 - 专门用于查询操作（余额查询、账号检查等）
        
        Args:
            inner_payload: API请求载荷
            account_id: 账号ID
            timeout: 超时时间（秒），默认15秒（查询操作超时时间较短）
        """
        try:
            import base64
            import hashlib
            import json
            
            # EasyPaisa API配置 - 从config获取
            api_url = EASYPAISA_API_URL
            user_id = EASYPAISA_USER_ID
            secret_key = EASYPAISA_SECRET_KEY
            
            if not all([api_url, user_id, secret_key]):
                self.logger.error("EasyPaisa API配置缺失")
                return None
            
            # 1. 准备payload - 安全序列化，处理可能的Decimal类型
            try:
                payload_json = json.dumps(inner_payload, separators=(',', ':'))
            except TypeError as e:
                # 如果有Decimal类型导致序列化失败，使用安全转换
                self.logger.warning(f"JSON序列化失败，使用安全转换: {e}")
                
                def safe_json_convert(obj):
                    """递归转换对象中的Decimal类型"""
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: safe_json_convert(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple)):
                        return [safe_json_convert(item) for item in obj]
                    else:
                        return obj
                
                safe_payload = safe_json_convert(inner_payload)
                payload_json = json.dumps(safe_payload, separators=(',', ':'))
            
            # 2. Base64编码
            payload_b64 = base64.b64encode(payload_json.encode()).decode()
            
            # 3. 生成签名
            sign_str = payload_b64 + secret_key
            sign = hashlib.md5(sign_str.encode()).hexdigest()
            
            # 4. 构建请求数据
            form_data = {
                'user_id': user_id,
                'data': payload_b64,
                'sign': sign
            }
            
            # 5. 发送HTTP请求 - 使用查询专用的请求方法
            # 构造login_data参数（make_request需要）
            login_data = {'id': account_id}
            
            response = await self.retry_make_request_query(
                login_data, 
                "POST", 
                url=api_url, 
                headers=None, 
                params=None, 
                data=form_data, 
                json_data=None,
                timeout=timeout  # 使用传入的timeout参数
            )
            
            if response and response.status_code == 200:
                try:
                    result = response.json()
                    self.logger.info(f"EasyPaisa API查询响应: {result}")
                    return result
                except Exception as e:
                    self.logger.error(f"EasyPaisa API查询响应解析失败: {e}")
                    return None
            else:
                status_code = response.status_code if response else 'None'
                self.logger.error(f"EasyPaisa API查询HTTP错误: {status_code}")
                return None
                        
        except Exception as e:
            self.logger.error(f"调用EasyPaisa API查询异常: {e}")
            return None
    
    async def _call_easypaisa_api(self, inner_payload: Dict, account_id: str, timeout: int = 30) -> Optional[Dict]:
        """调用EasyPaisa API的底层方法
        
        Args:
            inner_payload: API请求载荷
            account_id: 账号ID
            timeout: 超时时间（秒），默认30秒，转账API使用60秒
        """
        try:
            import base64
            import hashlib
            import json
            
            # EasyPaisa API配置 - 从config获取
            api_url = EASYPAISA_API_URL
            user_id = EASYPAISA_USER_ID
            secret_key = EASYPAISA_SECRET_KEY
            
            if not all([api_url, user_id, secret_key]):
                self.logger.error("EasyPaisa API配置缺失")
                return None
            
            # 1. 准备payload - 安全序列化，处理可能的Decimal类型
            try:
                payload_json = json.dumps(inner_payload, separators=(',', ':'))
            except TypeError as e:
                # 如果有Decimal类型导致序列化失败，使用安全转换
                self.logger.warning(f"JSON序列化失败，使用安全转换: {e}")
                
                def safe_json_convert(obj):
                    """递归转换对象中的Decimal类型"""
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: safe_json_convert(v) for k, v in obj.items()}
                    elif isinstance(obj, (list, tuple)):
                        return [safe_json_convert(item) for item in obj]
                    else:
                        return obj
                
                safe_payload = safe_json_convert(inner_payload)
                payload_json = json.dumps(safe_payload, separators=(',', ':'))
            
            # 2. Base64编码
            payload_b64 = base64.b64encode(payload_json.encode()).decode()
            
            # 3. 生成签名
            sign_str = payload_b64 + secret_key
            sign = hashlib.md5(sign_str.encode()).hexdigest()
            
            # 4. 构建请求数据
            form_data = {
                'user_id': user_id,
                'data': payload_b64,
                'sign': sign
            }
            
            # 5. 发送HTTP请求 - 使用统一的make_request方法
            # 构造login_data参数（make_request需要）
            login_data = {'id': account_id}
            
            response = await self.retry_make_request(
                login_data, 
                "POST", 
                url=api_url, 
                headers=None, 
                params=None, 
                data=form_data, 
                json_data=None,
                timeout=timeout  # 使用传入的timeout参数
            )
            
            if response and response.status_code == 200:
                try:
                    result = response.json()
                    self.logger.info(f"EasyPaisa API响应: {result}")
                    return result
                except Exception as e:
                    self.logger.error(f"EasyPaisa API响应解析失败: {e}")
                    return None
            else:
                status_code = response.status_code if response else 'None'
                self.logger.error(f"EasyPaisa API HTTP错误: {status_code}")
                return None
                        
        except Exception as e:
            self.logger.error(f"调用EasyPaisa API异常: {e}")
            return None
    
    def _extract_transaction_id(self, api_result: Dict, action: str) -> str:
        """从API响应中提取交易ID"""
        try:
            data = api_result.get('data', {})
            
            # 优先从 data.body.data.extOrderNo 提取（EasyPaisa API 实际返回路径）
            body = data.get('body', {})
            body_data = body.get('data', {})
            transaction_id = body_data.get('extOrderNo', '')
            
            if transaction_id:
                return transaction_id
            
            # 备用路径1：尝试从 body.orderNo 提取
            transaction_id = body.get('orderNo', '')
            if transaction_id:
                return transaction_id
            
            # 备用路径2：尝试从 body.busOrderNo 提取
            transaction_id = body.get('busOrderNo', '')
            if transaction_id:
                return transaction_id
            
            # 如果都没有，记录警告并生成备用ID
            self.logger.warning(f"API响应中未找到交易ID，使用备用方案生成ID")
            return f"EP{uuid.uuid4().hex[:12].upper()}"  # 备用方案，使用EP前缀
                
        except Exception as e:
            self.logger.error(f"提取交易ID失败: {e}")
            return f"EP{uuid.uuid4().hex[:12].upper()}"

    # ========== 数据库操作方法（保持不变） ==========
    # 废弃：已整合到统一事务控制中
    # 以下函数已注释，因为没有被调用且功能已被其他函数替代
    
    # async def _get_order_data(self, order_code: str) -> Optional[Dict]:
    #     """获取订单数据 - 已废弃，使用统一事务控制"""
    #     try:
    #         connection = pymysql.connect(
    #             host=conf['mysql_host'],
    #             user=conf['mysql_user'], 
    #             password=conf['mysql_password'],
    #             db=conf['mysql_database'],
    #             charset='utf8mb4',
    #             cursorclass=pymysql.cursors.DictCursor
    #         )
    #         
    #         try:
    #             connection.ping()
    #             with connection.cursor() as cur:
    #                 sql = 'SELECT * FROM orders_df WHERE code = %s'
    #                 cur.execute(sql, order_code)
    #                 result = cur.fetchone()
    #                 return result
    #         finally:
    #             connection.close()
    #             
    #     except Exception as e:
    #         self.logger.error(f"查询订单{order_code}失败: {e}")
    #         return None

    # async def _update_order_status(self, order_code: str, status: int):
    #     """更新订单状态"""
    #     try:
    #         connection = pymysql.connect(
    #             host=conf['mysql_host'],
    #             user=conf['mysql_user'],
    #             password=conf['mysql_password'],
    #             db=conf['mysql_database'], 
    #             charset='utf8mb4',
    #             cursorclass=pymysql.cursors.DictCursor
    #         )
    #         
    #         try:
    #             with connection.cursor() as cur:
    #                 sql = """
    #                     UPDATE orders_df 
    #                     SET status = %s, time_accept = NOW(), otherpay = 'easypaisa_auto',
    #                         processed_by_auto = 1
    #                     WHERE code = %s
    #                 """
    #                 cur.execute(sql, (status, order_code))
    #                 connection.commit()
    #         finally:
    #             connection.close()
    #             
    #     except Exception as e:
    #         self.logger.error(f"更新订单{order_code}状态失败: {e}")

    # async def _update_order_success(self, order_code: str, result: Dict):
    #     """更新订单为成功状态"""
    #     try:
    #         connection = pymysql.connect(
    #             host=conf['mysql_host'],
    #             user=conf['mysql_user'],
    #             password=conf['mysql_password'],
    #             db=conf['mysql_database'],
    #             charset='utf8mb4',
    #             cursorclass=pymysql.cursors.DictCursor
    #         )
    #         
    #         try:
    #             with connection.cursor() as cur:
    #                 sql = """
    #                     UPDATE orders_df 
    #                     SET status = 3, time_payed = NOW(), time_success = NOW()
    #                     WHERE code = %s
    #                 """
    #                 cur.execute(sql, (order_code,))
    #                 connection.commit()
    #                 
    #             # 发送成功通知到Redis
    #             self.redis.publish('order_df_notify', order_code)
    #         finally:
    #             connection.close()
    #             
    #     except Exception as e:
    #         self.logger.error(f"更新订单{order_code}成功状态失败: {e}")

    # async def _update_order_failed(self, order_code: str, result: Dict):
    #     """更新订单为失败状态"""
    #     try:
    #         connection = pymysql.connect(
    #             host=conf['mysql_host'],
    #             user=conf['mysql_user'],
    #             password=conf['mysql_password'],
    #             db=conf['mysql_database'],
    #             charset='utf8mb4',
    #             cursorclass=pymysql.cursors.DictCursor
    #         )
    #         
    #         try:
    #             with connection.cursor() as cur:
    #                 sql = """
    #                     UPDATE orders_df 
    #                     SET status = -1, time_payed = NOW()
    #                     WHERE code = %s
    #                 """
    #                 cur.execute(sql, (order_code,))
    #                 connection.commit()
    #         finally:
    #             connection.close()
    #             
    #     except Exception as e:
    #         self.logger.error(f"更新订单{order_code}失败状态失败: {e}")

    # ========== 多进程和并发处理（保持不变） ==========
# 重复方法已删除 - 使用第一个get_active_processes_count方法

    async def process_single_order_async(self, order_message: str, pre_selected_account: Dict = None) -> bool:
        """异步处理单个订单 - 完整事务控制版本"""
        order_code = None
        order_lock_value = None
        connection = None
        account_lock = None  # 账号锁
        payment_id_lock_value = None  # payment_id 锁
        account_id = None  # 账号ID（用于释放锁）
        payment_id = None  # payment_id（用于错误处理和失败记录）
        order_data = None  # 初始化订单数据，防止异常时访问未定义变量
        success_result = False  # 初始化最终结果
        
        try:
            self.logger.info(f'收到订单消息: {order_message}')
            
            # 解析订单消息（格式：{code}_{amount}）
            parts = order_message.split('_')
            if len(parts) < 2:
                self.logger.error(f"订单消息格式错误: {order_message}")
                return False
            
            order_code = parts[0]
            amount = parts[1]
            
            # 🚨 处理前再次检查紧急停机状态
            emergency_stop = self.redis.get("easypaisa_emergency_stop")
            if emergency_stop == b"1" or emergency_stop == "1":
                self.logger.warning(f"⚠️ 订单{order_code}处理前检测到紧急停机状态，停止处理")
                return False
            
            # 🔥 订单锁已移到 prepare_account_and_locks 中获取（有可用账号后才获取）
            
            # 1. 建立数据库连接和事务
            connection = pymysql.connect(
                host=conf['mysql_host'],
                user=conf['mysql_user'],
                password=conf['mysql_password'],
                db=conf['mysql_database'],
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False  # 关闭自动提交，手动控制事务
            )
            
            try:
                with connection.cursor() as cur:
                    # 2. 查询订单信息（在事务内）
                    sql = 'SELECT * FROM orders_df WHERE code = %s'
                    cur.execute(sql, order_code)
                    order_data = cur.fetchone()
                    
                    if not order_data:
                        self.logger.error(f'订单{order_code}不存在')
                        return False
                    
                    # 检查订单状态
                    if order_data['status'] != 0:
                        self.logger.info(f'订单{order_code}已被处理，状态: {order_data["status"]}')
                        return False
                    
                    # 注意：冷却期检查已在get_pending_orders_by_time中完成
                    
                    # 🔥 3. 准备账号并获取锁
                    if pre_selected_account:
                        # 预分配模式：跳过账号选择，直接使用预分配账号获取锁
                        _pid = pre_selected_account['payment_id']
                        _phone = pre_selected_account['phone']
                        _target = order_data.get('payment_account', '')

                        # 快速防护检查：收付款相同
                        if _target and _phone == _target:
                            self.logger.info(f"订单{order_code} 预分配账号收付相同，跳过")
                            return False

                        # 专卡专户过滤
                        if order_data.get('target_payment'):
                            if _pid not in order_data['target_payment'].split(','):
                                self.logger.info(f"订单{order_code} 预分配账号{_pid}不在专卡列表，跳过")
                                return False
                        else:
                            _tpk = (self.redis.get("target_payment_key") or b"").decode()
                            if _tpk and _pid in _tpk.split(','):
                                self.logger.info(f"订单{order_code} 预分配账号{_pid}是全局专卡，跳过")
                                return False

                        # 重复订单检测
                        if _target:
                            _dup = self.check_duplicate_failure(
                                payment_id=_pid, amount=Decimal(str(order_data['amount'])),
                                to_account=_target, time_window=1200
                            )
                            if _dup.get('has_duplicate'):
                                self.logger.info(f"订单{order_code} 预分配账号{_pid}重复订单，跳过")
                                return False

                        # 获取三把锁
                        _order_lock = self.get_lock(order_code)
                        if not _order_lock:
                            self.logger.info(f"订单{order_code} 未抢到订单锁")
                            return False

                        _account_lock = await self.acquire_account_lock(_phone, order_code)
                        if not _account_lock:
                            self.del_lock(order_code, _order_lock)
                            self.logger.info(f"订单{order_code} 账号{_phone}被锁定")
                            return False

                        _pid_lock = self.get_payment_id_lock(_pid)
                        if not _pid_lock:
                            self.release_account_lock(_phone, _account_lock)
                            self.del_lock(order_code, _order_lock)
                            self.logger.info(f"订单{order_code} payment_id={_pid}锁定失败")
                            return False

                        prepare_result = {
                            'success': True,
                            'selected_account': {
                                **pre_selected_account,
                                'preallocated_mode': True,
                            },
                            'order_lock_value': _order_lock,
                            'account_lock': _account_lock,
                            'payment_id_lock_value': _pid_lock,
                            'account_id': _phone,
                            'payment_id': _pid,
                        }
                    else:
                        # 原模式：调用 prepare_account_and_locks 选账号
                        prepare_result = await self.prepare_account_and_locks(order_data)

                    if not prepare_result['success']:
                        self.logger.info(
                            f"订单{order_code} 准备账号失败: {prepare_result.get('message','')}，"
                            f"不更新订单状态，等待下次轮询"
                        )
                        return False
                    
                    # 提取准备好的资源
                    selected_account = prepare_result['selected_account']
                    order_lock_value = prepare_result['order_lock_value']
                    account_lock = prepare_result['account_lock']
                    payment_id_lock_value = prepare_result['payment_id_lock_value']
                    account_id = prepare_result['account_id']
                    payment_id = prepare_result['payment_id']
                    
                    self.logger.info(
                        f"订单{order_code} 准备完成: 账号{account_id}, payment_id={payment_id}"
                    )
                    
                    # 🔥 4. 更新订单状态为处理中（确认有可用账号且已锁定后才更新）
                    sql = """
                        UPDATE orders_df 
                        SET status = 1, time_accept = NOW()
                        WHERE code = %s AND status = 0
                    """
                    cur.execute(sql, (order_code,))
                    affected_rows = cur.rowcount
                    if affected_rows == 0:
                        self.logger.warning(f'订单{order_code}状态已不是0，可能已被其他进程处理，跳过')
                        return False
                    connection.commit()  # 立即提交，防止其他进程重复查询此订单
                    self.logger.info(f'订单{order_code}状态已更新为处理中(status=1)，事务已提交')
                    
                    # 🔥 5. 执行转账（传入已选择的账号）
                    result = await self.process_payout_order(
                        order_data, 
                        connection,
                        selected_account=selected_account
                    )
                    
                    # 6. 记录处理该订单的 payment_id 和 partner_id（所有情况都记录）
                    # 🔥 payment_id 和 account_id 已经从 prepare_result 中提取（第5094行），用于finally释放锁
                    partner_id = selected_account.get('partner_id')
                    
                    # 更新订单的 payment_id 和 partner_id
                    if partner_id:
                        # 同时设置payment_id和partner_id
                        sql = """
                            UPDATE orders_df 
                            SET payment_id = %s, partner_id = %s
                            WHERE code = %s
                        """
                        cur.execute(sql, (payment_id, partner_id, order_code))
                        self.logger.info(f"订单{order_code}已分配账号 payment_id: {payment_id}, partner_id: {partner_id}")
                    else:
                        # 如果partner_id为空，只设置payment_id
                        sql = """
                            UPDATE orders_df 
                            SET payment_id = %s
                            WHERE code = %s
                        """
                        cur.execute(sql, (payment_id, order_code))
                        self.logger.info(f"订单{order_code}已分配账号 payment_id: {payment_id} (partner_id为空)")
                    
                    # 7. 如果处理成功，立即更新订单状态为3
                    if result.get('success', False):
                        self.logger.info(f"订单{order_code}转账成功，payment_id: {payment_id}")
                        # 🔥 优化：转账成功后立即更新订单状态为3
                        time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        transaction_id = result.get('transaction_id', '')
                        sql_update_status = """
                            UPDATE orders_df 
                            SET status = 3, time_payed = %s, time_success = %s, utr = %s
                            WHERE code = %s AND status IN (0, 1)
                        """
                        cur.execute(sql_update_status, (time_now, time_now, transaction_id, order_code))
                        affected_rows = cur.rowcount
                        if affected_rows > 0:
                            self.logger.info(f"✅ 订单{order_code}转账成功，状态已更新为成功(status=3)，transaction_id: {transaction_id}")
                        else:
                            self.logger.warning(f"⚠️ 订单{order_code}转账成功，但状态已不是0或1，可能已被其他进程处理")
                    
                    # 8. 提交 payment_id 和订单状态更新事务
                    connection.commit()
                    self.logger.info(f'订单{order_code}payment_id已更新: {payment_id}, 订单状态: {result.get("success") and "成功" or "失败"}')
                    
                    # 9. 根据处理结果分别处理（独立事务）
                    if result.get('success', False):
                        # 9.1 代付成功：处理余额、佣金、流水
                        success_connection = None
                        try:
                            self.logger.info(f"订单{order_code}开始处理余额、佣金和流水")
                            
                            # 重新建立连接进行后续处理
                            success_connection = pymysql.connect(
                                host=conf['mysql_host'],
                                user=conf['mysql_user'],
                                password=conf['mysql_password'],
                                db=conf['mysql_database'],
                                charset='utf8mb4',
                                cursorclass=pymysql.cursors.DictCursor,
                                autocommit=False
                            )
                            
                            try:
                                with success_connection.cursor() as success_cur:
                                    # 设置 qr_id 用于后续处理
                                    self.qr_id = result.get('payment_id')
                                    
                                    # 🔥 重新查询最新的订单数据（包含已更新的payment_id、partner_id、status等）
                                    sql_refresh = 'SELECT * FROM orders_df WHERE code = %s'
                                    success_cur.execute(sql_refresh, (order_code,))
                                    updated_order_data = success_cur.fetchone()
                                    
                                    if not updated_order_data:
                                        self.logger.error(f"重新查询订单{order_code}失败，数据不存在")
                                        success_result = False
                                    else:
                                        self.logger.info(f"✅ 重新查询订单{order_code}成功：status={updated_order_data.get('status')}, payment_id={updated_order_data.get('payment_id')}, partner_id={updated_order_data.get('partner_id')}")
                                        
                                        # 调用自己的success处理逻辑（使用最新的订单数据）
                                        if self.handle_payout_success(success_connection, success_cur, updated_order_data, result):
                                            success_connection.commit()
                                            self.logger.info(f"订单{order_code}success处理成功")
                                            success_result = True
                                        else:
                                            success_connection.rollback()
                                            self.logger.error(f"订单{order_code}success处理失败")
                                            success_result = False
                            finally:
                                if success_connection:
                                    success_connection.close()
                                
                        except Exception as e:
                            self.logger.error(f"订单{order_code}调用success处理异常: {e}")
                            self.logger.error(traceback.format_exc())
                            success_result = False
                    
                    elif result.get('reject', False):
                        # 9.2 驳回处理：退款 + status=-1（独立连接）
                        self.logger.warning(f'订单{order_code}需要驳回，开始执行驳回操作: {result.get("reject_reason")}')
                        
                        reject_connection = None
                        try:
                            # 重新建立独立连接进行驳回处理
                            reject_connection = pymysql.connect(
                                host=conf['mysql_host'],
                                user=conf['mysql_user'],
                                password=conf['mysql_password'],
                                db=conf['mysql_database'],
                                charset='utf8mb4',
                                cursorclass=pymysql.cursors.DictCursor,
                                autocommit=False
                            )
                            
                            # 调用驳回函数（使用独立连接）
                            reject_result = self.reject_order_with_refund(
                                order_data=order_data,
                                connection=reject_connection,
                                reason=result.get('reject_reason', 'Unknown rejection reason'),
                                selected_account=selected_account
                            )
                            
                            if reject_result.get('reject', False):
                                # 驳回成功，提交
                                reject_connection.commit()
                                self.logger.info(f'✅ 订单{order_code}驳回成功，payment_id={payment_id}, status=-1，账号已放回活跃列表')
                                
                                # 🔥 新增：发送驳回通知到Redis
                                try:
                                    self.redis.publish('order_df_notify', order_code)
                                    self.logger.info(f'📢 已发送驳回通知到Redis: {order_code}')
                                except Exception as e:
                                    self.logger.error(f'发送驳回通知失败: {order_code}, 错误: {e}')
                            else:
                                # 驳回失败
                                reject_connection.rollback()
                                self.logger.error(f'❌ 订单{order_code}驳回失败: {reject_result.get("message")}，但payment_id已记录')
                        except Exception as e:
                            self.logger.error(f'订单{order_code}驳回异常: {e}')
                            if reject_connection:
                                try:
                                    reject_connection.rollback()
                                except:
                                    pass
                        finally:
                            if reject_connection:
                                try:
                                    reject_connection.close()
                                except:
                                    pass
                        
                        return False
                    
                    else:
                        # 9.3 普通失败：处理重试逻辑
                        success_result = False
                        
                        # 失败：检查是否为紧急停机
                        if 'emergency_stop' in result.get('message', '') or 'system紧急停机' in result.get('message', ''):
                            # 紧急停机：将订单重置为待处理状态（status=1已在第4471行提交，无法回滚）
                            self.logger.warning(f'⚠️ 订单{order_code}遇到紧急停机，重置为待处理状态: {result["message"]}')
                            sql = """
                                UPDATE orders_df 
                                SET status = 0, time_accept = NULL
                                WHERE code = %s AND status = 1
                            """
                            cur.execute(sql, (order_code,))
                            connection.commit()
                            self.logger.info(f'订单{order_code}已重置为待处理状态(status=0)')
                            success_result = False
                            return success_result
                        elif result.get('treat_as_success', True):  # 默认按成功处理
                            # 先增加重试次数
                            current_retry_count = order_data.get('retry_count', 0)
                            new_retry_count = current_retry_count + 1
                            
                            # 🔥 注释掉强制3次限制的旧代码（保留作为参考）
                            # if new_retry_count > 3:
                            #     # 重试次数超过3次，设置为异常按成功处理
                            #     sql = """
                            #         UPDATE orders_df 
                            #         SET status = 5, time_payed = NOW(), time_success = NOW(), retry_count = %s
                            #         WHERE code = %s
                            #     """
                            #     cur.execute(sql, (new_retry_count, order_code,))
                            #     connection.commit()
                            #     self.logger.info(f'订单{order_code}重试次数超过3次，异常按成功处理(status=5)，重试次数: {current_retry_count} -> {new_retry_count}')
                            #     
                            #     # 修改：重试次数超限按成功处理
                            #     # 但记录到订单冷却期Hash用于统计分析
                            #     updated_order_data = order_data.copy()
                            #     updated_order_data['retry_count'] = new_retry_count
                            #     
                            #     # 设置订单冷却期（包括没有可用账号的情况）
                            #     self.set_order_cooldown(
                            #         order_code, 
                            #         result.get('payment_id'),  # 可能为None，方法内部会处理
                            #         result.get('message', '重试次数超过3次'), 
                            #         updated_order_data, 
                            #         status=3,  # 3: 超限异常按成功处理
                            #         available_payment_ids=result.get('available_payment_ids', [])  # 传入匹配的payment_id列表
                            #     )
                            #     self.logger.info(f'订单{order_code}重试超限，记录到统计分析，不影响payment_id')
                            #     
                            #     success_result = True  # 异常按成功处理
                            # else:
                            
                            # 🔥 新增：检查重试次数是否超过8次
                            if new_retry_count > 8:
                                # 超过8次，设置为失败状态
                                sql = """
                                    UPDATE orders_df 
                                    SET status = 2, retry_count = %s
                                    WHERE code = %s AND status IN (0, 1)
                                """
                                cur.execute(sql, (new_retry_count, order_code,))
                                affected_rows = cur.rowcount
                                connection.commit()
                                
                                if affected_rows > 0:
                                    self.logger.error(
                                        f'订单{order_code}重试次数超过8次，设置为失败状态(status=2)，'
                                        f'重试次数: {current_retry_count} -> {new_retry_count}'
                                    )
                                else:
                                    self.logger.warning(f'订单{order_code}状态已不是0或1，可能已被其他进程处理为成功(status=3)，跳过更新')
                                    
                                    # 记录失败详情
                                    self.record_payment_failure(
                                        payment_id=payment_id,
                                        amount=order_data['amount'],
                                        to_account=order_data.get('payment_account', ''),
                                        reason=f"重试次数超过8次: {result.get('message', '')}",
                                        order_code=order_code
                                    )
                                
                                success_result = False
                                return success_result
                            
                            else:
                                # 未超过8次，继续重试
                                # 所有失败按成功处理的订单，更新重试次数并重新设为待处理状态，同时清除payment_id和partner_id
                                sql = """
                                    UPDATE orders_df 
                                    SET retry_count = %s, status = 0, time_accept = NULL, payment_id = NULL, partner_id = NULL
                                    WHERE code = %s AND status IN (0, 1)
                                """
                                cur.execute(sql, (new_retry_count, order_code,))
                                affected_rows = cur.rowcount
                                connection.commit()  # 提交更新
                                if affected_rows > 0:
                                    self.logger.info(f'订单{order_code}按成功处理但继续重试，重新设为待处理状态（已清除payment_id和partner_id），重试次数: {current_retry_count} -> {new_retry_count}')
                                else:
                                    self.logger.warning(f'订单{order_code}状态已不是0或1，可能已被其他进程处理为成功(status=3)，跳过更新')
                                
                                # 新增：所有按成功处理的失败都设置订单冷却期
                                failure_message = result.get('message', '')
                                # 更新订单数据的retry_count用于冷却期计算
                                updated_order_data = order_data.copy()
                                updated_order_data['retry_count'] = new_retry_count
                                
                                self.set_order_cooldown(
                                    order_code, 
                                    result.get('payment_id'),  # 可能为None，方法内部会处理
                                    failure_message, 
                                    updated_order_data, 
                                    status=1
                                )
                                self.logger.info(f'订单{order_code}按成功处理的失败，已设置冷却期: {failure_message}')
                                
                                success_result = False
                                return success_result  # 返回False
                        else:
                            # 真正的失败
                            current_retry_count = order_data.get('retry_count', 0)
                            new_retry_count = current_retry_count + 1
                            sql = """
                                UPDATE orders_df 
                                SET status = 2, retry_count = %s
                                WHERE code = %s AND status IN (0, 1)
                            """
                            cur.execute(sql, (new_retry_count, order_code,))
                            affected_rows = cur.rowcount
                            connection.commit()
                            if affected_rows > 0:
                                self.logger.error(f'订单{order_code}处理失败，事务已提交: {result["message"]}')
                            else:
                                self.logger.warning(f'订单{order_code}状态已不是0或1，可能已被其他进程处理为成功(status=3)，跳过更新')
                            
                            # 设置payment_id失败冷却期（只有当有payment_id时才设置）
                            if payment_id:
                                self.set_payment_id_failed(
                                    payment_id, 
                                    result.get('message', '处理失败'), 
                                    order_data, 
                                    status=1  # 1: 真正失败
                                )
                                
                                # 🔥 记录失败详情到统一Hash（用于重复订单检测）
                                self.record_payment_failure(
                                    payment_id=payment_id,
                                    amount=order_data['amount'],
                                    to_account=order_data.get('payment_account', ''),
                                    reason=result.get('message', '处理失败'),
                                    order_code=order_code
                                )
                            else:
                                self.logger.info(f'订单{order_code}真正失败但无payment_id（如无可用账号），跳过payment_id冷却期设置')
                            
                            # 注意：真正失败的订单不放入订单冷却期Hash，因为不会再重试
                            
                            success_result = False
                    
                    return success_result
                    
            except Exception as e:
                # 任何异常都需要重置订单状态（status=1已在第4471行提交，无法回滚）
                self.logger.error(f"订单{order_code}处理异常: {e}")
                tb_str = traceback.format_exc()
                self.logger.error(f"详细错误: {tb_str}")
                
                # 将订单标记为失败状态（status=2），保留time_accept用于追踪
                try:
                    with connection.cursor() as cur:
                        sql = """
                            UPDATE orders_df 
                            SET status = 2
                            WHERE code = %s AND status = 1
                        """
                        cur.execute(sql, (order_code,))
                        connection.commit()
                        self.logger.info(f'订单{order_code}异常后已标记为失败状态(status=2)，保留time_accept')
                except Exception as reset_e:
                    self.logger.error(f'订单{order_code}更新失败状态失败: {reset_e}')
                
                # 设置payment_id失败冷却期
                if payment_id:
                    # 在异常情况下，order_data可能不可用，所以只传递已知信息
                    order_info = {'code': order_code} if order_code else None
                    self.set_payment_id_failed(
                        payment_id, 
                        f"系统异常: {str(e)}", 
                        order_info, 
                        status=3  # 3: 系统异常
                    )
                    
                    # 🔥 记录失败详情到统一Hash（用于重复订单检测）
                    # 只有在order_data可用时才记录（防止异常发生在查询订单之前）
                    if order_data:
                        self.record_payment_failure(
                            payment_id=payment_id,
                            amount=order_data['amount'],
                            to_account=order_data.get('payment_account', ''),
                            reason=f"系统异常: {str(e)}",
                            order_code=order_code
                        )
                    
                return False
                
        except Exception as e:
            self.logger.error(f"处理订单{order_message}初始化异常: {e}")
            tb_str = traceback.format_exc()
            self.logger.error(f"详细错误: {tb_str}")
            return False
            
        finally:
            # 7. 释放所有锁和资源（倒序释放）
            if connection:
                try:
                    connection.close()
                except:
                    pass
            
            # 释放 payment_id 锁
            if payment_id_lock_value and payment_id:
                self.del_payment_id_lock(payment_id, payment_id_lock_value)
            
            # 释放账号锁
            if account_lock and account_id:
                self.release_account_lock(account_id, account_lock)
                    
            # 释放订单锁
            if order_lock_value and order_code:
                self.del_lock(order_code, order_lock_value)





# 主程序入口
if __name__ == "__main__":
    try:
        logger.info(f"{'=' * 10}EasyPaisa自动代付系统启动{'=' * 10}")
        auto_payout = EasyPaisaAutoPayout("ep_auto_payout")

        last_stats_time = time.time()
        no_success_rounds = 0

        while True:
            sleep_time = 2  # 默认值
            try:
                auto_payout.init_function(logger)
                success_count, processed_count = auto_payout.main()
                round_state = classify_round_state(success_count, processed_count)

                if round_state == "emergency_stop":
                    sleep_time = 10  # 紧急停机
                elif round_state == "success":
                    no_success_rounds = 0
                    sleep_time = 2
                elif round_state == "no_orders":
                    no_success_rounds = 0
                    sleep_time = 2  # 无订单，正常等待
                elif round_state == "no_available_accounts":
                    no_success_rounds += 1
                    sleep_time = min(2 ** no_success_rounds, 30)  # 序列: 2→4→8→16→30
                    logger.info(f"无可用账号，退避 {sleep_time}s（连续 {no_success_rounds} 轮）")
                else:
                    sleep_time = 5  # 有账号但全失败

                # 每分钟输出日志统计
                current_time = time.time()
                if current_time - last_stats_time >= 60:
                    stats = auto_payout.get_log_stats()
                    if stats:
                        logger.info(f"日志统计: {stats}")
                    last_stats_time = current_time
            except KeyboardInterrupt:
                logger.info("程序被用户中断")
                break
            except Exception as e:
                tb_str = traceback.format_exc()
                logger.error(f'main 循环错误: {e}\n{tb_str}')
                auto_payout.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
                sleep_time = 5
            finally:
                time.sleep(sleep_time)
    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f'main 程序启动错误: {e}\n{tb_str}')
    finally:
        if hasattr(file_handler, 'close'):
            file_handler.close()
        logger.info("EasyPaisa自动代付系统已停止")

# TODO: 后续优化方向 - 全队列重构
# 1. 将 EasyPaisa + JazzCash + PakistanPay 所有通道统一为生产者-消费者队列模型
# 2. 使用 aiomysql 替代 pymysql 的同步连接（MySQL 连接池）
# 3. 定时任务同步 payment 表状态到 Redis sorted set（清理幽灵账号）
# 4. 接入 Grafana 监控代付吞吐量和锁冲突指标
