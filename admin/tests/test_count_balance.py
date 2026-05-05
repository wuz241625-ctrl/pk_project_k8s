import os
import sys
import unittest
from decimal import Decimal


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.count.count import normalize_balance_count


class CountBalanceTests(unittest.TestCase):
    def test_normalize_balance_count_treats_empty_partner_sums_as_zero(self):
        count = normalize_balance_count({
            "balance_p": None,
            "balance_p_frozen": None,
            "balance_p_deposit": None,
            "balance_m": Decimal("0.0000"),
            "balance_m_frozen": Decimal("0.0000"),
            "balance_p_inside": None,
            "balance_p_frozen_inside": None,
            "balance_p_outside": None,
            "balance_p_frozen_outside": None,
        })

        self.assertEqual(count["balance_p"], Decimal("0"))
        self.assertEqual(count["balance"], Decimal("0.0000"))


if __name__ == "__main__":
    unittest.main()
