"""Unit tests for TransferExecutor module."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from jobs.easypaisa.payout.transfer_executor import TransferExecutor


@pytest.fixture
def redis_mock():
    return MagicMock()


@pytest.fixture
def logger_mock():
    return MagicMock()


@pytest.fixture
def conf():
    return {
        'mysql_host': 'localhost',
        'mysql_user': 'root',
        'mysql_password': 'test',
        'mysql_database': 'testdb',
    }


@pytest.fixture
def redis_keys():
    return {}


@pytest.fixture
def transaction_logger_mock():
    mock = MagicMock()
    mock.log_complete_transaction = MagicMock()
    return mock


@pytest.fixture
def account_selector_mock():
    mock = MagicMock()
    mock.fetch_balance_from_api = AsyncMock(return_value={'success': True, 'balance': Decimal('10000')})
    mock.update_account_balance_after_transfer = MagicMock()
    return mock


@pytest.fixture
def executor(redis_mock, logger_mock, conf, redis_keys, transaction_logger_mock, account_selector_mock):
    return TransferExecutor(
        redis_client=redis_mock,
        logger=logger_mock,
        conf=conf,
        REDIS_KEYS=redis_keys,
        api_url='https://api.easypaisa.test/v1',
        user_id='test_user',
        secret_key='test_secret',
        transaction_logger=transaction_logger_mock,
        account_selector=account_selector_mock,
    )


# ========== _extract_transaction_id tests ==========

class TestExtractTransactionId:
    """Test _extract_transaction_id with various response formats."""

    def test_extract_from_ext_order_no(self, executor):
        """Primary path: data.body.data.extOrderNo"""
        api_result = {
            'code': 200,
            'data': {
                'body': {
                    'data': {
                        'extOrderNo': 'TXN123456789'
                    }
                }
            }
        }
        result = executor._extract_transaction_id(api_result, 'transferToAcc')
        assert result == 'TXN123456789'

    def test_extract_from_order_no(self, executor):
        """Fallback path 1: data.body.orderNo"""
        api_result = {
            'code': 200,
            'data': {
                'body': {
                    'orderNo': 'ORD987654321',
                    'data': {}
                }
            }
        }
        result = executor._extract_transaction_id(api_result, 'transferToAcc')
        assert result == 'ORD987654321'

    def test_extract_from_bus_order_no(self, executor):
        """Fallback path 2: data.body.busOrderNo"""
        api_result = {
            'code': 200,
            'data': {
                'body': {
                    'busOrderNo': 'BUS111222333',
                    'data': {}
                }
            }
        }
        result = executor._extract_transaction_id(api_result, 'transferToCard')
        assert result == 'BUS111222333'

    def test_missing_transaction_id_returns_empty_string(self, executor):
        """没有官方交易号时不能生成本地假 UTR。"""
        api_result = {
            'code': 200,
            'data': {
                'body': {
                    'data': {}
                }
            }
        }
        result = executor._extract_transaction_id(api_result, 'transferToAcc')
        assert result == ''

    def test_empty_data_returns_empty_string(self, executor):
        """Empty data dict returns no transaction ID."""
        api_result = {'code': 200, 'data': {}}
        result = executor._extract_transaction_id(api_result, 'transferToAcc')
        assert result == ''

    def test_exception_returns_empty_string(self, executor):
        """Exception during extraction returns no transaction ID."""
        api_result = {'code': 200, 'data': None}  # Will cause AttributeError
        result = executor._extract_transaction_id(api_result, 'transferToAcc')
        assert result == ''


# ========== _is_pakistan_mobile_number tests ==========

class TestIsPakistanMobileNumber:
    """Test Pakistan mobile number detection."""

    def test_valid_pakistan_mobile(self, executor):
        assert executor._is_pakistan_mobile_number('03001234567') is True

    def test_valid_with_non_digit_chars(self, executor):
        assert executor._is_pakistan_mobile_number('0300-1234567') is True

    def test_bank_account_number(self, executor):
        assert executor._is_pakistan_mobile_number('1234567890123456') is False

    def test_empty_string(self, executor):
        assert executor._is_pakistan_mobile_number('') is False

    def test_none(self, executor):
        assert executor._is_pakistan_mobile_number(None) is False

    def test_short_number(self, executor):
        assert executor._is_pakistan_mobile_number('0300123') is False


# ========== _execute_easypaisa_transfer tests ==========

class TestExecuteEasypaisaTransfer:
    """Test the main transfer execution flow."""

    @pytest.mark.asyncio
    async def test_successful_transfer_same_bank(self, executor):
        """Test successful EasyPaisa same-bank transfer (code=200, orderStatus=S)."""
        order_data = {
            'code': 'ORD001',
            'amount': 1000,
            'payment_account': '03001234567',
            'payment_name': 'Test User',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY001',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        # Mock _call_easypaisa_api to return success
        executor._call_easypaisa_api = AsyncMock(return_value={
            'code': 200,
            'msg': 'Success',
            'data': {
                'body': {
                    'orderStatus': 'S',
                    'data': {
                        'extOrderNo': 'TXN_SUCCESS_001'
                    }
                }
            }
        })

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is True
        assert result['transaction_id'] == 'TXN_SUCCESS_001'
        assert result['payer_phone'] == '03009876543'

    @pytest.mark.asyncio
    async def test_transfer_pending_status(self, executor):
        """Test transfer with orderStatus=P returns pending marker."""
        order_data = {
            'code': 'ORD002',
            'amount': 500,
            'payment_account': '03001234567',
            'payment_name': 'Test',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY002',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        executor._call_easypaisa_api = AsyncMock(return_value={
            'code': 200,
            'msg': 'Pending',
            'data': {
                'body': {
                    'orderStatus': 'P',
                    'data': {'extOrderNo': 'TXN_PENDING'}
                }
            }
        })

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert result['order_status'] == 'P'

    @pytest.mark.asyncio
    async def test_success_status_without_transaction_id_is_not_success(self, executor):
        """官方返回 S 但缺少官方交易号时进入人工确认，不写假 UTR。"""
        order_data = {
            'code': 'ORD001_NO_TXN',
            'amount': 1000,
            'payment_account': '03001234567',
            'payment_name': 'Test User',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY001',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        executor._call_easypaisa_api = AsyncMock(return_value={
            'code': 200,
            'msg': 'Success',
            'data': {
                'body': {
                    'orderStatus': 'S',
                    'data': {}
                }
            }
        })

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert result['code'] == 200
        assert result['order_status'] == 'S'
        assert result['can_retry'] is False

    @pytest.mark.asyncio
    async def test_code_200_unknown_order_status_is_not_success(self, executor):
        """code=200 但 orderStatus 不是明确 S 时不能按成功结算。"""
        order_data = {
            'code': 'ORD002X',
            'amount': 500,
            'payment_account': '03001234567',
            'payment_name': 'Test',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY002X',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        executor._call_easypaisa_api = AsyncMock(return_value={
            'code': 200,
            'msg': 'Unknown state',
            'data': {
                'body': {
                    'data': {'extOrderNo': 'TXN_UNKNOWN'}
                }
            }
        })

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert result['code'] == 200
        assert result['order_status'] is None
        assert result['can_retry'] is False

    @pytest.mark.asyncio
    async def test_transfer_402_returns_retryable_failure_without_msgcd_branch(self, executor):
        """所有 code=402 都是通用可重试失败，msgCd 只记录不分支。"""
        order_data = {
            'code': 'ORD003',
            'amount': 2000,
            'payment_account': '03001234567',
            'payment_name': 'Test',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY003',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        executor._call_easypaisa_api = AsyncMock(return_value={
            'code': 402,
            'msg': 'Account blocked',
            'data': {'msgCd': 'ANY_402_CODE'}
        })

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert result['code'] == 402
        assert 'reject' not in result

    @pytest.mark.asyncio
    async def test_transfer_501_account_invalid(self, executor):
        """Test code=501 returns account_invalid marker."""
        order_data = {
            'code': 'ORD004',
            'amount': 1000,
            'payment_account': '03001234567',
            'payment_name': 'Test',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY004',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        executor._call_easypaisa_api = AsyncMock(return_value={
            'code': 501,
            'msg': 'Account invalid',
            'data': {}
        })

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert result['account_invalid'] is True

    @pytest.mark.asyncio
    async def test_transfer_no_response(self, executor):
        """Test API returning None (network error)."""
        order_data = {
            'code': 'ORD005',
            'amount': 1000,
            'payment_account': '03001234567',
            'payment_name': 'Test',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY005',
            'phone': '03009876543',
            'account_accno': 'ACC123',
        }

        executor._call_easypaisa_api = AsyncMock(return_value=None)

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert result['code'] == -1

    @pytest.mark.asyncio
    async def test_missing_account_accno_fails(self, executor):
        """Test that missing account_accno returns failure."""
        order_data = {
            'code': 'ORD006',
            'amount': 1000,
            'payment_account': '03001234567',
            'payment_name': 'Test',
            'ifsc': 'easypaisa',
        }
        account_info = {
            'payment_id': 'PAY006',
            'phone': '03009876543',
            # No account_accno
        }

        result = await executor._execute_easypaisa_transfer(order_data, account_info)

        assert result is not None
        assert result['success'] is False
        assert 'account_accno' in result['message']
