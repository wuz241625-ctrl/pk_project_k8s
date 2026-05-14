"""hotfix-2 P0: change_pin_http 内部续推 secondLogin(with_pwd) + queryAccountList。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_pin():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.set = AsyncMock(return_value=True)
    handler.redis.setex = AsyncMock(return_value=True)
    handler.redis.expire = AsyncMock(return_value=True)
    handler.redis.delete = AsyncMock(return_value=True)
    handler.current_user = MagicMock()
    handler.current_user.id = 33057
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_change_pin_chains_secondlogin_with_pwd_to_account_selection(ep_pin):
    """hotfix-2 P0: change_pin 成功后内部续推 secondLogin(with_pwd=True) + queryAccountList → ACCOUNT_SELECTION_REQUIRED。"""
    session = {
        'id': 533302, 'phone': '03194834960', 'bankname': 'easypaisa',
        'status': LoginStatus.AWAITING_PIN_CHANGE,
        'status_history': [LoginStatus.AWAITING_PIN_CHANGE],
        'pinCode': '11223',
        'pin_times': 0,
    }
    ep_pin._resolve_session_context = AsyncMock(return_value={
        'session_data': session,
        'redis_key': 'pre_login_easypaisa_533302',
        'resolved_payment_id': 533302,
    })
    ep_pin._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_pin._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_pin._change_pin = AsyncMock()
    ep_pin._save_payment = AsyncMock(return_value=533302)
    ep_pin._update_session_status = AsyncMock()
    ep_pin._persist_session_data = AsyncMock(return_value=533302)
    ep_pin._call_second_login = AsyncMock(return_value={'outcome': 'success'})
    ep_pin._call_query_account_list = AsyncMock(return_value={
        'outcome': 'success',
        'accounts_json': json.dumps([{'accno': '96699538', 'accountStatus': 'ACTIVE'}]),
    })

    result = await ep_pin.change_pin_http({
        'bankname': 'easypaisa',
        'payment_id': '533302',
        'pin': '99988',
    })

    # 续推结果：直接到 ACCOUNT_SELECTION_REQUIRED + next_step='select_accts'
    assert result['status'] == 'success'
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    assert result['data']['next_step'] == 'select_accts'
    assert result['data']['id'] == 533302
    # _change_pin 被调用一次（新 PIN）
    ep_pin._change_pin.assert_awaited_once()
    # secondLogin 调一次 + with_pwd=True
    ep_pin._call_second_login.assert_awaited_once()
    args, kwargs = ep_pin._call_second_login.await_args
    assert kwargs.get('with_pwd') is True, 'change_pin 续推必须 with_pwd=True'
    # queryAccountList 调一次
    ep_pin._call_query_account_list.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_pin_secondlogin_failure_returns_needs_relogin(ep_pin):
    """hotfix-2 P0: change_pin 后续推 secondLogin 失败 → NEEDS_RELOGIN（不抛 PIN_CHANGE_REJECTED）。"""
    session = {
        'id': 533302, 'phone': '03194834960', 'bankname': 'easypaisa',
        'status': LoginStatus.AWAITING_PIN_CHANGE,
        'status_history': [LoginStatus.AWAITING_PIN_CHANGE],
        'pinCode': '11223',
        'pin_times': 0,
    }
    ep_pin._resolve_session_context = AsyncMock(return_value={
        'session_data': session,
        'redis_key': 'pre_login_easypaisa_533302',
        'resolved_payment_id': 533302,
    })
    ep_pin._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_pin._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_pin._change_pin = AsyncMock()
    ep_pin._save_payment = AsyncMock(return_value=533302)
    ep_pin._update_session_status = AsyncMock()
    ep_pin._persist_session_data = AsyncMock(return_value=533302)
    # secondLogin 失败
    ep_pin._call_second_login = AsyncMock(return_value={
        'outcome': 'upstream_error', 'message': 'cloud error',
    })

    result = await ep_pin.change_pin_http({
        'bankname': 'easypaisa',
        'payment_id': '533302',
        'pin': '99988',
    })

    assert result['status'] == 'error'
    assert result['data']['code'] in ('SL_UPSTREAM_ERROR', 'SL_NEEDS_RELOGIN')
