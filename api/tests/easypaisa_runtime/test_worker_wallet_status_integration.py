import asyncio
import sys
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

    def mark_available(self, payment_id, reason=""):
        self.available.append((payment_id, reason))
        return 1

    def mark_offline(self, payment_id, reason=""):
        self.offline.append((payment_id, reason))
        return 1


class PakistanpayWalletStatusIntegrationTests(unittest.TestCase):
    def _bank(self, rows=None):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.name = "easypaisa"
        bank.hash_key = "hash_easypaisa"
        bank.set_key = "set_easypaisa"
        bank.redis = FakeRedis()
        bank.logger = MagicMock()
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

    def test_collection_scan_sql_uses_wallet_status_without_business_state_filters(self):
        bank = self._bank()

        bank.fetch_wallet_collection_rows()

        sql, params = bank.db_connection.executed[0]
        self.assertIsNone(params)
        self.assertIn("wallet_status = 1", sql)
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

    def test_login_off_marks_wallet_status_offline(self):
        bank = self._bank()
        bank.sendMsg = AsyncMock()
        bank.callbackStatus = AsyncMock()
        bank.on_off = MagicMock()

        asyncio.run(bank.login_off({"id": 533267, "partner_id": 33056}))

        self.assertEqual(bank.wallet_status_service.offline, [(533267, "login_off")])
        bank.on_off.assert_called_once()
        bank.callbackStatus.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
