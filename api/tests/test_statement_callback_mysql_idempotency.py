import sys
import unittest
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


WORKER_SOURCES = [
    REPO_ROOT / "api" / "jobs" / "pakistanpay_v2.py",
    REPO_ROOT / "api" / "jobs" / "Jazzcashpay_v2.py",
]
UTR_CALLBACK = REPO_ROOT / "api" / "application" / "pay" / "utr_callback.py"
ORDER_CALLBACK = REPO_ROOT / "api" / "application" / "pay" / "order.py"
WEBSOCKET_CALLBACK = REPO_ROOT / "api" / "application" / "websocket" / "callback.py"
EASYPAISA_PAYOUT_SETTLEMENT = REPO_ROOT / "api" / "jobs" / "easypaisa" / "payout" / "settlement.py"
JAZZCASH_PAYOUT_SETTLEMENT = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "settlement.py"
JAZZCASH_TRANSFER_EXECUTOR = REPO_ROOT / "api" / "jobs" / "jazzcash" / "payout" / "transfer_executor.py"


class StatementCallbackMysqlIdempotencySourceTests(unittest.TestCase):
    def test_statement_workers_do_not_skip_callbacks_by_redis_marker(self):
        for source_path in WORKER_SOURCES:
            with self.subTest(source=source_path.name):
                source = source_path.read_text()
                self.assertNotIn("zscore(self.if_callback_key", source)
                self.assertNotIn("mark_transaction_callback(", source)
                self.assertNotIn("clean_if_callback_key()", source)

    def test_mysql_callback_paths_keep_order_and_statement_guards(self):
        utr_callback = UTR_CALLBACK.read_text()
        order_callback = ORDER_CALLBACK.read_text()

        self.assertIn("where code=%s and status in (-1,1,2)", utr_callback)
        self.assertIn("callback=0 and trade_type=1", utr_callback)
        self.assertIn("update bank_record set callback=1,order_code=%s", utr_callback)
        self.assertIn("trans_id", utr_callback)

        self.assertIn("get_result_by_condition('bank_record'", order_callback)
        self.assertIn("create_result('bank_record'", order_callback)
        self.assertIn("success_busy_{trans_id}", order_callback)

    def test_order_success_locks_statement_before_business_callback(self):
        order_callback = ORDER_CALLBACK.read_text()

        self.assertIn("async def _handle_pakistan_statement_callback", order_callback)
        helper = order_callback.split("async def _handle_pakistan_statement_callback", 1)[1]
        lock_index = helper.index("await self.redis.setnx(lock_key, '1')")
        duplicate_index = helper.index("get_result_by_condition('bank_record'")
        success_ds_index = helper.index("callback.success_ds")
        success_df_index = helper.index("callback.success_df")

        self.assertLess(lock_index, duplicate_index)
        self.assertLess(lock_index, success_ds_index)
        self.assertLess(lock_index, success_df_index)

    def test_duplicate_statement_is_accepted_without_business_callback_retry(self):
        order_callback = ORDER_CALLBACK.read_text()

        self.assertIn("Duplicate statement accepted", order_callback)
        self.assertIn("statement_record.get('callback')", order_callback)
        self.assertIn("bank_record.callback=0 只允许补单链路处理", order_callback)
        self.assertNotIn("发现重复的代收订单: UTR={data['utr']}, 金额={data['amount']}\")\n                            return await self.json_response(msg[10019])", order_callback)
        self.assertNotIn("发现重复的代付订单: trans_id={data['trans_id']}\")\n                            return await self.json_response(msg[10019])", order_callback)

    def test_pakistan_callback_names_separate_payer_phone_and_statement_ref(self):
        callback_source = WEBSOCKET_CALLBACK.read_text()

        self.assertIn("付款手机号(utr字段)", callback_source)
        self.assertIn("statement_ref = data['trans_id']", callback_source)
        self.assertIn("payout_match_account = data['account']", callback_source)
        self.assertIn("orders_df.utr 成功后写官方交易号", callback_source)
        self.assertNotIn("source_utr = data['trans_id']", callback_source)
        self.assertNotIn("final_utr = data['utr']", callback_source)
        self.assertNotIn("需要将account作为收款手机号→作为utr的数据处理", callback_source)

    def test_payout_settlement_does_not_claim_payer_phone_updates_order_utr(self):
        for source_path in [EASYPAISA_PAYOUT_SETTLEMENT, JAZZCASH_PAYOUT_SETTLEMENT, JAZZCASH_TRANSFER_EXECUTOR]:
            with self.subTest(source=source_path.name):
                source = source_path.read_text()
                self.assertNotIn("付款手机号用于更新utr字段", source)
                self.assertNotIn("未获取到付款手机号，utr字段保持原值", source)


if __name__ == "__main__":
    unittest.main()
