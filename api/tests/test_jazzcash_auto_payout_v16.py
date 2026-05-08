import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


AUTO_PAYOUT_SOURCES = [
    REPO_ROOT / "api" / "jobs" / "jazzcash" / "jazzcash_auto_payout.py",
    REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "account_selector.py",
    REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "order_lifecycle.py",
    REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "settlement.py",
    REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "transaction_log.py",
    REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "transfer_executor.py",
]


class JazzCashAutoPayoutV16SourceTests(unittest.TestCase):
    def read_source(self):
        return "\n".join(path.read_text() for path in AUTO_PAYOUT_SOURCES)

    def test_account_selection_uses_payout_final_status_without_account_selection(self):
        source = self.read_source()

        self.assertIn("payout_status = 1", source)
        self.assertNotIn("account_accno IS NOT NULL", source)
        self.assertNotIn("account_accno <> ''", source)
        self.assertNotIn("payment_info.get('account_accno')", source)
        self.assertNotIn("status = 1 AND certified = 1", source)

    def test_account_selection_does_not_use_legacy_redis_online_or_active_gate(self):
        source = self.read_source()

        self.assertNotIn("lpop(self.REDIS_KEYS['jazzcash_active_df'])", source)
        self.assertNotIn("rpush(self.REDIS_KEYS['jazzcash_active_df']", source)
        self.assertNotIn("sismember(self.REDIS_KEYS['jazzcash_online_df']", source)
        self.assertNotIn("sismember('payment_online_df'", source)
        self.assertNotIn("rpush('payment_active_df'", source)
        self.assertNotIn("降级使用Redis状态", source)
        self.assertIn("MySQL payout_status", source)

    def test_api_signing_uses_jazzcash_gateway(self):
        source = self.read_source()

        self.assertIn("from application.jazzcash_gateway import build_form_body", source)
        self.assertIn("build_form_body(", source)
        self.assertNotIn("payload_b64 = base64.b64encode", source)

    def test_orchestrator_passes_config_values_into_extracted_modules(self):
        orchestrator = (REPO_ROOT / "api" / "jobs" / "jazzcash" / "jazzcash_auto_payout.py").read_text()

        self.assertIn("conf.get('jazzcash_api_url'", orchestrator)
        self.assertIn("conf.get('jazzcash_user_id'", orchestrator)
        self.assertIn("conf.get('jazzcash_secret_key'", orchestrator)
        self.assertNotIn("getattr(conf, 'jazzcash_api_url'", orchestrator)

    def test_orchestrator_keeps_standalone_worker_entrypoint(self):
        orchestrator = (REPO_ROOT / "api" / "jobs" / "jazzcash" / "jazzcash_auto_payout.py").read_text()

        self.assertIn('if __name__ == "__main__"', orchestrator)
        self.assertIn('JazzCashAutoPayout("jazzcash_auto_payout")', orchestrator)
        self.assertIn("while True:", orchestrator)
        self.assertIn("bank.main()", orchestrator)

    def test_v16_code_semantics_do_not_mark_500_as_retry_or_reject(self):
        source = self.read_source()

        self.assertIn("manual_confirm", source)
        self.assertIn("elif code == 500", source)
        self.assertIn("elif code == 503", source)
        self.assertIn("error_code == 402", source)
        self.assertNotIn("error_code in [402, 423, 503]", source)

    def test_extracted_payout_modules_keep_methods_on_classes(self):
        from jobs.jazzcash.payout import (
            AccountSelector,
            OrderLifecycle,
            Settlement,
            TransactionLogger,
            TransferExecutor,
        )

        expected_methods = {
            AccountSelector: [
                "get_available_accounts",
                "get_mysql_payout_candidates",
                "release_selected_account",
                "get_lock",
                "fetch_balance_from_api",
                "filter_cooldown_orders",
                "acquire_account_lock",
            ],
            OrderLifecycle: [
                "get_pending_orders_by_time",
                "prepare_account_and_locks",
                "process_payout_order",
                "process_single_order_async",
            ],
            Settlement: [
                "get_cache_result",
                "handle_payout_success",
                "reject_order_with_refund",
                "set_payment_id_failed",
            ],
            TransactionLogger: [
                "set_transfer_executor",
                "log_complete_transaction",
                "_convert_to_bank_code",
            ],
            TransferExecutor: [
                "_execute_jazzcash_transfer",
                "_call_jazzcash_api",
                "_convert_to_bank_code",
                "_extract_transaction_id",
            ],
        }

        for cls, methods in expected_methods.items():
            with self.subTest(cls=cls.__name__):
                for method in methods:
                    self.assertTrue(callable(getattr(cls, method, None)), method)


if __name__ == "__main__":
    unittest.main()
