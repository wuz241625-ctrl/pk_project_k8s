import json
import sys
import unittest
from fnmatch import fnmatch
from unittest.mock import AsyncMock, MagicMock

from application.easypaisa_runtime import keyspace


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

        snapshot = service.set_kickoff(
            533280,
            phone="923045536108",
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
            dispatch_ds=True,
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
        self.monitor.runtime_service.force_offline.assert_called_once_with(
            533280,
            phone="923045536108",
            source="easypaisa_monitor",
            reason="api_error",
        )

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
            dispatch_ds=True,
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
            dispatch_ds=True,
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
            dispatch_ds=True,
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

    def test_inactive_cleanup_reads_runtime_online_index_for_easypaisa(self):
        from jobs.clear_redis_inactive_payment import get_all_active_payment_ids_from_redis

        self.worker.redis.sadd("easypaisa_runtime:index:online", 533280)

        active = get_all_active_payment_ids_from_redis(self.worker.redis)

        self.assertEqual(active["533280"], "easypaisa")


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

    async def test_verify_and_handle_abnormal_payout_still_offlines_for_non_transient_failure(self):
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

        self.worker.on_off.assert_called_once_with(login_data, 0)


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


if __name__ == "__main__":
    unittest.main()
