import pytest


def test_ds_candidate_sql_keeps_current_push_order_filters():
    from application.pay.pay import build_ds_candidate_sql

    sql, params = build_ds_candidate_sql(
        amount=2000,
        channel_code="1001",
        target_payment_ids=[],
        dedicated_payment_ids=["533301", "533302"],
        limit=20,
    )

    assert "pay.collection_status = 1" in sql
    assert "find_in_set('1001'" in sql
    assert "pay.account_iban IS NOT NULL" in sql
    assert "pay.account_iban <> ''" in sql
    assert "pay.bank_type = 98" in sql
    assert "pay.bank_type_id = 98" in sql
    assert "p.balance >= %s" in sql
    assert "(p.ds_min <= %s OR p.ds_min = 0)" in sql
    assert "(p.ds_max >= %s OR p.ds_max = 0)" in sql
    assert "p.certified = 1" in sql
    assert "p.status = 1" in sql
    assert "JOIN vip v ON v.vip = p.vip" in sql
    assert "v.ds_min <= %s" in sql
    assert "v.ds_max >= %s" in sql
    assert "LEFT JOIN (" not in sql
    assert "GROUP BY partner_id" not in sql
    assert "pending_amount" not in sql
    assert "(p.balance - COALESCE" not in sql
    assert "pay.amount_top >= (" in sql
    assert "WHERE o.payment_id = pay.id" in sql
    assert "pay.id NOT IN (%s,%s)" in sql
    assert "ORDER BY COALESCE(pay.weight, 1) DESC, p.balance DESC, pay.id ASC" in sql
    assert "LIMIT %s" in sql
    assert "payment_online_ds" not in sql
    assert "payment_active_" not in sql
    assert "FOR UPDATE" not in sql
    assert "NOWAIT" not in sql

    assert params[-3:] == ["533301", "533302", 20]


def test_ds_candidate_sql_uses_target_payment_as_allow_list():
    from application.pay.pay import build_ds_candidate_sql

    sql, params = build_ds_candidate_sql(
        amount=1500,
        channel_code="1010",
        target_payment_ids=["533295", "533296"],
        dedicated_payment_ids=["533301"],
        limit=10,
    )

    assert "pay.id IN (%s,%s)" in sql
    assert "pay.id NOT IN" not in sql
    assert params[-3:] == ["533295", "533296", 10]


def test_ds_candidate_sql_does_not_require_iban_for_jazzcash():
    from application.pay.pay import build_ds_candidate_sql

    sql, params = build_ds_candidate_sql(
        amount=100,
        channel_code="1003",
        target_payment_ids=["533302"],
        limit=10,
    )

    assert "find_in_set('1003'" in sql
    assert "pay.collection_status = 1" in sql
    assert "pay.bank_type = 98" in sql
    assert "pay.bank_type_id = 98" in sql
    assert "OR (" in sql
    assert "pay.account_iban IS NOT NULL" in sql
    assert "pay.account_iban <> ''" in sql
    assert "pay.account_accno IS NOT NULL" not in sql
    assert "pay.account_accno <> ''" not in sql
    assert params[-2:] == ["533302", 10]


def test_collection_qrcode_gate_is_easypaisa_only():
    from application.pay.dispatch import _requires_collection_qrcode

    assert _requires_collection_qrcode(
        {"bank_type": 97, "bank_type_id": None},
        {"name": "EASYPAISA"},
    )
    assert _requires_collection_qrcode(
        {"bank_type": "97", "bank_type_id": None},
        {},
    )
    assert not _requires_collection_qrcode(
        {"bank_type": 98, "bank_type_id": None},
        {"name": "JAZZCASH"},
    )
    assert not _requires_collection_qrcode(
        {"bank_type": None, "bank_type_id": "98"},
        {},
    )


def test_ds_dispatch_nowait_error_detection():
    from application.pay.dispatch import _is_nowait_lock_error

    class MysqlError(Exception):
        pass

    assert _is_nowait_lock_error(MysqlError(3572, "Statement aborted because lock(s) could not be acquired immediately"))
    assert _is_nowait_lock_error(MysqlError(1205, "Lock wait timeout exceeded"))
    assert not _is_nowait_lock_error(MysqlError(1062, "Duplicate entry"))
    assert not _is_nowait_lock_error(RuntimeError("other error"))


@pytest.mark.asyncio
async def test_lock_ds_dispatch_candidate_locks_partner_then_payment_nowait():
    from application.pay.dispatch import _lock_ds_dispatch_candidate

    class FakeCursor:
        def __init__(self):
            self.calls = []

        async def execute(self, sql, params):
            self.calls.append((sql, params))
            return 1

        async def fetchone(self):
            if len(self.calls) == 1:
                return {"id": 33056, "balance": 1200}
            return {"id": 533302, "partner_id": 33056}

    cur = FakeCursor()

    partner, payment = await _lock_ds_dispatch_candidate(cur, 33056, 533302)

    assert partner["id"] == 33056
    assert payment["id"] == 533302
    assert "FROM partner" in cur.calls[0][0]
    assert "FOR UPDATE NOWAIT" in cur.calls[0][0]
    assert cur.calls[0][1] == (33056,)
    assert "FROM payment" in cur.calls[1][0]
    assert "FOR UPDATE NOWAIT" in cur.calls[1][0]
    assert cur.calls[1][1] == (533302,)


def test_push_order_locks_candidate_before_change_balance():
    import inspect
    from application.pay.dispatch import push_order

    source = inspect.getsource(push_order)

    assert "_lock_ds_dispatch_candidate(cur, partner['id'], payment_id)" in source
    assert source.index("_lock_ds_dispatch_candidate(cur, partner['id'], payment_id)") < source.index("handler.change_balance")


def test_push_order_uses_bank_specific_qrcode_gate():
    import inspect
    from application.pay.dispatch import push_order

    source = inspect.getsource(push_order)

    assert "_requires_collection_qrcode(payment, bank)" in source
    assert "order_ds_third_qr_" in source
    assert "不需要二维码" in source


def test_push_order_inserts_order_only_after_successful_dispatch():
    import inspect
    from application.pay.dispatch import push_order

    source = inspect.getsource(push_order)

    assert "_insert_order_ds_in_tx(handler, cur, insert_order_data)" in source
    assert "update orders_ds set" not in source.lower()
    assert "where code=%s and status=0" not in source.lower()
    assert source.index("handler.change_balance") < source.index("_insert_order_ds_in_tx")
