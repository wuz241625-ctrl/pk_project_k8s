import json
import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)


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

    async def set(self, key, value):
        self.kv[key] = value
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

    async def lrem(self, key, count, value):
        bucket = self.lists.setdefault(key, [])
        target = str(value)
        if count == 0:
            removed = bucket.count(target)
            self.lists[key] = [item for item in bucket if item != target]
            return removed
        raise NotImplementedError("fake only supports count=0")

    async def rpush(self, key, value):
        bucket = self.lists.setdefault(key, [])
        bucket.append(str(value))
        return len(bucket)

    async def lrange(self, key, start, end):
        bucket = self.lists.get(key, [])
        if end == -1:
            return bucket[start:]
        return bucket[start:end + 1]


class JazzCashAdminRuntimeReaderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()

    async def test_reader_uses_jazzcash_snapshot_instead_of_legacy(self):
        from application.jazzcash_runtime import keyspace
        from application.jazzcash_runtime.reader import JazzCashAdminRuntimeReader

        await self.redis.set(
            keyspace.snapshot_key(7001),
            json.dumps(
                {
                    "payment_id": 7001,
                    "online": True,
                    "collect_enabled": True,
                    "ds_order_enabled": False,
                    "df_order_enabled": True,
                    "dispatch_ds": False,
                    "dispatch_df": True,
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        await self.redis.sadd("payment_online_ds", 7001)

        reader = JazzCashAdminRuntimeReader(self.redis)

        self.assertTrue(await reader.is_payment_online_status(7001, bank_type=98))
        self.assertFalse(await reader.is_payment_online_ds(7001, bank_type=98))
        self.assertTrue(await reader.is_payment_online_df(7001, bank_type=98))

    async def test_reader_does_not_trust_legacy_when_snapshot_missing(self):
        from application.jazzcash_runtime.reader import JazzCashAdminRuntimeReader

        await self.redis.sadd("payment_online_ds", 7001)
        await self.redis.sadd("payment_online_df", 7001)
        await self.redis.set("login_on_jazzcash_7001", "1")

        reader = JazzCashAdminRuntimeReader(self.redis)

        self.assertFalse(await reader.is_payment_online_status(7001, bank_type=98))
        self.assertFalse(await reader.is_payment_online_ds(7001, bank_type=98))
        self.assertFalse(await reader.is_payment_online_df(7001, bank_type=98))


class JazzCashAdminRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()

    async def test_force_reset_clears_runtime_and_legacy_residuals(self):
        from application.jazzcash_runtime import keyspace
        from application.jazzcash_runtime.service import JazzCashAdminRuntimeService

        await self.redis.set(
            keyspace.snapshot_key(7001),
            json.dumps(
                {
                    "payment_id": 7001,
                    "phone": "03495863120",
                    "online": True,
                    "dispatch_ds": True,
                    "dispatch_df": True,
                    "channels": ["1003"],
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        await self.redis.set(keyspace.session_key(7001), '{"status":"activeSuccessful"}')
        await self.redis.set(keyspace.pre_login_key(7001), '{"status":"activeSuccessful"}')
        await self.redis.sadd(keyspace.INDEX_ONLINE, 7001)
        await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, 7001)
        await self.redis.sadd("payment_online_ds", 7001)
        await self.redis.sadd("payment_online_df", 7001)
        await self.redis.rpush("payment_active_1003", 7001)
        await self.redis.rpush("payment_active_df", 7001)
        await self.redis.set("login_on_jazzcash_7001", "1")
        await self.redis.set("login_on_jazzcash_03495863120", "1")
        await self.redis.hset(keyspace.JOB_HASH, 7001, '{"status":"grabstatement"}')
        await self.redis.zadd(keyspace.JOB_SET, {7001: 1_744_000_000})

        service = JazzCashAdminRuntimeService(self.redis, now_provider=lambda: 1_744_000_001)
        snapshot = await service.force_reset(7001, source="admin_reset")

        self.assertFalse(snapshot["online"])
        self.assertEqual(snapshot["session_phase"], "offline")
        self.assertIsNone(await self.redis.get(keyspace.session_key(7001)))
        self.assertIsNone(await self.redis.get(keyspace.pre_login_key(7001)))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_ONLINE, 7001))
        self.assertFalse(await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, 7001))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 7001))
        self.assertFalse(await self.redis.sismember("payment_online_df", 7001))
        self.assertEqual(self.redis.lists["payment_active_1003"], [])
        self.assertEqual(self.redis.lists["payment_active_df"], [])
        self.assertIsNone(await self.redis.get("login_on_jazzcash_7001"))
        self.assertIsNone(await self.redis.get("login_on_jazzcash_03495863120"))
        self.assertIsNone(await self.redis.hget(keyspace.JOB_HASH, 7001))
        self.assertIsNone(await self.redis.zscore(keyspace.JOB_SET, 7001))


class PartnerJazzCashRuntimeHelperTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()

    async def test_apply_jazzcash_runtime_fields_updates_partner_row_from_snapshot(self):
        from application.jazzcash_runtime import keyspace
        from application.jazzcash_runtime.reader import JazzCashAdminRuntimeReader
        from application.partner.partner import apply_jazzcash_runtime_fields

        await self.redis.set(
            keyspace.snapshot_key(7001),
            json.dumps(
                {
                    "payment_id": 7001,
                    "online": True,
                    "collect_enabled": True,
                    "ds_order_enabled": False,
                    "df_order_enabled": True,
                    "dispatch_ds": False,
                    "dispatch_df": True,
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        await self.redis.sadd("payment_online_ds", 7001)
        row = {"id": 7001, "bank_type": 98, "bank_type_id": 98, "online_status": 0, "online_ds": 1, "online_df": 0}

        await apply_jazzcash_runtime_fields(row, JazzCashAdminRuntimeReader(self.redis))

        self.assertEqual(row["online_status"], 1)
        self.assertEqual(row["online_ds"], 0)
        self.assertEqual(row["online_df"], 1)


if __name__ == "__main__":
    unittest.main()
