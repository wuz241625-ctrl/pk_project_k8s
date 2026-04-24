from marshmallow import Schema, fields, validate, validates, validates_schema, ValidationError, post_load
from marshmallow.validate import Email, Length
from application.lakshmi_api.base import ApiError
import bcrypt
import string
import random
import uuid


class PartnerSchema(Schema):
    id = fields.Int()
    name = fields.String(required=True)
    email = fields.String(required=True)
    cellphone = fields.String(required=True)
    hash_trade = fields.String(required=True)
    balance = fields.Decimal(as_string=True, places=2)
    balance_frozen = fields.Decimal(as_string=True, places=2)
    balance_deposit = fields.Decimal(as_string=True, places=2)
    authentication_token = fields.String(required=True)
    invitation_code = fields.String(required=True)


class SignUpPartnerSchema(Schema):
    cellphone = fields.String()
    name = fields.String(allow_none=True)
    email = fields.Email(allow_none=True)

    phone = fields.String(load_only=True, required=True)

    hash_trade = fields.String()
    hash_login = fields.String()
    authentication_token = fields.String()

    otp = fields.String(load_only=True, required=True)
    password = fields.String(load_only=True, validate=Length(min=6))
    confirm_password = fields.String(load_only=True)
    invite_code = fields.String(load_only=True, validate=Length(min=8))
    certified = fields.Int()

    @validates_schema
    def validate_password(self, data, **kwargs):
        if data['password'] != data['confirm_password']:
            raise ApiError('Password confirmation does not match.')

    @post_load
    def set_values(self, data, **kwargs):
        data['cellphone'] = data['phone']
        data['hash_login'] = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        # data['hash_trade'] = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        data['authentication_token'] = str(uuid.uuid4())
        data['certified'] = 1

        return data


class ForgotPasswordPartnerSchema(Schema):
    cellphone = fields.String()
    password = fields.String(required=True, validate=Length(min=6))
    otp = fields.String(required=True)

    phone = fields.String(load_only=True, required=True)

    @post_load
    def set_values(self, data, **kwargs):
        data['cellphone'] = data['phone']

        return data


class SignInPartnerSchema(Schema):
    phone = fields.String(required=True)
    password = fields.String(required=True)


class MemberSchema(Schema):
    id = fields.Integer(required=True)
    name = fields.String()


# 定义Marshmallow序列化器
class PrizeSettingPartnerBeginnerTutorialTaskSchema(Schema):
    id = fields.Int()
    prize_id = fields.Int()
    name = fields.String()
    type = fields.Int()
    status_enable = fields.Int()
    description = fields.String()
    json_parameters = fields.String()

    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")

    # 码商是否已完成此步任务
    _is_finished = fields.Boolean()
    # 码商完成此步任务的时间
    _time_finished = fields.DateTime(attribute="time_finished", format="%Y-%m-%d %H:%M:%S")

