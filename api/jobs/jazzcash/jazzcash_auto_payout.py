"""
JazzCash自动代付系统 — Pure Orchestrator
Instantiates focused modules and delegates all work.
Refactored from 5069-line God Class into 5 modules + this orchestrator.
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
import traceback
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional

# 将项目的主目录添加进系统path
root_dir = os.path.dirname(__file__)  # jobs/jazzcash
root_dir = os.path.dirname(root_dir)  # jobs
root_dir = os.path.dirname(root_dir)  # api根目录
sys.path.append(root_dir)

from config import get_config
from jobs.common.logging_setup import ProgramLogger, TraceIDFilter, setup_high_performance_logging
from jobs.common.db import DBConnection
from jobs.auto_payout_state import is_auto_payout_enabled

# Payout modules
from jobs.jazzcash.payout import Settlement, TransactionLogger, AccountSelector, TransferExecutor, OrderLifecycle

# 程序名称（用于日志）
PROGRAM_NAME = 'jazzcash_auto_payout'

# 初始化日志系统
logger, trace_id_filter, file_handler = setup_high_performance_logging(PROGRAM_NAME, use_async=True)

conf = get_config()


# ========== JazzCash自动代付系统 ==========
class JazzCashAutoPayout:
    def __init__(self, name):
        self.name = name
        # Redis键名定义
        self.list_key = f"list_{name}"
        self.hash_key = f"hash_{name}"
        self.set_key = f"set_{name}"

        # 系统配置参数
        self.lock_time = 120  # 操作锁的锁定时间（秒）

        # 系统组件
        self.logger = logger
        self.local_mock = False
        self.log_handler = file_handler

        # 连接Redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

        # 系统配置
        self.concurrent_limit = 20

        # Redis键名配置
        self.REDIS_KEYS = {
            'jazzcash_account_used_prefix': 'jazzcash_account_used:',
            'jazzcash_release_time': 'jazzcash_release_time',
            'jazzcash_failures': 'jazzcash_failures',
            'grab_df_prefix': 'grab_df_',
            'jazzcash_account_lock_prefix': 'jazzcash_account_lock:',
            'payment_id_lock_prefix': 'payment_id_lock:',
            'payment_id_failed_prefix': 'payment_id_failed_jazzcash:',
        }

        self.qr_id = None

        # Module config dict passed to all modules
        module_config = {
            'redis_keys': self.REDIS_KEYS,
            'lock_time': self.lock_time,
            'jazzcash_api_url': conf.get('jazzcash_api_url', 'http://34.150.42.92:84'),
            'jazzcash_user_id': conf.get('jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36'),
            'jazzcash_secret_key': conf.get('jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de'),
            'db': DBConnection(conf),
        }

        # Instantiate modules
        self.transfer_executor = TransferExecutor(self.redis, self.logger, module_config)
        self.settlement = Settlement(self.redis, self.logger, module_config)
        self.transaction_logger = TransactionLogger(self.redis, self.logger, module_config, trace_id_filter)
        self.account_selector = AccountSelector(self.redis, self.logger, module_config)
        self.order_lifecycle = OrderLifecycle(
            self.redis, self.logger, module_config,
            settlement=self.settlement,
            transfer_executor=self.transfer_executor,
            account_selector=self.account_selector,
            transaction_logger=self.transaction_logger,
        )

        # Wire cross-module references
        self.transaction_logger.set_transfer_executor(self.transfer_executor)
        self.settlement.account_selector = self.account_selector
        self.transfer_executor.account_selector = self.account_selector
        self.transfer_executor.transaction_logger = self.transaction_logger
        self.account_selector.transfer_executor = self.transfer_executor

    def get_log_stats(self):
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

    def get_cache_result(self, table, keys, condition=None):
        """获取缓存数据 — delegates to settlement"""
        return self.settlement.get_cache_result(table, keys, condition)

    def init_function(self, exist_logger):
        """初始化函数"""
        try:
            self.logger = exist_logger
            self.local_mock = False
            self.check_redis_connection()
        except Exception as e:
            tb_str = traceback.format_exc()
            self.logger.error('init_function 脚本运行错误{}\n{}\n'.format(e, tb_str))

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
        """获取操作锁（orchestrator级别）"""
        try:
            busy_key = '{}_operate_{}'.format(self.name, _id)
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value)
            if not _lock:
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
            self.logger.error('get_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, tb_str))
            return False

    def del_lock(self, _id, value):
        """删除操作锁"""
        try:
            busy_key = '{}_operate_{}'.format(self.name, _id)
            self.logger.info(f"准备删除Lock {busy_key}")
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(busy_key)
                self.logger.info(f"删除Lock {busy_key}, result: {result}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            self.logger.error('del_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, tb_str))
            return False

    def get_active_processes_count(self):
        """获取当前活跃进程数量"""
        try:
            process_key = "active_processes_auto_payout"
            current_process_id = f"{process_key}:{os.getpid()}"
            self.redis.setex(current_process_id, 30, int(time.time()))

            active_processes = self.redis.keys(f"{process_key}:*")
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

        allocated_members = []
        active_processes = self.redis.keys("active_processes_auto_payout:*")
        active_pids = []
        for key in active_processes:
            try:
                pid = int(key.decode().split(':')[-1])
                active_pids.append(pid)
            except:
                continue
        active_pids.sort()
        self.logger.info(f"活跃进程PIDs: {active_pids}, 当前PID: {os.getpid()}")

        for member in members:
            member_id = member.decode()
            hash_value = int(hashlib.md5(member_id.encode()).hexdigest(), 16)
            assigned_index = hash_value % total_processes
            if assigned_index == current_index:
                allocated_members.append(member)

        self.logger.info(f"进程 {os.getpid()} (索引:{current_index}/{total_processes}) "
                         f"从 {len(members)} 个成员中分配到 {len(allocated_members)} 个")
        return allocated_members

    async def process_members_concurrent(self, members: List[bytes], concurrent_limit: int = 20):
        """并发处理订单members"""
        if not members:
            return

        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(member):
            async with semaphore:
                order_message = member.decode()
                return await self.order_lifecycle.process_single_order_async(order_message)

        tasks = [process_with_semaphore(member) for member in members]
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(f"进程 {os.getpid()} 并发处理完成: "
                         f"总数 {len(members)}, 成功 {success_count}, 失败 {len(results) - success_count}, "
                         f"异常 {error_count}, 耗时 {end_time - start_time:.2f}秒")

    def main(self):
        """主处理循环"""
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"

            if not is_auto_payout_enabled(conf, self.logger):
                self.logger.warning("检测到MySQL自动代付开关关闭，停止所有订单处理")
                time.sleep(10)
                return

            # 数据库轮询获取待处理订单
            orders = asyncio.run(self.order_lifecycle.get_pending_orders_by_time())

            if not orders:
                self.logger.info("数据库中暂无待处理订单")
                time.sleep(2)
                return

            self.logger.info(f"数据库轮询发现 {len(orders)} 个待处理订单")

            # 转换为member格式
            members = [f"{order['code']}_{order['amount']}".encode() for order in orders]

            # 根据进程数量分配
            allocated_members = self.get_process_allocated_members(members)
            if not allocated_members:
                self.logger.info(f"进程 {os.getpid()} 没有分配到需要处理的订单")
                time.sleep(2)
                return

            # 并发处理
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.process_members_concurrent(allocated_members, concurrent_limit=20))
            except Exception as e:
                self.logger.error(f"并发处理失败: {e}")
            finally:
                if loop and not loop.is_closed():
                    loop.close()

        except Exception as e:
            tb_str = traceback.format_exc()
            logging.error('main过程错误： 错误详情：{}\n{}'.format(e, tb_str))

    def init_function_v2(self, exist_logger):
        """初始化函数v2"""
        try:
            self.logger = exist_logger
            self.check_redis_connection()
            self.logger.debug("init_function 初始化完成")
        except Exception as e:
            tb_str = traceback.format_exc()
            self.logger.error('init_function 脚本运行错误{}\n{}\n'.format(e, tb_str))


if __name__ == "__main__":
    try:
        logger.info(f"{'=' * 10}JazzCash自动代付系统启动{'=' * 10}")
        bank = JazzCashAutoPayout("jazzcash_auto_payout")

        last_stats_time = time.time()
        while True:
            try:
                bank.init_function_v2(logger)
                bank.main()

                current_time = time.time()
                if current_time - last_stats_time >= 60:
                    stats = bank.get_log_stats()
                    if stats:
                        logger.info(f"日志系统统计: {json.dumps(stats, ensure_ascii=False)}")
                    last_stats_time = current_time
            except KeyboardInterrupt:
                logger.info("程序被用户中断")
                break
            except Exception as e:
                logger.error(f"main 循环程序运行错误: {e}\n{traceback.format_exc()}")
                bank.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            finally:
                time.sleep(0.1)
    except Exception as e:
        logger.error(f"main 程序启动错误: {e}\n{traceback.format_exc()}")
    finally:
        if hasattr(file_handler, 'close'):
            file_handler.close()
