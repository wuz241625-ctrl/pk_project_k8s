from marshmallow import Schema, fields


class LakshmiApiSettingSchema (Schema):
    genre = fields.String(required=True)
    name = fields.String(required=True)
    key = fields.String(required=True)
    value = fields.String(required=True)