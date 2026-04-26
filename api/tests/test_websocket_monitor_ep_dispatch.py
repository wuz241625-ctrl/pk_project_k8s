import json
import unittest
from unittest import mock

import fakeredis.aioredis


class WebsocketMonitorEPDispatchTests(unittest.IsolatedAsyncioTestCase):
    """qrcode_online for bank_type=97 must route through runtime service."""

    async def asyncSetUp(self):
        self.redis = fakeredis.aioredis.FakeRedis()

    async def test_ep_online_ds_calls_set_collection_dispatch_enabled_true(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 533294
        handler.logger = mock.MagicMock()
        # mock DB: EP card, certified, channel=1001
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'manual_status': 0, 'status': 1, 'channel': '1001', 'bank_type': '97'}
        )
        handler.query = mock.AsyncMock(return_value=[])

        # patch runtime_service set_ds_order_dispatch
        with mock.patch(
            'application.websocket.monitor.EasyPaisaRuntimeService'
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_ds_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=True, _type='ds')

        mock_service.set_ds_order_dispatch.assert_awaited_once()
        call = mock_service.set_ds_order_dispatch.await_args
        assert call.kwargs['enabled'] is True
        assert call.kwargs['channels'] == ['1001']
        assert json.loads(result['data'])['status'] == 1

    async def test_ep_offline_ds_calls_set_collection_dispatch_enabled_false(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 533294
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'channel': '1001', 'bank_type': '97'}
        )
        handler.qr_channels = ['1001']
        # online=False 分支不先读 DB（当前代码行为），所以 get_result_by_condition 不必被调

        with mock.patch(
            'application.websocket.monitor.EasyPaisaRuntimeService'
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_ds_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=False, _type='ds')

        mock_service.set_ds_order_dispatch.assert_awaited_once()
        call = mock_service.set_ds_order_dispatch.await_args
        assert call.kwargs['enabled'] is False

    async def test_ep_online_df_calls_runtime_df_dispatch(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 533294
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'manual_status': 1, 'status': 1, 'channel': '1001', 'bank_type': '97'}
        )
        handler.query = mock.AsyncMock(return_value=[])

        with mock.patch(
            'application.websocket.monitor.EasyPaisaRuntimeService'
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_df_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=True, _type='df')

        mock_service.set_df_order_dispatch.assert_awaited_once()
        call = mock_service.set_df_order_dispatch.await_args
        assert call.kwargs['enabled'] is True
        assert call.kwargs['channels'] == ['1001']
        assert json.loads(result['data'])['status'] == 1

    async def test_ep_online_df_disabled_status_uses_bank_type_id_and_fails(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 533294
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'manual_status': 0, 'status': 0, 'channel': '1001', 'bank_type': '14', 'bank_type_id': '97'}
        )
        handler.query = mock.AsyncMock(return_value=[])

        with mock.patch(
            'application.websocket.monitor.EasyPaisaRuntimeService'
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_df_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=True, _type='df')

        mock_service.set_df_order_dispatch.assert_awaited_once()
        call = mock_service.set_df_order_dispatch.await_args
        assert call.kwargs['enabled'] is False
        assert json.loads(result['data'])['status'] == 0

    async def test_ep_online_df_disabled_status_uses_legacy_bank_type_and_fails(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 533294
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'manual_status': 0, 'status': 0, 'channel': '1001', 'bank_type': '97', 'bank_type_id': '14'}
        )
        handler.query = mock.AsyncMock(return_value=[])

        with mock.patch(
            'application.websocket.monitor.EasyPaisaRuntimeService'
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_df_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=True, _type='df')

        mock_service.set_df_order_dispatch.assert_awaited_once()
        call = mock_service.set_df_order_dispatch.await_args
        assert call.kwargs['enabled'] is False
        assert json.loads(result['data'])['status'] == 0

    async def test_non_ep_online_ds_preserves_legacy_write(self):
        """非 runtime 码商走原 legacy 写入，不调 runtime service。"""
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 888888
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'channel': '1003', 'bank_type': '14'}
        )

        with mock.patch(
            'application.websocket.monitor.EasyPaisaRuntimeService'
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_ds_order_dispatch = mock.AsyncMock()

            await handler.qrcode_online(online=True, _type='ds')

        mock_service.set_ds_order_dispatch.assert_not_awaited()
        assert await self.redis.sismember('payment_online_ds', 888888)

    async def test_jazzcash_online_ds_calls_runtime_dispatch(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 7001
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'manual_status': 0, 'status': 1, 'channel': '1003', 'bank_type': '98'}
        )
        handler.query = mock.AsyncMock(return_value=[])

        with mock.patch('application.websocket.monitor.JazzCashRuntimeService') as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_ds_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=True, _type='ds')

        mock_service.set_ds_order_dispatch.assert_awaited_once()
        call = mock_service.set_ds_order_dispatch.await_args
        assert call.kwargs['enabled'] is True
        assert call.kwargs['channels'] == ['1003']
        assert json.loads(result['data'])['status'] == 1
        assert not await self.redis.sismember('payment_online_ds', 7001)

    async def test_jazzcash_online_df_calls_runtime_dispatch(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 7001
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'certified': 1, 'manual_status': 0, 'status': 1, 'channel': '1003', 'bank_type': '98'}
        )
        handler.query = mock.AsyncMock(return_value=[])

        with mock.patch('application.websocket.monitor.JazzCashRuntimeService') as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_df_order_dispatch = mock.AsyncMock()

            result = await handler.qrcode_online(online=True, _type='df')

        mock_service.set_df_order_dispatch.assert_awaited_once()
        call = mock_service.set_df_order_dispatch.await_args
        assert call.kwargs['enabled'] is True
        assert call.kwargs['channels'] == ['1003']
        assert json.loads(result['data'])['status'] == 1
        assert not await self.redis.sismember('payment_online_df', 7001)

    async def test_jazzcash_offline_uses_runtime_dispatch(self):
        from application.websocket.monitor import Websocket
        handler = Websocket.__new__(Websocket)
        handler.redis = self.redis
        handler.qr_id = 7001
        handler.logger = mock.MagicMock()
        handler.get_result_by_condition = mock.AsyncMock(
            return_value={'bank_type': '98', 'bank_type_id': '98', 'channel': '1003'}
        )

        with mock.patch('application.websocket.monitor.JazzCashRuntimeService') as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.set_ds_order_dispatch = mock.AsyncMock()
            mock_service.set_df_order_dispatch = mock.AsyncMock()

            await handler.qrcode_online(online=False, _type=None)

        mock_service.set_ds_order_dispatch.assert_awaited_once()
        mock_service.set_df_order_dispatch.assert_awaited_once()
