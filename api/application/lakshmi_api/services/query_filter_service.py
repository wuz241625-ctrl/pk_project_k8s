from decimal import Decimal
from application.lakshmi_api.schema.lakshmi_api_setting_schema import LakshmiApiSettingSchema
from application.lakshmi_api.models.lakshmi_api_setting import LakshmiApiSetting
import global_resources


class QueryFilterService:
    def __init__(self):
        self.db_orm = global_resources.db_orm

    def filter_order_amounts(self):
        # TODO: improve get data from redis, not query DB everytime
        filters = []
        previous_amount = None
        with self.db_orm.sessionmaker() as session:
            order_amount_filters = session.query(LakshmiApiSetting).filter(
                LakshmiApiSetting.genre == 'order_amount_filter').all()

        order_amount_filter_data = LakshmiApiSettingSchema(many=True).dump(order_amount_filters)
        amounts = [int(order_amount_filter['value']) for order_amount_filter in order_amount_filter_data]
        sorted_amounts = sorted(amounts)
        for amount in sorted_amounts:
            if previous_amount is not None:
                filters.append({'min': int(previous_amount + Decimal(1)), 'max': amount})

            previous_amount = Decimal(amount)

        if previous_amount is not None:
            filters.append({'min': int(previous_amount + Decimal(1))})
        return filters
