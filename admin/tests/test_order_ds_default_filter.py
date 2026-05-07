import os
import sys
import unittest
from datetime import date, datetime


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.order.order import (
    build_order_ds_default_time_create_between,
    should_apply_order_ds_default_time_create_between,
)


class OrderDsDefaultFilterTests(unittest.TestCase):
    def test_default_time_create_range_ends_at_day_end(self):
        result = build_order_ds_default_time_create_between(datetime(2026, 5, 1, 18, 50, 0))

        self.assertEqual(result["key"], "time_create")
        self.assertEqual(result["start"], date(2026, 5, 1))
        self.assertEqual(result["end"], datetime(2026, 5, 1, 23, 59, 59))

    def test_existing_between_is_not_overwritten_when_code_is_missing(self):
        explicit_between = {
            "key": "time_create",
            "start": "2026-05-01 00:00:00",
            "end": "2026-05-01 23:59:59",
        }

        self.assertFalse(should_apply_order_ds_default_time_create_between({}, explicit_between))

    def test_minimal_channel_filter_can_use_default_without_code_key(self):
        self.assertTrue(should_apply_order_ds_default_time_create_between({"channel_code": 1010}, None))


if __name__ == "__main__":
    unittest.main()
