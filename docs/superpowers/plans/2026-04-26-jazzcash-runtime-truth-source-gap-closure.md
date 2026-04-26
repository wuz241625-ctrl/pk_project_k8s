# JazzCashBusiness Runtime Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining JazzCashBusiness paths that still treat legacy Redis keys as the source of truth.

**Architecture:** Keep the existing per-bank branching pattern. EasyPaisa keeps using `easypaisa_runtime`, JazzCashBusiness uses `jazzcash_runtime`, and non-runtime banks keep legacy Redis behavior.

**Tech Stack:** Python 3.12, Tornado handlers, Redis runtime snapshots/indexes, unittest/fakeredis.

---

### Task 1: Failing Tests For Remaining Gaps

**Files:**
- Modify: `api/tests/test_websocket_monitor_ep_dispatch.py`
- Modify: `api/tests/test_time_out_guard.py`
- Modify: `admin/tests/test_jazzcash_runtime_reader.py`
- Modify: `api/tests/jazzcash_runtime/test_reader.py`
- Modify: `api/tests/test_jazzcash_business_flow_v2.py`

- [x] Add tests proving JazzCash websocket ds/df uses `JazzCashRuntimeService`.
- [x] Add tests proving `TimeOutGuard` checks `jazzcash_runtime:index:dispatch_ds` for `bank_type=98`.
- [x] Add tests proving admin order requeue ignores JazzCash legacy `payment_online_df` without snapshot.
- [x] Add tests proving `pay.py` ignores legacy `kick_off_*` for JazzCash unless runtime kickoff exists.
- [x] Add FakeRedis sorted-set methods needed by JazzCash runtime activation tests.

Run:

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_jazzcash_business_flow_v2 \
  api.tests.test_websocket_monitor_ep_dispatch \
  api.tests.test_time_out_guard \
  api.tests.jazzcash_runtime.test_reader -v

PYTHONPATH=admin python3.12 -m unittest admin.tests.test_jazzcash_runtime_reader -v
```

Expected before implementation: new behavior tests fail against current code.

### Task 2: Runtime Implementations

**Files:**
- Modify: `api/application/websocket/monitor.py`
- Modify: `api/application/jazzcash_runtime/runtime_service.py`
- Modify: `api/jobs/time_out.py`
- Modify: `admin/application/order/order.py`
- Modify: `api/application/pay/pay.py`

- [x] Add JazzCash helpers/imports to websocket monitor and route ds/df online/offline through `JazzCashRuntimeService`.
- [x] Add `JazzCashRuntimeService.set_df_order_dispatch()` mirroring EasyPaisa behavior at the small surface websocket needs.
- [x] Extend `TimeOutGuard` with JazzCash runtime dispatch index.
- [x] Extend admin order `requeue_df_if_online()` with `JazzCashAdminRuntimeReader`.
- [x] Add `pay._has_collection_kickoff()` and use it in both collection requeue loops.
- [x] Remove tracked stale JazzCash `.bak` auto-payout code that still read legacy Redis as a source.

### Task 3: Documentation And Verification

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `admin/build.md`
- Modify: `admin/err.md`
- Modify: this plan document checkbox status

- [x] Update `api/build.md` and `api/err.md` with JazzCashBusiness websocket/time_out/pay runtime验收与排错口径。
- [x] Update `admin/build.md` and `admin/err.md` with JazzCashBusiness admin 回队验收与排错口径。

Run:

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_jazzcash_business_flow_v2 \
  api.tests.test_websocket_monitor_ep_dispatch \
  api.tests.test_time_out_guard \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.test_order_push_easypaisa_runtime_guard -v

PYTHONPATH=admin python3.12 -m unittest \
  admin.tests.test_jazzcash_runtime_reader \
  admin.tests.test_easypaisa_runtime_reader \
  admin.tests.test_admin_collection_control -v

python3.12 -m py_compile \
  api/application/jazzcash_runtime/*.py \
  api/application/websocket/monitor.py \
  api/application/pay/pay.py \
  api/jobs/time_out.py \
  admin/application/order/order.py

git diff --check
```

Expected after implementation: all commands exit 0.
