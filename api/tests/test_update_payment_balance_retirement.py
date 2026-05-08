import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKER_SOURCE = REPO_ROOT / "api" / "jobs" / "update_payment_balance.py"


class UpdatePaymentBalanceRetirementTests(unittest.TestCase):
    def test_worker_is_retired_no_shared_balance_polling(self):
        source = WORKER_SOURCE.read_text()

        self.assertIn("RETIRED_WORKER_NAME", source)
        self.assertIn("update_payment_balance 已退役", source)
        self.assertNotIn("class BalanceUpdateMonitor", source)
        self.assertNotIn("easypaisa_balance_sorted", source)
        self.assertNotIn("jazzcash_balance_sorted", source)
        self.assertNotIn("aiohttp.ClientSession", source)
        self.assertNotIn("while True", source)

    def test_worker_entrypoint_exits_successfully(self):
        result = subprocess.run(
            [sys.executable, str(WORKER_SOURCE)],
            cwd=str(REPO_ROOT / "api" / "jobs"),
            text=True,
            capture_output=True,
            timeout=5,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("update_payment_balance 已退役", result.stdout)


if __name__ == "__main__":
    unittest.main()
