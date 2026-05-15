"""U1-U25 端到端验收（mock 上游）。spec §7。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_mock():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.get = AsyncMock(return_value=None)
    handler.redis.set = AsyncMock(return_value=True)
    handler.redis.setex = AsyncMock(return_value=True)
    handler.redis.delete = AsyncMock(return_value=True)
    handler.redis.ttl = AsyncMock(return_value=300)
    handler.redis.expire = AsyncMock(return_value=True)
    handler.current_user = MagicMock()
    handler.current_user.id = 1
    handler.current_user.hash_trade = '$2b$12$dummyhash'
    handler.db_orm = MagicMock()
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_u3_pre_login_returns_ready_when_active(ep_mock):
    """U3: 已 active 账号再次 pre_login 返回 ready。"""
    # mock bcrypt 校验通过
    with patch('bcrypt.checkpw', return_value=True):
        # mock _check_payment 返回已 active 的 payment
        ep_mock._check_payment = AsyncMock(return_value={
            'id': 533264,
            'phone': '03421904953',
            'user_id': 1,
            'wallet_status': 1,  # ACTIVE
            'fingerprint_path': '/fingerprint/easypaisa_533264_03421904953.zip',
        })
        # mock interface lock
        ep_mock._get_payment_interface_lock = AsyncMock(
            return_value={'lock_id': 'k', 'lock_value': 'v'}
        )
        ep_mock._release_payment_interface_lock = AsyncMock(return_value=True)
        # 注：传 payment_id=533264 时 pre_login_http 会查 MySQL，需要 mock db_orm 路径
        # 但既然我们传 payment_id 的话会进入 MySQL 查询分支，mock 起来麻烦。
        # 简化：不传 payment_id，让代码走 _check_payment 路径（_check_payment 已 mock）
        result = await ep_mock.pre_login_http({
            'bankname': 'easypaisa',
            'phone': '03421904953',
            'password': 'tradepwd',
            'pin': '14725',
            'name': 'Test User',
            'step': 'complete_login',
        })
    assert result['status'] == 'success'
    assert result['data']['next_step'] == 'ready'
    assert result['data']['phase'] == LoginStatus.ACTIVE_SUCCESSFUL


@pytest.mark.asyncio
async def test_u2_second_time_login_success(ep_mock, tmp_path):
    """U2: 二次上号一气呵成到 ACCOUNT_SELECTION_REQUIRED。"""
    zip_path = tmp_path / "ep.zip"
    zip_path.write_bytes(b'fake zip content')
    bound_payment = {
        'id': 533264,
        'phone': '03421904953',
        'fingerprint_path': str(zip_path),
        'wallet_status': 0,
    }
    session_data = {
        'id': 533264, 'phone': '03421904953', 'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED],
    }
    ep_mock._call_upload_data = AsyncMock(return_value=True)
    ep_mock._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    ep_mock._call_second_login = AsyncMock(return_value={'outcome': 'success'})
    ep_mock._call_query_account_list = AsyncMock(return_value={
        'outcome': 'success',
        'accounts_json': json.dumps([{'accno': '88521642', 'accountStatus': 'ACTIVE'}]),
    })
    ep_mock._persist_session_data = AsyncMock(return_value=int(123))
    result = await ep_mock._pre_login_second_time_chain(
        'pre_login_easypaisa_533264', session_data, bound_payment
    )
    assert result['status'] == 'success'
    assert result['data']['next_step'] == 'second_login'
    assert session_data['status'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED


@pytest.mark.asyncio
async def test_u20_local_zip_missing_routes_to_upload_fingerprint(ep_mock):
    """hotfix-3: MySQL 没有可用指纹时，不当作真实掉线，回到录指纹流程。"""
    bound = {'id': 1, 'phone': 'x', 'fingerprint_path': '/nonexistent/file.zip', 'wallet_status': 0}
    session = {'id': 1, 'phone': 'x', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep_mock._persist_session_data = AsyncMock(return_value=True)
    result = await ep_mock._pre_login_second_time_chain('pre_login_easypaisa_1', session, bound)
    assert result['status'] == 'error'
    assert result['data']['code'] == 'FP_REQUIRED_OR_UNVERIFIED'
    assert result['data']['next_step'] == 'upload_fingerprint'
    assert result['data']['phase'] == LoginStatus.OTP_VERIFIED
    assert session['status'] == LoginStatus.OTP_VERIFIED


@pytest.mark.asyncio
async def test_u17_payment_status_returns_new_enum_strings(ep_mock):
    """U17: payment_status_http 返回新 8 状态枚举字符串。"""
    session = {'status': LoginStatus.FINGERPRINT_VERIFIED, 'phone': 'x', 'id': '1',
               'last_error': None, 'cd_until': 0}
    ep_mock._resolve_session_context = AsyncMock(return_value={
        'session_data': session, 'resolved_payment_id': '1',
    })
    result = await ep_mock.payment_status_http({'bankname': 'easypaisa', 'payment_ids': '1'})
    assert result['status'] == 'success'
    assert result['datas'][0]['status'] == 'fingerprintVerified'
    assert result['datas'][0]['next_action'] == 'second_login'


@pytest.mark.asyncio
async def test_second_login_idempotent_after_pre_login_chain(ep_mock):
    """Fix #1: 二次上号续推完成后 APP 调 second_login_http 应幂等返回 success。"""
    session = {
        'id': '533294', 'phone': '03130268536', 'bankname': 'easypaisa',
        'status': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        'account_entire': '[{"accno":"53512051","accountStatus":"ACTIVE"}]',
        'status_history': [LoginStatus.PRE_LOGIN_CREATED, LoginStatus.ACCOUNT_SELECTION_REQUIRED],
    }
    ep_mock._resolve_session_context = AsyncMock(return_value={
        'session_data': session, 'redis_key': 'pre_login_easypaisa_533294',
        'resolved_payment_id': '533294',
    })
    ep_mock._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_mock._release_payment_interface_lock = AsyncMock(return_value=True)
    # _call_second_login 不该被调用（幂等短路）
    ep_mock._call_second_login = AsyncMock(side_effect=Exception('should not be called'))

    result = await ep_mock.second_login_http({
        'bankname': 'easypaisa', 'payment_id': '533294'
    })

    assert result['status'] == 'success'
    assert result['data']['ok'] is True
    assert result['data']['next_step'] == 'query_accts'
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED


@pytest.mark.asyncio
async def test_second_login_idempotent_after_active(ep_mock):
    """Fix #1: ACTIVE_SUCCESSFUL 状态调 second_login_http 也幂等成功。"""
    session = {
        'id': '533294', 'phone': '03130268536', 'bankname': 'easypaisa',
        'status': LoginStatus.ACTIVE_SUCCESSFUL,
        'status_history': [LoginStatus.ACTIVE_SUCCESSFUL],
    }
    ep_mock._resolve_session_context = AsyncMock(return_value={
        'session_data': session, 'redis_key': 'pre_login_easypaisa_533294',
        'resolved_payment_id': '533294',
    })
    ep_mock._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_mock._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_mock._call_second_login = AsyncMock(side_effect=Exception('should not be called'))

    result = await ep_mock.second_login_http({
        'bankname': 'easypaisa', 'payment_id': '533294'
    })

    assert result['status'] == 'success'
    assert result['data']['phase'] == LoginStatus.ACTIVE_SUCCESSFUL


def test_build_verify_account_request_with_pwd_includes_phone_and_pwd():
    """hotfix-2 P0: with_pwd=True 时 request body 必含 phone + pwd 字段。"""
    handler = MagicMock()
    ep = EasyPaisa(handler)

    session = {'phone': '03194834960', 'pinCode': '11223'}

    # Mock _encode_indus_request 让测试不依赖加密细节
    captured_payloads = []

    def fake_encode(funcName, endpoint, json_str):
        captured_payloads.append(json_str)
        return b'encoded_bytes'

    ep._encode_indus_request = fake_encode

    # 默认 with_pwd=False
    ep._build_verify_account_request(session)
    default_payload = captured_payloads[-1]
    assert '"account_id": "03194834960"' in default_payload
    assert '"pwd"' not in default_payload
    assert default_payload.count('"phone"') == 0

    # with_pwd=True
    ep._build_verify_account_request(session, with_pwd=True)
    pwd_payload = captured_payloads[-1]
    assert '"account_id": "03194834960"' in pwd_payload
    assert '"phone": "03194834960"' in pwd_payload
    assert '"pwd": "11223"' in pwd_payload


@pytest.mark.asyncio
async def test_pre_login_second_time_chain_skips_upload_and_verify_fingerprint(ep_mock, tmp_path):
    """hotfix-2 P0: 二次上号链路不再前置 upload_data + verifyFingerprint（节省 5-6s/次）。"""
    zip_path = tmp_path / "ep.zip"
    zip_path.write_bytes(b'fake zip content')
    bound_payment = {
        'id': 533264,
        'phone': '03421904953',
        'fingerprint_path': str(zip_path),
        'wallet_status': 0,
    }
    session_data = {
        'id': 533264, 'phone': '03421904953', 'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED],
    }
    # 这两个不应该被调用！
    ep_mock._call_upload_data = AsyncMock(
        side_effect=Exception('Should not be called in hotfix-2 二次上号链路'),
    )
    ep_mock._call_verify_fingerprint = AsyncMock(
        side_effect=Exception('Should not be called in hotfix-2 二次上号链路'),
    )
    ep_mock._call_second_login = AsyncMock(return_value={'outcome': 'success'})
    ep_mock._call_query_account_list = AsyncMock(return_value={
        'outcome': 'success',
        'accounts_json': json.dumps([{'accno': '88521642', 'accountStatus': 'ACTIVE'}]),
    })
    ep_mock._persist_session_data = AsyncMock(return_value=int(123))

    result = await ep_mock._pre_login_second_time_chain(
        'pre_login_easypaisa_533264', session_data, bound_payment
    )

    assert result['status'] == 'success'
    assert result['data']['next_step'] == 'second_login'
    assert session_data['status'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    # 验证 0 次调用
    ep_mock._call_upload_data.assert_not_awaited()
    ep_mock._call_verify_fingerprint.assert_not_awaited()
    ep_mock._call_second_login.assert_awaited_once()
    ep_mock._call_query_account_list.assert_awaited_once()
