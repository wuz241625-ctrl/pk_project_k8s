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
