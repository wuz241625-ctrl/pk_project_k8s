"""U4 / U5 / U14 URM90040 fallback 测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import AsyncMock, MagicMock
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep():
    handler = MagicMock()
    handler.redis = AsyncMock()
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_u4_first_urm90040_triggers_fallback(ep):
    session = {'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep.redis.incr = AsyncMock(return_value=1)
    ep.redis.expire = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)
    result = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_OTP'
    assert session['status'] == LoginStatus.OTP_SENT
    assert session['fallback_from_urm90040'] is True


@pytest.mark.asyncio
async def test_u5_fourth_urm90040_forces_needs_relogin(ep):
    """U5: 1 小时内第 4 次 URM90040 直接 needsRelogin。"""
    session = {'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep.redis.incr = AsyncMock(return_value=4)  # INCR returns 4 > LIMIT=3 → reject
    ep.redis.expire = AsyncMock(return_value=True)
    result = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert session['status'] == LoginStatus.NEEDS_RELOGIN


@pytest.mark.asyncio
async def test_urm90040_atomic_concurrent_calls(ep):
    """Fix #3: 模拟 5 个并发请求 INCR 返回 1,2,3,4,5；前 3 通过，后 2 拒。"""
    ep.redis.incr = AsyncMock(side_effect=[1, 2, 3, 4, 5])
    ep.redis.expire = AsyncMock(return_value=True)
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)

    results = []
    for i in range(5):
        session = {
            'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
            'status': LoginStatus.PRE_LOGIN_CREATED,
            'status_history': [LoginStatus.PRE_LOGIN_CREATED],
        }
        r = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
        results.append(r)

    # 前 3 个：SL_NEEDS_OTP（fallback 生效）
    assert results[0]['data']['code'] == 'SL_NEEDS_OTP'
    assert results[1]['data']['code'] == 'SL_NEEDS_OTP'
    assert results[2]['data']['code'] == 'SL_NEEDS_OTP'
    # 第 4 / 第 5：SL_NEEDS_RELOGIN（限频拒）
    assert results[3]['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert results[4]['data']['code'] == 'SL_NEEDS_RELOGIN'


@pytest.mark.asyncio
async def test_urm90040_first_call_sets_expire(ep):
    """Fix #3: INCR 返回 1 时必须调 EXPIRE 设 TTL 3600，避免 key 永不过期。"""
    ep.redis.incr = AsyncMock(return_value=1)
    ep.redis.expire = AsyncMock(return_value=True)
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)

    session = {
        'id': 533290, 'phone': 'x', 'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED,
        'status_history': [LoginStatus.PRE_LOGIN_CREATED],
    }
    await ep._urm90040_fallback('k', session, 'URM90040')

    # 必须调用过 expire 且 TTL=3600
    ep.redis.expire.assert_called_with('easypaisa:urm90040_count:533290', 3600)
