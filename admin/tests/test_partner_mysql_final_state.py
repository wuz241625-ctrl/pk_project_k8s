import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.partner.partner import (
    apply_payment_wallet_status_fields,
    is_mysql_final_state_payment,
)


class PartnerMysqlFinalStateTests(unittest.TestCase):
    def test_jazzcash_uses_mysql_wallet_collection_and_payout_status(self):
        payment = {
            "bank_type": 98,
            "wallet_status": 1,
            "collection_status": 1,
            "payout_status": 0,
        }

        apply_payment_wallet_status_fields(payment)

        self.assertTrue(is_mysql_final_state_payment(payment))
        self.assertEqual(payment["online_status"], 1)
        self.assertEqual(payment["online_ds"], 1)
        self.assertEqual(payment["online_df"], 0)

    def test_legacy_bank_is_not_mysql_final_state_payment(self):
        payment = {"bank_type": 16, "wallet_status": 1, "collection_status": 1, "payout_status": 1}

        result = apply_payment_wallet_status_fields(payment)

        self.assertFalse(is_mysql_final_state_payment(payment))
        self.assertIs(result, payment)
        self.assertNotIn("online_status", payment)


if __name__ == "__main__":
    unittest.main()
