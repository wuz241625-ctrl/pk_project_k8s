import json
import os
import random

from application.lakshmi_api.base import ApiError
from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.models.user import User
from decimal import Decimal
from sqlalchemy import text
import global_resources


class UserPushService:
    def __init__(self):
        self.db_orm = global_resources.db_orm
        self.redis = global_resources.redis
        self.redis_pub = global_resources.redis_pub

    async def user_information(self, partner_id) -> int:
        with self.db_orm.sessionmaker() as session:
            current_user = session.query(User).filter_by(id=partner_id).first()
            # deduct unfulfilled order amount
            query = text(
                'select ifnull(sum(amount), 0) as deduction_balance from bank_record where payment_id in (select id from payment where partner_id = :partner_id)  and callback=0 and trade_type=1 and invalid=0 and if_ew=0')
            result = session.execute(query, {'partner_id': current_user.id})
            if os.environ.get('RUN_ENV') == 'DEV':
                current_user.balance = random.randint(1, 10000)
            else:
                current_user.balance = max(
                    Decimal(current_user.balance) - Decimal(result.fetchone().deduction_balance),
                    Decimal(0)
                )
        if current_user:
            personal_channel_name = "user_channel_{}".format(current_user.id)
            num_clients = await self.redis_pub.publish(
                personal_channel_name,
                json.dumps(
                    {
                        "type": "user_information",
                        "content": "success",
                        "data": {
                            "user": PartnerSchema().dump(current_user)
                        }
                    }
                )
            )
            return num_clients
        else:
            raise ApiError('User not found')

    async def publish_everyone(self, message, icon="online_prediction", color="primary", position="top",
                               timeout=3000) -> int:
        public_channel_name = 'public_channel'
        num_clients = await self.redis_pub.publish(
            public_channel_name,
            json.dumps(
                {
                    "type": "publish_everyone",
                    "content": "success",
                    "data": {
                        "message": message,
                        "icon": icon,
                        "color": color,
                        "position": position,
                        "timeout": timeout
                    }
                }
            )
        )
        return num_clients

    async def push_message_to_user(self, partner_id, message, icon="online_prediction", color="primary",
                                   position="top",
                                   timeout=6000) -> int:
        with self.db_orm.sessionmaker() as session:
            current_user = session.query(User).filter_by(id=partner_id).first()
        if current_user:
            personal_channel_name = "user_channel_{}".format(current_user.id)
            num_clients = await self.redis_pub.publish(
                personal_channel_name,
                json.dumps(
                    {
                        "type": "push_message_to_user",
                        "content": "success",
                        "data": {
                            "message": message,
                            "icon": icon,
                            "color": color,
                            "position": position,
                            "timeout": timeout
                        }
                    }
                )
            )
            return num_clients
        else:
            raise ApiError('User not found')

    async def disconnect_user_channel(self, partner_id) -> int:
        with self.db_orm.sessionmaker() as session:
            current_user = session.query(User).filter_by(id=partner_id).first()
            if current_user:
                personal_channel_name = "user_channel_{}".format(current_user.id)
                num_clients = await self.redis_pub.publish(
                    personal_channel_name,
                    'disconnect_user'
                )
                return num_clients
            else:
                raise ApiError('User not found')
