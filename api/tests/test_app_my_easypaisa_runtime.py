import json
import unittest
from unittest.mock import MagicMock


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.ttl_map = {}
        self.sets = {}
        self.zsets = {}
        self.lists = {}

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

    async def zadd(self, key, mapping):
        bucket = self.zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)
        return True

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

    async def keys(self, pattern):
        import fnmatch

        keys = list(self.kv.keys()) + list(self.sets.keys()) + list(self.lists.keys())
        return [key for key in keys if fnmatch.fnmatch(key, pattern)]


class FakeMyHandler:
    def __init__(self):
        self.current_user = {"id": 9001}
        self.redis = FakeRedis()
        self.logger = MagicMock()
        self.payment_rows = []
        self.payment_by_id = {}
        self.updated_rows = []

    async def is_null(self, data, keys):
        return any(key not in data for key in keys)

    async def get_result(self, table, keys, condition, offset):
        assert table == "payment"
        assert condition == {"partner_id": self.current_user["id"]}
        return [dict(row) for row in self.payment_rows[offset:]]

    async def get_results_by_condition(self, table, keys, condition):
        assert table == "payment"
        assert condition == {"partner_id": self.current_user["id"]}
        return [dict(row) for row in self.payment_rows]

    async def get_result_by_condition(self, table, keys, condition):
        assert table == "payment"
        payment = self.payment_by_id.get(condition["id"])
        return dict(payment) if payment else None

    async def update_result(self, table, data, condition):
        assert table == "payment"
        payment = self.payment_by_id.get(condition["id"])
        if not payment:
            return False
        payment.update(data)
        self.updated_rows.append({"id": condition["id"], "data": dict(data)})
        return True


class AppMyEasyPaisaRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.handler = FakeMyHandler()
        self.now = 1_744_000_000

    async def _seed_runtime_online(self, payment_id=533280, phone="923045536108", dispatch_ds=True):
        from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService

        service = EasyPaisaRuntimeService(self.handler.redis, now_provider=lambda: self.now)
        await service.write_snapshot(
            payment_id,
            {
                "phone": phone,
                "online": True,
                "dispatch_df": True,
                "dispatch_ds": dispatch_ds,
                "session_phase": "activeSuccessful",
                "last_transition": "activeSuccessful",
            },
            source="test_seed",
        )
        return service

    async def test_getpayment_prefers_runtime_snapshot_for_easypaisa(self):
        from application.app.my import my as my_module

        self.handler.payment_rows = [
            {
                "id": 533280,
                "bank_type": 97,
                "net_id": "demo",
                "upi": "demo@wallet",
                "phone": "03045536108",
                "name": "EasyPaisa Demo",
                "status": 1,
                "certified": 1,
            }
        ]
        await self._seed_runtime_online(dispatch_ds=False)

        result = await my_module.getpayment(self.handler, {"offset": 0})

        self.assertEqual(result["type"], "payment.getpayment")
        self.assertEqual(result["data"][0]["online_ds"], 0)
        self.assertEqual(result["data"][0]["online_df"], 1)

    async def test_getonlinepayment_returns_runtime_online_easypaisa(self):
        from application.app.my import my as my_module

        self.handler.payment_rows = [
            {
                "id": 533280,
                "bank_type": 97,
                "net_id": "demo",
                "upi": "demo@wallet",
                "phone": "03045536108",
                "name": "EasyPaisa Demo",
                "status": 1,
                "certified": 1,
            }
        ]
        await self._seed_runtime_online(dispatch_ds=True)

        result = await my_module.getOnlinePayment(self.handler, {})

        self.assertEqual(result["type"], "payment.getOnlinePayment")
        self.assertEqual([row["id"] for row in result["data"]], [533280])
        self.assertEqual(result["data"][0]["online_ds"], 1)
        self.assertEqual(result["data"][0]["online_df"], 1)

    async def test_change_payment_offline_clears_easypaisa_runtime_state(self):
        from application.app.my import my as my_module
        from application.easypaisa_runtime.keyspace import session_key, snapshot_key

        payment_id = 533280
        phone = "923045536108"
        self.handler.payment_by_id[payment_id] = {
            "certified": 1,
            "bank_type": 97,
            "phone": phone,
            "account_type": 1,
            "partner_id": 9001,
            "channel": 1002,
        }
        service = await self._seed_runtime_online(payment_id=payment_id, phone=phone, dispatch_ds=True)
        await self.handler.redis.set(session_key(payment_id), json.dumps({"phase": "otpSent"}))
        await self.handler.redis.set(f"login_on_easypaisa_{payment_id}", "1")
        await self.handler.redis.set(f"login_on_easypaisa_{phone}", "1")
        await self.handler.redis.sadd("payment_online_ds", payment_id)
        await self.handler.redis.sadd("payment_online_df", payment_id)
        await self.handler.redis.rpush("payment_active_df", payment_id)

        result = await my_module.change_payment(self.handler, {"id": payment_id, "status": 0})

        self.assertEqual(result["code"], 10603)
        self.assertEqual(self.handler.payment_by_id[payment_id]["status"], 0)
        self.assertIsNone(await self.handler.redis.get(session_key(payment_id)))
        snapshot = json.loads(await self.handler.redis.get(snapshot_key(payment_id)))
        self.assertFalse(snapshot["online"])
        self.assertFalse(snapshot["dispatch_df"])
        self.assertFalse(snapshot["dispatch_ds"])
        self.assertEqual(snapshot["session_phase"], "offline")
        self.assertFalse(await self.handler.redis.sismember("payment_online_ds", payment_id))
        self.assertFalse(await self.handler.redis.sismember("payment_online_df", payment_id))
        self.assertEqual(self.handler.redis.lists["payment_active_df"], [])
        self.assertIsNone(await self.handler.redis.get(f"login_on_easypaisa_{payment_id}"))
        self.assertIsNone(await self.handler.redis.get(f"login_on_easypaisa_{phone}"))


if __name__ == "__main__":
    unittest.main()
