from marshmallow import Schema, fields


class TodayWithdrawOrderSummarySchema(Schema):
    total_orders = fields.Integer()
    success_orders = fields.Integer()
    fail_orders = fields.Integer()
