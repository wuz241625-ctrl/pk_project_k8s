"""验证 _force_terminal_needs_relogin 的统一终止行为。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_instance():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.set = AsyncMock(return_value=True)
    handler.redis.setex = AsyncMock(return_value=True)
    handler.redis.expire = AsyncMock(return_value=True)
    ep = EasyPaisa(handler)
    return ep


@pytest.mark.asyncio
async def test_force_terminal_writes_status(ep_instance):
    redis_key = "pre_login_easypaisa_533290"
    session = {
        'phone': '03445021275',
        'id': '533290',
        'bankname': 'easypaisa',
        'status': LoginStatus.FINGERPRINT_VERIFIED,
        'status_history': [LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_SENT,
                           LoginStatus.OTP_VERIFIED, LoginStatus.FINGERPRINT_VERIFIED],
    }
    result = await ep_instance._force_terminal_needs_relogin(
        redis_key=redis_key,
        session_data=session,
        reason='Test forced terminal',
        error_code='SL_NEEDS_RELOGIN',
    )
    assert session['status'] == LoginStatus.NEEDS_RELOGIN
    assert LoginStatus.NEEDS_RELOGIN in session['status_history']
    assert session['last_error']['code'] == 'SL_NEEDS_RELOGIN'
    assert session['last_error']['reason'] == 'Test forced terminal'


@pytest.mark.asyncio
async def test_force_terminal_returns_standard_envelope(ep_instance):
    session = {'phone': 'x', 'id': '1', 'bankname': 'easypaisa', 'status': LoginStatus.OTP_SENT, 'status_history': []}
    result = await ep_instance._force_terminal_needs_relogin(
        redis_key='k', session_data=session,
        reason='r', error_code='SL_NEEDS_RELOGIN', message='custom msg',
    )
    assert result['status'] == 'error'
    assert result['message'] == 'custom msg'
    assert result['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert result['data']['phase'] == LoginStatus.NEEDS_RELOGIN


@pytest.mark.asyncio
async def test_force_terminal_schedules_delayed_delete(ep_instance):
    """5 秒后删 key 让 APP 能拉 last_error。"""
    session = {'phone': 'x', 'id': '1', 'bankname': 'easypaisa', 'status': LoginStatus.OTP_VERIFIED, 'status_history': []}
    await ep_instance._force_terminal_needs_relogin(
        redis_key='pre_login_easypaisa_1', session_data=session,
        reason='r', error_code='SL_NEEDS_RELOGIN',
    )
    # expire 应该被调用过，TTL 设为 5
    ep_instance.redis.expire.assert_called_with('pre_login_easypaisa_1', 5)


@pytest.mark.asyncio
async def test_force_terminal_rejects_already_active(ep_instance):
    """已是 ACTIVE_SUCCESSFUL 时禁止跳到 NEEDS_RELOGIN（邻接表禁止）。"""
    session = {'phone': 'x', 'id': '1', 'bankname': 'easypaisa',
               'status': LoginStatus.ACTIVE_SUCCESSFUL, 'status_history': []}
    with pytest.raises(Exception) as exc:
        await ep_instance._force_terminal_needs_relogin(
            redis_key='k', session_data=session,
            reason='r', error_code='SL_NEEDS_RELOGIN',
        )
    assert 'INVALID_TRANSITION' in str(exc.value) or 'ACTIVE_SUCCESSFUL' in str(exc.value)
