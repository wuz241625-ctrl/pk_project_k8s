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
    assert "p.balance >= %s" in sql
    assert "(p.ds_min <= %s OR p.ds_min = 0)" in sql
    assert "(p.ds_max >= %s OR p.ds_max = 0)" in sql
    assert "p.certified = 1" in sql
    assert "p.status = 1" in sql
    assert "JOIN vip v ON v.vip = p.vip" in sql
    assert "v.ds_min <= %s" in sql
    assert "v.ds_max >= %s" in sql
    assert "LEFT JOIN (" in sql
    assert "FROM orders_ds" in sql
    assert "status IN (0, 1, 2)" in sql
    assert "GROUP BY partner_id" in sql
    assert "(p.balance - COALESCE(pend.pending_amount, 0)) >= %s" in sql
    assert "pay.amount_top >= (" in sql
    assert "WHERE o.payment_id = pay.id" in sql
    assert "pay.id NOT IN (%s,%s)" in sql
    assert "ORDER BY COALESCE(pend.pending_amount, 0) ASC, COALESCE(pay.weight, 1) DESC, pay.id ASC" in sql
    assert "LIMIT %s" in sql
    assert "payment_online_ds" not in sql
    assert "payment_active_" not in sql

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
