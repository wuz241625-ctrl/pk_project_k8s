import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

API_ROOT = str(Path(__file__).resolve().parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl_map = {}

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        self.ttl_map[key] = ttl
        return True


def _make_ep():
    handler = MagicMock()
    handler.current_user = MagicMock(id=33049)
    ep = EasyPaisa(handler)
    ep.redis = FakeRedis()
    ep._persist_session_data = AsyncMock(return_value=ep.expire_time_login_pending)
    return ep


def _session():
    return {
        "status": LoginStatus.PRE_LOGIN_CREATED,
        "status_history": [LoginStatus.PRE_LOGIN_CREATED],
        "id": "533264",
        "payment_id": "533264",
        "phone": "03445021275",
        "bankname": "easypaisa",
        "pinCode": "client_pin_should_not_be_used",
    }


REDIS_KEY = "pre_login_easypaisa_533264"
BOUND = {"id": 533264, "phone": "03445021275", "pin": "11223"}


class FastpathTests(unittest.TestCase):
    def test_success_queries_accounts_and_enters_account_selection(self):
        async def run():
            ep = _make_ep()
            ep._call_second_login = AsyncMock(return_value={"outcome": "success"})
            ep._call_query_account_list = AsyncMock(
                return_value={"outcome": "success", "accounts_json": '[{"accno":"1"}]'}
            )
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            ep._call_second_login.assert_awaited_once()
            _, kwargs = ep._call_second_login.await_args
            self.assertIs(kwargs.get("with_pwd"), True)
            self.assertEqual(out["data"]["phase"], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            self.assertEqual(out["data"]["next_step"], "select_accts")

        asyncio.run(run())

    def test_needs_pin_change_returns_awaiting_pin_envelope(self):
        async def run():
            ep = _make_ep()
            ep._call_second_login = AsyncMock(return_value={"outcome": "needs_pin_change"})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertEqual(out["data"]["code"], "SL_NEEDS_PIN_CHANGE")
            self.assertEqual(out["data"]["phase"], LoginStatus.AWAITING_PIN_CHANGE)

        asyncio.run(run())

    def test_cooldown_keeps_pre_login_state(self):
        async def run():
            ep = _make_ep()
            ep._call_second_login = AsyncMock(return_value={"outcome": "cooldown", "cd_until": 123})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertEqual(out["data"]["code"], "SL_COOLDOWN")
            self.assertEqual(out["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)
            self.assertEqual(out["data"]["cd_until"], 123)

        asyncio.run(run())

    def test_needs_relogin_returns_none_for_fallthrough(self):
        async def run():
            ep = _make_ep()
            ep._call_second_login = AsyncMock(return_value={"outcome": "needs_relogin"})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertIsNone(out)

        asyncio.run(run())

    def test_urm90040_returns_none_for_fallthrough(self):
        async def run():
            ep = _make_ep()
            ep._call_second_login = AsyncMock(
                return_value={"outcome": "urm90040", "message": "URM90040"}
            )
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertIsNone(out)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
