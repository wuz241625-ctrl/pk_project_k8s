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


class EasyPaisaRedisCompatRetirementTests(unittest.TestCase):
    def test_pay_df_no_longer_publishes_order_df_push(self):
        pay_py = API_ROOT / "application" / "pay" / "pay.py"
        source = pay_py.read_text(encoding="utf-8")

        self.assertNotIn("order_df_push", source)

    def test_auto_payout_no_longer_contains_retired_queue_cleanup_helpers(self):
        source = (JOBS_ROOT / "easypaisa" / "auto_payout.py").read_text(encoding="utf-8")

        self.assertNotIn("clear_retired_", source)
        self.assertNotIn("payment_" + "active_", source)

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

    def test_bill_worker_does_not_use_realtime_logout_redis_key(self):
        source = (JOBS_ROOT / "pakistanpay_v2.py").read_text(encoding="utf-8")

        self.assertNotIn("login_off_" + "realtime_", source)

    def test_app_login_no_longer_touches_retired_runtime_keys(self):
        source = (API_ROOT / "application" / "app" / "login" / "banks" / "easypaisa.py").read_text(encoding="utf-8")

        self.assertNotIn("easypaisa_" + "runtime:", source)

    def test_retired_runtime_audit_script_is_removed(self):
        repo_root = API_ROOT.parent

        self.assertFalse((repo_root / "scripts" / "ep_state_audit.py").exists())
        self.assertFalse((repo_root / "scripts" / "ep_dispatch_trace.py").exists())


if __name__ == "__main__":
    unittest.main()
