import json
import unittest

import fakeredis

from jobs.time_out import TimeOutGuard


class TimeOutGuardTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis()
        self.guard = TimeOutGuard(self.redis)

    def test_guard_skips_offline_pid_for_ep_channel(self):
        # bank_type_id=97, 未在 INDEX_DISPATCH_DS
        allowed = self.guard.check(payment_id=533240, bank_type_id=97)
        self.assertFalse(allowed)

    def test_guard_allows_online_pid_for_ep_channel(self):
        self.redis.sadd("easypaisa_runtime:index:dispatch_ds", "533282")
        allowed = self.guard.check(payment_id=533282, bank_type_id=97)
        self.assertTrue(allowed)

    def test_requeue_ep_channel_uses_runtime_bridge(self):
        self.redis.set(
            "easypaisa_runtime:snapshot:533282",
            json.dumps(
                {
                    "payment_id": 533282,
                    "phone": "923045536108",
                    "online": True,
                    "collect_enabled": True,
                    "ds_order_enabled": True,
                    "df_order_enabled": False,
                    "dispatch_ds": True,
                    "dispatch_df": False,
                    "session_phase": "activeSuccessful",
                    "channels": ["1001"],
                }
            ),
        )

        self.assertTrue(
            self.guard.requeue(
                payment_id=533282,
                channel_code=1001,
                bank_type_id=97,
            )
        )
        self.assertEqual(self.redis.lrange("payment_active_1001", 0, -1), [b"533282"])

    def test_guard_skips_offline_pid_for_jazzcash_channel(self):
        allowed = self.guard.check(payment_id=7001, bank_type_id=98)
        self.assertFalse(allowed)

    def test_guard_allows_online_pid_for_jazzcash_channel(self):
        self.redis.sadd("jazzcash_runtime:index:dispatch_ds", "7001")
        allowed = self.guard.check(payment_id=7001, bank_type_id=98)
        self.assertTrue(allowed)

    def test_guard_bypasses_non_runtime_channels(self):
        allowed = self.guard.check(payment_id=999, bank_type_id=14)
        self.assertTrue(allowed)
