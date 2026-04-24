import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.setting.otherpay_option import build_otherpay_option, _truncate


class TruncateTests(unittest.TestCase):
    def test_short_string_unchanged(self):
        self.assertEqual(_truncate("165338898"), "165338898")

    def test_exact_limit_unchanged(self):
        self.assertEqual(_truncate("123456789012"), "123456789012")

    def test_long_string_truncated(self):
        self.assertEqual(
            _truncate("1e9638c20cc44ad799640b4c7c44e586"),
            "1e9638c2...e586",
        )

    def test_rsa_key_truncated(self):
        rsa = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA"
        result = _truncate(rsa)
        self.assertEqual(len(result), 15)  # 8 + 3 + 4
        self.assertIn("...", result)


class OtherpayOptionLabelTests(unittest.TestCase):
    def test_label_with_short_merchant_id(self):
        row = {"id": 27, "name": "easypay", "merchant_id": "165338898"}
        option = build_otherpay_option(row)
        self.assertEqual(option["label"], "easypay | 165338898 | #27")

    def test_label_with_long_merchant_id_truncated(self):
        row = {"id": 23, "name": "pakistanpay", "merchant_id": "1e9638c20cc44ad799640b4c7c44e586"}
        option = build_otherpay_option(row)
        self.assertEqual(option["label"], "pakistanpay | 1e9638c2...e586 | #23")

    def test_label_skips_empty_merchant_id(self):
        row = {"id": 25, "name": "easypay", "merchant_id": ""}
        option = build_otherpay_option(row)
        self.assertEqual(option["label"], "easypay | #25")

    def test_label_no_key3_in_output(self):
        row = {"id": 25, "name": "easypay", "merchant_id": "165338898", "key3": "1203411"}
        option = build_otherpay_option(row)
        self.assertNotIn("1203411", option["label"])


if __name__ == "__main__":
    unittest.main()
