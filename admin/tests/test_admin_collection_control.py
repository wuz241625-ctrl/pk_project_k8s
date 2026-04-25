import json
import os
import sys
import unittest

import fakeredis.aioredis

CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.easypaisa_runtime.service import EasyPaisaAdminRuntimeService
from application.easypaisa_runtime import keyspace


class AdminCollectionControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = fakeredis.aioredis.FakeRedis()
        self.service = EasyPaisaAdminRuntimeService(self.redis)

    async def test_admin_disable_goes_through_set_manual_off(self):
        payment_id = 940001
        await self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0306000001",
                        "online": True, "collect_enabled": True,
                        "ds_order_enabled": True, "df_order_enabled": True,
                        "dispatch_ds": True, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )
        await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        await self.redis.rpush("payment_active_1001", str(payment_id))

        await self.service.set_manual_off(payment_id, reason="admin_manual")

        assert await self.redis.get(keyspace.manual_off_collection_key(payment_id)) is not None
        snapshot = json.loads((await self.redis.get(keyspace.snapshot_key(payment_id))).decode())
        assert snapshot["manual_ds_paused"] is True
        assert snapshot["manual_ds_pause_reason"] == "admin_manual"
        assert await self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        assert str(payment_id).encode() not in await self.redis.lrange("payment_active_1001", 0, -1)

        await self.service.clear_manual_off(payment_id)
        snapshot = json.loads((await self.redis.get(keyspace.snapshot_key(payment_id))).decode())
        assert snapshot["manual_ds_paused"] is False
        assert snapshot["manual_ds_pause_reason"] is None
        assert await self.redis.get(keyspace.manual_off_collection_key(payment_id)) is None

    async def test_admin_health_pause_is_recorded_in_snapshot(self):
        payment_id = 940005
        await self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0306000005",
                        "online": True, "collect_enabled": True,
                        "ds_order_enabled": True, "df_order_enabled": True,
                        "dispatch_ds": True, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )

        snapshot = await self.service.set_order_health_pause(
            payment_id,
            reason="api_error",
            ttl=180,
            source="admin_health_pause",
            phone="0306000005",
            channels=["1001"],
        )

        assert snapshot["order_health_paused"] is True
        assert snapshot["order_health_pause_reason"] == "api_error"
        assert snapshot["order_health_paused_until"] > 0
        assert snapshot["ds_order_enabled"] is False
        assert snapshot["df_order_enabled"] is False
        assert await self.service.is_order_health_paused(payment_id) is True

        await self.service.clear_order_health_pause(payment_id, source="admin_health_clear")
        snapshot = json.loads((await self.redis.get(keyspace.snapshot_key(payment_id))).decode())
        assert snapshot["order_health_paused"] is False
        assert snapshot["order_health_pause_reason"] is None
        assert snapshot["order_health_paused_until"] == 0
        assert await self.service.is_order_health_paused(payment_id) is False

    async def test_admin_status_disable_pauses_dispatch_without_resetting_session_or_job(self):
        payment_id = 940003
        await self.redis.set(keyspace.session_key(payment_id), '{"status":"activeSuccessful"}')
        await self.redis.hset(keyspace.JOB_HASH, str(payment_id), '{"status":"grabstatement"}')
        await self.redis.zadd(keyspace.JOB_SET, {str(payment_id): 1_000})
        await self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({"payment_id": payment_id, "phone": "0306000003",
                        "online": True, "collect_enabled": True,
                        "ds_order_enabled": True, "df_order_enabled": True,
                        "dispatch_ds": True, "dispatch_df": True,
                        "session_phase": "activeSuccessful", "channels": ["1001"]}),
        )
        await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        await self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, str(payment_id))
        await self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, str(payment_id))
        await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        await self.redis.sadd(keyspace.INDEX_DISPATCH_DF, str(payment_id))
        await self.redis.rpush("payment_active_1001", str(payment_id))
        await self.redis.rpush("payment_active_df", str(payment_id))

        snapshot = await self.service.pause_order_dispatch(
            payment_id,
            phone="0306000003",
            channels=["1001"],
            source="admin_payment_disable",
        )

        assert snapshot["online"] is True
        assert snapshot["collect_enabled"] is True
        assert snapshot["ds_order_enabled"] is False
        assert snapshot["df_order_enabled"] is False
        assert await self.redis.get(keyspace.session_key(payment_id)) is not None
        assert await self.redis.hget(keyspace.JOB_HASH, str(payment_id)) is not None
        assert await self.redis.zscore(keyspace.JOB_SET, str(payment_id)) is not None
        assert await self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_DS_ORDER_ENABLED, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_DF_ORDER_ENABLED, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_DISPATCH_DF, str(payment_id))
        assert str(payment_id).encode() not in await self.redis.lrange("payment_active_1001", 0, -1)
        assert str(payment_id).encode() not in await self.redis.lrange("payment_active_df", 0, -1)

    async def test_admin_status_disable_offline_snapshot_does_not_recurse(self):
        payment_id = 940004
        await self.redis.set(
            keyspace.snapshot_key(payment_id),
            json.dumps({
                "payment_id": payment_id,
                "phone": "0306000004",
                "online": False,
                "collect_enabled": False,
                "ds_order_enabled": False,
                "df_order_enabled": False,
                "dispatch_ds": False,
                "dispatch_df": False,
                "session_phase": "offline",
                "channels": ["1001"],
            }),
        )

        snapshot = await self.service.pause_order_dispatch(
            payment_id,
            phone="0306000004",
            channels=["1001"],
            source="admin_payment_disable",
        )

        assert snapshot["online"] is False
        assert snapshot["collect_enabled"] is False
        assert snapshot["ds_order_enabled"] is False
        assert snapshot["df_order_enabled"] is False
        assert await self.redis.get(keyspace.session_key(payment_id)) is None
        assert await self.redis.hget(keyspace.JOB_HASH, str(payment_id)) is None
        assert not await self.redis.sismember(keyspace.INDEX_ONLINE, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_COLLECT_ENABLED, str(payment_id))
        assert not await self.redis.sismember(keyspace.INDEX_DISPATCH_DS, str(payment_id))

    async def test_admin_force_reset_clears_all_residuals(self):
        payment_id = 940002
        await self.redis.set(f"pre_login_easypaisa_{payment_id}", '{"status":"otpSent"}')
        await self.redis.setex(f"easypaisa_runtime:kickoff:{payment_id}", 1200, "1")
        await self.redis.hset("hash_easypaisa", str(payment_id), '{"status":"grabstatement"}')
        await self.redis.zadd("set_easypaisa", {str(payment_id): 1_000})
        await self.redis.set(keyspace.manual_off_collection_key(payment_id), "admin")
        await self.redis.setex(keyspace.health_pause_order_key(payment_id), 180, "api_error")
        await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): 1_000})

        await self.service.force_reset(payment_id, source="admin_reset")

        assert await self.redis.get(f"pre_login_easypaisa_{payment_id}") is None
        assert await self.redis.get(f"easypaisa_runtime:kickoff:{payment_id}") is None
        assert await self.redis.hget("hash_easypaisa", str(payment_id)) is None
        assert await self.redis.zscore("set_easypaisa", str(payment_id)) is None
        assert await self.redis.get(keyspace.manual_off_collection_key(payment_id)) is None
        assert await self.redis.get(keyspace.health_pause_order_key(payment_id)) is None
        assert await self.redis.zscore(keyspace.SCHEDULE_COLLECTION, str(payment_id)) is None


if __name__ == "__main__":
    unittest.main()
