import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


AUTO_PAYOUT_SOURCE = REPO_ROOT / "api" / "jobs" / "jazzcash" / "jazzcash_auto_payout.py"


class JazzCashAutoPayoutV16SourceTests(unittest.TestCase):
    def read_source(self):
        return AUTO_PAYOUT_SOURCE.read_text()

    def test_account_selection_uses_payout_final_status_without_account_selection(self):
        source = self.read_source()

        self.assertIn("payout_status = 1", source)
        self.assertNotIn("account_accno IS NOT NULL", source)
        self.assertNotIn("account_accno <> ''", source)
        self.assertNotIn("payment_info.get('account_accno')", source)
        self.assertNotIn("status = 1 AND certified = 1", source)

    def test_account_selection_does_not_use_legacy_redis_online_or_active_gate(self):
        source = self.read_source()

        self.assertNotIn("lpop(self.REDIS_KEYS['jazzcash_active_df'])", source)
        self.assertNotIn("rpush(self.REDIS_KEYS['jazzcash_active_df']", source)
        self.assertNotIn("sismember(self.REDIS_KEYS['jazzcash_online_df']", source)
        self.assertNotIn("sismember('payment_online_df'", source)
        self.assertNotIn("rpush('payment_active_df'", source)
        self.assertNotIn("降级使用Redis状态", source)
        self.assertIn("MySQL payout_status", source)

    def test_api_signing_uses_jazzcash_gateway(self):
        source = self.read_source()

        self.assertIn("from application.jazzcash_gateway import build_form_body", source)
        self.assertIn("build_form_body(", source)
        self.assertNotIn("payload_b64 = base64.b64encode", source)

    def test_v16_code_semantics_do_not_mark_500_as_retry_or_reject(self):
        source = self.read_source()

        self.assertIn("manual_confirm", source)
        self.assertIn("elif code == 500", source)
        self.assertIn("elif code == 503", source)
        self.assertIn("code in [402, 423, 503]", source)


if __name__ == "__main__":
    unittest.main()
