import unittest
from unittest.mock import MagicMock


class FakeRedis:
    def __init__(self):
        self.kv = {}

    async def set(self, key, value, ex=None):
        self.kv[key] = value
        return True

    async def delete(self, key):
        existed = key in self.kv
        self.kv.pop(key, None)
        return 1 if existed else 0


class FakePayment:
    def __init__(self, *, payment_id=533280, certified=0, status=1, phone="923045536108", channel=1001, bank_type_id=97):
        self.id = payment_id
        self.certified = certified
        self.status = status
        self.phone = phone
        self.channel = channel
        self.bank_type_id = bank_type_id


class FakeQuery:
    def __init__(self, payment):
        self.payment = payment

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.payment


class FakeSession:
    def __init__(self, payment):
        self.payment = payment
        self.commit_count = 0

    def query(self, _model):
        return FakeQuery(self.payment)

    def commit(self):
        self.commit_count += 1


class FakeSessionFactory:
    def __init__(self, payment):
        self.session = FakeSession(payment)

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDbOrm:
    def __init__(self, payment):
        self.sessionmaker = FakeSessionFactory(payment)


class FakeRuntimeService:
    calls = []

    def __init__(self, redis):
        self.redis = redis

    async def set_collection_dispatch(self, payment_id, *, enabled, phone=None, channels=None, source):
        FakeRuntimeService.calls.append(
            {
                "payment_id": payment_id,
                "enabled": enabled,
                "phone": phone,
                "channels": channels,
                "source": source,
            }
        )
        return {"payment_id": payment_id, "dispatch_ds": enabled}


class EasyPaisaCollectionRuntimeToggleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.logger = MagicMock()
        FakeRuntimeService.calls = []

    async def test_selling_active_syncs_easypaisa_runtime_dispatch(self):
        from application.lakshmi_api.services.payments import e_wallet_handler as handler_module
        from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService

        payment = FakePayment(certified=0, status=1)
        db_orm = FakeDbOrm(payment)
        original_runtime_service = handler_module.EasyPaisaRuntimeService
        handler_module.EasyPaisaRuntimeService = FakeRuntimeService
        try:
            service = EasyPaisaPayService(db_orm, self.redis, None, self.logger)

            result = await service.selling_active(payment.id)

            self.assertTrue(result)
            self.assertEqual(payment.certified, 1)
            self.assertEqual(
                FakeRuntimeService.calls,
                [
                    {
                        "payment_id": 533280,
                        "enabled": True,
                        "phone": "923045536108",
                        "channels": 1001,
                        "source": "app_selling_active",
                    }
                ],
            )
        finally:
            handler_module.EasyPaisaRuntimeService = original_runtime_service

    async def test_selling_inactive_syncs_easypaisa_runtime_dispatch(self):
        from application.lakshmi_api.services.payments import e_wallet_handler as handler_module
        from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService

        payment = FakePayment(certified=1, status=1)
        db_orm = FakeDbOrm(payment)
        original_runtime_service = handler_module.EasyPaisaRuntimeService
        handler_module.EasyPaisaRuntimeService = FakeRuntimeService
        try:
            service = EasyPaisaPayService(db_orm, self.redis, None, self.logger)

            result = await service.selling_inactive(payment.id)

            self.assertTrue(result)
            self.assertEqual(payment.certified, 0)
            self.assertEqual(
                FakeRuntimeService.calls,
                [
                    {
                        "payment_id": 533280,
                        "enabled": False,
                        "phone": "923045536108",
                        "channels": 1001,
                        "source": "app_selling_inactive",
                    }
                ],
            )
        finally:
            handler_module.EasyPaisaRuntimeService = original_runtime_service


if __name__ == "__main__":
    unittest.main()
