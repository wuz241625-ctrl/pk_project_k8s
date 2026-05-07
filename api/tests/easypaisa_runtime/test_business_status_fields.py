import os
import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


class PaymentBusinessStatusSchemaTests(unittest.TestCase):
    def test_upi_payment_schema_declares_collection_and_payout_status(self):
        from application.lakshmi_api.schema.payment_schema import UpiPaymentSchema

        schema = UpiPaymentSchema()

        self.assertIn("collection_status", schema.fields)
        self.assertIn("payout_status", schema.fields)


class EasyPaisaCollectionDispatchPolicyTests(unittest.TestCase):
    def test_collection_dispatch_requires_final_collection_status_only(self):
        from application.pay.pay import _is_collection_dispatch_enabled

        payment = {
            "wallet_status": 1,
            "account_accno": "98525348",
            "collection_status": 1,
            "payment_status": 1,
            "payment_certified": 1,
            "manual_status": 0,
        }

        self.assertTrue(_is_collection_dispatch_enabled(payment))
        self.assertTrue(_is_collection_dispatch_enabled(dict(payment, manual_status=1)))
        self.assertTrue(_is_collection_dispatch_enabled(dict(payment, payment_status=0)))
        self.assertTrue(_is_collection_dispatch_enabled(dict(payment, payment_certified=0)))
        self.assertTrue(_is_collection_dispatch_enabled(dict(payment, wallet_status=0)))
        self.assertFalse(_is_collection_dispatch_enabled(dict(payment, collection_status=0)))

    def test_wallet_status_already_includes_selected_account(self):
        from application.pay.pay import _is_collection_dispatch_enabled

        payment = {
            "wallet_status": 1,
            "account_accno": "",
            "collection_status": 1,
            "payment_status": 1,
            "payment_certified": 1,
            "manual_status": 0,
        }

        self.assertTrue(_is_collection_dispatch_enabled(payment))

    def test_collection_sql_has_single_mysql_truth_formula(self):
        from application.pay.pay import _collection_dispatch_extra_sql_condition

        sql = _collection_dispatch_extra_sql_condition("pay", "1010")

        self.assertIn("pay.collection_status = 1", sql)

        self.assertNotIn("pay.wallet_status = 1", sql)
        self.assertNotIn("pay.status = 1", sql)
        self.assertNotIn("pay.certified = 1", sql)
        self.assertNotIn("pay.manual_status = 0", sql)
        self.assertNotIn("bank_type_id = 97", sql)
        self.assertNotIn(" OR ", sql)
        self.assertNotIn("account_accno IS NOT NULL", sql)
        self.assertNotIn("account_accno <> ''", sql)


class EasyPaisaBusinessStatusBackfillTests(unittest.TestCase):
    def test_backfill_formula_keeps_manual_lock_ds_only(self):
        try:
            from api.scripts.easypaisa_business_status_backfill import calculate_business_status
        except ModuleNotFoundError:
            from scripts.easypaisa_business_status_backfill import calculate_business_status

        collection_status, payout_status = calculate_business_status(
            {"wallet_status": 1, "status": 1, "certified": 1, "manual_status": 1}
        )

        self.assertEqual(collection_status, 0)
        self.assertEqual(payout_status, 1)

    def test_backfill_formula_blocks_business_when_wallet_offline(self):
        try:
            from api.scripts.easypaisa_business_status_backfill import calculate_business_status
        except ModuleNotFoundError:
            from scripts.easypaisa_business_status_backfill import calculate_business_status

        collection_status, payout_status = calculate_business_status(
            {"wallet_status": 0, "status": 1, "certified": 1, "manual_status": 0}
        )

        self.assertEqual(collection_status, 0)
        self.assertEqual(payout_status, 0)


class EasyPaisaAccountSelectionBusinessStatusTests(unittest.TestCase):
    def test_account_selection_business_status_respects_manual_lock(self):
        from application.app.login.banks.easypaisa import EasyPaisa

        statuses = EasyPaisa._selected_account_business_status(
            wallet_status=1,
            status=1,
            certified=1,
            manual_status=1,
        )

        self.assertEqual(statuses, {"collection_status": 0, "payout_status": 1})

    def test_account_selection_business_status_blocks_business_when_wallet_offline(self):
        from application.app.login.banks.easypaisa import EasyPaisa

        statuses = EasyPaisa._selected_account_business_status(
            wallet_status=0,
            status=1,
            certified=1,
            manual_status=0,
        )

        self.assertEqual(statuses, {"collection_status": 0, "payout_status": 0})


if __name__ == "__main__":
    unittest.main()
