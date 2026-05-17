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
async def test_u4_first_urm90040_triggers_fallback(ep, tmp_path):
    zip_path = tmp_path / "ep_533290.zip"
    zip_path.write_bytes(b'confirmed fp')
    session = {'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep.redis.incr = AsyncMock(return_value=1)
    ep.redis.expire = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)
    result = await ep._urm90040_fallback(
        'pre_login_easypaisa_533290', session, 'URM90040', fingerprint_path=str(zip_path)
    )
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_OTP'
    assert session['status'] == LoginStatus.OTP_SENT
    assert session['fallback_from_urm90040'] is True


@pytest.mark.asyncio
async def test_urm90040_login_step1_direct_success_continues_fallback_chain(ep, tmp_path):
    """v2.2: URM90040 fallback 的 loginStep1 若直接成功，不再要求用户输入 OTP。"""
    zip_path = tmp_path / "ep_533290.zip"
    zip_path.write_bytes(b'confirmed fp')
    session = {
        'id': 533290,
        'phone': '03445021275',
        'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED,
        'status_history': [LoginStatus.PRE_LOGIN_CREATED],
        'partner_id': 33057,
        'pinCode': '11223',
        'name': 'Fallback Direct',
    }
    ep.redis.incr = AsyncMock(return_value=1)
    ep.redis.expire = AsyncMock(return_value=True)
    ep.redis.delete = AsyncMock(return_value=True)
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={
        'status': 'success',
        'message': 'loginStep1成功',
        'direct_login': True,
    })
    ep._save_payment = AsyncMock(return_value=533290)
    ep._verify_otp_fallback_chain = AsyncMock(return_value={
        'status': 'success',
        'message': 'fallback 续推成功',
        'data': {
            'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
            'next_step': 'select_accts',
            'id': 533290,
        },
    })

    result = await ep._urm90040_fallback(
        'pre_login_easypaisa_533290', session, 'URM90040', fingerprint_path=str(zip_path)
    )

    assert result['status'] == 'success'
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    assert session['fallback_from_urm90040'] is True
    assert session['status'] == LoginStatus.OTP_VERIFIED
    ep._verify_otp_fallback_chain.assert_awaited_once()


@pytest.mark.asyncio
async def test_u5_fourth_urm90040_forces_needs_relogin(ep, tmp_path):
    """U5: 1 小时内第 4 次 URM90040 直接 needsRelogin。"""
    zip_path = tmp_path / "ep_533290.zip"
    zip_path.write_bytes(b'confirmed fp')
    session = {'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep.redis.incr = AsyncMock(return_value=4)  # INCR returns 4 > LIMIT=3 → reject
    ep.redis.expire = AsyncMock(return_value=True)
    result = await ep._urm90040_fallback(
        'pre_login_easypaisa_533290', session, 'URM90040', fingerprint_path=str(zip_path)
    )
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert session['status'] == LoginStatus.NEEDS_RELOGIN


@pytest.mark.asyncio
async def test_urm90040_atomic_concurrent_calls(ep, tmp_path):
    """Fix #3: 模拟 5 个并发请求 INCR 返回 1,2,3,4,5；前 3 通过，后 2 拒。"""
    zip_path = tmp_path / "ep_533290.zip"
    zip_path.write_bytes(b'confirmed fp')
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
        r = await ep._urm90040_fallback(
            'pre_login_easypaisa_533290', session, 'URM90040', fingerprint_path=str(zip_path)
        )
        results.append(r)

    # 前 3 个：SL_NEEDS_OTP（fallback 生效）
    assert results[0]['data']['code'] == 'SL_NEEDS_OTP'
    assert results[1]['data']['code'] == 'SL_NEEDS_OTP'
    assert results[2]['data']['code'] == 'SL_NEEDS_OTP'
    # 第 4 / 第 5：SL_NEEDS_RELOGIN（限频拒）
    assert results[3]['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert results[4]['data']['code'] == 'SL_NEEDS_RELOGIN'


@pytest.mark.asyncio
async def test_urm90040_first_call_sets_expire(ep, tmp_path):
    """Fix #3: INCR 返回 1 时必须调 EXPIRE 设 TTL 3600，避免 key 永不过期。"""
    zip_path = tmp_path / "ep_533290.zip"
    zip_path.write_bytes(b'confirmed fp')
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
    await ep._urm90040_fallback('k', session, 'URM90040', fingerprint_path=str(zip_path))

    # 必须调用过 expire 且 TTL=3600
    ep.redis.expire.assert_called_with('easypaisa:urm90040_count:533290', 3600)


@pytest.mark.asyncio
async def test_urm90040_envelope_contains_all_p0_fields(ep, tmp_path):
    """hotfix-2 P0: URM90040 fallback envelope 必含 id + next_step + expires_in:60 + urm90040_count (修真实事故 03194834960)。"""
    zip_path = tmp_path / "ep_533302.zip"
    zip_path.write_bytes(b'confirmed fp')
    ep.redis.incr = AsyncMock(return_value=1)
    ep.redis.expire = AsyncMock(return_value=True)
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)

    session = {
        'id': 533302, 'phone': '03194834960', 'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED,
        'status_history': [LoginStatus.PRE_LOGIN_CREATED],
    }
    result = await ep._urm90040_fallback(
        'pre_login_easypaisa_533302', session, 'URM90040', fingerprint_path=str(zip_path)
    )

    assert result['status'] == 'error'
    data = result['data']
    # P0 必须含的字段（修 APP exchange_api.dart line 193 抛 pre_login_no_id 的真实事故）
    assert data['id'] == 533302, 'envelope 必须含 id'
    assert data['next_step'] == 'verify_otp', 'envelope 必须含 next_step'
    assert data['code'] == 'SL_NEEDS_OTP'
    assert data['phase'] == LoginStatus.OTP_SENT
    assert data['expires_in'] == 60, 'OTP 实际 60s 过期（云机实战值），不是 120'
    assert data['urm90040_count'] == 1, 'envelope 暴露当前限频计数让 APP/监控可见'


@pytest.mark.asyncio
async def test_urm90040_without_confirmed_fingerprint_routes_to_upload_fingerprint(ep):
    """hotfix-3: 没有 MySQL 指纹时，URM90040 表示指纹未验证成功，不得调 loginStep1。"""
    session = {
        'id': 533302,
        'phone': '03194834960',
        'bankname': 'easypaisa',
        'status': LoginStatus.OTP_VERIFIED,
        'status_history': [LoginStatus.OTP_VERIFIED],
    }
    ep.redis.incr = AsyncMock(side_effect=Exception('没有指纹时不应该增加 URM90040 OTP fallback 计数'))
    ep._send_otp = AsyncMock(side_effect=Exception('没有指纹时不应该调用 loginStep1'))
    ep._persist_session_data = AsyncMock(return_value=True)

    result = await ep._urm90040_fallback(
        'pre_login_easypaisa_533302',
        session,
        'URM90040',
        fingerprint_path=None,
    )

    assert result['status'] == 'error'
    assert result['data']['code'] == 'FP_REQUIRED_OR_UNVERIFIED'
    assert result['data']['next_step'] == 'upload_fingerprint'
    assert result['data']['phase'] == LoginStatus.OTP_VERIFIED
    ep._send_otp.assert_not_awaited()
    ep.redis.incr.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_chain_full_with_pwd_to_account_selection(ep, tmp_path):
    """hotfix-2 P0: fallback 完整 chain (upload+verifyFingerprint+secondLogin(with_pwd)+queryAccountList) → ACCOUNT_SELECTION_REQUIRED。"""
    import json
    zip_path = tmp_path / "ep_533302.zip"
    zip_path.write_bytes(b'fake')

    session = {
        'id': 533302, 'phone': '03194834960', 'pinCode': 'client_pin_should_not_be_used',
        'bankname': 'easypaisa', 'status': LoginStatus.OTP_VERIFIED,
        'status_history': [LoginStatus.OTP_VERIFIED], 'fallback_from_urm90040': True,
    }
    ep._query_payment = AsyncMock(return_value={
        'id': 533302, 'phone': '03194834960', 'pin': 'db_pin_11223',
        'fingerprint_path': str(zip_path),
    })
    ep._call_upload_data = AsyncMock(return_value=True)
    ep._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    ep._call_second_login = AsyncMock(return_value={'outcome': 'success'})
    ep._call_query_account_list = AsyncMock(return_value={
        'outcome': 'success',
        'accounts_json': json.dumps([{'accno': '96699538', 'accountStatus': 'ACTIVE'}]),
    })
    ep._update_session_status = AsyncMock()
    ep._persist_session_data = AsyncMock()

    result = await ep._verify_otp_fallback_chain('pre_login_easypaisa_533302', session)

    assert result['status'] == 'success'
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    # 完整 chain 都被调一次
    ep._call_upload_data.assert_awaited_once()
    ep._call_verify_fingerprint.assert_awaited_once()
    ep._call_second_login.assert_awaited_once()
    ep._call_query_account_list.assert_awaited_once()
    # secondLogin 必须 with_pwd=True
    args, kwargs = ep._call_second_login.await_args
    assert kwargs.get('with_pwd') is True, 'fallback secondLogin 必须 with_pwd=True 救冻'
    assert args[0]['pinCode'] == 'db_pin_11223', 'fallback secondLogin pwd 必须来自 DB PIN'


@pytest.mark.asyncio
async def test_fallback_chain_urm90040_recurses_to_urm90040_fallback(ep, tmp_path):
    """hotfix-2 P0: fallback chain secondLogin 仍 URM90040 → 走 _urm90040_fallback (再发 OTP, counter++)。"""
    zip_path = tmp_path / "ep_533302.zip"
    zip_path.write_bytes(b'fake')

    session = {
        'id': 533302, 'phone': '03194834960', 'pinCode': '11223',
        'bankname': 'easypaisa', 'status': LoginStatus.OTP_VERIFIED,
        'status_history': [LoginStatus.OTP_VERIFIED], 'fallback_from_urm90040': True,
    }
    ep._query_payment = AsyncMock(return_value={
        'id': 533302, 'phone': '03194834960', 'pin': 'db_pin_11223',
        'fingerprint_path': str(zip_path),
    })
    ep._call_upload_data = AsyncMock(return_value=True)
    ep._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    ep._call_second_login = AsyncMock(return_value={'outcome': 'urm90040', 'message': 'URM90040'})
    ep._call_query_account_list = AsyncMock()
    ep._update_session_status = AsyncMock()
    ep._persist_session_data = AsyncMock()
    # _urm90040_fallback 应该被调
    ep.redis.incr = AsyncMock(return_value=2)
    ep.redis.expire = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})

    result = await ep._verify_otp_fallback_chain('pre_login_easypaisa_533302', session)

    # 结果应该是 _urm90040_fallback 返回的 (再发 OTP)
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_OTP'
    assert result['data']['next_step'] == 'verify_otp'
    # queryAccountList 不应该被调（secondLogin 已经 urm90040 了）
    ep._call_query_account_list.assert_not_awaited()
