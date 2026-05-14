import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
EASYPAISA_SOURCE = REPO_ROOT / "api" / "application" / "app" / "login" / "banks" / "easypaisa.py"


class EasyPaisaSecondLoginFallbackSourceTests(unittest.TestCase):
    def read_source(self):
        return EASYPAISA_SOURCE.read_text()

    def test_second_login_upstream_error_falls_back_to_login_step1(self):
        source = self.read_source()
        second_login_block = source.split("async def second_login_http", 1)[1].split("async def active_account_http", 1)[0]

        self.assertIn("await asyncio.sleep(2)", second_login_block)
        self.assertIn("retry_result = await self._perform_second_login(session_data)", second_login_block)
        # 501 走 fallback
        self.assertIn("return await self._fallback_to_first_login(session_data, redis_key, reason=message)", second_login_block)
        # 501 检测
        self.assertIn("'501' in str(message) or 'AccountInvalid' in str(message)", second_login_block)
        # 防循环
        self.assertIn("fallback_from", second_login_block)

    def test_fallback_session_keeps_pin_code_and_releases_login_locks(self):
        source = self.read_source()
        fallback_block = source.split("async def _fallback_to_first_login", 1)[1].split("def _get_payment_fingerprint_path", 1)[0]

        self.assertIn("'pinCode': session_data.get('pinCode', '')", fallback_block)
        self.assertNotIn("'pin': session_data.get('pin'", fallback_block)
        self.assertIn("'fallback_from': 'secondLogin'", fallback_block)
        self.assertIn("'code': 'SL_RESTARTED'", fallback_block)
        self.assertIn("self._login_lock_payment_key(payment_id)", fallback_block)
        self.assertIn("self._login_lock_phone_key(phone)", fallback_block)

    def test_server_busy_helper_detects_423_and_server_busy(self):
        source = self.read_source()
        helper_block = source.split("def _is_server_busy", 1)[1].split("async def _fallback_to_first_login", 1)[0]

        self.assertIn("'423' in str(message)", helper_block)
        self.assertIn("'ServerBusy' in str(message)", helper_block)


if __name__ == "__main__":
    unittest.main()
