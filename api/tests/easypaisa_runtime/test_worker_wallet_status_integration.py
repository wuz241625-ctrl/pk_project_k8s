import asyncio
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs"))


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))
        return len(self.connection.rows)

    def fetchall(self):
        return list(self.connection.rows)


class FakeConnection:
    open = True

    def __init__(self, rows=None):
        self.rows = rows or []
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
        self.hashes = {}
        self.zsets = {}
        self.deleted = []

    def zrem(self, key, member):
        self.zsets.setdefault(key, {}).pop(str(member), None)
        return 1

    def hdel(self, key, field):
        self.hashes.setdefault(key, {}).pop(str(field), None)
        return 1

    def delete(self, key):
        self.deleted.append(key)
        self.kv.pop(key, None)
        return 1

    def get(self, key):
        return self.kv.get(key)

    def setex(self, key, ttl, value):
        self.kv[key] = value
        return 1

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[str(field)] = value
        return 1

    def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = score
        return 1

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))


class FakeWalletStatusService:
    def __init__(self):
        self.available = []
        self.offline = []
        self.account_invalid = []

    def mark_available(self, payment_id, reason=""):
        self.available.append((payment_id, reason))
        return 1

    def mark_offline(self, payment_id, reason=""):
        self.offline.append((payment_id, reason))
        return 1

    def mark_account_invalid(self, payment_id, reason=""):
        self.account_invalid.append((payment_id, reason))
        return 1


class PakistanpayWalletStatusIntegrationTests(unittest.TestCase):
    def _bank(self, rows=None):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.name = "easypaisa"
        bank.enable_payout_observation = True
        bank.query_bill_fail_threshold = 3
        bank.query_bill_fail_ttl = 300
        bank.callback_lock_ttl = 5 * 60
        bank.redis = FakeRedis()
        bank.logger = MagicMock()
        bank._db_lock = threading.RLock()
        bank.db_connection = FakeConnection(rows=rows)
        bank.wallet_status_service = FakeWalletStatusService()
        bank.check_db_connection = MagicMock(return_value=bank.db_connection)
        return bank

    def test_reconcile_candidate_sql_covers_account_wallet_mismatch_only(self):
        bank = self._bank()

        bank.fetch_wallet_status_reconcile_rows()

        sql, params = bank.db_connection.executed[0]
        self.assertIsNone(params)
        self.assertIn("SELECT id, wallet_status, account_accno", sql)
        self.assertIn("wallet_status = 1 AND (account_accno IS NULL OR account_accno = '')", sql)
        self.assertIn("wallet_status = 0 AND account_accno IS NOT NULL AND account_accno <> ''", sql)
        self.assertIn("bank_type = 97 OR bank_type = '97' OR bank_type_id = 97", sql)

    def test_due_statement_payment_scan_sql_uses_wallet_status_without_business_state_filters(self):
        bank = self._bank()

        bank.fetch_due_statement_payment_ids()

        sql, params = bank.db_connection.executed[0]
        self.assertIsNone(params)
        self.assertIn("wallet_status = 1", sql)
        self.assertIn("JOIN orders_ds", sql)
        self.assertIn("JOIN orders_df", sql)
        self.assertNotIn("account_accno IS NOT NULL", sql)
        self.assertNotIn("account_accno <> ''", sql)
        self.assertNotIn("AND status = 1", sql)
        self.assertNotIn("AND certified = 1", sql)
        self.assertNotIn("AND manual_status = 0", sql)

    def test_reconcile_marks_offline_and_confirms_before_available(self):
        bank = self._bank(
            rows=[
                {"id": 533267, "wallet_status": 1, "account_accno": ""},
                {"id": 533295, "wallet_status": 0, "account_accno": "98525348"},
            ]
        )
        bank.confirm_wallet_available = MagicMock(return_value=True)

        stats = bank.reconcile_wallet_status_from_mysql()

        self.assertEqual(stats, {"confirm": 1, "offline": 1, "noop": 0})
        self.assertEqual(bank.wallet_status_service.offline, [(533267, "account_selection_cleared")])
        self.assertEqual(bank.wallet_status_service.available, [(533295, "upstream_confirmed")])
        bank.confirm_wallet_available.assert_called_once_with(
            {"id": 533295, "wallet_status": 0, "account_accno": "98525348"}
        )

    def test_wallet_status_service_receives_worker_redis_lock_client(self):
        from jobs.easypaisa.wallet_status_service import WorkerWalletStatusService

        bank = self._bank()

        service = bank._new_wallet_status_service()

        self.assertIsInstance(service, WorkerWalletStatusService)
        self.assertIs(service.redis, bank.redis)

    def test_grabstatement_501_marks_account_invalid(self):
        bank = self._bank()
        bank.getBills = AsyncMock(return_value={"is_success": False, "error_code": 501})
        account_context = {"id": 533267, "partner_id": 33056}

        result = asyncio.run(bank.grabstatement(account_context))

        self.assertEqual(result, "account_invalid")
        self.assertEqual(bank.wallet_status_service.account_invalid, [(533267, "501抓取流水账号无效")])

    def test_grabstatement_501_marker_failure_still_returns_account_invalid(self):
        bank = self._bank()
        bank.getBills = AsyncMock(return_value={"is_success": False, "error_code": 501})
        bank.wallet_status_service.mark_account_invalid = MagicMock(side_effect=RuntimeError("redis down"))
        account_context = {"id": 533267, "partner_id": 33056}

        result = asyncio.run(bank.grabstatement(account_context))

        self.assertEqual(result, "account_invalid")
        bank.logger.error.assert_called()


if __name__ == "__main__":
    unittest.main()
