import json
import unittest

from application.easypaisa_runtime import keyspace


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

    async def delete(self, key):
        existed = key in self.kv
        self.kv.pop(key, None)
        self.ttl_map.pop(key, None)
        return 1 if existed else 0

    async def ttl(self, key):
        if key not in self.kv:
            return -2
        return self.ttl_map.get(key, -1)

    async def sadd(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        for value in values:
            bucket.add(str(value))
        return len(bucket) - before

    async def srem(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        removed = 0
        for value in values:
            removed += 1 if str(value) in bucket else 0
            bucket.discard(str(value))
        return removed

    async def sismember(self, key, value):
        return str(value) in self.sets.get(key, set())

    async def smembers(self, key):
        return self.sets.get(key, set())

    async def scard(self, key):
        return len(self.sets.get(key, set()))

    async def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return True

    async def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    async def lrem(self, key, count, value):
        bucket = self.lists.setdefault(key, [])
        target = str(value)
        if count == 0:
            removed = bucket.count(target)
            self.lists[key] = [item for item in bucket if item != target]
            return removed
        raise NotImplementedError("test fake only supports count=0")

    async def rpush(self, key, value):
        bucket = self.lists.setdefault(key, [])
        bucket.append(str(value))
        return len(bucket)


class EasyPaisaRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.now = 1_744_000_000

    async def test_write_snapshot_persists_json_and_updated_index(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "preLoginCreated",
                "online": False,
            },
            source="login_flow",
        )

        self.assertEqual(snapshot["payment_id"], 533280)
        self.assertEqual(snapshot["phone"], "923045536108")
        self.assertEqual(snapshot["session_phase"], "preLoginCreated")
        self.assertEqual(snapshot["last_source"], "login_flow")
        self.assertEqual(snapshot["updated_at"], self.now)

        raw = await self.redis.get("easypaisa_runtime:snapshot:533280")
        stored = json.loads(raw)
        self.assertEqual(stored["payment_id"], 533280)
        self.assertEqual(await self.redis.zscore("easypaisa_runtime:index:updated_at", 533280), float(self.now))

    async def test_mark_active_successful_updates_runtime_and_legacy_bridge(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "secondLoginPassed",
                "online": False,
                "dispatch_df": False,
            },
            source="login_flow",
        )

        snapshot = await service.mark_active_successful(
            533280,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="login_flow",
            online_ttl=660,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["dispatch_df"])
        self.assertEqual(snapshot["session_phase"], "activeSuccessful")
        self.assertEqual(snapshot["selected_accno"], "88521643")
        self.assertEqual(snapshot["selected_iban"], "PK12HABB0000000088521643")

        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:online", 533280))
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:dispatch_df", 533280))
        self.assertTrue(await self.redis.sismember("payment_online_df", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], ["533280"])
        self.assertEqual(await self.redis.get("login_on_easypaisa_533280"), "1")
        self.assertEqual(await self.redis.ttl("login_on_easypaisa_533280"), 660)
        self.assertEqual(await self.redis.get("login_on_easypaisa_923045536108"), "1")

    async def test_mark_active_successful_can_enable_dispatch_ds_projection(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "secondLoginPassed",
                "online": False,
                "dispatch_df": False,
                "dispatch_ds": False,
                "channels": ["1001"],
            },
            source="statement_worker",
        )

        snapshot = await service.mark_active_successful(
            533280,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="statement_worker",
            online_ttl=660,
            dispatch_ds=True,
        )

        self.assertTrue(snapshot["dispatch_ds"])
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:dispatch_ds", 533280))
        self.assertTrue(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(snapshot["channels"], ["1001"])
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])

    async def test_mark_active_successful_without_dispatch_ds_cleans_collection_channel_queue(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "activeSuccessful",
                "online": True,
                "dispatch_df": True,
                "dispatch_ds": True,
                "channels": ["1001"],
                "selected_accno": "88521643",
                "selected_iban": "PK12HABB0000000088521643",
            },
            source="statement_worker",
        )
        await service.mark_active_successful(
            533280,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="statement_worker",
            online_ttl=660,
            dispatch_ds=True,
        )

        snapshot = await service.mark_active_successful(
            533280,
            selected_accno=None,
            selected_iban=None,
            source="easypaisa_monitor",
            online_ttl=660,
            dispatch_ds=False,
        )

        self.assertFalse(snapshot["dispatch_ds"])
        self.assertEqual(snapshot["selected_accno"], "88521643")
        self.assertEqual(snapshot["selected_iban"], "PK12HABB0000000088521643")
        self.assertEqual(snapshot["channels"], ["1001"])
        self.assertFalse(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_1001"], [])

    async def test_set_collection_dispatch_can_enable_channel_projection_without_touching_dispatch_df(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="login_flow",
            online_ttl=660,
            channels=["1001"],
            dispatch_ds=False,
        )

        snapshot = await service.set_collection_dispatch(
            533280,
            enabled=True,
            phone="923045536108",
            channels=["1001"],
            source="app_selling_active",
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["dispatch_df"])
        self.assertTrue(snapshot["dispatch_ds"])
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:dispatch_df", 533280))
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:dispatch_ds", 533280))
        self.assertTrue(await self.redis.sismember("payment_online_df", 533280))
        self.assertTrue(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], ["533280"])
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])

    async def test_set_collection_dispatch_can_disable_channel_projection_without_offlining_payment(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="statement_worker",
            online_ttl=660,
            channels=["1001"],
            dispatch_ds=True,
        )

        snapshot = await service.set_collection_dispatch(
            533280,
            enabled=False,
            phone="923045536108",
            channels=["1001"],
            source="app_selling_inactive",
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["dispatch_df"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:dispatch_df", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:dispatch_ds", 533280))
        self.assertTrue(await self.redis.sismember("payment_online_df", 533280))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], ["533280"])
        self.assertEqual(self.redis.lists["payment_active_1001"], [])

    async def test_force_offline_cleans_runtime_and_legacy_bridge(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "activeSuccessful",
                "online": True,
                "dispatch_df": True,
                "channels": ["1001"],
            },
            source="monitor",
        )
        await service.mark_active_successful(
            533280,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            online_ttl=660,
            dispatch_ds=True,
        )
        await self.redis.set(keyspace.lock_payment_key(533280), "1")
        await self.redis.set(keyspace.lock_phone_key("923045536108"), "1")

        snapshot = await service.force_offline(
            533280,
            source="cleanup",
            reason="inactive_cleanup",
        )

        self.assertFalse(snapshot["online"])
        self.assertFalse(snapshot["dispatch_df"])
        self.assertEqual(snapshot["session_phase"], "offline")
        self.assertEqual(snapshot["last_transition"], "inactive_cleanup")
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:online", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:dispatch_df", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:dispatch_ds", 533280))
        self.assertFalse(await self.redis.sismember("payment_online_df", 533280))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], [])
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertIsNone(await self.redis.get("login_on_easypaisa_533280"))
        self.assertIsNone(await self.redis.get("login_on_easypaisa_923045536108"))
        self.assertIsNone(await self.redis.get(keyspace.lock_payment_key(533280)))
        self.assertIsNone(await self.redis.get(keyspace.lock_phone_key("923045536108")))

    async def test_store_account_selection_writes_account_fields(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "secondLoginPassed",
            },
            source="query_accts",
        )

        account_options = [
            {
                "accno": "88521642",
                "accountStatus": "ACTIVE",
                "IBAN": "PK12TMFB0000000088521642",
            },
            {
                "accno": "88521643",
                "accountStatus": "ACTIVE",
                "IBAN": "PK12HABB0000000088521643",
            },
        ]

        snapshot = await service.store_account_selection(
            533280,
            account_options=account_options,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="query_accts",
        )

        self.assertEqual(snapshot["account_options"], account_options)
        self.assertEqual(snapshot["selected_accno"], "88521643")
        self.assertEqual(snapshot["selected_iban"], "PK12HABB0000000088521643")
        self.assertEqual(snapshot["session_phase"], "accountSelectionRequired")


if __name__ == "__main__":
    unittest.main()
