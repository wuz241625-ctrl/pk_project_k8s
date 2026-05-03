import json
import unittest
from fnmatch import fnmatch

from application.easypaisa_runtime import keyspace


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.ttl_map = {}
        self.sets = {}
        self.zsets = {}
        self.lists = {}
        self.hashes = {}

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

    def scan_iter(self, pattern):
        for key in self.kv:
            if fnmatch(key, pattern):
                yield key.encode("utf-8")

    async def hset(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        bucket[str(field)] = value
        return 1

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    async def hdel(self, key, *fields):
        bucket = self.hashes.setdefault(key, {})
        removed = 0
        for field in fields:
            text = str(field)
            existed = text in bucket
            bucket.pop(text, None)
            removed += 1 if existed else 0
        return removed

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

    async def zrem(self, key, *members):
        bucket = self.zsets.setdefault(key, {})
        removed = 0
        for member in members:
            text = str(member)
            existed = text in bucket
            bucket.pop(text, None)
            removed += 1 if existed else 0
        return removed

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

    async def test_mark_active_successful_clears_runtime_and_legacy_kickoff_keys(self):
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
        await self.redis.setex(keyspace.kickoff_key(533280), 1200, "1")
        await self.redis.setex(keyspace.legacy_kickoff_key(533280), 1200, "1")

        await service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="login_flow",
            online_ttl=660,
        )

        self.assertIsNone(await self.redis.get(keyspace.kickoff_key(533280)))
        self.assertIsNone(await self.redis.get(keyspace.legacy_kickoff_key(533280)))

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

    async def test_requeue_ds_if_online_routes_channel_queue_through_runtime_bridge(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533280
        await service.mark_active_successful(
            payment_id,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="test",
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
            channels=["1001"],
        )
        await self.redis.lrem("payment_active_1001", 0, payment_id)

        self.assertTrue(
            await service.requeue_ds_if_online(
                payment_id,
                channels=["1001"],
                source="timeout_requeue",
            )
        )
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])

    async def test_collect_enabled_keeps_jobs_when_ds_order_disabled(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = await service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            online_ttl=660,
            channels=["1001"],
            collect_enabled=True,
            ds_order_enabled=False,
            df_order_enabled=True,
        )

        self.assertTrue(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertTrue(snapshot["df_order_enabled"])
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:collect_enabled", 533280))
        self.assertTrue(await self.redis.sismember("easypaisa_runtime:index:df_order_enabled", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:ds_order_enabled", 533280))
        self.assertIsNotNone(await self.redis.zscore(keyspace.SCHEDULE_COLLECTION, 533280))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists.get("payment_active_1001", []), [])
        self.assertTrue(await self.redis.sismember("payment_online_df", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], ["533280"])

    async def test_collect_disabled_cleans_all_runtime_projections(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            online_ttl=660,
            channels=["1001"],
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        snapshot = await service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno=None,
            selected_iban=None,
            source="admin_disable_collect",
            online_ttl=660,
            collect_enabled=False,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        self.assertFalse(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["df_order_enabled"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertFalse(snapshot["dispatch_df"])
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:collect_enabled", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:ds_order_enabled", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:df_order_enabled", 533280))
        self.assertIsNone(await self.redis.zscore(keyspace.SCHEDULE_COLLECTION, 533280))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 533280))
        self.assertFalse(await self.redis.sismember("payment_online_df", 533280))
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertEqual(self.redis.lists["payment_active_df"], [])

    async def test_pause_order_dispatch_keeps_collection_session_and_job_queue(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533280
        await service.mark_active_successful(
            payment_id,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="statement_worker",
            online_ttl=660,
            channels=["1001"],
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )
        await service.write_session(payment_id, {"status": "activeSuccessful"})
        await self.redis.hset(keyspace.JOB_HASH, payment_id, '{"status":"grabstatement"}')
        await self.redis.zadd(keyspace.JOB_SET, {payment_id: self.now})

        snapshot = await service.pause_order_dispatch(
            payment_id,
            phone="923045536108",
            channels=["1001"],
            source="admin_payment_disable",
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["df_order_enabled"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertFalse(snapshot["dispatch_df"])
        self.assertIsNotNone(await self.redis.get(keyspace.session_key(payment_id)))
        self.assertIsNotNone(await self.redis.hget(keyspace.JOB_HASH, payment_id))
        self.assertIsNotNone(await self.redis.zscore(keyspace.JOB_SET, payment_id))
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, payment_id))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, payment_id))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, payment_id))
        self.assertFalse(await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id))
        self.assertFalse(await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id))
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertEqual(self.redis.lists["payment_active_df"], [])

    async def test_set_df_order_dispatch_does_not_change_ds_dispatch(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533280
        await service.mark_active_successful(
            payment_id,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="statement_worker",
            online_ttl=660,
            channels=["1001"],
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        snapshot = await service.set_df_order_dispatch(
            payment_id,
            enabled=False,
            channels=["1001"],
            source="websocket_df_offline",
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertTrue(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["df_order_enabled"])
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, payment_id))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, payment_id))
        self.assertTrue(await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id))
        self.assertFalse(await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id))
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])
        self.assertEqual(self.redis.lists["payment_active_df"], [])

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

    async def test_set_ds_order_dispatch_can_disable_ds_without_disabling_collection(self):
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
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        snapshot = await service.set_ds_order_dispatch(
            533280,
            enabled=False,
            phone="923045536108",
            channels=["1001"],
            source="app_selling_inactive",
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertTrue(snapshot["df_order_enabled"])
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, 533280))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, 533280))
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, 533280))
        self.assertIsNotNone(await self.redis.zscore(keyspace.SCHEDULE_COLLECTION, 533280))

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

    async def test_force_reset_cleans_prelogin_kickoff_and_job_keys(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533280
        phone = "923045536108"
        await service.mark_active_successful(
            payment_id,
            phone=phone,
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            online_ttl=660,
            channels=["1001"],
            dispatch_ds=True,
        )
        await service.write_session(payment_id, {"status": "otpSent"})
        await self.redis.set(keyspace.pre_login_key(payment_id), json.dumps({"status": "otpSent"}))
        await self.redis.set(
            keyspace.pre_login_key("03145168419"),
            json.dumps(
                {
                    "kind": "payment_id_alias",
                    "target_payment_id": str(payment_id),
                    "bankname": "easypaisa",
                    "phone": "03145168419",
                }
            ),
        )
        await self.redis.setex(keyspace.kickoff_key(payment_id), 1200, "1")
        await self.redis.setex(keyspace.legacy_kickoff_key(payment_id), 1200, "1")
        await self.redis.setex(keyspace.health_pause_order_key(payment_id), 180, "api_error")
        await self.redis.hset(keyspace.JOB_HASH, payment_id, json.dumps({"status": "grabstatement"}))
        await self.redis.zadd(keyspace.JOB_SET, {payment_id: self.now + 1})

        snapshot = await service.force_reset(
            payment_id,
            phone=phone,
            source="app_change_payment",
        )

        self.assertFalse(snapshot["online"])
        self.assertEqual(snapshot["session_phase"], "offline")
        self.assertIsNone(await self.redis.get(keyspace.session_key(payment_id)))
        self.assertIsNone(await self.redis.get(keyspace.pre_login_key(payment_id)))
        self.assertIsNone(await self.redis.get(keyspace.pre_login_key("03145168419")))
        self.assertIsNone(await self.redis.get(keyspace.kickoff_key(payment_id)))
        self.assertIsNone(await self.redis.get(keyspace.legacy_kickoff_key(payment_id)))
        self.assertIsNone(await self.redis.get(keyspace.health_pause_order_key(payment_id)))
        self.assertIsNone(await self.redis.hget(keyspace.JOB_HASH, payment_id))
        self.assertIsNone(await self.redis.zscore(keyspace.JOB_SET, payment_id))

    async def test_sync_collection_job_state_updates_runtime_and_job_projection(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = await service.sync_collection_job_state(
            {
                "id": 533280,
                "phone": "923045536108",
                "status": "grabstatement",
                "partner_id": 7,
                "qr_channel": 1001,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
            },
            source="login_flow",
            schedule_score=1_744_000_321,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertTrue(snapshot["ds_order_enabled"])
        self.assertTrue(snapshot["df_order_enabled"])
        self.assertEqual(snapshot["channels"], ["1001"])
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, 533280))
        self.assertTrue(await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, 533280))
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])
        self.assertEqual(await self.redis.zscore(keyspace.JOB_SET, 533280), float(1_744_000_321))
        self.assertIsNotNone(await self.redis.hget(keyspace.JOB_HASH, 533280))

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

    async def test_manual_off_is_recorded_in_snapshot(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533294
        await service.mark_active_successful(
            payment_id,
            phone="03045536108",
            selected_accno="88521643",
            selected_iban="PK12TMFB0000000088521643",
            source="monitor",
            dispatch_ds=True,
            channels=["1001"],
        )

        await service.set_manual_off(payment_id, reason="admin_manual")
        snapshot = await service.read_snapshot(payment_id)

        self.assertTrue(snapshot["manual_ds_paused"])
        self.assertEqual(snapshot["manual_ds_pause_reason"], "admin_manual")
        self.assertTrue(await service.is_manual_off(payment_id))

        await service.clear_manual_off(payment_id)
        snapshot = await service.read_snapshot(payment_id)

        self.assertFalse(snapshot["manual_ds_paused"])
        self.assertIsNone(snapshot["manual_ds_pause_reason"])
        self.assertFalse(await service.is_manual_off(payment_id))
        self.assertIsNone(await self.redis.get(keyspace.manual_off_collection_key(payment_id)))

    async def test_order_health_pause_is_recorded_in_snapshot(self):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533295
        await service.mark_active_successful(
            payment_id,
            phone="03045536109",
            selected_accno="88521644",
            selected_iban="PK12TMFB0000000088521644",
            source="monitor",
            dispatch_ds=True,
            channels=["1001"],
        )

        snapshot = await service.set_order_health_pause(
            payment_id,
            reason="api_error",
            ttl=180,
            source="monitor_health_error",
            phone="03045536109",
            channels=["1001"],
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["df_order_enabled"])
        self.assertTrue(snapshot["order_health_paused"])
        self.assertEqual(snapshot["order_health_pause_reason"], "api_error")
        self.assertEqual(snapshot["order_health_paused_until"], self.now + 180)
        self.assertTrue(await service.is_order_health_paused(payment_id))

        await service.clear_order_health_pause(payment_id, source="monitor_success")
        snapshot = await service.read_snapshot(payment_id)

        self.assertFalse(snapshot["order_health_paused"])
        self.assertIsNone(snapshot["order_health_pause_reason"])
        self.assertEqual(snapshot["order_health_paused_until"], 0)
        self.assertFalse(await service.is_order_health_paused(payment_id))
        self.assertIsNone(await self.redis.get(keyspace.health_pause_order_key(payment_id)))


class KeyspaceConstantsTests(unittest.TestCase):
    def test_keyspace_has_manual_off_collection_key_helper(self):
        assert keyspace.MANUAL_OFF_COLLECTION_KEY == "easypaisa_runtime:manual_off:collection:{payment_id}"
        assert keyspace.manual_off_collection_key(533294) == "easypaisa_runtime:manual_off:collection:533294"

    def test_keyspace_has_health_pause_order_key_helper(self):
        assert keyspace.HEALTH_PAUSE_ORDER_KEY == "easypaisa_runtime:health_pause:order:{payment_id}"
        assert keyspace.health_pause_order_key(533294) == "easypaisa_runtime:health_pause:order:533294"

    def test_keyspace_has_schedule_collection_constant(self):
        assert keyspace.SCHEDULE_COLLECTION == "easypaisa_runtime:schedule:collection"


if __name__ == "__main__":
    unittest.main()
