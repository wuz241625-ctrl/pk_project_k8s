import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.ttl_map = {}
        self.sets = {}
        self.zsets = {}
        self.lists = {}

    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True

    async def setex(self, key, ttl, value):
        self.kv[key] = value
        self.ttl_map[key] = ttl
        return True

    async def ttl(self, key):
        if key not in self.kv:
            return -2
        return self.ttl_map.get(key, -1)

    async def delete(self, key):
        self.kv.pop(key, None)
        self.ttl_map.pop(key, None)
        return True

    async def sadd(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        for value in values:
            bucket.add(str(value))
        return True

    async def srem(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        for value in values:
            bucket.discard(str(value))
        return True

    async def sismember(self, key, value):
        return str(value) in self.sets.get(key, set())

    async def smembers(self, key):
        return self.sets.get(key, set())

    async def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return True

    async def lrem(self, key, count, value):
        bucket = self.lists.setdefault(key, [])
        target = str(value)
        if count == 0:
            self.lists[key] = [item for item in bucket if item != target]
            return True
        raise NotImplementedError("test fake only supports count=0")

    async def rpush(self, key, value):
        bucket = self.lists.setdefault(key, [])
        bucket.append(str(value))
        return len(bucket)


class EasyPaisaRuntimeReaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()

    async def _seed_active_snapshot(self, *, dispatch_ds=True):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: 1_744_000_000)
        await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "secondLoginPassed",
            },
            source="test",
        )
        await service.mark_active_successful(
            533280,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="test",
            online_ttl=660,
            dispatch_ds=dispatch_ds,
        )

    async def test_reader_prefers_runtime_snapshot_when_enabled(self):
        from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader

        await self._seed_active_snapshot()
        reader = EasyPaisaRuntimeReader(self.redis)

        self.assertTrue(await reader.is_place_order_online(533280))
        self.assertTrue(await reader.is_selling_order_online(533280))

    async def test_reader_falls_back_to_legacy_when_runtime_flag_disabled(self):
        from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader

        await self.redis.sadd("payment_online_df", 533280)
        await self.redis.sadd("payment_online_ds", 533280)

        with patch.dict(os.environ, {"EASYPAISA_RUNTIME_READ_ENABLED": "0"}):
            reader = EasyPaisaRuntimeReader(self.redis)
            self.assertTrue(await reader.is_place_order_online(533280))
            self.assertTrue(await reader.is_selling_order_online(533280))

    async def test_easypaisa_pay_service_reads_runtime_snapshot(self):
        from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService

        await self._seed_active_snapshot()
        service = EasyPaisaPayService(
            db_orm=SimpleNamespace(sessionmaker=lambda: None),
            redis=self.redis,
            redis_pub=MagicMock(),
            logger=MagicMock(),
        )

        self.assertTrue(await service.place_order_status(533280))
        self.assertTrue(await service.selling_order_status(533280))

    async def test_upi_handler_status_helpers_read_runtime_snapshot(self):
        from application.lakshmi_api.controllers.upi_controller import UpiHandler

        await self._seed_active_snapshot()
        handler = SimpleNamespace(redis=self.redis)

        self.assertTrue(await UpiHandler._check_place_order_status(handler, 533280))
        self.assertTrue(await UpiHandler._check_selling_order_status(handler, 533280))

    async def test_upi_handler_collection_online_payment_ids_include_runtime_dispatch_ds(self):
        from application.lakshmi_api.controllers.upi_controller import UpiHandler

        await self._seed_active_snapshot(dispatch_ds=True)
        handler = SimpleNamespace(redis=self.redis)

        self.assertEqual(await UpiHandler._collection_online_payment_ids(handler), ["533280"])

    async def test_reader_separates_dispatch_df_and_dispatch_ds(self):
        from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader

        await self._seed_active_snapshot(dispatch_ds=False)
        reader = EasyPaisaRuntimeReader(self.redis)

        self.assertTrue(await reader.is_place_order_online(533280))
        self.assertFalse(await reader.is_selling_order_online(533280))
        self.assertFalse(await reader.is_collection_order_online(533280))

    async def test_collection_online_payment_ids_reads_runtime_dispatch_ds(self):
        from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader

        await self._seed_active_snapshot(dispatch_ds=True)
        reader = EasyPaisaRuntimeReader(self.redis)

        self.assertEqual(await reader.collection_online_payment_ids(), {"533280"})


if __name__ == "__main__":
    unittest.main()
