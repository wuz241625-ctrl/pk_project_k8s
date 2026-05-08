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
        service.account_selector = MagicMock()
        service.account_selector.check_account_release_time.return_value = True
        service.order_lifecycle = MagicMock()
        service.order_lifecycle.process_payout_order = AsyncMock(return_value={"success": True})
        account = {"payment_id": "533280", "phone": "03000000000"}
        orders = [{"code": "ORD001", "amount": 100}]

        result = asyncio.run(
            service.process_members_concurrent(account_order_batches=[(account, orders)])
        )

        self.assertEqual(result, (1, 1))
        service.order_lifecycle.process_payout_order.assert_awaited_once_with(
            orders[0], selected_account=account
        )

    def test_auto_payout_respects_concurrent_limit(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.logger = MagicMock()
        service.account_selector = MagicMock()
        service.account_selector.check_account_release_time.return_value = True
        service.order_lifecycle = MagicMock()
        active = 0
        max_active = 0

        async def process_order(_order, selected_account=None):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {"success": True}

        service.order_lifecycle.process_payout_order = AsyncMock(side_effect=process_order)
        batches = [
            ({"payment_id": "1", "phone": "03000000001"}, [{"code": "ORD001", "amount": 100}]),
            ({"payment_id": "2", "phone": "03000000002"}, [{"code": "ORD002", "amount": 100}]),
        ]

        result = asyncio.run(
            service.process_members_concurrent(
                account_order_batches=batches,
                concurrent_limit=1,
            )
        )

        self.assertEqual(result, (2, 2))
        self.assertEqual(max_active, 1)

    def test_auto_payout_marks_stale_claimed_orders_before_polling(self):
        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        service = EasyPaisaAutoPayout.__new__(EasyPaisaAutoPayout)
        service.logger = MagicMock()
        service.order_lifecycle = MagicMock()
        service.order_lifecycle.filter_cooldown_orders.side_effect = lambda orders: orders
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = []
        fake_conn = MagicMock()
        fake_conn.cursor.return_value.__enter__ = MagicMock(return_value=fake_cursor)
        fake_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        import jobs.easypaisa.auto_payout as auto_payout_module

        original_connect = auto_payout_module.pymysql.connect
        auto_payout_module.pymysql.connect = MagicMock(return_value=fake_conn)
        try:
            asyncio.run(service.get_pending_orders_by_time())
        finally:
            auto_payout_module.pymysql.connect = original_connect

        service.order_lifecycle.mark_stale_claimed_orders_unknown.assert_called_once()

    def test_auto_payout_no_longer_accepts_legacy_members_argument(self):
        from inspect import signature

        from jobs.easypaisa.auto_payout import EasyPaisaAutoPayout

        parameters = signature(EasyPaisaAutoPayout.process_members_concurrent).parameters

        self.assertIn("account_order_batches", parameters)
        self.assertNotIn("members", parameters)

    def test_auto_payout_online_check_uses_mysql_payout_status_not_snapshot_gate(self):
        from jobs.easypaisa.payout.account_selector import AccountSelector

        service = AccountSelector.__new__(AccountSelector)
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

    def test_auto_payout_business_switch_no_longer_uses_redis_key(self):
        files = [
            API_ROOT / "application" / "pay" / "payout.py",
            API_ROOT / "jobs" / "easypaisa" / "auto_payout.py",
            API_ROOT / "jobs" / "easypaisa" / "payout" / "order_lifecycle.py",
            API_ROOT / "jobs" / "jazzcash" / "jazzcash_auto_payout.py",
            API_ROOT / "jobs" / "jazzcash" / "payout" / "order_lifecycle.py",
            API_ROOT.parent / "admin" / "application" / "order" / "auto_payout.py",
        ]

        for path in files:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("easypaisa_" + "emergency_stop", source, str(path))
            self.assertTrue(
                "auto_payout_system_status" in source or "is_auto_payout_enabled" in source,
                str(path),
            )

    def test_target_payment_cache_is_not_used_as_business_state(self):
        files = [
            API_ROOT / "main.py",
            API_ROOT / "application" / "pay" / "dispatch.py",
            API_ROOT / "jobs" / "jazzcash" / "payout" / "order_lifecycle.py",
            API_ROOT.parent / "admin" / "application" / "merchant" / "merchant.py",
        ]

        for path in files:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("target_" + "payment_key", source, str(path))


if __name__ == "__main__":
    unittest.main()
