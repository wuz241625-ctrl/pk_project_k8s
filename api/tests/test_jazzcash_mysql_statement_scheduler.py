import asyncio
from datetime import datetime
import sys
import time
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

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        if ex is not None:
            self.kv[f"{key}:ttl"] = ex
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
        bank.upi_time = 5 * 60
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
        self.assertIn("utr", executed_sql)
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

    def test_jazzcash_trade_time_uses_existing_naive_time_without_pkt_to_utc(self):
        bank = self._bank()
        mapped_trans = {
            "txnAmount": "1.00",
            "custRefNo": "923325009516",
            "tradeTime": "2026-05-09T09:11:20",
        }
        ds_orders = [{
            "amount": "1.00",
            "utr": "03325009516",
            "time_create": datetime(2026, 5, 9, 9, 10, 0),
        }]

        self.assertTrue(bank._credit_statement_matches_due_order(mapped_trans, ds_orders))

    def test_jazzcash_credit_uses_due_context_and_pay_is_observation_only(self):
        bank = self._bank()
        bank.grabUpi = AsyncMock(return_value={"is_success": True})
        bank.getBills = AsyncMock(return_value={
            "is_success": True,
            "transaction_history_list": [
                {
                    "TRANS_ID": "JC-CREDIT-1",
                    "AC_FROM": "923325009516",
                    "AC_TO": "923409297123",
                    "AMOUNT_DEBITED": "0",
                    "AMOUNT_CREDITED": "1.00",
                    "FEE": "0",
                    "DESCRIPTION": "credit",
                    "INITIATOR_MSISDN": "923325009516",
                    "TRX_DTTM": "2026-05-09T09:11:20",
                    "CONTEXT_DATA": {},
                },
                {
                    "TRANS_ID": "JC-PAY-1",
                    "AC_FROM": "923409297123",
                    "AC_TO": "923001112222",
                    "AMOUNT_DEBITED": "1.00",
                    "AMOUNT_CREDITED": "0",
                    "FEE": "0",
                    "DESCRIPTION": "pay",
                    "INITIATOR_MSISDN": "923409297123",
                    "TRX_DTTM": "2026-05-09T09:12:20",
                    "CONTEXT_DATA": {"ACCOUNT_NUMBER": "03001112222"},
                },
            ],
        })
        bank.transaction_callback = AsyncMock(return_value=True)
        login_data = {
            "id": "533302",
            "phone": "03409297123",
            "partner_id": 33056,
            "upi_time": int(time.time()),
        }
        statement_context = {
            "ds_orders": [{
                "code": "S1",
                "payment_id": "533302",
                "partner_id": 33056,
                "amount": "1.00",
                "utr": "03325009516",
                "time_create": datetime(2026, 5, 9, 9, 10, 0),
            }],
            "df_orders": [{
                "code": "D1",
                "payment_id": "533302",
                "partner_id": 33056,
                "amount": "1.00",
                "time_accept": datetime(2026, 5, 9, 9, 11, 0),
                "payment_account": "03001112222",
                "utr": "",
            }],
        }

        asyncio.run(bank.grabstatement(login_data, if_first_time=False, statement_context=statement_context))

        bank.transaction_callback.assert_awaited_once()
        callback_transaction = bank.transaction_callback.await_args.args[0]
        self.assertEqual(callback_transaction["txnType"], "CREDIT")
        self.assertEqual(callback_transaction["extOrderNo"], "JC-CREDIT-1")

    def test_transaction_callback_rejects_pay_without_debit_compatibility(self):
        bank = self._bank()
        bank.send = AsyncMock()

        result = asyncio.run(bank.transaction_callback(
            {
                "txnType": "PAY",
                "txnAmount": "1.00",
                "custRefNo": "03001112222",
                "txnStatus": "SUCCESS",
                "txnNote": "pay",
                "payeeAccountNo": "03001112222",
                "payeeIfsc": "",
                "fee": "0",
                "extOrderNo": "JC-PAY-1",
            },
            {"id": "533302", "partner_id": 33056},
        ))

        self.assertFalse(result)
        bank.send.assert_not_awaited()

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
