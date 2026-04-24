from datetime import datetime
from typing import List

from application.lakshmi_api.base import BaseHandler
from application.lakshmi_api.base_websocket import WebsocketBaseHandler
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.models import DepositOrder, DepositOrderCancel, Payment
from application.lakshmi_api.schema.deposit_order_schema import OrderStatus
from application.lakshmi_api.services.websockets import *
from application.lakshmi_api.websocket.partner import Websocket
from constants import RedisKeys


class PushUserInformation(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['id'])
        partner_id = params['id']
        service = UserPushService()
        num_clients = await service.user_information(partner_id)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )


class PublishEveryone(WebsocketBaseHandler):
    async def post(self):
        params = self._get_params(['message'])
        message = params["message"]

        params = self._get_params(['icon', 'color', 'position', 'timeout'])
        params = {k: v for k, v in params.items() if v is not None}
        service = UserPushService()
        num_clients = await service.publish_everyone(message, **params)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )


class PushMessageToUser(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['message', 'id'])
        message = params["message"]
        partner_id = params["id"]

        params = self._get_params(['icon', 'color', 'position', 'timeout'])
        params = {k: v for k, v in params.items() if v is not None}
        service = UserPushService()
        num_clients = await service.push_message_to_user(partner_id, message, **params)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )


class PushPaymentInformation(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['id'])
        payment_id = params["id"]
        self.logger.info("Request [POST] (/websocket/push_payment_information), payment_id: %s", payment_id)
        service = PaymentPushService()
        num_clients = await service.payment_information(payment_id)
        responseData = {
            "data": {
                "message": 'Success',
                "num_clients": num_clients
            }
        }
        self.logger.info("Response [POST] (/websocket/push_payment_information), payment_id: %s, responseData: %s", payment_id, responseData)
        self.write(responseData)

"""
取消一个payment获取UPI的通知
"""
class PushCancelPaymentGetUPINotify(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['id'])
        payment_id = params["id"]
        self.logger.info("Request [POST] (/websocket/push_cancel_payment_get_upi), payment_id: %s", payment_id)
        service = PaymentPushService()
        num_clients = await service.notify_cancel_payment_get_upi(payment_id)
        responseData = {
            "data": {
                "message": 'Success',
                "num_clients": num_clients
            }
        }
        self.logger.info("Response [POST] (/websocket/push_cancel_payment_get_upi), payment_id: %s, responseData: %s", payment_id, responseData)
        self.write(responseData)

"""
绑定upi成功的通知
"""
class PushPaymentBindUpiSuccessNotify(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['id'])
        payment_id = params["id"]
        self.logger.info("Request [POST] (/websocket/push_cancel_payment_get_upi), payment_id: %s", payment_id)
        service = PaymentPushService()
        num_clients = await service.notify_payment_bind_upi_success(payment_id)
        responseData = {
            "data": {
                "message": 'Success',
                "num_clients": num_clients
            }
        }
        self.logger.info("Response [POST] (/websocket/push_cancel_payment_get_upi), payment_id: %s, responseData: %s", payment_id, responseData)
        self.write(responseData)


"""
弹出OTP的输入窗口（otp发送成功）
"""
class PushUpiOtpSuccessNotify(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['id'])
        payment_id = params["id"]
        websocket = Websocket(application=self.application, request = self.request)
        connected_count = await websocket.get_connected_clients_count()
        # 获取所有在线用户ID
        online_users = await websocket.get_connected_user_ids()
        self.logger.info("Request [POST] (/websocket/push_upi_opt_success), payment_id: %s, connected_count: %s, online_users: %s", payment_id, connected_count, online_users)
        service = PaymentPushService()
        num_clients = await service.opt_information(payment_id)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )

"""
php中otp发送失败
"""
class PushUpiOtpFailNotify(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['id', 'error_message'])
        payment_id = params["id"]
        payment_error_message = params["error_message"]
        service = PaymentPushService()
        self.logger.info("Request [POST] (/websocket/push_upi_opt_fail), payment_id: %s, payment_error_message: %s", payment_id, payment_error_message)
        num_clients = await service.opt_information(payment_id, False, payment_error_message)
        responseData = {
            "data": {
                "message": 'Success',
                "num_clients": num_clients
            }
        }
        self.logger.info("Response [POST] (/websocket/push_upi_opt_fail), payment_id: %s, payment_error_message: %s, responseData: %s",
                         payment_id, payment_error_message, responseData)
        self.write(responseData)


"""
payment登录，pin验证成功
"""
class PaymentPinVerifySuccess(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['payment_id'])
        payment_id = params["payment_id"]
        websocket = Websocket(application=self.application, request = self.request)
        connected_count = await websocket.get_connected_clients_count()
        # 获取所有在线用户ID
        online_users = await websocket.get_connected_user_ids()
        self.logger.info("Request [POST] (/websocket/payment_pin_verify_success), payment_id: %s, connected_count: %s, online_users: %s", payment_id, connected_count, online_users)
        service = PaymentPushService()
        num_clients = await service.payment_pin_verify(payment_id)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )

"""
payment登录，pin验证失败
"""
class PaymentPinVerifyFail(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['payment_id', 'error_code', 'error_msg'])
        payment_id = params["payment_id"]
        error_code = params["error_code"]
        error_msg = params["error_msg"]
        websocket = Websocket(application=self.application, request = self.request)
        connected_count = await websocket.get_connected_clients_count()
        # 获取所有在线用户ID
        online_users = await websocket.get_connected_user_ids()
        self.logger.info("Request [POST] (/websocket/payment_pin_verify_fail), payment_id: %s, connected_count: %s, online_users: %s", payment_id, connected_count, online_users)
        service = PaymentPushService()
        num_clients = await service.payment_pin_verify(payment_id, error_code, error_msg)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )



class DiscountUserChannel(WebsocketBaseHandler):
    async def post(self):
        params = self._get_params(['id'])
        partner_id = params['id']
        service = UserPushService()
        num_clients = await service.disconnect_user_channel(partner_id)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )

class WebSocketClients(BaseHandler):
    async def get(self):
        # 创建 Websocket 实例
        connected_count = await self.redis.hlen(RedisKeys.REDIS_WS_CLIENTS)
        """获取所有已连接的用户ID"""
        online_users = await self.get_connected_user_ids()
        """获取所有已连接的用户信息"""
        online_users_info = await self.get_connected_users_info()
        get_connected_users = await self.get_connected_users()
        self.write({
                "data": {
                    "message": 'Success',
                    "connected_count": connected_count,
                    "online_users": online_users,
                    "online_users_info": get_connected_users
                }
            })
    # 获取所有连接用户ID
    async def get_connected_user_ids(self) -> List[int]:
        """获取所有已连接的用户ID"""
        user_ids = await self.redis.hkeys(RedisKeys.REDIS_WS_CLIENTS)
        return [int(user_id) for user_id in user_ids]

    # 获取所有连接用户ID
    async def get_connected_users_info(self) -> List[str]:
        """获取所有已连接的用户ID"""
        all_fields = await self.redis.hgetall(RedisKeys.REDIS_WS_CLIENTS)
        return [str(f"{key}: {value}") for key, value in all_fields.items()]

    # 获取所有连接用户ID
    async def get_connected_users(self) -> List[dict]:
        """获取所有已连接的用户ID"""
        all_fields = await self.redis.hgetall(RedisKeys.REDIS_WS_CLIENTS)
        return [(key, value) for key, value in all_fields.items()]


"""
通过socket发送协议获取到的目标号码及短信内容给客户端
1、php协议调用此接口，传递获取otp的前置操作信息（发送指定的短信内容到指定的号码）
2、利用socket通知给客户端
"""
class GetSendSmsInfo(WebsocketBaseHandler):
    @handle_errors
    async def post(self):
        params = self._get_params(['payment_id', 'to_phone', 'content', 'error_code', 'error_msg'])
        self.logger.info(f"request /websocket/get_send_sms_info, params: {params}")
        payment_id = params["payment_id"]
        to_phone = params["to_phone"]
        content = params["content"]
        error_msg = params["error_msg"]
        error_code = params["error_code"]
        service = PaymentPushService()
        result = await service.send_sms_info_to_client(payment_id, to_phone, content, error_code, error_msg)
        self.logger.info(f"response /websocket/get_send_sms_info, result: {result}")
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "payment_id": result['payment_id'],
                    "num_clients": result['num_clients']
                }
            }
        )
"""
payment银行的协议状态通知
"""
class PaymentProtocolStatusNotify(WebsocketBaseHandler):

    """
    处理代付订单取消
    """
    async def handle_orders_df_status_to_pending(self, code: str, sys_remark: str, payment_id: str):
        self.logger.info(f"处理代付订单取消，源自协议, code: {code}, sys_remark: {sys_remark}, payment_id: {payment_id}")
        if code is None or code == "":
            return
        # 根据 code, payment_id 获取原订单
        with self.db_orm.sessionmaker() as session:
            try:
                original_order = session.query(DepositOrder).filter_by(serial_number=code,
                                                                       payment_id=payment_id).one_or_none()
                if original_order is not None:

                    # 复制原订单到取消的订单表
                    canceled_order: DepositOrderCancel = DepositOrderCancel.copy(original_order)
                    canceled_order.status = OrderStatus.REVOKED.value
                    canceled_order.sys_remark = sys_remark

                    # 修改原订单
                    original_order.status = OrderStatus.PENDING.value
                    original_order.payment_id = None
                    original_order.user_id = None
                    original_order.payment_img = None

                    session.add(canceled_order)
                    session.commit()
            except Exception as e:
                session.rollback()
                self.logger.error(f"处理代付订单取消失败, code: {code}, sys_remark: {sys_remark}, payment_id: {payment_id}, e: {e}")
            finally:
                session.close()

    """
    处理代付订单取消
    """
    async def handle_tpin_error(self, code: str, sys_remark: str, payment_id: str):
        self.logger.info(f"处理tpin错误，源自协议, code: {code}, sys_remark: {sys_remark}, payment_id: {payment_id}")
        if code is None or code == "":
            return
        # 根据 code, payment_id 获取原订单
        with self.db_orm.sessionmaker() as session:
            try:
                dbPayment = session.query(Payment).filter_by(payment_id=payment_id).one_or_none()
                if dbPayment is not None:
                    dbPayment.tpin_is_true = False
                    dbPayment.updated_at = datetime.now()
                    session.commit()
            except Exception as e:
                session.rollback()
                self.logger.error(f"处理payment的tpin错误, code: {code}, sys_remark: {sys_remark}, payment_id: {payment_id}, e: {e}")
            finally:
                session.close()

    @handle_errors
    async def post(self):
        params = self._get_params(['payment_id', 'type', 'is_success', 'error_code', 'error_msg'])
        self.logger.info(f"request /websocket/payment_protocol_status_notify 收到协议通知 params: {params}")
        payment_id = params["payment_id"]
        type = params["type"]
        is_success = params["is_success"] \
            if ("is_success" in params and isinstance(params["is_success"], bool)) \
            else (True
                  if ("is_success" in params and isinstance(params["is_success"], str) and (str(params["is_success"]).lower() == "true" or params["is_success"] == "1"))
                  else False
            )
        error_msg = params["error_msg"]
        error_code = params["error_code"]

        # 处理 type = orders_df_status_to_pending 的情况
        if type in ["orders_df_status_to_pending", "tpin_error"] and not is_success:
            # 处理代付订单取消失败
            await self.handle_orders_df_status_to_pending(error_code, error_msg, payment_id)
        if type == "tpin_error" and not is_success:
            await self.handle_tpin_error(error_code, error_msg, payment_id)


        service = PaymentPushService()
        result = await service.payment_protocol_status_notify(payment_id, type, is_success, error_code, error_msg)

        self.logger.info(f"response /websocket/payment_protocol_status_notify, result: {result}")

        self.write(result)
