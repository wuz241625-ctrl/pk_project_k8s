import json
import unittest


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

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.kv:
                removed += 1
            self.kv.pop(key, None)
            self.ttl_map.pop(key, None)
        return removed

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
            if text in bucket:
                removed += 1
            bucket.pop(text, None)
        return removed

    def hkeys(self, key):
        return list(self.hashes.get(key, {}).keys())

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
            text = str(value)
            if text in bucket:
                removed += 1
            bucket.discard(text)
        return removed

    def sismember(self, key, value):
        return str(value) in self.sets.get(key, set())

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def lrange(self, key, start, end):
        bucket = list(self.lists.get(key, []))
        if end == -1:
            return bucket[start:]
        return bucket[start : end + 1]

    def lrem(self, key, count, value):
        if count != 0:
            raise NotImplementedError("fake redis only supports lrem count=0")
        text = str(value)
        bucket = list(self.lists.get(key, []))
        removed = bucket.count(text)
        self.lists[key] = [item for item in bucket if item != text]
        return removed

    def rpush(self, key, *values):
        bucket = self.lists.setdefault(key, [])
        for value in values:
            bucket.append(str(value))
        return len(bucket)

    def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return len(mapping)

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    def zrem(self, key, *members):
        bucket = self.zsets.setdefault(key, {})
        removed = 0
        for member in members:
            text = str(member)
            if text in bucket:
                removed += 1
            bucket.pop(text, None)
        return removed

    def zrange(self, key, start, end):
        members = list(self.zsets.get(key, {}).keys())
        if end == -1:
            return members[start:]
        return members[start : end + 1]

    def scan_iter(self, pattern):
        from fnmatch import fnmatch

        for key in sorted(self.kv):
            if fnmatch(key, pattern):
                yield key


class EasyPaisaAccountRetentionTests(unittest.TestCase):
    def setUp(self):
        from application.easypaisa_runtime import keyspace
        from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService

        self.keyspace = keyspace
        self.redis = FakeSyncRedis()
        self.runtime_service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: 1_744_000_000)

        self.accounts = [
            {"id": 533277, "phone": "03194937489", "status": 1, "bank_type": 97},
            {"id": 533280, "phone": "03045536108", "status": 1, "bank_type": 97},
            {"id": 533281, "phone": "03489696378", "status": 1, "bank_type": 97},
        ]

        self.runtime_service.mark_active_successful(
            533277,
            phone="03194937489",
            selected_accno="ACC-277",
            selected_iban="IBAN-277",
            source="test_setup",
            online_ttl=660,
        )
        self.runtime_service.mark_active_successful(
            533280,
            phone="03045536108",
            selected_accno="ACC-280",
            selected_iban="IBAN-280",
            source="test_setup",
            online_ttl=660,
        )

        self.redis.sadd(keyspace.INDEX_ONLINE, 533281)
        self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, 533281)
        self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, 533281)
        self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, 533277)
        self.redis.sadd(keyspace.INDEX_DISPATCH_DF, 533281)
        self.redis.sadd(keyspace.INDEX_DISPATCH_DS, 533277)
        self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {533281: 1_744_000_001})
        self.redis.zadd(keyspace.INDEX_UPDATED_AT, {533281: 1_744_000_001})

        self.redis.set(keyspace.pre_login_key(533277), '{"phase":"otpSent"}')
        self.redis.set(keyspace.pre_login_key(533281), '{"phase":"otpSent"}')
        self.redis.set(keyspace.session_key(533277), '{"phase":"activeSuccessful"}')
        self.redis.set(keyspace.session_key(533281), '{"phase":"otpSent"}')
        self.redis.set(keyspace.kickoff_key(533277), "1")
        self.redis.set(keyspace.legacy_kickoff_key(533277), "1")
        self.redis.set(keyspace.health_pause_order_key(533277), "api_error")
        self.redis.set(keyspace.health_pause_order_key(533281), "api_error")
        self.redis.set(keyspace.lock_payment_key(533277), "1")
        self.redis.set(keyspace.lock_phone_key("03194937489"), "1")
        self.redis.set(keyspace.legacy_login_on_phone_key("03489696378"), "1")

        self.redis.hset(keyspace.JOB_HASH, 533277, '{"status":"grabstatement"}')
        self.redis.hset(keyspace.JOB_HASH, 599999, '{"status":"grabstatement"}')
        self.redis.zadd(keyspace.JOB_SET, {533277: 1_744_000_010, 599999: 1_744_000_011})

        self.redis.hset(keyspace.MONITOR_HASH, 533277, '{"status":"monitoring"}')
        self.redis.hset(keyspace.MONITOR_HASH, 533280, '{"status":"monitoring"}')
        self.redis.hset(keyspace.MONITOR_HASH, 599999, '{"status":"monitoring"}')
        self.redis.zadd(
            keyspace.MONITOR_SET,
            {533277: 1_744_000_020, 533280: 1_744_000_021, 599999: 1_744_000_022},
        )

        self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DF, 533999)
        self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 533999)
        self.redis.set("login_on_jazzcash_533999", "1")

    def test_build_retention_plan_keeps_only_whitelist(self):
        from application.easypaisa_runtime.account_retention import build_retention_plan

        plan = build_retention_plan(self.redis, self.accounts, {"03045536108"})

        self.assertEqual(plan["keep_payment_ids"], ["533280"])
        self.assertEqual(plan["disable_db_payment_ids"], ["533277", "533281"])
        self.assertEqual(plan["disable_payment_ids"], ["533277", "533281", "599999"])
        self.assertEqual(plan["orphan_payment_ids"], ["599999"])
        self.assertEqual(plan["disable_phones"], ["03194937489", "03489696378"])
        self.assertEqual(plan["runtime_online_payment_ids"], ["533277", "533281"])
        self.assertEqual(plan["runtime_collect_payment_ids"], ["533277", "533281"])
        self.assertEqual(plan["runtime_df_order_payment_ids"], ["533277", "533281"])
        self.assertEqual(plan["runtime_ds_order_payment_ids"], ["533277"])
        self.assertEqual(plan["runtime_dispatch_df_payment_ids"], ["533277", "533281"])
        self.assertEqual(plan["runtime_dispatch_ds_payment_ids"], ["533277"])
        self.assertEqual(plan["runtime_schedule_collection_payment_ids"], ["533277", "533281"])
        self.assertEqual(plan["legacy_online_payment_ids"], ["533277"])
        self.assertEqual(plan["legacy_active_payment_ids"], ["533277"])
        self.assertEqual(plan["job_hash_payment_ids"], ["533277", "599999"])
        self.assertEqual(plan["job_set_payment_ids"], ["533277", "599999"])
        self.assertEqual(plan["monitor_hash_payment_ids"], ["533277", "599999"])
        self.assertEqual(plan["monitor_set_payment_ids"], ["533277", "599999"])
        self.assertIn(self.keyspace.pre_login_key(533277), plan["matched_keys"])
        self.assertIn(self.keyspace.session_key(533277), plan["matched_keys"])
        self.assertIn(self.keyspace.health_pause_order_key(533277), plan["matched_keys"])
        self.assertIn(self.keyspace.health_pause_order_key(533281), plan["matched_keys"])
        self.assertIn(self.keyspace.legacy_login_on_phone_key("03194937489"), plan["matched_keys"])
        self.assertIn(self.keyspace.legacy_login_on_phone_key("03489696378"), plan["matched_keys"])
        self.assertNotIn(self.keyspace.legacy_login_on_phone_key("03045536108"), plan["matched_keys"])

    def test_execute_retention_plan_cleans_non_kept_runtime_state(self):
        from application.easypaisa_runtime.account_retention import (
            build_retention_plan,
            execute_retention_plan,
        )

        plan = build_retention_plan(self.redis, self.accounts, {"03045536108"})
        result = execute_retention_plan(self.redis, plan)

        self.assertEqual(result["forced_offline_payment_ids"], 2)
        self.assertEqual(result["removed_job_hash"], 2)
        self.assertEqual(result["removed_job_set"], 2)
        self.assertEqual(result["removed_monitor_hash"], 2)
        self.assertEqual(result["removed_monitor_set"], 2)

        self.assertEqual(self.redis.smembers(self.keyspace.INDEX_ONLINE), {"533280"})
        self.assertEqual(self.redis.smembers(self.keyspace.INDEX_COLLECT_ENABLED), {"533280"})
        self.assertEqual(self.redis.smembers(self.keyspace.INDEX_DF_ORDER_ENABLED), {"533280"})
        self.assertEqual(self.redis.smembers(self.keyspace.INDEX_DS_ORDER_ENABLED), set())
        self.assertEqual(self.redis.smembers(self.keyspace.INDEX_DISPATCH_DF), {"533280"})
        self.assertEqual(self.redis.smembers(self.keyspace.INDEX_DISPATCH_DS), set())
        self.assertEqual(self.redis.zrange(self.keyspace.SCHEDULE_COLLECTION, 0, -1), ["533280"])
        self.assertEqual(self.redis.smembers(self.keyspace.LEGACY_PAYMENT_ONLINE_DF), {"533280", "533999"})
        self.assertEqual(self.redis.lrange(self.keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, -1), ["533280", "533999"])

        self.assertEqual(self.redis.hkeys(self.keyspace.JOB_HASH), [])
        self.assertEqual(self.redis.zrange(self.keyspace.JOB_SET, 0, -1), [])
        self.assertEqual(self.redis.hkeys(self.keyspace.MONITOR_HASH), ["533280"])
        self.assertEqual(self.redis.zrange(self.keyspace.MONITOR_SET, 0, -1), ["533280"])

        self.assertIsNone(self.redis.get(self.keyspace.pre_login_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.session_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.kickoff_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.legacy_kickoff_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.health_pause_order_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.health_pause_order_key(533281)))
        self.assertIsNone(self.redis.get(self.keyspace.lock_payment_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.lock_phone_key("03194937489")))
        self.assertIsNone(self.redis.get(self.keyspace.legacy_login_on_payment_key(533277)))
        self.assertIsNone(self.redis.get(self.keyspace.legacy_login_on_phone_key("03194937489")))
        self.assertIsNone(self.redis.get(self.keyspace.legacy_login_on_payment_key(533281)))
        self.assertIsNone(self.redis.get(self.keyspace.legacy_login_on_phone_key("03489696378")))

        keep_snapshot = json.loads(self.redis.get(self.keyspace.snapshot_key(533280)))
        self.assertTrue(keep_snapshot["online"])

        offline_snapshot = json.loads(self.redis.get(self.keyspace.snapshot_key(533277)))
        self.assertFalse(offline_snapshot["online"])
        self.assertEqual(offline_snapshot["last_transition"], "retain_only_whitelist")

        self.assertIsNone(self.redis.zscore(self.keyspace.INDEX_UPDATED_AT, "533277"))
        self.assertIsNone(self.redis.zscore(self.keyspace.INDEX_UPDATED_AT, "533281"))
        self.assertEqual(self.redis.get("login_on_jazzcash_533999"), "1")


if __name__ == "__main__":
    unittest.main()
