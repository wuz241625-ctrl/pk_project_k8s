import asyncio
import unittest
from decimal import Decimal
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "api" / "sql" / "20260509_add_fund_integrity_constraints.sql"


class FakeAsyncCursor:
    def __init__(self, affected=1):
        self.affected = affected
        self.executed = []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self.affected


class FakeSyncCursor:
    def __init__(self, affected=1):
        self.affected = affected
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self.affected


class FundIntegrityContractTests(unittest.TestCase):
    def test_migration_declares_order_statement_and_balance_idempotency_contracts(self):
        sql = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("uk_orders_df_merchant_code", sql)
        self.assertIn("`orders_df`", sql)
        self.assertIn("`merchant_id`, `merchant_code`", sql)
        self.assertIn("orders_ds_trans_id_unique", sql)
        self.assertIn("uk_orders_ds_trans_id_unique", sql)
        self.assertIn("bank_record_trans_id_unique", sql)
        self.assertIn("uk_bank_record_payment_trade_trans", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS `balance_record_idempotency`", sql)
        self.assertIn("PRIMARY KEY (`idempotency_key`)", sql)
        self.assertIn("INFORMATION_SCHEMA.STATISTICS", sql)

    def test_balance_idempotency_key_skips_empty_or_legacy_zero_code(self):
        from application.balance_idempotency import build_balance_idempotency_key

        self.assertIsNone(build_balance_idempotency_key(None, 1, 10, Decimal("1.00"), 0))
        self.assertIsNone(build_balance_idempotency_key("", 1, 10, Decimal("1.00"), 0))
        self.assertIsNone(build_balance_idempotency_key("0", 1, 10, Decimal("1.00"), 0))

    def test_balance_idempotency_key_is_stable_for_same_business_event(self):
        from application.balance_idempotency import build_balance_idempotency_key

        left = build_balance_idempotency_key("DF123", 1, 20, Decimal("10.0"), 3)
        right = build_balance_idempotency_key("DF123", "1", "20", "10.0000", "3")

        self.assertEqual(left, right)
        self.assertEqual(len(left), 64)

    def test_async_reservation_returns_false_for_duplicate_business_key(self):
        from application.balance_idempotency import reserve_balance_idempotency

        cursor = FakeAsyncCursor(affected=0)
        result = asyncio.run(
            reserve_balance_idempotency(
                cursor,
                "a" * 64,
                code="DF123",
                user_type=1,
                user_id=20,
                amount=Decimal("10.00"),
                record_type=3,
            )
        )

        self.assertFalse(result)
        self.assertIn("INSERT IGNORE INTO `balance_record_idempotency`", cursor.executed[0][0])

    def test_sync_reservation_returns_true_for_new_business_key(self):
        from application.balance_idempotency import reserve_balance_idempotency_sync

        cursor = FakeSyncCursor(affected=1)
        result = reserve_balance_idempotency_sync(
            cursor,
            "b" * 64,
            code="DF123",
            user_type=1,
            user_id=20,
            amount=Decimal("10.00"),
            record_type=3,
        )

        self.assertTrue(result)
        self.assertIn("INSERT IGNORE INTO `balance_record_idempotency`", cursor.executed[0][0])

    def test_core_balance_writers_reserve_idempotency_before_balance_update(self):
        expected_files = [
            "api/application/base.py",
            "admin/application/base.py",
            "merchant/application/base.py",
            "api/jobs/easypaisa/payout/settlement.py",
            "api/jobs/jazzcash/payout/settlement.py",
        ]

        for relative in expected_files:
            source = (REPO_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("build_balance_idempotency_key", source, relative)
            self.assertIn("reserve_balance_idempotency", source, relative)


if __name__ == "__main__":
    unittest.main()
