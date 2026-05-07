import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


BILL_WORKER_SOURCE = REPO_ROOT / "api" / "jobs" / "Jazzcashpay_v2.py"


class JazzCashBillWorkerFinalStateSourceTests(unittest.TestCase):
    def read_source(self):
        return BILL_WORKER_SOURCE.read_text()

    def test_bill_worker_rechecks_mysql_wallet_final_status_without_account_selection(self):
        source = self.read_source()

        self.assertIn("wallet_status = 1", source)
        self.assertNotIn("account_accno IS NOT NULL", source)
        self.assertNotIn("account_accno <> ''", source)


if __name__ == "__main__":
    unittest.main()
