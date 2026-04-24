from enum import Enum
from marshmallow import Schema, fields, validate


class OrderStatus(Enum):
    REVOKED = -1
    PENDING = 0
    PROCESSING = 1
    DONE = 2


class TransferOrderSchema(Schema):
    serial_number = fields.String(attribute="serial_number", required=True)
    amount = fields.Decimal(attribute="amount", as_string=True, places=2)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    status = fields.Method('set_status')
    user_id = fields.Integer(attribute="user_id", required=True)
    to_user_id = fields.Integer(attribute="to_user_id", required=True)

    @staticmethod
    def set_status(obj):
        return OrderStatus(obj.status).name
