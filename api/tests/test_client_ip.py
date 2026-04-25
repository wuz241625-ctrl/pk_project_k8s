import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from application.client_ip import resolve_client_ip


class ClientIpTests(unittest.TestCase):
    def test_prefers_x_real_ip_from_trusted_proxy(self):
        headers = {
            "X-Real-IP": "103.135.100.192",
            "X-Forwarded-For": "103.135.100.192, 10.244.0.2",
        }

        self.assertEqual(resolve_client_ip(headers, "10.244.0.2"), "103.135.100.192")

    def test_uses_first_forwarded_ip_when_real_ip_missing(self):
        headers = {"X-Forwarded-For": "103.135.100.192, 10.244.0.2"}

        self.assertEqual(resolve_client_ip(headers, "10.244.0.2"), "103.135.100.192")

    def test_does_not_trust_spoofed_cf_connecting_ip_from_proxy_chain(self):
        headers = {"CF-Connecting-IP": "8.8.8.8"}

        self.assertEqual(resolve_client_ip(headers, "10.244.0.2"), "10.244.0.2")

    def test_ignores_forwarded_headers_from_untrusted_remote_peer(self):
        headers = {"X-Forwarded-For": "103.135.100.192"}

        self.assertEqual(resolve_client_ip(headers, "8.8.4.4"), "8.8.4.4")


if __name__ == "__main__":
    unittest.main()
