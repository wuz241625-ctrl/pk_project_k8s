from datetime import timedelta, datetime
from enum import Enum
from marshmallow import Schema, fields, validate
from application.lakshmi_api.schema.payment_schema import PaymentSchema
from application.lakshmi_api.services.deposit_extra_bonus_service import DepositExtraBonusService
import logging


class OrderStatus(Enum):
    UNKNOWN = -2
    REVOKED = -1
    PENDING = 0
    PROCESSING = 1
    INSPECTING = 2
    CONFIRMED = 3
    DONE = 4


class DepositOrderSchema(Schema):
    payment_name = fields.String(required=True)
    amount = fields.Decimal(as_string=True, places=2)
    payment_account = fields.String(required=True)
    serial_number = fields.String(attribute="serial_number", required=True)
    benefit = fields.Decimal(attribute="benefit", as_string=True, places=2)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    paid_at = fields.DateTime(attribute="paid_at", format="%Y-%m-%d %H:%M:%S")
    status = fields.Method('set_status')
    payment = fields.Nested(PaymentSchema)

    @staticmethod
    def set_status(obj):
        # if not picture, 100% return PROCESSING
        if obj.payment_img == 0:
            return 'PROCESSING'
        else:
            return OrderStatus(obj.status).name


class OrderDataSchema(DepositOrderSchema):
    place_order_path = fields.Method('set_place_order_path')
    promote = fields.Method('set_promote')
    payment_bank_name = fields.Method('set_payment_bank_name')

    @staticmethod
    def set_place_order_path(obj):
        return f'/api/v1/orders/{obj.serial_number}'

    @staticmethod
    def set_promote(obj):
        service = DepositExtraBonusService()
        extra_bonus = service.extra_bonus(obj.amount)
        status = True if extra_bonus is not None else False
        return {"status": status, "extra_bonus": extra_bonus}

    @staticmethod
    def set_payment_bank_name(obj):
        if obj.payment_id is None or obj.payment is None or obj.payment.bank is None:
            return None
        return obj.payment.bank.name


class SingleDepositOrderSchema(Schema):
    serial_number = fields.String(attribute="serial_number")
    amount = fields.Decimal(data_key="Amount", as_string=True, places=2)
    ifsc = fields.String(data_key="IFSC", required=True)
    name = fields.String(attribute="payment_name", data_key="Name", required=True)
    account = fields.String(attribute="payment_account", data_key="Account")
    bank = fields.String(attribute="payment_bank", data_key="Bank")
    benefit = fields.Decimal(attribute="benefit", as_string=True, places=2)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    paid_at = fields.DateTime(attribute="paid_at", format="%Y-%m-%d %H:%M:%S")
    order_placed_at = fields.DateTime(attribute="order_placed_at", format="%Y-%m-%d %H:%M:%S")
    status = fields.Method('set_status')
    patch_path = fields.Method('set_patch_path')
    expired_at_in_seconds = fields.Method('set_expired_at')
    payment_bank_name = fields.Method('set_payment_bank_name')

    @staticmethod
    def set_patch_path(obj):
        return f'/api/v1/orders/{obj.serial_number}'

    @staticmethod
    def set_status(obj):
        return OrderStatus(obj.status).name.lower()

    @staticmethod
    def set_payment_bank_name(obj):
        return obj.payment.bank.name

    @staticmethod
    def set_expired_at(obj):
        logger = logging.getLogger(__name__)
        # if transaction confirmed but image not exist, let the expired is None
        if obj.payment_img == 0 and obj.status == 3:
            return None

        if obj.order_placed_at:
            logger.warning(f"order_placed_at: {obj.order_placed_at}")
            expired_at = obj.order_placed_at + timedelta(minutes=30)
            logger.warning(f"expired_at: {expired_at}")
            current_time: datetime = datetime.now()
            logger.warning(f"current_time: {current_time}")
            difference = (expired_at - current_time).total_seconds()
            logger.warning(f"difference: {difference}")
            if difference < 0:
                difference = 0
            return difference
        else:
            return 0


class NewOrderSchema(Schema):
    payment_id = fields.Integer(required=True)
