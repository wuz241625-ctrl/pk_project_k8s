from application.lakshmi_api.services.websockets import *
from application.lakshmi_api.base_ws import BaseHandler


class PushUserInformation(BaseHandler):
    async def get(self):
        partner_id = self.get_query_argument('id')
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


class PublishEveryone(BaseHandler):
    async def get(self):
        message = self.get_query_argument("message")
        params = {
            'icon': self.get_query_argument('icon', None),
            'color': self.get_query_argument('color', None),
            'position': self.get_query_argument('position', None),
            'timeout': self.get_query_argument('timeout', None)
        }
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


class PushMessageToUser(BaseHandler):
    async def get(self):
        partner_id = self.get_query_argument('id')
        message = self.get_query_argument("message")
        params = {
            'icon': self.get_query_argument('icon', None),
            'color': self.get_query_argument('color', None),
            'position': self.get_query_argument('position', None),
            'timeout': self.get_query_argument('timeout', None)
        }
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


class PushPaymentInformation(BaseHandler):
    async def get(self):
        payment_id = self.get_query_argument('id')
        service = PaymentPushService()
        num_clients = await service.payment_information(payment_id)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )


class PushUpiOtpSuccessNotify(BaseHandler):
    async def get(self):
        payment_id = self.get_query_argument('id')
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


class PushUpiOtpFailNotify(BaseHandler):
    async def get(self):
        payment_id = self.get_query_argument('id')
        payment_error_message = self.get_query_argument("error_message")
        service = PaymentPushService()
        num_clients = await service.opt_information(payment_id, False, payment_error_message)
        self.write(
            {
                "data": {
                    "message": 'Success',
                    "num_clients": num_clients
                }
            }
        )


class DiscountUserChannel(BaseHandler):
    async def get(self):
        partner_id = self.get_query_argument('id')
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
