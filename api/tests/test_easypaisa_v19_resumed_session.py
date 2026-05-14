"""§3.3.1 残留 session 复用协议。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.ttl = AsyncMock(return_value=300)
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_resumed_otp_sent(ep):
    session = {'status': LoginStatus.OTP_SENT, 'phone': '03445021275', 'id': '533290'}
    result = await ep._build_resumed_session_response('pre_login_easypaisa_533290', session)
    assert result['status'] == 'success'
    assert result['data']['resumed'] is True
    assert result['data']['phase'] == LoginStatus.OTP_SENT
    assert result['data']['next_step'] == 'verify_otp'
    assert result['data']['expires_in'] == 300


@pytest.mark.asyncio
async def test_resumed_account_selection_includes_accounts(ep):
    session = {
        'status': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        'phone': '03445021275', 'id': '533290',
        'account_entire': json.dumps([{'accno': '88521642', 'accountStatus': 'ACTIVE'}]),
    }
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['resumed'] is True
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    assert result['data']['next_step'] == 'select_accts'
    assert 'accounts' in result['data']
    assert result['data']['accounts'] == [{'accno': '88521642', 'accountStatus': 'ACTIVE'}]


@pytest.mark.asyncio
async def test_resumed_awaiting_pin_change(ep):
    session = {'status': LoginStatus.AWAITING_PIN_CHANGE, 'phone': 'x', 'id': '1'}
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['next_step'] == 'change_pin'


@pytest.mark.asyncio
async def test_resumed_fingerprint_verified_returns_second_login(ep):
    session = {'status': LoginStatus.FINGERPRINT_VERIFIED, 'phone': 'x', 'id': '1'}
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['next_step'] == 'second_login'


@pytest.mark.asyncio
async def test_resumed_otp_verified(ep):
    session = {'status': LoginStatus.OTP_VERIFIED, 'phone': 'x', 'id': '1'}
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['next_step'] == 'upload_fingerprint'
