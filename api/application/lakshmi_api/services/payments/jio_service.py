from application.lakshmi_api.services.payments.e_wallet_handler import *


class JioService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_jio"
    OTP_PREFIX = "login_jio_OTP"
    LOGOUT_PREFIX = "login_off_jio"
    ONLINE_PREFIX = "login_on_jio"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'jio', False)
