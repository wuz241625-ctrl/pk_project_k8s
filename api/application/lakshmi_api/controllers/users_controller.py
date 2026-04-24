import os
import uuid
import bcrypt
import math
import ipaddress

from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.schema.partner_schema import (PartnerSchema, SignUpPartnerSchema,
                                                           ForgotPasswordPartnerSchema, SignInPartnerSchema)
from application.lakshmi_api.services.partner_tree_service import PartnerTreeService

from application.lakshmi_api.services.redis_service import RedisService
from application.lakshmi_api.services.sms_service import SmsService
from application.lakshmi_api.services.websockets.user_service import UserPushService

from application.lakshmi_api.models.user import User, PartnerLoginLog

from sqlalchemy import update


class UsersHandler(BaseHandler):
    LOGIN_FAILED_COUNT_KEY = 'login_failed_count_{phone}'

    async def _validate_cellphone(self, cellphone):
        if cellphone is not None and cellphone != '':
            with self.db_orm.sessionmaker() as session:
                partner = session.query(User).filter_by(cellphone=cellphone).first()
                if partner:
                    raise ApiError('Phone number already exists')

    async def _verify_otp(self, partner):
        service = RedisService()
        valid_otp = await service.validate_sms_otp(partner['cellphone'], partner['otp'])

        if not valid_otp:
            raise ApiError('OTP is not valid')

    async def _send_otp(self, phone):
        sms_service = SmsService()
        redis_service = RedisService()
        cooldown_milliseconds = await redis_service.show_sms_otp_cooldown_in_millisecond(phone)
        if cooldown_milliseconds > 0:
            cooldown_seconds = math.ceil(cooldown_milliseconds / 1000)
            raise ApiError(f"Please try it again after {cooldown_seconds} seconds")
        if await sms_service.send_itniotech_sms(phone):
            await redis_service.set_sms_otp_cooldown(phone)
            if os.environ.get('RUN_ENV') == 'DEV':
                return {
                    "data": {
                        "otp_dev": sms_service.code,
                    }
                }
            else:
                return {
                    "data": {}
                }
        else:
            raise ApiError('Fail to sent OTP, please try again')

    async def _bind_invitation_code(self, partner, invite_code):
        with self.db_orm.sessionmaker() as session:
            parent_partner = session.query(User).filter_by(invitation_code=invite_code).first()

        if parent_partner:
            partner_service = PartnerTreeService()
            await partner_service.add_parent_partner(partner.id, parent_partner.id)
            partner_to_update = session.query(User).filter_by(id=partner.id).first()
            if partner_to_update:
                partner_to_update.pid = parent_partner.id
                session.commit()
        else:
            raise ApiError('Invalid partner code')

    async def _verify_invitation_code(self, invite_code):
        with self.db_orm.sessionmaker() as session:
            parent_partner = session.query(User).filter_by(invitation_code=invite_code).first()
            if not parent_partner:
                raise ApiError('Invalid Invitation Code')

    async def _verify_password_bcrypt(self, password, hashed_password, phone):
        if not bcrypt.checkpw(password.encode('utf8'), hashed_password.encode('utf8')):
            current_failed_key = self.LOGIN_FAILED_COUNT_KEY.format(phone=phone)
            current_failed_num = await self.redis.get(current_failed_key)
            if current_failed_num:
                current_failed_num = int(current_failed_num) + 1
            else:
                current_failed_num = 1
            await self.redis.set(current_failed_key, current_failed_num, 60 * 60 * 2)
            raise ApiError('recheck your phone or password')

    def _filter_request_params(self, keys):
        data = {}
        for key in keys:
            data[key] = self.get_body_argument(key, default=None)

        return data


class SignUpOtpVerification(UsersHandler):

    @handle_errors
    async def post(self):
        invite_code = self.get_body_argument('invite_code')
        phone = self.get_body_argument('cellphone')
        phone_key_exists = await self.redis.exists(f"otp_number_{phone}")
        ip_key_exists = await self.redis.exists(f"otp_ip_{await self.get_ip()}")
        if phone_key_exists or ip_key_exists:
            self.set_status(429)
            self.write({"error": {"message": "Too many requests. Please try again later."}})
            return
        await self.redis.set(f"otp_number_{phone}", 1, 60)
        await self.redis.set(f"otp_ip_{await self.get_ip()}", 1, 60)
        await self._verify_invitation_code(invite_code)
        await self._validate_cellphone(phone)
        # Todo: add timer to prevent sending multiple OTP in the same number
        response = await self._send_otp(phone)
        if response is not None:
            response['data']['sign_up_path'] = '/api/v1/users/sign_up'
            response['data']['otp'] = True
            response['data']['otp_digits'] = 4
            self.write(response)


class SignUp(UsersHandler):

    @handle_errors
    async def post(self):
        user_params = self._partner_params()
        user = SignUpPartnerSchema().load(user_params)
        await self._verify_invitation_code(user_params['invite_code'])
        await self._validate_cellphone(user['cellphone'])
        await self._verify_otp(user)

        user = SignUpPartnerSchema().dump(user)
        with self.db_orm.sessionmaker() as session:
            new_user = User(**user)
            session.add(new_user)
            session.commit()

            await self._bind_invitation_code(new_user, user_params['invite_code'])
            serialized_data = PartnerSchema().dump(new_user)
            self.write({"data": {"user": serialized_data}})

    def _partner_params(self):
        return self._filter_request_params(['otp', 'phone', 'name', 'email', 'password',
                                            'confirm_password', 'invite_code'])


class SignIn(UsersHandler):
    async def log_partner_login(self, partner_id):
        ip = await self.get_ip()
        ref = self.request.headers.get('Referer')
        try:
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.version == 4:
                loc = '-'.join(self.application.ipip.find(ip, 'CN'))
            else:
                loc = 'IPv6地址'
        except Exception:
            loc = '-'

        with self.db_orm.sessionmaker() as session:
            login_log = PartnerLoginLog(
                partner_id=partner_id,
                ip=ip,
                ref=ref,
                loc=loc,
            )
            session.add(login_log)
            session.commit()
            self.logger.info(f'用户 {partner_id} 登录成功，IP: {ip}, 归属地: {loc}, 请求来源: {ref}')

    @handle_errors
    async def post(self):
        partner_schema = SignInPartnerSchema().load(self._params())
        self.logger.info("Request [POST] (/users/sign_in), params: %s", partner_schema)
        # 从redis取得登录失败的次数，超过3次禁止登录2小时，redis缓存时间是2小时
        current_failed_key = self.LOGIN_FAILED_COUNT_KEY.format(phone=partner_schema['phone'])
        current_failed_num = await self.redis.get(current_failed_key)
        if current_failed_num and int(current_failed_num) >= 3:
            self.logger.info('用户 {} 登录失败超过3次，限制登录'.format(partner_schema['phone']))
            raise ApiError('Try too many times, try again after two hours.')

        with self.db_orm.sessionmaker() as session:
            user = session.query(User).filter(User.cellphone == partner_schema['phone']).first()
            if user is None:
                raise ApiError('No Account Match')
            await self._verify_password_bcrypt(partner_schema['password'], user.hash_login, partner_schema['phone'])
            user.authentication_token = str(uuid.uuid4())
            session.commit()
            service = UserPushService()
            await service.disconnect_user_channel(user.id)
            serialized_data = PartnerSchema().dump(user)
            self.logger.info("Response [POST] (/users/sign_in), params: %s, responseData: %s", partner_schema, serialized_data)
            await self.log_partner_login(user.id)
            self.write({"data": {"user": serialized_data}})

    def _params(self):
        return self._filter_request_params(['phone', 'password'])


class Otp(UsersHandler):

    @handle_errors
    async def post(self):
        # Todo: add timer to prevent sending multiple OTP in the same number
        phone = self.get_body_argument('phone')
        with self.db_orm.sessionmaker() as session:
            partner = session.query(User).filter_by(cellphone=phone).first()
            if partner is None:
                raise ApiError("Phone number is either incorrect or doesn't exist.")
            else:
                response = await self._send_otp(partner.cellphone)
                if response is not None:
                    response['data']['reset_password_path'] = '/api/v1/users/forgot_password'
                    response['data']['otp'] = True
                    response['data']['otp_digits'] = 4
                    self.write(response)


class ForgotPassword(UsersHandler):

    @handle_errors
    async def put(self):
        await self.forgot_password()

    @handle_errors
    async def patch(self):
        await self.forgot_password()

    async def forgot_password(self):
        partner_schema = ForgotPasswordPartnerSchema().load(self._params())
        await self._verify_otp(partner_schema)
        with self.db_orm.sessionmaker() as session:
            user = session.query(User).filter_by(cellphone=partner_schema['cellphone']).first()
            hashed_password = bcrypt.hashpw(partner_schema['password'].encode('utf-8'), bcrypt.gensalt()).decode(
                'utf-8')
            session.execute(
                update(User)
                .where(User.id == user.id)
                .values(hash_login=hashed_password)
            )
            session.commit()

            service = RedisService()
            await service.delete_sms_otp(partner_schema['cellphone'])
            self.write({"data": {"message": "success"}})

    def _params(self):
        return self._filter_request_params(['otp', 'phone', 'password'])


class SignOut(BaseHandler):
    @handle_errors
    async def delete(self):
        await self.authenticate_current_user()

        with self.db_orm.sessionmaker() as session:
            session.execute(
                update(User)
                .where(User.id == self.current_user.id)
                .values(authentication_token=None)
            )
            session.commit()
            service = UserPushService()
            await service.disconnect_user_channel(self.current_user.id)
            self.write({"data": {"message": "success"}})
