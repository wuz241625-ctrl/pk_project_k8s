import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

API_ROOT = str(Path(__file__).resolve().parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


class FakeRedis:
    def __init__(self):
        self.storage = {}

    async def get(self, key):
        return self.storage.get(key)

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        return True

    async def set(self, key, value, ex=None):
        self.storage[key] = value
        return True

    async def delete(self, key):
        self.storage.pop(key, None)
        return True

    async def ttl(self, key):
        return 300

    async def expire(self, key, ttl):
        return True


def _make_ep():
    handler = MagicMock()
    handler.redis = FakeRedis()
    handler.current_user = MagicMock(id=33049)
    handler.current_user.hash_trade = "unused"
    handler.db_orm = MagicMock()
    ep = EasyPaisa(handler)
    ep._verify_payment_password_bcrypt = AsyncMock()
    ep._check_login_failed_attempts = AsyncMock(return_value=False)
    ep._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "x", "lock_value": "y"})
    ep._release_payment_interface_lock = AsyncMock()
    ep._select_proxy_ip = AsyncMock(return_value="")
    return ep


def _payload(phone="03999999999"):
    return {
        "bankname": "easypaisa",
        "phone": phone,
        "password": "trade_pwd",
        "pin": "14725",
        "name": "Test",
        "step": "complete_login",
    }


def _bound():
    return {
        "id": 533264,
        "phone": "03445021275",
        "user_id": 33049,
        "pin": "11223",
        "wallet_status": 0,
        "fingerprint_path": None,
    }


class PreLoginBranchingTests(unittest.TestCase):
    def test_new_number_uses_loginstep1_classifier_not_registered_probe(self):
        async def run():
            ep = _make_ep()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "otp_sent", "code": 100, "message": "otp"}
            )
            ep._is_account_registered = AsyncMock(side_effect=AssertionError("不得调用 isAccountRegistered"))
            ep._try_secondlogin_fastpath = AsyncMock()

            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http(_payload())

            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_SENT)
            self.assertEqual(result["data"]["next_step"], "verify_otp")
            ep._perform_loginstep1.assert_awaited_once()
            ep._try_secondlogin_fastpath.assert_not_awaited()

        asyncio.run(run())

    def test_new_number_direct_success_without_local_fp_requests_fingerprint_upload(self):
        async def run():
            ep = _make_ep()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "direct_success", "code": 200, "message": "ok"}
            )
            ep._save_payment = AsyncMock(return_value=778899)

            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http(_payload())

            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_VERIFIED)
            self.assertEqual(result["data"]["next_step"], "upload_fingerprint")
            self.assertEqual(result["data"]["next_phase"], "fingerprintUploadRequired")

        asyncio.run(run())

    def test_bound_payment_secondlogin_success_skips_loginstep1(self):
        async def run():
            ep = _make_ep()
            ep._try_secondlogin_fastpath = AsyncMock(
                return_value={
                    "status": "success",
                    "data": {
                        "phase": LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                        "next_step": "select_accts",
                    },
                }
            )
            ep._perform_loginstep1 = AsyncMock()

            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=_bound())):
                result = await ep.pre_login_http(_payload(phone="03445021275"))

            self.assertEqual(result["data"]["phase"], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            ep._try_secondlogin_fastpath.assert_awaited_once()
            ep._perform_loginstep1.assert_not_awaited()

        asyncio.run(run())

    def test_bound_payment_secondlogin_fallthrough_uses_loginstep1(self):
        async def run():
            ep = _make_ep()
            ep._try_secondlogin_fastpath = AsyncMock(return_value=None)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "otp_sent", "code": 100, "message": "otp"}
            )

            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=_bound())):
                result = await ep.pre_login_http(_payload(phone="03445021275"))

            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_SENT)
            ep._try_secondlogin_fastpath.assert_awaited_once()
            ep._perform_loginstep1.assert_awaited_once()

        asyncio.run(run())

    def test_bound_payment_otp_success_reuses_local_fingerprint(self):
        async def run():
            ep = _make_ep()
            redis_key = "pre_login_easypaisa_533264"
            zip_path = Path(__file__).with_name("old_fp.zip")
            zip_path.write_bytes(b"old-fingerprint")
            self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
            session = {
                "id": 533264,
                "phone": "03445021275",
                "bankname": "easypaisa",
                "status": LoginStatus.OTP_SENT,
                "status_history": [LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_SENT],
                "pinCode": "client_pin_should_not_be_used",
                "reuse_local_fingerprint_after_otp": True,
                "local_fingerprint_path": str(zip_path),
            }
            ep.redis.storage[redis_key] = json.dumps(session)
            ep._verify_otp = AsyncMock(return_value={"data": {"requestId": "req-1"}})
            ep._save_payment = AsyncMock(return_value=533264)
            ep._hydrate_second_login_pin_from_db = AsyncMock(return_value=True)
            ep._call_upload_data = AsyncMock(return_value=True)
            ep._call_verify_fingerprint = AsyncMock(return_value={"outcome": "success"})
            ep._call_second_login = AsyncMock(return_value={"outcome": "success"})
            ep._call_query_account_list = AsyncMock(
                return_value={
                    "outcome": "success",
                    "accounts_json": json.dumps([{"accno": "88521642", "accountStatus": "ACTIVE"}]),
                }
            )

            result = await ep.verify_otp_http(
                {"bankname": "easypaisa", "payment_id": 533264, "otp": "123456"}
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["data"]["phase"], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            self.assertEqual(result["data"]["next_step"], "second_login")
            ep._call_upload_data.assert_awaited_once()
            ep._call_verify_fingerprint.assert_awaited_once()
            ep._call_second_login.assert_awaited_once()
            ep._call_query_account_list.assert_awaited_once()

        asyncio.run(run())

    def test_bound_payment_direct_success_reuses_local_fingerprint_without_missing_helper(self):
        async def run():
            ep = _make_ep()
            zip_path = Path(__file__).with_name("old_fp_direct.zip")
            zip_path.write_bytes(b"old-fingerprint")
            self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
            bound = _bound()
            bound["fingerprint_path"] = str(zip_path)
            ep._try_secondlogin_fastpath = AsyncMock(return_value=None)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "direct_success", "code": 200, "message": "ok"}
            )
            ep._save_payment = AsyncMock(return_value=533264)
            ep._hydrate_second_login_pin_from_db = AsyncMock(return_value=True)
            ep._call_upload_data = AsyncMock(return_value=True)
            ep._call_verify_fingerprint = AsyncMock(return_value={"outcome": "success"})
            ep._call_second_login = AsyncMock(return_value={"outcome": "success"})
            ep._call_query_account_list = AsyncMock(
                return_value={
                    "outcome": "success",
                    "accounts_json": json.dumps([{"accno": "88521642", "accountStatus": "ACTIVE"}]),
                }
            )

            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=bound)):
                result = await ep.pre_login_http(_payload(phone="03445021275"))

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["data"]["phase"], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            self.assertEqual(result["data"]["next_step"], "second_login")
            ep._call_upload_data.assert_awaited_once()
            ep._call_verify_fingerprint.assert_awaited_once()
            ep._call_second_login.assert_awaited_once()

        asyncio.run(run())

    def test_bound_payment_local_fingerprint_rejected_routes_to_upload(self):
        async def run():
            ep = _make_ep()
            zip_path = Path(__file__).with_name("old_fp_rejected.zip")
            zip_path.write_bytes(b"old-fingerprint")
            self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
            session = {
                "id": 533264,
                "phone": "03445021275",
                "bankname": "easypaisa",
                "status": LoginStatus.OTP_VERIFIED,
                "status_history": [LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_VERIFIED],
                "pinCode": "11223",
            }
            ep._call_upload_data = AsyncMock(return_value=True)
            ep._call_verify_fingerprint = AsyncMock(
                return_value={"outcome": "rejected", "message": "FingerprintRejected"}
            )

            result = await ep._reuse_local_fingerprint_after_otp(
                "pre_login_easypaisa_533264", session, str(zip_path)
            )

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["data"]["code"], "FP_UPSTREAM_REJECTED")
            self.assertEqual(result["data"]["next_step"], "upload_fingerprint")
            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_VERIFIED)
            ep._call_upload_data.assert_awaited_once()
            ep._call_verify_fingerprint.assert_awaited_once()

        asyncio.run(run())

    def test_loginstep1_501_forces_needs_relogin(self):
        async def run():
            ep = _make_ep()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "offline_501", "code": 501, "message": "AccountInvalid"}
            )
            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http(_payload())
            self.assertEqual(result["data"]["phase"], LoginStatus.NEEDS_RELOGIN)
            self.assertEqual(result["data"]["code"], "SL_NEEDS_RELOGIN")

        asyncio.run(run())

    def test_loginstep1_423_returns_retry_with_pre_login_phase(self):
        async def run():
            ep = _make_ep()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "server_busy", "code": 423, "message": "busy"}
            )
            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http(_payload())
            self.assertEqual(result["data"]["code"], "EP_RETRY")
            self.assertEqual(result["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)
            self.assertEqual(result["data"]["next_step"], "pre_login")

        asyncio.run(run())

    def test_loginstep1_rejected_returns_upstream_error(self):
        async def run():
            ep = _make_ep()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "rejected", "code": 500, "message": "CommonError"}
            )
            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http(_payload())
            self.assertEqual(result["data"]["code"], "EP_UPSTREAM_ERROR")
            self.assertEqual(result["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)

        asyncio.run(run())

    def test_loginstep1_network_error_returns_upstream_error(self):
        async def run():
            ep = _make_ep()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "network_error", "code": 503, "message": "NetworkError"}
            )
            with patch.object(ep, "_check_payment", new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http(_payload())
            self.assertEqual(result["data"]["code"], "EP_UPSTREAM_ERROR")
            self.assertEqual(result["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
