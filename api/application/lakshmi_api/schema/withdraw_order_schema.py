from typing import Type

from marshmallow import Schema, fields
from application.lakshmi_api.schema.payment_schema import PaymentSchema
from enum import Enum


class OrderStatus(Enum):
    UNKNOWN = -2
    REVOKED = -1
    PENDING = 0
    PROCESSING = 1
    INSPECTING = 2
    CONFIRMED = 3
    DONE = 4


class WithdrawOrderSchema(Schema):
    utr = fields.String(required=True)
    amount = fields.Decimal(as_string=True, places=2)
    serial_number = fields.String(attribute="serial_number", required=True)
    benefit = fields.Decimal(attribute="benefit", as_string=True, places=2)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    paid_at = fields.DateTime(attribute="paid_at", format="%Y-%m-%d %H:%M:%S")
    payment = fields.Nested(PaymentSchema)
    status = fields.Method('set_status')

    @staticmethod
    def set_status(obj):
        return OrderStatus(obj.status).name


class UnfulfilledSchema(Schema):
    id = fields.Int(required=True)
    utr = fields.String(required=True)
    amount = fields.Decimal(as_string=True, places=2)
    created_at = fields.DateTime(attribute="time_create", format="%Y-%m-%d %H:%M:%S")
    serial_number = fields.Str(attribute="ew_code")
    void = fields.Boolean(attribute='invalid')
    status = fields.Method('_set_status')

    def _set_status(self, obj):
        if obj.invalid:
            if obj.ew_code:
                return 'returned'
            else:
                return 'revoked'
        elif not obj.invalid:
            if obj.ew_code:
                return 'deducted'
            else:
                return 'pending'
