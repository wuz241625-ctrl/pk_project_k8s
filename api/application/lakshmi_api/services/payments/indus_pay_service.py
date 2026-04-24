from application.lakshmi_api.services.payments.e_wallet_handler import *


class IndusPayService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_indus"
    OTP_PREFIX = "login_indus_OTP"
    LOGOUT_PREFIX = "login_off_indus"
    ONLINE_PREFIX = "login_on_indus"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'indus', True)
