import base64
import hashlib
import json
import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


class JazzCashGatewayV16Tests(unittest.TestCase):
    def test_build_form_body_wraps_action_payload_and_signs_base64_plus_secret(self):
        from application.jazzcash_gateway import build_form_body

        body = build_form_body(
            "loginStep1",
            {"account_id": "03001234567", "msisdn": "03001234567", "mpin": "1234"},
            user_id="merchant-user",
            secret="merchant-secret",
            request_id="fixed-request-id",
        )

        self.assertEqual(set(body.keys()), {"user_id", "data", "sign"})
        self.assertEqual(body["user_id"], "merchant-user")

        decoded = json.loads(base64.b64decode(body["data"]).decode("utf-8"))
        self.assertEqual(decoded["id"], "fixed-request-id")
        self.assertEqual(decoded["action"], "loginStep1")
        self.assertEqual(
            decoded["payload"],
            {"account_id": "03001234567", "msisdn": "03001234567", "mpin": "1234"},
        )

        expected_sign = hashlib.md5((body["data"] + "merchant-secret").encode("utf-8")).hexdigest()
        self.assertEqual(body["sign"], expected_sign)

    def test_build_form_body_uses_form_field_names_from_v16_document(self):
        from application.jazzcash_gateway import build_form_body

        body = build_form_body(
            "secondLogin",
            {"account_id": "03001234567"},
            user_id="merchant-user",
            secret="merchant-secret",
            request_id="fixed-request-id",
        )

        self.assertNotIn("payload", body)
        self.assertNotIn("action", body)
        self.assertIn("user_id", body)
        self.assertIn("data", body)
        self.assertIn("sign", body)

    def test_decode_response_accepts_json_string_and_plain_dict(self):
        from application.jazzcash_gateway import decode_response

        decoded = decode_response("{\"code\": 200, \"msg\": \"ok\", \"data\": true}")

        self.assertEqual(decoded["code"], 200)
        self.assertEqual(decoded["msg"], "ok")
        self.assertIs(decoded["data"], True)
        self.assertEqual(decode_response({"code": 501, "msg": "invalid"})["code"], 501)

    def test_classify_code_matches_v16_business_semantics(self):
        from application.jazzcash_gateway import classify_code

        self.assertEqual(classify_code(200)["category"], "success")
        self.assertEqual(classify_code(100)["category"], "success")
        self.assertEqual(classify_code(401)["action"], "relogin")
        self.assertEqual(classify_code(402)["action"], "reroute")
        self.assertEqual(classify_code(423)["action"], "retry")
        self.assertEqual(classify_code(503)["action"], "retry")
        self.assertEqual(classify_code(500)["action"], "manual_confirm")
        self.assertEqual(classify_code(501)["action"], "offline_account")

    def test_calculate_final_status_keeps_manual_lock_collection_only(self):
        from application.jazzcash_gateway import calculate_final_status

        unlocked = calculate_final_status(status=1, certified=1, manual_status=0, wallet_status=1)
        self.assertEqual(unlocked, {"wallet_status": 1, "collection_status": 1, "payout_status": 1})

        manual_locked = calculate_final_status(status=1, certified=1, manual_status=1, wallet_status=1)
        self.assertEqual(manual_locked, {"wallet_status": 1, "collection_status": 0, "payout_status": 1})

        offline = calculate_final_status(status=1, certified=1, manual_status=0, wallet_status=0)
        self.assertEqual(offline, {"wallet_status": 0, "collection_status": 0, "payout_status": 0})


if __name__ == "__main__":
    unittest.main()
