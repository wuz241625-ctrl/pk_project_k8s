# D7pay Sync pk_project EasyPaisa Worker Scale Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同步 pk_project 最新 EasyPaisa 代付 worker 扩容加固到 D7pay。

**Architecture:** 只同步 EasyPaisa 代付 worker 的 selector/lifecycle/executor 及其测试。D7pay 租户配置、部署脚本、前端和 APK 不参与本次同步。

**Tech Stack:** Python 3、PyMySQL、Redis lock、pytest、GitNexus。

---

### Task 1: 同步测试并确认红灯

**Files:**
- Modify: `api/jobs/easypaisa/tests/test_account_selector.py`
- Modify: `api/jobs/easypaisa/tests/test_order_lifecycle.py`
- Modify: `api/jobs/easypaisa/tests/test_transfer_executor.py`

- [x] **Step 1: 从 pk_project 同步测试**

Run:

```bash
cp /Users/tear/pk_project/api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_account_selector.py
cp /Users/tear/pk_project/api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_order_lifecycle.py
cp /Users/tear/pk_project/api/jobs/easypaisa/tests/test_transfer_executor.py api/jobs/easypaisa/tests/test_transfer_executor.py
```

- [x] **Step 2: 跑红灯**

Run:

```bash
python3 -m pytest api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py -q
```

Expected: 旧实现失败，暴露日限额剩余额度、锁内余额复查、事务扣余额、缺官方交易号不成功等缺口。

### Task 2: 同步实现

**Files:**
- Modify: `api/jobs/easypaisa/payout/account_selector.py`
- Modify: `api/jobs/easypaisa/payout/order_lifecycle.py`
- Modify: `api/jobs/easypaisa/payout/transfer_executor.py`

- [x] **Step 1: GitNexus 影响分析**

Run impact for:

```text
AccountSelector
OrderLifecycle
TransferExecutor
```

Expected: 风险 LOW，直接入口为 EasyPaisa 自动代付 worker。

- [x] **Step 2: 从 pk_project 同步实现**

Run:

```bash
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/account_selector.py api/jobs/easypaisa/payout/account_selector.py
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/order_lifecycle.py api/jobs/easypaisa/payout/order_lifecycle.py
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/transfer_executor.py api/jobs/easypaisa/payout/transfer_executor.py
```

### Task 3: 验收与提交

- [x] **Step 1: 目标测试转绿**

Run:

```bash
python3 -m pytest api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py -q
```

Expected: PASS.

- [x] **Step 2: 业务回归和 D7pay 边界**

Run:

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa_runtime/test_worker_wallet_status_integration.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa/test_common_db.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/jobs/easypaisa/tests/test_settlement.py api/jobs/easypaisa/tests/test_transaction_log.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_websocket_monitor_ep_dispatch.py api/tests/test_easypaisa_redis_compat_retirement.py -q
python3 -m pytest api/tests/test_client_ip.py api/tests/test_timezone_policy.py -q
python3 -m pytest admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py admin/tests/test_redis_business_state_retirement.py -q
python3 -m pytest merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
python3 ops/tenants/d7pay/verify_release_contract.py
```

- [x] **Step 3: GitNexus、提交、推送**

Run:

```bash
npx gitnexus analyze
gitnexus detect_changes(scope="staged")
git add <本次文件>
git commit -m "fix: sync pk easypaisa worker scale hardening"
git push origin d7pay
```
