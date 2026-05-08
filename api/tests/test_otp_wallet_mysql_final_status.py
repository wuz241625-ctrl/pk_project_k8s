import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService
from application.lakshmi_api.services.payments.jazzcash_pay_service import JazzCashPayService


class DummySession:
    def __init__(self, payment):
        self.payment = payment

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, _model):
        query = MagicMock()
        query.filter.return_value.first.return_value = self.payment
        return query


class DummyDb:
    def __init__(self, payment):
        self.payment = payment

    def sessionmaker(self):
        return DummySession(self.payment)


class FakeRedis:
    async def get(self, _key):
        return "legacy-online-marker"

    async def sismember(self, _key, _value):
        return True


class OtpWalletMysqlFinalStatusTests(unittest.TestCase):
    def _service(self, service_cls, payment):
        return service_cls(DummyDb(payment), FakeRedis(), None, MagicMock())

    def test_jazzcash_selling_status_reads_mysql_collection_status_not_redis(self):
        asyncio.run(self._run_jazzcash_collection_case())

    async def _run_jazzcash_collection_case(self):
        offline_payment = SimpleNamespace(
            id=533302,
            wallet_status=1,
            status=1,
            certified=1,
            manual_status=0,
            collection_status=0,
            payout_status=1,
        )
        service = self._service(JazzCashPayService, offline_payment)

        self.assertFalse(await service.selling_order_status(533302))
        self.assertTrue(await service.place_order_status(533302))

        online_payment = SimpleNamespace(
            id=533302,
            wallet_status=1,
            status=1,
            certified=1,
            manual_status=0,
            collection_status=1,
            payout_status=0,
        )
        service = self._service(JazzCashPayService, online_payment)

        self.assertTrue(await service.selling_order_status(533302))
        self.assertFalse(await service.place_order_status(533302))

    def test_easypaisa_still_reads_mysql_final_status(self):
        asyncio.run(self._run_easypaisa_collection_case())

    async def _run_easypaisa_collection_case(self):
        payment = SimpleNamespace(
            id=533295,
            wallet_status=1,
            status=1,
            certified=1,
            manual_status=0,
            collection_status=1,
            payout_status=1,
        )
        service = self._service(EasyPaisaPayService, payment)

        self.assertTrue(await service.selling_order_status(533295))
        self.assertTrue(await service.place_order_status(533295))


if __name__ == "__main__":
    unittest.main()
