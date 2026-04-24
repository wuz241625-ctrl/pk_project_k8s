from marshmallow import Schema, fields, post_dump


class BalanceRecordSchema(Schema):
    type = fields.Method('set_type_to_word')
    amount = fields.Decimal(places=2, required=True)
    running_balance = fields.Decimal(places=2, attribute="change_after", required=True)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S", required=True)

    @staticmethod
    def set_type_to_word(obj):
        type_mapping = {
            0: "Sell Token",
            1: "Buy Token",
            2: "Withdraw",
            3: "Commission",
            4: "Frozen",
            5: "Security Deposit",
            6: "Manual",
            7: "Deposit",
            8: "Transfer",
            9: "Revoke",
            10: "Bonus"
        }
        return type_mapping[obj.record_type]

    @post_dump
    def process_decimals(self, data, **kwargs):
        if data['amount'] is not None:
            data['amount'] = float(data['amount'])
        if data['running_balance'] is not None:
            data['running_balance'] = float(data['running_balance'])
        return data
