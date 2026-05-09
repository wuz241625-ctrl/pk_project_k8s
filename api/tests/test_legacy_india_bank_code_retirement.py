import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LegacyIndiaBankCodeRetirementTest(unittest.TestCase):
    LEGACY_PATHS = [
        "api/application/app/login/banks/indus_bank.py",
        "api/application/phonepe",
        "api/application/lakshmi_api/services/payments/airtel_service.py",
        "api/application/lakshmi_api/services/payments/amazon_pay_service.py",
        "api/application/lakshmi_api/services/payments/freecharge_service.py",
        "api/application/lakshmi_api/services/payments/indus_pay_service.py",
        "api/application/lakshmi_api/services/payments/jio_service.py",
        "api/application/lakshmi_api/services/payments/maha_service.py",
        "api/application/lakshmi_api/services/payments/mobikwik_service.py",
        "api/application/lakshmi_api/services/payments/phonepe_service.py",
        "api/application/lakshmi_api/services/payments/ulcash_service.py",
        "api/jobs/freecharge-monitor",
        "api/jobs/induspay",
        "api/jobs/jio",
        "api/jobs/maha",
        "api/sql/20241125-添加indus银行.sql",
        "api/sql/20241223-添加银行jio.sql",
        "api/sql/20250206-添加银行maha.sql",
        "api/static/images/india_transaction/PhonePe.svg",
        "frontend_src/admin/src/views/partner/phonepe.vue",
    ]

    def assert_file_not_contains(self, relative_path, *tokens):
        path = ROOT / relative_path
        if not path.exists():
            return
        content = path.read_text(encoding="utf-8")
        for token in tokens:
            self.assertNotIn(token, content, f"{relative_path} 不应再包含 {token}")

    def test_legacy_modules_and_jobs_are_removed(self):
        for relative_path in self.LEGACY_PATHS:
            self.assertFalse((ROOT / relative_path).exists(), f"{relative_path} 应已删除")

    def test_payment_service_registry_no_longer_registers_legacy_banks(self):
        self.assert_file_not_contains(
            "api/application/lakshmi_api/services/payment_services.py",
            "FREECHARGE",
            "PHONEPE",
            "MOBIKWIK",
            "AIRTEL",
            "AMAZON",
            "INDUS",
            "JIO",
            "MAHA",
            "ULCASH",
        )

    def test_payment_controllers_no_longer_expose_ulcash_otp_or_callback(self):
        self.assert_file_not_contains(
            "api/application/lakshmi_api/controllers/payment_controller.py",
            "ULCASH",
        )
        self.assert_file_not_contains(
            "api/application/lakshmi_api/controllers/upi_controller.py",
            "ULCASH",
        )
        self.assert_file_not_contains(
            "api/application/lakshmi_api/services/websockets/payment_service.py",
            "ULCASH",
        )
        self.assert_file_not_contains(
            "api/application/pay/order.py",
            "ulcash",
        )

    def test_phonepe_routes_and_admin_entrypoints_are_removed(self):
        self.assert_file_not_contains("api/router.py", "application.phonepe", "/phonepe")
        self.assert_file_not_contains("api/router_lakshmi.py", "StoreCookie", "GrabOTP")
        self.assert_file_not_contains(
            "admin/application/partner/partner.py",
            "get_Phonepe",
            "add_Phonepe",
            "update_Phonepe",
            "del_Phonepe",
            "login_off_freecharge",
            "login_off_phonepe",
            "login_off_mobi",
            "login_off_airtel",
            "login_off_amazon",
            "freecharge",
            "phonepe",
            "mobikwik",
            "airtel",
            "amazon",
            "indus",
            "jio",
            "maha",
        )

    def test_app_no_longer_pushes_legacy_bank_redis_queues(self):
        self.assert_file_not_contains(
            "api/application/app/my/my.py",
            "application.phonepe",
            "login_phonepe",
            "login_freecharge",
            "login_mobi",
            "login_airtel",
            "login_indus",
            "login_jio",
            "PHONEPE",
            "FREECHARGE",
            "MOBIKWIK",
            "INDUS",
            "JIO",
        )

    def test_websocket_bank_analysis_no_longer_keeps_retired_bank_parsers(self):
        self.assert_file_not_contains(
            "api/application/websocket/bank_analysis.py",
            "async def indusind",
            "async def freecharge",
            "async def mobikwik",
            "async def maharastra",
        )

    def test_wallet_workers_do_not_keep_unreachable_indus_grab_upi_flow(self):
        for relative_path in ("api/jobs/pakistanpay_v2.py", "api/jobs/Jazzcashpay_v2.py"):
            self.assert_file_not_contains(
                relative_path,
                "indusupiprd.indusind.com",
                "verifyAppPinWeb",
                "com.mgs.induspsp",
                "def read_redis_list",
                "def encrypt_message",
                "def decrypt_message",
                "def get_standard_headers",
                "def safetyNetId",
            )
        self.assert_file_not_contains(
            "api/jobs/pakistanpay_v2.py",
            "def _should_force_statement_worker_offline",
        )

    def test_nginx_and_admin_frontend_no_longer_expose_phonepe(self):
        self.assert_file_not_contains("docker/nginx/default.conf", "phonepe")
        self.assert_file_not_contains("docker/nginx/tc160-brrr.conf", "phonepe")
        self.assert_file_not_contains("frontend_src/admin/src/api/partner.js", "phonepe")
        self.assert_file_not_contains("frontend_src/admin/src/router/index.js", "phonepe")


if __name__ == "__main__":
    unittest.main()
