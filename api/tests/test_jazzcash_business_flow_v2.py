import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.app.login.banks import jazzcash as jazzcash_module
from application.app.login.banks.jazzcash import AccountStatus, ErrorCode, JazzCash, LoginStatus
from application.lakshmi_api.exceptions.api_error import NewApiError
from application.lakshmi_api.controllers import http_login_controller


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl_map = {}
        self.set_buckets = {}
        self.list_buckets = {}
        self.zset_buckets = {}

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.storage:
            return False
        self.storage[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        self.ttl_map[key] = ttl
        return True

    async def delete(self, key):
        existed = key in self.storage
        self.storage.pop(key, None)
        self.ttl_map.pop(key, None)
        return 1 if existed else 0

    async def ttl(self, key):
        if key not in self.storage:
            return -2
        return self.ttl_map.get(key, -1)

    async def sadd(self, key, *values):
        bucket = self.set_buckets.setdefault(key, set())
        before = len(bucket)
        for value in values:
            bucket.add(str(value))
        return len(bucket) - before

    async def srem(self, key, *values):
        bucket = self.set_buckets.setdefault(key, set())
        before = len(bucket)
        for value in values:
            bucket.discard(str(value))
        return before - len(bucket)

    async def smembers(self, key):
        return set(self.set_buckets.get(key, set()))

    async def lrem(self, key, count, value):
        bucket = self.list_buckets.setdefault(key, [])
        target = str(value)
        if count != 0:
            raise NotImplementedError("FakeRedis only supports count=0")
        removed = bucket.count(target)
        self.list_buckets[key] = [item for item in bucket if item != target]
        return removed

    async def rpush(self, key, value):
        bucket = self.list_buckets.setdefault(key, [])
        bucket.append(str(value))
        return len(bucket)

    async def zadd(self, key, mapping):
        bucket = self.zset_buckets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return True

    async def zrem(self, key, *members):
        bucket = self.zset_buckets.setdefault(key, {})
        removed = 0
        for member in members:
            if str(member) in bucket:
                removed += 1
                bucket.pop(str(member), None)
        return removed


class DummySession:
    def __init__(self):
        self.add = MagicMock()
        self.execute = MagicMock()
        self.commit = MagicMock()
        self.rollback = MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class JazzCashBusinessFlowV2Tests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.db_session = DummySession()
        handler = SimpleNamespace(
            redis=self.redis,
            logger=MagicMock(),
            db_orm=SimpleNamespace(sessionmaker=lambda: self.db_session),
            current_user=SimpleNamespace(id=7, hash_trade="hash-trade", cellphone="03000000000"),
        )
        self.jazzcash = JazzCash(handler)
        self.jazzcash.logger = MagicMock()

    def _session(self, status):
        return {
            "id": 533280,
            "partner_id": 7,
            "phone": "03001234567",
            "bankname": "jazzcash",
            "pinCode": "1234",
            "password": "pass",
            "is_new_user": False,
            "name": "tester",
            "status": status,
            "status_history": [status],
            "last_status_change": 0,
            "last_request_time": 0,
            "app_gen_id": "app-gen-id",
            "androidId": "android-id",
            "safetyNetId": "safety-net-id",
            "qr_channel": "1003",
        }

    def test_jazzcash_uses_send_otp_first_api_mode(self):
        self.assertEqual(jazzcash_module.JAZZCASH_API_VERSION, "v1.5")

    def test_jazzcash_has_no_upstream_verify_fingerprint_action(self):
        self.assertNotIn("verify_fingerprint", self.jazzcash.API_ENDPOINTS)

    def test_pre_login_writes_runtime_snapshot_with_qr_channel(self):
        asyncio.run(self._run_pre_login_qr_channel_case())

    async def _run_pre_login_qr_channel_case(self):
        self.jazzcash._check_login_failed_attempts = AsyncMock(return_value=False)
        self.jazzcash._verify_payment_password_bcrypt = AsyncMock(return_value=None)
        self.jazzcash._check_payment = AsyncMock(return_value=None)
        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._select_proxy_ip = AsyncMock(return_value="")

        result = await self.jazzcash.pre_login_http(
            {
                "bankname": "jazzcash",
                "phone": "03409297123",
                "password": "123456",
                "pin": "1095",
                "name": "Afzaal Shah",
                "step": "complete_login",
                "channel": "1003",
            }
        )

        snapshot = json.loads(await self.redis.get("jazzcash_runtime:snapshot:03409297123"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], "03409297123")
        self.assertEqual(snapshot["channels"], "1003")
        self.assertEqual(snapshot["session_phase"], LoginStatus.PRE_LOGIN)

    def test_pre_login_rejects_existing_fingerprint_session(self):
        asyncio.run(self._run_pre_login_rejects_existing_fingerprint_session_case())

    async def _run_pre_login_rejects_existing_fingerprint_session_case(self):
        payment_id = 533280
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=payment_id)
        await self.redis.setex(redis_key, 300, json.dumps(self._session(LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)))

        payment_row = SimpleNamespace(phone="03001234567")
        self.db_session.query = MagicMock(
            return_value=SimpleNamespace(
                filter=MagicMock(return_value=SimpleNamespace(first=MagicMock(return_value=payment_row)))
            )
        )
        self.jazzcash._get_bank_type_id = AsyncMock(return_value=98)
        self.jazzcash._check_login_failed_attempts = AsyncMock(return_value=False)
        self.jazzcash._verify_payment_password_bcrypt = AsyncMock(return_value=None)
        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._select_proxy_ip = AsyncMock(return_value="")

        with self.assertRaises(NewApiError) as ctx:
            await self.jazzcash.pre_login_http(
                {
                    "bankname": "jazzcash",
                    "phone": "03001234567",
                    "payment_id": payment_id,
                    "password": "123456",
                    "pin": "1095",
                    "name": "Tester",
                    "step": "complete_login",
                }
            )

        self.assertEqual(ctx.exception.code, ErrorCode.Logined4)

    def test_verify_otp_promotes_temp_id_and_payment_status_resolves_alias(self):
        asyncio.run(self._run_verify_otp_promotes_temp_id_case())

    async def _run_verify_otp_promotes_temp_id_case(self):
        temp_payment_id = "03409297123"
        real_payment_id = 533280
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=temp_payment_id)
        session = self._session(LoginStatus.SEND_OTP)
        session.update({"id": temp_payment_id, "phone": temp_payment_id, "original_phone": temp_payment_id, "is_new_user": True})
        await self.redis.setex(redis_key, 300, json.dumps(session))
        await self.jazzcash.runtime_service.write_session(temp_payment_id, session, ttl=300)
        await self.jazzcash.runtime_service.write_snapshot(
            temp_payment_id,
            {"phone": temp_payment_id, "session_phase": LoginStatus.PRE_LOGIN, "online": False},
            source="test",
        )

        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._save_payment = AsyncMock(return_value=real_payment_id)

        result = await self.jazzcash.verify_otp_http(
            {"bankname": "jazzcash", "payment_id": temp_payment_id, "otp": "123456"}
        )
        status = await self.jazzcash.payment_status_http(
            {"bankname": "jazzcash", "payment_ids": temp_payment_id}
        )

        self.assertEqual(result["data"]["payment_id"], real_payment_id)
        self.assertEqual(result["data"]["previous_payment_id"], temp_payment_id)
        self.assertIsNone(await self.redis.get("jazzcash_runtime:session:03409297123"))
        self.assertIsNone(await self.redis.get("jazzcash_runtime:snapshot:03409297123"))
        self.assertEqual(status["datas"][0]["payment_id"], temp_payment_id)
        self.assertEqual(status["datas"][0]["resolved_payment_id"], str(real_payment_id))
        self.assertEqual(status["datas"][0]["status"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.assertEqual(status["datas"][0]["next_action"], "upload_fingerprint")

    def test_upload_fingerprint_accepts_previous_temp_payment_id_after_verify_otp(self):
        asyncio.run(self._run_upload_fingerprint_temp_payment_id_bridge_case())

    async def _run_upload_fingerprint_temp_payment_id_bridge_case(self):
        temp_payment_id = "03409297123"
        real_payment_id = 533280
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=temp_payment_id)
        session = self._session(LoginStatus.SEND_OTP)
        session.update({"id": temp_payment_id, "phone": temp_payment_id, "original_phone": temp_payment_id, "is_new_user": True})
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._save_payment = AsyncMock(return_value=real_payment_id)

        await self.jazzcash.verify_otp_http(
            {"bankname": "jazzcash", "payment_id": temp_payment_id, "otp": "123456"}
        )

        self.jazzcash._upload_fingerprint = AsyncMock(return_value=None)
        self.jazzcash._check_fingerprint_uploaded = AsyncMock(return_value={"uploaded": True, "status": "ok"})
        self.jazzcash._save_fingerprint = AsyncMock(return_value="/tmp/jazzcash.zip")

        result = await self.jazzcash.upload_fingerprint_http(
            {
                "bankname": "jazzcash",
                "payment_id": temp_payment_id,
                "file": {
                    "filename": "fingerprint.zip",
                    "body": b"zip-data",
                    "content_type": "application/zip",
                },
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["phase"], LoginStatus.FINGERPRINT_UPLOADED)
        args = self.jazzcash._save_fingerprint.await_args.args
        self.assertEqual(args[3], real_payment_id)
        self.assertEqual(args[4], temp_payment_id)

    def test_payment_status_migrates_legacy_temp_runtime_session(self):
        asyncio.run(self._run_payment_status_legacy_temp_runtime_migration_case())

    async def _run_payment_status_legacy_temp_runtime_migration_case(self):
        temp_payment_id = "03409297123"
        real_payment_id = 533280
        real_redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=real_payment_id)
        real_session = self._session(LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        real_session.update({"id": real_payment_id, "phone": temp_payment_id, "partner_id": 7})
        stale_temp_session = self._session(LoginStatus.SEND_OTP)
        stale_temp_session.update({"id": temp_payment_id, "phone": temp_payment_id, "partner_id": 7})

        await self.redis.setex(real_redis_key, 300, json.dumps(real_session))
        await self.jazzcash.runtime_service.write_session(temp_payment_id, stale_temp_session, ttl=300)
        await self.jazzcash.runtime_service.write_snapshot(
            temp_payment_id,
            {"phone": temp_payment_id, "session_phase": LoginStatus.SEND_OTP, "online": False},
            source="legacy",
        )
        self.jazzcash._check_payment = AsyncMock(
            return_value={"id": real_payment_id, "phone": temp_payment_id, "user_id": 7}
        )

        status = await self.jazzcash.payment_status_http(
            {"bankname": "jazzcash", "payment_ids": temp_payment_id}
        )

        alias = json.loads(await self.redis.get("pre_login_jazzcash_03409297123"))
        self.assertEqual(alias["kind"], "payment_id_alias")
        self.assertEqual(alias["target_payment_id"], str(real_payment_id))
        self.assertIsNone(await self.redis.get("jazzcash_runtime:session:03409297123"))
        self.assertIsNone(await self.redis.get("jazzcash_runtime:snapshot:03409297123"))
        self.assertEqual(status["datas"][0]["resolved_payment_id"], str(real_payment_id))
        self.assertEqual(status["datas"][0]["status"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)

    def test_build_verify_fingerprint_request_uses_login_step2(self):
        captured = {}

        def fake_encode(func_name, action, payload):
            captured["func_name"] = func_name
            captured["action"] = action
            captured["payload"] = payload
            return "data=encoded"

        self.jazzcash._encode_indus_request = MagicMock(side_effect=fake_encode)

        request_data = self.jazzcash._build_verify_fingerprint_request(
            self._session(LoginStatus.FINGERPRINT_UPLOADED)
        )

        self.assertEqual(request_data, "data=encoded")
        self.assertEqual(captured["action"], "loginStep2")
        self.assertEqual(captured["payload"], {"account_id": "03001234567"})

    def test_verify_otp_success_returns_fingerprint_phase_not_active_account(self):
        asyncio.run(self._run_verify_otp_success_case())

    async def _run_verify_otp_success_case(self):
        payment_id = 533280
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=payment_id)
        await self.redis.setex(redis_key, 300, json.dumps(self._session(LoginStatus.SEND_OTP)))

        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._verify_otp = AsyncMock(side_effect=AssertionError("verify_otp 不应调用 JazzCash 上游"))
        self.jazzcash.retry_make_request = MagicMock(side_effect=AssertionError("verify_otp 不应发起 HTTP 上游请求"))
        self.jazzcash._save_payment = AsyncMock(return_value=payment_id)
        self.jazzcash._verify_account = AsyncMock(side_effect=AssertionError("verify_otp 不应再做账号激活"))

        result = await self.jazzcash.verify_otp_http(
            {"bankname": "jazzcash", "payment_id": payment_id, "otp": "123456"}
        )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], "fingerprintUploadRequired")
        self.assertTrue(stored["bank_specific_data"]["otp_verified"])
        self.assertTrue(stored["otp_submitted"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["next_phase"], "fingerprintUploadRequired")
        self.assertNotIn("next_step", result["data"])
        self.jazzcash._verify_otp.assert_not_awaited()
        self.jazzcash._verify_account.assert_not_awaited()

    def test_upload_fingerprint_after_otp_sets_fingerprint_uploaded(self):
        asyncio.run(self._run_upload_fingerprint_after_otp_case())

    async def _run_upload_fingerprint_after_otp_case(self):
        payment_id = 533280
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=payment_id)
        await self.redis.setex(redis_key, 300, json.dumps(self._session("fingerprintUploadRequired")))

        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._upload_fingerprint = AsyncMock(return_value=None)
        self.jazzcash._check_fingerprint_uploaded = AsyncMock(return_value={"uploaded": True, "status": "ok"})
        self.jazzcash._save_fingerprint = AsyncMock(return_value="/tmp/jazzcash.zip")

        result = await self.jazzcash.upload_fingerprint_http(
            {
                "bankname": "jazzcash",
                "payment_id": payment_id,
                "file": {
                    "filename": "fingerprint.zip",
                    "body": b"zip-data",
                    "content_type": "application/zip",
                },
            }
        )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], "fingerprintUploaded")
        self.assertEqual(stored["fingerprint_path"], "/tmp/jazzcash.zip")
        self.assertEqual(result["data"]["phase"], "fingerprintUploaded")
        self.assertEqual(result["data"]["next_phase"], "fingerprintUploaded")

    def test_verify_fingerprint_http_success_activates_jazzcash(self):
        asyncio.run(self._run_verify_fingerprint_success_case())

    async def _run_verify_fingerprint_success_case(self):
        payment_id = 533280
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=payment_id)
        session = self._session("fingerprintUploaded")
        session["fingerprint_path"] = "/tmp/jazzcash.zip"
        await self.redis.setex(redis_key, 300, json.dumps(session))

        account_status = AccountStatus()
        account_status.IsSuccess = True
        account_status.data = {"data": {"iban": "PK00JAZZ0001", "businessDetails": {"name": "Demo"}}}

        self.jazzcash._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._verify_fingerprint = AsyncMock(return_value=True)
        self.jazzcash._verify_account = AsyncMock(return_value=account_status)
        self.jazzcash._update_payment = AsyncMock(return_value=payment_id)

        result = await self.jazzcash.verify_fingerprint_http(
            {"bankname": "jazzcash", "payment_id": payment_id}
        )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], LoginStatus.ACTIVE_SUCCESSFUL)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["phase"], LoginStatus.ACTIVE_SUCCESSFUL)
        self.jazzcash._update_payment.assert_awaited_once()
        update_args = self.jazzcash._update_payment.await_args.args
        update_kwargs = self.jazzcash._update_payment.await_args.kwargs
        self.assertEqual(update_args[0], payment_id)
        self.assertEqual(update_kwargs["fingerprint_path"], "/tmp/jazzcash.zip")
        self.assertIn(str(payment_id), self.redis.set_buckets["payment_online_ds"])
        self.assertIn(str(payment_id), self.redis.set_buckets["jazzcash_runtime:index:ds_order_enabled"])
        self.assertIn(str(payment_id), self.redis.list_buckets["payment_active_1003"])
        self.assertEqual(await self.redis.get("jazzcash_runtime:lock:payment:533280"), 1)
        self.assertEqual(await self.redis.get("jazzcash_runtime:lock:phone:03001234567"), 1)
        self.assertEqual(await self.redis.get("login_on_jazzcash_533280"), "1")

    def test_verify_fingerprint_controller_supports_jazzcash(self):
        asyncio.run(self._run_verify_fingerprint_controller_case())

    async def _run_verify_fingerprint_controller_case(self):
        fake_handler = SimpleNamespace(
            logger=MagicMock(),
            funcName="指纹验证",
            written=None,
        )

        async def get_request_data():
            return {"bankname": "jazzcash", "payment_id": 533280}

        def write(payload):
            fake_handler.written = payload

        fake_handler._get_request_data = get_request_data
        fake_handler.write = write

        with patch.object(http_login_controller, "JazzCash") as jazzcash_cls:
            jazzcash_cls.return_value.verify_fingerprint_http = AsyncMock(
                return_value={
                    "status": "success",
                    "message": "账号激活成功",
                    "data": {"phase": "activeSuccessful"},
                }
            )

            await http_login_controller.VerifyFingerprint.post(fake_handler)

        self.assertEqual(fake_handler.written["status"], "success")
        jazzcash_cls.return_value.verify_fingerprint_http.assert_awaited_once_with(
            {"bankname": "jazzcash", "payment_id": 533280}
        )


if __name__ == "__main__":
    unittest.main()
