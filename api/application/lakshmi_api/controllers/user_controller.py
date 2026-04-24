from decimal import Decimal

import bcrypt
from sqlalchemy import text
from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.models.user import User
from application.lakshmi_api.controllers.users_controller import UsersHandler
from application.lakshmi_api.services.redis_service import RedisService


class Show(BaseHandler):

    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        with self.db_orm.sessionmaker() as session:
            user = session.query(User).filter_by(id=self.current_user.id).first()
        deduction_balance = await self._deduct_frozen_orders_amount(self.current_user.id)
        user.balance = max(Decimal(user.balance) - Decimal(deduction_balance), Decimal(0))
        # 判断并设置 is_setpassword
        if user.hash_trade:
            user.is_setpassword = True
        else:
            user.is_setpassword = False
        # 获取并添加 is_setpassword 到用户数据中
        user_data = PartnerSchema().dump(user)
        user_data['is_setpassword'] = user.is_setpassword  # 添加 is_setpassword 字段
        self.write({
            "data": {
                "user": user_data,
            }
        })

    async def _deduct_frozen_orders_amount(self, partner_id) -> Decimal:
        query = text(
            'select ifnull(sum(amount), 0) as deduction_balance from bank_record where payment_id in (select id from payment where partner_id = :pid) and callback=0 and trade_type=1 and invalid=0 and if_ew=0')
        with self.db_orm.sessionmaker() as session:
            result = session.execute(query, {'pid': partner_id})
            row = result.fetchone()
            deduction_balance = row[0]
            return deduction_balance


class GetOtp(UsersHandler):
    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        response = await self._send_otp(self.current_user.cellphone)
        if response is not None:
            response['data']['message'] = "OTP send successfully"
            response['data']['cooldown'] = 60000
            self.write(response)


class ChangePaymentPassword(UsersHandler):
    @handle_errors
    async def post(self):
        await self.authenticate_current_user()
        payment_password = self.get_body_argument('payment_password')
        confirm_payment_password = self.get_body_argument('confirm_payment_password')
        otp = self.get_body_argument('otp')

        # payment password and confirm_payment_password same
        if payment_password != confirm_payment_password:
            raise ApiError('payment password and confirmation password do not match')

        # verify OTP
        redis_service = RedisService()
        valid_otp = await redis_service.validate_sms_otp(self.current_user.cellphone, otp)
        if valid_otp:
            await redis_service.delete_sms_otp(self.current_user.cellphone)
        else:
            raise ApiError('invalid otp')

        # update payment password
        with self.db_orm.sessionmaker() as session:
            user = session.query(User).filter_by(id=self.current_user.id).first()
            user.hash_trade = bcrypt.hashpw(payment_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            session.commit()
        self.write({
            "data": {
                "message": "payment password change success"
            }
        })
