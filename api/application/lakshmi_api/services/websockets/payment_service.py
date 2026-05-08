import json
import os
import random
import time

from sqlalchemy.orm import joinedload

import global_resources
from application.lakshmi_api.base import ApiError
from application.lakshmi_api.enums.payment_login_progress import PaymentLoginProgress
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.schema.payment_schema import UpiPaymentSchema
from application.lakshmi_api.services.payment_services import BANK_SERVICES
from application.lakshmi_api.services.error_manager import ErrorManager
from application.lakshmi_api.exceptions.api_error import NewApiError

# 各银行输入OTP的位数；当前 EasyPaisa/JazzCash 使用默认 4 位兼容流程。
OTP_DIGITS = {}


class PaymentPushService:
    def __init__(self):
        self.db_orm = global_resources.db_orm
        self.redis = global_resources.redis
        self.redis_pub = global_resources.redis_pub
        self.logger = global_resources.logger
        self.error_manager = ErrorManager()

    async def payment_information(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            current_payment = session.query(Payment).options(joinedload(Payment.user)).filter_by(id=payment_id).first()
            if current_payment is not None:
                user = current_payment.user
                service_class = BANK_SERVICES[current_payment.bank.name]
                service = service_class(self.db_orm, self.redis, self.redis_pub, self.logger)
                personal_channel_name = "user_channel_{}".format(user.id)
                raw_payment = UpiPaymentSchema().dump(current_payment)
                if os.environ.get('RUN_ENV') == 'DEV':
                    raw_payment['place_order_status'] = random.choice([True, False])
                    raw_payment['selling_order_status'] = random.choice([True, False])
                    raw_payment['lock_status'] = random.choice([True, False])
                    raw_payment['status'] = random.choice(['active', 'inactive'])
                    raw_payment['selling'] = random.choice(['active', 'inactive'])
                else:
                    raw_payment['place_order_status'] = await service.place_order_status(current_payment.id)
                    raw_payment['selling_order_status'] = await service.selling_order_status(current_payment.id)
                    raw_payment['lock_status'] = await service.lock_status(current_payment.id)
                    raw_payment['status'] = await service.status_to_word(current_payment.status)
                    raw_payment['selling'] = await service.status_to_word(current_payment.certified)
                publishData = {
                    "type": "payment_information",
                    "content": "success",
                    "data": {
                        "user": PartnerSchema().dump(user),
                        "payment": raw_payment,
                    }
                }
                self.logger.info(
                    "payment_information(), payment_id: %s, publishData: %s",
                    payment_id, publishData)
                num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(publishData), retry = True)
                return num_clients
            else:
                self.logger.error(
                    "payment_information(), payment_id: %s, errorMsg: %s",
                    payment_id, 'Payment not found')
                
                # 使用标准错误码抛出结构化异常
                raise NewApiError('10301')  # 激活请求失败
    
    """
    取消一个payment获取UPI的通知
    """
    async def notify_cancel_payment_get_upi(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            current_payment = session.query(Payment).options(joinedload(Payment.user)).filter_by(id=payment_id).first()
            if current_payment is not None:
                user = current_payment.user
                service_class = BANK_SERVICES[current_payment.bank.name]
                service = service_class(self.db_orm, self.redis, self.redis_pub, self.logger)
                personal_channel_name = "user_channel_{}".format(user.id)
                raw_payment = UpiPaymentSchema().dump(current_payment)
                if os.environ.get('RUN_ENV') == 'DEV':
                    raw_payment['place_order_status'] = random.choice([True, False])
                    raw_payment['selling_order_status'] = random.choice([True, False])
                    raw_payment['lock_status'] = random.choice([True, False])
                    raw_payment['status'] = random.choice(['active', 'inactive'])
                    raw_payment['selling'] = random.choice(['active', 'inactive'])
                else:
                    raw_payment['place_order_status'] = await service.place_order_status(current_payment.id)
                    raw_payment['selling_order_status'] = await service.selling_order_status(current_payment.id)
                    raw_payment['lock_status'] = await service.lock_status(current_payment.id)
                    raw_payment['status'] = await service.status_to_word(current_payment.status)
                    raw_payment['selling'] = await service.status_to_word(current_payment.certified)
                publishData = {
                    "type": "cancel_payment_get_upi",
                    "content": "success",
                    "data": {
                        "user": PartnerSchema().dump(user),
                        "payment": raw_payment,
                    }
                }
                self.logger.info("notify_cancel_payment_get_upi(), payment_id: %s, publishData: %s", payment_id, publishData)
                num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(publishData), retry = True)
                return num_clients
            else:
                self.logger.info("notify_cancel_payment_get_upi(), payment_id: %s, errorMsg: %s", payment_id, 'Payment not found')
                # 使用标准错误码抛出结构化异常
                raise NewApiError('10301')  # 激活请求失败

    """
    绑定upi成功的通知
    """
    async def notify_payment_bind_upi_success(self, payment_id):
        with self.db_orm.sessionmaker() as session:
            current_payment = session.query(Payment).options(joinedload(Payment.user)).filter_by(
                id=payment_id).first()
            if current_payment is not None:
                user = current_payment.user
                service_class = BANK_SERVICES[current_payment.bank.name]
                service = service_class(self.db_orm, self.redis, self.redis_pub, self.logger)
                personal_channel_name = "user_channel_{}".format(user.id)
                raw_payment = UpiPaymentSchema().dump(current_payment)
                if os.environ.get('RUN_ENV') == 'DEV':
                    raw_payment['place_order_status'] = random.choice([True, False])
                    raw_payment['selling_order_status'] = random.choice([True, False])
                    raw_payment['lock_status'] = random.choice([True, False])
                    raw_payment['status'] = random.choice(['active', 'inactive'])
                    raw_payment['selling'] = random.choice(['active', 'inactive'])
                else:
                    raw_payment['place_order_status'] = await service.place_order_status(current_payment.id)
                    raw_payment['selling_order_status'] = await service.selling_order_status(current_payment.id)
                    raw_payment['lock_status'] = await service.lock_status(current_payment.id)
                    raw_payment['status'] = await service.status_to_word(current_payment.status)
                    raw_payment['selling'] = await service.status_to_word(current_payment.certified)
                publishData = {
                    "type": "payment_bind_upi_success",
                    "content": "success",
                    "data": {
                        "user": PartnerSchema().dump(user),
                        "payment": raw_payment,
                    }
                }
                self.logger.info("notify_payment_bind_upi_success(), payment_id: %s, publishData: %s", payment_id, publishData)
                num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(publishData), retry = True)
                return num_clients
            else:
                self.logger.info("notify_payment_bind_upi_success(), payment_id: %s, errorMsg: %s", payment_id, 'Payment not found')
                # 使用标准错误码抛出结构化异常
                raise NewApiError('10301')  # 激活请求失败

    async def opt_information(self, payment_id, status=True, error_message=None):
        # so far the data is useless, control the OTP input box from API
        with self.db_orm.sessionmaker() as session:
            current_payment = session.query(Payment).options(joinedload(Payment.user),
                                                             joinedload(Payment.bank)).filter_by(id=payment_id).first()
        self.logger.info("INTO opt_information(), payment_id: %s, current_payment: %s", payment_id, current_payment)
        self.logger.info("INTO opt_information(), payment_id: %s, current_payment.bank.name: %s", payment_id, current_payment.bank.name)
        if current_payment is not None:
            user = current_payment.user
            personal_channel_name = "user_channel_{}".format(user.id)
            if status:
                otp_digits = OTP_DIGITS.get(current_payment.bank.name, 4)
                publishData = {
                    "type": "payment_opt_notify",
                    "content": "success",
                    "is_success": True,
                    "data": {
                        "bank_name": current_payment.bank.name,
                        "otp": True,
                        "otp_digits": otp_digits,
                        "active_path": f"/api/v1/user/upi/{current_payment.id}/active",
                    }
                }
            else:
                publishData = {
                    "type": "payment_opt_notify",
                    "content": "fail",
                    "is_success": False,
                    "message": error_message
                }
            # 把发送OTP的结果数据保存至缓存
            redis_key = f"payment_protocol_status_notify:{PaymentLoginProgress.STATUS_OF_SENDING_OTP.name.lower()}:{payment_id}"
            await self.redis.set(redis_key, json.dumps(publishData), 600)
            num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(publishData), retry = True)
            self.logger.info("INTO opt_information(), payment_id: %s, personal_channel_name: %s, current_payment.bank.name: %s, publishData: %s", payment_id, personal_channel_name, current_payment.bank.name, publishData)
            return num_clients
        else:
            # 使用标准错误码抛出结构化异常
            raise NewApiError('10301')  # 激活请求失败

    """
    payment登录的pin验证
    """
    async def payment_pin_verify(self, payment_id, error_code = None, error_msg = None):
        # so far the data is useless, control the OTP input box from API
        with self.db_orm.sessionmaker() as session:
            current_payment = session.query(Payment).options(joinedload(Payment.user),
                                                             joinedload(Payment.bank)).filter_by(id=payment_id).first()
        self.logger.info("INTO opt_information(), payment_id: %s, current_payment: %s", payment_id, current_payment)
        publishData = None
        if current_payment is not None:
            personal_channel_name = "user_channel_{}".format(current_payment.user.id)
            if error_code is None and error_msg is None:
                publishData = {
                    "type": "payment_pin_verify",
                    "content": "success",
                    "payment_id": payment_id
                }
            else:
                publishData = {
                    "type": "payment_pin_verify",
                    "content": "fail",
                    "payment_id": payment_id,
                    "error_code": error_code,
                    "error_msg": error_msg
                }
            num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(publishData), retry = True)
            self.logger.info("INTO payment_pin_verify(), payment_id: %s, publishData: %s", payment_id, publishData)
            return num_clients
        else:
            # 使用标准错误码抛出结构化异常
            raise NewApiError('10301')  # 激活请求失败
            
    async def send_sms_info_to_client(self, payment_id, to_phone, content, error_code, error_msg):
        # so far the data is useless, control the OTP input box from API
        with self.db_orm.sessionmaker() as session:
            # bank = session.query(BankType).filter_by(name=bank_name).first()
            current_payment = session.query(Payment).options(joinedload(Payment.user),
                                                             joinedload(Payment.bank)).filter_by(id = payment_id).first()
        if current_payment is None:
            # 使用标准错误码抛出结构化异常
            raise NewApiError('10301')  # 激活请求失败
        else:
            user = current_payment.user

            redis_key_send_sms = f"payment_protocol_status_notify:{PaymentLoginProgress.DATA_TO_SEND_SMS.name.lower()}:{payment_id}"

            # 协议端不正常
            if error_msg or error_code:
                # 删除缓存
                redis_key_upi_active_payment = f"upi_active_payment:{payment_id}"
                delete_result = await self.redis.delete(redis_key_upi_active_payment)
                self.logger.info(f"payment.id: {payment_id}, 发送短信的号码及内容，获取失败 code:{error_code}, msg:{error_msg}, delete_result: {delete_result}")

                socket_data = {
                    "type": "to_send_sms",
                    "is_success": False,
                    "error_msg": error_msg,
                    "error_code": error_code,
                    "data": {
                        "payment_id": payment_id
                    }
                }
            # 协议端正常
            else:
                value = {
                    "payment_id": payment_id,
                    "bank_name": current_payment.bank.name,
                    "phone": current_payment.phone,
                    "to_phone": to_phone,
                    "content": content,
                }

                socket_data = {
                    "type": "to_send_sms",
                    "is_success": True,
                    "data": {
                        "payment_id": current_payment.id,
                        "from_phone": current_payment.phone,
                        "to_phone": to_phone,
                        "content": content
                    }
                }

                self.logger.info(
                    f"payment.id: {payment_id}, 发送短信的号码及内容，获取成功 to_phone:{to_phone}, content:{content}"
                    f"写入redis: {redis_key_send_sms}, value: {value}"
                    f"socket数据：{socket_data}"
                )

            await self.redis.set(redis_key_send_sms, json.dumps(socket_data), 60)

            personal_channel_name = "user_channel_{}".format(user.id)
            num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(socket_data), retry=True)

            self.logger.info(
                f"payment.id: {payment_id}, 发送短信的号码及内容，结果通知 num_clients: {num_clients}, socket_data: {socket_data}"
            )
            result = {
                "payment_id": current_payment.id,
                "num_clients": num_clients
            }
            return result

    async def publish_message(self, channel, message: str, times: int = 1, retry: bool = False):
        num_clients = await self.redis_pub.publish(
            channel,
            message
        )
        if not retry:
            return num_clients
        self.logger.info(f"推送消息给客户端，channel:{channel}, message:{message}, times:{times}, num_clients: {num_clients}")
        if times > 10:
            return num_clients
        time.sleep(0.3)
        if num_clients == 0:
            return await self.publish_message(channel, message, times = times + 1, retry = retry)
        return num_clients

    async def payment_protocol_status_notify(self, payment_id, type, is_success, error_code, error_msg):
        # so far the data is useless, control the OTP input box from API
        with self.db_orm.sessionmaker() as session:
            # bank = session.query(BankType).filter_by(name=bank_name).first()
            current_payment = session.query(Payment).options(joinedload(Payment.user),
                                                             joinedload(Payment.bank)).filter_by(id = payment_id).first()
        if current_payment is None:
                # 使用标准错误码抛出结构化异常
                raise NewApiError('10301')  # 激活请求失败
        else:
            user = current_payment.user
            bank = current_payment.bank
            socket_data = {
                "type": type,
                "is_success": is_success,
                "error_code": error_code,
                "error_msg": error_msg,
                "data": {
                    "payment_id": payment_id,
                    "partner_id": user.id,
                    "bank_id": bank.id,
                    "bank_name": bank.name.lower(),
                    "payment_phone": current_payment.phone
                }
            }
            # 写入缓存 协议通知过来的数据
            redis_key_payment_protocol_status_notify_type = f"payment_protocol_status_notify:{type}:{payment_id}"
            value_setex = await self.redis.setex(redis_key_payment_protocol_status_notify_type, 60, json.dumps(socket_data))
            self.logger.info(f"payment_protocol_status_notify(), 写入缓存：{redis_key_payment_protocol_status_notify_type}: {socket_data}, 写入结果: {value_setex}")
            personal_channel_name = "user_channel_{}".format(user.id)
            # 向redis发布消息，发送socket通知给前端
            num_clients = await self.publish_message(channel = personal_channel_name, message = json.dumps(socket_data), retry=True)
            self.logger.info(f"request /websocket/payment_protocol_status_notify, redis publish channel: {personal_channel_name}, message: {socket_data}, 接收到消息的客户端的数量: {num_clients}")
            socket_data['data']['num_clients'] = num_clients
            return socket_data
