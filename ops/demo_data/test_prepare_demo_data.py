import datetime as dt
import decimal
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from prepare_demo_data import (
    DEMO_IP,
    build_insert_sql,
    build_permission_csv,
    compute_opening_balances_from_events,
    compute_opening_balances,
    demo_order_created_at,
    ds_timestamps,
    generate_demo_api_key,
    generate_demo_totp_secret,
    merge_csv_values,
    normalize_realistic_merchants,
    normalize_amount,
    quote_identifier,
)


class DemoDataHelperTests(unittest.TestCase):
    def test_permission_csv_includes_matching_permissions_and_ancestors(self):
        permissions = [
            {"id": 1, "pid": 0, "path": ""},
            {"id": 2, "pid": 1, "path": "/merchant"},
            {"id": 3, "pid": 2, "path": "/merchant/getmerchant"},
            {"id": 4, "pid": 1, "path": "/order"},
            {"id": 5, "pid": 4, "path": "/order/getorderds"},
            {"id": 6, "pid": 0, "path": "/unrelated"},
        ]

        csv = build_permission_csv(permissions, ["/merchant/%"])

        self.assertEqual(csv, "1,2,3")

    def test_ds_timestamps_follow_order_status(self):
        created = dt.datetime(2026, 4, 25, 10, 0, 0)

        pending = ds_timestamps(created, 0)
        success = ds_timestamps(created, 3)

        self.assertEqual(pending, (created, None, None, None))
        self.assertEqual(
            success,
            (
                created,
                created + dt.timedelta(minutes=5),
                created + dt.timedelta(minutes=10),
                created + dt.timedelta(minutes=12),
            ),
        )

    def test_normalize_amount_keeps_reasonable_demo_range(self):
        self.assertEqual(normalize_amount(decimal.Decimal("0.5"), 1), decimal.Decimal("260.00"))
        self.assertEqual(normalize_amount(decimal.Decimal("999999"), 2), decimal.Decimal("420.00"))
        self.assertEqual(normalize_amount(decimal.Decimal("1234.56"), 3), decimal.Decimal("1234.56"))

    def test_build_insert_sql_is_stable_and_uses_named_columns(self):
        sql, values = build_insert_sql("merchant", {"id": 1, "ip": DEMO_IP, "name": "Demo"})

        self.assertEqual(sql, "INSERT INTO merchant (`id`, `ip`, `name`) VALUES (%s, %s, %s)")
        self.assertEqual(values, [1, DEMO_IP, "Demo"])

    def test_generate_demo_merchant_secrets_have_safe_shapes(self):
        self.assertRegex(generate_demo_api_key(), r"^[0-9a-f]{32}$")
        self.assertRegex(generate_demo_totp_secret(), r"^[A-Z2-7]{16}$")

    def test_realistic_merchants_do_not_keep_source_keys(self):
        rows = normalize_realistic_merchants(
            [
                {
                    "id": 195,
                    "cellphone": "111112233",
                    "name": "PAKGAMES",
                    "hash_login": "old_hash",
                    "gg_key": "SOURCEGOOGLEKEY1",
                    "mc_key": "source_merchant_key",
                    "status": 0,
                    "status_df": 0,
                    "target_payment": "1,2",
                    "ip": "1.1.1.1",
                    "ip_df": "2.2.2.2",
                    "balance": decimal.Decimal("1.0000"),
                    "balance_frozen": decimal.Decimal("2.0000"),
                    "pid": None,
                }
            ],
            "demo_hash",
            DEMO_IP,
        )

        self.assertEqual(rows[0]["hash_login"], "demo_hash")
        self.assertNotEqual(rows[0]["gg_key"], "SOURCEGOOGLEKEY1")
        self.assertNotEqual(rows[0]["mc_key"], "source_merchant_key")
        self.assertRegex(rows[0]["gg_key"], r"^[A-Z2-7]{16}$")
        self.assertRegex(rows[0]["mc_key"], r"^[0-9a-f]{32}$")
        self.assertIsNone(rows[0]["target_payment"])
        self.assertEqual(rows[0]["ip"], DEMO_IP)
        self.assertEqual(rows[0]["ip_df"], DEMO_IP)

    def test_opening_balances_keep_demo_ledger_non_negative(self):
        merchants = [{"id": 9101}, {"id": 9102}]
        base_time = dt.datetime(2026, 4, 25, 10, 0, 0)
        rows = [
            {
                "code": "DFDEMO00001",
                "status": 3,
                "merchant_id": 9101,
                "realpay": decimal.Decimal("50000.0000"),
                "time_create": base_time,
            },
            {
                "code": "DSDEMO00002",
                "status": 3,
                "merchant_id": 9101,
                "realpay": decimal.Decimal("2000.0000"),
                "time_create": base_time + dt.timedelta(minutes=1),
            },
            {
                "code": "DFDEMO00003",
                "status": 3,
                "merchant_id": 9102,
                "realpay": decimal.Decimal("1000.0000"),
                "time_create": base_time,
            },
        ]

        balances = compute_opening_balances(merchants, [], rows)

        self.assertEqual(balances[9101], decimal.Decimal("60000.0000"))
        self.assertEqual(balances[9102], decimal.Decimal("14000.0000"))

    def test_demo_order_dates_cover_each_merchant_today_before_aging(self):
        now = dt.datetime(2026, 4, 25, 16, 0, 0)

        created_days = [
            demo_order_created_at(now, index, merchant_count=8, minute_step=11).date()
            for index in range(1, 9)
        ]

        self.assertEqual(created_days, [now.date()] * 8)
        self.assertEqual(
            demo_order_created_at(now, 9, merchant_count=8, minute_step=11).date(),
            (now - dt.timedelta(days=1)).date(),
        )

    def test_quote_identifier_rejects_unsafe_database_names(self):
        self.assertEqual(quote_identifier("pakistan_backup_20260425"), "`pakistan_backup_20260425`")
        with self.assertRaises(ValueError):
            quote_identifier("pakistan;drop")

    def test_merge_csv_values_preserves_order_and_dedupes(self):
        merged = merge_csv_values("103.135.100.192, 1.54.194.2", ["1.54.194.2", "47.238.21.150"])

        self.assertEqual(merged, "103.135.100.192,1.54.194.2,47.238.21.150")

    def test_opening_balances_cover_realistic_negative_swing(self):
        base_time = dt.datetime(2026, 4, 25, 10, 0, 0)
        events = [
            {
                "user_type": 1,
                "user_id": 195,
                "amount": decimal.Decimal("-250000.0000"),
                "time_create": base_time,
            },
            {
                "user_type": 1,
                "user_id": 195,
                "amount": decimal.Decimal("50000.0000"),
                "time_create": base_time + dt.timedelta(minutes=1),
            },
        ]

        balances = compute_opening_balances_from_events([195], events, 1, decimal.Decimal("100000.0000"))

        self.assertEqual(balances[195], decimal.Decimal("260000.0000"))


if __name__ == "__main__":
    unittest.main()
