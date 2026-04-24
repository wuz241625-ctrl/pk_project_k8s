import random
import requests
import json
import os
import global_resources
from urllib.parse import quote


class SmsService:
    def __init__(self):
        self.code = None
        self.redis = global_resources.redis
        self.logger = global_resources.logger

    async def send_fast2_sms(self, phone):
        url = 'https://www.fast2sms.com/dev/bulkV2'
        code = "{:04d}".format(random.randint(0, 9999))
        await self.redis.set(phone, code, 300)

        try:
            payload = f'variables_values={code}&route=otp&numbers={phone}'
            headers = {
                'authorization': "dXLrW3tkRSimIqvT0HhBfxnueAFDwa6jUYbGy2EcV1gMNZKQplDqd1GK8NU6QRWYlOwIjr9zCB4omPL5",
                'Content-Type': "application/x-www-form-urlencoded",
                'Cache-Control': "no-cache",
            }
            if not os.environ.get('RUN_ENV') == 'DEV':
                self.logger.info(f'SMS send now: code: {code} to phone: {phone}')
                respond = requests.post(url, data=payload, headers=headers, timeout=5)
                self.logger.info(f'SMS sent result:{respond.text}, code: {code} to phone: {phone}')
                ret = json.loads(respond.text)
                if ret['message'] == ['SMS sent successfully.']:
                    return True
            else:
                self.code = code
                self.logger.info(f'SMS sent successfully, code: {code} to phone: {phone}')
                return True

        except Exception as e:

            self.logger.exception(f"send_fast2_sms_error:{str(e)}")
            return False

    # async def get_balance(self, phone):
    #     timestamp = int(time.time())
    #     s = "%s%s%s" % (api_key, api_pwd, str(timestamp))
    #     sign = hashlib.md5(s.encode(encoding='UTF-8')).hexdigest()
    #     headers = {
    #         'Content-Type': 'application/json;charset=utf-8',
    #         'Sign': sign,
    #         'Timestamp': str(timestamp),
    #         'Api-Key': api_key
    #     }
    #     url = "%s/getBalance" % base_url
    #     rsp = requests.get(url, headers=headers)
    #     if rsp.status_code == 200:
    #         res = json.loads(rsp.text)
    #         return res

    async def send_itniotech_sms(self, phone):
        code = "{:04d}".format(random.randint(0, 9999))
        await self.redis.set(phone, code, 300)
        url = "http://47.242.85.7:9090/sms/batch/v2"
        api_key = "k2D8aq"
        api_pwd = "LfsC8c"
        appid = "1000"
        content = f"Your verification code is {code}"
        phone = phone = phone.lstrip("0") if phone.startswith("0") else phone
        reqUrl = f'{url}?appkey={api_key}&appsecret={api_pwd}&appcode={appid}&phone=92{phone}&msg={quote(content)}'
        try:
            if not os.environ.get('RUN_ENV') == 'DEV':
                self.logger.info(f'SMS send now: {reqUrl}')
                respond = requests.get(reqUrl, timeout=5)
                self.logger.info(f'SMS sent result:{respond.text}, code: {code} to phone: {phone}')
                if respond.status_code == 200:
                    ret = json.loads(respond.text)
                    if ret.get('code') == '00000':
                        self.logger.info(f'SMS sent successfully, code: {code} to phone: {phone}')
                        return True
                    else:
                        self.logger.exception(f"send_sms_fail:{ret}")
                        return False
            else:
                self.code = code
                self.logger.info(f'SMS sent successfully, code: {code} to phone: {phone}')
                return True
        except Exception as e:
            self.logger.exception(f"send_sms_error:{str(e)}")
            return False
