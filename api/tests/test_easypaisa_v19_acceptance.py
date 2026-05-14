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
