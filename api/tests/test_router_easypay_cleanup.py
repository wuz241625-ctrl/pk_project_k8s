import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import router as router_module


class RouterEasypayCleanupTests(unittest.TestCase):
    def _route_patterns(self):
        routes = getattr(router_module, "urls", None)
        if routes is None and hasattr(router_module, "build_urls"):
            routes = router_module.build_urls(enable_local_mock=False)
        self.assertIsNotNone(routes)
        return {route.matcher.regex.pattern for route in routes}

    def test_router_does_not_expose_easypay_web_redirect_or_ipn_routes(self):
        patterns = self._route_patterns()

        self.assertNotIn("/easypay_notify$", patterns)
        self.assertNotIn("/easypay_ipn$", patterns)
        self.assertNotIn("/easypay_bridge/start/(?P<token>\\S+)$", patterns)
        self.assertNotIn("/easypay_bridge/callback/(?P<bridge_id>[^/]+)$", patterns)
        self.assertNotIn("/easypay_bridge/(?P<bridge_id>[^/]+)/(?P<proxy_path>.*)$", patterns)
        self.assertNotIn("/localmock/pay/(?P<order_code>\\S+)$", patterns)
        self.assertNotIn("/localmock/action/(?P<order_code>\\S+)$", patterns)

    def test_router_keeps_easypay_soap_initiate_route(self):
        patterns = self._route_patterns()

        self.assertIn("/easypay/initiate$", patterns)


if __name__ == "__main__":
    unittest.main()
