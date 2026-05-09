import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


ORDER_LIFECYCLE = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "order_lifecycle.py"
SETTLEMENT = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "settlement.py"
TRANSFER_EXECUTOR = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "transfer_executor.py"


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.executed = []
        self.rowcount = 0
        self._fetchone = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, params))
        if "SET status = 1" in normalized and "WHERE code = %s AND status = 0" in normalized:
            self.rowcount = self.connection.claim_rowcount
            return self.rowcount
        if normalized.startswith("SELECT * FROM orders_df WHERE code = %s"):
            self._fetchone = self.connection.order_row
            self.rowcount = 1 if self.connection.order_row else 0
            return self.rowcount
        if "SET status = 2" in normalized:
            self.rowcount = 1
            return 1
        if "SET retry_count = %s, status = 0" in normalized:
            self.rowcount = 1
            return 1
        if "SET retry_count=%s" in normalized and "WHERE code=%s AND status=-2" in normalized:
            self.rowcount = 1
            return 1
        self.rowcount = 1
        return 1

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return [self._fetchone] if self._fetchone else []


class FakeConnection:
    def __init__(self, claim_rowcount=1, retry_count=0):
        self.claim_rowcount = claim_rowcount
        self.order_row = {
            "code": "JZ001",
            "amount": Decimal("100.00"),
            "realpay": Decimal("100.00"),
            "merchant_id": 5,
            "partner_id": 9,
            "payment_id": "533302",
            "payment_account": "03001234567",
            "payment_name": "Ali",
            "retry_count": retry_count,
            "status": 1,
            "is_split": 0,
            "parent_id": None,
            "earn_merchant": Decimal("0"),
            "earn_partner_self": Decimal("0"),
        }
        self.cursor_obj = FakeCursor(self)
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _selected_account():
    return {
        "payment_id": "533302",
        "phone": "03409297123",
        "partner_id": 9,
        "balance": Decimal("1000.00"),
    }


def _lifecycle():
    from jobs.jazzcash.payout.order_lifecycle import OrderLifecycle

    redis_client = MagicMock()
    logger = MagicMock()
    config = {
        "redis_keys": {
            "payment_id_failed_prefix": "payment_id_failed_jazzcash:",
            "jazzcash_order_cooldown_hash": "jazzcash_order_cooldown",
        },
        "lock_time": 120,
    }
    settlement = MagicMock()
    transfer_executor = MagicMock()
    account_selector = MagicMock()
    transaction_logger = MagicMock()
    lifecycle = OrderLifecycle(
        redis_client,
        logger,
        config,
        settlement=settlement,
        transfer_executor=transfer_executor,
        account_selector=account_selector,
        transaction_logger=transaction_logger,
    )
    account_selector.get_lock.return_value = "order-lock"
    account_selector.acquire_account_lock = AsyncMock(return_value="account-lock")
    account_selector.get_payment_id_lock.return_value = "payment-lock"
    account_selector.del_lock.return_value = True
    account_selector.release_account_lock.return_value = True
    account_selector.del_payment_id_lock.return_value = True
    account_selector.check_account_release_time.return_value = True
    account_selector.is_account_recently_used.return_value = False
    account_selector.check_account_amount_limits = AsyncMock(return_value={"passed": True})
    account_selector.check_payment_balance.return_value = True
    account_selector.deduct_account_balance_in_transaction.return_value = True
    return lifecycle


class JazzCashPayoutStateMachineSourceTests(unittest.TestCase):
    def test_success_final_state_is_set_only_by_settlement_with_status_guard(self):
        lifecycle = ORDER_LIFECYCLE.read_text()
        settlement = SETTLEMENT.read_text()

        self.assertNotIn("WHERE code = %s AND status IN (0, 1)", lifecycle)
        self.assertNotIn("状态status=3已在转账成功时更新", settlement)
        self.assertIn("SET earn_merchant=%s,", settlement)
        self.assertIn("status=3", settlement)
        self.assertIn("WHERE code=%s AND status=1", settlement)

    def test_only_402_retries_and_third_402_rejects(self):
        lifecycle = ORDER_LIFECYCLE.read_text()
        transfer_executor = TRANSFER_EXECUTOR.read_text()

        self.assertIn("error_code == 402", lifecycle)
        self.assertIn("new_retry_count >= 3", lifecycle)
        self.assertNotIn("error_code in [402, 423, 503]", lifecycle)
        self.assertNotIn("new_retry_count > 8", lifecycle)
        self.assertNotIn("reject_msg_codes", transfer_executor)
        self.assertNotIn("msg_cd in reject_msg_codes", transfer_executor)

    def test_single_order_entry_does_not_keep_old_split_claim_and_success_chain(self):
        lifecycle = ORDER_LIFECYCLE.read_text()

        self.assertIn("_process_single_order_via_state_machine", lifecycle)
        self.assertNotIn("success_connection = pymysql.connect", lifecycle)
        self.assertNotIn("result = await self.process_payout_order(\n                        order_data,\n                        connection,", lifecycle)


class JazzCashPayoutStateMachineBehaviorTests(unittest.TestCase):
    def test_claim_failure_does_not_call_official_transfer(self):
        lifecycle = _lifecycle()
        fake_conn = FakeConnection(claim_rowcount=0)
        lifecycle.transfer_executor._execute_jazzcash_transfer = AsyncMock()

        with patch("jobs.jazzcash.payout.order_lifecycle.is_auto_payout_enabled", return_value=True), \
             patch("jobs.jazzcash.payout.order_lifecycle.pymysql.connect", return_value=fake_conn):
            result = asyncio_run(lifecycle.process_payout_order(
                {"code": "JZ001", "amount": "100.00", "retry_count": 0},
                selected_account=_selected_account(),
            ))

        self.assertFalse(result["success"])
        self.assertFalse(result["claimed"])
        lifecycle.transfer_executor._execute_jazzcash_transfer.assert_not_called()

    def test_success_claims_order_deducts_balance_and_calls_settlement_in_same_chain(self):
        lifecycle = _lifecycle()
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_jazzcash_transfer = AsyncMock(return_value={
            "success": True,
            "transaction_id": "JC-TXN-1",
            "payer_phone": "03409297123",
        })
        lifecycle.settlement.handle_payout_success.return_value = True

        with patch("jobs.jazzcash.payout.order_lifecycle.is_auto_payout_enabled", return_value=True), \
             patch("jobs.jazzcash.payout.order_lifecycle.pymysql.connect", return_value=fake_conn):
            result = asyncio_run(lifecycle.process_payout_order(
                {"code": "JZ001", "amount": "100.00", "retry_count": 0},
                selected_account=_selected_account(),
            ))

        self.assertTrue(result["success"])
        lifecycle.account_selector.deduct_account_balance_in_transaction.assert_called_once()
        lifecycle.settlement.handle_payout_success.assert_called_once()
        self.assertEqual(lifecycle.settlement.qr_id, "533302")
        lifecycle.redis.publish.assert_called_with("order_df_notify", "JZ001")

    def test_no_response_marks_claimed_order_unknown(self):
        lifecycle = _lifecycle()
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_jazzcash_transfer = AsyncMock(return_value=None)

        with patch("jobs.jazzcash.payout.order_lifecycle.is_auto_payout_enabled", return_value=True), \
             patch("jobs.jazzcash.payout.order_lifecycle.pymysql.connect", return_value=fake_conn):
            result = asyncio_run(lifecycle.process_payout_order(
                {"code": "JZ001", "amount": "100.00", "retry_count": 0},
                selected_account=_selected_account(),
            ))

        self.assertFalse(result["success"])
        self.assertTrue(result["unknown"])
        self.assertTrue(any("SET status = 2" in sql for sql, _ in fake_conn.cursor_obj.executed))

    def test_first_402_returns_order_to_retry_pool(self):
        lifecycle = _lifecycle()
        fake_conn = FakeConnection(claim_rowcount=1, retry_count=0)
        lifecycle.transfer_executor._execute_jazzcash_transfer = AsyncMock(return_value={
            "success": False,
            "code": 402,
            "message": "connection failed",
        })

        with patch("jobs.jazzcash.payout.order_lifecycle.is_auto_payout_enabled", return_value=True), \
             patch("jobs.jazzcash.payout.order_lifecycle.pymysql.connect", return_value=fake_conn):
            result = asyncio_run(lifecycle.process_payout_order(
                {"code": "JZ001", "amount": "100.00", "retry_count": 0},
                selected_account=_selected_account(),
            ))

        self.assertFalse(result["success"])
        self.assertTrue(result["retry"])
        self.assertEqual(result["retry_count"], 1)
        self.assertTrue(any("SET retry_count = %s, status = 0" in sql for sql, _ in fake_conn.cursor_obj.executed))

    def test_locks_are_released_after_processing(self):
        lifecycle = _lifecycle()
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_jazzcash_transfer = AsyncMock(return_value={
            "success": False,
            "code": 500,
            "message": "server error",
        })

        with patch("jobs.jazzcash.payout.order_lifecycle.is_auto_payout_enabled", return_value=True), \
             patch("jobs.jazzcash.payout.order_lifecycle.pymysql.connect", return_value=fake_conn):
            asyncio_run(lifecycle.process_payout_order(
                {"code": "JZ001", "amount": "100.00", "retry_count": 0},
                selected_account=_selected_account(),
            ))

        lifecycle.account_selector.del_lock.assert_called_with("JZ001", "order-lock")
        lifecycle.account_selector.release_account_lock.assert_called_with("03409297123", "account-lock")
        lifecycle.account_selector.del_payment_id_lock.assert_called_with("533302", "payment-lock")


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
