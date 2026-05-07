import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


API_ROOT = Path(__file__).resolve().parents[1]
JOBS_ROOT = API_ROOT / "jobs"
for path in (str(API_ROOT), str(JOBS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


class FakeRedis:
    def __init__(self):
        self.lists = {}

    def lrem(self, key, count, value):
        target = str(value)
        bucket = self.lists.setdefault(key, [])
        self.lists[key] = [item for item in bucket if item != target]
        return True

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(str(value))
        return True

    def get(self, key):
        return None


class EasyPaisaRedisCompatRetirementTests(unittest.TestCase):
    def test_pay_df_no_longer_publishes_order_df_push(self):
        pay_py = API_ROOT / "application" / "pay" / "pay.py"
        source = pay_py.read_text(encoding="utf-8")

        self.assertNotIn("order_df_push", source)

    def test_auto_payout_does_not_return_accounts_to_payment_active_df(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.redis = FakeRedis()
        service.logger = MagicMock()
        service.REDIS_KEYS = {"retired_payment_active_df": "payment_active_df"}
        service.redis.rpush("payment_active_df", "533280")

        self.assertFalse(service.clear_retired_df_queue_residue("533280"))
        service.clear_retired_account_queue_residue({"payment_id": "533280", "phone": "03000000000"})

        self.assertEqual(service.redis.lists["payment_active_df"], [])

    def test_auto_payout_uses_account_order_batches_parameter_name(self):
        from inspect import signature

        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        parameters = signature(EasyPaisaAutoPayout.process_members_concurrent).parameters

        self.assertIn("account_order_batches", parameters)
        self.assertNotIn("dispatched_pairs", parameters)

    def test_auto_payout_processes_account_order_batches_in_memory(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.logger = MagicMock()
        service.check_account_release_time = MagicMock(return_value=True)
        service.process_single_order_async = AsyncMock(return_value=True)
        account = {"payment_id": "533280", "phone": "03000000000"}
        orders = [{"code": "ORD001", "amount": 100}]

        result = asyncio.run(
            service.process_members_concurrent(account_order_batches=[(account, orders)])
        )

        self.assertEqual(result, (1, 1))
        service.process_single_order_async.assert_awaited_once_with(
            "ORD001_100", pre_selected_account=account
        )

    def test_auto_payout_rejects_legacy_members_mode_without_processing(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.logger = MagicMock()
        service.process_single_order_async = AsyncMock(return_value=True)

        result = asyncio.run(service.process_members_concurrent(members=[b"ORD001_100"], concurrent_limit=1))

        self.assertEqual(result, (0, 0))
        service.process_single_order_async.assert_not_called()

    def test_auto_payout_online_check_uses_mysql_payout_status_not_snapshot_gate(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.logger = MagicMock()
        service.get_phone_by_payment_id = MagicMock(return_value={"phone": "03000000000", "payout_status": 1})
        service._check_account_online_via_api = AsyncMock(return_value=True)

        self.assertTrue(asyncio.run(service.check_account_online_status("533280")))


if __name__ == "__main__":
    unittest.main()
