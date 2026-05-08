import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class LegacyPartnerWebsocketRetirementTests(unittest.TestCase):
    def _read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_partner_ws_route_is_not_registered(self):
        source = self._read("api/router.py")

        self.assertNotIn('url("/partner/ws"', source)
        self.assertNotIn("application.app.websocket import app", source)

    def test_files_upload_route_is_preserved(self):
        source = self._read("api/router.py")

        self.assertIn('url("/files/upload"', source)
        self.assertIn("issue.upload", source)

    def test_legacy_redissub_thread_is_not_started(self):
        source = self._read("api/main.py")

        self.assertNotIn("from application.phonepe import redissub", source)
        self.assertNotIn("threading.Thread(target=redissub.main", source)

    def test_lakshmi_websocket_and_protocol_notifications_remain(self):
        source = self._read("api/router_lakshmi.py")

        self.assertIn('url("/lakshmi/partner"', source)
        self.assertIn('url("/websocket/payment_protocol_status_notify"', source)
        self.assertIn('url("/websocket/get_send_sms_info"', source)
