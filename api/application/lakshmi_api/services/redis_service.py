import global_resources


class RedisService:
    def __init__(self):
        self.redis = global_resources.redis
        self.logger = global_resources.logger

    async def validate_sms_otp(self, phone, otp, universal=True):
        # 取消固定验证码，暂时注释
        # if universal:
            # selected_digits = phone[:2] + phone[-2:]
            # increments = [7, 5, 1, 8]
            # increased_digits = [(int(d) + inc) % 10 for d, inc in zip(selected_digits, increments)]
            # encrypt_number = ''.join(map(str, increased_digits))
            # if encrypt_number == otp:
                # return True

        phone_otp = await self.redis.get(phone)
        if phone_otp and otp == phone_otp:
            await self.redis.delete(phone)  # 验证通过立即删除，避免下次使用
            return True
        else:
            await self.validate_sms_otp_attempts_count(phone, phone_otp)
            return False

    async def validate_sms_otp_attempts_count(self, phone, phone_otp):
        # 记录验证错误次数，第3次错误直接清空验证码
        phone_otp_attempts_key = 'phone_otp_attempts_{}'.format(phone)
        phone_otp_attempts_count = await self.redis.get(phone_otp_attempts_key)
        if phone_otp_attempts_count:
            phone_otp_attempts_count = int(phone_otp_attempts_count) + 1
            if phone_otp_attempts_count >= 3:
                if phone_otp:
                    self.logger.warning('手机号 {} 3次输错验证码，删除redis中此手机号验证码'.format(phone))
                    await self.redis.delete(phone)
            else:
                await self.redis.set(phone_otp_attempts_key, phone_otp_attempts_count, 60 * 5)
        else:
            await self.redis.set(phone_otp_attempts_key, 1, 60 * 5)

    async def delete_sms_otp(self, phone):
        await self.redis.delete(phone)

    async def set_sms_otp_cooldown(self, phone):
        cooldown_key = f"{phone}_cooldown"
        await self.redis.setex(cooldown_key, 60, 1)

    async def show_sms_otp_cooldown_in_millisecond(self, phone):
        cooldown_key = f"{phone}_cooldown"
        ttl = await self.redis.pttl(cooldown_key)
        return ttl
