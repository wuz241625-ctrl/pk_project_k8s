"""Unit tests for AccountSelector module."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from jobs.easypaisa.payout.account_selector import AccountSelector


@pytest.fixture
def redis_mock():
    return MagicMock()


@pytest.fixture
def logger_mock():
    return MagicMock()


@pytest.fixture
def redis_keys():
    return {
        'easypaisa_account_lock_prefix': 'easypaisa_account_lock:',
        'easypaisa_release_time': 'easypaisa_release_time',
        'easypaisa_failures': 'easypaisa_failures',
        'easypaisa_account_used_prefix': 'easypaisa_account_used:',
        'payment_id_lock_prefix': 'easypaisa_payment_id_lock:',
        'payment_id_failed_prefix': 'easypaisa_payment_id_failed:',
        'grab_df_prefix': 'grab_df:',
    }


@pytest.fixture
def conf():
    return {
        'mysql_host': 'localhost',
        'mysql_user': 'root',
        'mysql_password': 'test',
        'mysql_database': 'testdb',
    }


@pytest.fixture
def selector(redis_mock, logger_mock, conf, redis_keys):
    return AccountSelector(
        redis_client=redis_mock,
        logger=logger_mock,
        conf=conf,
        REDIS_KEYS=redis_keys,
        api_url='http://test.api/endpoint',
        user_id='test_user',
        secret_key='test_secret',
    )


# ========== _is_pakistan_mobile_number tests ==========

class TestIsPakistanMobileNumber:
    def test_valid_mobile_03_prefix_11_digits(self, selector):
        assert selector._is_pakistan_mobile_number('03001234567') is True

    def test_valid_mobile_with_non_digit_chars(self, selector):
        assert selector._is_pakistan_mobile_number('030-0123-4567') is True

    def test_invalid_wrong_prefix(self, selector):
        assert selector._is_pakistan_mobile_number('05001234567') is False

    def test_invalid_too_short(self, selector):
        assert selector._is_pakistan_mobile_number('0300123456') is False

    def test_invalid_too_long(self, selector):
        assert selector._is_pakistan_mobile_number('030012345678') is False

    def test_empty_string(self, selector):
        assert selector._is_pakistan_mobile_number('') is False

    def test_none_value(self, selector):
        assert selector._is_pakistan_mobile_number(None) is False

    def test_bank_account_number(self, selector):
        assert selector._is_pakistan_mobile_number('1234567890123456') is False


# ========== check_account_release_time tests ==========

class TestCheckAccountReleaseTime:
    def test_no_release_time_set(self, selector, redis_mock):
        redis_mock.hget.return_value = None
        assert selector.check_account_release_time('acc_001') is True

    def test_release_time_in_future(self, selector, redis_mock):
        future_time = (datetime.now() + timedelta(minutes=5)).isoformat()
        redis_mock.hget.return_value = future_time.encode()
        assert selector.check_account_release_time('acc_001') is False

    def test_release_time_in_past(self, selector, redis_mock):
        past_time = (datetime.now() - timedelta(minutes=5)).isoformat()
        redis_mock.hget.return_value = past_time.encode()
        assert selector.check_account_release_time('acc_001') is True

    def test_exception_returns_true(self, selector, redis_mock):
        redis_mock.hget.side_effect = Exception("Redis error")
        assert selector.check_account_release_time('acc_001') is True


# ========== acquire/release_account_lock tests ==========

class TestAccountLock:
    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, selector, redis_mock):
        redis_mock.set.return_value = True
        result = await selector.acquire_account_lock('acc_001', 'ORD_001')
        assert result is not None
        assert 'ORD_001' in result
        redis_mock.set.assert_called_once()
        assert redis_mock.set.call_args.kwargs == {'nx': True, 'ex': 300}
        redis_mock.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, selector, redis_mock):
        redis_mock.set.return_value = False
        result = await selector.acquire_account_lock('acc_001', 'ORD_001')
        assert result is None

    def test_release_lock_matching_value(self, selector, redis_mock):
        selector.release_account_lock('acc_001', 'ORD_001_abc123')
        redis_mock.eval.assert_called_once()

    def test_release_lock_mismatched_value(self, selector, redis_mock):
        selector.release_account_lock('acc_001', 'ORD_001_abc123')
        redis_mock.delete.assert_not_called()


# ========== check_account_amount_limits tests ==========

class TestCheckAccountAmountLimits:
    @pytest.mark.asyncio
    async def test_amount_within_limits(self, selector):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {'amount_top': 100000, 'balance_limit': 50000},
            {'today_count': 5, 'today_amount': Decimal('20000')},
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        selector.db_provider = lambda: mock_conn

        result = await selector.check_account_amount_limits('pay_001', Decimal('5000'))
        assert result['passed'] is True

    @pytest.mark.asyncio
    async def test_balance_limit_exceeded(self, selector):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {'amount_top': 0, 'balance_limit': 3000},
            {'today_count': 1, 'today_amount': Decimal('1000')},
        ]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        selector.db_provider = lambda: mock_conn

        result = await selector.check_account_amount_limits('pay_001', Decimal('5000'))
        assert result['passed'] is False
        assert result['reason'] == 'balance_limit_exceeded'

    @pytest.mark.asyncio
    async def test_exception_returns_passed(self, selector):
        selector.db_provider = MagicMock(side_effect=Exception("DB error"))
        result = await selector.check_account_amount_limits('pay_001', Decimal('5000'))
        assert result['passed'] is True


# ========== update_account_balance_after_transfer tests ==========

class TestUpdateAccountBalance:
    def test_successful_deduction(self, selector, redis_mock):
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = 1
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        selector.db_provider = lambda: mock_conn

        result = selector.update_account_balance_after_transfer('pay_001', Decimal('5000'))

        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        redis_mock.zincrby.assert_not_called()

    def test_no_payment_row_returns_false(self, selector, redis_mock):
        mock_cursor = MagicMock()
        mock_cursor.execute.return_value = 0
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        selector.db_provider = lambda: mock_conn

        result = selector.update_account_balance_after_transfer('pay_001', Decimal('5000'))

        assert result is False
        mock_conn.commit.assert_called_once()
        redis_mock.zadd.assert_not_called()


# ========== get_payment_id_lock tests ==========

class TestPaymentIdLock:
    def test_get_lock_success(self, selector, redis_mock):
        redis_mock.set.return_value = True
        result = selector.get_payment_id_lock('pay_001')
        assert result is not False
        redis_mock.set.assert_called_once()
        assert redis_mock.set.call_args.kwargs == {'nx': True, 'ex': 300}
        redis_mock.expire.assert_not_called()

    def test_get_lock_already_locked(self, selector, redis_mock):
        redis_mock.set.return_value = False
        redis_mock.ttl.return_value = 200
        result = selector.get_payment_id_lock('pay_001')
        assert result is False

    def test_get_lock_invalid_payment_id(self, selector, redis_mock):
        result = selector.get_payment_id_lock(None)
        assert result is False

    def test_del_lock_matching(self, selector, redis_mock):
        result = selector.del_payment_id_lock('pay_001', 'abc123')
        assert result is True
        redis_mock.eval.assert_called_once()


class TestOrderLock:
    def test_get_order_lock_uses_atomic_set(self, selector, redis_mock):
        redis_mock.set.return_value = True

        result = selector.get_lock('ORD_001')

        assert result is not False
        redis_mock.set.assert_called_once()
        assert redis_mock.set.call_args.kwargs == {'nx': True, 'ex': selector.lock_time}
        redis_mock.expire.assert_not_called()

    def test_del_order_lock_uses_compare_and_delete_lua(self, selector, redis_mock):
        result = selector.del_lock('ORD_001', 'lock-value')

        assert result is True
        redis_mock.eval.assert_called_once()


class TestDispatchOrdersToAccounts:
    def test_dispatch_assigns_only_one_order_per_account(self, selector):
        accounts = [{
            'payment_id': 'pay_001',
            'balance': Decimal('10000'),
            'balance_limit': Decimal('0'),
            'amount_top': Decimal('0'),
        }]
        orders = [
            {'code': 'ORD_BIG', 'amount': Decimal('5000')},
            {'code': 'ORD_SMALL', 'amount': Decimal('100')},
        ]

        result = selector.dispatch_orders_to_accounts(orders, accounts)

        assert len(result) == 1
        assert len(result[0][1]) == 1
        assert result[0][1][0]['code'] == 'ORD_BIG'

    def test_dispatch_checks_actual_order_amount_against_balance_limit(self, selector):
        accounts = [{
            'payment_id': 'pay_001',
            'balance': Decimal('10000'),
            'balance_limit': Decimal('1000'),
            'amount_top': Decimal('0'),
        }]
        orders = [{'code': 'ORD_TOO_LARGE', 'amount': Decimal('5000')}]

        result = selector.dispatch_orders_to_accounts(orders, accounts)

        assert result == []
