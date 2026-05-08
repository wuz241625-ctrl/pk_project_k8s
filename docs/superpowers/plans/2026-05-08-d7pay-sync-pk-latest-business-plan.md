# D7pay Sync pk_project Latest Business Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同步 pk_project 最新 Pakistan 钱包业务改动到 D7pay，同时保留 D7pay 租户边界。

**Architecture:** 以 pk_project 业务文件为源，按文件同步 API/job/admin 后端业务代码；对 D7pay 特有 IP/时区/env/K8s/Jenkins 相关文件不做覆盖。用 pk_project 新测试加 D7pay 边界测试作为验收。

**Tech Stack:** Python、Tornado、pytest、GitNexus。

---

### Task 1: 同步测试并确认红灯

**Files:**
- Modify/Create: pk_project 最近提交涉及的 `api/tests/**`、`api/jobs/easypaisa/tests/**`

- [ ] **Step 1: 同步 pk_project 新测试**

从 `/Users/tear/pk_project` 同步以下测试：

```text
api/tests/test_statement_callback_mysql_idempotency.py
api/tests/easypaisa_runtime/test_statement_order_scheduler.py
api/tests/easypaisa_runtime/test_worker_wallet_status_integration.py
api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py
api/tests/easypaisa/test_common_db.py
api/jobs/easypaisa/tests/test_account_selector.py
api/jobs/easypaisa/tests/test_order_lifecycle.py
api/jobs/easypaisa/tests/test_transfer_executor.py
api/tests/test_jazzcash_auto_payout_v16.py
```

- [ ] **Step 2: 保留 D7pay Redis 业务态边界测试**

确保 `api/tests/test_easypaisa_redis_compat_retirement.py` 仍覆盖：

```python
self.assertNotIn("payment_" + "online_df", source)
self.assertNotIn("payment_" + "active_channel_", source)
```

- [x] **Step 3: 运行同步前红灯**

Run:

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa/test_common_db.py api/jobs/easypaisa/tests/test_account_selector.py api/tests/test_jazzcash_auto_payout_v16.py -q
```

Expected: 当前旧实现至少在 UTR 语义、DBConnection、MySQL 余额源或 Redis 业务态退役断言上失败。

### Task 2: 同步业务代码

**Files:**
- Modify/Create: `api/jobs/common/db.py`
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: `api/application/websocket/callback.py`
- Modify: `api/application/pay/order.py`
- Modify: `api/jobs/easypaisa/**`
- Modify: `api/jobs/jazzcash/**`
- Modify: `admin/application/order/auto_payout.py`
- Modify: `admin/application/merchant/merchant.py`
- Modify: `admin/application/partner/partner.py`

- [x] **Step 1: 同步 API/job 文件**

按 pk_project 对应文件同步，保留 D7pay 不相关配置文件不动。

- [x] **Step 2: 合并 D7pay 边界**

确认以下内容仍成立：

```text
api/application/client_ip.py 保留
api/application/timezone.py 保留
api/tests/test_client_ip.py 保留
api/tests/test_timezone_policy.py 保留
```

- [x] **Step 3: 静态检查旧业务态 key**

Run:

```bash
rg -n "payment_online_df|payment_active_df|payment_active_channel_|easypaisa_emergency_stop|target_payment_key" api/application api/jobs admin/application -g '*.py'
```

Expected: 不应出现在业务资格判断路径；允许测试名或非业务锁/cache 场景另行说明。

### Task 3: 验收与推送

- [x] **Step 1: 运行业务测试**

Run:

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa_runtime/test_worker_wallet_status_integration.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa/test_common_db.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

- [x] **Step 2: 运行 D7pay 边界测试**

Run:

```bash
python3 -m pytest api/tests/test_client_ip.py api/tests/test_timezone_policy.py admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
python3 ops/tenants/d7pay/verify_release_contract.py
```

- [x] **Step 3: GitNexus 与 Git**

Run:

```bash
npx gitnexus analyze
gitnexus detect_changes(scope="all")
git add <本次同步文件>
git commit -m "fix: sync latest pk business changes"
git push origin d7pay
```
