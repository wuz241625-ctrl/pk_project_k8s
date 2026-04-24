from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.error_handler import handle_errors
from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.schema.withdraw_order_schema import WithdrawOrderSchema, OrderStatus, UnfulfilledSchema
from application.lakshmi_api.services.pagination_service import PaginationService
from datetime import datetime, timedelta
from application.lakshmi_api.models.withdraw_order import WithdrawOrder
from application.lakshmi_api.models.bank_type import BankType
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.models.bank_record import BankRecord
from sqlalchemy import and_, desc
from sqlalchemy.orm import joinedload

INVALID_ORDER_STATUS = [
    -2,  # UNKNOWN
    -1,  # REVOKED
    0,  # PENDING
]

VALID_STATUSES = [1, 2, 3, 4]


class WithdrawOrders(BaseHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()

        time_frame = self.set_value_to_integer("time_frame", 7)
        date_from = (datetime.now() - timedelta(days=time_frame))
        where_clause = and_(WithdrawOrder.updated_at >= date_from,
                            WithdrawOrder.status.in_(VALID_STATUSES),
                            WithdrawOrder.user_id == self.current_user.id)
        with self.db_orm.sessionmaker() as session:
            total_count = session.query(WithdrawOrder).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            user_withdraw_orders = session.query(WithdrawOrder).filter(where_clause) \
                .options(joinedload(WithdrawOrder.payment)) \
                .order_by(desc(WithdrawOrder.id)) \
                .offset(offset) \
                .limit(limit) \
                .all()

            withdraw_order_schema = WithdrawOrderSchema(many=True)
            self.write({
                "data": {
                    "user": PartnerSchema().dump(self.current_user),
                    "orders": withdraw_order_schema.dump(user_withdraw_orders)
                },
                "pagination": pagination_data
            })


class Unfulfilled(BaseHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()
        # 是否正式环境，否则为内部测试
        is_formal = self.get_query_argument('is_formal', "1")
        time_frame = self.set_value_to_integer("time_frame", 7)
        date_from = (datetime.now() - timedelta(days=time_frame))

        with self.db_orm.sessionmaker() as session:
            if is_formal == "1":
                bank_types = session.query(BankType).filter(BankType.status == 1, BankType.genre == 1).all()
            else:
                bank_types = session.query(BankType).filter(BankType.status == 1).all()
            bank_type_ids = [bank_type.id for bank_type in bank_types]
            payments = session.query(Payment).filter(and_(
                Payment.user_id == self.current_user.id,
                Payment.bank_type_id.in_(bank_type_ids))
            ).all()
            payment_ids = [payment.id for payment in payments]
            where_clause = and_(BankRecord.created_at >= date_from,
                                BankRecord.user_id == self.current_user.id,
                                BankRecord.payment_id.in_(payment_ids),
                                BankRecord.trade_type == 1,
                                BankRecord.callback == 0)

            total_count = session.query(BankRecord).filter(where_clause).count()
            unfulfilled_bank_records = session.query(BankRecord).filter(where_clause).order_by(
                desc(BankRecord.id)).all()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)
            unfulfilled_schema = UnfulfilledSchema(many=True)

            self.write({
                "data": {
                    "user": PartnerSchema().dump(self.current_user),
                    "orders": unfulfilled_schema.dump(unfulfilled_bank_records)
                },
                "pagination": pagination_data
            })


class FailWithdraw(BaseHandler):
    @handle_errors
    async def get(self):
        await self.authenticate_current_user()

        time_frame = self.set_value_to_integer("time_frame", 7)
        date_from = (datetime.now() - timedelta(days=time_frame))
        where_clause = and_(WithdrawOrder.created_at >= date_from,
                            WithdrawOrder.status.in_(INVALID_ORDER_STATUS),
                            WithdrawOrder.user_id == self.current_user.id)

        with self.db_orm.sessionmaker() as session:
            total_count = session.query(WithdrawOrder).filter(where_clause).count()
            pagination_service = PaginationService(self.request.path, self.request)
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_count)

            user_withdraw_orders = session.query(WithdrawOrder).filter(where_clause) \
                .options(joinedload(WithdrawOrder.payment)) \
                .order_by(desc(WithdrawOrder.id)) \
                .offset(offset) \
                .limit(limit) \
                .all()

            withdraw_order_schema = WithdrawOrderSchema(many=True)
            self.write({
                "data": {
                    "user": PartnerSchema().dump(self.current_user),
                    "orders": withdraw_order_schema.dump(user_withdraw_orders)
                },
                "pagination": pagination_data
            })
