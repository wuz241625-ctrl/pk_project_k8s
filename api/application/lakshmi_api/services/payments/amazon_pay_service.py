import json
from datetime import datetime

from application.lakshmi_api.base import ApiError, ApiInfo
from application.lakshmi_api.services.payments.e_wallet_handler import EWalletHandler

class AmazonService(EWalletHandler):
    LOGIN_METHOD = 'webview'
    OTP_LIMIT_PREFIX = "login_amazon"
    OTP_PREFIX = "login_amazon_OTP"
    LOGOUT_PREFIX = "login_off_amazon"
    ONLINE_PREFIX = "login_on_amazon"

    def __init__(self, db_orm, redis, redis_pub, logger):
        super().__init__(db_orm, redis, redis_pub, logger)
        self.cookie = None
        self.headers = None

    def _verify_cookie(self):
        required_keys = [
            'ubid-acbin', 'lc-acbin', 'i18n-prefs',
            'x-acbin', 'at-acbin', 'sess-at-acbin', 'sst-acbin'
        ]
        for key in required_keys:
            if key not in self.cookie:
                raise ApiError(f"Amazon active fail, {key} is not in exist")

    async def handle_activation(self, payment):
        self.logger.info("INTO handle_activation(payment), payment: %s", payment)
        await self.validate_webview_login_status(payment)
        if self.cookie is None:
            raise ApiError('Please login first and click Done')
        new_login_key = f"login_amazon"

        # arrange cookie from parse json then convert to string key=value;
        self.cookie = json.loads(self.cookie)
        self.cookie = ';'.join([f"{key}={value}" for key, value in self.cookie.items()])
        self._verify_cookie()

        headers = json.loads(self.headers)
        lower_case_headers = {}
        for key in list(headers.keys()):
            new_key = key.lower()
            new_value = headers[key]
            new_value = new_value.replace('\\/', '/')
            lower_case_headers[new_key] = new_value

        new_login_data = {
            'id': payment.id,
            'partner_id': payment.user_id,
            'phone': payment.phone,
            'status': 'grabstatement',
            'time': int(datetime.now().timestamp()),
            'try_count': 0,
            'socks_ip': '',
            'to': 'amazon',
            'qr_channel': payment.channel,
            'cookie': self.cookie,
            'headers': lower_case_headers
        }

        new_login_data = json.dumps(new_login_data)

        submit_login = await self.redis.lpush(new_login_key, new_login_data)
        if not submit_login:
            raise ApiError(f"Amazon failed to activate")

        await self.redis.set(f"{self.OTP_LIMIT_PREFIX}_{payment.id}", '1', 5 * 60)

        return True

    async def validate_webview_login_status(self, payment):
        if payment.status:
            self.logger.error("INTO validate_webview_login_status(payment), payment: %s. AmazonPay is connected, you don't need KYC again.", payment)
            raise ApiError(f"AmazonPay is connected, you don't need KYC again.")

        limit_request_otp_key = f"{self.OTP_LIMIT_PREFIX}_{payment.id}"
        request_exists = await self.redis.get(limit_request_otp_key)
        limit_request_otp_ttl = await self.redis.ttl(limit_request_otp_key)
        # await self.redis.set(f"crawl_frequently_{payment.id}", 1, 60 * 10)
        self.logger.info("validate_webview_login_status(), payment: %s, limit_request_otp_key: %s, request_exists: %s, limit_request_otp_ttl: %s",
         payment, limit_request_otp_key, request_exists, limit_request_otp_ttl
         )
        hours, remainder = divmod(limit_request_otp_ttl, 3600)
        minutes, _ = divmod(remainder, 60)
        if request_exists:
            self.logger.error(
                "INTO validate_webview_login_status(payment), payment: %s. Please try %s mins later, we're processing your request.",
                payment, minutes)
            raise ApiInfo(f"Please try {minutes} mins later, we're processing your request.")
