from datetime import datetime, timedelta

from sqlalchemy import and_, text, update
from sqlalchemy.orm import joinedload

from application.crypto import decrypt, encrypt
from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.models import *
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.schema.payment_schema import *
from application.lakshmi_api.services.payment_services import BANK_SERVICES

PAYMENT_STATUS = {0: 'inactive', 1: 'active'}
CERTIFIED_STATUS = {'inactive': 0, 'active': 1}

class PaymentHandler(BaseHandler):
    def _get_params(self, keys):
        params = {}
        for key in keys:
            params[key] = self.get_body_argument(key, default=None)
        return params

    async def _assign_bank(self, bank_id):
        with self.db_orm.sessionmaker() as session:
            bank = session.query(BankType).filter_by(id=bank_id).first()
            if bank is not None:
                return bank

            raise ApiError('Bank not found')

    async def _assign_payment(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            payment = (
                session.query(Payment)
                .options(joinedload(Payment.bank))
                .filter(Payment.id == payment_id, Payment.user_id == self.current_user.id)
                .first()
            )
        if payment is not None:
            return payment

        raise ApiError('payment not found')

class PaymentTpin(PaymentHandler):
    """
    查询Payment的tpin（aes加密返回）
    """
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        payment_id = self.get_query_argument('payment_id', None)
        if payment_id is None:
            raise ApiError('Parameter payment_id is required')

        tpin_encrypt = ""
        # 根据 payment_id 获取原订单
        with self.db_orm.sessionmaker() as session:
            try:
                dbPayment = session.query(Payment).filter_by(id=payment_id).one_or_none()

                if dbPayment is None:
                    raise ApiError('Payment not found')

                if dbPayment is not None and dbPayment.tpin is not None:
                    tpin_encrypt = encrypt(dbPayment.tpin)

            except ApiError as e:
                raise e
            except Exception as e:
                self.logger.error(f"修改Payment的tpin e: {e}")
            finally:
                session.close()

        responseData = {
            "is_success": True,
            "tpin_encrypt": tpin_encrypt
        }

        self.logger.info("Response [POST] (/payment/tpin), user: %s, name: %s, responseData: %s",
                         self.current_user.id,
                         self.current_user.name, responseData)
        self.write(responseData)

    """
    修改Payment的tpin
    """
    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        params = self._get_params(['payment_id', 'tpin'])
        self.logger.info("Request [POST] (/payment/tpin), user.id: %s, user.name: %s, params: %s", self.current_user.id, self.current_user.name, params)
        paymentTpin = PaymentTpinSchema().load(params)
        payment_id = paymentTpin.get("payment_id")
        # 对接收到的tpin进行解密
        tpin = decrypt(paymentTpin.get("tpin"))

        self.logger.info(f"payment.id: {payment_id}, 修改tpin: {paymentTpin.get("tpin")}, 解密：{tpin}")

        is_success = True
        # 根据 code, payment_id 获取原订单
        with self.db_orm.sessionmaker() as session:
            try:
                dbPayment = session.query(Payment).filter_by(id=payment_id).one_or_none()
                if dbPayment is not None:
                    dbPayment.tpin_is_true = True
                    dbPayment.tpin = tpin
                    dbPayment.updated_at = datetime.now()
                    session.commit()
                # 保存新的tpin到缓存，1天后过期
                redis_key = f"payment_tpin_newest:{payment_id}"
                self.logger.info(f"redis key: {redis_key}，设置新的tpin: {tpin}")
                await self.redis.set(redis_key, tpin, 60 * 60 * 24)

            except Exception as e:
                is_success = False
                session.rollback()
                self.logger.error(
                    f"修改Payment的tpin e: {e}")
            finally:
                session.close()

        responseData = {
            "is_success": is_success,
        }

        self.logger.info("Response [POST] (/payment/tpin), user: %s, name: %s, responseData: %s",
                         self.current_user.id,
                         self.current_user.name, responseData)
        self.write(responseData)
