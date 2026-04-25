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
    def __init__(self, *, payment_id=533280, certified=0, status=1, manual_status=0, phone="923045536108", channel=1001, bank_type_id=97, bank_type=None):
        self.id = payment_id
        self.certified = certified
        self.status = status
        self.manual_status = manual_status
        self.phone = phone
        self.channel = channel
        self.bank_type_id = bank_type_id
        self.bank_type = bank_type


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
        return await self.set_ds_order_dispatch(
            payment_id,
            enabled=enabled,
            phone=phone,
            channels=channels,
            source=source,
        )

    async def set_ds_order_dispatch(self, payment_id, *, enabled, phone=None, channels=None, source):
        FakeRuntimeService.calls.append(
            {
                "method": "set_ds_order_dispatch",
                "payment_id": payment_id,
                "enabled": enabled,
                "phone": phone,
                "channels": channels,
                "source": source,
            }
        )
        return {"payment_id": payment_id, "dispatch_ds": enabled}

    async def pause_order_dispatch(self, payment_id, *, phone=None, channels=None, source):
        FakeRuntimeService.calls.append(
            {
                "method": "pause_order_dispatch",
                "payment_id": payment_id,
                "phone": phone,
                "channels": channels,
                "source": source,
            }
        )
        return {"payment_id": payment_id, "dispatch_ds": False, "dispatch_df": False}

    async def resume_order_dispatch(self, payment_id, *, ds_enabled=True, df_enabled=True, phone=None, channels=None, source):
        FakeRuntimeService.calls.append(
            {
                "method": "resume_order_dispatch",
                "payment_id": payment_id,
                "ds_enabled": ds_enabled,
                "df_enabled": df_enabled,
                "phone": phone,
                "channels": channels,
                "source": source,
            }
        )
        return {"payment_id": payment_id, "dispatch_ds": ds_enabled, "dispatch_df": df_enabled}


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
                        "method": "resume_order_dispatch",
                        "payment_id": 533280,
                        "ds_enabled": True,
                        "df_enabled": True,
                        "phone": "923045536108",
                        "channels": 1001,
                        "source": "app_selling_active",
                    }
                ],
            )
        finally:
            handler_module.EasyPaisaRuntimeService = original_runtime_service

    async def test_selling_active_uses_runtime_when_legacy_bank_type_marks_easypaisa(self):
        from application.lakshmi_api.services.payments import e_wallet_handler as handler_module
        from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService

        payment = FakePayment(certified=0, status=1, bank_type_id=14, bank_type='97')
        db_orm = FakeDbOrm(payment)
        original_runtime_service = handler_module.EasyPaisaRuntimeService
        handler_module.EasyPaisaRuntimeService = FakeRuntimeService
        try:
            service = EasyPaisaPayService(db_orm, self.redis, None, self.logger)

            result = await service.selling_active(payment.id)

            self.assertTrue(result)
            self.assertEqual(FakeRuntimeService.calls[0]["method"], "resume_order_dispatch")
        finally:
            handler_module.EasyPaisaRuntimeService = original_runtime_service

    async def test_selling_active_keeps_ds_paused_when_admin_manual_lock_exists(self):
        from application.lakshmi_api.services.payments import e_wallet_handler as handler_module
        from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService

        payment = FakePayment(certified=0, status=1, manual_status=1)
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
                        "method": "resume_order_dispatch",
                        "payment_id": 533280,
                        "ds_enabled": False,
                        "df_enabled": True,
                        "phone": "923045536108",
                        "channels": 1001,
                        "source": "app_selling_active",
                    }
                ],
            )
        finally:
            handler_module.EasyPaisaRuntimeService = original_runtime_service

    async def test_selling_active_keeps_dispatch_paused_when_payment_disabled(self):
        from application.lakshmi_api.services.payments import e_wallet_handler as handler_module
        from application.lakshmi_api.services.payments.easypaisa_pay_service import EasyPaisaPayService

        payment = FakePayment(certified=0, status=0, manual_status=0)
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
                        "method": "resume_order_dispatch",
                        "payment_id": 533280,
                        "ds_enabled": False,
                        "df_enabled": False,
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
            self.assertNotIn("login_off_easypaisa_533280", self.redis.kv)
            self.assertEqual(
                FakeRuntimeService.calls,
                [
                    {
                        "method": "pause_order_dispatch",
                        "payment_id": 533280,
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
