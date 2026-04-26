import asyncio
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import IntegrityError

from application.app.login.banks import easypaisa as easypaisa_module
from application.app.login.banks.easypaisa import EasyPaisa, ErrorCode, LoginStatus, STATUS_TRANSITIONS
from application.easypaisa_runtime import keyspace
from application.lakshmi_api.controllers import http_login_controller
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.exceptions.api_error import NewApiError


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl_map = {}
        self.set_calls = []
        self.setex_calls = []
        self.delete_calls = []
        self.set_buckets = {}
        self.list_buckets = {}
        self.zset_buckets = {}
        self.hash_buckets = {}

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.storage:
            return False
        self.storage[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        self.set_calls.append((key, value, nx, ex))
        return True

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        self.ttl_map[key] = ttl
        self.setex_calls.append((key, ttl, value))
        return True

    async def delete(self, key):
        self.delete_calls.append(key)
        existed = key in self.storage
        self.storage.pop(key, None)
        self.ttl_map.pop(key, None)
        return 1 if existed else 0

    async def hset(self, key, field, value):
        bucket = self.hash_buckets.setdefault(key, {})
        bucket[str(field)] = value
        return 1

    async def hget(self, key, field):
        return self.hash_buckets.get(key, {}).get(str(field))

    async def hdel(self, key, *fields):
        bucket = self.hash_buckets.setdefault(key, {})
        removed = 0
        for field in fields:
            text = str(field)
            existed = text in bucket
            bucket.pop(text, None)
            removed += 1 if existed else 0
        return removed

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
        removed = 0
        for value in values:
            removed += 1 if str(value) in bucket else 0
            bucket.discard(str(value))
        return removed

    async def sismember(self, key, value):
        return str(value) in self.set_buckets.get(key, set())

    async def smembers(self, key):
        return self.set_buckets.get(key, set())

    async def scard(self, key):
        return len(self.set_buckets.get(key, set()))

    async def lrem(self, key, count, value):
        bucket = self.list_buckets.setdefault(key, [])
        target = str(value)
        if count == 0:
            removed = bucket.count(target)
            self.list_buckets[key] = [item for item in bucket if item != target]
            return removed
        raise NotImplementedError("FakeRedis only supports count=0")

    async def rpush(self, key, value):
        bucket = self.list_buckets.setdefault(key, [])
        bucket.append(str(value))
        return len(bucket)

    async def zadd(self, key, mapping):
        bucket = self.zset_buckets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return True

    async def zscore(self, key, member):
        return self.zset_buckets.get(key, {}).get(str(member))

    async def zrem(self, key, *members):
        bucket = self.zset_buckets.setdefault(key, {})
        removed = 0
        for member in members:
            text = str(member)
            existed = text in bucket
            bucket.pop(text, None)
            removed += 1 if existed else 0
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


class EasyPaisaBusinessFlowV2Tests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.db_session = DummySession()
        handler = SimpleNamespace(
            redis=self.redis,
            logger=MagicMock(),
            db_orm=SimpleNamespace(sessionmaker=lambda: self.db_session),
            current_user=SimpleNamespace(id=7, hash_trade="hash-trade", cellphone="03000000000"),
        )
        self.easypaisa = EasyPaisa(handler)
        self.easypaisa.logger = MagicMock()

    def _session(self, status):
        return {
            "id": 533280,
            "phone": "923045536108",
            "bankname": "easypaisa",
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
        }

    def test_state_machine_legal_transitions_pass(self):
        legal_pairs = {
            (source, target)
            for source, targets in STATUS_TRANSITIONS.items()
            for target in targets
        }
        for source, target in legal_pairs:
            self.easypaisa._assert_status_transition(
                self._session(source), source, target, "test"
            )

    def test_state_machine_illegal_transitions_raise_invalid_transition(self):
        all_statuses = list(STATUS_TRANSITIONS.keys())
        legal_pairs = {
            (source, target)
            for source, targets in STATUS_TRANSITIONS.items()
            for target in targets
        }
        for source in all_statuses:
            for target in all_statuses:
                if (source, target) in legal_pairs:
                    continue
                with self.assertRaises(NewApiError) as ctx:
                    self.easypaisa._assert_status_transition(
                        self._session(source), source, target, "test"
                    )
                self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")

    def test_save_fingerprint_uses_mounted_module_fingerprint_dir(self):
        asyncio.run(self._run_save_fingerprint_mount_dir_case())

    async def _run_save_fingerprint_mount_dir_case(self):
        session = self._session(LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.easypaisa._save_payment = AsyncMock(return_value=True)
        fingerprint_path = None
        root_dir = Path("/fingerprint")
        root_existed = root_dir.exists()
        expected_dir = Path(easypaisa_module.__file__).resolve().parent / "fingerprint"
        expected_dir_existed = expected_dir.exists()

        try:
            result = await self.easypaisa._save_fingerprint(
                session,
                b"zip-data",
                "easypaisa",
                533290,
                "03445021275",
            )
            self.assertTrue(result)
            fingerprint_path = self.easypaisa._save_payment.await_args.kwargs["fingerprint_path"]
            saved = Path(fingerprint_path).resolve()
            saved.relative_to(expected_dir.resolve())
            self.assertEqual(saved.name, "easypaisa_533290_03445021275.zip")
            self.assertEqual(saved.read_bytes(), b"zip-data")
        finally:
            if fingerprint_path:
                Path(fingerprint_path).unlink(missing_ok=True)
            if not expected_dir_existed and expected_dir.exists():
                try:
                    expected_dir.rmdir()
                except OSError:
                    pass
            if not root_existed and root_dir.exists():
                try:
                    root_dir.rmdir()
                except OSError:
                    pass

    def test_verify_otp_replay_success_sets_fingerprint_uploaded(self):
        asyncio.run(self._run_verify_otp_replay_case(True, LoginStatus.FINGERPRINT_UPLOADED))

    def test_verify_otp_replay_failure_sets_fingerprint_upload_required(self):
        asyncio.run(self._run_verify_otp_replay_case(False, LoginStatus.FINGERPRINT_UPLOAD_REQUIRED))

    def test_verify_otp_replay_exception_is_swallowed(self):
        asyncio.run(self._run_verify_otp_replay_case(RuntimeError("boom"), LoginStatus.FINGERPRINT_UPLOAD_REQUIRED))

    def test_verify_otp_returns_real_payment_id_when_temp_id_is_promoted(self):
        asyncio.run(self._run_verify_otp_returns_real_payment_id_case())

    def test_upload_fingerprint_http_accepts_previous_temp_payment_id_after_verify_otp(self):
        asyncio.run(self._run_upload_fingerprint_temp_payment_id_bridge_case())

    def test_payment_status_http_resolves_previous_temp_payment_id_after_verify_otp(self):
        asyncio.run(self._run_payment_status_temp_payment_id_bridge_case())

    async def _run_verify_otp_replay_case(self, replay_result, expected_status):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.OTP_SENT)
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._verify_otp = AsyncMock(return_value={"data": {"requestId": "req-1", "serv_gen_id": "req-1"}})
        self.easypaisa._save_payment = AsyncMock(return_value=payment_id)

        if isinstance(replay_result, Exception):
            self.easypaisa._replay_saved_fingerprint = AsyncMock(side_effect=replay_result)
        else:
            self.easypaisa._replay_saved_fingerprint = AsyncMock(return_value=replay_result)

        result = await self.easypaisa.verify_otp_http(
            {"bankname": "easypaisa", "payment_id": payment_id, "otp": "123456"}
        )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], expected_status)
        self.assertEqual(result["data"]["next_phase"], expected_status)
        self.assertNotIn("cd_until", result["data"])

    async def _run_verify_otp_returns_real_payment_id_case(self):
        temp_payment_id = "03445021275"
        real_payment_id = 533290
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=temp_payment_id)
        session = self._session(LoginStatus.OTP_SENT)
        session.update({"id": temp_payment_id, "phone": temp_payment_id, "original_phone": temp_payment_id})
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._verify_otp = AsyncMock(return_value={"data": {"requestId": "req-1", "serv_gen_id": "req-1"}})
        self.easypaisa._save_payment = AsyncMock(return_value=real_payment_id)
        self.easypaisa._replay_saved_fingerprint = AsyncMock(return_value=False)

        result = await self.easypaisa.verify_otp_http(
            {"bankname": "easypaisa", "payment_id": temp_payment_id, "otp": "123456"}
        )

        self.assertEqual(result["data"]["next_phase"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.assertEqual(result["data"]["payment_id"], real_payment_id)
        self.assertEqual(result["data"]["previous_payment_id"], temp_payment_id)

    async def _run_upload_fingerprint_temp_payment_id_bridge_case(self):
        temp_payment_id = "03445021275"
        real_payment_id = 533290
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=temp_payment_id)
        session = self._session(LoginStatus.OTP_SENT)
        session.update({"id": temp_payment_id, "phone": temp_payment_id, "original_phone": temp_payment_id})
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._verify_otp = AsyncMock(return_value={"data": {"requestId": "req-1", "serv_gen_id": "req-1"}})
        self.easypaisa._save_payment = AsyncMock(return_value=real_payment_id)
        self.easypaisa._replay_saved_fingerprint = AsyncMock(return_value=False)

        await self.easypaisa.verify_otp_http(
            {"bankname": "easypaisa", "payment_id": temp_payment_id, "otp": "123456"}
        )

        self.easypaisa._upload_fingerprint = AsyncMock(return_value=None)
        self.easypaisa._save_fingerprint = AsyncMock(return_value=True)

        result = await self.easypaisa.upload_fingerprint_http(
            {
                "bankname": "easypaisa",
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
        self.easypaisa._save_fingerprint.assert_awaited_once()
        args = self.easypaisa._save_fingerprint.await_args.args
        self.assertEqual(args[3], real_payment_id)
        self.assertEqual(args[4], temp_payment_id)

    async def _run_payment_status_temp_payment_id_bridge_case(self):
        temp_payment_id = "03445021275"
        real_payment_id = 533290
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=temp_payment_id)
        session = self._session(LoginStatus.OTP_SENT)
        session.update({"id": temp_payment_id, "phone": temp_payment_id, "original_phone": temp_payment_id})
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._verify_otp = AsyncMock(return_value={"data": {"requestId": "req-1", "serv_gen_id": "req-1"}})
        self.easypaisa._save_payment = AsyncMock(return_value=real_payment_id)
        self.easypaisa._replay_saved_fingerprint = AsyncMock(return_value=False)

        await self.easypaisa.verify_otp_http(
            {"bankname": "easypaisa", "payment_id": temp_payment_id, "otp": "123456"}
        )

        result = await self.easypaisa.payment_status_http(
            {"bankname": "easypaisa", "payment_ids": temp_payment_id}
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["datas"]), 1)
        self.assertEqual(result["datas"][0]["payment_id"], temp_payment_id)
        self.assertEqual(result["datas"][0]["status"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.assertEqual(result["datas"][0]["next_action"], "upload_fingerprint")

    def test_replay_saved_fingerprint_empty_path_returns_false(self):
        self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value=None)
        result = asyncio.run(self.easypaisa._replay_saved_fingerprint(1, "92300"))
        self.assertFalse(result)

    def test_replay_saved_fingerprint_missing_file_returns_false(self):
        self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value="/tmp/not-found.zip")
        result = asyncio.run(self.easypaisa._replay_saved_fingerprint(1, "92300"))
        self.assertFalse(result)

    def test_replay_saved_fingerprint_bridge_4xx_returns_false(self):
        with tempfile.NamedTemporaryFile() as fp:
            self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value=fp.name)
            self.easypaisa.retry_make_request = MagicMock(return_value=SimpleNamespace(status_code=403, text="denied"))
            result = asyncio.run(self.easypaisa._replay_saved_fingerprint(1, "92300"))
        self.assertFalse(result)

    def test_replay_saved_fingerprint_bridge_200_returns_true(self):
        with tempfile.NamedTemporaryFile() as fp:
            fp.write(b"zip-data")
            fp.flush()
            self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value=fp.name)
            self.easypaisa.retry_make_request = MagicMock(return_value=SimpleNamespace(status_code=200, text="ok"))
            result = asyncio.run(self.easypaisa._replay_saved_fingerprint(1, "92300"))
        self.assertTrue(result)

    def test_replay_saved_fingerprint_exception_is_swallowed(self):
        with tempfile.NamedTemporaryFile() as fp:
            self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value=fp.name)
            self.easypaisa.retry_make_request = MagicMock(side_effect=RuntimeError("network"))
            result = asyncio.run(self.easypaisa._replay_saved_fingerprint(1, "92300"))
        self.assertFalse(result)

    def test_build_verify_fingerprint_request_keeps_payload_as_json_object(self):
        session = self._session(LoginStatus.FINGERPRINT_UPLOADED)
        request_data = self.easypaisa._build_verify_fingerprint_request(session)

        encoded_outer = parse_qs(request_data)["data"][0]
        outer = json.loads(base64.b64decode(encoded_outer).decode("utf-8"))

        self.assertEqual(outer["action"], "verifyFingerprint")
        self.assertIsInstance(outer["payload"], dict)
        self.assertEqual(outer["payload"], {"account_id": "923045536108"})

    def test_verify_fingerprint_http_rejected_clears_saved_fingerprint(self):
        asyncio.run(self._run_verify_fingerprint_rejected_case())

    async def _run_verify_fingerprint_rejected_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.FINGERPRINT_UPLOADED)
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._perform_verify_fingerprint = AsyncMock(
            return_value={"outcome": "rejected", "message": "缺少指纹数据"}
        )
        self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value="/tmp/fingerprint.zip")

        with patch("application.app.login.banks.easypaisa.os.remove") as remove_mock:
            result = await self.easypaisa.verify_fingerprint_http(
                {"bankname": "easypaisa", "payment_id": payment_id}
            )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["data"]["code"], "FP_UPSTREAM_REJECTED")
        self.assertEqual(result["data"]["phase"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.db_session.execute.assert_called_once()
        self.db_session.commit.assert_called_once()
        remove_mock.assert_called_once_with("/tmp/fingerprint.zip")

    def test_verify_fingerprint_http_transient_does_not_cleanup_cache(self):
        asyncio.run(self._run_verify_fingerprint_transient_case())

    async def _run_verify_fingerprint_transient_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.FINGERPRINT_UPLOADED)
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._perform_verify_fingerprint = AsyncMock(
            return_value={"outcome": "transient", "message": "empty response"}
        )
        self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value="/tmp/fingerprint.zip")

        with patch("application.app.login.banks.easypaisa.os.remove") as remove_mock:
            result = await self.easypaisa.verify_fingerprint_http(
                {"bankname": "easypaisa", "payment_id": payment_id}
            )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], LoginStatus.FINGERPRINT_UPLOADED)
        self.assertEqual(result["data"]["code"], "FP_UPSTREAM_TRANSIENT")
        self.db_session.execute.assert_not_called()
        self.db_session.commit.assert_not_called()
        remove_mock.assert_not_called()

    def test_perform_verify_fingerprint_corruption_maps_to_rejected(self):
        asyncio.run(self._run_perform_verify_fingerprint_corruption_case())

    async def _run_perform_verify_fingerprint_corruption_case(self):
        session = self._session(LoginStatus.FINGERPRINT_UPLOADED)
        self.easypaisa._build_verify_fingerprint_request = MagicMock(return_value="payload")
        self.easypaisa._log_response = MagicMock()
        self.easypaisa.retry_make_request = MagicMock(
            return_value=SimpleNamespace(status_code=200, text="raw-response")
        )
        self.easypaisa._decode_indus_response = MagicMock(
            return_value={
                "code": 403,
                "msg": "读取03431940911指纹数据失败，请检查指纹数据包(Fingerprint data corruption)",
                "data": None,
            }
        )

        result = await self.easypaisa._perform_verify_fingerprint(session)

        self.assertEqual(result["outcome"], "rejected")
        self.assertIn("Fingerprint data corruption", result["message"])

    def test_verify_fingerprint_http_cleanup_db_failure_is_best_effort(self):
        asyncio.run(self._run_verify_fingerprint_cleanup_db_failure_case())

    async def _run_verify_fingerprint_cleanup_db_failure_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.FINGERPRINT_UPLOADED)
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.db_session.execute.side_effect = RuntimeError("db down")
        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._perform_verify_fingerprint = AsyncMock(
            return_value={"outcome": "rejected", "message": "缺少指纹数据"}
        )
        self.easypaisa._get_payment_fingerprint_path = MagicMock(return_value="/tmp/fingerprint.zip")

        with patch("application.app.login.banks.easypaisa.os.remove") as remove_mock:
            result = await self.easypaisa.verify_fingerprint_http(
                {"bankname": "easypaisa", "payment_id": payment_id}
            )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], LoginStatus.FINGERPRINT_UPLOAD_REQUIRED)
        self.assertEqual(result["data"]["code"], "FP_UPSTREAM_REJECTED")
        remove_mock.assert_called_once_with("/tmp/fingerprint.zip")

    def test_second_login_http_needs_change_pin_sets_awaiting_pin_change(self):
        asyncio.run(self._run_second_login_needs_pin_change_case())

    async def _run_second_login_needs_pin_change_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.FINGERPRINT_VERIFIED)
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._perform_second_login = AsyncMock(
            return_value={"outcome": "needs_pin_change", "message": "URM20008"}
        )

        result = await self.easypaisa.second_login_http(
            {"bankname": "easypaisa", "payment_id": payment_id}
        )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], LoginStatus.AWAITING_PIN_CHANGE)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["data"]["code"], "SL_NEEDS_PIN_CHANGE")
        self.assertEqual(result["data"]["phase"], LoginStatus.AWAITING_PIN_CHANGE)

    def test_payment_status_http_is_read_only(self):
        asyncio.run(self._run_payment_status_read_only_case())

    async def _run_payment_status_read_only_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.FINGERPRINT_VERIFIED)
        session["cd_until"] = 123456
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._verify_account = AsyncMock(side_effect=AssertionError("_verify_account 不应被调用"))

        before_set_calls = len(self.redis.set_calls)
        before_setex_calls = len(self.redis.setex_calls)

        result = await self.easypaisa.payment_status_http(
            {"bankname": "easypaisa", "payment_ids": str(payment_id)}
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["datas"][0]["status"], LoginStatus.FINGERPRINT_VERIFIED)
        self.assertEqual(result["datas"][0]["next_action"], "second_login")
        self.assertEqual(len(self.redis.set_calls), before_set_calls)
        self.assertEqual(len(self.redis.setex_calls), before_setex_calls)

    def test_send_otp_http_resend_within_cooldown_returns_payment_locked(self):
        asyncio.run(self._run_send_otp_resend_within_cooldown_case())

    async def _run_send_otp_resend_within_cooldown_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.OTP_SENT)
        session["sendOTPTime"] = 1_000
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._send_otp = AsyncMock(return_value={"status": "success"})

        with patch("application.app.login.banks.easypaisa.time.time", return_value=1_010):
            with self.assertRaises(NewApiError) as ctx:
                await self.easypaisa.send_otp_http(
                    {"bankname": "easypaisa", "payment_id": payment_id}
                )

        self.assertEqual(ctx.exception.code, ErrorCode.PaymentLocked)
        self.easypaisa._send_otp.assert_not_awaited()

    def test_send_otp_http_resend_after_cooldown_succeeds(self):
        asyncio.run(self._run_send_otp_resend_after_cooldown_case())

    async def _run_send_otp_resend_after_cooldown_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.OTP_SENT)
        session["sendOTPTime"] = 1_000
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._send_otp = AsyncMock(return_value={"status": "success"})

        with patch("application.app.login.banks.easypaisa.time.time", return_value=1_025):
            result = await self.easypaisa.send_otp_http(
                {"bankname": "easypaisa", "payment_id": payment_id}
            )

        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(result["status"], "success")
        self.assertEqual(stored["status"], LoginStatus.OTP_SENT)
        self.assertEqual(stored["resend_count"], 1)
        self.easypaisa._send_otp.assert_awaited_once()

    def test_pre_login_other_merchant_phone_raises_10402(self):
        asyncio.run(self._run_pre_login_other_merchant_phone_case())

    def test_pre_login_same_merchant_phone_reuses_existing_payment_id(self):
        asyncio.run(self._run_pre_login_same_merchant_phone_case())

    async def _run_pre_login_other_merchant_phone_case(self):
        self.easypaisa._check_login_failed_attempts = AsyncMock(return_value=False)
        self.easypaisa._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.easypaisa._check_payment = AsyncMock(
            return_value={
                "id": 533280,
                "phone": "03045536108",
                "user_id": 9,
            }
        )
        self.easypaisa._get_payment_interface_lock = AsyncMock(
            side_effect=AssertionError("不应继续获取接口锁")
        )

        with self.assertRaises(NewApiError) as ctx:
            await self.easypaisa.pre_login_http(
                {
                    "step": "complete_login",
                    "bankname": "easypaisa",
                    "phone": "03045536108",
                    "password": "pass",
                    "pin": "1234",
                    "name": "tester",
                }
            )

        self.assertEqual(ctx.exception.code, "10402")
        self.assertIn("occupied", ctx.exception.message.lower())
        self.easypaisa._check_payment.assert_awaited_once()

    async def _run_pre_login_same_merchant_phone_case(self):
        self.easypaisa._check_login_failed_attempts = AsyncMock(return_value=False)
        self.easypaisa._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.easypaisa._check_payment = AsyncMock(
            return_value={
                "id": 533280,
                "phone": "03045536108",
                "user_id": 7,
            }
        )
        self.easypaisa._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._select_proxy_ip = AsyncMock(return_value="")
        self.easypaisa._get_session_data = AsyncMock(return_value=None)

        result = await self.easypaisa.pre_login_http(
            {
                "step": "complete_login",
                "bankname": "easypaisa",
                "phone": "03045536108",
                "password": "pass",
                "pin": "1234",
                "name": "tester",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], 533280)
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=533280)
        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["id"], 533280)
        self.assertFalse(stored["is_new_user"])
        self.easypaisa._check_payment.assert_awaited_once()
        self.easypaisa._get_payment_interface_lock.assert_awaited_once()

    def test_pre_login_same_merchant_phone_persists_runtime_session_snapshot(self):
        asyncio.run(self._run_pre_login_runtime_snapshot_case())

    def test_pre_login_ignores_legacy_online_marker(self):
        asyncio.run(self._run_pre_login_ignores_legacy_online_marker_case())

    def test_pre_login_duplicate_lock_uses_runtime_lock_key(self):
        asyncio.run(self._run_pre_login_duplicate_lock_runtime_key_case())

    def test_pre_login_clears_stale_runtime_session_when_snapshot_offline(self):
        asyncio.run(self._run_pre_login_clears_stale_runtime_session_case())

    async def _run_pre_login_runtime_snapshot_case(self):
        self.easypaisa._check_login_failed_attempts = AsyncMock(return_value=False)
        self.easypaisa._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.easypaisa._check_payment = AsyncMock(
            return_value={
                "id": 533280,
                "phone": "03045536108",
                "user_id": 7,
            }
        )
        self.easypaisa._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._select_proxy_ip = AsyncMock(return_value="")
        self.easypaisa._get_session_data = AsyncMock(return_value=None)

        await self.easypaisa.pre_login_http(
            {
                "step": "complete_login",
                "bankname": "easypaisa",
                "phone": "03045536108",
                "channel": 1001,
                "password": "pass",
                "pin": "1234",
                "name": "tester",
            }
        )

        runtime_session = json.loads(await self.redis.get("easypaisa_runtime:session:533280"))
        runtime_snapshot = json.loads(await self.redis.get("easypaisa_runtime:snapshot:533280"))
        self.assertEqual(runtime_session["schema_version"], 1)
        self.assertEqual(runtime_session["status"], LoginStatus.PRE_LOGIN_CREATED)
        self.assertEqual(runtime_snapshot["payment_id"], 533280)
        self.assertEqual(runtime_snapshot["session_phase"], LoginStatus.PRE_LOGIN_CREATED)
        self.assertEqual(runtime_snapshot["channels"], ["1001"])
        self.assertFalse(runtime_snapshot["online"])

    async def _run_pre_login_ignores_legacy_online_marker_case(self):
        await self.redis.set("login_on_easypaisa_533280", "1")
        await self.redis.set("login_on_easypaisa_03045536108", "1")

        self.easypaisa._check_login_failed_attempts = AsyncMock(return_value=False)
        self.easypaisa._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.easypaisa._check_payment = AsyncMock(
            return_value={
                "id": 533280,
                "phone": "03045536108",
                "user_id": 7,
            }
        )
        self.easypaisa._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._select_proxy_ip = AsyncMock(return_value="")
        self.easypaisa._get_session_data = AsyncMock(return_value=None)

        result = await self.easypaisa.pre_login_http(
            {
                "step": "complete_login",
                "bankname": "easypaisa",
                "phone": "03045536108",
                "password": "pass",
                "pin": "1234",
                "name": "tester",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], 533280)

    async def _run_pre_login_duplicate_lock_runtime_key_case(self):
        await self.redis.set(keyspace.lock_phone_key("03045536108"), "1")

        self.easypaisa._check_login_failed_attempts = AsyncMock(return_value=False)
        self.easypaisa._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.easypaisa._check_payment = AsyncMock(return_value=None)
        self.easypaisa._get_payment_interface_lock = AsyncMock(
            side_effect=AssertionError("命中新锁后不应继续获取接口锁")
        )

        with self.assertRaises(NewApiError) as ctx:
            await self.easypaisa.pre_login_http(
                {
                    "step": "complete_login",
                    "bankname": "easypaisa",
                    "phone": "03045536108",
                    "password": "pass",
                    "pin": "1234",
                    "name": "tester",
                }
            )

        self.assertEqual(ctx.exception.code, ErrorCode.Logined)
        self.easypaisa._get_payment_interface_lock.assert_not_awaited()

    async def _run_pre_login_clears_stale_runtime_session_case(self):
        payment_id = 533280
        await self.redis.set(
            keyspace.session_key(payment_id),
            json.dumps(
                {
                    "id": payment_id,
                    "phone": "03045536108",
                    "status": LoginStatus.ACTIVE_SUCCESSFUL,
                }
            ),
        )
        await self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps(
                {
                    "schema_version": 1,
                    "payment_id": payment_id,
                    "phone": "03045536108",
                    "session_phase": "offline",
                    "online": False,
                    "dispatch_df": False,
                    "dispatch_ds": False,
                }
            ),
        )

        self.easypaisa._check_login_failed_attempts = AsyncMock(return_value=False)
        self.easypaisa._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.easypaisa._check_payment = AsyncMock(
            return_value={
                "id": payment_id,
                "phone": "03045536108",
                "user_id": 7,
            }
        )
        self.easypaisa._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._select_proxy_ip = AsyncMock(return_value="")

        result = await self.easypaisa.pre_login_http(
            {
                "step": "complete_login",
                "bankname": "easypaisa",
                "phone": "03045536108",
                "channel": 1001,
                "password": "pass",
                "pin": "1234",
                "name": "tester",
            }
        )

        runtime_session = json.loads(await self.redis.get(keyspace.session_key(payment_id)))
        self.assertEqual(result["status"], "success")
        self.assertEqual(runtime_session["status"], LoginStatus.PRE_LOGIN_CREATED)
        self.assertIn(keyspace.session_key(payment_id), self.redis.delete_calls)

    def test_select_accts_http_persists_runtime_active_snapshot(self):
        asyncio.run(self._run_select_accts_runtime_snapshot_case())

    async def _run_select_accts_runtime_snapshot_case(self):
        payment_id = 533280
        redis_key = self.easypaisa.PRELOGIN_KEY.format(bankname="easypaisa", payment_id=payment_id)
        session = self._session(LoginStatus.ACCOUNT_SELECTION_REQUIRED)
        session["qr_channel"] = 1001
        session["account_entire"] = json.dumps(
            [
                {
                    "accno": "88521642",
                    "accountStatus": "ACTIVE",
                    "accountName": "Easypaisa Wallet",
                    "IBAN": "PK12TMFB0000000088521642",
                },
                {
                    "accno": "88521643",
                    "accountStatus": "ACTIVE",
                    "accountName": "Family Account",
                    "accountProfile": "Savings MA",
                    "IBAN": "PK12HABB0000000088521643",
                },
            ]
        )
        await self.redis.setex(redis_key, 300, json.dumps(session))

        self.easypaisa._get_payment_interface_lock = AsyncMock(return_value={"lock_id": "lock", "lock_value": "value"})
        self.easypaisa._release_payment_interface_lock = AsyncMock(return_value=True)
        self.easypaisa._update_payment = AsyncMock(return_value=True)

        result = await self.easypaisa.select_accts_http(
            {"bankname": "easypaisa", "payment_id": payment_id, "accno": "88521643"}
        )

        runtime_snapshot = json.loads(await self.redis.get("easypaisa_runtime:snapshot:533280"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(runtime_snapshot["session_phase"], LoginStatus.ACTIVE_SUCCESSFUL)
        self.assertTrue(runtime_snapshot["online"])
        self.assertTrue(runtime_snapshot["dispatch_df"])
        self.assertEqual(runtime_snapshot["channels"], ["1001"])
        self.assertEqual(runtime_snapshot["selected_accno"], "88521643")
        self.assertEqual(runtime_snapshot["selected_iban"], "PK12HABB0000000088521643")
        self.assertTrue(await self.redis.sismember("payment_online_df", 533280))

    def test_payment_status_http_prefers_runtime_snapshot_when_session_missing(self):
        asyncio.run(self._run_payment_status_from_runtime_case())

    async def _run_payment_status_from_runtime_case(self):
        await self.redis.set(
            "easypaisa_runtime:snapshot:533280",
            json.dumps(
                {
                    "schema_version": 1,
                    "payment_id": 533280,
                    "session_phase": LoginStatus.FINGERPRINT_VERIFIED,
                    "online": False,
                    "dispatch_df": False,
                    "cd_until": 123456,
                    "last_source": "login_flow",
                    "updated_at": 1_744_000_000,
                }
            ),
        )

        result = await self.easypaisa.payment_status_http(
            {"bankname": "easypaisa", "payment_ids": "533280"}
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["datas"][0]["status"], LoginStatus.FINGERPRINT_VERIFIED)
        self.assertEqual(result["datas"][0]["next_action"], "second_login")
        self.assertEqual(result["datas"][0]["cd_until"], 123456)

    def test_force_logout_updates_runtime_snapshot_and_kickoff_keys(self):
        asyncio.run(self._run_force_logout_runtime_cleanup_case())

    async def _run_force_logout_runtime_cleanup_case(self):
        payment_id = 533280
        phone = "03045536108"

        class QueryChain:
            def __init__(self, payment):
                self.payment = payment

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self.payment

        class ForceLogoutSession(DummySession):
            def __init__(self, payment):
                super().__init__()
                self.payment = payment
                self.execute = MagicMock(return_value=SimpleNamespace(rowcount=1))

            def query(self, *_args, **_kwargs):
                return QueryChain(self.payment)

        payment = SimpleNamespace(id=payment_id, phone=phone, channel=1001)
        force_logout_session = ForceLogoutSession(payment)
        self.easypaisa.handler.db_orm = SimpleNamespace(sessionmaker=lambda: force_logout_session)

        await self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps(
                {
                    "schema_version": 1,
                    "payment_id": payment_id,
                    "phone": phone,
                    "session_phase": LoginStatus.ACTIVE_SUCCESSFUL,
                    "online": True,
                    "dispatch_df": True,
                    "dispatch_ds": True,
                    "channels": ["1001"],
                }
            ),
        )
        await self.redis.set(
            keyspace.session_key(payment_id),
            json.dumps({"id": payment_id, "phone": phone, "status": LoginStatus.ACTIVE_SUCCESSFUL}),
        )
        await self.redis.set(keyspace.pre_login_key(payment_id), json.dumps({"status": LoginStatus.ACTIVE_SUCCESSFUL}))
        await self.redis.set(keyspace.legacy_login_on_payment_key(payment_id), "1")
        await self.redis.set(keyspace.legacy_login_on_phone_key(phone), "1")
        await self.redis.sadd("payment_online_df", payment_id)
        await self.redis.sadd("payment_online_ds", payment_id)
        await self.redis.rpush("payment_active_df", payment_id)
        await self.redis.rpush("payment_active_1001", payment_id)

        result = await self.easypaisa._force_logout(payment_id, "easypaisa", "URM10004_SESSION_EXPIRED")

        self.assertTrue(result)
        runtime_snapshot = json.loads(await self.redis.get(keyspace.snapshot_key(payment_id)))
        self.assertEqual(runtime_snapshot["session_phase"], "offline")
        self.assertFalse(runtime_snapshot["online"])
        self.assertEqual(runtime_snapshot["last_transition"], "URM10004_SESSION_EXPIRED")
        self.assertEqual(await self.redis.get(keyspace.kickoff_key(payment_id)), "1")
        self.assertEqual(await self.redis.ttl(keyspace.kickoff_key(payment_id)), 1200)
        self.assertEqual(await self.redis.get(keyspace.legacy_kickoff_key(payment_id)), "1")
        self.assertEqual(await self.redis.ttl(keyspace.legacy_kickoff_key(payment_id)), 1200)
        self.assertIsNone(await self.redis.get(keyspace.session_key(payment_id)))
        self.assertIsNone(await self.redis.get(keyspace.pre_login_key(payment_id)))
        self.assertFalse(await self.redis.sismember("payment_online_df", payment_id))
        self.assertFalse(await self.redis.sismember("payment_online_ds", payment_id))
        self.assertEqual(self.redis.list_buckets["payment_active_df"], [])
        self.assertEqual(self.redis.list_buckets["payment_active_1001"], [])

        status_result = await self.easypaisa.payment_status_http(
            {"bankname": "easypaisa", "payment_ids": str(payment_id)}
        )
        self.assertEqual(status_result["datas"][0]["status"], "offline")

    def test_create_payment_unique_conflict_reuses_existing_same_merchant_payment(self):
        conflict = DummySession()
        conflict.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
        self.easypaisa.handler.db_orm = SimpleNamespace(sessionmaker=lambda: conflict)
        self.easypaisa._get_bank_type_id = AsyncMock(return_value=97)
        self.easypaisa._check_payment = AsyncMock(
            return_value={"id": 533280, "phone": "923045536108", "user_id": 7}
        )

        result = asyncio.run(
            self.easypaisa._create_payment(
                {
                    "bankname": "easypaisa",
                    "phone": "923045536108",
                    "password": "pass",
                    "pinCode": "1234",
                    "partner_id": 7,
                },
                "tester",
            )
        )

        self.assertEqual(result, 533280)
        conflict.rollback.assert_called_once()
        self.easypaisa._check_payment.assert_awaited_once_with("easypaisa", "923045536108", 7)

    def test_active_account_controller_returns_410_for_easypaisa(self):
        asyncio.run(self._run_active_account_controller_case("easypaisa"))

    def test_active_account_controller_keeps_jazzcash_behavior(self):
        asyncio.run(self._run_active_account_controller_case("jazzcash"))

    async def _run_active_account_controller_case(self, bankname):
        fake_handler = SimpleNamespace(
            logger=MagicMock(),
            funcName="账号激活",
            status_code=None,
            written=None,
        )

        async def get_request_data():
            return {"bankname": bankname, "payment_id": 1}

        def set_status(code):
            fake_handler.status_code = code

        def write(payload):
            fake_handler.written = payload

        fake_handler._get_request_data = get_request_data
        fake_handler.set_status = set_status
        fake_handler.write = write

        with patch.object(
            http_login_controller, "EasyPaisa"
        ) as easypaisa_cls, patch.object(
            http_login_controller, "JazzCash"
        ) as jazzcash_cls:
            easypaisa_cls.return_value.active_account_http = AsyncMock(
                return_value={"code": "API_DEPRECATED", "hint": "use verify_fingerprint + second_login"}
            )
            jazzcash_cls.return_value.active_account_http = AsyncMock(
                return_value={"status": "success", "message": "ok"}
            )

            await http_login_controller.ActiveAccount.post(fake_handler)

        if bankname == "easypaisa":
            self.assertEqual(fake_handler.status_code, 410)
            self.assertEqual(fake_handler.written["code"], "API_DEPRECATED")
        else:
            self.assertIsNone(fake_handler.status_code)
            self.assertEqual(fake_handler.written["status"], "success")

    def test_handle_errors_maps_invalid_transition_to_http_400(self):
        asyncio.run(self._run_invalid_transition_http_status_case())

    async def _run_invalid_transition_http_status_case(self):
        class FakeHandler:
            def __init__(self):
                self.logger = MagicMock()
                self.status_code = None
                self.payload = None

            def set_status(self, code):
                self.status_code = code

            def write(self, payload):
                self.payload = payload

        @handle_errors
        async def endpoint(self):
            raise NewApiError("INVALID_TRANSITION", "bad transition")

        handler = FakeHandler()
        await endpoint(handler)
        self.assertEqual(handler.status_code, 400)
        self.assertEqual(handler.payload["error"]["code"], "INVALID_TRANSITION")

    def test_query_bound_accounts_http_returns_active_accounts_and_persists_cache(self):
        payment = SimpleNamespace(
            id=533280,
            phone="923045536108",
            bank=SimpleNamespace(name="EASYPAISA"),
            account_entire=None,
            account_accno="88521642",
        )
        self.easypaisa._query_accts = AsyncMock(return_value={
            "status": "success",
            "data": json.dumps([
                {"accno": "88521642", "accountStatus": "ACTIVE", "IBAN": "PK12TMFB0000000088521642"},
                {"accno": "88521643", "accountStatus": "ACTIVE", "IBAN": "PK12TMFB0000000088521643"},
                {"accno": "88521644", "accountStatus": "BLOCKED", "IBAN": "PK12TMFB0000000088521644"},
            ]),
        })

        result = asyncio.run(self.easypaisa.query_bound_accounts_http(payment))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["account_selected"], "88521642")
        self.assertEqual(len(result["data"]["account_entire"]), 2)
        self.assertIn("88521644", payment.account_entire)
        self.db_session.execute.assert_called_once()
        self.db_session.commit.assert_called_once()

    def test_select_bound_account_http_updates_selected_account(self):
        payment = SimpleNamespace(
            id=533280,
            phone="923045536108",
            bank=SimpleNamespace(name="EASYPAISA"),
            account_entire=json.dumps([
                {
                    "accno": "88521642",
                    "accountStatus": "ACTIVE",
                    "accountName": "Easypaisa Wallet",
                    "IBAN": "PK12TMFB0000000088521642",
                },
                {
                    "accno": "88521643",
                    "accountStatus": "ACTIVE",
                    "accountName": "Family Account",
                    "accountProfile": "Savings MA",
                    "IBAN": "PK12HABB0000000088521643",
                },
            ]),
            account_accno="88521642",
            account_iban="PK12TMFB0000000088521642",
            account_type=0,
        )

        result = asyncio.run(self.easypaisa.select_bound_account_http(payment, "88521643"))

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["account_selected"], "88521643")
        self.assertEqual(payment.account_accno, "88521643")
        self.assertEqual(payment.account_iban, "PK12HABB0000000088521643")
        self.assertEqual(payment.account_type, 20)
        self.db_session.execute.assert_called_once()
        self.db_session.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
