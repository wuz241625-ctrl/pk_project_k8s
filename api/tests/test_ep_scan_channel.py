import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


ROOT = Path(__file__).resolve().parents[2]


class EpScanChannelTests(unittest.TestCase):
    def test_pakistanpay_maps_1010_to_dedicated_template(self):
        source = (ROOT / "api/application/pay/order.py").read_text()
        tree = ast.parse(source)
        mapping_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "TEMPLATE_MAPPING":
                        mapping_node = node.value
                    if isinstance(target, ast.Attribute) and target.attr == "TEMPLATE_MAPPING":
                        mapping_node = node.value
        self.assertIsNotNone(mapping_node)
        mapping = ast.literal_eval(mapping_node)

        self.assertEqual(mapping["pakistanpay"][1001], 1010)
        self.assertEqual(mapping["pakistanpay"][1010], 10100)

    def test_order_handler_has_dedicated_1010_branch(self):
        source = (ROOT / "api/application/pay/order.py").read_text()

        self.assertIn("channel_code == 1010", source)
        self.assertIn("template_code = self.get_template_code", source)
        self.assertIn("order_india.{template_code}.html", source)
        self.assertIn("order_info['utr'] = order_info.get('utr') or ''", source)

    def test_1010_template_is_scan_only(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn('data-channel-purpose="ep-scan-only"', template)
        self.assertIn("ep-qr-payload", template)
        forbidden = [
            "Copy Account",
            "copy",
            "UTR",
            "upi-id",
            "popup-form",
            "account-details-container",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, template)

    def test_1010_template_renders_qr_with_local_function(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn("function generateQrcode", template)
        self.assertIn("new QRCode", template)
        self.assertIn("QRCode.CorrectLevel", template)

    def test_1010_template_collects_phone_before_showing_qr_without_easypay_initiate(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn("phone-step", template)
        self.assertIn("qr-step", template)
        self.assertIn('reverse_url("card_num_submit", token)', template)
        self.assertIn("normalizePhone", template)
        self.assertIn("orders_ds.utr", template)

        forbidden = ["easypay/initiate"]
        for marker in forbidden:
            self.assertNotIn(marker, template)

    def test_1010_template_stores_callback_match_phone_without_leading_zero(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn("function normalizeMatchPhone", template)
        self.assertIn("const submitPhone = normalizeMatchPhone(phone);", template)
        self.assertIn("data: {card_num: submitPhone}", template)
        self.assertNotIn("data: {card_num: phone}", template)

    def test_1010_template_uses_default_static_assets_served_by_nginx(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        required_assets = [
            "{{ static_url('css/reset.css') }}",
            "{{ static_url('css/layer.css') }}",
            "{{ static_url('v2/plugins/jquery/jquery-2.1.4.min.js') }}",
            "{{ static_url('js/qrcode.min.js') }}",
            "{{ static_url('js/layer3.js') }}",
        ]
        for asset in required_assets:
            self.assertIn(asset, template)

        self.assertNotIn("/api{{ static_url", template)

    def test_1010_template_defaults_to_english_and_supports_urdu(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn('<html lang="en" dir="ltr"', template)
        self.assertIn("EasyPaisa QR Payment", template)
        self.assertIn("Enter payer EasyPaisa mobile number", template)
        self.assertIn("Scan QR", template)
        self.assertIn("Waiting for payment", template)
        self.assertIn('id="lang-en"', template)
        self.assertIn('id="lang-ur"', template)
        self.assertIn("function applyLanguage(language)", template)
        self.assertIn('document.documentElement.dir = language === "ur" ? "rtl" : "ltr";', template)
        self.assertIn("ادائیگی کرنے والا موبائل نمبر درج کریں", template)
        self.assertIn("QR اسکین کریں", template)
        self.assertIn("ادائیگی کا انتظار ہے", template)
        self.assertIn('dir="ltr"', template)

    def test_1010_template_guides_exact_amount_and_expiry(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn("عین رقم", template)
        self.assertIn("QR میں عین رقم خود شامل ہے", template)
        self.assertIn("ٹائمر ختم ہونے سے پہلے", template)
        self.assertIn("{{ '{0:.2f}'.format(amount) }}", template)
        self.assertIn("countdown-time", template)

    def test_1010_qr_step_does_not_show_submitted_phone_line(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertNotIn('id="confirmed-phone"', template)
        self.assertNotIn("phone-number", template)
        self.assertNotIn("موبائل نمبر:", template)
        self.assertNotIn('document.getElementById("confirmed-phone")', template)

    def test_1010_template_has_success_and_timeout_screens(self):
        template = (ROOT / "api/template/order_india.10100.html").read_text()

        self.assertIn('id="success-overlay"', template)
        self.assertIn('id="timeout-overlay"', template)
        self.assertIn("Payment received", template)
        self.assertIn("Time expired", template)
        self.assertIn("ادائیگی موصول ہو گئی", template)
        self.assertIn("وقت ختم ہو گیا", template)
        self.assertIn("function showSuccessState", template)
        self.assertIn("function showTimeoutState", template)
        self.assertIn("setTimeout(function ()", template)
        self.assertIn("leaveCheckout(redirectUrl)", template)
        self.assertIn("location.href = targetUrl", template)
        self.assertIn('id="timeout-exit"', template)
        self.assertIn("function leaveCheckout", template)
        self.assertIn("showTimeoutState(result.url)", template)
        self.assertIn("result.code === 10002", template)

    def test_1001_template_keeps_copy_transfer_page(self):
        template = (ROOT / "api/template/order_india.1010.html").read_text()

        self.assertNotIn('data-channel-purpose="ep-scan-only"', template)
        self.assertIn("account-details-container", template)

    def test_tracked_sql_contains_1010_ep_scan_channel(self):
        mysql_sql = (ROOT / "api/mysql.sql").read_text()

        self.assertIn("1010,'EP 扫码'", mysql_sql)


if __name__ == "__main__":
    unittest.main()
