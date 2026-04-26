import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs.jazzcash.jazzcash_auto_payout import JazzCashAutoPayout


class JazzCashAutoPayoutV16Tests(unittest.TestCase):
    def setUp(self):
        self.payout = JazzCashAutoPayout.__new__(JazzCashAutoPayout)
        self.payout.logger = MagicMock()
        self.payout._is_pakistan_mobile_number = MagicMock(return_value=True)
        self.payout.fetch_balance_from_api = AsyncMock(return_value={"success": True, "balance": Decimal("5000")})
        self.payout._call_jazzcash_api = AsyncMock(
            return_value={
                "code": 500,
                "msg": "upstream returned ambiguous transfer result",
                "data": {"ref": "JCB-AMBIGUOUS"},
            }
        )
        self.payout.log_complete_transaction = MagicMock()

    def test_transfer_code_500_enters_pending_reconciliation(self):
        result = asyncio.run(
            self.payout._execute_jazzcash_transfer(
                {
                    "code": "DF-DEMO-500",
                    "amount": "100",
                    "payment_account": "03001234567",
                    "payment_name": "Demo Receiver",
                    "ifsc": "jazzcash",
                    "bank_ifsc": "jazzcash",
                },
                {
                    "payment_id": 533298,
                    "phone": "03409297123",
                },
            )
        )

        self.assertFalse(result["success"])
        self.assertTrue(result["pending_check"])
        self.assertFalse(result.get("reject", False))
        self.assertFalse(result["can_retry"])
        self.assertEqual(result["code"], 500)
        self.assertIn("待核查", result["message"])

        self.payout.log_complete_transaction.assert_called_once()
        self.assertEqual(self.payout.log_complete_transaction.call_args.args[4], "pending_reconciliation")
        process_details = self.payout.log_complete_transaction.call_args.kwargs["process_details"]
        self.assertEqual(process_details["lock_release_details"]["release_reason"], "pending_reconciliation")

    def test_process_payout_order_preserves_pending_reconciliation_signal(self):
        self.payout.check_payout_risk = AsyncMock(return_value={"passed": True})
        self.payout._execute_jazzcash_transfer = AsyncMock(
            return_value={
                "success": False,
                "pending_check": True,
                "message": "JazzCash转账返回500，待核查",
                "can_retry": False,
                "code": 500,
            }
        )
        self.payout.set_account_release_time = MagicMock()
        self.payout.return_account_to_active_list = MagicMock()

        result = asyncio.run(
            self.payout.process_payout_order(
                {
                    "code": "DF-DEMO-500",
                    "amount": "100",
                    "payment_account": "03001234567",
                    "payment_name": "Demo Receiver",
                    "ifsc": "jazzcash",
                },
                selected_account={
                    "payment_id": 533298,
                    "phone": "03409297123",
                    "partner_id": 10001,
                },
            )
        )

        self.assertFalse(result["success"])
        self.assertTrue(result["pending_check"])
        self.assertFalse(result["treat_as_success"])
        self.assertEqual(result["code"], 500)
        self.assertEqual(result["payment_id"], 533298)
        self.assertEqual(result["partner_id"], 10001)

    def test_process_single_order_marks_pending_without_payment_failure_cooldown(self):
        class FakeCursor:
            def __init__(self):
                self.rowcount = 1
                self.statements = []
                self._next_row = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params=None):
                self.statements.append((sql, params))
                if "SELECT * FROM orders_df WHERE code" in sql:
                    self._next_row = {
                        "code": "DF-DEMO-500",
                        "amount": Decimal("100"),
                        "payment_account": "03001234567",
                        "payment_name": "Demo Receiver",
                        "ifsc": "jazzcash",
                        "status": 0,
                        "retry_count": 0,
                    }
                self.rowcount = 1

            def fetchone(self):
                return self._next_row

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()
                self.commit_count = 0
                self.closed = False

            def cursor(self):
                return self.cursor_obj

            def commit(self):
                self.commit_count += 1

            def close(self):
                self.closed = True

        fake_connection = FakeConnection()
        self.payout.redis = MagicMock()
        self.payout.redis.get = MagicMock(return_value=None)
        self.payout.prepare_account_and_locks = AsyncMock(
            return_value={
                "success": True,
                "selected_account": {
                    "payment_id": 533298,
                    "phone": "03409297123",
                    "partner_id": 10001,
                },
                "order_lock_value": "order-lock",
                "account_lock": "account-lock",
                "payment_id_lock_value": "payment-lock",
                "account_id": "03409297123",
                "payment_id": 533298,
            }
        )
        self.payout.process_payout_order = AsyncMock(
            return_value={
                "success": False,
                "pending_check": True,
                "treat_as_success": False,
                "message": "JazzCash转账返回500，待核查",
                "code": 500,
                "payment_id": 533298,
                "partner_id": 10001,
            }
        )
        self.payout.set_payment_id_failed = MagicMock()
        self.payout.record_payment_failure = MagicMock()
        self.payout.del_payment_id_lock = MagicMock()
        self.payout.release_account_lock = MagicMock()
        self.payout.del_lock = MagicMock()

        with patch("jobs.jazzcash.jazzcash_auto_payout.pymysql.connect", return_value=fake_connection):
            result = asyncio.run(self.payout.process_single_order_async("DF-DEMO-500_100"))

        self.assertFalse(result)
        self.payout.set_payment_id_failed.assert_not_called()
        self.payout.record_payment_failure.assert_not_called()
        status_updates = [
            (sql, params)
            for sql, params in fake_connection.cursor_obj.statements
            if "SET status = 2" in sql and "retry_count" in sql
        ]
        self.assertEqual(len(status_updates), 1)
        sql, params = status_updates[0]
        self.assertIn("sys_remark", sql)
        self.assertIn("待核查", params[1])
