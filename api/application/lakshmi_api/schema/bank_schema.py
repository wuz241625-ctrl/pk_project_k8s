from marshmallow import Schema, fields, validate

from application.lakshmi_api.services.payment_services import BANK_SERVICES


class BankSchema(Schema):
    name = fields.String(required=True, validate=validate.Length(min=2))


class UpiBankSchema(Schema):
    id = fields.String(attribute="id")
    name = fields.String()
    logo_url = fields.String()
    final_page_url = fields.Method('set_final_page_url')
    in_app_browser = fields.Method('set_in_app_browser')
    in_app_browser_url = fields.Method('set_in_app_browser_url')
    hint_image_url = fields.Method('set_hint_image_url')
    is_webview = fields.Method('set_is_webview')

    @staticmethod
    def set_in_app_browser(obj):
        return True if obj.name == 'AMAZON' else False

    @staticmethod
    def set_in_app_browser_url(obj):
        if obj.name == 'AMAZON':
            return 'https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0'
        else:
            return None

    @staticmethod
    def set_final_page_url(obj):
        if obj.name == 'AMAZON':
            return 'https://www.amazon.in/amazonpay/home'
        else:
            return None

    @staticmethod
    def set_hint_image_url(obj):
        if obj.name == 'AMAZON':
            return 'https://lakshmivip.com/lakshmi_apk/amazon_hint.jpg'
            # return 'https://storage.googleapis.com/lakshmi_apk/amazon_hint.jpg'
        else:
            return None

    @staticmethod
    def set_is_webview(obj):
        try:
            service_class = BANK_SERVICES[obj.name]
            if service_class.LOGIN_METHOD == 'webview':
                return True
            else:
                return False
        except Exception as e:
            return False
