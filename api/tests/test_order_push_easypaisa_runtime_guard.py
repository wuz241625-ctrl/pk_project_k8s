import unittest

import fakeredis

from jobs.order_push import _df_order_online, _requeue_df_if_online
from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService


class OrderPushEasyPaisaRuntimeGuardTests(unittest.TestCase):
    def setUp(self):
        self.redis = fakeredis.FakeRedis()

    def test_easypaisa_df_guard_ignores_stale_legacy_online_without_snapshot(self):
        payment = {"id": 533280, "bank_type": 97, "bank_type_id": 97}
        self.redis.sadd("payment_online_df", 533280)
        self.redis.rpush("payment_active_df", 533280)

        self.assertFalse(_df_order_online(self.redis, payment))
        self.assertFalse(_requeue_df_if_online(self.redis, payment))
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), [])

    def test_easypaisa_df_guard_treats_either_bank_field_as_runtime_owned(self):
        payment = {"id": 533280, "bank_type": 97, "bank_type_id": 14}
        self.redis.sadd("payment_online_df", 533280)
        self.redis.rpush("payment_active_df", 533280)

        self.assertFalse(_df_order_online(self.redis, payment))
        self.assertFalse(_requeue_df_if_online(self.redis, payment))
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), [])

    def test_easypaisa_df_guard_uses_runtime_snapshot(self):
        payment = {"id": 533280, "bank_type": 97, "bank_type_id": 97}
        service = SyncEasyPaisaRuntimeService(self.redis, now_provider=lambda: 1_744_000_000)
        service.mark_active_successful(
            533280,
            phone="923045536108",
            selected_accno="88521643",
            selected_iban="PK12HABB0000000088521643",
            source="test",
            collect_enabled=True,
            ds_order_enabled=False,
            df_order_enabled=True,
        )
        self.redis.lrem("payment_active_df", 0, 533280)

        self.assertTrue(_df_order_online(self.redis, payment))
        self.assertTrue(_requeue_df_if_online(self.redis, payment))
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), [b"533280"])

    def test_jazzcash_df_guard_ignores_stale_legacy_online_without_snapshot(self):
        payment = {"id": 99, "bank_type": 98, "bank_type_id": 98}
        self.redis.sadd("payment_online_df", 99)
        self.redis.rpush("payment_active_df", 99)

        self.assertFalse(_df_order_online(self.redis, payment))
        self.assertFalse(_requeue_df_if_online(self.redis, payment))
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), [])

    def test_jazzcash_df_guard_uses_runtime_snapshot(self):
        from application.jazzcash_runtime.sync_runtime_service import SyncJazzCashRuntimeService

        payment = {"id": 99, "bank_type": 98, "bank_type_id": 98}
        service = SyncJazzCashRuntimeService(self.redis, now_provider=lambda: 1_744_000_000)
        service.mark_active_successful(
            99,
            phone="03495863120",
            selected_accno="03495863120",
            selected_iban="PK12JAZZ000000003495863120",
            source="test",
            collect_enabled=True,
            ds_order_enabled=False,
            df_order_enabled=True,
        )
        self.redis.lrem("payment_active_df", 0, 99)

        self.assertTrue(_df_order_online(self.redis, payment))
        self.assertTrue(_requeue_df_if_online(self.redis, payment))
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), [b"99"])

    def test_non_runtime_df_guard_keeps_legacy_online(self):
        payment = {"id": 99, "bank_type": 14, "bank_type_id": 14}
        self.redis.sadd("payment_online_df", 99)

        self.assertTrue(_df_order_online(self.redis, payment))
        self.assertTrue(_requeue_df_if_online(self.redis, payment))
        self.assertEqual(self.redis.lrange("payment_active_df", 0, -1), [b"99"])


if __name__ == "__main__":
    unittest.main()
