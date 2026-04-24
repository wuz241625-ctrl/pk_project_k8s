import sys
import unittest
from pathlib import Path

MERCHANT_ROOT = Path(__file__).resolve().parents[1]
if str(MERCHANT_ROOT) not in sys.path:
    sys.path.insert(0, str(MERCHANT_ROOT))

from merchant.application.order import order


class OrderQueryHelperTest(unittest.TestCase):
    def test_only_merchant_code_should_not_trigger_default_range(self):
        condition = {"merchant_code": "M123"}

        result = order.should_use_default_order_range(condition, between=None)

        self.assertFalse(result)

    def test_empty_condition_without_between_should_trigger_default_range(self):
        result = order.should_use_default_order_range({}, between=None)

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
