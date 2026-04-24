from marshmallow import Schema, fields

# 活动设置
class PrizeSettingSchema(Schema):
    id = fields.String(attribute="id")
    # title = fields.String(attribute="title")
    # content = fields.String(attribute="content")
    type = fields.Integer(attribute="type")
    participant = fields.String(attribute="participant")
    pic = fields.String(attribute="pic")
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    status = fields.Integer(attribute="status")
    is_app_show = fields.Integer(attribute="is_app_show")
    begin_at = fields.DateTime(attribute="begin_at", format="%Y-%m-%d %H:%M:%S")
    end_at = fields.DateTime(attribute="end_at", format="%Y-%m-%d %H:%M:%S")
    lottery_chance_setting = fields.Integer(attribute="lottery_chance_setting")


# 活动详细设置
class PrizeSettingDetailSchema(Schema):
    id = fields.String(attribute="id")
    prize_id = fields.String(attribute="prize_id")
    # prize_title = fields.String(attribute="prize_title")
    # title = fields.String(attribute="title")
    prize_limit_min = fields.Integer(attribute="prize_limit_min")
    prize_limit_max = fields.Integer(attribute="prize_limit_max")
    prize_type = fields.Integer(attribute="prize_type")
    money = fields.Decimal(as_string=True, places=4)
    ratio = fields.Decimal(as_string=True, places=6)
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
    updated_at = fields.DateTime(attribute="updated_at", format="%Y-%m-%d %H:%M:%S")
    status = fields.Integer(attribute="status")


# 中奖记录
class PrizeEarnLogSchema(Schema):
    id = fields.String(attribute="id")
    user_id = fields.Integer(attribute="user_id")
    # title = fields.String(attribute="title")
    prize_id = fields.Integer(attribute="prize_id")
    prize_detail_id = fields.Integer(attribute="prize_detail_id")
    # prize_title = fields.String(attribute="prize_title")
    money = fields.Decimal(as_string=True, places=4)
    # remark = fields.String(attribute="remark")
    created_at = fields.DateTime(attribute="created_at", format="%Y-%m-%d %H:%M:%S")
