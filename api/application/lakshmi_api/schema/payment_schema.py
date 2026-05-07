from enum import Enum
import re
from marshmallow import Schema, fields, validate, ValidationError, post_dump

from application.lakshmi_api.schema.bank_schema import UpiBankSchema
from application.lakshmi_api.schema.today_withdraw_order_summary import TodayWithdrawOrderSummarySchema

OBJECT_STATUS = {0: 'inactive', 1: 'active'}


class StatusEnum(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


def check_status_value(value):
    if value not in (e.value for e in StatusEnum):
        raise ValidationError(f"{value} is not a valid value.")
    return value


def validate_indian_phone(number):
    print(number)
    if not re.match(r'\d{10}', number):
        raise ValidationError("Invalid Indian phone number.")


class PaymentSchema(Schema):
    id = fields.Int()
    name = fields.String(required=True)
    bank_name = fields.Function(lambda obj: obj.bank.name if obj.bank else None)
    upi = fields.String()
    account = fields.String(required=True)
    net_id = fields.String()
    email = fields.String(attribute="email")
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")


class UpiPaymentSchema(Schema):
    id = fields.Int(required=True)
    name = fields.String(required=True)
    bank_type_id = fields.String(attribute="bank_type_id")
    upi = fields.String()
    status = fields.Method('set_status')
    manual_status = fields.Boolean()
    selling = fields.Method('set_selling_status')
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    bank_name = fields.Method('set_bank_name')
    phone = fields.Method('phone_with_original')
    upi_list = fields.Method('split_string_by_comma')
    remarks = fields.String()
    bank = fields.Nested(UpiBankSchema)
    pin = fields.String(required=False)
    tpin_is_true = fields.Method('set_tpin_is_true')
    account_accno = fields.String(required=False, allow_none=True)
    account_iban = fields.String(required=False, allow_none=True)
    wallet_status = fields.Int(required=False, allow_none=True)
    collection_status = fields.Int(required=False, allow_none=True)
    payout_status = fields.Int(required=False, allow_none=True)

    @staticmethod
    def set_status(obj):
        return OBJECT_STATUS[obj.status]

    @staticmethod
    def set_tpin_is_true(obj):
        return obj.tpin_is_true == 1

    @staticmethod
    def set_selling_status(obj):
        return OBJECT_STATUS[obj.certified]

    @staticmethod
    def set_bank_name(obj):
        return obj.bank.name

    @staticmethod
    def phone_with_mask(obj):
        phone = obj.phone
        masked_phone = phone[:3] + '*' * (len(phone) - 6) + phone[-3:]
        return masked_phone

    @staticmethod
    def phone_with_original(obj):
        return obj.phone

    @staticmethod
    def split_string_by_comma(obj):
        if obj.upi_list:
            return obj.upi_list.split(',')
        else:
            return []

    @staticmethod
    def set_active_status(obj):
        # in db status is INT, so need to user == let it return True or False
        return obj.status == 1


class UpiPaymentSummarySchema(UpiPaymentSchema):
    today_withdraw_order_summary = fields.Nested(TodayWithdrawOrderSummarySchema)

    @post_dump
    def set_default_today_withdraw_order_summary(self, data, **kwargs):
        if data['today_withdraw_order_summary'] is None:
            data['today_withdraw_order_summary'] = {
                'total_orders': 0,
                'success_orders': 0,
                'fail_orders': 0,
            }
        return data


class CreateUpiSchema(Schema):
    bank_id = fields.Str(required=True, validate=validate.Length(min=1))
    name = fields.Str(required=True, validate=validate.Length(min=2))
    phone = fields.Str(required=True, validate=[validate.Length(min=10), validate_indian_phone])
    pin = fields.Str(required=False,allow_none=True)
    mpin = fields.Str(required=False,allow_none=True)
    tpin = fields.Str(required=False,allow_none=True)
    account = fields.Str(required=False,allow_none=True)
    net_pw = fields.Str(required=False,allow_none=True)
    mock = fields.Str(required=False,allow_none=True)


class UpiActiveSchema(Schema):
    status = fields.String(required=True, validate=[check_status_value, validate.Length(min=1)])
    otp = fields.String()
    upi = fields.String()
    mock = fields.String()


class UpiSellingSchema(Schema):
    certified = fields.String(required=True, validate=[check_status_value, validate.Length(min=1)])

"""
使用pin预登录
"""
class PinPreSignInSchema(Schema):
    payment_id = fields.Str(required=True, validate=validate.Length(min=1))
    pin = fields.Str(required=True, validate=validate.Length(min=1))
    mock = fields.Str(required=False,allow_none=True)

"""
修改tpin
"""
class PaymentTpinSchema(Schema):
    payment_id = fields.Str(required=True, validate=validate.Length(min=1))
    tpin = fields.Str(required=True, validate=validate.Length(min=4))


class PaymentAccountSelectSchema(Schema):
    accno = fields.Str(required=True, validate=validate.Length(min=1))

"""
payment UPI 变更历史
"""
class PaymentUpiHistorySchema(Schema):
    id = fields.Int(required=True)
    payment_id = fields.Int(required=True)
    partner_id = fields.Int(required=True)
    bank_id = fields.Int(required=True)
    upi = fields.String(required=True)
    time_create = fields.DateTime(required=True, attribute="time_create", format="%Y-%m-%d %H:%M:%S")
