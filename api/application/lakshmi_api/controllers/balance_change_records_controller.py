from application.lakshmi_api.base import BaseHandler, ApiError
from application.lakshmi_api.models.balance_record import BalanceRecord
from application.lakshmi_api.schema.balance_record_schema import BalanceRecordSchema
from application.lakshmi_api.schema.partner_schema import PartnerSchema
from application.lakshmi_api.services.pagination_service import PaginationService
from sqlalchemy import desc


class BalanceChangeRecord(BaseHandler):
    async def get(self):
        await self.authenticate_current_user()

        pagination_service = PaginationService(self.request.path, self.request)

        with self.db_orm.sessionmaker() as session:
            query = session.query(BalanceRecord).filter(
                BalanceRecord.user_id == self.current_user.id).order_by(desc(BalanceRecord.id))

            total_records = query.count()
            offset, limit, pagination_data = await pagination_service.get_pagination_data(total_records)
            balance_records = query.offset(offset).limit(limit).all()

        balance_record_schema = BalanceRecordSchema(many=True)

        response = {
            "data": {
                "user": PartnerSchema().dump(self.current_user),
                "balance_change_records": balance_record_schema.dump(balance_records)
            },
            "pagination": pagination_data
        }

        self.write(response)
