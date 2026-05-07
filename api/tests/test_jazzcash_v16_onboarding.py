import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


JAZZCASH_SOURCE = REPO_ROOT / "api" / "application" / "app" / "login" / "banks" / "jazzcash.py"


class JazzCashV16OnboardingSourceTests(unittest.TestCase):
    def read_source(self):
        return JAZZCASH_SOURCE.read_text()

    def test_no_legacy_api_version_branches_remain(self):
        source = self.read_source()

        self.assertNotIn("JAZZCASH_API_VERSION", source)
        self.assertNotIn("v1.2", source)
        self.assertNotIn("v1.5", source)
        self.assertIn("v1.6", source)

    def test_login_step2_uses_v16_flags(self):
        source = self.read_source()

        self.assertIn('"should_verify_otpcode": False', source)
        self.assertIn('"should_verify_fingerprint": True', source)


    def test_v16_pre_login_starts_with_send_otp_but_does_not_mark_fingerprint_uploaded(self):
        source = self.read_source()
        pre_login_block = source.split("async def pre_login_http", 1)[1].split("async def send_otp_http", 1)[0]

        self.assertIn("next_step = 'send_otp'", pre_login_block)
        self.assertIn("fingerprint_uploaded = False", pre_login_block)
        self.assertNotIn("v1.6流程：跳过指纹检查", pre_login_block)
        self.assertNotIn("跳过指纹上传", pre_login_block)

    def test_send_otp_routes_to_fingerprint_upload_before_verify(self):
        source = self.read_source()
        send_otp_block = source.split("async def send_otp_http", 1)[1].split("async def verify_otp_http", 1)[0]

        self.assertIn("'next_step': 'upload_fingerprint'", send_otp_block)
        self.assertIn("OTP发送成功，请上传指纹后再验证OTP", send_otp_block)
        self.assertNotIn("'next_status': LoginStatus.VERIFY_OTP", send_otp_block)

    def test_upload_fingerprint_routes_to_verify_otp_and_marks_session_uploaded(self):
        source = self.read_source()
        upload_block = source.split("async def upload_fingerprint_http", 1)[1].split("async def _is_logined", 1)[0]

        self.assertIn("'fingerprint_uploaded': True", upload_block)
        self.assertIn("'next_step': 'verify_otp'", upload_block)
        self.assertNotIn("'next_step': 'send_otp'", upload_block)

    def test_verify_otp_requires_uploaded_fingerprint(self):
        source = self.read_source()
        verify_block = source.split("async def verify_otp_http", 1)[1].split("async def active_account_http", 1)[0]

        self.assertIn("session_data.get('fingerprint_uploaded')", verify_block)
        self.assertIn("Please upload fingerprint before OTP verification", verify_block)

    def test_payment_status_does_not_return_pin(self):
        source = self.read_source()
        status_block = source.split("async def payment_status_http", 1)[1].split("async def _send_otp", 1)[0]

        self.assertNotIn('"pin"', status_block)
        self.assertNotIn("pinCode", status_block)


if __name__ == "__main__":
    unittest.main()
