import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


WORKER_SOURCES = [
    REPO_ROOT / "api" / "jobs" / "pakistanpay_v2.py",
    REPO_ROOT / "api" / "jobs" / "Jazzcashpay_v2.py",
]
UTR_CALLBACK = REPO_ROOT / "api" / "application" / "pay" / "utr_callback.py"
ORDER_CALLBACK = REPO_ROOT / "api" / "application" / "pay" / "order.py"


class StatementCallbackMysqlIdempotencySourceTests(unittest.TestCase):
    def test_statement_workers_do_not_skip_callbacks_by_redis_marker(self):
        for source_path in WORKER_SOURCES:
            with self.subTest(source=source_path.name):
                source = source_path.read_text()
                self.assertNotIn("zscore(self.if_callback_key", source)
                self.assertNotIn("mark_transaction_callback(", source)
                self.assertNotIn("clean_if_callback_key()", source)

    def test_mysql_callback_paths_keep_order_and_statement_guards(self):
        utr_callback = UTR_CALLBACK.read_text()
        order_callback = ORDER_CALLBACK.read_text()

        self.assertIn("where code=%s and status in (-1,1,2)", utr_callback)
        self.assertIn("callback=0 and trade_type=1", utr_callback)
        self.assertIn("update bank_record set callback=1,order_code=%s", utr_callback)
        self.assertIn("trans_id", utr_callback)

        self.assertIn("get_result_by_condition('bank_record'", order_callback)
        self.assertIn("create_result('bank_record'", order_callback)
        self.assertIn("success_busy_{trans_id}", order_callback)


if __name__ == "__main__":
    unittest.main()
