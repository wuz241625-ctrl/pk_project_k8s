import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


MONITOR_SOURCE = REPO_ROOT / "api" / "jobs" / "jazzcash" / "jazzcash_monitor.py"


class JazzCashMonitorFinalStateSourceTests(unittest.TestCase):
    def read_source(self):
        return MONITOR_SOURCE.read_text()

    def test_monitor_reads_wallet_final_status_without_account_selection(self):
        source = self.read_source()

        self.assertIn("wallet_status = 1", source)
        self.assertNotIn("payout_status = 1", source)
        self.assertNotIn("account_accno IS NOT NULL", source)
        self.assertNotIn("account_accno != ''", source)
        self.assertNotIn(
            "WHERE status = 1 \n                          AND certified = 1\n                          AND bank_type = 98",
            source,
        )

    def test_501_offline_clears_mysql_final_status_and_redis_projection(self):
        source = self.read_source()

        self.assertIn("wallet_status = 0", source)
        self.assertIn("collection_status = 0", source)
        self.assertIn("payout_status = 0", source)
        self.assertIn("srem('payment_online_ds'", source)
        self.assertIn("srem('payment_online_df'", source)
        self.assertIn("lrem('payment_active_df'", source)

    def test_monitor_does_not_write_legacy_redis_online_gate(self):
        source = self.read_source()

        self.assertNotIn("sadd('payment_online_ds'", source)
        self.assertNotIn("sadd('payment_online_df'", source)
        self.assertNotIn("setex('kick_off_'", source)
        self.assertNotIn("sismember(cache_key_payment_online_df", source)
        self.assertIn("wallet_status = 1", source)


if __name__ == "__main__":
    unittest.main()
