"""Unit tests for Settlement"""
import pytest
from unittest.mock import MagicMock, patch, call
from decimal import Decimal

from jobs.easypaisa.payout.settlement import Settlement


@pytest.fixture
def mock_deps():
    """Create mock dependencies for Settlement."""
    redis_client = MagicMock()
    logger = MagicMock()
    conf = {
        'mysql_host': 'localhost',
        'mysql_user': 'root',
        'mysql_password': 'pass',
        'mysql_database': 'testdb',
    }
    return redis_client, logger, conf


@pytest.fixture
def settlement(mock_deps):
    redis_client, logger, conf = mock_deps
    return Settlement(redis_client, logger, conf)


class TestFormatSql:
    def test_mogrify_bytes(self, settlement):
        cur = MagicMock()
        cur.mogrify.return_value = b"SELECT * FROM t WHERE id = 1"
        result = settlement._format_sql(cur, "SELECT * FROM t WHERE id = %s", (1,))
        assert result == "SELECT * FROM t WHERE id = 1"

    def test_mogrify_string(self, settlement):
        cur = MagicMock()
        cur.mogrify.return_value = "SELECT * FROM t WHERE id = 1"
        result = settlement._format_sql(cur, "SELECT * FROM t WHERE id = %s", (1,))
        assert result == "SELECT * FROM t WHERE id = 1"

    def test_fallback_last_executed(self, settlement):
        cur = MagicMock(spec=[])
        cur._last_executed = "SELECT * FROM t WHERE id = 1"
        result = settlement._format_sql(cur, "SELECT * FROM t WHERE id = %s", (1,))
        assert result == "SELECT * FROM t WHERE id = 1"

    def test_simple_replacement(self, settlement):
        cur = MagicMock(spec=[])
        cur._last_executed = None
        result = settlement._format_sql(cur, "SELECT * FROM t WHERE id = %s AND name = %s", (1, 'foo'))
        assert "1" in result
        assert "'foo'" in result

    def test_no_params(self, settlement):
        cur = MagicMock(spec=[])
        cur._last_executed = None
        result = settlement._format_sql(cur, "SELECT 1")
        assert result == "SELECT 1"

    def test_exception_returns_fallback(self, settlement):
        cur = MagicMock()
        cur.mogrify.side_effect = Exception("fail")
        result = settlement._format_sql(cur, "SELECT %s", (1,))
        assert "SELECT %s" in result


class TestGetCacheResult:
    def test_cache_hit(self, settlement, mock_deps):
        redis_client, logger, conf = mock_deps
        import simplejson
        cached = simplejson.dumps({'range_df': '{}', 'other': 'val'})
        redis_client.get.return_value = cached
        result = settlement.get_cache_result('sys_info', ['range_df'])
        assert result == {'range_df': '{}'}
        redis_client.get.assert_called_once_with('cache_info_sys_info_1')

    def test_cache_hit_all_keys(self, settlement, mock_deps):
        redis_client, logger, conf = mock_deps
        import simplejson
        cached = simplejson.dumps({'a': 1, 'b': 2})
        redis_client.get.return_value = cached
        result = settlement.get_cache_result('sys_info', ['*'])
        assert result == {'a': 1, 'b': 2}

    @patch('jobs.easypaisa.payout.settlement.pymysql')
    def test_cache_miss_queries_db(self, mock_pymysql, settlement, mock_deps):
        redis_client, logger, conf = mock_deps
        redis_client.get.return_value = None
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 1, 'range_df': '{"isOpen1":1}'}
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymysql.connect.return_value = mock_conn
        mock_pymysql.cursors.DictCursor = 'DictCursor'

        result = settlement.get_cache_result('sys_info', ['range_df'])
        assert result == {'range_df': '{"isOpen1":1}'}
        mock_pymysql.connect.assert_called_once()

    def test_exception_returns_empty(self, settlement, mock_deps):
        redis_client, logger, conf = mock_deps
        redis_client.get.side_effect = Exception("redis down")
        result = settlement.get_cache_result('sys_info', ['range_df'])
        assert result == {}


class TestChangeBalance:
    def test_success_merchant(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        # Step 1: select balance
        # Step 3: select balance after
        cur.execute.return_value = 1
        cur.fetchall.side_effect = [
            [{'balance': Decimal('1000')}],       # step 1
            [{'balance': Decimal('900')}],        # step 3
            [{'merchant_code': 'MC001'}],         # step 6
        ]
        result = settlement.change_balance(
            conn, cur, 'merchant', 1, Decimal('-100'), 'ORD001', 0,
            remark='test', merchant_code=None
        )
        assert result is True

    def test_balance_insufficient(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.return_value = 1
        cur.fetchall.side_effect = [
            [{'balance': Decimal('50')}],         # step 1
            [{'balance': Decimal('-10')}],        # step 3 (negative)
        ]
        result = settlement.change_balance(
            conn, cur, 'merchant', 1, Decimal('-60'), 'ORD001', 0
        )
        assert result is False

    def test_select_fails(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.return_value = 0  # first execute fails
        result = settlement.change_balance(
            conn, cur, 'merchant', 1, Decimal('100'), 'ORD001', 0
        )
        assert result is False

    def test_vip_upgrade_for_partner(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.return_value = 1
        cur.fetchall.side_effect = [
            [{'balance': Decimal('1000'), 'vip': 1}],   # step 1
            [{'balance': Decimal('2000'), 'vip': 1}],   # step 3
            # step 6 skipped because merchant_code is provided
            [{'vip': 1, 'conditions': Decimal('500')},   # step 8 vip configs
             {'vip': 2, 'conditions': Decimal('1500')},
             {'vip': 3, 'conditions': Decimal('5000')}],
        ]
        result = settlement.change_balance(
            conn, cur, 'partner', 1, Decimal('1000'), 'ORD001', 1,
            merchant_code='MC001'
        )
        assert result is True


class TestRejectOrderWithRefund:
    def test_success(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        cur.fetchall.return_value = [{'amount': Decimal('-100'), 'user_type': 1, 'user_id': 5}]
        cur.execute.return_value = 1
        cur.rowcount = 1

        order_data = {'code': 'ORD001', 'merchant_id': 5}
        with patch.object(settlement, 'change_balance', return_value=True):
            result = settlement.reject_order_with_refund(order_data, conn, 'API error', {'id': 1})
        assert result['reject'] is True
        assert result['success'] is False

    def test_refund_fails(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur
        cur.fetchall.return_value = [{'amount': Decimal('-100'), 'user_type': 1, 'user_id': 5}]
        cur.execute.return_value = 1

        order_data = {'code': 'ORD001', 'merchant_id': 5}
        with patch.object(settlement, 'change_balance', return_value=False):
            result = settlement.reject_order_with_refund(order_data, conn, 'API error', {'id': 1})
        assert result['reject'] is False
        assert result['success'] is False


class TestHandlePayoutSuccess:
    def test_success_updates_order_to_status_3_with_status_guard(self, settlement):
        conn = MagicMock()
        cur = MagicMock()
        cur.execute.return_value = 1
        cur.rowcount = 1
        settlement.qr_id = '533295'
        order_data = {
            'code': 'ORD001',
            'amount': Decimal('100.00'),
            'realpay': Decimal('100.00'),
            'merchant_id': 5,
            'partner_id': 9,
            'status': 1,
            'is_split': 0,
            'parent_id': None,
            'earn_merchant': Decimal('0'),
            'earn_partner_self': Decimal('0'),
        }
        result_data = {
            'transaction_id': 'TXN001',
            'payer_phone': '03325009516',
        }

        with patch.object(settlement, 'change_balance', return_value=True), \
             patch.object(settlement, 'get_cache_result', return_value={}):
            result = settlement.handle_payout_success(conn, cur, order_data, result_data)

        assert result is True
        executed_sql = [" ".join(call_args[0][0].split()) for call_args in cur.execute.call_args_list]
        assert any("SET earn_merchant=%s, status=3" in sql for sql in executed_sql)
        assert any("WHERE code=%s AND status=1" in sql for sql in executed_sql)
        settlement.redis.publish.assert_not_called()
