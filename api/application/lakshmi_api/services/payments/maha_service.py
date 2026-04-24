from application.lakshmi_api.services.payments.e_wallet_handler import *


class MahaService(EWalletHandler):
    BANK_TYPE_ID = 90
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_maha"
    OTP_PREFIX = "login_maha_OTP"
    LOGOUT_PREFIX = "login_off_maha"
    ONLINE_PREFIX = "login_on_maha"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'maha', True)
