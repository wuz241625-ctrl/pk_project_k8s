from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "api/template/order_india.10100.html"
ORDER_HANDLER = ROOT / "api/application/pay/order.py"


class OrderIndia10100TemplateTests(unittest.TestCase):
    def test_payment_page_supports_english_and_urdu_with_english_default(self):
        template = TEMPLATE.read_text()

        for marker in [
            '<html lang="en" dir="ltr"',
            '<title>EasyPaisa QR Payment</title>',
            'id="lang-en"',
            'id="lang-ur"',
            'data-lang="en"',
            'data-lang="ur"',
            "let currentLanguage = \"en\";",
            "const translations = {",
            "const guideStepsByLanguage = {",
            "let guideSteps = guideStepsByLanguage.en;",
            "function getCopy(key)",
            "function applyLanguage(language)",
            "function bindLanguageSwitch()",
            "document.documentElement.lang = language === \"ur\" ? \"ur\" : \"en\";",
            "document.documentElement.dir = language === \"ur\" ? \"rtl\" : \"ltr\";",
            "bindLanguageSwitch();",
        ]:
            self.assertIn(marker, template)

        for english in [
            "Payment amount",
            "Enter payer EasyPaisa mobile number",
            "Save QR",
            "Payment received",
            "Time expired",
            "Skip",
            "Next",
            "Start",
        ]:
            self.assertIn(english, template)

        for urdu in [
            "رقم",
            "ادائیگی کرنے والا موبائل نمبر درج کریں",
            "QR محفوظ کریں",
            "ادائیگی موصول ہو گئی",
            "وقت ختم ہو گیا",
            "چھوڑ دیں",
            "اگلا",
            "شروع کریں",
        ]:
            self.assertIn(urdu, template)

    def test_payment_page_has_targeted_transparent_coachmarks(self):
        template = TEMPLATE.read_text()

        for marker in [
            'id="guide-overlay"',
            'data-guide-style="transparent-coachmark"',
            'id="guide-highlight"',
            'id="guide-arrow"',
            'id="guide-progress"',
            'id="guide-title"',
            'id="guide-body"',
            'id="guide-skip"',
            'id="guide-next"',
            "const guideSteps",
            'openGuide("phone")',
            "function openQrGuide()",
            "function bindGuideControls()",
            "function positionGuideStep()",
            "function getGuideTargetRect(step)",
            "function bindGuidePositionUpdates()",
        ]:
            self.assertIn(marker, template)

        self.assertNotIn('aria-modal="true"', template)
        self.assertNotIn('role="dialog"', template)
        self.assertIn("background: transparent;", template)
        self.assertIn("pointer-events: none;", template)
        self.assertIn("pointer-events: auto;", template)
        self.assertIn("position: absolute;", template)
        self.assertIn("scrollIntoView", template)
        self.assertIn('document.getElementById("guide-skip").addEventListener("click", closeGuide);', template)

        for target in [
            'target: "#payer-phone"',
            'target: "#phone-submit"',
            'target: ".amount"',
            'target: "#countdown-time"',
            'target: ".qr-frame"',
            'target: "#save-qr"',
            'target: "#status-text"',
        ]:
            self.assertIn(target, template)

    def test_guide_can_switch_language_while_open(self):
        template = TEMPLATE.read_text()

        for marker in [
            'class="guide-language-switch"',
            'aria-label="Guide language"',
            'data-guide-language-switch',
            'data-guide-language="en"',
            'data-guide-language="ur"',
            'function syncLanguageButtons()',
            'syncLanguageButtons();',
            'renderGuideStep();',
        ]:
            self.assertIn(marker, template)

    def test_guide_card_does_not_cover_page_language_switch(self):
        template = TEMPLATE.read_text()

        for marker in [
            "function getGuideProtectedRects(step)",
            'const protectedSelectors = [".language-switch"];',
            "function rectsOverlap(first, second)",
            "function placeGuideCardAwayFromProtectedTargets(",
            "cardTop = placeGuideCardAwayFromProtectedTargets(cardTop, cardLeft, cardWidth, cardHeight, step, viewportHeight, cardGap);",
            "const cardIsAboveTarget = cardTop + cardHeight <= rect.top;",
        ]:
            self.assertIn(marker, template)

    def test_qr_guide_filters_targets_already_explained(self):
        template = TEMPLATE.read_text()

        for marker in [
            "let completedGuideTargets = new Set();",
            "function markVisibleGuideStepsCompleted()",
            "function getGuideFlowSteps(flow)",
            "return !completedGuideTargets.has(step.target);",
            "markVisibleGuideStepsCompleted();",
            "activeGuideSteps = getGuideFlowSteps(flow);",
        ]:
            self.assertIn(marker, template)

        self.assertNotIn("guide-hint", template)

    def test_payment_page_has_qr_save_button_and_fallback(self):
        template = TEMPLATE.read_text()

        for marker in [
            'id="save-qr"',
            "function saveQrImage()",
            'toDataURL("image/png")',
            'download = "easypaisa-order-{{ token }}.png"',
            'window.open(imageUrl, "_blank")',
            "function bindSaveQrButton()",
            "bindSaveQrButton();",
        ]:
            self.assertIn(marker, template)

    def test_qr_generation_uses_larger_medium_correction_code(self):
        template = TEMPLATE.read_text()

        for marker in [
            "const QR_RENDER_SIZE = 280;",
            "function generateQrcode(el, text, size)",
            "width: size,",
            "height: size,",
            "correctLevel: QRCode.CorrectLevel.M",
            "generateQrcode(qrNode, payload, QR_RENDER_SIZE);",
        ]:
            self.assertIn(marker, template)

    def test_saved_qr_adds_amount_label_and_high_resolution_quiet_zone(self):
        template = TEMPLATE.read_text()

        for marker in [
            "const QR_SAVE_PADDING = 80;",
            "const QR_SAVE_SIZE = 520;",
            "const QR_SAVE_HEADER_HEIGHT = 96;",
            "function getQrPayload()",
            "function getQrAmountText()",
            "function drawCenteredText(context, text, centerX, y, maxWidth, font)",
            "function createQrSourceNode(payload, size)",
            "generateQrcode(holder, payload, size);",
            "function buildSavedQrImageUrl()",
            "const qrSource = createQrSourceNode(payload, QR_SAVE_SIZE);",
            "const amountText = getQrAmountText();",
            'context.fillStyle = "#ffffff";',
            "context.fillRect(0, 0, outputCanvas.width, outputCanvas.height);",
            "\"Amount: \" + amountText",
            "outputCanvas.width = QR_SAVE_SIZE + QR_SAVE_PADDING * 2;",
            "outputCanvas.height = QR_SAVE_HEADER_HEIGHT + QR_SAVE_SIZE + QR_SAVE_PADDING * 2;",
            "context.drawImage(sourceNode, QR_SAVE_PADDING, QR_SAVE_HEADER_HEIGHT + QR_SAVE_PADDING, QR_SAVE_SIZE, QR_SAVE_SIZE);",
            "return outputCanvas.toDataURL(\"image/png\");",
            "return buildSavedQrImageUrl();",
        ]:
            self.assertIn(marker, template)

    def test_show_qr_step_opens_scan_guide_only_after_qr_rendered(self):
        template = TEMPLATE.read_text()
        match = re.search(r"function showQrStep\(\) \{(?P<body>.*?)\n    \}", template, re.S)

        self.assertIsNotNone(match)
        self.assertRegex(
            match.group("body"),
            r"const qrRendered = renderQr\(\);\s+if \(qrRendered\) \{\s+openQrGuide\(\);\s+\}",
        )

    def test_cashier_submit_checks_pakistan_wallet_phone_conflict_before_utr_write(self):
        source = ORDER_HANDLER.read_text()
        card_num_source = source[source.index("class card_num"):source.index("    async def order_success_ds")]

        for marker in [
            "def _normalize_pakistan_wallet_msisdn",
            "normalized_utr = self._normalize_pakistan_wallet_msisdn(utr)",
            "SELECT code, payment_id, amount, status",
            "payment_id = %s",
            "AND amount = %s",
            "AND utr = %s",
            "AND status IN (1, 2)",
            "AND time_create >= DATE_SUB(NOW(), INTERVAL 7 MINUTE)",
            "AND code <> %s",
            "UPDATE orders_ds SET utr=%s,time_payed=now()",
            "WHERE code=%s AND status IN (1,2)",
        ]:
            self.assertIn(marker, card_num_source)

        self.assertLess(
            card_num_source.index("AND code <> %s"),
            card_num_source.index("UPDATE orders_ds SET utr=%s,time_payed=now()"),
        )

    def test_order_get_uses_phone_or_accno_for_1001_and_qr_payload_for_1010(self):
        source = ORDER_HANDLER.read_text()
        get_source = source[source.index("    async def get(self, token=None):"):source.index("    @staticmethod")]

        self.assertIn("str(order_info['channel_code']) == '1001' and account_type == '10'", get_source)
        self.assertIn("account_iban = phone", get_source)
        self.assertIn("str(order_info['channel_code']) == '1001' and account_type == '20'", get_source)
        self.assertIn("account_iban = account_accno", get_source)
        self.assertIn("elif channel_code == 1010:", get_source)
        self.assertIn("order_info['ep_qr_payload'] = order_info.get('upi') or ''", get_source)


if __name__ == "__main__":
    unittest.main()
