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


@pytest.mark.asyncio
async def test_session_data_does_not_contain_password(ep_instance):
    """Fix #5: pre_login_http 完成后 session 不含明文 password 字段。"""
    import bcrypt

    # 准备 bcrypt 校验通过的 hash
    test_password = b'test_pwd_123'
    hashed = bcrypt.hashpw(test_password, bcrypt.gensalt()).decode()

    captured_sessions = []

    async def fake_persist(redis_key, session_data):
        captured_sessions.append(dict(session_data))
        return 999

    ep_instance._persist_session_data = fake_persist
    ep_instance._select_proxy_ip = AsyncMock(return_value='')
    ep_instance._check_login_failed_attempts = AsyncMock(return_value=False)
    ep_instance._check_payment = AsyncMock(return_value=None)  # 走"首次"分支
    ep_instance._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_instance._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_instance._get_session_data = AsyncMock(return_value=None)
    ep_instance._is_account_registered = AsyncMock(return_value=False)
    ep_instance.redis.get = AsyncMock(return_value=None)

    ep_instance.handler.current_user.id = 33057
    ep_instance.handler.current_user.hash_trade = hashed

    await ep_instance.pre_login_http({
        'bankname': 'easypaisa',
        'phone': '03130268536',
        'password': test_password.decode(),
        'pin': '12345',
        'name': 'Test',
        'step': 'complete_login',
    })

    # 必须至少调用过一次 _persist_session_data
    assert len(captured_sessions) > 0, '_persist_session_data 未被调用'
    # 任何一次 persist 的 session 都不该含 password 字段
    for s in captured_sessions:
        assert 'password' not in s, \
            f'session 不该含明文 password，但实际有: {str(s.get("password"))[:5]}***'
