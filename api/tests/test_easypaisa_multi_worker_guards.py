import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PAKISTAN_WORKER = REPO_ROOT / "api" / "jobs" / "pakistanpay_v2.py"
ORDER_CALLBACK = REPO_ROOT / "api" / "application" / "pay" / "order.py"
WEBSOCKET_CALLBACK = REPO_ROOT / "api" / "application" / "websocket" / "callback.py"
DISPATCH = REPO_ROOT / "api" / "application" / "pay" / "dispatch.py"
REDIS_CLIENT = REPO_ROOT / "api" / "jobs" / "easypaisa" / "common" / "redis_client.py"
INITIAL_SCHEMA = REPO_ROOT / "api" / "migrations" / "20240327134145_initial" / "migration.sql"
UNIQUE_MIGRATION = REPO_ROOT / "api" / "migrations" / "20260508170000_add_orders_ds_merchant_code_unique" / "migration.sql"


def test_easypaisa_worker_only_scans_submitted_collection_orders():
    source = PAKISTAN_WORKER.read_text()

    assert "AND status = 2" in source
    assert "AND od.status = 2" in source
    assert "AND status IN (1, 2)" not in source
    assert "AND od.status IN (1, 2)" not in source
    assert "AND utr IS NOT NULL" in source
    assert "AND od.utr IS NOT NULL" in source
    assert "_credit_statement_matches_due_order" in source
    assert "CREDIT流水未匹配 status=2 待确认订单" in source


def test_easypaisa_statement_locks_are_atomic_and_worker_concurrency_is_capped():
    worker_source = PAKISTAN_WORKER.read_text()
    redis_source = REDIS_CLIENT.read_text()

    assert "self.statement_concurrent_limit" in worker_source
    assert "concurrent_limit=self.statement_concurrent_limit" in worker_source
    assert "concurrent_limit: int = 3" in worker_source
    assert "self._redis.set(busy_key, value, nx=True, ex=ttl)" in redis_source
    assert "self._redis.setnx(busy_key, value)" not in redis_source


def test_order_success_uses_atomic_redis_locks():
    source = ORDER_CALLBACK.read_text()

    assert "await self.redis.set(lock_key, '1', nx=True, ex=60)" in source
    assert "await self.redis.set(utr_lock_key, 1, nx=True, ex=UTR_LOCK_EXPIRY_SECONDS)" in source
    assert "await self.redis.setnx(lock_key, '1')" not in source
    assert "got_utr_lock = await self.redis.setnx(utr_lock_key, 1)" not in source


def test_pakistan_success_ds_is_status2_row_locked_and_single_transition():
    source = WEBSOCKET_CALLBACK.read_text()
    success_ds_source = source.split("async def success_ds", 1)[1].split("\n\n# 代付确认", 1)[0]

    assert "AND status = 2" in success_ds_source
    assert "FOR UPDATE" in success_ds_source
    assert "where code=%s and status=2 limit 1" in success_ds_source
    assert "status in (-1,1,2)" not in success_ds_source.lower()


def test_dispatch_lock_rechecks_full_payment_state_and_limits():
    import sys

    api_root = REPO_ROOT / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    from application.pay.dispatch import _lock_ds_dispatch_candidate, push_order

    lock_source = inspect.getsource(_lock_ds_dispatch_candidate)
    push_source = inspect.getsource(push_order)

    for field in [
        "wallet_status",
        "status",
        "certified",
        "bank_type",
        "bank_type_id",
        "account_iban",
        "account_accno",
        "account_type",
        "phone",
    ]:
        assert field in lock_source

    assert "_locked_payment_can_collect" in push_source
    assert "_locked_payment_has_required_account" in push_source
    assert "orders_ds_count[0]['count'] >= int(maximum_simultaneous_orders_count)" in push_source
    assert "if not locked_partner['type'] == 0:" in push_source
    assert "send_orders_interval_global and not partner['type'] == 0" not in push_source


def test_orders_ds_merchant_code_unique_index_is_declared():
    for path in [INITIAL_SCHEMA, UNIQUE_MIGRATION]:
        source = path.read_text()
        assert "uk_orders_ds_merchant_code" in source
        assert "merchant_id" in source
        assert "merchant_code" in source
