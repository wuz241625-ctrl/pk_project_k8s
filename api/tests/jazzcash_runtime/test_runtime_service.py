import json
import unittest


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

    async def ttl(self, key):
        if key not in self.kv:
            return -2
        return self.ttl_map.get(key, -1)

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[str(field)] = value
        return 1

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    async def hdel(self, key, *fields):
        bucket = self.hashes.setdefault(key, {})
        removed = 0
        for field in fields:
            text = str(field)
            removed += 1 if text in bucket else 0
            bucket.pop(text, None)
        return removed

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
            text = str(value)
            removed += 1 if text in bucket else 0
            bucket.discard(text)
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
            removed += 1 if text in bucket else 0
            bucket.pop(text, None)
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

    async def lrange(self, key, start, end):
        bucket = self.lists.get(key, [])
        if end == -1:
            return bucket[start:]
        return bucket[start:end + 1]


class JazzCashRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.now = 1_744_000_000

    async def test_mark_active_successful_writes_runtime_and_legacy_projection(self):
        from application.jazzcash_runtime.runtime_service import JazzCashRuntimeService
        from application.jazzcash_runtime import keyspace

        service = JazzCashRuntimeService(self.redis, now_provider=lambda: self.now)
        snapshot = await service.mark_active_successful(
            7001,
            phone="03495863120",
            selected_accno="03495863120",
            selected_iban="PK12JAZZ000000003495863120",
            source="login_flow",
            dispatch_ds=True,
            df_order_enabled=True,
            channels=["1003"],
            online_ttl=660,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["dispatch_ds"])
        self.assertTrue(snapshot["dispatch_df"])
        self.assertEqual(snapshot["session_phase"], "activeSuccessful")
        self.assertEqual(snapshot["channels"], ["1003"])

        raw = await self.redis.get(keyspace.snapshot_key(7001))
        stored = json.loads(raw)
        self.assertEqual(stored["payment_id"], 7001)
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_ONLINE, 7001))
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, 7001))
        self.assertTrue(await self.redis.sismember(keyspace.INDEX_DISPATCH_DF, 7001))
        self.assertTrue(await self.redis.sismember("payment_online_ds", 7001))
        self.assertTrue(await self.redis.sismember("payment_online_df", 7001))
        self.assertEqual(self.redis.lists["payment_active_1003"], ["7001"])
        self.assertEqual(self.redis.lists["payment_active_df"], ["7001"])
        self.assertEqual(await self.redis.get("login_on_jazzcash_7001"), "1")
        self.assertEqual(await self.redis.get("login_on_jazzcash_03495863120"), "1")

    async def test_mark_active_successful_clears_stale_error_and_cooldown_fields(self):
        from application.jazzcash_runtime.runtime_service import JazzCashRuntimeService
        from application.jazzcash_runtime import keyspace

        service = JazzCashRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            7001,
            {
                "phone": "03495863120",
                "online": False,
                "session_phase": "fingerprintVerified",
                "last_error": {"code": "FP_COOLDOWN"},
                "cd_until": self.now - 1,
                "cooldown_until": self.now - 1,
                "session_expires_at": self.now - 300,
            },
            source="jazzcash_login_flow",
        )

        snapshot = await service.mark_active_successful(
            7001,
            phone="03495863120",
            selected_accno="03495863120",
            selected_iban="PK12JAZZ000000003495863120",
            source="login_flow",
            online_ttl=660,
            channels=["1003"],
        )

        self.assertIsNone(snapshot["last_error"])
        self.assertEqual(snapshot["cd_until"], 0)
        self.assertEqual(snapshot["cooldown_until"], 0)
        self.assertEqual(snapshot["session_expires_at"], self.now + 660)

        stored = json.loads(await self.redis.get(keyspace.snapshot_key(7001)))
        self.assertIsNone(stored["last_error"])
        self.assertEqual(stored["cd_until"], 0)
        self.assertEqual(stored["cooldown_until"], 0)
        self.assertEqual(stored["session_expires_at"], self.now + 660)

    async def test_force_reset_clears_runtime_indexes_sessions_jobs_and_legacy(self):
        from application.jazzcash_runtime.runtime_service import JazzCashRuntimeService
        from application.jazzcash_runtime import keyspace

        service = JazzCashRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.mark_active_successful(
            7001,
            phone="03495863120",
            selected_accno="03495863120",
            selected_iban="PK12JAZZ000000003495863120",
            source="login_flow",
            dispatch_ds=True,
            channels=["1003"],
        )
        await self.redis.set(keyspace.session_key(7001), json.dumps({"status": "activeSuccessful"}))
        await self.redis.set(keyspace.pre_login_key(7001), json.dumps({"status": "activeSuccessful"}))
        await self.redis.hset(keyspace.JOB_HASH, 7001, json.dumps({"status": "grabstatement"}))
        await self.redis.zadd(keyspace.JOB_SET, {7001: self.now})

        snapshot = await service.force_reset(7001, source="admin_reset")

        self.assertFalse(snapshot["online"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertEqual(snapshot["session_phase"], "offline")
        self.assertIsNone(await self.redis.get(keyspace.session_key(7001)))
        self.assertIsNone(await self.redis.get(keyspace.pre_login_key(7001)))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_ONLINE, 7001))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, 7001))
        self.assertIsNone(await self.redis.hget(keyspace.JOB_HASH, 7001))
        self.assertIsNone(await self.redis.zscore(keyspace.JOB_SET, 7001))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 7001))
        self.assertFalse(await self.redis.sismember("payment_online_df", 7001))
        self.assertEqual(self.redis.lists["payment_active_1003"], [])
        self.assertEqual(self.redis.lists["payment_active_df"], [])
        self.assertIsNone(await self.redis.get("login_on_jazzcash_7001"))
        self.assertIsNone(await self.redis.get("login_on_jazzcash_03495863120"))

    async def test_clear_snapshot_removes_all_runtime_indexes(self):
        from application.jazzcash_runtime.runtime_service import JazzCashRuntimeService
        from application.jazzcash_runtime import keyspace

        service = JazzCashRuntimeService(self.redis, now_provider=lambda: self.now)
        await service.mark_active_successful(
            7002,
            phone="03495863121",
            selected_accno="03495863121",
            selected_iban="PK12JAZZ000000003495863121",
            source="login_flow",
            dispatch_ds=True,
            df_order_enabled=True,
            channels=["1003"],
        )

        await service.clear_snapshot(7002)

        self.assertIsNone(await self.redis.get(keyspace.snapshot_key(7002)))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_ONLINE, 7002))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, 7002))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, 7002))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, 7002))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, 7002))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DISPATCH_DF, 7002))
        self.assertIsNone(await self.redis.zscore(keyspace.INDEX_UPDATED_AT, 7002))
        self.assertIsNone(await self.redis.zscore(keyspace.SCHEDULE_COLLECTION, 7002))


if __name__ == "__main__":
    unittest.main()
