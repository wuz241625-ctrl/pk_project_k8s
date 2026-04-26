import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.sets = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value):
        self.kv[key] = value
        return True

    async def sadd(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        for value in values:
            bucket.add(str(value))
        return True

    async def sismember(self, key, value):
        return str(value) in self.sets.get(key, set())

    async def smembers(self, key):
        return self.sets.get(key, set())


class JazzCashRuntimeReaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()

    async def _seed_snapshot(self, payment_id=7001, **patch):
        from application.jazzcash_runtime import keyspace

        payload = {
            "payment_id": payment_id,
            "phone": "03495863120",
            "online": True,
            "collect_enabled": True,
            "ds_order_enabled": True,
            "df_order_enabled": True,
            "dispatch_ds": True,
            "dispatch_df": True,
            "session_phase": "activeSuccessful",
        }
        payload.update(patch)
        await self.redis.set(keyspace.snapshot_key(payment_id), json.dumps(payload))

    async def test_reader_uses_snapshot_and_ignores_stale_legacy_for_jazzcash(self):
        from application.jazzcash_runtime.reader import JazzCashRuntimeReader

        await self._seed_snapshot(dispatch_ds=False, ds_order_enabled=False)
        await self.redis.sadd("payment_online_ds", 7001)

        reader = JazzCashRuntimeReader(self.redis)

        self.assertFalse(await reader.is_collection_order_online(7001))
        self.assertTrue(await reader.is_place_order_online(7001))

    async def test_reader_does_not_trust_legacy_when_snapshot_missing(self):
        from application.jazzcash_runtime.reader import JazzCashRuntimeReader

        await self.redis.sadd("payment_online_ds", 7001)
        await self.redis.sadd("payment_online_df", 7001)

        reader = JazzCashRuntimeReader(self.redis)

        self.assertFalse(await reader.is_collection_order_online(7001))
        self.assertFalse(await reader.is_place_order_online(7001))

    async def test_reader_can_fallback_to_legacy_when_runtime_flag_disabled(self):
        from application.jazzcash_runtime.reader import JazzCashRuntimeReader

        await self.redis.sadd("payment_online_ds", 7001)
        await self.redis.sadd("payment_online_df", 7001)

        with patch.dict(os.environ, {"JAZZCASH_RUNTIME_READ_ENABLED": "0"}):
            reader = JazzCashRuntimeReader(self.redis)
            self.assertTrue(await reader.is_collection_order_online(7001))
            self.assertTrue(await reader.is_place_order_online(7001))

    async def test_upi_handler_treats_jazzcash_as_runtime_owned(self):
        from application.lakshmi_api.controllers.upi_controller import UpiHandler

        await self.redis.sadd("payment_online_ds", 7001)
        await self.redis.sadd("payment_online_df", 7001)
        handler = SimpleNamespace(redis=self.redis)

        self.assertFalse(await UpiHandler._check_selling_order_status(handler, 7001, bank_type_id=98, bank_type=98))
        self.assertFalse(await UpiHandler._check_place_order_status(handler, 7001, bank_type_id=98, bank_type=98))

    async def test_upi_handler_collects_jazzcash_runtime_dispatch_ds_ids(self):
        from application.jazzcash_runtime import keyspace
        from application.lakshmi_api.controllers.upi_controller import UpiHandler

        await self._seed_snapshot(payment_id=7001, dispatch_ds=True, ds_order_enabled=True)
        await self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, 7001)
        handler = SimpleNamespace(redis=self.redis, db_orm=None)

        self.assertEqual(await UpiHandler._collection_online_payment_ids(handler), ["7001"])

    async def test_pay_requeue_ignores_legacy_kickoff_for_jazzcash(self):
        from application.pay.pay import _has_collection_kickoff

        await self.redis.set("kick_off_7001", "1")
        handler = SimpleNamespace(
            redis=self.redis,
            get_result_by_condition=AsyncMock(return_value={"bank_type": 98, "bank_type_id": 98}),
        )

        self.assertFalse(await _has_collection_kickoff(handler, 7001))

    async def test_pay_requeue_uses_runtime_kickoff_for_jazzcash(self):
        from application.pay.pay import _has_collection_kickoff

        await self.redis.set("jazzcash_runtime:kickoff:7001", "admin_off")
        handler = SimpleNamespace(
            redis=self.redis,
            get_result_by_condition=AsyncMock(return_value={"bank_type": 98, "bank_type_id": 98}),
        )

        self.assertTrue(await _has_collection_kickoff(handler, 7001))


if __name__ == "__main__":
    unittest.main()
