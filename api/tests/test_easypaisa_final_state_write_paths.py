import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
API_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)


class PaymentFinalStateWritePathTests(unittest.TestCase):
    def test_app_status_toggle_recomputes_final_statuses(self):
        from application.app.my.my import payment_update_for_status

        payment = {
            "wallet_status": 1,
            "certified": 1,
            "manual_status": 0,
        }

        self.assertEqual(
            payment_update_for_status(payment, 0),
            {"status": 0, "collection_status": 0, "payout_status": 0},
        )
        self.assertEqual(
            payment_update_for_status(payment, 1),
            {"status": 1, "collection_status": 1, "payout_status": 1},
        )

    def test_app_certified_toggle_recomputes_final_statuses(self):
        from application.app.my.my import payment_update_for_certified

        payment = {
            "wallet_status": 1,
            "status": 1,
            "manual_status": 0,
        }

        self.assertEqual(
            payment_update_for_certified(payment, 0),
            {"certified": 0, "collection_status": 0, "payout_status": 0},
        )
        self.assertEqual(
            payment_update_for_certified(payment, 1),
            {"certified": 1, "collection_status": 1, "payout_status": 1},
        )

    def test_low_success_manual_lock_closes_collection_for_all_wallets(self):
        from application.pay.pay import _manual_lock_update_fields

        self.assertEqual(
            _manual_lock_update_fields({"bank_type_id": 97}),
            {"manual_status": 1, "collection_status": 0},
        )
        self.assertEqual(
            _manual_lock_update_fields({"bank_type_id": 14}),
            {"manual_status": 1, "collection_status": 0},
        )


if __name__ == "__main__":
    unittest.main()
