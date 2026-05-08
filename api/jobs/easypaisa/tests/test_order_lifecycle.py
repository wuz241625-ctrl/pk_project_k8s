"""Unit tests for OrderLifecycle"""
import pytest
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from decimal import Decimal

from jobs.easypaisa.payout.order_lifecycle import OrderLifecycle


@pytest.fixture
def mock_deps():
    """Create mock dependencies for OrderLifecycle."""
    redis_client = MagicMock()
    logger = MagicMock()
    conf = {
        'mysql_host': 'localhost',
        'mysql_user': 'root',
        'mysql_password': 'pass',
        'mysql_database': 'testdb',
    }
    REDIS_KEYS = {
        'payment_id_failed_prefix': 'ep_failed_',
        'easypaisa_order_cooldown_hash': 'ep_order_cooldown',
        'easypaisa_order_cooldown_config': 'ep_cooldown_config',
    }
    account_selector = MagicMock()
    transfer_executor = MagicMock()
    settlement = MagicMock()
    transaction_logger = MagicMock()
    return redis_client, logger, conf, REDIS_KEYS, account_selector, transfer_executor, settlement, transaction_logger


@pytest.fixture
def lifecycle(mock_deps):
    redis_client, logger, conf, REDIS_KEYS, account_selector, transfer_executor, settlement, transaction_logger = mock_deps
    return OrderLifecycle(redis_client, logger, conf, REDIS_KEYS,
                          account_selector, transfer_executor, settlement, transaction_logger)


class TestIsOrderInCooldown:
    def test_not_in_cooldown_no_record(self, lifecycle):
        lifecycle.redis.hget.return_value = None
        assert lifecycle.is_order_in_cooldown('ORD001') is False

    def test_in_cooldown_active(self, lifecycle):
        info = {
            'expire_time': time.time() + 600,
            'reason': 'test failure',
        }
        lifecycle.redis.hget.return_value = json.dumps(info).encode()
        assert lifecycle.is_order_in_cooldown('ORD001') is True

    def test_cooldown_expired(self, lifecycle):
        info = {
            'expire_time': time.time() - 100,
            'reason': 'old failure',
            'status': 'active',
            'cooldown_level': 2,
        }
        lifecycle.redis.hget.return_value = json.dumps(info).encode()
        assert lifecycle.is_order_in_cooldown('ORD001') is False
        # Should mark as expired
        lifecycle.redis.hset.assert_called_once()

    def test_exception_returns_false(self, lifecycle):
        lifecycle.redis.hget.side_effect = Exception("Redis down")
        assert lifecycle.is_order_in_cooldown('ORD001') is False


class TestCalculateCooldownMinutes:
    def test_level1_default(self, lifecycle):
        lifecycle.redis.get.return_value = None
        assert lifecycle.calculate_cooldown_minutes(1) == 30

    def test_level2_default(self, lifecycle):
        lifecycle.redis.get.return_value = None
        assert lifecycle.calculate_cooldown_minutes(2) == 120

    def test_level4_default(self, lifecycle):
        lifecycle.redis.get.return_value = None
        assert lifecycle.calculate_cooldown_minutes(4) == 1440

    def test_level_beyond_default_uses_last(self, lifecycle):
        lifecycle.redis.get.return_value = None
        assert lifecycle.calculate_cooldown_minutes(10) == 1440

    def test_uses_redis_config(self, lifecycle):
        config = {
            'levels': [
                {'level': 1, 'minutes': 5},
                {'level': 2, 'minutes': 10},
                {'level': 3, 'minutes': 20},
            ]
        }
        lifecycle.redis.get.return_value = json.dumps(config).encode()
        assert lifecycle.calculate_cooldown_minutes(2) == 10

    def test_redis_config_beyond_max_uses_last(self, lifecycle):
        config = {
            'levels': [
                {'level': 1, 'minutes': 5},
                {'level': 2, 'minutes': 10},
            ]
        }
        lifecycle.redis.get.return_value = json.dumps(config).encode()
        assert lifecycle.calculate_cooldown_minutes(5) == 10


class TestFilterCooldownOrders:
    def test_empty_list(self, lifecycle):
        assert lifecycle.filter_cooldown_orders([]) == []

    def test_no_cooldown_orders_pass_through(self, lifecycle):
        orders = [{'code': 'ORD001'}, {'code': 'ORD002'}]
        pipe = MagicMock()
        pipe.execute.return_value = [None, None]
        lifecycle.redis.pipeline.return_value = pipe
        result = lifecycle.filter_cooldown_orders(orders)
        assert len(result) == 2

    def test_cooldown_order_filtered_out(self, lifecycle):
        orders = [{'code': 'ORD001'}, {'code': 'ORD002'}]
        active_info = json.dumps({
            'expire_time': time.time() + 600,
            'reason': 'failure',
            'cooldown_level': 1,
        }).encode()
        pipe = MagicMock()
        pipe.execute.return_value = [active_info, None]
        lifecycle.redis.pipeline.return_value = pipe
        result = lifecycle.filter_cooldown_orders(orders)
        assert len(result) == 1
        assert result[0]['code'] == 'ORD002'

    def test_max_retry_final_not_filtered(self, lifecycle):
        orders = [{'code': 'ORD001'}]
        info = json.dumps({
            'expire_time': time.time() + 600,
            'status': 'max_retry_final',
        }).encode()
        pipe = MagicMock()
        pipe.execute.return_value = [info]
        lifecycle.redis.pipeline.return_value = pipe
        result = lifecycle.filter_cooldown_orders(orders)
        assert len(result) == 1

    def test_exception_returns_original(self, lifecycle):
        orders = [{'code': 'ORD001'}]
        lifecycle.redis.pipeline.side_effect = Exception("Redis down")
        result = lifecycle.filter_cooldown_orders(orders)
        assert result == orders


class TestSetPaymentIdFailed:
    def test_sets_redis_key_with_20min_ttl(self, lifecycle):
        result = lifecycle.set_payment_id_failed('PID001', reason='test fail')
        assert result is True
        lifecycle.redis.setex.assert_called_once()
        args = lifecycle.redis.setex.call_args[0]
        assert args[0] == 'ep_failed_PID001'
        assert args[1] == 1200  # 20 minutes

    def test_includes_order_data(self, lifecycle):
        order_data = {
            'code': 'ORD001',
            'amount': Decimal('100.50'),
            'payment_account': '03001234567',
            'name': 'Test User',
            'bank_code': 'EP',
            'time_accept': '2024-01-01 12:00:00',
            'user_id': 1,
            'channel_id': 2,
        }
        result = lifecycle.set_payment_id_failed('PID001', order_data=order_data)
        assert result is True
        stored_json = lifecycle.redis.setex.call_args[0][2]
        stored = json.loads(stored_json)
        assert stored['order_code'] == 'ORD001'
        assert stored['amount'] == 100.50

    def test_exception_returns_false(self, lifecycle):
        lifecycle.redis.setex.side_effect = Exception("Redis down")
        result = lifecycle.set_payment_id_failed('PID001')
        assert result is False


class TestCheckPayoutRisk:
    @pytest.mark.asyncio
    @patch('jobs.easypaisa.payout.order_lifecycle.is_auto_payout_enabled', return_value=False)
    async def test_emergency_stop(self, _mock_enabled, lifecycle):
        result = await lifecycle.check_payout_risk({'amount': '100'})
        assert result['passed'] is False
        assert result['reason'] == 'emergency_stop'

    @pytest.mark.asyncio
    @patch('jobs.easypaisa.payout.order_lifecycle.is_auto_payout_enabled', return_value=True)
    async def test_amount_too_small(self, _mock_enabled, lifecycle):
        lifecycle.redis.get.return_value = None
        result = await lifecycle.check_payout_risk({'amount': '0.01'})
        assert result['passed'] is False
        assert result['reason'] == 'amount_too_small'

    @pytest.mark.asyncio
    @patch('jobs.easypaisa.payout.order_lifecycle.is_auto_payout_enabled', return_value=True)
    async def test_passes_normal(self, _mock_enabled, lifecycle):
        lifecycle.redis.get.return_value = None
        result = await lifecycle.check_payout_risk({'amount': '500'})
        assert result['passed'] is True


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
            self.rowcount = 1 if self.connection.order_row else 0
            self._fetchone = self.connection.order_row
            return self.rowcount
        if "SET retry_count = %s, status = 0" in normalized:
            self.rowcount = 1
            return 1
        if "SET status = 2" in normalized:
            self.rowcount = 1
            return 1
        if "SET retry_count = %s" in normalized and "WHERE code = %s" in normalized:
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
            'code': 'ORD001',
            'amount': Decimal('100.00'),
            'realpay': Decimal('100.00'),
            'merchant_id': 5,
            'partner_id': 9,
            'payment_id': '533295',
            'payment_account': '03001234567',
            'payment_name': 'Ali',
            'ifsc': 'easypaisa',
            'retry_count': retry_count,
            'status': 1,
            'is_split': 0,
            'parent_id': None,
            'earn_merchant': Decimal('0'),
            'earn_partner_self': Decimal('0'),
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
        'payment_id': '533295',
        'phone': '03325009516',
        'partner_id': 9,
        'account_accno': '68382729',
        'balance': Decimal('1000.00'),
    }


def _wire_locks(lifecycle):
    lifecycle.account_selector.get_lock.return_value = 'order-lock'
    lifecycle.account_selector.acquire_account_lock = AsyncMock(return_value='account-lock')
    lifecycle.account_selector.get_payment_id_lock.return_value = 'payment-lock'
    lifecycle.account_selector.del_lock.return_value = True
    lifecycle.account_selector.release_account_lock.return_value = True
    lifecycle.account_selector.del_payment_id_lock.return_value = True


class TestProcessPayoutOrderStateMachine:
    @pytest.mark.asyncio
    async def test_claim_failure_does_not_call_official_transfer(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=0)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock()

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            result = await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 0},
                selected_account=_selected_account(),
            )

        assert result['success'] is False
        assert result['claimed'] is False
        lifecycle.transfer_executor._execute_easypaisa_transfer.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_claims_order_and_calls_settlement(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock(return_value={
            'success': True,
            'transaction_id': 'TXN001',
            'payer_phone': '03325009516',
        })
        lifecycle.settlement.handle_payout_success.return_value = True

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            result = await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 0},
                selected_account=_selected_account(),
            )

        assert result['success'] is True
        lifecycle.settlement.handle_payout_success.assert_called_once()
        assert lifecycle.settlement.qr_id == '533295'
        lifecycle.redis.publish.assert_called_with('order_df_notify', 'ORD001')

    @pytest.mark.asyncio
    async def test_balance_deduction_failure_marks_unknown_and_skips_settlement(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock(return_value={
            'success': True,
            'transaction_id': 'TXN001',
            'payer_phone': '03325009516',
        })
        lifecycle.account_selector.update_account_balance_after_transfer.return_value = False

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            result = await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 0},
                selected_account=_selected_account(),
            )

        assert result['success'] is False
        assert result['unknown'] is True
        lifecycle.settlement.handle_payout_success.assert_not_called()
        assert any("SET status = 2" in sql for sql, _ in fake_conn.cursor_obj.executed)

    @pytest.mark.asyncio
    async def test_first_402_returns_order_to_retry_pool(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=1, retry_count=0)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock(return_value={
            'success': False,
            'code': 402,
            'message': 'connection failed',
        })

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            result = await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 0},
                selected_account=_selected_account(),
            )

        assert result['success'] is False
        assert result['retry'] is True
        assert result['retry_count'] == 1
        assert any("SET retry_count = %s, status = 0" in sql for sql, _ in fake_conn.cursor_obj.executed)
        lifecycle.redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_third_402_rejects_order(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=1, retry_count=2)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock(return_value={
            'success': False,
            'code': 402,
            'message': 'connection failed',
        })
        lifecycle.settlement.reject_order_with_refund.return_value = {'success': False, 'reject': True}

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            result = await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 2},
                selected_account=_selected_account(),
            )

        assert result['success'] is False
        assert result['reject'] is True
        lifecycle.settlement.reject_order_with_refund.assert_called_once()
        lifecycle.redis.publish.assert_called_with('order_df_notify', 'ORD001')

    @pytest.mark.asyncio
    async def test_500_marks_order_unknown_manual_review(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock(return_value={
            'success': False,
            'code': 500,
            'message': 'server error',
        })

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            result = await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 0},
                selected_account=_selected_account(),
            )

        assert result['success'] is False
        assert result['unknown'] is True
        assert any("SET status = 2" in sql for sql, _ in fake_conn.cursor_obj.executed)
        lifecycle.redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_locks_are_released_after_processing(self, lifecycle):
        _wire_locks(lifecycle)
        fake_conn = FakeConnection(claim_rowcount=1)
        lifecycle.transfer_executor._execute_easypaisa_transfer = AsyncMock(return_value={
            'success': False,
            'code': 500,
            'message': 'server error',
        })

        with patch('jobs.easypaisa.payout.order_lifecycle.pymysql.connect', return_value=fake_conn):
            await lifecycle.process_payout_order(
                {'code': 'ORD001', 'amount': '100.00', 'retry_count': 0},
                selected_account=_selected_account(),
            )

        lifecycle.account_selector.del_lock.assert_called_with('ORD001', 'order-lock')
        lifecycle.account_selector.release_account_lock.assert_called_with('03325009516', 'account-lock')
        lifecycle.account_selector.del_payment_id_lock.assert_called_with('533295', 'payment-lock')
