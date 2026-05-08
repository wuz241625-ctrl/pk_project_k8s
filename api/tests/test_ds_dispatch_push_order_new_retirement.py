from pathlib import Path


def test_ds_order_flow_does_not_call_push_order_new_fallback():
    source = Path("api/application/pay/pay.py").read_text()

    assert "await self.push_order_new(" not in source
    assert "调用 push_order_new" not in source
    assert "push_order_new准备派单" not in source
