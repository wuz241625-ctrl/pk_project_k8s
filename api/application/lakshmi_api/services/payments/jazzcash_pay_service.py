from application.lakshmi_api.services.payments.e_wallet_handler import *


class JazzCashPayService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_jazzcash"
    OTP_PREFIX = "login_jazzcash_OTP"
    LOGOUT_PREFIX = "login_off_jazzcash"
    ONLINE_PREFIX = "login_on_jazzcash"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'jazzcash', True)
