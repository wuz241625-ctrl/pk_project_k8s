import unittest


class FakeSyncRedis:
    def __init__(self):
        self.kv = {}
        self.sets = {}
        self.lists = {}
        self.zsets = {}
        self.hashes = {}

    def set(self, key, value):
        self.kv[key] = value
        return True

    def get(self, key):
        return self.kv.get(key)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.kv:
                removed += 1
            self.kv.pop(key, None)
        return removed

    def hset(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        bucket[str(field)] = value
        return 1

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

    def scan_iter(self, pattern):
        from fnmatch import fnmatch

        for key in sorted(self.kv):
            if fnmatch(key, pattern):
                yield key

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


class EasyPaisaRuntimeRolloutCleanupTests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeSyncRedis()
        self.redis.set("login_on_easypaisa_533280", "1")
        self.redis.set("login_on_easypaisa_923045536108", "1")
        self.redis.set("pre_login_easypaisa_533280", '{"status":"otpSent"}')
        self.redis.set("login_on_jazzcash_533999", "1")
        self.redis.set("easypaisa_runtime:session:533280", '{"status":"activeSuccessful"}')
        self.redis.set("easypaisa_runtime:snapshot:533280", '{"online":true}')
        self.redis.sadd("payment_online_ds", 533280, 533997)
        self.redis.sadd("payment_online_df", 533280, 533999)
        self.redis.rpush("payment_active_df", 533280, 533998, 533280)
        self.redis.sadd("easypaisa_runtime:index:online", 533280)
        self.redis.sadd("easypaisa_runtime:index:dispatch_df", 533280)
        self.redis.sadd("easypaisa_runtime:index:dispatch_ds", 533280)
        self.redis.zadd("easypaisa_runtime:index:updated_at", {533280: 1744000000})
        self.redis.hset("hash_easypaisa", 533280, '{"status":"grabstatement"}')
        self.redis.zadd("set_easypaisa", {533280: 1744000000})

    def test_collect_cleanup_plan_only_targets_easypaisa_state(self):
        from application.easypaisa_runtime.rollout_cleanup import collect_cleanup_plan

        plan = collect_cleanup_plan(self.redis, {"533280", "533281"})

        self.assertEqual(plan["matched_keys"], [
            "easypaisa_runtime:session:533280",
            "easypaisa_runtime:snapshot:533280",
            "login_on_easypaisa_533280",
            "login_on_easypaisa_923045536108",
            "pre_login_easypaisa_533280",
        ])
        self.assertEqual(plan["legacy_online_payment_ids"], ["533280"])
        self.assertEqual(plan["legacy_collection_payment_ids"], ["533280"])
        self.assertEqual(plan["legacy_active_payment_ids"], ["533280"])
        self.assertEqual(plan["runtime_online_payment_ids"], ["533280"])
        self.assertEqual(plan["runtime_dispatch_df_payment_ids"], ["533280"])
        self.assertEqual(plan["runtime_dispatch_ds_payment_ids"], ["533280"])
        self.assertEqual(plan["job_hash_payment_ids"], ["533280"])
        self.assertEqual(plan["job_set_payment_ids"], ["533280"])
        self.assertEqual(plan["runtime_updated_payment_ids"], ["533280"])

    def test_execute_cleanup_removes_only_targeted_easypaisa_state(self):
        from application.easypaisa_runtime.rollout_cleanup import (
            collect_cleanup_plan,
            execute_cleanup,
        )

        plan = collect_cleanup_plan(self.redis, {"533280"})
        result = execute_cleanup(self.redis, plan)

        self.assertEqual(result["deleted_keys"], 5)
        self.assertEqual(result["removed_online_df"], 1)
        self.assertEqual(result["removed_online_ds"], 1)
        self.assertEqual(result["removed_active_df"], 2)
        self.assertEqual(result["removed_runtime_online"], 1)
        self.assertEqual(result["removed_runtime_dispatch_df"], 1)
        self.assertEqual(result["removed_runtime_dispatch_ds"], 1)
        self.assertEqual(result["removed_job_hash"], 1)
        self.assertEqual(result["removed_job_set"], 1)
        self.assertEqual(result["removed_runtime_updated"], 1)

        self.assertIsNone(self.redis.get("login_on_easypaisa_533280"))
        self.assertIsNone(self.redis.get("login_on_easypaisa_923045536108"))
        self.assertIsNone(self.redis.get("pre_login_easypaisa_533280"))
        self.assertIsNone(self.redis.get("easypaisa_runtime:session:533280"))
        self.assertIsNone(self.redis.get("easypaisa_runtime:snapshot:533280"))

        self.assertEqual(self.redis.smembers("payment_online_ds"), {"533997"})
        self.assertEqual(self.redis.smembers("payment_online_df"), {"533999"})
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), ["533998"])
        self.assertEqual(self.redis.smembers("easypaisa_runtime:index:online"), set())
        self.assertEqual(self.redis.smembers("easypaisa_runtime:index:dispatch_df"), set())
        self.assertEqual(self.redis.smembers("easypaisa_runtime:index:dispatch_ds"), set())
        self.assertEqual(self.redis.zscore("easypaisa_runtime:index:updated_at", "533280"), None)
        self.assertEqual(self.redis.hkeys("hash_easypaisa"), [])
        self.assertEqual(self.redis.zrange("set_easypaisa", 0, -1), [])

        self.assertEqual(self.redis.get("login_on_jazzcash_533999"), "1")

    def test_collect_cleanup_plan_also_removes_orphan_runtime_and_job_ids_missing_in_db(self):
        from application.easypaisa_runtime.rollout_cleanup import (
            collect_cleanup_plan,
            execute_cleanup,
        )

        self.redis.hset("hash_easypaisa", 599999, '{"status":"grabstatement"}')
        self.redis.zadd("set_easypaisa", {599999: 1745000000})

        plan = collect_cleanup_plan(self.redis, set())

        self.assertIn("599999", plan["job_hash_payment_ids"])
        self.assertIn("599999", plan["job_set_payment_ids"])

        result = execute_cleanup(self.redis, plan)

        self.assertGreaterEqual(result["removed_job_hash"], 2)
        self.assertGreaterEqual(result["removed_job_set"], 2)
        self.assertFalse("599999" in self.redis.hkeys("hash_easypaisa"))
        self.assertFalse("599999" in self.redis.zrange("set_easypaisa", 0, -1))


if __name__ == "__main__":
    unittest.main()
