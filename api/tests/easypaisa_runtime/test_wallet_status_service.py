import unittest


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))
        return self.connection.rowcount


class FakeConnection:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1


class PaymentWalletStatusSchemaTests(unittest.TestCase):
    def test_upi_payment_schema_declares_wallet_status(self):
        from application.lakshmi_api.schema.payment_schema import UpiPaymentSchema

        schema = UpiPaymentSchema()

        self.assertIn("wallet_status", schema.fields)


class WorkerWalletStatusServiceTests(unittest.TestCase):
    def test_mark_available_requires_selected_account(self):
        from jobs.easypaisa.wallet_status_service import WorkerWalletStatusService

        connection = FakeConnection(rowcount=1)
        service = WorkerWalletStatusService(connection)

        affected = service.mark_available(533280, "login_confirmed")

        self.assertEqual(affected, 1)
        self.assertEqual(connection.commits, 1)
        sql, params = connection.executed[0]
        self.assertEqual(params, (533280,))
        self.assertIn("SET wallet_status = 1", sql)
        self.assertIn("collection_status = CASE", sql)
        self.assertIn("payout_status = CASE", sql)
        self.assertIn("status = 1", sql)
        self.assertIn("certified = 1", sql)
        self.assertIn("manual_status = 0", sql)
        self.assertIn("account_accno IS NOT NULL", sql)
        self.assertIn("account_accno <> ''", sql)

    def test_mark_offline_is_idempotent(self):
        from jobs.easypaisa.wallet_status_service import WorkerWalletStatusService

        connection = FakeConnection(rowcount=0)
        service = WorkerWalletStatusService(connection)

        affected = service.mark_offline(533280, "session_invalid")

        self.assertEqual(affected, 0)
        self.assertEqual(connection.commits, 1)
        sql, params = connection.executed[0]
        self.assertEqual(params, (533280,))
        self.assertIn("SET wallet_status = 0", sql)
        self.assertIn("collection_status = 0", sql)
        self.assertIn("payout_status = 0", sql)
        self.assertIn("wallet_status <> 0", sql)
        self.assertIn("collection_status <> 0", sql)
        self.assertIn("payout_status <> 0", sql)

    def test_reconcile_wallet_status_row_returns_expected_action(self):
        from jobs.easypaisa.wallet_status_service import WorkerWalletStatusService

        self.assertEqual(
            WorkerWalletStatusService.reconcile_wallet_status_row(
                {"account_accno": "88521642", "wallet_status": 0}
            ),
            "confirm",
        )
        self.assertEqual(
            WorkerWalletStatusService.reconcile_wallet_status_row(
                {"account_accno": "", "wallet_status": 1}
            ),
            "offline",
        )
        self.assertEqual(
            WorkerWalletStatusService.reconcile_wallet_status_row(
                {"account_accno": "88521642", "wallet_status": 1}
            ),
            "noop",
        )


if __name__ == "__main__":
    unittest.main()
