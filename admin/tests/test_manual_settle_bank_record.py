import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.order.order import (  # noqa: E402
    manual_settle_bank_record_query,
    manual_settle_bank_record_update_sql,
)


class ManualSettleBankRecordTests(unittest.TestCase):
    def test_manual_settle_query_uses_trans_id_and_accepts_voided_bank_record(self):
        query = manual_settle_bank_record_query()

        self.assertIn("trans_id=%s", query)
        self.assertNotIn("utr=%s", query)
        self.assertIn("amount=%s", query)
        self.assertIn("callback=0", query)
        self.assertIn("trade_type=1", query)
        self.assertIn("invalid in (0,1)", query)
        self.assertIn("order by invalid asc, id desc", query)

    def test_manual_settle_update_marks_record_consumed_and_active(self):
        sql = manual_settle_bank_record_update_sql()

        self.assertIn("callback=1", sql)
        self.assertIn("invalid=0", sql)
        self.assertIn("where id=%s and callback=0", sql)


if __name__ == "__main__":
    unittest.main()
