import os
import sys
import time
import uuid
import json
import aiohttp
import redis
import asyncio
import hashlib
import logging
import requests
import simplejson
import threading
import traceback

import base64

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

# API_URL = 'http://104.198.86.150:83'
# USER_ID = 'ba08c3c0e4f546ad92dd2c2e8542ca36'
# SECRET_KEY = 'ca45b35e132b46b9b68dd55f1ab077de'

# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

import config
from jobs.common.db import DBConnection
from jobs.easypaisa.wallet_status_service import WorkerWalletStatusService
from datetime import datetime, timedelta

# EasyPaisa 账单 worker：MySQL 订单窗口调度，Redis 不再作为钱包状态或旧队列来源。

from jobs.easypaisa.common import ProgramLogger, RedisClient
from jobs.easypaisa.common.logging_setup import setup_high_performance_logging, TraceIDFilter

# 初始化日志系统
logger, trace_id_filter, file_handler = setup_high_performance_logging("pakistanpay_v2", log_dir=current_dir, use_async=True)


conf = config.get_config()

# 配置参数
API_URL = conf['easypaisa_api_url']
USER_ID = conf['easypaisa_user_id']
SECRET_KEY = conf['easypaisa_secret_key']


def _conf_int(key: str, default: int) -> int:
    try:
        return int(conf.get(key, default))
    except Exception:
        return default


def _conf_bool(key: str, default: bool = False) -> bool:
    value = conf.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


class BankLogin:
    def __init__(self, name):
        self.name = name
        self.lock_time = _conf_int("easypaisa_operate_lock_time", 30)
        self.statement_ds_window_seconds = _conf_int("easypaisa_statement_ds_window_seconds", 7 * 60)
        self.statement_df_window_seconds = _conf_int("easypaisa_statement_df_window_seconds", 10 * 60)
        self.statement_df_probe_interval = _conf_int("easypaisa_statement_df_probe_interval", 2 * 60)
        self.enable_payout_observation = _conf_bool("easypaisa_enable_payout_observation", True)
        self.statement_scan_lock_ttl = _conf_int("easypaisa_statement_scan_lock_ttl", 55)
        self.query_bill_fail_threshold = _conf_int("easypaisa_query_bill_fail_threshold", 3)
        self.query_bill_fail_ttl = _conf_int("easypaisa_query_bill_fail_ttl", 300)
        self.query_bill_timeout = _conf_int("easypaisa_query_bill_timeout", 30)
        self.callback_lock_ttl = _conf_int("easypaisa_collection_callback_lock_ttl", 5 * 60)
        self.internal_callback_host = (
            os.environ.get('API_INTERNAL_CALLBACK_HOST')
            or conf.get('internal_callback_host')
            or 'http://127.0.0.1:9000'
        )
        self.logger = logger
        # 如果使用异步日志处理器，可以定期检查状态
        self.log_handler = file_handler

        # 连接redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        self.redis_client = RedisClient({'redis_host': conf['redis_host'], 'redis_port': 6379})
        self.db = DBConnection(conf)
        self._db_lock = threading.RLock()
        self.db_connection = self.check_db_connection()
        self.wallet_status_service = self._new_wallet_status_service()
    
    def check_db_connection(self):
        """通过统一 DBConnection 获取同步 worker 的 MySQL 连接。"""
        try:
            if not getattr(self, "db", None):
                self.db = DBConnection(conf)
            connection = self.db.connection
            self.logger.info("数据库连接成功")
            return connection
        except Exception as e:
            self.logger.error(f"数据库连接失败: {e}", exc_info=True)
            return None

    def _new_wallet_status_service(self):
        if not getattr(self, "db_connection", None):
            return None
        return WorkerWalletStatusService(self.db_connection, self.logger, redis_client=self.redis)

    def get_wallet_status_service(self):
        with self._db_lock:
            if not hasattr(self, "db_connection"):
                return None
            if not getattr(self, "db_connection", None) or not self.db_connection.open:
                self.logger.error("数据库连接已关闭，尝试重新连接...")
                self.db_connection = self.check_db_connection()
                self.wallet_status_service = self._new_wallet_status_service()
            if not getattr(self, "wallet_status_service", None):
                self.wallet_status_service = self._new_wallet_status_service()
            return self.wallet_status_service

    def mark_wallet_account_invalid(self, account_context, reason):
        payment_id = account_context.get('id') if isinstance(account_context, dict) else None
        if not payment_id:
            return 0
        try:
            wallet_status_service = self.get_wallet_status_service()
            if not wallet_status_service:
                return 0
            with self._db_lock:
                return wallet_status_service.mark_account_invalid(payment_id, reason)
        except Exception as e:
            self.logger.error(f"easypaisa {payment_id} 标记501账号无效失败: {e}", exc_info=True)
            return 0

    def get_health_monitor(self):
        if not hasattr(self, "_health_monitor") or self._health_monitor is None:
            from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor
            self._health_monitor = AutoPayoutMonitor("ep_monitor")
            self._health_monitor.logger = self.logger
        return self._health_monitor

    async def run_health_balance_check(self):
        """复用 EasyPaisa monitor 做余额和限额健康检查。"""
        monitor = self.get_health_monitor()
        await monitor.run_easypaisa_monitor_check()
        return True

    def acquire_health_balance_check_lock(self):
        key = "easypaisa_health_balance_check_lock"
        try:
            interval = max(1, _conf_int("easypaisa_health_balance_interval", 30))
            return bool(self.redis.set(key, 1, nx=True, ex=interval))
        except Exception as e:
            self.logger.error(f"EasyPaisa 健康余额检查锁获取失败: {e}")
            return False

    def run_health_balance_check_once(self):
        if not self.acquire_health_balance_check_lock():
            self.logger.info("EasyPaisa 健康余额检查仍在节流窗口内，本轮跳过")
            return False

        loop = None
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self.run_health_balance_check())
        except Exception as e:
            self.logger.error(f"EasyPaisa 健康余额检查失败: {e}\n{traceback.format_exc()}")
            return False
        finally:
            if loop and not loop.is_closed():
                loop.close()

    def fetch_wallet_status_reconcile_rows(self, limit=50):
        with self._db_lock:
            if not self._ensure_db_connection():
                return []
            with self.db_connection.cursor() as cur:
                try:
                    sql = """
                        SELECT id, wallet_status, account_accno, phone
                        FROM payment
                        WHERE (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
                          AND (
                            (wallet_status = 1 AND (account_accno IS NULL OR account_accno = ''))
                            OR (wallet_status = 0 AND account_accno IS NOT NULL AND account_accno <> '')
                          )
                        LIMIT {limit}
                    """.format(limit=int(limit))
                    cur.execute(sql)
                    return cur.fetchall() or []
                except Exception as e:
                    self.logger.error(f"查询 EasyPaisa wallet_status 纠偏候选失败: {e}", exc_info=True)
                    self.db_connection.rollback()
                    return []
                finally:
                    self.db_connection.commit()

    def confirm_wallet_available(self, row):
        payment_id = row.get("id")
        phone = str(row.get("phone") or "").strip()
        account_accno = str(row.get("account_accno") or "").strip()
        if not phone or not account_accno:
            return False

        payload = {
            "id": str(uuid.uuid4()),
            "action": "queryBill",
            "payload": {"account_id": phone, "accno": account_accno},
        }
        payload_str = json.dumps(payload, separators=(',', ':'))
        data_base64 = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
        sign = hashlib.md5((data_base64 + SECRET_KEY).encode('utf-8')).hexdigest()
        request_data = {'user_id': USER_ID, 'data': data_base64, 'sign': sign}

        try:
            response = requests.post(API_URL, data=request_data, timeout=10)
            if response.status_code != 200:
                self.logger.warning(f"EasyPaisa wallet_status 确认失败 payment_id={payment_id}, HTTP={response.status_code}")
                return False
            response_data = response.json()
            if response_data.get("code") == 200:
                return True
            self.logger.warning(
                f"EasyPaisa wallet_status 确认失败 payment_id={payment_id}, code={response_data.get('code')}, msg={response_data.get('msg')}"
            )
            return False
        except Exception as e:
            self.logger.warning(f"EasyPaisa wallet_status 确认异常 payment_id={payment_id}: {e}")
            return False

    def reconcile_wallet_status_from_mysql(self):
        service = self.get_wallet_status_service()
        if not service:
            return {"confirm": 0, "offline": 0, "noop": 0}

        stats = {"confirm": 0, "offline": 0, "noop": 0}
        for row in self.fetch_wallet_status_reconcile_rows():
            action = WorkerWalletStatusService.reconcile_wallet_status_row(row)
            if action == "offline":
                with self._db_lock:
                    service.mark_offline(row["id"], "account_selection_cleared")
                stats["offline"] += 1
            elif action == "confirm":
                throttle_key = f"easypaisa_wallet_status_confirm:{row['id']}"
                if self.redis.get(throttle_key):
                    stats["noop"] += 1
                    continue
                self.redis.setex(throttle_key, 300, 1)
                if self.confirm_wallet_available(row):
                    with self._db_lock:
                        service.mark_available(row["id"], "upstream_confirmed")
                    stats["confirm"] += 1
                else:
                    stats["noop"] += 1
            else:
                stats["noop"] += 1
        return stats

    def _read_statement_wallet_status(self, payment_id):
        with self._db_lock:
            if not self._ensure_db_connection():
                return None
            with self.db_connection.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT id, wallet_status
                        FROM payment
                        WHERE id = %s
                        """,
                        (payment_id,),
                    )
                    return cur.fetchone()
                except Exception as e:
                    self.logger.error(f"查询 EasyPaisa wallet_status 失败 payment_id={payment_id}: {e}", exc_info=True)
                    self.db_connection.rollback()
                    return None
                finally:
                    self.db_connection.commit()

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
            self.logger = exist_logger
            self.check_redis_connection()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('init_function 脚本运行错误{}\n{}\n'.format(e, error_message))

    def check_redis_connection(self):
        """检查Redis连接"""
        self.redis_client.check_connection()
        self.redis = self.redis_client.redis

    def get_lock(self, _id):
        try:
            value = self.redis_client.get_lock(self.name, _id, self.lock_time)
            if value:
                self.logger.info(f"{_id}, {self.name}_operate_{_id} 加锁时间 {self.lock_time} s, _value: {value}")
            else:
                busy_key = f'{self.name}_operate_{_id}'
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{_id}, {busy_key} 剩余生存时间 {_ttl} s")
            return value if value else False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, error_message))
            return False

    def del_lock(self, _id, value):
        try:
            busy_key = f'{self.name}_operate_{_id}'
            self.logger.info(f"准备删除Lock {busy_key}")
            result = self.redis_client.del_lock(self.name, _id, value)
            self.logger.info(f"删除Lock {busy_key}, result: {result}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('del_lock 脚本运行错误{}\n{}\n{}'.format(_id, e, error_message))
            return False

    def _ensure_db_connection(self):
        if not hasattr(self, "db_connection"):
            return False
        if not getattr(self, "db_connection", None) or not self.db_connection.open:
            self.logger.error("数据库连接已关闭，尝试重新连接...")
            self.db_connection = self.check_db_connection()
            self.wallet_status_service = self._new_wallet_status_service()
        return bool(getattr(self, "db_connection", None))

    def _fetch_rows(self, sql, params=None):
        with self._db_lock:
            if not self._ensure_db_connection():
                return []
            with self.db_connection.cursor() as cur:
                try:
                    cur.execute(sql, params)
                    return cur.fetchall()
                except Exception as e:
                    self.logger.error(f"查询 EasyPaisa 账单调度候选失败: {e}", exc_info=True)
                    self.db_connection.rollback()
                    return []
                finally:
                    self.db_connection.commit()

    def _execute_update(self, sql, params=None):
        with self._db_lock:
            if not self._ensure_db_connection():
                return 0
            with self.db_connection.cursor() as cur:
                try:
                    affected = cur.execute(sql, params)
                    self.db_connection.commit()
                    return affected
                except Exception as e:
                    self.logger.error(f"执行 EasyPaisa MySQL 更新失败: {e}", exc_info=True)
                    self.db_connection.rollback()
                    return 0

    def _is_statement_wallet_enabled(self, payment_id):
        payment = self._read_statement_wallet_status(payment_id)
        try:
            return int((payment or {}).get("wallet_status") or 0) == 1
        except Exception:
            self.logger.error(f"EasyPaisa wallet_status 字段异常 payment_id={payment_id}: {payment}")
            return False

    def fetch_due_statement_scan_context(self, payment_id):
        context = {"payment_id": payment_id, "ds_orders": [], "df_orders": [], "has_due": False, "interval": 60}
        if not self._is_statement_wallet_enabled(payment_id):
            self.logger.info(f"EasyPaisa {payment_id} wallet_status!=1，跳过订单驱动账单爬取")
            return context

        ds_sql = """
            SELECT code, payment_id, partner_id, amount, time_create
            FROM orders_ds
            WHERE payment_id = %s
              AND status IN (1, 2)
              AND time_create >= DATE_SUB(NOW(), INTERVAL 7 MINUTE)
            ORDER BY id DESC
            LIMIT 20
        """
        df_sql = """
            SELECT code, payment_id, partner_id, amount, time_accept, payment_account, utr
            FROM orders_df
            WHERE payment_id = %s
              AND status = 2
              AND time_accept IS NOT NULL
              AND time_accept >= DATE_SUB(NOW(), INTERVAL 10 MINUTE)
            ORDER BY id DESC
            LIMIT 20
        """
        context["ds_orders"] = self._fetch_rows(ds_sql, (payment_id,))
        context["df_orders"] = self._fetch_rows(df_sql, (payment_id,))
        context["has_due"] = bool(context["ds_orders"] or context["df_orders"])
        context["interval"] = self.statement_df_probe_interval if context["df_orders"] and not context["ds_orders"] else 60
        return context

    def fetch_due_statement_payment_ids(self, limit=200):
        rows = self._fetch_rows(
            """
            SELECT DISTINCT id
            FROM (
                SELECT p.id
                FROM payment p
                JOIN orders_ds od ON od.payment_id = p.id
                WHERE p.wallet_status = 1
                  AND (p.bank_type = 97 OR p.bank_type = '97' OR p.bank_type_id = 97)
                  AND od.status IN (1, 2)
                  AND od.time_create >= DATE_SUB(NOW(), INTERVAL 7 MINUTE)
                UNION
                SELECT p.id
                FROM payment p
                JOIN orders_df ofd ON ofd.payment_id = p.id
                WHERE p.wallet_status = 1
                  AND (p.bank_type = 97 OR p.bank_type = '97' OR p.bank_type_id = 97)
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

    def fetch_statement_account_context(self, payment_id):
        rows = self._fetch_rows(
            """
            SELECT id, phone, partner_id, account_accno
            FROM payment
            WHERE id = %s
              AND wallet_status = 1
              AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
            LIMIT 1
            """,
            (payment_id,),
        )
        if not rows:
            self.logger.info(f"EasyPaisa {payment_id} MySQL 无可用采集账号上下文，跳过账单查询")
            return None
        account_context = dict(rows[0])
        account_context["id"] = payment_id
        account_context["real_payment_id"] = payment_id
        account_context["status"] = "grabstatement"
        return account_context

    def reserve_due_statement_scan_context(self, context):
        reserved = dict(context)
        reserved_df_orders = []
        if not self.enable_payout_observation:
            reserved["df_orders"] = []
            reserved["has_due"] = bool(reserved.get("ds_orders"))
            return reserved
        for order in context.get("df_orders", []):
            code = order.get("code")
            if not code:
                continue
            lock_key = f"payout_unknown_probe_lock:{self.name}:{code}"
            try:
                if self.redis.set(lock_key, 1, nx=True, ex=max(1, int(self.statement_df_probe_interval))):
                    reserved_df_orders.append(order)
                else:
                    self.logger.info(f"EasyPaisa 代付未知订单 {code} 两分钟探测锁未释放，跳过本轮账单观测")
            except Exception as e:
                self.logger.warning(f"EasyPaisa 代付未知订单 {code} 观测锁写入失败，保守加入本轮观测: {e}")
                reserved_df_orders.append(order)
        reserved["df_orders"] = reserved_df_orders
        reserved["has_due"] = bool(reserved.get("ds_orders") or reserved_df_orders)
        return reserved

    def acquire_statement_wallet_lock(self, payment_id, ttl):
        lock_key = f"statement_scan_lock:{self.name}:{payment_id}"
        try:
            ok = self.redis.set(lock_key, 1, nx=True, ex=max(1, int(ttl)))
            if not ok:
                self.logger.info(f"EasyPaisa {payment_id} 账单爬取锁未释放，跳过本轮")
                return False
            return True
        except Exception as e:
            self.logger.error(f"EasyPaisa {payment_id} 账单爬取锁获取失败: {e}", exc_info=True)
            return False

    @staticmethod
    def _to_money(value) -> Optional[Decimal]:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _money_to_callback(value: Optional[Decimal]) -> str:
        if value is None:
            return "0.00"
        return format(value, "f")

    @staticmethod
    def _parse_statement_time(value):
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        value = str(value).strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %I:%M:%S %p", "%d-%m-%Y %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _digits(value) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @classmethod
    def _normalize_msisdn(cls, value) -> str:
        number = cls._digits(value)
        while number.startswith("92"):
            number = number[2:]
        while number.startswith("0"):
            number = number[1:]
        return number

    @staticmethod
    def _strip_ac_prefix(value) -> str:
        value = str(value or "").strip()
        if value.upper().startswith("AC"):
            return value[2:].strip()
        return value

    @staticmethod
    def _mask(value, keep_left=3, keep_right=3) -> str:
        value = str(value or "")
        if len(value) <= keep_left + keep_right:
            return "***" if value else ""
        return f"{value[:keep_left]}***{value[-keep_right:]}"

    def _extract_statement_ref(self, transaction: Dict[str, Any], detail_dto: Dict[str, Any]) -> str:
        for key in ("orderNo", "transactionId", "transId", "rrn", "utr"):
            value = transaction.get(key)
            if value:
                return str(value).strip()
        for key in ("extOrderNo", "orderNo", "transactionId", "transId"):
            value = detail_dto.get(key)
            if value:
                return str(value).strip()
        return ""

    def _extract_payer_callback_utr(self, transaction: Dict[str, Any], detail_dto: Dict[str, Any]) -> str:
        for value in (
            detail_dto.get("accountNo"),
            transaction.get("accountNo"),
            detail_dto.get("fromFri"),
            transaction.get("fromFri"),
        ):
            normalized = self._normalize_msisdn(value)
            if normalized:
                return normalized
        return ""

    def _is_payout_statement(self, account_context: Dict[str, Any], detail_dto: Dict[str, Any]) -> bool:
        from_fri = str(detail_dto.get("fromFri") or "")
        normalized_from_fri_digits = self._digits(from_fri)
        own_phone = self._normalize_msisdn(account_context.get("phone"))
        own_accno = str(account_context.get("account_accno") or "").strip()

        if own_phone and own_phone in normalized_from_fri_digits:
            return True
        if own_accno and own_accno in from_fri:
            return True
        return False

    def _payout_statement_matches_order(self, mapped_trans, raw_trans, order):
        order_amount = self._to_money(order.get("amount"))
        trans_amount = self._to_money(raw_trans.get("amount", mapped_trans.get("txnAmount")))
        if order_amount is None or trans_amount is None or order_amount != trans_amount:
            return False

        trade_time = self._parse_statement_time(
            mapped_trans.get("tradeTime")
            or raw_trans.get("tradeTime")
            or raw_trans.get("trnDate")
            or raw_trans.get("transactionTime")
        )
        accept_time = self._parse_statement_time(order.get("time_accept"))
        if not trade_time or not accept_time:
            return False
        lower_bound = accept_time - timedelta(seconds=30)
        upper_bound = accept_time + timedelta(seconds=self.statement_df_window_seconds)
        return lower_bound <= trade_time <= upper_bound

    def observe_payout_statement_matches(self, mapped_trans, raw_trans, account_context, df_orders):
        if not self.enable_payout_observation:
            return False
        if not df_orders:
            self.logger.info(f"EasyPaisa {account_context['id']} 发现代付流水，但本轮没有 MySQL 代付未知订单，按观测模式跳过回调")
            return False
        matched = False
        for order in df_orders:
            if not self._payout_statement_matches_order(mapped_trans, raw_trans, order):
                continue
            matched = True
            self.logger.info(
                "EasyPaisa 代付账单观测匹配，不回调: "
                f"payment_id={account_context['id']}, order_code={order.get('code')}, "
                f"amount={order.get('amount')}, trade_time={mapped_trans.get('tradeTime')}, "
                f"utr={mapped_trans.get('custRefNo')}, trans_id={mapped_trans.get('extOrderNo')}"
            )
        if not matched:
            self.logger.info(
                f"EasyPaisa {account_context['id']} 代付流水未匹配未知订单，不回调: "
                f"amount={raw_trans.get('amount', mapped_trans.get('txnAmount'))}, trade_time={mapped_trans.get('tradeTime')}"
            )
        return matched

    def _build_payout_mapped_transaction(self, transaction: Dict[str, Any], account_context: Dict[str, Any]):
        mapped = self._build_credit_mapped_transaction(transaction, account_context)
        if not mapped:
            return None
        mapped["txnType"] = "PAY"
        return mapped

    def _build_credit_mapped_transaction(self, transaction: Dict[str, Any], account_context: Dict[str, Any]):
        detail_dto = transaction.get("historyDetailRspDTO") or {}
        amount = self._to_money(transaction.get("amount"))
        if amount is None:
            self.logger.warning(
                f"EasyPaisa {account_context['id']} 流水金额异常，跳过: amount={transaction.get('amount')}"
            )
            return None

        fee = self._to_money(detail_dto.get("fee")) or Decimal("0.00")
        statement_ref = self._extract_statement_ref(transaction, detail_dto)
        payer_callback_utr = self._extract_payer_callback_utr(transaction, detail_dto)
        if not payer_callback_utr:
            self.logger.warning(f"EasyPaisa {account_context['id']} CREDIT流水缺少付款方手机号，跳过")
            return None

        payer_account = payer_callback_utr
        payee_account = self._strip_ac_prefix(detail_dto.get("gatherNo"))
        if not payee_account:
            payee_account = str(account_context.get("account_accno") or "").strip()

        ext_order_no = str(statement_ref or detail_dto.get("extOrderNo") or transaction.get("orderNo") or "").strip()
        trade_time = (
            transaction.get("tradeTime")
            or transaction.get("trnDate")
            or transaction.get("transactionTime")
            or ""
        )

        return {
            "txnType": "CREDIT",
            "txnAmount": self._money_to_callback(amount),
            "custRefNo": payer_callback_utr,
            "txnStatus": "SUCCESS",
            "txnNote": transaction.get("busTypeName", ""),
            "accountNo": payer_account,
            "payeeAccountNo": payee_account,
            "payeeIfsc": "",
            "tradeTime": trade_time,
            "extOrderNo": ext_order_no,
            "fee": self._money_to_callback(fee),
        }

    def acquire_collection_callback_lock(self, payment_id, utr, amount=None, trans_id=None):
        fingerprint_source = f"{payment_id}|{utr}|{amount or ''}|{trans_id or ''}"
        fingerprint = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()
        lock_key = f"easypaisa:collection_callback_lock:{self.name}:{payment_id}:{fingerprint}"
        lock_value = str(uuid.uuid4())
        try:
            ok = self.redis.set(lock_key, lock_value, nx=True, ex=max(1, int(self.callback_lock_ttl)))
            if not ok:
                self.logger.info(
                    f"EasyPaisa {payment_id} 代收回调锁未释放，跳过本轮: "
                    f"utr={self._mask(utr)}, amount={amount}, trans_id={self._mask(trans_id)}"
                )
                return None, None
            return lock_key, lock_value
        except Exception as e:
            self.logger.error(
                f"EasyPaisa {payment_id} 代收回调锁获取失败 "
                f"utr={self._mask(utr)}, amount={amount}, trans_id={self._mask(trans_id)}: {e}",
                exc_info=True,
            )
            return None, None

    def release_collection_callback_lock(self, lock_key, lock_value):
        if not lock_key or not lock_value:
            return False
        try:
            script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
            """
            return bool(self.redis.eval(script, 1, lock_key, lock_value))
        except Exception as e:
            self.logger.error(f"EasyPaisa 代收UTR回调锁释放失败 key={lock_key}: {e}", exc_info=True)
            return False

    # 调用 API 接口 /order/Success 确认代收订单。
    def normalize_callback_base(self, host):
        base_domain = (host or '').strip().rstrip('/')
        if base_domain.endswith('/api'):
            base_domain = base_domain[:-4]
        return base_domain

    def get_order_success_url(self):
        internal_host = self.normalize_callback_base(getattr(self, 'internal_callback_host', None))
        if internal_host:
            return f"{internal_host}/order/Success"
        return "/order/Success"

    async def send(self, orders_send, account_context):
        result = {"is_success": False}
        try:
            url = self.get_order_success_url()
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            }
            self.logger.info(f"{account_context['id']},send()发起请求：{url}, headers: {headers}, data: {orders_send}")

            response_text = None
            for attempt in range(2):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, headers=headers, data=orders_send,
                                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            response_text = await resp.text()
                            if resp.status == 200:
                                break
                except Exception as e:
                    self.logger.error(f"网络请求错误: uid: {account_context['id']}; 错误详情:{e}")
                if attempt == 0:
                    await asyncio.sleep(0.5)

            if response_text is None:
                error_message = f"error:{account_context['id']}, send {self.name}, callback message：None"
                self.logger.error(error_message)
                result['error_message'] = error_message
                return result

            self.logger.info(f"{account_context['id']}, 发送{self.name}回调信息：{response_text}")
            _res = simplejson.loads(response_text)

            if _res['code'] == 100:
                result["is_success"] = True
                return result
            else:
                error_message = f"payment_id: {account_context['id']}, 请求{url}失败：{orders_send}"
                result["error_code"] = _res['code']
                result["error_message"] = error_message
                return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = f"send() 脚本运行错误: {e}\n{''.join(tb_str)}\n{simplejson.dumps(account_context)}"
            self.logger.error(error_message)
            result["error_message"] = error_message
            return result

    # 抓取账单
    async def getBills(self, account_context):
        self.logger.info(f"payment_id: {account_context['id']}, getBills")
        result = {"is_success": False}
        try:
            account_id = str(account_context.get('phone') or '').strip()
            if not account_id:
                self.logger.error(f"{account_context['id']}, 无有效的account_id，无法查询账单")
                return result
            payment_id = account_context['id']
            if not payment_id:
                self.logger.error("回调数据中缺少 payment_id。")
                return result

            account_selected = str(account_context.get('account_accno') or '').strip()
            if not account_selected:
                self.logger.error(f"{account_context['id']}, MySQL 缺少 account_accno，无法查询账单")
                return result
            payload = {"id": str(uuid.uuid4()), "action": "queryBill", "payload": {"account_id": account_id, "accno": account_selected}}
            payload_str = json.dumps(payload, separators=(',', ':'))
            data_base64 = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
            sign = hashlib.md5((data_base64 + SECRET_KEY).encode('utf-8')).hexdigest()
            request_data = {'user_id': USER_ID, 'data': data_base64, 'sign': sign}
            self.logger.info(
                "EasyPaisa queryBill 请求: "
                f"payment_id={payment_id}, api={API_URL}, "
                f"account_id={self._mask(account_id)}, accno={self._mask(account_selected)}, "
                f"payload_id={payload['id']}, sign={self._mask(sign, 6, 4)}"
            )
            timeout = aiohttp.ClientTimeout(total=self.query_bill_timeout)
            async with aiohttp.ClientSession() as session:
                for attempt in range(2):
                    try:
                        async with session.post(API_URL, data=request_data, timeout=timeout) as response:
                            # 检查HTTP状态码
                            if response.status != 200:
                                self.logger.error(f"{account_context['id']}, queryBill API请求失败，HTTP状态码: {response.status}")
                                self.logger.error(f"响应内容（原始文本）:\n{await response.text()}")
                                result['error_code'] = response.status
                                result['error_message'] = await response.text()
                                return result
                            # 检查Content-Type
                            content_type = response.headers.get('Content-Type', '')
                            if 'application/json' not in content_type:
                                self.logger.error(f"{account_context['id']}, API响应非JSON格式，Content-Type: {content_type}")
                                self.logger.error(f"响应内容（原始文本）:\n{await response.text()}")
                                result['error_code'] = 'invalid_content_type'
                                result['error_message'] = f"非JSON格式，Content-Type: {content_type}"
                                return result
                            response_data = await response.json()
                            self.logger.info(f"--- API响应成功 ---")
                            self.logger.info(json.dumps(response_data, indent=4, ensure_ascii=False))
                            # 检查API返回的业务码
                            if response_data.get('code') != 200:
                                self.logger.error(f"{account_context['id']}, queryBill失败: {response_data.get('msg')}")
                                result['error_code'] = response_data.get('code')
                                result['error_message'] = response_data.get('msg')
                                if response_data.get('code') == 423 and attempt == 0:
                                    self.logger.warning(f"{account_context['id']}, queryBill返回423，2秒后短重试一次")
                                    await asyncio.sleep(2)
                                    continue
                                return result
                            transactionHistoryList = response_data.get('data', {}).get('body', {}).get('transactionHistory', [])
                            self.logger.info(f"{account_context['id']}, 爬取交易记录：{transactionHistoryList}")
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
                            return result
                    except aiohttp.ClientError as e:
                        self.logger.error(f"{account_context['id']}, 请求失败: {e}")
                        result['error_message'] = str(e)
                        return result
                    except json.JSONDecodeError as e:
                        self.logger.error(f"{account_context['id']}, API响应JSON解析失败: {e}")
                        result['error_message'] = str(e)
                        return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{account_context['id']}, getBills() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(account_context)}')
            result['error_message'] = error_message
        return result

    def _query_bill_fail_key(self, payment_id):
        return f"easypaisa:query_bill_fail:{payment_id}"

    def record_query_bill_failure(self, payment_id, error_code=None, error_message=None) -> int:
        key = self._query_bill_fail_key(payment_id)
        try:
            count = int(self.redis.incr(key))
            self.redis.expire(key, max(1, self.query_bill_fail_ttl))
            self.logger.warning(
                f"EasyPaisa {payment_id} queryBill失败计数={count}, code={error_code}, msg={error_message}"
            )
            return count
        except Exception as e:
            self.logger.error(f"EasyPaisa {payment_id} queryBill失败计数写入Redis失败: {e}")
            return 1

    def clear_query_bill_failure(self, payment_id):
        try:
            self.redis.delete(self._query_bill_fail_key(payment_id))
        except Exception as e:
            self.logger.warning(f"EasyPaisa {payment_id} 清理queryBill失败计数失败: {e}")

    def maybe_pause_collection_status(self, payment_id, fail_count, error_code=None):
        if self.query_bill_fail_threshold <= 0:
            return 0
        if str(error_code) == "423":
            return 0
        if fail_count < self.query_bill_fail_threshold:
            return 0
        affected = self._execute_update(
            "UPDATE payment SET collection_status=0 WHERE id=%s AND collection_status=1",
            (payment_id,),
        )
        if affected:
            self.logger.warning(
                f"easypaisa {payment_id} queryBill连续失败{fail_count}次，collection_status 已暂停，等待 monitor 健康恢复。"
            )
        return affected

    async def callback_transaction(self, utr: str, mapped_trans: Dict, account_context) -> bool:
        callback_success = await self.transaction_callback(mapped_trans, account_context)
        if callback_success:
            return True
        self.logger.error(f"easypaisa {account_context['id']}, 代收交易 {utr} 回调失败，等待下轮账单扫描由 MySQL 幂等重试")
        return False

    async def grabstatement(self, account_context, statement_context=None):
        try:
            payment_id = account_context["id"]
            df_orders = (statement_context or {}).get("df_orders", [])
            self.logger.info(
                f"easypaisa {payment_id} 开始爬取账单，"
                f"代付观测候选={len(df_orders)}, 代付观测开关={self.enable_payout_observation}"
            )

            getBills = await self.getBills(account_context)
            self.logger.info(
                f"easypaisa {payment_id}, getBills返回: success={getBills.get('is_success')}, "
                f"code={getBills.get('error_code', 'N/A')}"
            )

            if isinstance(getBills, dict) and getBills.get('error_code') == 501:
                self.logger.error(f"easypaisa {payment_id} 抓取流水返回501错误，标记钱包账号无效。")
                self.mark_wallet_account_invalid(account_context, "501抓取流水账号无效")
                return 'account_invalid'

            if not getBills.get("is_success"):
                fail_count = self.record_query_bill_failure(
                    payment_id, getBills.get("error_code"), getBills.get("error_message")
                )
                self.maybe_pause_collection_status(payment_id, fail_count, getBills.get("error_code"))
                return False

            self.clear_query_bill_failure(payment_id)
            transaction_list = getBills.get("transaction_history_list") or []
            if not transaction_list:
                self.logger.info(f"easypaisa {payment_id} 爬取账单为空")
                return True

            callback_count = 0
            payout_observed_count = 0
            skipped_count = 0
            for idx, transaction in enumerate(transaction_list):
                detail_dto = transaction.get("historyDetailRspDTO") or {}
                statement_ref = self._extract_statement_ref(transaction, detail_dto)

                if transaction.get("appTransaction") is not True:
                    self.logger.info(f"easypaisa {payment_id}, 跳过非成功流水 ref={statement_ref or 'N/A'}")
                    skipped_count += 1
                    continue

                if self._is_payout_statement(account_context, detail_dto):
                    mapped_pay_trans = self._build_payout_mapped_transaction(transaction, account_context)
                    if self.enable_payout_observation and mapped_pay_trans:
                        if self.observe_payout_statement_matches(mapped_pay_trans, transaction, account_context, df_orders):
                            payout_observed_count += 1
                    else:
                        self.logger.info(
                            f"easypaisa {payment_id}, 第{idx}条流水识别为出款/PAY，当前未开启代付观测，跳过不回调: ref={statement_ref or 'N/A'}"
                        )
                    skipped_count += 1
                    continue

                mapped_trans = self._build_credit_mapped_transaction(transaction, account_context)
                if not mapped_trans:
                    skipped_count += 1
                    continue

                self.logger.info(
                    f"easypaisa {payment_id}, CREDIT流水准备回调，订单匹配交给 /order/Success MySQL 幂等入口: "
                    f"amount={mapped_trans.get('txnAmount')}, "
                    f"payer_phone={self._mask(mapped_trans.get('custRefNo'))}, "
                    f"trans_id={self._mask(mapped_trans.get('extOrderNo'))}, trade_time={mapped_trans.get('tradeTime')}"
                )
                callback_lock_key, callback_lock_value = self.acquire_collection_callback_lock(
                    payment_id,
                    mapped_trans["custRefNo"],
                    amount=mapped_trans.get("txnAmount"),
                    trans_id=mapped_trans.get("extOrderNo"),
                )
                if not callback_lock_value:
                    skipped_count += 1
                    continue

                try:
                    callback_ok = await self.callback_transaction(mapped_trans["custRefNo"], mapped_trans, account_context)
                    if callback_ok:
                        callback_count += 1
                    else:
                        self.release_collection_callback_lock(callback_lock_key, callback_lock_value)
                except Exception:
                    self.release_collection_callback_lock(callback_lock_key, callback_lock_value)
                    raise

            self.logger.info(
                f"easypaisa {payment_id} 账单处理完成: 代收回调成功={callback_count}, "
                f"代付观测匹配={payout_observed_count}, 跳过={skipped_count}, 总流水={len(transaction_list)}"
            )
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            account_text = simplejson.dumps(account_context) if isinstance(account_context, dict) else str(account_context)
            self.logger.error(f"easypaisa grabstatement() 脚本运行错误{e}\n{tb_str}\n{account_text}")
            return False

    # 爬取账单
    async def get_grabstatement(self, payment_id):
        try:
            if not payment_id:
                self.logger.error(f"{self.name} MySQL账单调度缺少 payment_id")
                return False

            account_context = self.fetch_statement_account_context(payment_id)
            if not account_context:
                return True

            statement_context = self.fetch_due_statement_scan_context(payment_id)
            if not statement_context.get("has_due"):
                self.logger.info(f"EasyPaisa {payment_id} 无代收待确认/代付未知订单，本轮不查询账单")
                return True

            statement_context = self.reserve_due_statement_scan_context(statement_context)
            if not statement_context.get("has_due"):
                self.logger.info(f"EasyPaisa {payment_id} 本轮订单账单探测锁均未释放，跳过查询账单")
                return True
            lock_ttl = self.statement_df_probe_interval - 5 if statement_context.get("df_orders") and not statement_context.get("ds_orders") else 55
            if not self.acquire_statement_wallet_lock(payment_id, lock_ttl):
                return True

            grabstatement = await self.grabstatement(account_context, statement_context=statement_context)
            self.logger.info(f"EasyPaisa {payment_id} grabstatement 返回结果: {grabstatement}")

            if isinstance(grabstatement, str) and grabstatement == 'account_invalid':
                self.logger.error(f"{self.name} 账单返回501，已写入 MySQL 钱包无效状态:" + simplejson.dumps(account_context))
                return 'account_invalid'

            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_grabstatement 脚本运行错误{}\n{}\npayment_id={}'.format(e, error_message, payment_id))
            return False

    # 回调代收账单
    async def transaction_callback(self, transaction: Dict, account_context) -> bool:
        self.logger.info(f"{account_context['id']}, transaction_callback(), 开始回调代收 transaction: {transaction}")
        try:
            if transaction.get("txnType") != "CREDIT":
                self.logger.error(f"{account_context['id']}, transaction_callback() 失败，本版本只支持代收CREDIT: {transaction}")
                return False
            account = transaction.get("payeeAccountNo", "")
            ifsc = transaction.get("payeeIfsc", "")

            orders_send = {
                "type": "New",
                "bank_name": self.name,
                "payment_id": account_context["id"],
                "partner_id": account_context["partner_id"],
                "amount": transaction["txnAmount"],
                "utr": transaction["custRefNo"],
                "trade_type": transaction["txnType"],
                "status": transaction["txnStatus"],
                "remarks": transaction["txnNote"],
                "ifsc": str(ifsc).upper(),
                "account": account,
                "fee": transaction["fee"],
                "trans_id": transaction["extOrderNo"],
            }
            if_send = await self.send(orders_send, account_context)
            if if_send.get("is_success") is False:
                await asyncio.sleep(0.5)
                if_send = await self.send(orders_send, account_context)

            if if_send.get("is_success") is True:
                self.logger.info(f"{account_context['id']}, transaction_callback 成功：{simplejson.dumps(orders_send)}")
                return True

            self.logger.info(f"{account_context['id']}, transaction_callback 失败：{simplejson.dumps(orders_send)}")
            return False
        except Exception as e:
            ref = transaction.get("custRefNo") or transaction.get("extOrderNo") or "N/A"
            self.logger.error(f"回调代收交易记录失败 ref={ref}: {e}", exc_info=True)
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
    
    async def process_statement_payment_id_async(self, payment_id) -> bool:
        """按 MySQL 候选 payment_id 执行账单扫描。"""
        try:
            _id = str(payment_id)

            self.logger.info(f"进程 {os.getpid()} 处理 EasyPaisa MySQL 候选 payment_id={_id}")
            _lock = self.get_lock(f"statement_payment_{_id}")
            if not _lock:
                self.logger.warning(f"{_id}, 未获取到 MySQL 调度锁！")
                return False

            try:
                res = await self.get_grabstatement(_id)
                self.logger.info(f"{_id}, get_grabstatement() res {type(res)}： {res}")
                return res is True
            finally:
                self.del_lock(f"statement_payment_{_id}", _lock)
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f"process_statement_payment_id_async 处理 payment_id={payment_id} 失败: {e} 错误详情：{error_message}")
            return False

    async def process_statement_payment_ids_concurrent(self, payment_ids: List[str], concurrent_limit: int = 20):
        """并发处理 MySQL 候选 payment_id。"""
        if not payment_ids:
            return

        semaphore = asyncio.Semaphore(concurrent_limit)

        async def process_with_semaphore(payment_id):
            async with semaphore:
                return await self.process_statement_payment_id_async(payment_id)

        tasks = [process_with_semaphore(payment_id) for payment_id in payment_ids]

        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))

        self.logger.info(f"进程 {os.getpid()} MySQL账单候选并发处理完成: "
                         f"总数 {len(payment_ids)}, 成功 {success_count}, 失败 {len(results) - success_count}, "
                         f"异常 {error_count}, 耗时 {end_time - start_time:.2f}秒")

    def main(self):
        try:
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"
            reconcile_stats = self.reconcile_wallet_status_from_mysql()
            due_payment_ids = self.fetch_due_statement_payment_ids(limit=200)
            self.logger.info(
                f"EasyPaisa MySQL账单调度扫描完成: reconcile={reconcile_stats}, due_payment_ids={len(due_payment_ids)}"
            )
            self.run_health_balance_check_once()

            if not due_payment_ids:
                self.logger.info("EasyPaisa MySQL账单调度没有待处理 payment_id")
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
                loop.run_until_complete(self.process_statement_payment_ids_concurrent(allocated_payment_ids, concurrent_limit=20))

            except Exception as e:
                self.logger.error(f"并发处理失败: {e}")

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
