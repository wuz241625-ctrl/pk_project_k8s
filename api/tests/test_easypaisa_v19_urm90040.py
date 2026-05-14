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
    ep.redis.get = AsyncMock(return_value=None)
    ep.redis.setex = AsyncMock(return_value=True)
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
    ep.redis.get = AsyncMock(return_value=b'3')
    ep.redis.setex = AsyncMock(return_value=True)
    ep.redis.expire = AsyncMock(return_value=True)
    result = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert session['status'] == LoginStatus.NEEDS_RELOGIN
