import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


ORDER_LIFECYCLE = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "order_lifecycle.py"
SETTLEMENT = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "settlement.py"
TRANSFER_EXECUTOR = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "transfer_executor.py"


class JazzCashPayoutStateMachineSourceTests(unittest.TestCase):
    def test_success_final_state_is_set_only_by_settlement_with_status_guard(self):
        lifecycle = ORDER_LIFECYCLE.read_text()
        settlement = SETTLEMENT.read_text()

        self.assertNotIn("WHERE code = %s AND status IN (0, 1)", lifecycle)
        self.assertNotIn("状态status=3已在转账成功时更新", settlement)
        self.assertIn("SET earn_merchant=%s,", settlement)
        self.assertIn("status=3", settlement)
        self.assertIn("WHERE code=%s AND status=1", settlement)

    def test_only_402_retries_and_third_402_rejects(self):
        lifecycle = ORDER_LIFECYCLE.read_text()
        transfer_executor = TRANSFER_EXECUTOR.read_text()

        self.assertIn("error_code == 402", lifecycle)
        self.assertIn("new_retry_count >= 3", lifecycle)
        self.assertNotIn("error_code in [402, 423, 503]", lifecycle)
        self.assertNotIn("new_retry_count > 8", lifecycle)
        self.assertNotIn("reject_msg_codes", transfer_executor)
        self.assertNotIn("msg_cd in reject_msg_codes", transfer_executor)


if __name__ == "__main__":
    unittest.main()
