# JazzCashBusiness Collection Runtime SOT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the JazzCashBusiness collection worker obey `jazzcash_runtime` as the source of truth.

**Architecture:** Add one sync runtime method that owns collection job projection, then route `Jazzcashpay_v2.py` worker updates and `pre_login` promotion through it. Keep the JCB invariant that payout dispatch requires collection ability because statements are needed for reconciliation.

**Tech Stack:** Python 3.12, unittest, Redis runtime snapshot/index model.

---

### Task 1: Runtime Projection Tests

**Files:**
- Create: `api/tests/jazzcash_runtime/test_sync_collection_worker.py`

- [x] Add a sync fake Redis with hash, zset, set, list, key, ttl methods.
- [x] Test `sync_collection_job_state()` writes:
  - `jazzcash_runtime:snapshot:{payment_id}`
  - `jazzcash_runtime:index:collect_enabled`
  - `jazzcash_runtime:schedule:collection`
  - `hash_jazzcash`
  - `set_jazzcash`
- [x] Test `collect_enabled=false` forces DS/DF false and removes `hash_jazzcash` / `set_jazzcash`.

Run:

```bash
PYTHONPATH=api python3.12 -m unittest api.tests.jazzcash_runtime.test_sync_collection_worker -v
```

Expected before implementation: failures for missing `sync_collection_job_state()`.

### Task 2: Worker Runtime Gate Tests

**Files:**
- Modify: `api/tests/jazzcash_runtime/test_sync_collection_worker.py`

- [x] Test `process_single_member_async()` skips a stale job when runtime snapshot is offline or `collect_enabled=false`.
- [x] Test `main()` promotes `pre_login_jazzcash_*` `activeSuccessful` through runtime and preserves collection while disabling DS/DF when policy is not dispatchable.

Run:

```bash
PYTHONPATH=api python3.12 -m unittest api.tests.jazzcash_runtime.test_sync_collection_worker -v
```

Expected before implementation: worker still trusts stale legacy job queue.

### Task 3: Sync Runtime Implementation

**Files:**
- Modify: `api/application/jazzcash_runtime/sync_runtime_service.py`

- [x] Add `is_collection_online(payment_id)`.
- [x] Add `sync_collection_job_state(login_data, source, schedule_score, collect_enabled, ds_order_enabled, df_order_enabled)`.
- [x] Keep the JCB invariant: when collection is disabled, DS/DF are disabled too.
- [x] Write or remove `hash_jazzcash` / `set_jazzcash` only from this method.

### Task 4: Collection Worker Implementation

**Files:**
- Modify: `api/jobs/Jazzcashpay_v2.py`

- [x] Add `_read_payment_runtime_flags()` and `payment_runtime_policy()`.
- [x] Make `on_off(1)` write runtime using policy instead of always opening DS/DF.
- [x] Make `update_key()` call `sync_collection_job_state()`.
- [x] Make `process_single_member_async()` check runtime collection state before calling upstream bills.
- [x] Make `main()` promote `pre_login` through runtime instead of direct queue writes.
- [x] Make old `login_off_jazzcash_*` a cleanup marker rather than the source of truth.

### Task 5: Documentation And Verification

**Files:**
- Create: `docs/superpowers/specs/2026-04-26-jazzcash-collection-runtime-sot-design.md`
- Create: `docs/superpowers/plans/2026-04-26-jazzcash-collection-runtime-sot.md`
- Modify: `api/build.md`
- Modify: `api/err.md`

- [x] Document the business rule: JCB payout requires collection for reconciliation.
- [x] Document local verification commands.
- [x] Document the stale legacy queue troubleshooting path.

Run:

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.jazzcash_runtime.test_sync_collection_worker \
  api.tests.test_jazzcash_business_flow_v2 -v

python3.12 -m py_compile \
  api/application/jazzcash_runtime/sync_runtime_service.py \
  api/jobs/Jazzcashpay_v2.py

git diff --check
```

Expected after implementation: all commands exit 0.
