from application.lakshmi_api.services.payments.e_wallet_handler import *


class AirtelService(EWalletHandler):
    LOGIN_METHOD = 'OTP'
    OTP_LIMIT_PREFIX = "login_airtel"
    OTP_PREFIX = "login_airtel_OTP"
    LOGOUT_PREFIX = "login_off_airtel"
    ONLINE_PREFIX = "login_on_airtel"

    async def send_otp(self, payment):
        return await shared_send_otp(self, payment, payment.bank.name, 'airtel', False)
