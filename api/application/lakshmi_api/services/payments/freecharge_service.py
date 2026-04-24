from application.lakshmi_api.services.payments.e_wallet_handler import *


class FreechargeService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_freecharge"
    OTP_PREFIX = "login_freecharge_OTP"
    LOGOUT_PREFIX = "login_off_freecharge"
    ONLINE_PREFIX = "login_on_freecharge"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'freecharge', False)
