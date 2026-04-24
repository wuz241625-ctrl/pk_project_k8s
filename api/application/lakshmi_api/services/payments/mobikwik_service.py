from application.lakshmi_api.services.payments.e_wallet_handler import *


class MobikwikService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_mobi"
    OTP_PREFIX = "login_mobi_OTP"
    LOGOUT_PREFIX = "login_off_mobi"
    ONLINE_PREFIX = "login_on_mobi"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'mobi', False)
