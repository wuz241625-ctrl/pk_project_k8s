from application.lakshmi_api.services.payments.e_wallet_handler import *


class UlCashPayService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_ulcash"
    OTP_PREFIX = "login_ulcash_OTP"
    LOGOUT_PREFIX = "login_off_ulcash"
    ONLINE_PREFIX = "login_on_ulcash"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'ulcash', False)
