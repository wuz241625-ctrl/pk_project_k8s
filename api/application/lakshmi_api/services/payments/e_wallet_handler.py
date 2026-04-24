import json
from datetime import datetime

from application.easypaisa_runtime.reader import EasyPaisaRuntimeReader
from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService
from application.lakshmi_api.base import ApiError, ApiInfo
from application.lakshmi_api.models import Payment


async def shared_handle_activation(self, payment, otp_key, limit_request_otp_key):
    self.logger.info(
        "INTO shared_handle_activation(payment, otp_key, limit_request_otp_key), payment: %s, otp_key: %s, limit_request_otp_key: %s",
        payment, otp_key, limit_request_otp_key
    )
    otp_exists = await self.redis.get(otp_key)
    request_exists = await self.redis.get(limit_request_otp_key)
    limit_request_otp_ttl = await self.redis.ttl(limit_request_otp_key)

    self.logger.info(
        "INTO shared_handle_activation(payment, otp_key, limit_request_otp_key), %s: %s, %s: %s, limit_request_otp_ttl: %s",
        otp_key, otp_exists, limit_request_otp_key, request_exists, limit_request_otp_ttl
    )

    hours, remainder = divmod(limit_request_otp_ttl, 3600)
    minutes, _ = divmod(remainder, 60)
    # if ttl > 5 mins , that's mean system lock it
    if limit_request_otp_ttl > 5 * 60:
        if hours > 0:
            raise ApiInfo(
                f"Too many login/logout, for the safety of your account, please try {hours} hours {minutes} mins later")
        else:
            raise ApiInfo(f"Too many login/logout, for the safety of your account, please try {minutes} mins later")
    elif request_exists:
        raise ApiInfo(f"Please try {minutes} mins later, avoid too many request OTP.")
    elif request_exists and otp_exists:
        raise ApiInfo(f"We are connecting to the service ({payment.id}), please wait.")
    else:
        # TODO request OTP success need to notify
        await self.send_otp(payment)


async def shared_send_otp(self, payment, bank_name, redis_key, is_prepare_login):
    if payment.status:
        self.logger.warning(f"upi登录，发现重复登录 payment.id: {payment.id}, payment.status: {payment.status}")
        raise ApiError(f"{bank_name} is connected, you don't need KYC again.")
    else:
        new_login_key = f"login_{redis_key}"

        # 获取列表中的所有值，检查是否重复
        existing_values = await self.redis.lrange(new_login_key, 0, -1)
        for item in existing_values:
            try:
                cache_payment = json.loads(item)
                if payment.id == cache_payment.get("id", 0):
                    self.logger.warning(f"upi登录，发现重复登录 payment.id: {payment.id}, {new_login_key}: {item}")
                    raise ApiError(f"{bank_name} is connected, you don't need KYC again.")
            except ApiError as e:
                raise e
            except Exception as e:
                self.logger.error(f"发现无法转换为dict的数据：{item}, {e}")
                pass

        # 检查协议是否已登录
        login_bank_hash_key = f"login_{str(bank_name).lower()}_hash"
        try:
            login_bank_hash_exists = await self.redis.hexists(login_bank_hash_key, payment.id)
            if login_bank_hash_exists:
                login_bank_hash_value = await self.redis.hget(login_bank_hash_key, payment.id)
                self.logger.warning(f"upi登录，发现重复登录 payment.id: {payment.id}, {login_bank_hash_key}: {login_bank_hash_value}")
                raise ApiError(f"{bank_name} is connected, you don't need KYC again.")
        except ApiError as e:
            raise e
        except Exception as e:
            self.logger.error(f"检查协议是否已登录时出错：{login_bank_hash_key}, {e}")
            pass

        new_login_data = {
            'id': payment.id,
            'partner_id': payment.user_id,
            'phone': payment.phone,
            'status': 'prepare_login' if is_prepare_login and is_prepare_login == True else 'sendOTP',
            'time': int(datetime.now().timestamp()),
            'try_count': 0,
            'socks_ip': '',
            'to': redis_key,
            # 'qr_channel': 1002 if payment.account_type == 2 else 1001
            'qr_channel': payment.channel,
            'pin': payment.pin if is_prepare_login and is_prepare_login == True else None,
            'tpin': payment.tpin if is_prepare_login and is_prepare_login == True else None,
            'account': payment.account,
            'net_pw': payment.net_pw,
        }
        new_login_data = json.dumps(new_login_data)

        submit_login = await self.redis.lpush(new_login_key, new_login_data)
        if not submit_login:
            raise ApiError(f"{bank_name} failed to activate")

        key = f"login_{redis_key}_{payment.id}"
        await self.redis.set(key, '1', 5 * 60)


class EWalletHandler:
    EASYPAISA_BANK_TYPE_ID = 97
    LOGIN_METHOD = None
    LOGOUT_PREFIX = None
    OTP_LIMIT_PREFIX = None
    OTP_PREFIX = None
    ONLINE_PREFIX = None

    def __init__(self, db_orm, redis, redis_pub, logger):
        self.db_orm = db_orm
        self.redis = redis
        self.redis_pub = redis_pub
        self.logger = logger

    async def selling_active(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            payment = session.query(Payment).filter(Payment.id == payment_id).first()
            payment.certified = 1
            session.commit()
            await self.destroy_log_off_key(payment)
            await self._sync_easypaisa_collection_dispatch(payment, enabled=True, source="app_selling_active")
            if payment.certified == 1:
                return True
            else:
                return False

    async def selling_inactive(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            payment = session.query(Payment).filter(Payment.id == payment_id).first()
            payment.certified = 0
            session.commit()
            if payment.status:
                await self.push_log_off_key(payment)
            await self._sync_easypaisa_collection_dispatch(payment, enabled=False, source="app_selling_inactive")
            if payment.certified == 0:
                return True
            else:
                return False

    async def handle_activation(self, payment):
        limit_request_otp_key = f"{self.__class__.OTP_LIMIT_PREFIX}_{payment.id}"
        otp_key = f"{self.__class__.OTP_PREFIX}_{payment.id}"
        return await shared_handle_activation(self, payment, otp_key, limit_request_otp_key)

    async def push_login_otp_to_redis(self, payment, otp):
        key = f"{self.__class__.OTP_PREFIX}_{payment.id}"
        await self.redis.set(key, otp, 60 * 5)
        # TODO: refactor UserPushService
        personal_channel_name = "user_channel_{}".format(payment.user_id)
        await self.redis_pub.publish(
            personal_channel_name,
            json.dumps(
                {
                    "type": "push_message_to_user",
                    "content": "success",
                    "data": {
                        "message": f"OTP {otp} received: please wait. connecting to {payment.id}",
                        "icon": 'online_prediction',
                        "color": 'primary',
                        "position": 'center',
                        "timeout": 6000
                    }
                }
            )
        )

    async def push_log_off_key(self, payment):
        key = f"{self.__class__.LOGOUT_PREFIX}_{payment.id}"
        await self.redis.set(key, int(datetime.now().timestamp()), 190 * 60)

    async def destroy_log_off_key(self, payment):
        key = f"{self.__class__.LOGOUT_PREFIX}_{payment.id}"
        await self.redis.delete(key)

    def _use_easypaisa_runtime_reader(self):
        return self.__class__.ONLINE_PREFIX == "login_on_easypaisa"

    @staticmethod
    def _is_easypaisa_payment(payment):
        return str(getattr(payment, "bank_type_id", "")) == str(EWalletHandler.EASYPAISA_BANK_TYPE_ID)

    async def _sync_easypaisa_collection_dispatch(self, payment, *, enabled: bool, source: str):
        if not self._is_easypaisa_payment(payment):
            return
        runtime_service = EasyPaisaRuntimeService(self.redis)
        await runtime_service.set_collection_dispatch(
            payment.id,
            enabled=enabled,
            phone=getattr(payment, "phone", None),
            channels=getattr(payment, "channel", None),
            source=source,
        )

    # TODO: Fix use payment_id, different with others service problem
    async def selling_order_status(self, payment_id):
        if self._use_easypaisa_runtime_reader():
            reader = EasyPaisaRuntimeReader(self.redis)
            value = await reader.is_selling_order_online(payment_id)
            self.logger.info(
                f"selling_order_status() payment_id: {payment_id}, source: runtime_reader, value: {value}"
            )
            return value
        key = f"{self.__class__.ONLINE_PREFIX}_{payment_id}"
        value = await self.redis.get(key)
        self.logger.info(f"selling_order_status() payment_id: {payment_id}, key: {key}, value: {value}")
        return value is not None

    async def lock_status(self, payment_id):
        return await self.redis.get(f"orders_ds_limit_{payment_id}") is not None

    async def place_order_status(self, payment_id):
        if self._use_easypaisa_runtime_reader():
            reader = EasyPaisaRuntimeReader(self.redis)
            return await reader.is_place_order_online(payment_id)
        return await self.redis.sismember('payment_online_df', payment_id)

    @staticmethod
    async def status_to_word(status):
        if status == 0:
            return 'inactive'
        elif status == 1:
            return 'active'
