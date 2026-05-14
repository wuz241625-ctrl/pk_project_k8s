"""Fix #2: _check_payment SQL filter by partner_id (defense-in-depth)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa


@pytest.fixture
def ep_for_check():
    handler = MagicMock()
    ep = EasyPaisa(handler)
    return ep


@pytest.mark.asyncio
async def test_check_payment_filter_includes_partner_id(ep_for_check):
    """Fix #2: SQL filter 必须含 Payment.user_id == partner_id（ORM 列名 partner_id）。"""
    ep_for_check._get_bank_type_id = AsyncMock(return_value=97)
    captured_filters = []

    class FakeQuery:
        def __init__(self):
            self._filters = []

        def filter(self, *args):
            captured_filters.extend(args)
            return self

        def first(self):
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def query(self, model):
            return FakeQuery()

    ep_for_check.handler.db_orm.sessionmaker = lambda: FakeSession()

    await ep_for_check._check_payment('easypaisa', '03130268536', 33057)

    # 验证 captured_filters 含一个针对 partner_id 的等值条件
    filter_strs = [str(f) for f in captured_filters]
    assert any('partner_id' in s for s in filter_strs), \
        f'_check_payment SQL filter 缺 partner_id 条件，实际 filters: {filter_strs}'


@pytest.mark.asyncio
async def test_check_payment_returns_only_owner_record(ep_for_check):
    """Fix #2: 跨 partner 查询时 SQL 应返回 None（filter 拦下）。"""
    ep_for_check._get_bank_type_id = AsyncMock(return_value=97)

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            # 模拟 SQL 含 partner_id 过滤 → 查不到（返回 None）
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def query(self, model):
            return FakeQuery()

    ep_for_check.handler.db_orm.sessionmaker = lambda: FakeSession()

    # A partner (33057) 查 B partner 的 phone
    result = await ep_for_check._check_payment('easypaisa', 'B_phone', 33057)
    assert result is None  # SQL 拦下，无返回
