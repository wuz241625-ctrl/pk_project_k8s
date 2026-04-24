from application.lakshmi_api.services.payments.e_wallet_handler import *


class EasyPaisaPayService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_easypaisa"
    OTP_PREFIX = "login_easypaisa_OTP"
    LOGOUT_PREFIX = "login_off_easypaisa"
    ONLINE_PREFIX = "login_on_easypaisa"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'easypaisa', True)
