import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

API_ROOT = str(Path(__file__).resolve().parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from application.app.login.banks.easypaisa import EasyPaisa


def _make_ep():
    handler = MagicMock()
    handler.current_user = MagicMock(id=33049)
    ep = EasyPaisa(handler)
    ep._build_send_otp_request = MagicMock(return_value="enc")
    ep._log_response = MagicMock()
    ep._mark_payment_official_501_offline = AsyncMock(return_value=True)
    return ep


def _resp(code):
    return SimpleNamespace(
        status_code=200,
        text=json.dumps({"code": code, "msg": f"msg{code}", "data": None}),
    )


SESSION = {
    "id": "533264",
    "payment_id": "533264",
    "phone": "03445021275",
    "pinCode": "11223",
}


class LoginStep1ClassifierTests(unittest.TestCase):
    def test_code_200_is_direct_success(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(200))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "direct_success")
            self.assertEqual(out["code"], 200)

        asyncio.run(run())

    def test_code_100_is_otp_sent(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(100))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "otp_sent")

        asyncio.run(run())

    def test_code_501_offline_and_marks_offline(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(501))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "offline_501")
            ep._mark_payment_official_501_offline.assert_awaited_once()

        asyncio.run(run())

    def test_code_423_is_server_busy(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(423))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "server_busy")

        asyncio.run(run())

    def test_code_503_is_network_error(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(503))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "network_error")

        asyncio.run(run())

    def test_code_403_and_500_are_rejected(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(403))
            self.assertEqual((await ep._perform_loginstep1(dict(SESSION)))["outcome"], "rejected")
            ep.retry_make_request = MagicMock(return_value=_resp(500))
            self.assertEqual((await ep._perform_loginstep1(dict(SESSION)))["outcome"], "rejected")

        asyncio.run(run())

    def test_empty_response_is_network_error(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=None)
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "network_error")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
