from application.lakshmi_api.services.payments.e_wallet_handler import *


class PhonepeService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_phonepe"
    OTP_PREFIX = "login_phonepe_OTP"
    LOGOUT_PREFIX = "login_off_phonepe"
    ONLINE_PREFIX = "login_on_phonepe"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'phonepe', False)
