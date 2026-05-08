import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def ttl(self, key):
        return 120 if key in self.values else -2


class EasyPaisaMonitorIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    def _monitor(self):
        from jobs.easypaisa.easypaisa_monitor import AutoPayoutMonitor

        monitor = AutoPayoutMonitor.__new__(AutoPayoutMonitor)
        monitor.name = "ep_monitor"
        monitor.redis = FakeRedis()
        monitor.logger = MagicMock()
        monitor.REDIS_KEYS = {
            "easypaisa_monitor_report": "easypaisa_monitor_report",
            "easypaisa_limits_hash": "easypaisa_limits_hash",
            "easypaisa_account_lock_prefix": "easypaisa_account_lock:",
            "payment_id_lock_prefix": "payment_id_lock:",
        }
        monitor.restore_payment_dispatch_after_health_success = MagicMock(return_value=1)
        monitor.pause_payment_dispatch_for_health_error = MagicMock(return_value=1)
        monitor.remove_account_completely = MagicMock(return_value=True)
        monitor.update_payment_balance_snapshot = MagicMock(return_value=1)
        return monitor

    def _online_status(self):
        return {
            "account_id": "533295",
            "payment_id": "533295",
            "phone": "03325009516",
            "account_name": "EasyPaisa_03325009516",
            "is_online": True,
            "status": "online",
            "balance": Decimal("1000.00"),
        }

    async def test_update_redis_cache_skips_balance_zadd_when_payout_lock_exists(self):
        monitor = self._monitor()
        monitor.redis.values["payment_id_lock:533295"] = b"payout-lock"

        result = await monitor.update_redis_cache(self._online_status())

        self.assertFalse(result)
        monitor.update_payment_balance_snapshot.assert_not_called()
        monitor.restore_payment_dispatch_after_health_success.assert_not_called()

    async def test_update_redis_cache_writes_mysql_balance_when_no_payout_lock(self):
        monitor = self._monitor()

        result = await monitor.update_redis_cache(self._online_status())

        self.assertFalse(result)
        monitor.update_payment_balance_snapshot.assert_called_once_with("533295", Decimal("1000.00"))
        monitor.restore_payment_dispatch_after_health_success.assert_called_once_with("533295")

    async def test_run_monitor_check_processes_only_allocated_payment_ids(self):
        monitor = self._monitor()
        monitor.get_online_payments_from_db = AsyncMock(return_value=[
            {"id": "533295"},
            {"id": "533296"},
            {"id": "533297"},
        ])
        monitor.get_process_allocated_members = MagicMock(return_value=[b"533296"])
        monitor.check_account_health = AsyncMock(side_effect=lambda row: {
            "account_id": str(row["id"]),
            "payment_id": str(row["id"]),
            "phone": f"phone-{row['id']}",
            "is_online": True,
            "status": "online",
            "balance": Decimal("100.00"),
        })
        monitor.update_redis_cache = AsyncMock(return_value=False)
        monitor.handle_problematic_accounts = AsyncMock()
        monitor.generate_monitor_report = AsyncMock()

        await monitor.run_easypaisa_monitor_check()

        monitor.get_process_allocated_members.assert_called_once_with([b"533295", b"533296", b"533297"])
        monitor.check_account_health.assert_awaited_once_with({"id": "533296"})
        monitor.update_redis_cache.assert_awaited_once()
        monitor.generate_monitor_report.assert_awaited_once()

    async def test_monitor_loop_interval_defaults_to_30_seconds(self):
        from jobs.easypaisa.easypaisa_monitor import get_monitor_loop_interval

        self.assertEqual(get_monitor_loop_interval({}), 30)
        self.assertEqual(get_monitor_loop_interval({"easypaisa_monitor_loop_interval": "45"}), 45)
        self.assertEqual(get_monitor_loop_interval({"easypaisa_monitor_loop_interval": "0"}), 1)
        self.assertEqual(get_monitor_loop_interval({"easypaisa_monitor_loop_interval": "bad"}), 30)


if __name__ == "__main__":
    unittest.main()
