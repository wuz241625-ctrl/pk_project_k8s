"""EasyPaisa自动代付系统 — 纯调度器（业务逻辑在 payout/ 子模块）"""
import os, sys, time, uuid, hashlib, asyncio, secrets, logging, traceback
import redis, pymysql
from typing import List, Dict

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(root_dir)

from config import get_config
from jobs.easypaisa.scheduling_state import (
    EMERGENCY_STOP, NO_AVAILABLE_ACCOUNTS, NO_ORDERS, classify_round_state)
from jobs.easypaisa.common.logging_setup import setup_high_performance_logging, TraceIDFilter
from jobs.easypaisa.payout.transaction_log import TransactionLogger
from jobs.easypaisa.payout.settlement import Settlement
from jobs.easypaisa.payout.account_selector import AccountSelector
from jobs.easypaisa.payout.transfer_executor import TransferExecutor
from jobs.easypaisa.payout.order_lifecycle import OrderLifecycle

logger, trace_id_filter, file_handler = setup_high_performance_logging("easypaisa_auto_payout")
conf = get_config()
EASYPAISA_API_URL = getattr(conf, 'easypaisa_api_url', 'http://34.150.42.92:83')
EASYPAISA_USER_ID = getattr(conf, 'easypaisa_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
EASYPAISA_SECRET_KEY = getattr(conf, 'easypaisa_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')
class EasyPaisaAutoPayout:
    def __init__(self, name):
        self.name = name
        self.lock_time = 120
        self.logger = logger
        self.log_handler = file_handler
        self.concurrent_limit = 20
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        self.REDIS_KEYS = {
            'easypaisa_balance_sorted_set': 'easypaisa_balance_sorted',
            'easypaisa_balance_prefix': 'easypaisa_balance:',
            'easypaisa_account_used_prefix': 'easypaisa_account_used:',
            'easypaisa_release_time': 'easypaisa_release_time',
            'easypaisa_failures': 'easypaisa_failures',
            'easypaisa_emergency_stop': 'easypaisa_emergency_stop',
            'grab_df_prefix': 'grab_df_',
            'easypaisa_account_lock_prefix': 'easypaisa_account_lock:',
            'payment_id_lock_prefix': 'payment_id_lock:',
            'payment_id_failed_prefix': 'payment_id_failed:',
            'easypaisa_order_cooldown_hash': 'easypaisa_order_cooldown',
            'easypaisa_order_cooldown_config': 'easypaisa_order_cooldown_config'
        }
        self._invalid_payment_cache = {}
        # 构造子模块
        self.transaction_logger = TransactionLogger(self.redis, self.logger, trace_id_filter, conf)
        self.settlement = Settlement(self.redis, self.logger, conf)
        self.account_selector = AccountSelector(
            self.redis, self.logger, conf, self.REDIS_KEYS,
            EASYPAISA_API_URL, EASYPAISA_USER_ID, EASYPAISA_SECRET_KEY)
        self.transfer_executor = TransferExecutor(
            self.redis, self.logger, conf, self.REDIS_KEYS,
            EASYPAISA_API_URL, EASYPAISA_USER_ID, EASYPAISA_SECRET_KEY,
            self.transaction_logger, self.account_selector)
        self.order_lifecycle = OrderLifecycle(
            self.redis, self.logger, conf, self.REDIS_KEYS,
            self.account_selector, self.transfer_executor,
            self.settlement, self.transaction_logger)

    def get_log_stats(self):
        if hasattr(self.log_handler, 'get_stats'):
            return self.log_handler.get_stats()
        if hasattr(self.log_handler, 'buffer'):
            return {'buffer_size': len(self.log_handler.buffer),
                    'buffer_bytes': getattr(self.log_handler, 'buffer_bytes', 0),
                    'is_running': not getattr(self.log_handler, '_shutdown', False)}
        return None

    def init_function(self, exist_logger):
        try:
            self.logger = exist_logger
            self.check_redis_connection()
        except Exception as e:
            self.logger.error(f'init_function error: {e}\n{traceback.format_exc()}')
    init_function_v2 = init_function

    def check_redis_connection(self):
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
            busy_key = f'{self.name}_operate_{_id}'
            _value = secrets.token_hex(8)
            if not self.redis.setnx(busy_key, _value):
                _ttl = self.redis.ttl(busy_key)
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                return False
            self.redis.expire(busy_key, self.lock_time)
            return _value
        except Exception as e:
            self.logger.error(f'get_lock error {_id}: {e}')
            return False

    def del_lock(self, _id, value):
        try:
            busy_key = f'{self.name}_operate_{_id}'
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == value:
                self.redis.delete(busy_key)
            return True
        except Exception as e:
            self.logger.error(f'del_lock error {_id}: {e}')
            return False

    def get_active_processes_count(self):
        try:
            process_key = "active_processes_auto_payout"
            self.redis.setex(f"{process_key}:{os.getpid()}", 30, int(time.time()))
            pids = sorted(int(k.decode().split(':')[-1])
                          for k in self.redis.keys(f"{process_key}:*")
                          if k.decode().split(':')[-1].isdigit())
            idx = pids.index(os.getpid()) if os.getpid() in pids else 0
            return len(pids), idx
        except Exception as e:
            self.logger.error(f"获取活跃进程失败: {e}")
            return 1, 0

    def get_process_allocated_members(self, members: List[bytes]) -> List[bytes]:
        if not members:
            return []
        total, idx = self.get_active_processes_count()
        if total <= 1:
            return members
        allocated = [m for m in members
                     if int(hashlib.md5(m.decode().encode()).hexdigest(), 16) % total == idx]
        self.logger.info(f"进程{os.getpid()} (索引:{idx}/{total}) 分配到 {len(allocated)}/{len(members)} 个")
        return allocated

    def main(self):
        """主处理循环——预分配调度模式"""
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"
            emergency_stop = self.redis.get("easypaisa_emergency_stop")
            if emergency_stop is not None and emergency_stop != b"0" and emergency_stop != "0":
                self.logger.warning(f"检测到紧急停机状态（值：{emergency_stop}）")
                return (0, EMERGENCY_STOP)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                orders = loop.run_until_complete(self.get_pending_orders_by_time())
                if not orders:
                    self.logger.info("暂无待处理订单")
                    return (0, NO_ORDERS)
                self.logger.info(f"数据库轮询发现 {len(orders)} 个待处理订单")
                members = [f"{o['code']}_{o['amount']}".encode() for o in orders]
                allocated_members = self.get_process_allocated_members(members)
                if not allocated_members:
                    self.logger.info(f"进程{os.getpid()} 没有分配到订单")
                    return (0, NO_ORDERS)
                allocated_codes = {m.decode().split('_')[0] for m in allocated_members}
                allocated_orders = [o for o in orders if o['code'] in allocated_codes]
                available_accounts = loop.run_until_complete(
                    self.account_selector.get_real_available_accounts(allocated_orders))
                if not available_accounts:
                    self.logger.warning(f"预分配：无可用账号，{len(allocated_orders)}个订单等待下轮")
                    return (0, NO_AVAILABLE_ACCOUNTS)
                batches = self.account_selector.dispatch_orders_to_accounts(allocated_orders, available_accounts)
                if not batches:
                    self.logger.warning("预分配：分配结果为空")
                    return (0, NO_AVAILABLE_ACCOUNTS)
                success_count, total_count = loop.run_until_complete(
                    self.process_members_concurrent(account_order_batches=batches))
                return (success_count, total_count)
            except Exception as e:
                self.logger.error(f"预分配处理失败: {e}")
                return (0, NO_AVAILABLE_ACCOUNTS)
            finally:
                if loop and not loop.is_closed():
                    loop.close()
        except Exception as e:
            logging.error(f'main过程错误: {e}\n{traceback.format_exc()}')
            return (0, NO_AVAILABLE_ACCOUNTS)

    async def get_pending_orders_by_time(self) -> List[Dict]:
        """获取按时间排序的待处理订单"""
        connection = None
        try:
            connection = pymysql.connect(
                host=conf['mysql_host'], user=conf['mysql_user'],
                password=conf['mysql_password'], database=conf['mysql_database'],
                charset='utf8mb4', autocommit=False)
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT code, amount, payment_id, payment_account,
                           payment_name, remark, time_create, retry_count
                    FROM orders_df
                    WHERE status = 0 AND time_create >= DATE_SUB(NOW(), INTERVAL 3 DAY)
                    ORDER BY time_create ASC LIMIT 100""")
                cols = ['code', 'amount', 'payment_id', 'payment_account',
                        'payment_name', 'remark', 'time_create', 'retry_count']
                orders = [dict(zip(cols, row)) for row in cur.fetchall()]
                for o in orders:
                    o['amount'] = float(o['amount'])
            self.logger.info(f"从数据库获取到 {len(orders)} 个待处理订单")
            if orders:
                filtered = self.order_lifecycle.filter_cooldown_orders(orders)
                diff = len(orders) - len(filtered)
                if diff > 0:
                    self.logger.info(f"过滤掉 {diff} 个冷却期内的订单，剩余 {len(filtered)} 个可处理")
                return filtered
            return orders
        except Exception as e:
            self.logger.error(f"获取待处理订单失败: {e}")
            return []
        finally:
            if connection:
                connection.close()

    async def process_members_concurrent(self, account_order_batches=None, members=None, concurrent_limit=20):
        """并发处理订单（预分配模式）"""
        if not account_order_batches:
            if members:
                self.logger.warning("EasyPaisa legacy members 模式已退役，跳过 %s 个旧消息", len(members))
            return (0, 0)

        async def _process_batch(account, orders):
            success = 0
            pid = account['payment_id']
            try:
                for i, order in enumerate(orders):
                    if i > 0 and not self.account_selector.check_account_release_time(pid):
                        self.logger.info(f"账号{pid}已进入冷却期，剩余{len(orders)-i}个订单留给下轮")
                        break
                    try:
                        result = await self.order_lifecycle.process_payout_order(order, selected_account=account)
                        if result and result.get('success'):
                            success += 1
                    except Exception as e:
                        self.logger.error(f"订单{order['code']}处理异常: {e}")
            except Exception as e:
                self.logger.error(f"账号{pid}批量处理异常: {e}")
            return success

        tasks = [_process_batch(acct, ords) for acct, ords in account_order_batches]
        total_count = sum(len(ords) for _, ords in account_order_batches)
        t0 = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - t0
        success_count = sum(r for r in results if isinstance(r, int))
        error_count = sum(1 for r in results if isinstance(r, Exception))
        self.logger.info(
            f"进程{os.getpid()} 并发处理完成: 总数{total_count} 成功{success_count} "
            f"失败{total_count-success_count} 异常{error_count} "
            f"账号数{len(account_order_batches)} 耗时{elapsed:.2f}s")
        return (success_count, total_count)

if __name__ == "__main__":
    try:
        logger.info("==========EasyPaisa自动代付系统启动==========")
        auto_payout = EasyPaisaAutoPayout("ep_auto_payout")
        last_stats_time = time.time()
        no_success_rounds = 0
        while True:
            sleep_time = 2
            try:
                auto_payout.init_function(logger)
                success_count, processed_count = auto_payout.main()
                state = classify_round_state(success_count, processed_count)
                if state == "emergency_stop":
                    sleep_time = 10
                elif state == "success":
                    no_success_rounds = 0
                elif state == "no_orders":
                    no_success_rounds = 0
                elif state == "no_available_accounts":
                    no_success_rounds += 1
                    sleep_time = min(2 ** no_success_rounds, 30)
                else:
                    sleep_time = 5
                if time.time() - last_stats_time >= 60:
                    stats = auto_payout.get_log_stats()
                    if stats:
                        logger.info(f"日志统计: {stats}")
                    last_stats_time = time.time()
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f'main loop error: {e}\n{traceback.format_exc()}')
                auto_payout.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
                sleep_time = 5
            finally:
                time.sleep(sleep_time)
    except Exception as e:
        logger.error(f'startup error: {e}\n{traceback.format_exc()}')
    finally:
        if hasattr(file_handler, 'close'):
            file_handler.close()
        logger.info("EasyPaisa自动代付系统已停止")
