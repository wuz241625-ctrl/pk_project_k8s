from pathlib import Path


ADMIN_ROOT = Path(__file__).resolve().parents[1]


def test_admin_order_requeue_does_not_clean_legacy_payment_active_df():
    source = (ADMIN_ROOT / "application" / "order" / "order.py").read_text(encoding="utf-8")

    assert "payment_" + "active_df" not in source
    assert "async def requeue_df_if_online" in source
