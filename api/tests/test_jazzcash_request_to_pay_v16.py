import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


ORDER_SOURCE = REPO_ROOT / "api" / "application" / "pay" / "order.py"


class JazzCashRequestToPayV16SourceTests(unittest.TestCase):
    def read_source(self):
        return ORDER_SOURCE.read_text()

    def test_request_to_pay_uses_gateway_form_body(self):
        source = self.read_source()

        self.assertIn("from application.jazzcash_gateway import build_form_body", source)
        self.assertIn("post_data = build_form_body(", source)
        self.assertNotIn("data_base64 = base64.b64encode", source)

    def test_raast_id_remains_easypaisa_only(self):
        source = self.read_source()

        self.assertIn("merchantRequestToPay\" if type == 'jazz' else \"merchantRequestToPayEp", source)
        self.assertIn("if type == 'easypaisa':", source)
        self.assertIn("inner_payload[\"raast_id\"]", source)


if __name__ == "__main__":
    unittest.main()
