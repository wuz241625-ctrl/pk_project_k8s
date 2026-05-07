import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.app.login.banks.jazzcash import AccountStatus, ErrorCode, JazzCash, LoginStatus
from application.lakshmi_api.exceptions.api_error import NewApiError


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl_map = {}
        self.delete_calls = []

    async def get(self, key):
        return self.storage.get(key)

    async def set(self, key, value, ex=None):
        self.storage[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        self.ttl_map[key] = ttl
        return True

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            self.delete_calls.append(key)
            existed = key in self.storage
            self.storage.pop(key, None)
            self.ttl_map.pop(key, None)
            removed += 1 if existed else 0
        return removed

    async def ttl(self, key):
        if key not in self.storage:
            return -2
        return self.ttl_map.get(key, -1)

    async def sadd(self, key, *values):
        return len(values)

    async def srem(self, key, *values):
        return 0

    async def lrem(self, key, count, value):
        return 0

    async def rpush(self, key, value):
        return 1


class DummySession:
    def __init__(self):
        self.query = MagicMock()
        self.execute = MagicMock()
        self.commit = MagicMock()
        self.rollback = MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class JazzCashBoundSecondLoginTests(unittest.TestCase):
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

    def test_second_login_success_does_not_write_legacy_collection_redis_gate_source(self):
        source = Path(__file__).resolve().parents[1].joinpath(
            "application/app/login/banks/jazzcash.py"
        ).read_text()

        self.assertNotIn("await self.redis.sadd('payment_online_ds'", source)
        self.assertNotIn("await self.redis.rpush(f'payment_active_", source)
        self.assertIn("final_status", source)

    def _bound_payment_dict(self, user_id=7, payment_id=533302, phone="03409297123"):
        return {
            "id": payment_id,
            "phone": phone,
            "user_id": user_id,
            "pin": "1234",
            "name": "JazzCash Test",
            "account_entire": None,
            "account_accno": None,
            "account_iban": None,
            "channel": "1003",
        }

    def _payment_row(self, user_id=7, payment_id=533302, phone="03409297123"):
        return SimpleNamespace(
            id=payment_id,
            phone=phone,
            user_id=user_id,
            pin="1234",
            net_trade_pw="pass",
            name="JazzCash Test",
            account_entire=None,
            account_accno=None,
            account_iban="PK00JAZZCASH000000001",
            channel="1003",
        )

    def _success_account_status(self):
        status = AccountStatus()
        status.IsSuccess = True
        status.IsInCoolDown = False
        status.IsNeedRelogin = False
        status.IsNeedChangePin = False
        status.IsNeedFingerPrint = False
        status.data = {
            "data": {
                "iban": "PK00JAZZCASH000000001",
                "businessDetails": {"name": "JazzCash Test"},
            }
        }
        return status

    def test_pre_login_bound_same_partner_uses_is_logined_and_returns_second_login(self):
        asyncio.run(self._run_pre_login_bound_same_partner_case())

    async def _run_pre_login_bound_same_partner_case(self):
        self.jazzcash._check_login_failed_attempts = AsyncMock(return_value=False)
        self.jazzcash._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.jazzcash._check_payment = AsyncMock(return_value=self._bound_payment_dict())
        self.jazzcash._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._is_logined = AsyncMock(return_value={"code": 200, "data": True})
        self.jazzcash._select_proxy_ip = AsyncMock(side_effect=AssertionError("已绑定账号不应进入首次登录会话"))

        result = await self.jazzcash.pre_login_http(
            {
                "step": "complete_login",
                "bankname": "jazzcash",
                "phone": "03409297123",
                "password": "pass",
                "pin": "1234",
                "name": "JazzCash Test",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], 533302)
        self.assertEqual(result["data"]["next_step"], "second_login")
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=533302)
        self.assertIsNone(await self.redis.get(redis_key))
        self.jazzcash._is_logined.assert_awaited_once()

        with self.assertRaises(NewApiError) as ctx:
            await self.jazzcash.send_otp_http(
                {"bankname": "jazzcash", "payment_id": "533302"}
            )
        self.assertEqual(ctx.exception.code, ErrorCode.SessionNotExist)

    def test_pre_login_bound_same_partner_without_cloud_falls_back_to_login_step1(self):
        asyncio.run(self._run_pre_login_bound_without_cloud_case())

    async def _run_pre_login_bound_without_cloud_case(self):
        self.jazzcash._check_login_failed_attempts = AsyncMock(return_value=False)
        self.jazzcash._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.jazzcash._check_payment = AsyncMock(return_value=self._bound_payment_dict())
        self.jazzcash._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._is_logined = AsyncMock(return_value={"code": 403, "data": False})
        self.jazzcash._select_proxy_ip = AsyncMock(return_value="127.0.0.1:1080")

        result = await self.jazzcash.pre_login_http(
            {
                "step": "complete_login",
                "bankname": "jazzcash",
                "phone": "03409297123",
                "password": "pass",
                "pin": "1234",
                "name": "JazzCash Test",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["id"], 533302)
        self.assertEqual(result["data"]["next_step"], "send_otp")
        self.assertFalse(result["data"]["is_new_user"])
        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id=533302)
        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(stored["status"], LoginStatus.PRE_LOGIN)
        self.assertEqual(stored["phone"], "03409297123")
        self.jazzcash._is_logined.assert_awaited_once()
        self.jazzcash._select_proxy_ip.assert_awaited_once_with("jazzcash")

    def test_pre_login_bound_other_partner_is_rejected(self):
        asyncio.run(self._run_pre_login_bound_other_partner_case())

    async def _run_pre_login_bound_other_partner_case(self):
        self.jazzcash._check_login_failed_attempts = AsyncMock(return_value=False)
        self.jazzcash._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.jazzcash._check_payment = AsyncMock(return_value=self._bound_payment_dict(user_id=8))
        self.jazzcash._is_logined = AsyncMock(side_effect=AssertionError("其他码商账号不应调用 isLogined"))

        with self.assertRaises(NewApiError) as ctx:
            await self.jazzcash.pre_login_http(
                {
                    "step": "complete_login",
                    "bankname": "jazzcash",
                    "phone": "03409297123",
                    "password": "pass",
                    "pin": "1234",
                    "name": "JazzCash Test",
                }
            )

        self.assertEqual(ctx.exception.code, "10402")
        self.jazzcash._is_logined.assert_not_awaited()

    def test_pre_login_payment_id_rejects_same_phone_other_payment_id(self):
        asyncio.run(self._run_pre_login_payment_id_other_payment_case())

    async def _run_pre_login_payment_id_other_payment_case(self):
        payment = self._payment_row(payment_id=533302)
        query = MagicMock()
        query.filter.return_value.first.return_value = payment
        self.db_session.query = MagicMock(return_value=query)
        self.jazzcash._get_bank_type_id = AsyncMock(return_value=98)
        self.jazzcash._check_login_failed_attempts = AsyncMock(return_value=False)
        self.jazzcash._verify_payment_password_bcrypt = AsyncMock(return_value=True)
        self.jazzcash._check_payment = AsyncMock(
            return_value=self._bound_payment_dict(payment_id=533399)
        )
        self.jazzcash._is_logined = AsyncMock(side_effect=AssertionError("同号其他payment不应调用isLogined"))

        with self.assertRaises(NewApiError) as ctx:
            await self.jazzcash.pre_login_http(
                {
                    "step": "complete_login",
                    "bankname": "jazzcash",
                    "payment_id": "533302",
                    "phone": "03409297123",
                    "password": "pass",
                    "pin": "1234",
                    "name": "JazzCash Test",
                }
            )

        self.assertEqual(ctx.exception.code, "10402")
        self.jazzcash._is_logined.assert_not_awaited()

    def test_second_login_bound_payment_without_redis_activates_mysql_final_state(self):
        asyncio.run(self._run_second_login_bound_without_redis_case())

    async def _run_second_login_bound_without_redis_case(self):
        payment = self._payment_row()
        query = MagicMock()
        query.filter.return_value.first.return_value = payment
        self.db_session.query = MagicMock(return_value=query)
        self.jazzcash._get_bank_type_id = AsyncMock(return_value=98)
        self.jazzcash._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "lock", "lock_value": "value"}
        )
        self.jazzcash._release_payment_interface_lock = AsyncMock(return_value=True)
        self.jazzcash._is_logined = AsyncMock(return_value={"code": 200, "data": True})
        self.jazzcash._verify_account = AsyncMock(return_value=self._success_account_status())
        self.jazzcash._update_payment = AsyncMock(return_value=533302)

        result = await self.jazzcash.second_login_http(
            {"bankname": "jazzcash", "payment_id": "533302"}
        )

        redis_key = self.jazzcash.PRELOGIN_KEY.format(bankname="jazzcash", payment_id="533302")
        stored = json.loads(await self.redis.get(redis_key))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["phase"], LoginStatus.ACTIVE_SUCCESSFUL)
        self.assertEqual(stored["status"], LoginStatus.ACTIVE_SUCCESSFUL)
        self.assertEqual(stored["phone"], "03409297123")
        self.jazzcash._is_logined.assert_awaited_once()
        self.jazzcash._verify_account.assert_awaited_once()

        update_kwargs = self.jazzcash._update_payment.await_args.kwargs
        self.assertIn("account_entire", update_kwargs)
        self.assertEqual(update_kwargs["account_iban"], "PK00JAZZCASH000000001")
        self.assertIsNone(update_kwargs.get("account_accno"))


if __name__ == "__main__":
    unittest.main()
