import json
import unittest
from unittest import mock

import fakeredis.aioredis


class WebsocketMonitorEPDispatchTests(unittest.IsolatedAsyncioTestCase):
    """EasyPaisa monitor 只能读 MySQL 最终态，不能再写 旧 Redis 运行状态。"""

    async def asyncSetUp(self):
        self.redis = fakeredis.aioredis.FakeRedis()

    def _handler(self, bank):
        from application.websocket.monitor import Websocket

        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 533294
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(return_value=bank)
        handler.query = mock.AsyncMock(return_value=[])
        return handler

    async def test_ep_online_ds_reads_collection_status_without_redis_write(self):
        handler = self._handler(
            {
                'certified': 1,
                'manual_status': 0,
                'status': 1,
                'channel': '1001',
                'bank_type': '97',
                'collection_status': 1,
                'payout_status': 0,
            }
        )

        result = await handler.qrcode_online(online=True, _type='ds')

        self.assertEqual(json.loads(result['data'])['status'], 1)
        self.assertFalse(await self.redis.sismember('payment_online_ds', 533294))
        self.assertEqual(await self.redis.lrange('payment_active_1001', 0, -1), [])

    async def test_ep_online_ds_disabled_does_not_reopen_from_monitor(self):
        handler = self._handler(
            {
                'certified': 1,
                'manual_status': 0,
                'status': 1,
                'channel': '1001',
                'bank_type': '97',
                'collection_status': 0,
                'payout_status': 1,
            }
        )

        result = await handler.qrcode_online(online=True, _type='ds')

        self.assertEqual(json.loads(result['data'])['status'], 0)
        self.assertFalse(await self.redis.sismember('payment_online_ds', 533294))
        self.assertEqual(await self.redis.lrange('payment_active_1001', 0, -1), [])

    async def test_ep_online_df_reads_payout_status_without_redis_write(self):
        handler = self._handler(
            {
                'certified': 1,
                'manual_status': 1,
                'status': 1,
                'channel': '1001',
                'bank_type': '97',
                'collection_status': 0,
                'payout_status': 1,
            }
        )

        result = await handler.qrcode_online(online=True, _type='df')

        self.assertEqual(json.loads(result['data'])['status'], 1)
        self.assertFalse(await self.redis.sismember('payment_online_df', 533294))
        self.assertEqual(await self.redis.lrange('payment_active_df', 0, -1), [])

    async def test_ep_offline_is_noop_for_legacy_redis(self):
        handler = self._handler({'certified': 1, 'channel': '1001', 'bank_type': '97'})
        await self.redis.sadd('payment_online_ds', 999999)
        await self.redis.rpush('payment_active_1001', 999999)

        result = await handler.qrcode_online(online=False, _type='ds')

        self.assertEqual(json.loads(result['data'])['status'], 0)
        self.assertTrue(await self.redis.sismember('payment_online_ds', 999999))
        self.assertEqual(await self.redis.lrange('payment_active_1001', 0, -1), [b'999999'])

    async def test_non_ep_online_ds_does_not_write_legacy_business_projection(self):
        handler = self._handler({'certified': 1, 'channel': '1003', 'bank_type': '98'})

        await handler.qrcode_online(online=True, _type='ds')

        self.assertFalse(await self.redis.sismember('payment_online_ds', 533294))
        self.assertEqual(await self.redis.lrange('payment_active_1003', 0, -1), [])
