# Sync pk_project admin/api into pk_project_k8s Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the latest backend business logic and matching tests from `/home/ubuntu/pk_project` into `/home/ubuntu/pk_project_k8s` for `admin` and `api`, without overwriting k8s-specific deployment shape or environment-specific runtime artifacts.

**Architecture:** Treat `pk_project` as the backend business-logic source of truth and `pk_project_k8s` as the migrated deployment-shaped repo. Copy only differing business/test files under `admin` and `api`, explicitly excluding env configs, logs, caches, and runtime artifacts. Validate with targeted pytest runs covering the migrated Easypaisa/runtime and affected admin/api flows.

**Tech Stack:** Python, pytest, git, diff/cp/rsync shell tooling

---

### Task 1: Lock the sync file manifest

**Files:**
- Create: `docs/superpowers/plans/2026-04-25-sync-pk-project-admin-api.md`
- Verify: `/home/ubuntu/pk_project/admin/**`
- Verify: `/home/ubuntu/pk_project/api/**`
- Verify: `/home/ubuntu/pk_project_k8s/admin/**`
- Verify: `/home/ubuntu/pk_project_k8s/api/**`

- [ ] **Step 1: Enumerate differing business/test files only**

Run: `diff -qr /home/ubuntu/pk_project/admin /home/ubuntu/pk_project_k8s/admin && diff -qr /home/ubuntu/pk_project/api /home/ubuntu/pk_project_k8s/api`
Expected: diff list showing code, tests, config, and runtime artifacts.

- [ ] **Step 2: Reduce manifest to allowed sync targets**

Allowed:
- `admin/application/**`
- `admin/tests/**`
- `api/application/**`
- `api/jobs/**`
- `api/tests/**`

Excluded:
- `**/config.py`
- `**/logs/**`
- `**/__pycache__/**`
- `**/.pytest_cache/**`
- `**/*.log*`
- `**/nohup.out`
- non-backend repo-root deployment files

- [ ] **Step 3: Save the final manifest in the execution notes**

List exact files before copying so the sync is auditable.

### Task 2: Copy tests first

**Files:**
- Modify: `admin/tests/test_easypaisa_runtime_reader.py`
- Create: `admin/tests/test_admin_collection_control.py`
- Modify/Create: `api/tests/easypaisa_runtime/test_reader.py`
- Modify/Create: `api/tests/easypaisa_runtime/test_runtime_service.py`
- Modify/Create: `api/tests/easypaisa_runtime/test_sync_runtime_service.py`
- Modify/Create: `api/tests/test_app_my_easypaisa_runtime.py`
- Modify/Create: `api/tests/test_easypaisa_account_retention.py`
- Modify/Create: `api/tests/test_easypaisa_business_flow_v2.py`
- Modify/Create: `api/tests/test_easypaisa_collection_runtime_toggle.py`
- Modify/Create: `api/tests/test_easypaisa_runtime_rollout_cleanup.py`
- Create: `api/tests/test_easypaisa_timeout_guard.py`
- Create: `api/tests/test_order_push_easypaisa_runtime_guard.py`
- Create: `api/tests/test_time_out_guard.py`
- Create: `api/tests/test_websocket_monitor_ep_dispatch.py`

- [ ] **Step 1: Copy the selected test files from source repo**

Run exact copy commands for each file or an allowlisted rsync invocation.

- [ ] **Step 2: Run the migrated tests before copying production code**

Run: `cd /home/ubuntu/pk_project_k8s/admin && pytest tests/test_easypaisa_runtime_reader.py tests/test_admin_collection_control.py -q`
Run: `cd /home/ubuntu/pk_project_k8s/api && pytest tests/easypaisa_runtime/test_reader.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/test_easypaisa_timeout_guard.py tests/test_order_push_easypaisa_runtime_guard.py tests/test_time_out_guard.py tests/test_websocket_monitor_ep_dispatch.py -q`
Expected: failures or import/behavior mismatches demonstrating missing synced logic.

### Task 3: Sync admin business logic

**Files:**
- Modify: `admin/application/easypaisa_runtime/keyspace.py`
- Modify: `admin/application/easypaisa_runtime/reader.py`
- Modify: `admin/application/easypaisa_runtime/service.py`
- Modify: `admin/application/order/auto_payout.py`
- Modify: `admin/application/order/order.py`
- Modify: `admin/application/partner/partner.py`

- [ ] **Step 1: Copy admin business files from source repo**

Use exact copy commands.

- [ ] **Step 2: Run admin targeted tests**

Run: `cd /home/ubuntu/pk_project_k8s/admin && pytest tests/test_easypaisa_runtime_reader.py tests/test_admin_collection_control.py -q`
Expected: pass.

### Task 4: Sync api business logic

**Files:**
- Modify: `api/application/app/issue/issue.py`
- Modify: `api/application/app/login/banks/easypaisa.py`
- Modify: `api/application/app/my/my.py`
- Modify: `api/application/easypaisa_runtime/account_retention.py`
- Modify: `api/application/easypaisa_runtime/keyspace.py`
- Modify: `api/application/easypaisa_runtime/reader.py`
- Modify: `api/application/easypaisa_runtime/rollout_cleanup.py`
- Modify: `api/application/easypaisa_runtime/runtime_service.py`
- Modify: `api/application/easypaisa_runtime/sync_runtime_service.py`
- Modify: `api/application/lakshmi_api/controllers/upi_controller.py`
- Modify: `api/application/lakshmi_api/services/payments/e_wallet_handler.py`
- Modify: `api/application/pay/pay.py`
- Modify: `api/application/websocket/callback.py`
- Modify: `api/application/websocket/monitor.py`
- Modify: `api/jobs/easypaisa/auto_payout.py`
- Modify: `api/jobs/easypaisa/easypaisa_monitor.py`
- Modify: `api/jobs/order_push.py`
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: `api/jobs/time_out.py`
- Modify: `api/jobs/update_payment_balance.py`

- [ ] **Step 1: Copy api business files from source repo**

Use exact copy commands.

- [ ] **Step 2: Run api targeted tests**

Run: `cd /home/ubuntu/pk_project_k8s/api && pytest tests/easypaisa_runtime/test_reader.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/test_app_my_easypaisa_runtime.py tests/test_easypaisa_account_retention.py tests/test_easypaisa_business_flow_v2.py tests/test_easypaisa_collection_runtime_toggle.py tests/test_easypaisa_runtime_rollout_cleanup.py tests/test_easypaisa_timeout_guard.py tests/test_order_push_easypaisa_runtime_guard.py tests/test_time_out_guard.py tests/test_websocket_monitor_ep_dispatch.py -q`
Expected: pass.

### Task 5: Final verification and report

**Files:**
- Verify: `admin/**`
- Verify: `api/**`

- [ ] **Step 1: Show git diff summary**

Run: `git -C /home/ubuntu/pk_project_k8s status --short && git -C /home/ubuntu/pk_project_k8s diff --stat -- admin api`
Expected: only intended admin/api code and test files changed.

- [ ] **Step 2: Re-run final targeted verification suite**

Run the same admin/api pytest commands again and record pass/fail counts.

- [ ] **Step 3: Report exclusions explicitly**

State that `config.py`, logs, caches, and runtime artifacts were not synced.
