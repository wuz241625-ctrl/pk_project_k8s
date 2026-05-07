import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)


class PaymentAdminFinalStateWritePathTests(unittest.TestCase):
    def test_monitor_status_does_not_write_final_status(self):
        from application.partner.partner import monitor_status_update_fields

        payment = {
            "wallet_status": 1,
            "status": 1,
            "certified": 1,
            "manual_status": 0,
            "collection_status": 1,
        }

        self.assertEqual(
            monitor_status_update_fields(payment, monitor_status=0),
            {},
        )
        self.assertEqual(
            monitor_status_update_fields(payment, monitor_status=1),
            {},
        )

    def test_batch_disable_clears_final_statuses(self):
        from application.partner.partner import batch_disable_payment_update_sql

        sql = batch_disable_payment_update_sql(3)

        self.assertIn("certified=0", sql)
        self.assertIn("status=0", sql)
        self.assertIn("collection_status=0", sql)
        self.assertIn("payout_status=0", sql)
        self.assertEqual(sql.count("%s"), 3)


if __name__ == "__main__":
    unittest.main()
