import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class EasyPaisaLegacyStateRetirementTests(unittest.TestCase):
    def _read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding='utf-8')

    def test_retired_jobs_are_removed(self):
        for relative_path in [
            'api/jobs/order_push.py',
            'api/jobs/clear_redis_dsdf.py',
            'api/jobs/clear_redis_inactive_payment.py',
            'api/jobs/collect_partner_status.py',
            'api/jobs/weight.py',
        ]:
            self.assertFalse((ROOT / relative_path).exists(), relative_path)

    def test_time_out_does_not_requeue_payment_active(self):
        source = self._read('api/jobs/time_out.py')

        self.assertNotIn("rpush(list_name", source)
        self.assertNotIn("payment_active_{channel_code}", source)
        self.assertNotIn("TimeOutGuard", source)

    def test_app_login_does_not_import_runtime_service(self):
        source = self._read('api/application/app/login/banks/easypaisa.py')

        self.assertNotIn("EasyPaisaRuntimeService", source)
        self.assertNotIn("self.runtime_service", source)
        self.assertNotIn("write_snapshot", source)
        self.assertNotIn("mark_active_successful", source)

    def test_monitor_does_not_import_runtime_service(self):
        source = self._read('api/application/websocket/monitor.py')

        self.assertNotIn("EasyPaisaRuntimeService", source)
        self.assertNotIn("set_ds_order_dispatch", source)
        self.assertNotIn("set_df_order_dispatch", source)
