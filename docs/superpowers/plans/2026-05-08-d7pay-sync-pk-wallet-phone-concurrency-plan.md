# D7pay Sync pk_project Wallet Phone and Payout Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同步 pk_project 最新 EasyPaisa 钱包手机号、通道拆分和代付并发加固业务到 D7pay。

**Architecture:** 只同步 API 业务层和 worker 代码；D7pay 租户配置、部署脚本、前端和 APK 不参与本次同步。测试先覆盖 pk_project 新语义，再复制实现并执行 D7pay 边界验收。

**Tech Stack:** Python 3、Tornado handlers、PyMySQL、Redis lock、pytest、GitNexus。

---

### Task 1: 同步测试并确认红灯

**Files:**
- Modify: `api/tests/test_ds_dispatch_candidate_sql.py`
- Modify: `api/tests/test_easypaisa_qr_payload.py`
- Modify: `api/tests/test_order_10100_template.py`
- Modify: `api/tests/test_easypaisa_mysql_eligibility.py`
- Modify: `api/tests/test_jazzcash_mysql_statement_scheduler.py`
- Modify: `api/jobs/easypaisa/tests/test_account_selector.py`
- Modify: `api/jobs/easypaisa/tests/test_order_lifecycle.py`
- Modify: `api/jobs/easypaisa/tests/test_transfer_executor.py`
- Modify: `api/tests/test_easypaisa_redis_compat_retirement.py`

- [x] **Step 1: 从 pk_project 同步测试文件**

Run:

```bash
cp /Users/tear/pk_project/api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_ds_dispatch_candidate_sql.py
cp /Users/tear/pk_project/api/tests/test_easypaisa_qr_payload.py api/tests/test_easypaisa_qr_payload.py
cp /Users/tear/pk_project/api/tests/test_order_10100_template.py api/tests/test_order_10100_template.py
cp /Users/tear/pk_project/api/tests/test_easypaisa_mysql_eligibility.py api/tests/test_easypaisa_mysql_eligibility.py
cp /Users/tear/pk_project/api/tests/test_jazzcash_mysql_statement_scheduler.py api/tests/test_jazzcash_mysql_statement_scheduler.py
cp /Users/tear/pk_project/api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_account_selector.py
cp /Users/tear/pk_project/api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_order_lifecycle.py
cp /Users/tear/pk_project/api/jobs/easypaisa/tests/test_transfer_executor.py api/jobs/easypaisa/tests/test_transfer_executor.py
cp /Users/tear/pk_project/api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_easypaisa_redis_compat_retirement.py
```

- [x] **Step 2: 跑红灯**

Run:

```bash
python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py api/tests/test_order_10100_template.py api/tests/test_easypaisa_mysql_eligibility.py api/tests/test_jazzcash_mysql_statement_scheduler.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

Expected: 旧实现失败，暴露 `1001/1010` 展示、payer phone、Redis 原子锁、并发和代付成功判定缺口。

### Task 2: 同步实现

**Files:**
- Modify: `api/application/pay/dispatch.py`
- Modify: `api/application/pay/order.py`
- Modify: `api/application/pay/pay.py`
- Modify: `api/jobs/Jazzcashpay_v2.py`
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: `api/jobs/easypaisa/auto_payout.py`
- Modify: `api/jobs/easypaisa/payout/account_selector.py`
- Modify: `api/jobs/easypaisa/payout/order_lifecycle.py`
- Modify: `api/jobs/easypaisa/payout/transfer_executor.py`

- [x] **Step 1: GitNexus 影响分析**

Run impact for:

```text
build_ds_candidate_sql
card_num
BankLogin
EasyPaisaAutoPayout
AccountSelector
OrderLifecycle
TransferExecutor
```

Expected: 风险 LOW 或已记录说明。

- [x] **Step 2: 从 pk_project 同步实现文件**

Run:

```bash
cp /Users/tear/pk_project/api/application/pay/dispatch.py api/application/pay/dispatch.py
cp /Users/tear/pk_project/api/application/pay/order.py api/application/pay/order.py
cp /Users/tear/pk_project/api/application/pay/pay.py api/application/pay/pay.py
cp /Users/tear/pk_project/api/jobs/Jazzcashpay_v2.py api/jobs/Jazzcashpay_v2.py
cp /Users/tear/pk_project/api/jobs/pakistanpay_v2.py api/jobs/pakistanpay_v2.py
cp /Users/tear/pk_project/api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/auto_payout.py
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/account_selector.py api/jobs/easypaisa/payout/account_selector.py
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/order_lifecycle.py api/jobs/easypaisa/payout/order_lifecycle.py
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/transfer_executor.py api/jobs/easypaisa/payout/transfer_executor.py
```

### Task 3: 验收与提交

- [x] **Step 1: 目标测试转绿**

Run target tests from Task 1. Expected: PASS.

- [x] **Step 2: 跑业务回归和 D7pay 边界**

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
git commit -m "fix: sync pk wallet phone and payout concurrency"
git push origin d7pay
```
