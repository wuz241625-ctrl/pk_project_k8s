import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.order.order import build_third_duplicate_lookup_payload


class BuildThirdDuplicateLookupPayloadTests(unittest.TestCase):
    def test_easypay_uses_trans_id_for_duplicate_check(self):
        payload = build_third_duplicate_lookup_payload(
            third_party_name='easypay',
            utr='03174629500',
            query_result={'transactionId': '149222628'},
        )
        self.assertEqual(payload['field'], 'trans_id')
        self.assertEqual(payload['value'], '149222628')
        self.assertEqual(payload['message_key'], 10320)

    def test_easypay_missing_transaction_id_returns_none(self):
        payload = build_third_duplicate_lookup_payload(
            third_party_name='easypay',
            utr='03174629500',
            query_result={},
        )
        self.assertIsNone(payload)

    def test_non_easypay_keeps_utr_duplicate_check(self):
        payload = build_third_duplicate_lookup_payload(
            third_party_name='snakepay',
            utr='1234567890',
            query_result={},
        )
        self.assertEqual(payload['field'], 'utr')
        self.assertEqual(payload['value'], '1234567890')
        self.assertEqual(payload['message_key'], 10229)


if __name__ == "__main__":
    unittest.main()
