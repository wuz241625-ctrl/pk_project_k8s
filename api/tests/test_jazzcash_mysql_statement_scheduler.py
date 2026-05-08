import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

JAZZCASH_WORKER_SOURCE = REPO_ROOT / "api" / "jobs" / "Jazzcashpay_v2.py"
JAZZCASH_MONITOR_SOURCE = REPO_ROOT / "api" / "jobs" / "jazzcash" / "jazzcash_monitor.py"


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.current_rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "FROM (" in normalized and "JOIN orders_ds" in normalized:
            self.current_rows = list(self.connection.due_rows)
        elif "FROM payment" in normalized:
            self.current_rows = list(self.connection.payment_rows)
        else:
            self.current_rows = []
        return len(self.current_rows)

    def fetchall(self):
        return list(self.current_rows)

    def fetchone(self):
        return self.current_rows[0] if self.current_rows else None


class FakeConnection:
    open = True

    def __init__(self, due_rows=None, payment_rows=None):
        self.due_rows = due_rows or []
        self.payment_rows = payment_rows or []
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeRedis:
    def __init__(self):
        self.kv = {}

    def setnx(self, key, value):
        if key in self.kv:
            return False
        self.kv[key] = value
        return True

    def expire(self, key, ttl):
        self.kv[f"{key}:ttl"] = ttl
        return True

    def setex(self, key, ttl, value):
        self.kv[key] = value
        self.kv[f"{key}:ttl"] = ttl
        return True

    def get(self, key):
        return self.kv.get(key)

    def delete(self, *keys):
        for key in keys:
            self.kv.pop(key, None)
        return len(keys)


class JazzCashMysqlStatementSchedulerTests(unittest.TestCase):
    def _bank(self, due_rows=None, payment_rows=None):
        from jobs.Jazzcashpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.name = "jazzcash"
        bank.lock_time = 30
        bank.statement_ds_window_seconds = 7 * 60
        bank.statement_df_window_seconds = 10 * 60
        bank.statement_df_probe_interval = 2 * 60
        bank.redis = FakeRedis()
        bank.logger = MagicMock()
        bank.db_connection = FakeConnection(due_rows, payment_rows)
        bank.check_db_connection = MagicMock(return_value=bank.db_connection)
        return bank

    def test_due_payment_scan_uses_mysql_orders_not_hash_set_queue(self):
        bank = self._bank(due_rows=[{"id": 533302}])

        self.assertEqual(bank.fetch_due_statement_payment_ids(), ["533302"])

        executed_sql = "\n".join(sql for sql, _ in bank.db_connection.executed)
        self.assertIn("JOIN orders_ds", executed_sql)
        self.assertIn("JOIN orders_df", executed_sql)
        self.assertIn("wallet_status = 1", executed_sql)
        self.assertIn("bank_type_id = 98", executed_sql)
        self.assertIn("od.utr IS NOT NULL", executed_sql)
        self.assertIn("od.utr <> ''", executed_sql)
        self.assertIn("LIMIT 200", executed_sql)

    def test_due_statement_context_uses_only_ds_orders_with_payer_phone(self):
        bank = self._bank()

        bank.fetch_due_statement_scan_context("533302")

        executed_sql = "\n".join(sql for sql, _ in bank.db_connection.executed)
        self.assertIn("FROM orders_ds", executed_sql)
        self.assertIn("utr IS NOT NULL", executed_sql)
        self.assertIn("utr <> ''", executed_sql)

    def test_statement_account_context_is_mysql_wallet_context_without_account_accno(self):
        bank = self._bank(payment_rows=[{
            "id": 533302,
            "phone": "03409297123",
            "partner_id": 33056,
            "upi": "03409297123",
            "channel": "1003",
            "net_trade_pw": "",
        }])

        context = bank.fetch_statement_account_context("533302")

        self.assertEqual(context["id"], "533302")
        self.assertEqual(context["phone"], "03409297123")
        self.assertEqual(context["partner_id"], 33056)
        self.assertEqual(context["status"], "grabstatement")
        self.assertNotIn("account_accno", context)
        executed_sql = "\n".join(sql for sql, _ in bank.db_connection.executed)
        self.assertIn("wallet_status = 1", executed_sql)
        self.assertNotIn("account_accno IS NOT NULL", executed_sql)

    def test_main_uses_mysql_due_ids_and_processes_allocated_ids(self):
        bank = self._bank()
        bank.fetch_due_statement_payment_ids = MagicMock(return_value=["533302"])
        bank.get_process_allocated_members = MagicMock(return_value=[b"533302"])
        bank.process_statement_payment_ids_concurrent = AsyncMock(return_value=None)

        bank.main()

        bank.fetch_due_statement_payment_ids.assert_called_once_with(limit=200)
        bank.process_statement_payment_ids_concurrent.assert_awaited_once_with(["533302"], concurrent_limit=20)

    def test_statement_wallet_lock_prevents_duplicate_multi_instance_scan(self):
        bank = self._bank()

        self.assertTrue(bank.acquire_statement_wallet_lock("533302", 60))
        self.assertFalse(bank.acquire_statement_wallet_lock("533302", 60))
        self.assertIn("statement_scan_lock:jazzcash:533302", bank.redis.kv)

    def test_source_main_scheduler_does_not_use_legacy_hash_set_queue(self):
        source = JAZZCASH_WORKER_SOURCE.read_text()

        main_source = source[source.index("    def main(self):"):]
        self.assertIn("fetch_due_statement_payment_ids", main_source)
        self.assertNotIn("sync_mysql_wallet_collection_accounts", main_source)
        self.assertNotIn("zrangebyscore(self.set_key", main_source)
        self.assertNotIn("read_zset(self.set_key", main_source)

    def test_monitor_main_flow_reads_mysql_payments_not_hash_jazzcash(self):
        source = JAZZCASH_MONITOR_SOURCE.read_text()

        run_source = source[
            source.index("    async def run_jazzcash_monitor_check(self):"):
            source.index("    # ==================== 结束 JazzCash 监控相关方法")
        ]
        self.assertIn("get_online_payments_from_db", run_source)
        self.assertNotIn("get_online_jazzcash_accounts", run_source)
        self.assertNotIn("hash_jazzcash", run_source)

        main_source = source[source.index("    def main(self):"):]
        self.assertIn("run_jazzcash_monitor_check", main_source)
        self.assertNotIn("zrangebyscore(self.set_key", main_source)
        self.assertNotIn("read_zset(self.set_key", main_source)
        self.assertNotIn("hset(self.hash_key", main_source)

    def test_monitor_run_uses_process_sharding_for_mysql_accounts(self):
        from jobs.jazzcash.jazzcash_monitor import AutoPayoutMonitor

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.logger = MagicMock()
        monitor.get_online_payments_from_db = AsyncMock(return_value=[
            {"id": 533302, "phone": "03409297123"},
            {"id": 533303, "phone": "03400000000"},
        ])
        monitor.get_process_allocated_members = MagicMock(return_value=[b"533302"])
        monitor.check_account_health = AsyncMock(return_value={
            "account_id": "533302",
            "is_online": True,
            "status": "online",
            "balance": 120.0,
            "check_time": "2026-05-08T00:00:00",
            "error_message": "",
            "api_response_time": 0.1,
        })
        monitor.update_redis_cache = AsyncMock(return_value=False)
        monitor.handle_problematic_accounts = AsyncMock(return_value=None)
        monitor.generate_monitor_report = AsyncMock(return_value={})

        asyncio.run(monitor.run_jazzcash_monitor_check())

        monitor.get_online_payments_from_db.assert_awaited_once()
        monitor.get_process_allocated_members.assert_called_once()
        monitor.check_account_health.assert_awaited_once_with({"id": 533302, "phone": "03409297123"})


if __name__ == "__main__":
    unittest.main()
