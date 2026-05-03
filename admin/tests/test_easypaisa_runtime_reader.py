import json
import os
import sys
import unittest
from unittest.mock import patch


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

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

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    async def hset(self, key, field, value):
        bucket = self.hashes.setdefault(key, {})
        bucket[str(field)] = value
        return True

    async def hdel(self, key, *fields):
        bucket = self.hashes.get(key, {})
        removed = 0
        for field in fields:
            if str(field) in bucket:
                del bucket[str(field)]
                removed += 1
        return removed

    async def zrem(self, key, *members):
        bucket = self.zsets.get(key, {})
        removed = 0
        for member in members:
            if str(member) in bucket:
                del bucket[str(member)]
                removed += 1
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

    async def llen(self, key):
        return len(self.lists.get(key, []))


class EasyPaisaAdminRuntimeReaderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()

    async def test_reader_prefers_runtime_snapshot_for_easypaisa_online_df(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.set(
            "easypaisa_runtime:snapshot:533280",
            json.dumps(
                {
                    "payment_id": 533280,
                    "online": True,
                    "dispatch_df": True,
                    "session_phase": "activeSuccessful",
                }
            ),
        )

        reader = EasyPaisaAdminRuntimeReader(self.redis)

        self.assertTrue(await reader.is_payment_online_df(533280, bank_type=97))
        self.assertTrue(await reader.is_payment_online_status(533280, bank_type=97))

    async def test_reader_legacy_snapshot_keeps_df_online_when_dispatch_ds_is_false(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.set(
            "easypaisa_runtime:snapshot:533280",
            json.dumps(
                {
                    "payment_id": 533280,
                    "online": True,
                    "dispatch_df": True,
                    "dispatch_ds": False,
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        reader = EasyPaisaAdminRuntimeReader(self.redis)

        self.assertTrue(await reader.is_payment_online_df(533280, bank_type=97))
        self.assertTrue(await reader.is_payment_online_status(533280, bank_type=97))

    async def test_reader_returns_ds_from_runtime_snapshot_for_easypaisa(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.set(
            "easypaisa_runtime:snapshot:533280",
            json.dumps(
                {
                    "payment_id": 533280,
                    "online": True,
                    "collect_enabled": True,
                    "ds_order_enabled": True,
                    "df_order_enabled": False,
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        await self.redis.sadd("payment_online_df", 533280)

        reader = EasyPaisaAdminRuntimeReader(self.redis)

        self.assertTrue(await reader.is_payment_online_ds(533280, bank_type=97))
        self.assertFalse(await reader.is_payment_online_df(533280, bank_type=97))

    async def test_reader_falls_back_to_legacy_for_non_easypaisa(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.sadd("payment_online_df", 533280)
        await self.redis.set("login_on_phonepe_533280", "1")

        reader = EasyPaisaAdminRuntimeReader(self.redis)

        self.assertTrue(await reader.is_payment_online_df(533280, bank_type=14))
        self.assertTrue(await reader.is_payment_online_status(533280, bank_type=14, bank_name="phonepe"))

    async def test_reader_ignores_runtime_duplicate_lock_when_runtime_snapshot_missing(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.set(keyspace.lock_payment_key(533280), "1")

        reader = EasyPaisaAdminRuntimeReader(self.redis)

        self.assertFalse(await reader.is_payment_online_status(533280, bank_type=97))

    async def test_reader_does_not_trust_legacy_df_for_easypaisa_without_snapshot(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.sadd("payment_online_df", 533280)
        await self.redis.sadd("payment_online_ds", 533280)
        await self.redis.set("login_on_easypaisa_533280", "1")
        reader = EasyPaisaAdminRuntimeReader(self.redis)

        self.assertFalse(await reader.is_payment_online_df(533280, bank_type=97))
        self.assertFalse(await reader.is_payment_online_ds(533280, bank_type=97))
        self.assertFalse(await reader.is_payment_online_status(533280, bank_type=97))

    async def test_reader_active_queue_count_ignores_runtime_read_disable_flag(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader

        await self.redis.rpush("payment_active_df", 533280)
        await self.redis.rpush("payment_active_df", 533281)

        with patch.dict(os.environ, {"EASYPAISA_RUNTIME_READ_ENABLED": "0"}):
            reader = EasyPaisaAdminRuntimeReader(self.redis)

            self.assertEqual(await reader.active_df_count(), 0)


class EasyPaisaAdminRuntimeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()

    async def test_force_reset_clears_session_and_marks_snapshot_offline(self):
        from application.easypaisa_runtime.service import EasyPaisaAdminRuntimeService

        await self.redis.set(
            "easypaisa_runtime:snapshot:533280",
            json.dumps(
                {
                    "payment_id": 533280,
                    "phone": "923045536108",
                    "online": True,
                    "dispatch_df": True,
                    "dispatch_ds": True,
                    "channels": ["1001"],
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        await self.redis.set("easypaisa_runtime:session:533280", json.dumps({"status": "otpSent"}))
        await self.redis.sadd("easypaisa_runtime:index:online", 533280)
        await self.redis.sadd("easypaisa_runtime:index:dispatch_ds", 533280)
        await self.redis.sadd("payment_online_df", 533280)
        await self.redis.sadd("payment_online_ds", 533280)
        await self.redis.rpush("payment_active_df", 533280)
        await self.redis.rpush("payment_active_1001", 533280)
        await self.redis.set("login_on_easypaisa_533280", "1")
        await self.redis.set("login_on_easypaisa_923045536108", "1")
        await self.redis.set(keyspace.lock_payment_key(533280), "1")
        await self.redis.set(keyspace.lock_phone_key("923045536108"), "1")

        service = EasyPaisaAdminRuntimeService(self.redis, now_provider=lambda: 1_744_100_000)
        snapshot = await service.force_reset(533280, source="admin_resetting_payment")

        self.assertFalse(snapshot["online"])
        self.assertEqual(snapshot["session_phase"], "offline")
        self.assertEqual(snapshot["last_transition"], "admin_resetting_payment")
        self.assertIsNone(await self.redis.get("easypaisa_runtime:session:533280"))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:online", 533280))
        self.assertFalse(await self.redis.sismember("easypaisa_runtime:index:dispatch_ds", 533280))
        self.assertFalse(await self.redis.sismember("payment_online_df", 533280))
        self.assertFalse(await self.redis.sismember("payment_online_ds", 533280))
        self.assertEqual(self.redis.lists["payment_active_df"], [])
        self.assertEqual(self.redis.lists["payment_active_1001"], [])
        self.assertIsNone(await self.redis.get("login_on_easypaisa_533280"))
        self.assertIsNone(await self.redis.get(keyspace.lock_payment_key(533280)))
        self.assertIsNone(await self.redis.get(keyspace.lock_phone_key("923045536108")))


class PartnerAndMonitorHelperTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()

    async def test_apply_easypaisa_runtime_fields_updates_partner_row_from_snapshot(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader
        from application.partner.partner import apply_easypaisa_runtime_fields

        await self.redis.set(
            "easypaisa_runtime:snapshot:533280",
            json.dumps(
                {
                    "payment_id": 533280,
                    "online": True,
                    "collect_enabled": True,
                    "ds_order_enabled": False,
                    "df_order_enabled": False,
                    "dispatch_df": False,
                    "dispatch_ds": False,
                    "session_phase": "activeSuccessful",
                }
            ),
        )
        await self.redis.sadd("payment_online_df", 533280)
        await self.redis.sadd("payment_online_ds", 533280)
        row = {"id": 533280, "bank_type": 14, "bank_type_id": 97, "online_status": 0, "online_ds": 1, "online_df": 1}
        reader = EasyPaisaAdminRuntimeReader(self.redis)

        await apply_easypaisa_runtime_fields(row, reader)

        self.assertEqual(row["online_status"], 1)
        self.assertEqual(row["online_ds"], 0)
        self.assertEqual(row["online_df"], 0)

    async def test_load_easypaisa_monitor_counts_uses_runtime_df_order_and_list_length(self):
        from application.easypaisa_runtime.reader import EasyPaisaAdminRuntimeReader
        from application.order.auto_payout import load_easypaisa_monitor_counts

        await self.redis.sadd("easypaisa_runtime:index:online", 533280, 533281)
        await self.redis.sadd("easypaisa_runtime:index:df_order_enabled", 533280)
        await self.redis.rpush("payment_active_df", 533280)
        await self.redis.rpush("payment_active_df", 533999)

        reader = EasyPaisaAdminRuntimeReader(self.redis)
        counts = await load_easypaisa_monitor_counts(self.redis, reader)

        self.assertEqual(counts["online_accounts"], 1)
        self.assertEqual(counts["active_accounts"], 1)


if __name__ == "__main__":
    unittest.main()
