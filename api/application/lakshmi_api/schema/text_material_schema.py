from marshmallow import Schema, fields, validate


class TextMaterialSchema(Schema):
    title = fields.String(required=True, validate=validate.Length(min=4))
    content = fields.String(required=True, validate=validate.Length(min=4))
    genre = fields.String(required=True, load_only=True)
