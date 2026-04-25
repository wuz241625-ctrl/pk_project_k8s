import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.client_ip import resolve_client_ip, sanitize_request_body


class ClientIpTests(unittest.TestCase):
    def test_prefers_x_real_ip_from_trusted_proxy(self):
        headers = {
            "X-Real-IP": "103.135.100.192",
            "X-Forwarded-For": "103.135.100.192, 10.244.0.0",
        }

        self.assertEqual(resolve_client_ip(headers, "10.244.0.0"), "103.135.100.192")

    def test_uses_first_forwarded_ip_when_real_ip_missing(self):
        headers = {"X-Forwarded-For": "103.135.100.192, 10.244.0.0"}

        self.assertEqual(resolve_client_ip(headers, "10.244.0.0"), "103.135.100.192")

    def test_does_not_trust_spoofed_cf_connecting_ip_from_proxy_chain(self):
        headers = {"CF-Connecting-IP": "8.8.8.8"}

        self.assertEqual(resolve_client_ip(headers, "10.244.0.0"), "10.244.0.0")

    def test_redacts_login_secret_fields_from_request_body(self):
        body = b'{"username":"18088880000","password":"123456","googlecode":"137103"}'

        result = sanitize_request_body(body)

        self.assertIn("18088880000", result)
        self.assertNotIn("123456", result)
        self.assertNotIn("137103", result)
        self.assertIn("***", result)


if __name__ == "__main__":
    unittest.main()
