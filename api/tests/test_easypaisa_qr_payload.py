import datetime
import ast
import types
import unittest
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.pay import pay as pay_module


class _FakeCursor:
    def __init__(self, row):
        self.row = row
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, sql, params):
        self.executed.append((sql, params))
        return 1

    async def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, row):
        self.row = row

    def cursor(self, *_args):
        return _FakeCursor(self.row)


class _FakeAcquire:
    def __init__(self, row):
        self.row = row

    async def __aenter__(self):
        return _FakeConnection(self.row)

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDb:
    def __init__(self, row):
        self.row = row

    def acquire(self):
        return _FakeAcquire(self.row)


class EasyPaisaQrPayloadTests(unittest.IsolatedAsyncioTestCase):
    def test_collection_dispatch_does_not_read_legacy_kickoff_gate(self):
        source = Path(pay_module.__file__).read_text()
        tree = ast.parse(source)
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
                continue
            if not isinstance(node.func.value, ast.Attribute) or node.func.value.attr != "redis":
                continue
            first_arg = node.args[0] if node.args else None
            if not (
                isinstance(first_arg, ast.BinOp)
                and isinstance(first_arg.left, ast.Constant)
                and first_arg.left.value == "kick_off_"
            ):
                continue
            offenders.append(node.lineno)

        self.assertEqual(offenders, [])

    def test_build_payload_amount_matches_reference_dynamic_qr(self):
        payload = pay_module.build_payload_amount(
            iban="PK61TMFB0000000098214843",
            amount="500.00",
            timestamp="020520261857",
        )

        self.assertEqual(
            payload,
            "0002020102120202000424PK61TMFB0000000098214843050350007120205202618571004782A",
        )

    async def test_generate_qr_code_uses_amount_and_seven_minute_expiry(self):
        handler = pay_module.Pay.__new__(pay_module.Pay)
        handler.application = types.SimpleNamespace(
            db=_FakeDb({"account_iban": "PK61TMFB0000000098214843"})
        )
        handler.logger = types.SimpleNamespace(
            info=lambda *_args, **_kwargs: None,
            error=lambda *_args, **_kwargs: None,
        )
        pkt = datetime.timezone(datetime.timedelta(hours=5))
        now = datetime.datetime(2026, 5, 2, 18, 50, tzinfo=pkt).timestamp()

        with mock.patch.object(pay_module.time, "time", return_value=now):
            payload = await handler.generate_qr_code(
                payment_id="533295",
                account_id="03123456789",
                amount="500.00",
            )

        self.assertEqual(
            payload,
            "0002020102120202000424PK61TMFB0000000098214843050350007120205202618571004782A",
        )
        self.assertIn("010212", payload)
        self.assertIn("0503500", payload)
        self.assertIn("0712020520261857", payload)


if __name__ == "__main__":
    unittest.main()
