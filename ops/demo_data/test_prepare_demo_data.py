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
    compute_opening_balances,
    ds_timestamps,
    normalize_amount,
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


if __name__ == "__main__":
    unittest.main()
