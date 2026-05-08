import sys
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from application.pay.decimal_amount import generate_unique_decimal_amount, cleanup_decimal_callback_on_success


class FakePipeline:
    def __init__(self):
        self.calls = []

    def lpush(self, *args):
        self.calls.append(('lpush', args))

    def hset(self, *args):
        self.calls.append(('hset', args))

    def expire(self, *args):
        self.calls.append(('expire', args))

    async def execute(self):
        return [True] * len(self.calls)


class FakeRedis:
    def __init__(self, existing_ids=None):
        self._existing = existing_ids or []

    async def lrange(self, key, start, end):
        return self._existing

    def pipeline(self):
        return FakePipeline()


class FakeHandler:
    def __init__(self, existing_ids=None):
        self.redis = FakeRedis(existing_ids)
        self.logger = MagicMock()


@pytest.mark.asyncio
async def test_generate_returns_decimal_amount():
    handler = FakeHandler()
    result = await generate_unique_decimal_amount(
        handler, Decimal("1000"), 0.01, 0.99, "1005", "S123456", 100
    )
    assert result is not None
    assert result > Decimal("1000")
    assert result < Decimal("1001")


@pytest.mark.asyncio
async def test_generate_skips_existing_payment_id():
    handler = FakeHandler(existing_ids=[b"100"])
    with patch('application.pay.decimal_amount.random') as mock_random:
        mock_random.uniform.return_value = 0.50
        result = await generate_unique_decimal_amount(
            handler, Decimal("1000"), 0.01, 0.99, "1005", "S123456", 100
        )
    assert result is None


@pytest.mark.asyncio
async def test_cleanup_removes_from_redis():
    handler = FakeHandler()
    handler.redis.lrem = AsyncMock(return_value=1)
    handler.redis.hdel = AsyncMock(return_value=1)
    await cleanup_decimal_callback_on_success(handler, 100, Decimal("1000.50"))
    handler.redis.lrem.assert_called_once()
    assert handler.redis.hdel.call_count == 2
