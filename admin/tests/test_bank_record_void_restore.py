import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.partner.partner import (  # noqa: E402
    bank_record_void_update_data,
)


class BankRecordVoidTests(unittest.TestCase):
    def test_void_update_keeps_original_idempotency_keys(self):
        update_data = bank_record_void_update_data(
            {"id": 7, "utr": "03001234567", "trans_id": "TXN7"},
            "重复流水",
        )

        self.assertEqual(update_data["invalid"], 1)
        self.assertEqual(update_data["memo"], "重复流水")
        self.assertNotIn("utr", update_data)
        self.assertNotIn("trans_id", update_data)

    def test_void_update_default_memo_points_to_manual_settle(self):
        update_data = bank_record_void_update_data(
            {"id": 8, "utr": "03009999999", "trans_id": "TXN8"},
            "",
        )

        self.assertEqual(update_data["invalid"], 1)
        self.assertIn("人工补单", update_data["memo"])
        self.assertNotIn("utr", update_data)
        self.assertNotIn("trans_id", update_data)


if __name__ == "__main__":
    unittest.main()
