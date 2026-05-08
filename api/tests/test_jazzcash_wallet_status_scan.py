import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


API_ROOT = Path(__file__).resolve().parents[1]
JOBS_ROOT = API_ROOT / "jobs"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(JOBS_ROOT) not in sys.path:
    sys.path.insert(0, str(JOBS_ROOT))


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

    def fetchone(self):
        if self.connection.fetchone_rows:
            return self.connection.fetchone_rows.pop(0)
        return self.connection.fetchone_row


class FakeConnection:
    open = True

    def __init__(self, rows=None, fetchone_row=None, fetchone_rows=None):
        self.rows = rows or []
        self.fetchone_row = fetchone_row
        self.fetchone_rows = list(fetchone_rows or [])
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
        self.hashes = {}
        self.zsets = {}

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[str(field)] = value
        return 1

    def hdel(self, key, field):
        self.hashes.setdefault(key, {}).pop(str(field), None)
        return 1

    def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = score
        return 1

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    def zrem(self, key, member):
        self.zsets.setdefault(key, {}).pop(str(member), None)
        return 1


class JazzCashWalletStatusScanTests(unittest.TestCase):
    def _bank(self, rows=None, fetchone_row=None, fetchone_rows=None):
        from jobs.Jazzcashpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.name = "jazzcash"
        bank.hash_key = "hash_jazzcash"
        bank.set_key = "set_jazzcash"
        bank.redis = FakeRedis()
        bank.logger = MagicMock()
        bank.db_connection = FakeConnection(
            rows=rows,
            fetchone_row=fetchone_row,
            fetchone_rows=fetchone_rows,
        )
        bank.check_db_connection = MagicMock(return_value=bank.db_connection)
        return bank

    def test_collection_scan_sql_uses_wallet_status_without_account_selection(self):
        bank = self._bank()

        bank.fetch_wallet_collection_rows()

        sql, params = bank.db_connection.executed[0]
        self.assertIsNone(params)
        self.assertIn("wallet_status = 1", sql)
        self.assertIn("bank_type = 98 OR bank_type = '98' OR bank_type_id = 98", sql)
        self.assertNotIn("account_accno IS NOT NULL", sql)
        self.assertNotIn("account_accno <>", sql)
        self.assertNotIn("AND status = 1", sql)
        self.assertNotIn("AND certified = 1", sql)
        self.assertNotIn("AND manual_status = 0", sql)

    def test_sync_mysql_wallet_collection_accounts_restores_hash_and_zset(self):
        bank = self._bank(
            rows=[
                {
                    "id": 533302,
                    "phone": "03409297123",
                    "partner_id": 33056,
                    "upi": "03409297123",
                    "channel": "1003",
                    "net_trade_pw": "",
                }
            ]
        )

        synced = bank.sync_mysql_wallet_collection_accounts()

        self.assertEqual(synced, 1)
        raw = bank.redis.hget("hash_jazzcash", "533302")
        login_data = json.loads(raw)
        self.assertEqual(login_data["id"], 533302)
        self.assertEqual(login_data["real_payment_id"], 533302)
        self.assertEqual(login_data["status"], "grabstatement")
        self.assertEqual(login_data["phone"], "03409297123")
        self.assertEqual(login_data["qr_channel"], "1003")
        self.assertEqual(bank.redis.zscore("set_jazzcash", "533302"), 0)

    def test_update_key_removes_wallet_when_mysql_wallet_status_is_off(self):
        bank = self._bank(
            fetchone_row={
                "id": 533302,
                "phone": "03409297123",
                "wallet_status": 0,
                "collection_status": 0,
                "payout_status": 0,
                "status": 1,
                "certified": 1,
                "manual_status": 0,
                "channel": "1003",
            }
        )
        bank.redis.hset("hash_jazzcash", "533302", "{}")
        bank.redis.zadd("set_jazzcash", {"533302": 0})

        bank.update_key({"id": 533302, "status": "grabstatement"})

        self.assertIsNone(bank.redis.hget("hash_jazzcash", "533302"))
        self.assertIsNone(bank.redis.zscore("set_jazzcash", "533302"))


if __name__ == "__main__":
    unittest.main()
