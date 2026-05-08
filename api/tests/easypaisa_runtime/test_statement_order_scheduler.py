import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs"))

REPO_ROOT = Path(__file__).resolve().parents[3]
EASYPAISA_WORKER_SOURCE = REPO_ROOT / "api" / "jobs" / "pakistanpay_v2.py"


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.current_rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))
        normalized = " ".join(sql.split())
        if "FROM orders_ds" in normalized:
            self.current_rows = list(self.connection.ds_rows)
        elif "FROM orders_df" in normalized:
            self.current_rows = list(self.connection.df_rows)
        elif "FROM payment" in normalized:
            self.current_rows = list(self.connection.payment_rows)
        else:
            self.current_rows = []
        return len(self.current_rows)

    def fetchall(self):
        return list(self.current_rows)

    def fetchone(self):
        return self.current_rows[0] if self.current_rows else None


class FakeConnection:
    open = True

    def __init__(self, ds_rows=None, df_rows=None, payment_rows=None):
        self.ds_rows = ds_rows or []
        self.df_rows = df_rows or []
        self.payment_rows = payment_rows or [{"id": 533295, "wallet_status": 1}]
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.hashes = {}
        self.zsets = {}

    def get(self, key):
        return self.kv.get(key)

    def setnx(self, key, value):
        if key in self.kv:
            return False
        self.kv[key] = value
        return True

    def expire(self, key, ttl):
        return True

    def setex(self, key, ttl, value):
        self.kv[key] = value
        return True

    def delete(self, key):
        self.kv.pop(key, None)
        return 1

    def exists(self, key):
        return key in self.kv

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(str(field))

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[str(field)] = value
        return 1

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update({str(k): v for k, v in mapping.items()})
        return 1

    def zscore(self, key, member):
        return self.zsets.get(key, {}).get(str(member))

    def zrem(self, key, member):
        self.zsets.setdefault(key, {}).pop(str(member), None)
        return 1

    def hdel(self, key, field):
        self.hashes.setdefault(key, {}).pop(str(field), None)
        return 1


class FakeQueryBillResponse:
    def __init__(self, payload, status=200, content_type="application/json"):
        self.payload = payload
        self.status = status
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return str(self.payload)


class FakeQueryBillSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.post_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        self.post_calls += 1
        return self.responses.pop(0)


class EasyPaisaStatementOrderSchedulerTests(unittest.TestCase):
    def _bank(self, ds_rows=None, df_rows=None, payment_rows=None):
        from jobs.pakistanpay_v2 import BankLogin

        bank = BankLogin.__new__(BankLogin)
        bank.name = "easypaisa"
        bank.if_callback_key = "if_callback_easypaisa"
        bank.lock_time = 30
        bank.statement_ds_window_seconds = 7 * 60
        bank.statement_df_window_seconds = 10 * 60
        bank.statement_df_probe_interval = 2 * 60
        bank.redis = FakeRedis()
        bank.logger = MagicMock()
        bank.db_connection = FakeConnection(ds_rows, df_rows, payment_rows)
        bank.check_db_connection = MagicMock(return_value=bank.db_connection)
        return bank

    def test_no_pending_statement_orders_skips_bill_query(self):
        bank = self._bank()
        bank.getBills = AsyncMock()

        result = asyncio.run(bank.get_grabstatement(533295))

        self.assertTrue(result)
        bank.getBills.assert_not_awaited()
        executed_sql = "\n".join(sql for sql, _ in bank.db_connection.executed)
        self.assertIn("FROM orders_ds", executed_sql)
        self.assertIn("FROM orders_df", executed_sql)
        self.assertIn("status IN (1, 2)", executed_sql)
        self.assertIn("status = 2", executed_sql)

    def test_main_runs_health_balance_when_no_due_statement_orders(self):
        bank = self._bank()
        bank.reconcile_wallet_status_from_mysql = MagicMock(return_value={"confirm": 0, "offline": 0, "noop": 0})
        bank.fetch_due_statement_payment_ids = MagicMock(return_value=[])
        bank.run_health_balance_check_once = MagicMock(return_value=True)
        bank.clean_if_callback_key = MagicMock()

        with patch("jobs.pakistanpay_v2.time.sleep") as sleep_mock:
            bank.main()

        bank.run_health_balance_check_once.assert_called_once()
        bank.clean_if_callback_key.assert_called_once()
        sleep_mock.assert_called_once_with(2)

    def test_main_still_runs_health_balance_when_statement_orders_are_due(self):
        bank = self._bank()
        bank.reconcile_wallet_status_from_mysql = MagicMock(return_value={"confirm": 0, "offline": 0, "noop": 0})
        bank.fetch_due_statement_payment_ids = MagicMock(return_value=["533295"])
        bank.get_process_allocated_members = MagicMock(return_value=[b"533295"])
        bank.run_health_balance_check_once = MagicMock(return_value=True)
        bank.process_statement_payment_ids_concurrent = AsyncMock(return_value=None)

        bank.main()

        bank.run_health_balance_check_once.assert_called_once()
        bank.process_statement_payment_ids_concurrent.assert_awaited_once_with(["533295"], concurrent_limit=20)

    def test_health_balance_check_once_uses_30_second_redis_throttle(self):
        bank = self._bank()
        bank.run_health_balance_check = AsyncMock(return_value=True)

        first = bank.run_health_balance_check_once()
        second = bank.run_health_balance_check_once()

        self.assertTrue(first)
        self.assertFalse(second)
        bank.run_health_balance_check.assert_awaited_once()
        self.assertIn("easypaisa_health_balance_check_lock", bank.redis.kv)

    def test_due_payment_scan_uses_mysql_orders_not_hash_set_queue(self):
        bank = self._bank(payment_rows=[{"id": 533295}])

        self.assertEqual(bank.fetch_due_statement_payment_ids(), ["533295"])

        executed_sql = "\n".join(sql for sql, _ in bank.db_connection.executed)
        self.assertIn("JOIN orders_ds", executed_sql)
        self.assertIn("JOIN orders_df", executed_sql)
        self.assertIn("wallet_status = 1", executed_sql)
        self.assertIn("LIMIT 200", executed_sql)

    def test_due_order_scan_uses_mysql_account_context_only(self):
        ds_order = {"code": "DS001", "payment_id": 533295, "partner_id": 33056, "amount": "100.00"}
        payment_row = {
            "id": 533295,
            "wallet_status": 1,
            "phone": "03325009516",
            "partner_id": 33056,
            "account_accno": "98525348",
        }
        bank = self._bank(ds_rows=[ds_order], payment_rows=[payment_row])
        bank.getBills = AsyncMock(return_value={"is_success": True, "transaction_history_list": []})

        result = asyncio.run(bank.get_grabstatement(533295))

        self.assertTrue(result)
        bank.getBills.assert_awaited_once()
        account_context = bank.getBills.await_args.args[0]
        self.assertEqual(account_context["phone"], "03325009516")
        self.assertEqual(account_context["partner_id"], 33056)
        self.assertEqual(account_context["account_accno"], "98525348")
        self.assertNotIn("time", account_context)
        self.assertNotIn("count", account_context)
        self.assertNotIn("if_first_time", account_context)
        self.assertNotIn("try_count", account_context)
        self.assertNotIn("account_iban", account_context)
        self.assertNotIn("account_entire", account_context)
        self.assertNotIn("net_trade_pw", account_context)

    def test_payout_statement_match_is_observation_only_without_callback(self):
        df_order = {
            "code": "DF001",
            "payment_id": 533295,
            "amount": "100.00",
            "time_accept": "2026-05-08 12:00:00",
            "payment_account": "03001234567",
        }
        bank = self._bank(df_rows=[df_order])
        bank.send = AsyncMock(return_value={"is_success": True})
        bank.getBills = AsyncMock(return_value={
            "is_success": True,
            "transaction_history_list": [
                {
                    "orderNo": "UTR001",
                    "amount": 100.0,
                    "tradeTime": "2026-05-08T12:03:00",
                    "appTransaction": True,
                    "busTypeName": "Transfer",
                    "historyDetailRspDTO": {
                        "fromFri": "FRI:923325009516/MSISDN",
                        "gatherNo": "AC03001234567",
                        "accountNo": "03001234567",
                        "fee": 0,
                        "extOrderNo": "EXT001",
                    },
                }
            ],
        })

        result = asyncio.run(bank.grabstatement(
            {"id": 533295, "partner_id": 33056, "phone": "03325009516"},
            statement_context={"df_orders": [df_order], "ds_orders": [], "has_due": True},
        ))

        self.assertTrue(result)
        bank.send.assert_not_awaited()
        info_logs = "\n".join(str(call.args[0]) for call in bank.logger.info.call_args_list if call.args)
        self.assertIn("代付账单观测匹配", info_logs)
        self.assertIn("不回调", info_logs)

    def test_query_bill_423_fast_retries_once_then_uses_success_response(self):
        bank = self._bank()
        session = FakeQueryBillSession([
            FakeQueryBillResponse({"code": 423, "msg": "ServerBusy", "data": {}}),
            FakeQueryBillResponse({
                "code": 200,
                "msg": "queryBill成功",
                "data": {"body": {"transactionHistory": [{"orderNo": "UTR001"}]}},
            }),
        ])

        with patch("jobs.pakistanpay_v2.aiohttp.ClientSession", return_value=session), \
             patch("jobs.pakistanpay_v2.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = asyncio.run(bank.getBills({
                "id": 533295,
                "phone": "03325009516",
                "account_accno": "98525348",
            }))

        self.assertTrue(result["is_success"])
        self.assertEqual(result["transaction_history_list"], [{"orderNo": "UTR001"}])
        self.assertEqual(session.post_calls, 2)
        sleep_mock.assert_awaited_once_with(2)

    def test_query_bill_500_does_not_fast_retry(self):
        bank = self._bank()
        session = FakeQueryBillSession([
            FakeQueryBillResponse({"code": 500, "msg": "official error", "data": {}}),
        ])

        with patch("jobs.pakistanpay_v2.aiohttp.ClientSession", return_value=session), \
             patch("jobs.pakistanpay_v2.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = asyncio.run(bank.getBills({
                "id": 533295,
                "phone": "03325009516",
                "account_accno": "98525348",
            }))

        self.assertFalse(result["is_success"])
        self.assertEqual(result["error_code"], 500)
        self.assertEqual(session.post_calls, 1)
        sleep_mock.assert_not_awaited()

    def test_retired_abnormal_payout_redis_helper_is_removed(self):
        source = EASYPAISA_WORKER_SOURCE.read_text()

        self.assertNotIn("payment_id_failed", source)
        self.assertNotIn("ABNORMAL_PAYOUTS_KEY", source)
        self.assertNotIn("verify_and_handle_abnormal_payout", source)

    def test_order_driven_statement_scheduler_has_no_legacy_runtime_timing(self):
        source = EASYPAISA_WORKER_SOURCE.read_text()

        self.assertNotIn("crawl_frequently_", source)
        self.assertNotIn("if_first_time", source)
        self.assertNotIn("last_grab_failed", source)
        self.assertNotIn("time_grab", source)
        self.assertNotIn("upi", source.lower())
        self.assertNotIn("_wallet_collection_account_context", source)
        self.assertNotIn("grabUpi", source)
        self.assertNotIn("sync_mysql_wallet_collection_accounts", source)
        self.assertNotIn("process_single_member_async", source)
        self.assertNotIn("process_members_concurrent", source)
        self.assertNotIn("zrangebyscore", source)
        self.assertNotIn("hash_key", source)
        self.assertNotIn("set_key", source)
        self.assertNotIn("sendMsg", source)
        self.assertNotIn("login_off", source)
        self.assertNotIn("login_on_", source)
        self.assertNotIn("on_off", source)
        self.assertNotIn("update_key", source)
        self.assertNotIn("account_iban", source)
        self.assertNotIn("account_entire", source)
        self.assertNotIn("net_trade_pw", source)
        self.assertNotIn("login_data", source)


if __name__ == "__main__":
    unittest.main()
