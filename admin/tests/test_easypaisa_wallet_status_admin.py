import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
ADMIN_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if ADMIN_ROOT not in sys.path:
    sys.path.insert(0, ADMIN_ROOT)

from application.partner.partner import (
    apply_easypaisa_wallet_status_fields,
    easypaisa_business_status_from_config,
    easypaisa_reset_account_fields_sql,
    payment_business_status_select_keys,
    payment_wallet_status_select_key,
    reset_easypaisa_redis_state,
)


class EasyPaisaWalletStatusAdminTests(unittest.IsolatedAsyncioTestCase):
    def test_payment_list_selects_wallet_status_for_active_payment_table(self):
        self.assertEqual(payment_wallet_status_select_key("payment"), "a.wallet_status")
        self.assertEqual(payment_wallet_status_select_key("payment_d"), "0 AS wallet_status")
        self.assertEqual(
            payment_business_status_select_keys("payment"),
            ["a.collection_status", "a.payout_status"],
        )
        self.assertEqual(
            payment_business_status_select_keys("payment_d"),
            ["0 AS collection_status", "0 AS payout_status"],
        )

    def test_reset_clears_selected_account_fields_wallet_and_final_dispatch_statuses(self):
        sql = easypaisa_reset_account_fields_sql()

        self.assertIn("account_accno=NULL", sql)
        self.assertIn("account_iban=NULL", sql)
        self.assertIn("account_entire=NULL", sql)
        self.assertIn("wallet_status=0", sql)
        self.assertIn("collection_status=0", sql)
        self.assertIn("payout_status=0", sql)

    def test_display_formula_allows_df_but_not_ds_when_manual_locked(self):
        row = {
            "id": 533280,
            "bank_type_id": 97,
            "wallet_status": 1,
            "collection_status": 0,
            "payout_status": 1,
            "status": 1,
            "certified": 1,
            "manual_status": 1,
            "account_accno": "98525348",
        }

        apply_easypaisa_wallet_status_fields(row)

        self.assertEqual(row["online_status"], 1)
        self.assertEqual(row["online_df"], 1)
        self.assertEqual(row["online_ds"], 0)

    def test_display_formula_uses_final_business_status_only(self):
        row = {
            "id": 533281,
            "bank_type": "97",
            "wallet_status": 1,
            "collection_status": 1,
            "payout_status": 1,
            "status": 0,
            "certified": 1,
            "manual_status": 0,
            "account_accno": "98525348",
        }

        apply_easypaisa_wallet_status_fields(row)

        self.assertEqual(row["online_status"], 1)
        self.assertEqual(row["online_df"], 1)
        self.assertEqual(row["online_ds"], 1)

    def test_display_formula_treats_wallet_status_as_selected_account(self):
        row = {
            "id": 533283,
            "bank_type": "97",
            "wallet_status": 1,
            "collection_status": 1,
            "payout_status": 1,
            "status": 1,
            "certified": 1,
            "manual_status": 0,
            "account_accno": "",
        }

        apply_easypaisa_wallet_status_fields(row)

        self.assertEqual(row["online_status"], 1)
        self.assertEqual(row["online_df"], 1)
        self.assertEqual(row["online_ds"], 1)

    def test_display_formula_offline_wallet_only_affects_online_status(self):
        row = {
            "id": 533282,
            "bank_type_id": 97,
            "wallet_status": 0,
            "collection_status": 1,
            "payout_status": 1,
            "status": 1,
            "certified": 1,
            "manual_status": 0,
            "account_accno": "98525348",
        }

        apply_easypaisa_wallet_status_fields(row)

        self.assertEqual(row["online_status"], 0)
        self.assertEqual(row["online_df"], 1)
        self.assertEqual(row["online_ds"], 1)

    def test_manual_unlock_restores_collection_only_when_wallet_business_enabled(self):
        self.assertEqual(
            easypaisa_business_status_from_config(
                wallet_status=1,
                status=1,
                certified=1,
                manual_status=0,
            ),
            {"collection_status": 1, "payout_status": 1},
        )
        self.assertEqual(
            easypaisa_business_status_from_config(
                wallet_status=0,
                status=1,
                certified=1,
                manual_status=0,
            ),
            {"collection_status": 0, "payout_status": 0},
        )
        self.assertEqual(
            easypaisa_business_status_from_config(
                wallet_status=1,
                status=1,
                certified=1,
                manual_status=1,
            ),
            {"collection_status": 0, "payout_status": 1},
        )

    async def test_reset_easypaisa_redis_state_clears_explicit_reset_scope(self):
        import fakeredis.aioredis

        redis = fakeredis.aioredis.FakeRedis()
        payment_id = 533295
        await redis.set(f"pre_login_easypaisa_{payment_id}", "1")
        await redis.set(f"easypaisa_runtime:session:{payment_id}", "1")
        await redis.set(f"easypaisa_runtime:kickoff:{payment_id}", "1")
        await redis.set(f"kick_off_{payment_id}", "1")
        await redis.set(f"easypaisa_runtime:snapshot:{payment_id}", "1")
        await redis.set(f"easypaisa_runtime:health_pause:order:{payment_id}", "1")
        await redis.set(f"easypaisa_runtime:lock:payment:{payment_id}", "1")
        await redis.hset("hash_easypaisa", str(payment_id), '{"status":"grabstatement"}')
        await redis.zadd("set_easypaisa", {str(payment_id): 1000})
        await redis.sadd("payment_online_ds", str(payment_id))
        await redis.sadd("payment_online_df", str(payment_id))
        await redis.rpush("payment_active_1001", str(payment_id))
        await redis.rpush("payment_active_df", str(payment_id))
        for key in (
            "easypaisa_runtime:index:online",
            "easypaisa_runtime:index:collect_enabled",
            "easypaisa_runtime:index:df_order_enabled",
            "easypaisa_runtime:index:ds_order_enabled",
            "easypaisa_runtime:index:dispatch_df",
            "easypaisa_runtime:index:dispatch_ds",
        ):
            await redis.sadd(key, str(payment_id))
        await redis.zadd("easypaisa_runtime:schedule:collection", {str(payment_id): 1000})
        await redis.zadd("easypaisa_runtime:index:updated_at", {str(payment_id): 1000})

        result = await reset_easypaisa_redis_state(redis, payment_id, channels=["1001"])

        self.assertEqual(result["removed_job_hash"], 1)
        self.assertEqual(result["removed_job_set"], 1)
        self.assertIsNone(await redis.get(f"pre_login_easypaisa_{payment_id}"))
        self.assertIsNone(await redis.get(f"easypaisa_runtime:session:{payment_id}"))
        self.assertIsNone(await redis.get(f"easypaisa_runtime:snapshot:{payment_id}"))
        self.assertIsNone(await redis.hget("hash_easypaisa", str(payment_id)))
        self.assertIsNone(await redis.zscore("set_easypaisa", str(payment_id)))
        self.assertFalse(await redis.sismember("payment_online_ds", str(payment_id)))
        self.assertFalse(await redis.sismember("payment_online_df", str(payment_id)))
        self.assertEqual(await redis.lrange("payment_active_1001", 0, -1), [])
        self.assertEqual(await redis.lrange("payment_active_df", 0, -1), [])
        self.assertFalse(await redis.sismember("easypaisa_runtime:index:online", str(payment_id)))
        self.assertIsNone(await redis.zscore("easypaisa_runtime:schedule:collection", str(payment_id)))


if __name__ == "__main__":
    unittest.main()
