import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
EASYPAISA_SOURCE = REPO_ROOT / "api" / "application" / "app" / "login" / "banks" / "easypaisa.py"


class EasyPaisaSecondLoginFallbackSourceTests(unittest.TestCase):
    def read_source(self):
        return EASYPAISA_SOURCE.read_text()

    def test_second_login_upstream_error_forces_terminal_relogin(self):
        source = self.read_source()
        second_login_block = source.split("async def second_login_http", 1)[1].split("async def active_account_http", 1)[0]

        self.assertIn("sl = await self._call_second_login(session_data, with_pwd=True)", second_login_block)
        self.assertIn("if outcome != 'success':", second_login_block)
        self.assertIn("return await self._force_terminal_needs_relogin(", second_login_block)
        self.assertIn("'SL_NEEDS_RELOGIN' if outcome == 'needs_relogin' else 'SL_UPSTREAM_ERROR'", second_login_block)
        self.assertNotIn("_fallback_to_first_login(session_data, redis_key", second_login_block)

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
