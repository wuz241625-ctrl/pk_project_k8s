import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeRedis:
    def __init__(self):
        self.deleted_keys = []

    async def setnx(self, key, value):
        return True

    async def expire(self, key, seconds):
        return True

    async def delete(self, key):
        self.deleted_keys.append(key)
        return 1


class FakeHandler:
    def __init__(self):
        self.arguments = {
            'token': 'fake-token',
            'msisdn': '03188711901',
        }
        self.redis = FakeRedis()
        self.logger = MagicMock()
        self.written = []
        self.query = AsyncMock(side_effect=[
            [{
                'code': 'ORD-001',
                'amount': 100.0,
                'channel_code': '1002',
                'status': 0,
                'merchant_id': 1,
                'third_party_name': 'easypay',
                'otherpay': 9,
            }],
            [{
                'merchant_id': 'M-123',
                'key': 'user',
                'key2': 'pass',
                'key3': 'store',
                'pay_url': 'https://fake.endpoint',
            }],
        ])
        self.execute = AsyncMock(return_value=True)
        self.token_decode = AsyncMock(return_value='ORD-001')

    def get_argument(self, name, default=None):
        return self.arguments.get(name, default)

    def write(self, payload):
        self.written.append(payload)
        return payload


class EasypayHandlerTests(unittest.TestCase):
    def test_post_updates_status_and_utr_with_msisdn(self):
        from application.pay.easypay_handler import EasypayInitiate

        handler = FakeHandler()

        async def run():
            with patch('application.pay.easypay_handler.asyncio.create_task') as mock_create_task:
                await EasypayInitiate.post(handler)

                handler.execute.assert_awaited_once_with(
                    "UPDATE orders_ds SET status=1, utr=%s WHERE code=%s AND status=0",
                    '03188711901',
                    'ORD-001',
                )
                self.assertEqual(handler.written[-1], {'code': 0, 'message': 'payment request sent'})
                mock_create_task.assert_called_once()
                mock_create_task.call_args[0][0].close()

        asyncio.run(run())

    def test_background_task_writes_trans_id_from_initiate_response(self):
        from application.pay.easypay_handler import _easypay_background_task

        handler = SimpleNamespace(
            redis=SimpleNamespace(delete=AsyncMock(return_value=1)),
            application=SimpleNamespace(db=MagicMock()),
        )
        config = {
            'pay_url': 'https://fake.endpoint',
            'key': 'user',
            'key2': 'pass',
            'key3': 'store',
            'merchant_id': 'M-123',
        }

        mock_cursor = AsyncMock()
        mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor.__aexit__ = AsyncMock(return_value=False)

        mock_conn = AsyncMock()
        mock_conn.cursor = MagicMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)

        handler.application.db.acquire = MagicMock(return_value=mock_conn)

        async def run():
            with patch('application.pay.easypay_handler.async_initiate_transaction',
                       AsyncMock(return_value={'success': True, 'response_code': '0000', 'transaction_id': '48346432401'})), \
                    patch('application.pay.easypay_handler.order_success_ds_third',
                          AsyncMock(return_value=True)) as mock_settle:
                await _easypay_background_task(handler, 'ORD-001', config, 100.0, '03188711901')

                mock_settle.assert_awaited_once_with(handler, 'ORD-001', utr='03188711901')
                mock_cursor.execute.assert_awaited_once()
                sql_call = mock_cursor.execute.call_args
                self.assertIn('trans_id', sql_call[0][0])
                self.assertEqual(sql_call[0][1], ('48346432401', 'ORD-001'))

        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
