import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EASYPAISA_WORKER_SOURCE = REPO_ROOT / "api" / "jobs" / "pakistanpay_v2.py"


class EasyPaisaMysqlEligibilityTests(unittest.TestCase):
    def test_collection_requires_final_collection_status_only(self):
        from application.pay.pay import _is_collection_dispatch_enabled

        base = {
            "wallet_status": 1,
            "account_accno": "98525348",
            "collection_status": 1,
            "status": 1,
            "certified": 1,
            "manual_status": 0,
        }

        self.assertTrue(_is_collection_dispatch_enabled(base))
        self.assertFalse(_is_collection_dispatch_enabled(dict(base, collection_status=0)))
        self.assertTrue(_is_collection_dispatch_enabled(dict(base, wallet_status=0)))
        self.assertTrue(_is_collection_dispatch_enabled(dict(base, account_accno="")))
        self.assertTrue(_is_collection_dispatch_enabled(dict(base, status=0, certified=0, manual_status=1)))

    def test_payout_allows_manual_lock_but_requires_payout_status(self):
        from application.payment_eligibility import can_dispatch_df

        self.assertTrue(
            can_dispatch_df(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "payout_status": 1,
                    "status": 1,
                    "certified": 1,
                    "manual_status": 1,
                }
            )
        )
        self.assertFalse(
            can_dispatch_df(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "payout_status": 0,
                    "status": 1,
                    "certified": 1,
                    "manual_status": 1,
                }
            )
        )

    def test_statement_collection_ignores_business_switches(self):
        from application.payment_eligibility import can_collect_statement

        self.assertTrue(
            can_collect_statement(
                {
                    "wallet_status": 1,
                    "account_accno": "98525348",
                    "collection_status": 0,
                    "payout_status": 0,
                    "status": 0,
                    "certified": 0,
                    "manual_status": 1,
                }
            )
        )
        self.assertFalse(can_collect_statement({"wallet_status": 0, "account_accno": "98525348"}))
        self.assertTrue(can_collect_statement({"wallet_status": 1, "account_accno": ""}))

    def test_collection_sql_contains_final_mysql_truth_conditions(self):
        from application.pay.pay import _collection_dispatch_extra_sql_condition

        sql = _collection_dispatch_extra_sql_condition("pay", "1010")

        for fragment in ("pay.collection_status = 1", "find_in_set('1010'"):
            self.assertIn(fragment, sql)
        self.assertNotIn("pay.wallet_status = 1", sql)
        self.assertNotIn("pay.status = 1", sql)
        self.assertNotIn("pay.certified = 1", sql)
        self.assertNotIn("pay.manual_status = 0", sql)
        self.assertNotIn("bank_type_id = 97", sql)
        self.assertNotIn(" OR ", sql)
        self.assertNotIn("account_accno IS NOT NULL", sql)
        self.assertNotIn("account_accno <> ''", sql)

    def test_easypaisa_statement_scheduler_requires_payer_phone_for_ds_orders(self):
        source = EASYPAISA_WORKER_SOURCE.read_text()

        due_source = source[
            source.index("    def fetch_due_statement_payment_ids"):
            source.index("    def fetch_statement_account_context")
        ]
        scan_source = source[
            source.index("    def fetch_due_statement_scan_context"):
            source.index("    def fetch_due_statement_payment_ids")
        ]

        self.assertIn("od.utr IS NOT NULL", due_source)
        self.assertIn("od.utr <> ''", due_source)
        self.assertIn("utr IS NOT NULL", scan_source)
        self.assertIn("utr <> ''", scan_source)


if __name__ == "__main__":
    unittest.main()
