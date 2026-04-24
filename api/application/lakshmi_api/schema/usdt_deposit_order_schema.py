from datetime import datetime, timedelta
from enum import Enum

from marshmallow import Schema, fields
import logging


class OrderStatus(Enum):
    REVOKED = -1
    PENDING = 0
    PROCESSING = 1
    PAID = 2


class UsdtDepositOrderSchema(Schema):
    id = fields.String(attribute="id")
    serial_number = fields.String(attribute="serial_number")
    status = fields.Method('set_status')
    usdt_amount = fields.Decimal(data_key="usdt_amount", as_string=True, places=4)
    exchange_rate = fields.Decimal(attribute="exchange_rate", as_string=True, places=4)
    currency_amount = fields.Decimal(attribute="currency_amount", as_string=True, places=4)
    total_amount = fields.Decimal(attribute="total_amount", as_string=True, places=4)
    block_chain = fields.String(attribute="block_chain")
    bonus_rate = fields.Decimal(attribute="bonus_rate", as_string=True, places=4)
    bonus = fields.Decimal(attribute="bonus", as_string=True, places=4)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    paid_at = fields.DateTime(attribute="paid_at", format="%Y-%m-%d %H:%M:%S")
    address = fields.String(attribute="address")
    edit_path = fields.Method('set_edit_path')
    patch_path = fields.Method('set_patch_path')

    @staticmethod
    def set_edit_path(obj):
        return f'/api/v1/usdt/orders/{obj.serial_number}/edit'

    @staticmethod
    def set_patch_path(obj):
        return f'/api/v1/usdt/orders/{obj.serial_number}'

    @staticmethod
    def set_status(obj):
        return OrderStatus(obj.status).name


class SingleUsdtOrderSchema(Schema):
    serial_number = fields.String(attribute="serial_number")
    usdt_amount = fields.Decimal(data_key="usdt_amount", as_string=True, places=2)
    exchange_rate = fields.Decimal(attribute="exchange_rate", as_string=True, places=2)
    currency_amount = fields.Decimal(attribute="currency_amount", as_string=True, places=2)
    block_chain = fields.String(attribute="block_chain")
    bonus_rate = fields.Decimal(attribute="bonus_rate", as_string=True, places=2)
    bonus = fields.Decimal(attribute="bonus", as_string=True, places=2)
    total_amount = fields.Decimal(attribute="total_amount", as_string=True, places=2)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    address = fields.String(attribute="address")
    patch_path = fields.Method('set_patch_path')
    expired_at_in_seconds = fields.Method('set_expired_at')
    status = fields.Method('set_status')

    @staticmethod
    def set_patch_path(obj):
        return f'/api/v1/usdt/orders/{obj.serial_number}'

    @staticmethod
    def set_expired_at(obj):
        logger = logging.getLogger(__name__)
        # if transaction confirmed but image not exist, let the expired is None
        if obj.status == 2:
            return None

        expired_at = obj.created_at + timedelta(minutes=30)
        current_time: datetime = datetime.now()
        difference = (expired_at - current_time).total_seconds()
        if difference < 0:
            difference = 0
            return difference
        else:
            return difference

    @staticmethod
    def set_status(obj):
        return OrderStatus(obj.status).name
