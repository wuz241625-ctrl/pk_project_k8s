import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
API_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from router_lakshmi import prefixed_urls


class LakshmiSellingRouteTests(unittest.TestCase):
    def test_only_single_payment_selling_route_is_registered(self):
        route_patterns = [
            route[0] if isinstance(route, tuple) else route.regex.pattern
            for route in prefixed_urls
        ]

        self.assertIn("/v1/user/upi/(?P<payment_id>[0-9]+)/selling$", route_patterns)
        self.assertNotIn("/v1/user/upi/payment/selling$", route_patterns)


if __name__ == "__main__":
    unittest.main()
