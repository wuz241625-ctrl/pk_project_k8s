import asyncio
import json
import os
import sys
import unittest
from fnmatch import fnmatch
from unittest.mock import AsyncMock, MagicMock

from application.easypaisa_runtime import keyspace

API_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JOBS_ROOT = os.path.join(API_ROOT, "jobs")
if JOBS_ROOT not in sys.path:
    sys.path.insert(0, JOBS_ROOT)


class FakeSyncRedis:
    def __init__(self):
        self.kv = {}
        self.ttl_map = {}
        self.sets = {}
        self.zsets = {}
        self.lists = {}
        self.hashes = {}

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True

    def setex(self, key, ttl, value):
        self.kv[key] = value
        self.ttl_map[key] = ttl
        return True

    def delete(self, key):
        existed = key in self.kv
        self.kv.pop(key, None)
        self.ttl_map.pop(key, None)
        return 1 if existed else 0

    def hset(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        bucket[str(field)] = value
        return 1

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    def hdel(self, key, *fields):
        bucket = self.hashes.setdefault(key, {})
        removed = 0
        for field in fields:
            text = str(field)
            existed = text in bucket
            bucket.pop(text, None)
            removed += 1 if existed else 0
        return removed

    def ttl(self, key):
        if key not in self.kv:
            return -2
        return self.ttl_map.get(key, -1)

    def sadd(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        for value in values:
            bucket.add(str(value))
        return len(bucket) - before

    def srem(self, key, *values):
        bucket = self.sets.setdefault(key, set())
        removed = 0
        for value in values:
            removed += 1 if str(value) in bucket else 0
            bucket.discard(str(value))
        return removed

    def sismember(self, key, value):
        return str(value) in self.sets.get(key, set())

    def smembers(self, key):
        return self.sets.get(key, set())

    def scan_iter(self, pattern):
        for key in self.kv:
            if fnmatch(key, pattern):
                yield key.encode("utf-8")

    def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return True

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    def zrem(self, key, *members):
        bucket = self.zsets.setdefault(key, {})
        removed = 0
        for member in members:
            text = str(member)
            existed = text in bucket
            bucket.pop(text, None)
            removed += 1 if existed else 0
        return removed

    def lrem(self, key, count, value):
        bucket = self.lists.setdefault(key, [])
        target = str(value)
        if count == 0:
            removed = bucket.count(target)
            self.lists[key] = [item for item in bucket if item != target]
            return removed
        raise NotImplementedError("test fake only supports count=0")

    def rpush(self, key, value):
        bucket = self.lists.setdefault(key, [])
        bucket.append(str(value))
        return len(bucket)

    def lpop(self, key):
        bucket = self.lists.setdefault(key, [])
        if not bucket:
            return None
        return bucket.pop(0).encode("utf-8")

    def lrange(self, key, start, stop):
        bucket = self.lists.get(key, [])
        if stop == -1:
            return [item.encode("utf-8") for item in bucket[start:]]
        return [item.encode("utf-8") for item in bucket[start : stop + 1]]


class EasyPaisaSyncRuntimeServiceTests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeSyncRedis()
        self.now = 1_744_000_100

    def test_mark_active_successful_updates_runtime_and_legacy_bridge(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            online_ttl=660,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["dispatch_df"])
        self.assertEqual(snapshot["session_phase"], "activeSuccessful")
        self.assertEqual(snapshot["selected_accno"], "88521643")
        self.assertTrue(self.redis.sismember("easypaisa_runtime:index:online", 533280))
        self.assertTrue(self.redis.sismember("payment_online_df", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], ["533280"])
        self.assertEqual(self.redis.get("login_on_easypaisa_533280"), "1")
        self.assertEqual(self.redis.ttl("login_on_easypaisa_533280"), 660)

        raw = self.redis.get("easypaisa_runtime:snapshot:533280")
        stored = json.loads(raw)
        self.assertEqual(stored["phone"], "923045536108")
        self.assertEqual(self.redis.zscore("easypaisa_runtime:index:updated_at", 533280), float(self.now))

    def test_requeue_df_if_online_requires_runtime_snapshot_df_enabled(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533280
        self.redis.sadd("payment_online_df", payment_id)
        self.redis.rpush("payment_active_df", payment_id)

        self.assertFalse(service.requeue_df_if_online(payment_id))
        self.assertEqual(self.redis.lists["payment_active_df"], [])

        service.mark_active_successful(
            payment_id,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            collect_enabled=True,
            ds_order_enabled=False,
            df_order_enabled=True,
        )
        self.redis.lrem("payment_active_df", 0, payment_id)

        self.assertTrue(service.requeue_df_if_online(payment_id))
        self.assertEqual(self.redis.lists["payment_active_df"], ["533280"])

    def test_pop_df_order_candidate_uses_runtime_snapshot_and_drops_stale_legacy_entries(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        stale_id = 533279
        active_id = 533280
        self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, stale_id)
        self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, active_id)
        self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DF, stale_id, active_id)
        service.mark_active_successful(
            active_id,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            collect_enabled=True,
            df_order_enabled=True,
            ds_order_enabled=False,
        )

        self.assertEqual(service.pop_df_order_candidate(), "533280")
        self.assertFalse(self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, stale_id))
        self.assertEqual(self.redis.lists[keyspace.LEGACY_PAYMENT_ACTIVE_DF], [])

    def test_mark_active_successful_can_project_collection_channel_queue(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        service.write_snapshot(
            533280,
            {
                "phone": "923045536108",
                "session_phase": "secondLoginPassed",
                "online": False,
                "dispatch_df": False,
                "dispatch_ds": False,
                "channels": ["1001"],
            },
            source="pakistanpay_v2",
        )

        snapshot = service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="pakistanpay_v2",
            online_ttl=660,
            dispatch_ds=True,
        )

        self.assertTrue(snapshot["dispatch_ds"])
        self.assertEqual(snapshot["channels"], ["1001"])
        self.assertTrue(self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])

    def test_requeue_ds_if_online_routes_channel_queue_through_runtime_bridge(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 533280
        service.mark_active_successful(
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
        self.redis.lrem("payment_active_1001", 0, payment_id)

        self.assertTrue(
            service.requeue_ds_if_online(
                payment_id,
                channels=["1001"],
                source="timeout_requeue",
            )
        )
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])

    def test_mark_active_successful_without_dispatch_ds_cleans_collection_channel_queue(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        service.write_snapshot(
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
            source="pakistanpay_v2",
        )
        service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="pakistanpay_v2",
            online_ttl=660,
            dispatch_ds=True,
        )

        snapshot = service.mark_active_successful(
            533280,
            phone="923045536108",
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
        self.assertFalse(self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_1001"], [])

    def test_force_offline_cleans_runtime_and_legacy_bridge(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="monitor",
            online_ttl=660,
            channels=1001,
        )
        self.redis.set(keyspace.lock_payment_key(533280), "1")
        self.redis.set(keyspace.lock_phone_key("923045536108"), "1")

        snapshot = service.force_offline(
            533280,
            phone="923045536108",
            source="monitor",
            reason="monitor_api_error",
        )

        self.assertFalse(snapshot["online"])
        self.assertFalse(snapshot["dispatch_df"])
        self.assertEqual(snapshot["last_transition"], "monitor_api_error")
        self.assertFalse(self.redis.sismember("easypaisa_runtime:index:online", 533280))
        self.assertFalse(self.redis.sismember("payment_online_df", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], [])
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertIsNone(self.redis.get("login_on_easypaisa_533280"))
        self.assertIsNone(self.redis.get("login_on_easypaisa_923045536108"))
        self.assertIsNone(self.redis.get(keyspace.lock_payment_key(533280)))
        self.assertIsNone(self.redis.get(keyspace.lock_phone_key("923045536108")))

    def test_set_kickoff_writes_runtime_and_legacy_keys(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        self.redis.set(
            keyspace.pre_login_key("03045536108"),
            json.dumps(
                {
                    "kind": "payment_id_alias",
                    "target_payment_id": "533280",
                    "bankname": "easypaisa",
                    "phone": "03045536108",
                },
                ensure_ascii=True,
            ),
        )

        snapshot = service.set_kickoff(
            533280,
            phone="03045536108",
            ttl=1200,
            source="monitor",
            reason="force_logout",
        )

        self.assertEqual(self.redis.get("easypaisa_runtime:kickoff:533280"), "1")
        self.assertEqual(self.redis.ttl("easypaisa_runtime:kickoff:533280"), 1200)
        self.assertEqual(self.redis.get("kick_off_533280"), "1")
        self.assertEqual(self.redis.ttl("kick_off_533280"), 1200)
        self.assertFalse(snapshot["online"])
        self.assertEqual(snapshot["last_transition"], "force_logout")
        self.assertIsNone(self.redis.get(keyspace.pre_login_key("03045536108")))

    def test_sync_collection_job_state_updates_runtime_legacy_and_job_queue(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = service.sync_collection_job_state(
            {
                "id": 533280,
                "phone": "923045536108",
                "status": "grabstatement",
                "partner_id": 7,
                "qr_channel": 1001,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
            },
            source="pakistanpay_v2",
            schedule_score=1_744_000_321,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["dispatch_df"])
        self.assertTrue(snapshot["dispatch_ds"])
        self.assertTrue(self.redis.sismember("easypaisa_runtime:index:dispatch_ds", 533280))
        self.assertTrue(self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(snapshot["channels"], ["1001"])
        self.assertEqual(self.redis.lists["payment_active_1001"], ["533280"])
        self.assertEqual(self.redis.zscore("set_easypaisa", 533280), float(1_744_000_321))
        self.assertIsNotNone(self.redis.hget("hash_easypaisa", 533280))

    def test_sync_collection_job_state_preserves_existing_job_context_fields(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        self.redis.hset(
            "hash_easypaisa",
            533280,
            json.dumps(
                {
                    "id": 533280,
                    "phone": "923045536108",
                    "status": "grabstatement",
                    "qr_channel": 1001,
                    "authorization": "Bearer preserved-token",
                    "headers": {"X-Test": "keep"},
                },
                ensure_ascii=True,
            ),
        )

        service.sync_collection_job_state(
            {
                "id": 533280,
                "phone": "923045536108",
                "status": "grabstatement",
                "partner_id": 7,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
            },
            source="pakistanpay_v2",
            schedule_score=1_744_000_321,
        )

        merged = json.loads(self.redis.hget("hash_easypaisa", 533280))
        self.assertEqual(merged["qr_channel"], 1001)
        self.assertEqual(merged["authorization"], "Bearer preserved-token")
        self.assertEqual(merged["headers"], {"X-Test": "keep"})
        self.assertEqual(merged["account_accno"], "88521643")

    def test_sync_collection_job_state_with_collect_disabled_removes_job_queue(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        payment_id = 533280
        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        self.redis.hset(
            keyspace.JOB_HASH,
            payment_id,
            json.dumps(
                {
                    "id": payment_id,
                    "phone": "923045536108",
                    "status": "grabstatement",
                    "qr_channel": 1001,
                    "count": 42,
                },
                ensure_ascii=True,
            ),
        )
        self.redis.zadd(keyspace.JOB_SET, {payment_id: 1_744_000_200})
        self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
        self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        self.redis.rpush("payment_active_1001", payment_id)

        snapshot = service.sync_collection_job_state(
            {
                "id": payment_id,
                "phone": "923045536108",
                "status": "grabstatement",
                "partner_id": 7,
                "qr_channel": 1001,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
            },
            source="pakistanpay_v2",
            schedule_score=1_744_000_321,
            collect_enabled=False,
            ds_order_enabled=True,
        )

        self.assertTrue(snapshot["online"])
        self.assertFalse(snapshot["collect_enabled"])
        self.assertFalse(snapshot["dispatch_df"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertFalse(self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.INDEX_DISPATCH_DS, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id))
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertIsNone(self.redis.hget(keyspace.JOB_HASH, payment_id))
        self.assertIsNone(self.redis.zscore(keyspace.JOB_SET, payment_id))

    def test_sync_collection_job_state_keeps_collection_when_ds_order_disabled(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        payment_id = 533280
        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = service.sync_collection_job_state(
            {
                "id": payment_id,
                "phone": "923045536108",
                "status": "grabstatement",
                "partner_id": 7,
                "qr_channel": 1001,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
            },
            source="pakistanpay_v2",
            schedule_score=1_744_000_321,
            collect_enabled=True,
            ds_order_enabled=False,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertTrue(self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id))
        self.assertEqual(self.redis.lists.get("payment_active_1001", []), [])
        self.assertEqual(self.redis.zscore(keyspace.JOB_SET, payment_id), float(1_744_000_321))
        self.assertIsNotNone(self.redis.hget(keyspace.JOB_HASH, payment_id))

    def test_pause_order_dispatch_keeps_collection_session_and_job_queue(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        payment_id = 533280
        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        service.sync_collection_job_state(
            {
                "id": payment_id,
                "phone": "923045536108",
                "status": "grabstatement",
                "partner_id": 7,
                "qr_channel": 1001,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
            },
            source="pakistanpay_v2",
            schedule_score=1_744_000_321,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )
        self.redis.set(keyspace.session_key(payment_id), '{"status":"activeSuccessful"}')

        snapshot = service.pause_order_dispatch(
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
        self.assertIsNotNone(self.redis.get(keyspace.session_key(payment_id)))
        self.assertIsNotNone(self.redis.hget(keyspace.JOB_HASH, payment_id))
        self.assertIsNotNone(self.redis.zscore(keyspace.JOB_SET, payment_id))
        self.assertTrue(self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id))
        self.assertFalse(self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id))
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertEqual(self.redis.lists["payment_active_df"], [])


    def test_sync_set_collection_dispatch_enabled_mirrors_all_targets(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920001
        self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0304000001",
                        "online": True, "dispatch_ds": False, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )

        service.set_collection_dispatch(payment_id, enabled=True,
                                         channels=["1001"], source="test")

        snap = json.loads(self.redis.get(keyspace.snapshot_key(payment_id)))
        assert snap["collect_enabled"] is True
        assert snap["ds_order_enabled"] is True
        assert snap["dispatch_ds"] is True
        assert self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        assert self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, str(payment_id))
        assert self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        assert str(payment_id).encode() in self.redis.lrange("payment_active_1001", 0, -1)
        assert self.redis.zscore(keyspace.SCHEDULE_COLLECTION, str(payment_id)) is not None

    def test_sync_set_collection_dispatch_disabled_clears_all_targets(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920002
        self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0304000002",
                        "online": True, "dispatch_ds": True, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )
        self.redis.sadd(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        self.redis.rpush("payment_active_1001", str(payment_id))
        self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): 1_000})

        service.set_collection_dispatch(payment_id, enabled=False,
                                         channels=["1001"], source="test")

        snap = json.loads(self.redis.get(keyspace.snapshot_key(payment_id)))
        assert snap["collect_enabled"] is True
        assert snap["ds_order_enabled"] is False
        assert snap["dispatch_ds"] is False
        assert self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        assert not self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, str(payment_id))
        assert not self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        assert str(payment_id).encode() not in self.redis.lrange("payment_active_1001", 0, -1)
        assert self.redis.zscore(keyspace.SCHEDULE_COLLECTION, str(payment_id)) is not None

    def test_sync_set_ds_order_dispatch_disabled_keeps_collection_and_df(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920005
        service.sync_collection_job_state(
            {
                "id": payment_id,
                "phone": "0304000005",
                "status": "grabstatement",
                "partner_id": 7,
                "qr_channel": 1001,
            },
            source="pakistanpay_v2",
            schedule_score=1_744_000_321,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        snapshot = service.set_ds_order_dispatch(
            payment_id,
            enabled=False,
            channels=["1001"],
            source="app_selling_inactive",
        )

        assert snapshot["collect_enabled"] is True
        assert snapshot["ds_order_enabled"] is False
        assert snapshot["df_order_enabled"] is True
        assert self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        assert not self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, str(payment_id))
        assert self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, str(payment_id))
        assert self.redis.zscore(keyspace.JOB_SET, str(payment_id)) is not None

    def test_sync_set_manual_off_sets_key_and_disables_dispatch(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920003
        self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0304000003",
                        "online": True, "dispatch_ds": True, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )
        self.redis.sadd(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        self.redis.rpush("payment_active_1001", str(payment_id))

        service.set_manual_off(payment_id, reason="admin_manual")

        assert self.redis.get(keyspace.manual_off_collection_key(payment_id)) is not None
        assert not self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        assert str(payment_id).encode() not in self.redis.lrange("payment_active_1001", 0, -1)

    def test_sync_manual_off_is_recorded_in_snapshot(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920013
        service.mark_active_successful(
            payment_id,
            phone="0304000013",
            selected_accno="88521643",
            selected_iban="PK12TMFB0000000088521643",
            source="monitor",
            dispatch_ds=True,
            channels=["1001"],
        )

        service.set_manual_off(payment_id, reason="admin_manual")
        snapshot = service.read_snapshot(payment_id)

        assert snapshot["manual_ds_paused"] is True
        assert snapshot["manual_ds_pause_reason"] == "admin_manual"
        assert service.is_manual_off(payment_id) is True

        service.clear_manual_off(payment_id)
        snapshot = service.read_snapshot(payment_id)

        assert snapshot["manual_ds_paused"] is False
        assert snapshot["manual_ds_pause_reason"] is None
        assert service.is_manual_off(payment_id) is False
        assert self.redis.get(keyspace.manual_off_collection_key(payment_id)) is None

    def test_sync_order_health_pause_is_recorded_in_snapshot(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920014
        service.mark_active_successful(
            payment_id,
            phone="0304000014",
            selected_accno="88521644",
            selected_iban="PK12TMFB0000000088521644",
            source="monitor",
            dispatch_ds=True,
            channels=["1001"],
        )

        snapshot = service.set_order_health_pause(
            payment_id,
            reason="api_error",
            ttl=180,
            source="monitor_health_error",
            phone="0304000014",
            channels=["1001"],
        )

        assert snapshot["online"] is True
        assert snapshot["collect_enabled"] is True
        assert snapshot["ds_order_enabled"] is False
        assert snapshot["df_order_enabled"] is False
        assert snapshot["order_health_paused"] is True
        assert snapshot["order_health_pause_reason"] == "api_error"
        assert snapshot["order_health_paused_until"] == self.now + 180
        assert service.is_order_health_paused(payment_id) is True

        service.clear_order_health_pause(payment_id, source="monitor_success")
        snapshot = service.read_snapshot(payment_id)

        assert snapshot["order_health_paused"] is False
        assert snapshot["order_health_pause_reason"] is None
        assert snapshot["order_health_paused_until"] == 0
        assert service.is_order_health_paused(payment_id) is False
        assert self.redis.get(keyspace.health_pause_order_key(payment_id)) is None

    def test_sync_schedule_collection_reschedule_updates_score(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        payment_id = 920004
        service.schedule_collection(payment_id, next_at=1000)
        service.schedule_collection(payment_id, next_at=2000)
        assert int(self.redis.zscore(keyspace.SCHEDULE_COLLECTION, str(payment_id))) == 2000

    def test_monitor_should_enable_collection_dispatch_respects_manual_off(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        payment_id = 930001
        runtime_service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        runtime_service.set_manual_off(payment_id, reason="admin_manual")

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.redis = self.redis
        monitor.logger = MagicMock()
        monitor.runtime_service = runtime_service

        # Even with db_status=1 / certified=1 in payment_data, MANUAL_OFF wins
        result = monitor.should_enable_collection_dispatch(
            payment_id,
            payment_data={"status": 1, "certified": 1},
        )
        assert result is False

    def test_monitor_ignores_worker_status_string_when_deciding_collection(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.redis = self.redis
        monitor.logger = MagicMock()
        monitor.check_payment_status_in_db = MagicMock(return_value=True)

        result = monitor.should_enable_collection(
            930002,
            payment_data={"id": 930002, "status": "grabstatement"},
        )

        assert result is True
        monitor.check_payment_status_in_db.assert_called_once_with(930002)

    def test_monitor_api_error_updates_health_cache_without_force_offline(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.redis = self.redis
        monitor.logger = MagicMock()
        monitor.balance_cache_ttl = 300
        monitor.REDIS_KEYS = {
            "easypaisa_balance_sorted_set": "easypaisa_balance",
            "easypaisa_status_prefix": "easypaisa_status:",
        }
        monitor.runtime_service = MagicMock()

        result = asyncio.run(
            monitor.update_redis_cache(
                {
                    "account_id": 930003,
                    "phone": "0304000003",
                    "is_online": False,
                    "status": "api_error",
                    "check_time": "2026-04-25T12:00:00",
                    "error_message": "HTTP 503",
                    "api_response_time": 0,
                }
            )
        )

        assert result is False
        monitor.runtime_service.set_collection_dispatch.assert_not_called()
        monitor.runtime_service.force_offline.assert_not_called()
        assert self.redis.get("easypaisa_status:930003") is not None

    def test_monitor_remove_account_completely_does_not_reference_deleted_balance_counter(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.redis = self.redis
        monitor.logger = MagicMock()
        monitor.name = "easypaisa"
        monitor.hash_key = keyspace.JOB_HASH
        monitor.set_key = keyspace.JOB_SET
        monitor.REDIS_KEYS = {"easypaisa_balance_sorted_set": "easypaisa_balance"}
        monitor.runtime_service = MagicMock()
        monitor.get_phone_by_payment_id_cached = MagicMock(return_value={"phone": "0304000004"})
        monitor.update_payment_status_to_offline = MagicMock(return_value=True)
        self.redis.hset(keyspace.JOB_HASH, 930004, '{"status":"grabstatement"}')
        self.redis.zadd(keyspace.JOB_SET, {930004: 1_744_000_000})

        result = monitor.remove_account_completely(930004, "501账号无效")

        assert result is True
        monitor.runtime_service.force_offline.assert_called_once()

    def test_pakistanpay_policy_status_zero_is_business_pause_not_hard_offline(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.redis = self.redis
        bank.logger = MagicMock()
        bank._read_payment_runtime_flags = MagicMock(
            return_value={"id": 930005, "status": 0, "certified": 1, "manual_status": 0}
        )

        assert bank.payment_runtime_policy(930005) == "business_paused"

    def test_pakistanpay_policy_certified_zero_is_order_pause(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.redis = self.redis
        bank.logger = MagicMock()
        bank._read_payment_runtime_flags = MagicMock(
            return_value={"id": 930006, "status": 1, "certified": 0, "manual_status": 0}
        )

        assert bank.payment_runtime_policy(930006) == "order_paused"

    def test_pakistanpay_policy_manual_status_keeps_df_available(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.redis = self.redis
        bank.logger = MagicMock()
        bank._read_payment_runtime_flags = MagicMock(
            return_value={"id": 930007, "status": 1, "certified": 1, "manual_status": 1}
        )

        assert bank.payment_runtime_policy(930007) == "ds_dispatch_off"

    def test_pakistanpay_policy_health_pause_blocks_all_dispatch(self):
        from jobs.pakistanpay_v2 import BankLogin
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        bank = BankLogin.__new__(BankLogin)
        bank.redis = self.redis
        bank.logger = MagicMock()
        bank.runtime_service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        bank._read_payment_runtime_flags = MagicMock(
            return_value={"id": 930008, "status": 1, "certified": 1, "manual_status": 0}
        )
        bank.runtime_service.set_order_health_pause(
            930008,
            reason="api_error",
            ttl=180,
            source="test",
        )

        assert bank.payment_runtime_policy(930008) == "order_paused"

    def test_pakistanpay_policy_manual_pause_reads_snapshot_not_legacy_key_only(self):
        from jobs.pakistanpay_v2 import BankLogin
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        bank = BankLogin.__new__(BankLogin)
        bank.redis = self.redis
        bank.logger = MagicMock()
        bank.runtime_service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        bank._read_payment_runtime_flags = MagicMock(
            return_value={"id": 930018, "status": 1, "certified": 1, "manual_status": 0}
        )
        bank.runtime_service.write_snapshot(
            930018,
            {
                "online": True,
                "collect_enabled": True,
                "manual_ds_paused": True,
                "manual_ds_pause_reason": "admin_manual",
            },
            source="test",
        )

        assert bank.payment_runtime_policy(930018) == "ds_dispatch_off"

    def test_pakistanpay_grabstatement_non_501_failure_returns_false_for_retry(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.upi_time = 300
        bank.time_grab2 = 600
        bank.logger = MagicMock()
        bank.on_off = MagicMock()
        bank.getBills = AsyncMock(return_value={"is_success": False, "error_code": 500, "error_message": "HTTP 500"})

        result = asyncio.run(
            bank.grabstatement(
                {"id": 930006, "phone": "0304000006", "upi_time": 1_744_000_000},
                if_first_time=False,
            )
        )

        assert result is False
        bank.on_off.assert_not_called()

    def test_pakistanpay_grabstatement_501_returns_logout_without_calling_login_off(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.upi_time = 300
        bank.logger = MagicMock()
        bank.login_off = AsyncMock()
        bank.getBills = AsyncMock(return_value={"is_success": False, "error_code": 501, "error_message": "invalid"})

        result = asyncio.run(
            bank.grabstatement(
                {"id": 930007, "phone": "0304000007", "upi_time": 1_744_000_000},
                if_first_time=False,
            )
        )

        assert result == "logout"
        bank.login_off.assert_not_called()

    def test_pakistanpay_grabstatement_upi_failure_does_not_kick_worker_when_bills_succeed(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.upi_time = 300
        bank.time_grab2 = 600
        bank.logger = MagicMock()
        bank.on_off = MagicMock()
        bank.grabUpi = AsyncMock(return_value={"is_success": False})
        bank.getBills = AsyncMock(return_value={"is_success": True, "transaction_history_list": []})

        result = asyncio.run(
            bank.grabstatement(
                {"id": 930008, "phone": "0304000008"},
                if_first_time=False,
            )
        )

        assert result is True
        bank.on_off.assert_not_called()

    def test_pakistanpay_legacy_login_off_key_does_not_kick_collection_worker(self):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.redis = self.redis
        bank.logger = MagicMock()
        bank.name = "easypaisa"
        bank.list_key = "list_easypaisa"
        bank.time_grab = 60
        bank.time_grab2 = 300
        bank.try_count_limit = 3
        bank.on_off = MagicMock()
        payment_id = 930009
        self.redis.set(f"login_off_easypaisa_{payment_id}", "1")

        result = asyncio.run(
            bank.get_grabstatement(
                {
                    "id": payment_id,
                    "phone": "0304000009",
                    "count": 0,
                    "time": int(__import__("time").time()),
                    "if_first_time": False,
                }
            )
        )

        assert result is True
        assert self.redis.get(f"login_off_easypaisa_{payment_id}") is None
        bank.on_off.assert_not_called()

    def test_pakistanpay_login_off_removes_from_payment_active_1001(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        payment_id = 930002
        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)
        self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0305000002",
                        "online": True, "dispatch_ds": True, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )
        self.redis.sadd(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        self.redis.rpush("payment_active_1001", str(payment_id))

        service.set_collection_dispatch(payment_id, enabled=False, source="login_off",
                                        channels=["1001"])

        assert str(payment_id).encode() not in self.redis.lrange("payment_active_1001", 0, -1)


class EasyPaisaMonitorRuntimeIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor

        self.monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        self.monitor.redis = FakeSyncRedis()
        self.monitor.logger = MagicMock()
        self.monitor.name = "ep_monitor"
        self.monitor.balance_cache_ttl = 300
        self.monitor.REDIS_KEYS = {
            "easypaisa_online_df": "payment_online_df",
            "easypaisa_active_df": "payment_active_df",
            "easypaisa_balance_sorted_set": "easypaisa_balance_sorted",
            "easypaisa_status_prefix": "easypaisa_status:",
        }
        self.monitor.hash_key = "hash_easypaisa"
        self.monitor.set_key = "set_easypaisa"
        self.monitor.check_interval = 300
        self.monitor.runtime_service = MagicMock()
        self.monitor.remove_account_completely = MagicMock(return_value=True)
        self.monitor.check_payment_status_in_db = MagicMock(return_value=True)
        self.monitor.check_payment_ds_order_in_db = MagicMock(return_value=True)
        self.monitor.check_payment_df_order_in_db = MagicMock(return_value=True)

    async def test_update_redis_cache_online_syncs_runtime_service(self):
        status_info = {
            "account_id": 533280,
            "payment_id": 533280,
            "phone": "923045536108",
            "is_online": True,
            "status": "online",
            "balance": "1450.25",
            "check_time": "2026-04-19T12:00:00",
            "error_message": None,
            "api_response_time": 0.21,
        }

        deleted = await self.monitor.update_redis_cache(status_info)

        self.assertFalse(deleted)
        self.monitor.runtime_service.mark_active_successful.assert_called_once_with(
            533280,
            phone="923045536108",
            selected_accno=None,
            selected_iban=None,
            source="easypaisa_monitor",
            online_ttl=660,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
            channels=None,
        )

    async def test_update_redis_cache_offline_syncs_runtime_service(self):
        status_info = {
            "account_id": 533280,
            "payment_id": 533280,
            "phone": "923045536108",
            "is_online": False,
            "status": "api_error",
            "balance": "0",
            "check_time": "2026-04-19T12:00:00",
            "error_message": "api down",
            "api_response_time": 0.31,
        }

        deleted = await self.monitor.update_redis_cache(status_info)

        self.assertFalse(deleted)
        self.monitor.runtime_service.set_collection_dispatch.assert_not_called()
        self.monitor.runtime_service.force_offline.assert_not_called()

    async def test_update_redis_cache_online_respects_df_order_eligibility(self):
        status_info = {
            "account_id": 533280,
            "payment_id": 533280,
            "phone": "923045536108",
            "is_online": True,
            "status": "online",
            "balance": "1450.25",
            "check_time": "2026-04-19T12:00:00",
            "error_message": None,
            "api_response_time": 0.21,
        }
        self.monitor.check_payment_df_order_in_db.return_value = False
        self.monitor.redis.setex(keyspace.health_pause_order_key(533280), 180, "api_error")

        deleted = await self.monitor.update_redis_cache(status_info)

        self.assertFalse(deleted)
        self.assertIsNone(self.monitor.redis.get(keyspace.health_pause_order_key(533280)))
        _args, kwargs = self.monitor.runtime_service.mark_active_successful.call_args
        self.assertTrue(kwargs["collect_enabled"])
        self.assertTrue(kwargs["ds_order_enabled"])
        self.assertFalse(kwargs["df_order_enabled"])

    async def test_process_monitor_api_error_keeps_worker_online_for_retry(self):
        payment_id = 930010
        self.monitor.redis.hset(
            self.monitor.hash_key,
            str(payment_id),
            json.dumps({
                "id": payment_id,
                "phone": "0304000010",
                "status": "grabstatement",
            }).encode("utf-8"),
        )
        self.monitor.get_lock = MagicMock(return_value="lock-value")
        self.monitor.del_lock = MagicMock(return_value=True)
        self.monitor.check_payment_status_in_db = MagicMock(return_value=True)
        self.monitor.check_auto_payout_locks = MagicMock(return_value={"can_monitor": True})
        self.monitor.check_account_health = AsyncMock(return_value={
            "account_id": payment_id,
            "phone": "0304000010",
            "is_online": False,
            "status": "api_error",
            "check_time": "2026-04-25T12:00:00",
            "error_message": "HTTP 503",
            "api_response_time": 0,
        })
        self.monitor.update_redis_cache = AsyncMock(return_value=False)
        self.monitor.handle_problematic_accounts = AsyncMock()
        self.monitor.on_off = MagicMock()
        self.monitor.update_key = MagicMock()

        result = await self.monitor._process_easypaisa_monitor(str(payment_id).encode("utf-8"))

        self.assertTrue(result)
        self.monitor.on_off.assert_not_called()
        self.monitor.runtime_service.set_order_health_pause.assert_called_once_with(
            payment_id,
            reason="api_error",
            ttl=180,
            source="easypaisa_monitor_health_error",
            phone="0304000010",
            channels=None,
        )
        self.monitor.update_key.assert_called_once()
        _args, kwargs = self.monitor.update_key.call_args
        self.assertEqual(kwargs["next_check_interval"], 60)

    def test_on_off_routes_through_runtime_service(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }

        self.monitor.on_off(login_data, 1)
        self.monitor.on_off(login_data, 0)

        self.monitor.runtime_service.mark_active_successful.assert_called_once_with(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="easypaisa_monitor",
            online_ttl=660,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
            channels=None,
        )
        self.monitor.runtime_service.set_kickoff.assert_called_once_with(
            533280,
            phone="923045536108",
            ttl=1200,
            source="easypaisa_monitor",
            reason="monitor_offline",
        )

    def test_sync_online_payment_runtime_uses_runtime_service(self):
        payment_data = {
            "id": 533280,
            "phone": "923045536108",
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
            "status": 1,
            "certified": 1,
            "channel": "1001",
        }

        self.monitor.sync_online_payment_runtime(payment_data)

        self.monitor.runtime_service.mark_active_successful.assert_called_once_with(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="easypaisa_monitor",
            online_ttl=660,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
            channels="1001",
        )

    def test_refresh_job_account_fields_backfills_missing_account_iban(self):
        self.monitor.redis.hset(
            "hash_easypaisa",
            533280,
            json.dumps(
                {
                    "id": 533280,
                    "real_payment_id": 533280,
                    "phone": "923045536108",
                    "status": "grabstatement",
                    "partner_id": 7,
                    "account_accno": "88521643",
                    "account_iban": "",
                    "qr_channel": 1001,
                    "channel": 1001,
                },
                ensure_ascii=True,
            ),
        )

        self.monitor.refresh_job_account_fields(
            {
                "id": 533280,
                "phone": "923045536108",
                "partner_id": 7,
                "account_accno": "88521643",
                "account_iban": "PK12HABB0000000088521643",
                "channel": "1001",
            }
        )

        updated = json.loads(self.monitor.redis.hget("hash_easypaisa", 533280))
        self.assertEqual(updated["account_accno"], "88521643")
        self.assertEqual(updated["account_iban"], "PK12HABB0000000088521643")
        self.assertEqual(updated["qr_channel"], 1001)
        self.assertEqual(updated["channel"], 1001)

    def test_cleanup_missing_db_payment_syncs_runtime_and_queue_cleanup(self):
        self.monitor.redis.hset("hash_easypaisa", 533280, "{}")
        self.monitor.redis.zadd("set_easypaisa", {533280: 1})
        self.monitor.redis.set("login_on_ep_monitor_533280", "1")

        self.monitor.cleanup_missing_db_payment(533280, phone="923045536108")

        self.monitor.runtime_service.force_offline.assert_called_once_with(
            533280,
            phone="923045536108",
            source="easypaisa_monitor",
            reason="payment_missing_in_db",
        )
        self.assertIsNone(self.monitor.redis.hget("hash_easypaisa", 533280))
        self.assertIsNone(self.monitor.redis.zscore("set_easypaisa", 533280))


class EasyPaisaJobsRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        jobs_root = "/Users/tear/pk_project/api/jobs"
        if jobs_root not in sys.path:
            sys.path.insert(0, jobs_root)
        from jobs.pakistanpay_v2 import BankLogin

        self.worker = BankLogin.__new__(BankLogin)
        self.worker.redis = FakeSyncRedis()
        self.worker.logger = MagicMock()
        self.worker.list_key = "list_easypaisa"
        self.worker.runtime_service = MagicMock()
        self.worker.payment_runtime_policy = MagicMock(return_value="dispatch_on")

    def test_pakistanpay_read_cache_does_not_read_legacy_bridge_projection(self):
        class GuardedRedis(FakeSyncRedis):
            FORBIDDEN_PREFIXES = (
                "login_on_easypaisa_",
                "payment_active_",
                "kick_off_",
            )
            FORBIDDEN_KEYS = {
                "payment_online_ds",
                "payment_online_df",
            }

            def _guard(self, key):
                text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                if text in self.FORBIDDEN_KEYS or text.startswith(self.FORBIDDEN_PREFIXES):
                    raise AssertionError(f"禁止 Pakistanpay worker 读取 legacy bridge 投影: {text}")

            def get(self, key):
                self._guard(key)
                return super().get(key)

            def hget(self, key, field):
                self._guard(key)
                return super().hget(key, field)

            def zscore(self, key, member):
                self._guard(key)
                return super().zscore(key, member)

            def ttl(self, key):
                self._guard(key)
                return super().ttl(key)

            def sismember(self, key, value):
                self._guard(key)
                return super().sismember(key, value)

            def lrange(self, key, start, stop):
                self._guard(key)
                return super().lrange(key, start, stop)

        self.worker.redis = GuardedRedis()
        self.worker.logger = MagicMock()
        self.worker.name = "easypaisa"
        self.worker.hash_key = keyspace.JOB_HASH
        self.worker.set_key = keyspace.JOB_SET

        self.worker.read_cache(
            "unit-test",
            {
                "id": 533280,
                "qr_channel": "1001",
            },
        )

        self.worker.logger.error.assert_not_called()

    def test_pakistanpay_on_off_routes_through_runtime_service(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }

        self.worker.on_off(login_data, 1)
        self.worker.on_off(login_data, 0)

        self.worker.runtime_service.mark_active_successful.assert_called_once_with(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="pakistanpay_v2",
            online_ttl=660,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
            channels=1001,
        )
        self.worker.runtime_service.set_kickoff.assert_called_once_with(
            533280,
            phone="923045536108",
            ttl=1200,
            source="pakistanpay_v2",
            reason="statement_worker_offline",
        )

    def test_pakistanpay_update_key_routes_job_projection_through_runtime_service(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "status": "grabstatement",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }

        self.worker.update_key(login_data)

        self.worker.runtime_service.sync_collection_job_state.assert_called_once()
        args, kwargs = self.worker.runtime_service.sync_collection_job_state.call_args
        self.assertEqual(args[0]["id"], 533280)
        self.assertEqual(kwargs["source"], "pakistanpay_v2")
        self.assertTrue(kwargs["collect_enabled"])
        self.assertTrue(kwargs["ds_order_enabled"])
        self.assertTrue(kwargs["df_order_enabled"])

    def test_pakistanpay_update_key_order_pause_keeps_collection_and_blocks_all_dispatch(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "status": "grabstatement",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }
        self.worker.payment_runtime_policy = MagicMock(return_value="order_paused")

        self.worker.update_key(login_data)

        self.worker.runtime_service.sync_collection_job_state.assert_called_once()
        _args, kwargs = self.worker.runtime_service.sync_collection_job_state.call_args
        self.assertTrue(kwargs["collect_enabled"])
        self.assertFalse(kwargs["ds_order_enabled"])
        self.assertFalse(kwargs["df_order_enabled"])

    def test_pakistanpay_update_key_manual_ds_pause_keeps_df_dispatch(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "status": "grabstatement",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }
        self.worker.payment_runtime_policy = MagicMock(return_value="ds_dispatch_off")

        self.worker.update_key(login_data)

        self.worker.runtime_service.sync_collection_job_state.assert_called_once()
        _args, kwargs = self.worker.runtime_service.sync_collection_job_state.call_args
        self.assertTrue(kwargs["collect_enabled"])
        self.assertFalse(kwargs["ds_order_enabled"])
        self.assertTrue(kwargs["df_order_enabled"])

    def test_pakistanpay_on_off_forces_offline_when_policy_marks_offline(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }
        self.worker.payment_runtime_policy = MagicMock(return_value="offline")

        result = self.worker.on_off(login_data, 1)

        self.assertFalse(result)
        self.worker.runtime_service.force_offline.assert_called_once_with(
            533280,
            phone="923045536108",
            source="pakistanpay_v2",
            reason="payment_disabled",
            channels=1001,
        )
        self.worker.runtime_service.mark_active_successful.assert_not_called()

    def test_pakistanpay_on_off_order_pause_keeps_collection_job_queue(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }
        self.worker.redis.hset(keyspace.JOB_HASH, 533280, "{}")
        self.worker.redis.zadd(keyspace.JOB_SET, {533280: 1_744_000_200})
        self.worker.payment_runtime_policy = MagicMock(return_value="order_paused")

        result = self.worker.on_off(login_data, 1)

        self.assertTrue(result)
        self.worker.runtime_service.mark_active_successful.assert_called_once_with(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="pakistanpay_v2",
            online_ttl=660,
            collect_enabled=True,
            ds_order_enabled=False,
            df_order_enabled=False,
            channels=1001,
        )
        self.assertIsNotNone(self.worker.redis.hget(keyspace.JOB_HASH, 533280))
        self.assertIsNotNone(self.worker.redis.zscore(keyspace.JOB_SET, 533280))

    def test_pakistanpay_on_off_manual_ds_pause_keeps_df_dispatch(self):
        login_data = {
            "id": 533280,
            "phone": "923045536108",
            "qr_channel": 1001,
            "account_accno": "88521643",
            "account_iban": "PK12HABB0000000088521643",
        }
        self.worker.payment_runtime_policy = MagicMock(return_value="ds_dispatch_off")

        result = self.worker.on_off(login_data, 1)

        self.assertTrue(result)
        _args, kwargs = self.worker.runtime_service.mark_active_successful.call_args
        self.assertTrue(kwargs["collect_enabled"])
        self.assertFalse(kwargs["ds_order_enabled"])
        self.assertTrue(kwargs["df_order_enabled"])

    def test_pakistanpay_main_deletes_stale_alias_prelogin_without_locking(self):
        alias_key = "pre_login_easypaisa_03145168419"
        self.worker.name = "easypaisa"
        self.worker.hash_key = "hash_easypaisa"
        self.worker.set_key = "set_easypaisa"
        self.worker.redis.set(
            alias_key,
            json.dumps(
                {
                    "kind": "payment_id_alias",
                    "target_payment_id": "533294",
                    "bankname": "easypaisa",
                    "phone": "03145168419",
                },
                ensure_ascii=True,
            ),
        )
        self.worker.redis.keys = MagicMock(return_value=[alias_key.encode("utf-8")])

        self.worker.redis.zrangebyscore = MagicMock(return_value=[])
        self.worker.get_lock = MagicMock()
        self.worker.del_lock = MagicMock()
        self.worker.read_zset = MagicMock()
        self.worker.clean_if_callback_key = MagicMock()
        self.worker.runtime_service.read_snapshot.return_value = {
            "payment_id": 533294,
            "session_phase": "offline",
            "online": False,
            "dispatch_df": False,
            "dispatch_ds": False,
        }

        self.worker.main()

        self.assertIsNone(self.worker.redis.get(alias_key))
        self.worker.get_lock.assert_not_called()

    def test_inactive_cleanup_reads_runtime_online_index_for_easypaisa(self):
        from jobs.clear_redis_inactive_payment import get_all_active_payment_ids_from_redis

        self.worker.redis.sadd("easypaisa_runtime:index:online", 533280)

        active = get_all_active_payment_ids_from_redis(self.worker.redis)

        self.assertEqual(active["533280"], "easypaisa")


class EasyPaisaAutoPayoutSelectionTests(unittest.TestCase):
    def test_auto_payout_df_selection_requires_user_certified_but_not_manual_lock(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        class FakeCursor:
            def __init__(self):
                self.executed_sql = []
                self.last_sql = ""

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, _params=None):
                self.last_sql = sql
                self.executed_sql.append(sql)

            def fetchone(self):
                if (
                    "bank_type = 97" in self.last_sql
                    and "certified = 1" in self.last_sql
                    and "COALESCE(manual_status" not in self.last_sql
                ):
                    return {
                        "phone": "0304000011",
                        "account": "0304000011",
                        "name": "EP DF",
                        "bank_type": 97,
                        "partner_id": 7,
                        "status": 1,
                        "certified": 1,
                        "account_accno": "88521643",
                    }
                return None

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.logger = MagicMock()
        connection = FakeConnection()

        result = service.get_phone_by_payment_id("930011", connection=connection)

        self.assertIsNotNone(result)
        self.assertEqual(result["certified"], 1)
        primary_sql = connection.cursor_obj.executed_sql[0]
        self.assertIn("certified = 1", primary_sql)
        self.assertNotIn("manual_status", primary_sql)


class EasyPaisaBalanceUpdateSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_balance_update_ep_selection_does_not_require_ds_certified_flag(self):
        from unittest.mock import patch
        from jobs.update_payment_balance import BalanceUpdateMonitor

        class FakeCursor:
            def __init__(self):
                self.executed_sql = []
                self.last_sql = ""

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql):
                self.last_sql = sql
                self.executed_sql.append(sql)

            def fetchall(self):
                if "bank_type = 97" in self.last_sql and "certified = 1" not in self.last_sql:
                    return [
                        {
                            "id": 930012,
                            "phone": "0304000012",
                            "account": "0304000012",
                            "name": "EP Balance",
                            "bank_type": 97,
                            "partner_id": 7,
                            "status": 1,
                            "certified": 0,
                            "account_accno": "88521643",
                        }
                    ]
                return []

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.closed = False

            def cursor(self):
                return self.cursor_obj

            def close(self):
                self.closed = True

        monitor = BalanceUpdateMonitor.__new__(BalanceUpdateMonitor)
        monitor.logger = MagicMock()
        connection = FakeConnection()

        with patch("pymysql.connect", return_value=connection):
            result = await monitor.get_online_ep_payments_from_db()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["certified"], 0)
        self.assertFalse(
            any("certified = 1" in sql for sql in connection.cursor_obj.executed_sql)
        )


class EasyPaisaJobsTransientBillErrorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        jobs_root = "/Users/tear/pk_project/api/jobs"
        if jobs_root not in sys.path:
            sys.path.insert(0, jobs_root)
        from jobs.pakistanpay_v2 import BankLogin

        self.worker = BankLogin.__new__(BankLogin)
        self.worker.logger = MagicMock()
        self.worker.on_off = MagicMock()
        self.worker.getBills = AsyncMock()
        self.worker.if_callback = MagicMock(return_value=False)
        self.worker.get_payment_info = MagicMock(return_value="88521643")
        self.worker.callback_transaction = AsyncMock()

    async def test_verify_and_handle_abnormal_payout_keeps_dispatch_for_transient_423(self):
        login_data = {
            "id": 533280,
            "phone": "03489696378",
        }
        order_data = {
            "account_id": "03092969112",
            "amount": 500.0,
            "time_created": "2026-04-20 03:53:17",
        }
        self.worker.getBills.return_value = {
            "is_success": False,
            "error_code": 423,
            "error_message": "云机正忙查单，请稍后再试: 03489696378",
            "transaction_history_list": [
                {
                    "orderNo": "utr423",
                    "amount": 500.0,
                    "historyDetailRspDTO": {},
                }
            ],
        }

        await self.worker.verify_and_handle_abnormal_payout(login_data, order_data)

        self.worker.on_off.assert_not_called()

    async def test_verify_and_handle_abnormal_payout_keeps_runtime_for_non_501_failure(self):
        login_data = {
            "id": 533280,
            "phone": "03489696378",
        }
        order_data = {
            "account_id": "03092969112",
            "amount": 500.0,
            "time_created": "2026-04-20 03:53:17",
        }
        self.worker.getBills.return_value = {
            "is_success": False,
            "error_code": 500,
            "error_message": "HTTP 500",
            "transaction_history_list": [
                {
                    "orderNo": "utr500",
                    "amount": 500.0,
                    "historyDetailRspDTO": {},
                }
            ],
        }

        await self.worker.verify_and_handle_abnormal_payout(login_data, order_data)

        self.worker.on_off.assert_not_called()


class EasyPaisaAutoPayoutRuntimeTruthTests(unittest.TestCase):
    def test_return_account_to_active_list_uses_snapshot_df_state_not_legacy_set(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.redis = FakeSyncRedis()
        service.logger = MagicMock()
        service.REDIS_KEYS = {
            "easypaisa_online_df": "payment_online_df",
            "easypaisa_active_df": "payment_active_df",
        }
        payment_id = "930019"
        service.redis.sadd("payment_online_df", payment_id)
        service.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps(
                {
                    "payment_id": payment_id,
                    "online": True,
                    "collect_enabled": True,
                    "df_order_enabled": False,
                    "dispatch_df": False,
                }
            ),
        )

        service.return_account_to_active_list(payment_id)

        assert service.redis.lists.get("payment_active_df", []) == []


class EasyPaisaJobsCallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        jobs_root = "/Users/tear/pk_project/api/jobs"
        if jobs_root not in sys.path:
            sys.path.insert(0, jobs_root)
        from jobs.pakistanpay_v2 import BankLogin

        self.worker = BankLogin.__new__(BankLogin)
        self.worker.redis = FakeSyncRedis()
        self.worker.logger = MagicMock()
        self.worker.list_key = "list_easypaisa"
        self.worker.name = "easypaisa"
        self.worker.if_callback_key = "if_callback_easypaisa"
        self.worker.domain = "http://api.example.com/api/"
        self.worker.internal_callback_host = "http://127.0.0.1:9000/"

    async def test_send_prefers_internal_order_success_url(self):
        self.worker.retry_make_request = AsyncMock(
            return_value=MagicMock(status_code=200, text='{"code": 100}')
        )

        result = await self.worker.send({"payment_id": 533280}, {"id": 533280})

        self.assertTrue(result["is_success"])
        self.assertEqual(
            self.worker.retry_make_request.await_args.kwargs["url"],
            "http://127.0.0.1:9000/order/Success",
        )

    async def test_send_falls_back_to_normalized_domain_when_internal_missing(self):
        self.worker.internal_callback_host = None
        self.worker.retry_make_request = AsyncMock(
            return_value=MagicMock(status_code=200, text='{"code": 100}')
        )

        result = await self.worker.send({"payment_id": 533280}, {"id": 533280})

        self.assertTrue(result["is_success"])
        self.assertEqual(
            self.worker.retry_make_request.await_args.kwargs["url"],
            "http://api.example.com/order/Success",
        )

    async def test_callback_fail_does_not_mark_transaction_as_processed(self):
        login_data = {"id": 533280}
        self.worker.transaction_callback = AsyncMock(return_value=False)
        self.worker.mark_transaction_callback = MagicMock()

        await self.worker.callback_transaction(
            utr="PWM20260419135152388940",
            mapped_trans={"txnType": "CREDIT", "txnAmount": 100.0},
            login_data=login_data,
        )

        self.worker.mark_transaction_callback.assert_not_called()

    async def test_callback_success_marks_transaction_as_processed(self):
        login_data = {"id": 533280}
        self.worker.transaction_callback = AsyncMock(return_value=True)
        self.worker.mark_transaction_callback = MagicMock()

        await self.worker.callback_transaction(
            utr="PWM20260419135152388940",
            mapped_trans={"txnType": "CREDIT", "txnAmount": 100.0},
            login_data=login_data,
        )

        self.worker.mark_transaction_callback.assert_called_once_with(
            "PWM20260419135152388940",
            login_data,
        )


class Stage07JobHashRebuildTests(unittest.TestCase):
    """Stage 0.7: JOB_HASH self-heal from session when mark_active_successful is called."""

    def setUp(self):
        self.redis = FakeSyncRedis()
        self.now = 1_744_000_100

    def _make_service(self):
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService
        return SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: self.now)

    @property
    def service(self):
        return self._make_service()

    def test_mark_active_successful_rebuilds_job_hash_from_session_when_missing(self):
        """Stage 0.7: if dispatch_ds=True + JOB_HASH missing + session exists → rebuild."""
        payment_id = 980001
        phone = "0308000001"
        # Seed session (simulating a worker that did pre_login once)
        session_payload = {
            "schema_version": 1,
            "id": payment_id,
            "phone": phone,
            "original_phone": phone,
            "partner_id": 33045,
            "status": "activeSuccessful",   # session has activeSuccessful
            "access_token": "abc",
            "device_id": "dev123",
            "authorization": "Bearer xyz",
            "qr_channel": 1001,
            "pinCode": "12345",
            "password": "secret",
            "account_accno": "99999999",
            "account_iban": "PK00TMFB0000000099999999",
            "selected_upi": phone,
            "fg_times": 3,                   # should be dropped
            "login_time": 1776800000,
        }
        self.redis.set(keyspace.session_key(payment_id), json.dumps(session_payload))
        # Ensure hash_easypaisa is empty
        self.redis.hdel(keyspace.JOB_HASH, payment_id)
        self.redis.zrem(keyspace.JOB_SET, payment_id)

        self.service.mark_active_successful(
            payment_id,
            phone=phone,
            selected_accno="99999999",
            selected_iban="PK00TMFB0000000099999999",
            source="test",
            dispatch_df=True,
            dispatch_ds=True,
            channels=["1001"],
        )

        raw = self.redis.hget(keyspace.JOB_HASH, payment_id)
        assert raw is not None, "JOB_HASH should be rebuilt"
        data = json.loads(raw)
        assert data["id"] == payment_id
        assert data["status"] == "grabstatement"   # rewritten from activeSuccessful
        assert data["phone"] == phone
        assert data["device_id"] == "dev123"        # session credentials preserved
        assert data["authorization"] == "Bearer xyz"
        assert "schema_version" not in data
        assert "fg_times" not in data
        assert data.get("count") == 0
        assert data.get("if_first_time") is False
        assert self.redis.zscore(keyspace.JOB_SET, str(payment_id)) is not None

    def test_mark_active_successful_preserves_existing_job_hash_runtime_state(self):
        """If JOB_HASH already has data (with worker runtime state), don't overwrite."""
        payment_id = 980002
        phone = "0308000002"
        # Pre-existing JOB_HASH with worker runtime state
        preexisting = {
            "id": payment_id,
            "phone": phone,
            "status": "grabstatement",
            "count": 42,                          # worker's accumulated state
            "try_count": 3,
            "last_grab_failed_980002": True,
            "if_first_time": False,
        }
        self.redis.hset(keyspace.JOB_HASH, payment_id, json.dumps(preexisting))
        # Also seed session (should be ignored since JOB_HASH exists)
        self.redis.set(keyspace.session_key(payment_id), json.dumps({"schema_version": 1, "status": "activeSuccessful"}))

        self.service.mark_active_successful(
            payment_id,
            phone=phone,
            selected_accno=None,
            selected_iban=None,
            source="test",
            dispatch_df=True,
            dispatch_ds=True,
            channels=["1001"],
        )

        raw = self.redis.hget(keyspace.JOB_HASH, payment_id)
        data = json.loads(raw)
        # Runtime state preserved
        assert data["count"] == 42
        assert data["try_count"] == 3
        assert data["last_grab_failed_980002"] is True

    def test_mark_active_successful_skips_rebuild_when_session_missing(self):
        """If both JOB_HASH and session are missing, do nothing (avoid incomplete data)."""
        payment_id = 980003
        # Both missing
        self.redis.hdel(keyspace.JOB_HASH, payment_id)
        self.redis.delete(keyspace.session_key(payment_id))

        self.service.mark_active_successful(
            payment_id,
            phone="0308000003",
            selected_accno=None,
            selected_iban=None,
            source="test",
            dispatch_df=True,
            dispatch_ds=True,
            channels=["1001"],
        )

        # JOB_HASH should still be empty (don't write garbage)
        assert self.redis.hget(keyspace.JOB_HASH, payment_id) is None
        # But snapshot + INDEX_DISPATCH_DS + SCHEDULE_COLLECTION still get written (pre-existing behavior)
        assert self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        assert self.redis.zscore(keyspace.SCHEDULE_COLLECTION, str(payment_id)) is not None


class ShouldEnableCollectionDispatchTests(unittest.TestCase):
    """Unit tests for AutoPayoutMonitor.should_enable_collection_dispatch (Stage 0.6)."""

    def setUp(self):
        self.redis = FakeSyncRedis()

    def _make_monitor(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.redis = self.redis
        monitor.logger = MagicMock()
        return monitor

    def test_should_enable_collection_dispatch_respects_db_manual_status(self):
        """manual_status=1 in payment_data must block dispatch_ds regardless of status/certified."""
        monitor = self._make_monitor()
        payment_id = 970001
        # No Redis MANUAL_OFF key set; DB manual_status=1 carried in payment_data
        result = monitor.should_enable_collection_dispatch(
            payment_id,
            payment_data={"status": 1, "certified": 1, "manual_status": 1},
        )
        self.assertFalse(result, "manual_status=1 should prevent enabling dispatch_ds")

    def test_should_enable_collection_dispatch_returns_true_when_all_green(self):
        """status=1, certified=1, manual_status=0 must allow dispatch_ds."""
        monitor = self._make_monitor()
        payment_id = 970002
        result = monitor.should_enable_collection_dispatch(
            payment_id,
            payment_data={"status": 1, "certified": 1, "manual_status": 0},
        )
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
