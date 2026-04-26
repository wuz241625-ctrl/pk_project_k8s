import asyncio
import json
import os
import sys
import unittest
from fnmatch import fnmatch
from unittest.mock import AsyncMock, MagicMock, patch

from application.jazzcash_runtime import keyspace

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

    @staticmethod
    def _text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def get(self, key):
        return self.kv.get(self._text(key))

    def set(self, key, value, ex=None, nx=False):
        key = self._text(key)
        if nx and key in self.kv:
            return False
        self.kv[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True

    def setex(self, key, ttl, value):
        key = self._text(key)
        self.kv[key] = value
        self.ttl_map[key] = ttl
        return True

    def setnx(self, key, value):
        key = self._text(key)
        if key in self.kv:
            return False
        self.kv[key] = value
        return True

    def expire(self, key, ttl):
        self.ttl_map[self._text(key)] = ttl
        return True

    def ttl(self, key):
        key = self._text(key)
        if key not in self.kv:
            return -2
        return self.ttl_map.get(key, -1)

    def delete(self, *keys):
        removed = 0
        for key in keys:
            text = self._text(key)
            removed += 1 if text in self.kv else 0
            self.kv.pop(text, None)
            self.ttl_map.pop(text, None)
        return removed

    def exists(self, key):
        return self._text(key) in self.kv

    def keys(self, pattern):
        return [key.encode("utf-8") for key in self.kv if fnmatch(key, pattern)]

    def hset(self, key, field, value):
        self.hashes.setdefault(self._text(key), {})[self._text(field)] = value
        return 1

    def hget(self, key, field):
        return self.hashes.get(self._text(key), {}).get(self._text(field))

    def hdel(self, key, *fields):
        bucket = self.hashes.setdefault(self._text(key), {})
        removed = 0
        for field in fields:
            text = self._text(field)
            removed += 1 if text in bucket else 0
            bucket.pop(text, None)
        return removed

    def hexists(self, key, field):
        return self._text(field) in self.hashes.get(self._text(key), {})

    def sadd(self, key, *values):
        bucket = self.sets.setdefault(self._text(key), set())
        before = len(bucket)
        for value in values:
            bucket.add(self._text(value))
        return len(bucket) - before

    def srem(self, key, *values):
        bucket = self.sets.setdefault(self._text(key), set())
        removed = 0
        for value in values:
            text = self._text(value)
            removed += 1 if text in bucket else 0
            bucket.discard(text)
        return removed

    def sismember(self, key, value):
        return self._text(value) in self.sets.get(self._text(key), set())

    def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(self._text(key), {})
        for member, score in mapping.items():
            bucket[self._text(member)] = float(score)
        return True

    def zscore(self, key, member):
        return self.zsets.get(self._text(key), {}).get(self._text(member))

    def zrem(self, key, *members):
        bucket = self.zsets.setdefault(self._text(key), {})
        removed = 0
        for member in members:
            text = self._text(member)
            removed += 1 if text in bucket else 0
            bucket.pop(text, None)
        return removed

    def zrangebyscore(self, key, min_score, max_score, start=0, num=None):
        members = [
            member
            for member, score in sorted(self.zsets.get(self._text(key), {}).items(), key=lambda item: item[1])
            if float(min_score) <= score <= float(max_score)
        ]
        if num is None:
            selected = members[start:]
        else:
            selected = members[start:start + num]
        return [member.encode("utf-8") for member in selected]

    def lrem(self, key, count, value):
        key = self._text(key)
        bucket = self.lists.setdefault(key, [])
        target = self._text(value)
        if count == 0:
            removed = bucket.count(target)
            self.lists[key] = [item for item in bucket if item != target]
            return removed
        raise NotImplementedError("test fake only supports count=0")

    def rpush(self, key, value):
        bucket = self.lists.setdefault(self._text(key), [])
        bucket.append(self._text(value))
        return len(bucket)

    def ping(self):
        return True


class JazzCashSyncCollectionStateTests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeSyncRedis()
        self.now = 1_776_880_000

    def test_sync_collection_job_state_writes_runtime_snapshot_and_job_queue(self):
        from application.jazzcash_runtime.sync_runtime_service import SyncJazzCashRuntimeService

        service = SyncJazzCashRuntimeService(self.redis, now_provider=lambda: self.now)

        snapshot = service.sync_collection_job_state(
            {
                "id": 7001,
                "phone": "03495863120",
                "status": "grabstatement",
                "qr_channel": "1003",
                "account_accno": "03495863120",
                "account_iban": "PK12JAZZ000000003495863120",
            },
            source="Jazzcashpay_v2",
            schedule_score=123,
            collect_enabled=True,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertTrue(snapshot["ds_order_enabled"])
        self.assertTrue(snapshot["df_order_enabled"])
        self.assertTrue(self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, 7001))
        self.assertEqual(self.redis.zscore(keyspace.JOB_SET, 7001), 123.0)
        self.assertEqual(self.redis.zscore(keyspace.SCHEDULE_COLLECTION, 7001), float(self.now))
        stored_job = json.loads(self.redis.hget(keyspace.JOB_HASH, 7001))
        self.assertEqual(stored_job["status"], "grabstatement")
        self.assertEqual(stored_job["account_iban"], "PK12JAZZ000000003495863120")

    def test_collect_disabled_removes_job_and_blocks_df_because_payout_needs_statement_reconciliation(self):
        from application.jazzcash_runtime.sync_runtime_service import SyncJazzCashRuntimeService

        service = SyncJazzCashRuntimeService(self.redis, now_provider=lambda: self.now)
        self.redis.hset(keyspace.JOB_HASH, 7001, json.dumps({"status": "grabstatement"}))
        self.redis.zadd(keyspace.JOB_SET, {7001: 88})

        snapshot = service.sync_collection_job_state(
            {"id": 7001, "phone": "03495863120", "status": "grabstatement"},
            source="Jazzcashpay_v2",
            collect_enabled=False,
            ds_order_enabled=True,
            df_order_enabled=True,
        )

        self.assertFalse(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["df_order_enabled"])
        self.assertFalse(service.is_df_order_online(7001))
        self.assertIsNone(self.redis.hget(keyspace.JOB_HASH, 7001))
        self.assertIsNone(self.redis.zscore(keyspace.JOB_SET, 7001))


class JazzCashCollectionWorkerTests(unittest.TestCase):
    def setUp(self):
        import jobs.Jazzcashpay_v2 as jazzcash_worker
        from application.jazzcash_runtime.sync_runtime_service import SyncJazzCashRuntimeService

        self.jazzcash_worker = jazzcash_worker
        self.redis = FakeSyncRedis()
        self.now = 1_776_880_100
        self.worker = jazzcash_worker.BankLogin.__new__(jazzcash_worker.BankLogin)
        self.worker.name = "jazzcash"
        self.worker.list_key = "list_jazzcash"
        self.worker.hash_key = keyspace.JOB_HASH
        self.worker.set_key = keyspace.JOB_SET
        self.worker.if_callback_key = "if_callback_jazzcash"
        self.worker.redis = self.redis
        self.worker.runtime_service = SyncJazzCashRuntimeService(self.redis, now_provider=lambda: self.now)
        self.worker.logger = MagicMock()
        self.worker.lock_time = 30
        self.worker.time_grab = 40
        self.worker.time_grab2 = 600
        self.worker.try_count_limit = 10
        self.worker.get_lock = MagicMock(return_value="lock-value")
        self.worker.del_lock = MagicMock(return_value=True)
        self.worker.get_proxies = MagicMock(return_value={})
        self.worker.check_proxy = MagicMock(return_value={})
        self.worker.read_zset = MagicMock()
        self.worker.clean_if_callback_key = MagicMock()
        self.worker.payment_runtime_policy = MagicMock(return_value="dispatch_on")
        self.worker.get_grabstatement = AsyncMock(return_value=True)

    def test_worker_skips_stale_job_when_runtime_collect_is_disabled(self):
        payment_id = 7001
        self.worker.runtime_service.force_offline(
            payment_id,
            phone="03495863120",
            source="test",
            reason="admin_offline",
        )
        self.redis.hset(
            keyspace.JOB_HASH,
            payment_id,
            json.dumps({"id": payment_id, "phone": "03495863120", "status": "grabstatement"}).encode("utf-8"),
        )
        self.redis.zadd(keyspace.JOB_SET, {payment_id: self.now - 60})

        result = asyncio.run(self.worker.process_single_member_async(str(payment_id).encode("utf-8")))

        self.assertFalse(result)
        self.worker.get_grabstatement.assert_not_called()
        self.assertIsNone(self.redis.hget(keyspace.JOB_HASH, payment_id))
        self.assertIsNone(self.redis.zscore(keyspace.JOB_SET, payment_id))

    def test_main_promotes_active_successful_prelogin_through_runtime_not_direct_legacy_queue(self):
        payment_id = 7002
        pre_login_key = "pre_login_jazzcash_03495863121"
        self.redis.set(
            pre_login_key,
            json.dumps(
                {
                    "id": "03495863121",
                    "real_payment_id": payment_id,
                    "phone": "03495863121",
                    "status": "activeSuccessful",
                    "qr_channel": "1003",
                    "account_accno": "03495863121",
                    "account_iban": "PK12JAZZ000000003495863121",
                }
            ).encode("utf-8"),
        )
        self.worker.payment_runtime_policy = MagicMock(return_value="order_paused")

        with patch.object(self.jazzcash_worker.time, "sleep", return_value=None):
            self.worker.main()

        snapshot = self.worker.runtime_service.read_snapshot(payment_id)
        self.assertTrue(snapshot["online"])
        self.assertTrue(snapshot["collect_enabled"])
        self.assertFalse(snapshot["ds_order_enabled"])
        self.assertFalse(snapshot["df_order_enabled"])
        self.assertIsNone(self.redis.get(pre_login_key))
        self.assertIsNotNone(self.redis.hget(keyspace.JOB_HASH, payment_id))
        self.assertEqual(self.redis.zscore(keyspace.JOB_SET, payment_id), 0.0)


if __name__ == "__main__":
    unittest.main()
