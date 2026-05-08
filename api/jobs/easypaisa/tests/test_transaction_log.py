"""Unit tests for TransactionLogger"""
import pytest
from unittest.mock import MagicMock, patch

from jobs.easypaisa.payout.transaction_log import TransactionLogger


@pytest.fixture
def mock_deps():
    """Create mock dependencies for TransactionLogger."""
    redis_client = MagicMock()
    logger = MagicMock()
    trace_id_filter = MagicMock()
    trace_id_filter.trace_id = 'test-trace-123'
    conf = {
        'mysql_host': 'localhost',
        'mysql_user': 'root',
        'mysql_password': 'pass',
        'mysql_database': 'testdb',
    }
    return redis_client, logger, trace_id_filter, conf


class TestTransactionLoggerInit:
    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_init_table_exists(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('easypaisa_operation_logs',)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymysql.connect.return_value = mock_conn

        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)
        assert tl.operation_logs_enabled is True

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_init_table_not_exists(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_pymysql.connect.return_value = mock_conn

        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)
        assert tl.operation_logs_enabled is False

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_init_db_connection_error(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("Connection refused")

        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)
        assert tl.operation_logs_enabled is False


class TestIsPakistanMobileNumber:
    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_valid_international_format(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._is_pakistan_mobile_number('9230012345678') is True  # 13 digits with 92 prefix

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_valid_local_format(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._is_pakistan_mobile_number('03001234567') is True

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_invalid_number(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._is_pakistan_mobile_number('1234567890') is False

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_empty_string(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._is_pakistan_mobile_number('') is False

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_none(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._is_pakistan_mobile_number(None) is False


class TestGetBankNameByIfsc:
    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_known_bank_hbl(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._get_bank_name_by_ifsc('HBL12345') == 'Habib Bank Limited'

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_known_bank_easypaisa(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        # EASYPAISA[:4] = 'EASY', which doesn't match any key via startswith
        assert tl._get_bank_name_by_ifsc('EASYPAISA') == 'Bank (EASYPAISA)'

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_unknown_bank(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._get_bank_name_by_ifsc('XYZBANK') == 'Bank (XYZBANK)'

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_empty_ifsc(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._get_bank_name_by_ifsc('') is None

    @patch('jobs.easypaisa.payout.transaction_log.pymysql')
    def test_none_ifsc(self, mock_pymysql, mock_deps):
        redis_client, logger, trace_id_filter, conf = mock_deps
        mock_pymysql.connect.side_effect = Exception("skip")
        tl = TransactionLogger(redis_client, logger, trace_id_filter, conf)

        assert tl._get_bank_name_by_ifsc(None) is None
