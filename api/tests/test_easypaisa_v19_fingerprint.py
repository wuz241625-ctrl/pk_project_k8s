"""U7 / U15 指纹两阶段提交测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import json
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_fp(tmp_path):
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.db_orm = MagicMock()
    ep = EasyPaisa(handler)
    ep.FINGERPRINT_PATH = str(tmp_path) + '/'
    return ep


@pytest.mark.asyncio
async def test_u15_verify_fingerprint_rejected_keeps_old_zip(ep_fp, tmp_path):
    """U15: verify 失败时本地 ZIP md5 保持原状。"""
    old_zip = tmp_path / "easypaisa_1_03445021275.zip"
    old_zip.write_bytes(b'OLD ZIP VALID')
    md5_before = hashlib.md5(old_zip.read_bytes()).hexdigest()
    session = {'id': 1, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.OTP_VERIFIED, 'status_history': []}
    ep_fp._get_session_data = AsyncMock(return_value=session)
    ep_fp._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k', 'session_data': session, 'resolved_payment_id': 1,
    })
    ep_fp._get_payment_interface_lock = AsyncMock(return_value={'lock_id': 'k', 'lock_value': 'v'})
    ep_fp._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_fp.redis.get = AsyncMock(return_value=b'BAD ZIP')
    ep_fp.redis.delete = AsyncMock(return_value=True)
    ep_fp._call_upload_data_bytes = AsyncMock(return_value=True)
    ep_fp._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'rejected', 'message': 'bad'})
    result = await ep_fp.verify_fingerprint_http({'bankname': 'easypaisa', 'payment_id': 1})
    assert result['status'] == 'error'
    assert result['data']['code'] == 'FP_UPSTREAM_REJECTED'
    # 本地 ZIP md5 应该没变
    assert hashlib.md5(old_zip.read_bytes()).hexdigest() == md5_before


@pytest.mark.asyncio
async def test_verify_fingerprint_rollback_on_mysql_fail(ep_fp, tmp_path):
    """Fix #4: MySQL 写失败时 .new 临时文件被删，老 ZIP md5 不变。"""
    # 准备老 ZIP（已存在）
    old_zip = tmp_path / "easypaisa_1_03445021275.zip"
    old_zip.write_bytes(b'OLD VALID ZIP CONTENT')
    md5_before = hashlib.md5(old_zip.read_bytes()).hexdigest()

    session = {
        'id': 1, 'phone': '03445021275', 'bankname': 'easypaisa',
        'status': LoginStatus.OTP_VERIFIED, 'status_history': [],
    }
    ep_fp._get_session_data = AsyncMock(return_value=session)
    ep_fp._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k', 'session_data': session, 'resolved_payment_id': 1,
    })
    ep_fp._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_fp._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_fp.redis.get = AsyncMock(return_value=b'NEW ZIP TO BE REJECTED')
    ep_fp.redis.delete = AsyncMock(return_value=True)
    ep_fp._call_upload_data_bytes = AsyncMock(return_value=True)
    ep_fp._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    # MySQL 写失败
    ep_fp._update_payment_fingerprint_path = AsyncMock(
        side_effect=Exception('MySQL connection lost')
    )

    result = await ep_fp.verify_fingerprint_http({
        'bankname': 'easypaisa', 'payment_id': 1
    })

    # 验证：错误返回
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_UPSTREAM_ERROR'
    # 验证：老 ZIP 内容没变（md5 一致）
    assert hashlib.md5(old_zip.read_bytes()).hexdigest() == md5_before
    # 验证：.new 临时文件不存在（已被删）
    tmp_zip = tmp_path / "easypaisa_1_03445021275.zip.new"
    assert not tmp_zip.exists(), '.new tmp file should be cleaned up'


@pytest.mark.asyncio
async def test_verify_fingerprint_reads_pending_zip_from_binary_redis(tmp_path):
    """verify_fingerprint 读取 ZIP pending 必须避开 decoded Redis。"""
    decoded_redis = AsyncMock()
    decoded_redis.get = AsyncMock(
        side_effect=UnicodeDecodeError(
            'utf-8', b'PK\x03\x04\xafzip', 4, 5, 'invalid start byte'
        )
    )
    decoded_redis.delete = AsyncMock(return_value=True)
    binary_redis = AsyncMock()
    zip_body = b'PK\x03\x04\xafzip'
    binary_redis.get = AsyncMock(return_value=zip_body)

    handler = MagicMock()
    handler.redis = decoded_redis
    handler.db_orm = MagicMock()
    handler.application = MagicMock(redis_binary=binary_redis)
    ep = EasyPaisa(handler)
    ep.FINGERPRINT_PATH = str(tmp_path) + '/'

    session = {
        'id': 1,
        'phone': '03445021275',
        'bankname': 'easypaisa',
        'status': LoginStatus.OTP_VERIFIED,
        'status_history': [],
    }
    ep._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k',
        'session_data': session,
        'resolved_payment_id': 1,
    })
    ep._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'lock', 'lock_value': 'value'}
    )
    ep._release_payment_interface_lock = AsyncMock(return_value=True)
    ep._call_upload_data_bytes = AsyncMock(return_value=True)
    ep._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    ep._update_payment_fingerprint_path = AsyncMock(return_value=True)
    ep._update_session_status = AsyncMock(return_value=1)

    result = await ep.verify_fingerprint_http({
        'bankname': 'easypaisa',
        'payment_id': 1,
    })

    assert result['status'] == 'success'
    ep._call_upload_data_bytes.assert_awaited_once_with(session, zip_body)
    binary_redis.get.assert_awaited_once_with('easypaisa:pending_fp:1')
    decoded_redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_upload_fingerprint_stores_pending_zip_with_binary_redis(tmp_path):
    """upload_fingerprint 暂存 ZIP 时也必须使用二进制 Redis。"""
    decoded_redis = AsyncMock()
    decoded_redis.setex = AsyncMock()
    binary_redis = AsyncMock()
    binary_redis.setex = AsyncMock(return_value=True)

    handler = MagicMock()
    handler.redis = decoded_redis
    handler.db_orm = MagicMock()
    handler.application = MagicMock(redis_binary=binary_redis)
    ep = EasyPaisa(handler)
    ep.FINGERPRINT_PATH = str(tmp_path) + '/'

    session = {
        'id': 1,
        'phone': '03445021275',
        'bankname': 'easypaisa',
        'status': LoginStatus.OTP_VERIFIED,
        'status_history': [],
    }
    ep._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k',
        'session_data': session,
        'resolved_payment_id': 1,
    })
    ep._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'lock', 'lock_value': 'value'}
    )
    ep._release_payment_interface_lock = AsyncMock(return_value=True)

    zip_body = b'PK\x03\x04\xafzip'
    result = await ep.upload_fingerprint_http({
        'bankname': 'easypaisa',
        'payment_id': 1,
        'file': {
            'filename': 'fingerprint.zip',
            'body': zip_body,
            'content_type': 'application/zip',
        },
    })

    assert result['status'] == 'success'
    binary_redis.setex.assert_awaited_once_with('easypaisa:pending_fp:1', 600, zip_body)
    decoded_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_verify_fingerprint_idempotent_preserves_account_selection_phase(ep_fp):
    """已进入选账户状态时重复 verify_fingerprint 不能降回 fingerprintVerified。"""
    session = {
        'id': 1,
        'phone': '03445021275',
        'bankname': 'easypaisa',
        'status': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        'status_history': [LoginStatus.OTP_VERIFIED, LoginStatus.ACCOUNT_SELECTION_REQUIRED],
    }
    ep_fp._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k',
        'session_data': session,
        'resolved_payment_id': 1,
    })
    ep_fp._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'lock', 'lock_value': 'value'}
    )
    ep_fp._release_payment_interface_lock = AsyncMock(return_value=True)

    result = await ep_fp.verify_fingerprint_http({
        'bankname': 'easypaisa',
        'payment_id': 1,
    })

    assert result['status'] == 'success'
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    assert result['data']['next_step'] == 'select_accts'
