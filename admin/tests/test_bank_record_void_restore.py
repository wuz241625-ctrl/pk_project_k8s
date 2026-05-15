import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.partner.partner import (  # noqa: E402
    bank_record_active_duplicate_condition,
    bank_record_restore_update_data,
    bank_record_void_update_data,
    strip_bank_record_void_suffix,
)


class BankRecordVoidRestoreTests(unittest.TestCase):
    def test_void_update_keeps_original_idempotency_keys(self):
        update_data = bank_record_void_update_data(
            {"id": 7, "utr": "03001234567", "trans_id": "TXN7"},
            "重复流水",
        )

        self.assertEqual(update_data["invalid"], 1)
        self.assertEqual(update_data["memo"], "重复流水")
        self.assertNotIn("utr", update_data)
        self.assertNotIn("trans_id", update_data)

    def test_restore_strips_legacy_void_suffix(self):
        record = {
            "id": 123,
            "utr": "03001234567_123",
            "trans_id": "TXN123_123",
            "memo": "误废除",
        }

        update_data = bank_record_restore_update_data(record, "商户反馈已付款")

        self.assertEqual(update_data["invalid"], 0)
        self.assertEqual(update_data["utr"], "03001234567")
        self.assertEqual(update_data["trans_id"], "TXN123")
        self.assertIn("误废除", update_data["memo"])
        self.assertIn("恢复废除: 商户反馈已付款", update_data["memo"])

    def test_strip_suffix_only_when_suffix_matches_record_id(self):
        self.assertEqual(strip_bank_record_void_suffix("TXN_123", 123), "TXN")
        self.assertEqual(strip_bank_record_void_suffix("TXN_456", 123), "TXN_456")
        self.assertEqual(strip_bank_record_void_suffix("", 123), "")

    def test_active_duplicate_condition_uses_original_trans_id(self):
        condition = bank_record_active_duplicate_condition(
            {
                "id": 123,
                "payment_id": 533303,
                "trade_type": 1,
                "trans_id": "TXN123_123",
            }
        )

        self.assertEqual(
            condition,
            {
                "payment_id": 533303,
                "trade_type": 1,
                "trans_id": "TXN123",
                "invalid": 0,
            },
        )

    def test_active_duplicate_condition_ignores_empty_trans_id(self):
        self.assertIsNone(
            bank_record_active_duplicate_condition(
                {"id": 123, "payment_id": 533303, "trade_type": 1, "trans_id": ""}
            )
        )


if __name__ == "__main__":
    unittest.main()

