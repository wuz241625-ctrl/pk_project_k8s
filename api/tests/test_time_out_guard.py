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
