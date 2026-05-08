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
        return False

    @staticmethod
    def set_in_app_browser_url(obj):
        return None

    @staticmethod
    def set_final_page_url(obj):
        return None

    @staticmethod
    def set_hint_image_url(obj):
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
