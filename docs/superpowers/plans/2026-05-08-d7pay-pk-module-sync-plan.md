# D7pay PK Module Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `pk_project` 最新业务模块化改动同步到 D7pay，同时保留 D7pay 租户配置。

**Architecture:** 采用文件级同步，只复制 API 业务模块、worker 拆分模块和相关测试。配置、部署、前端、APK 下载站仍以 D7pay 当前仓库为准。

**Tech Stack:** Python 3.12、Tornado、aiomysql、aiohttp、pytest、GitNexus。

---

### Task 1: 同步 API pay 模块

**Files:**
- Modify: `api/application/pay/pay.py`
- Create or modify: `api/application/pay/collection.py`
- Create or modify: `api/application/pay/dispatch.py`
- Create or modify: `api/application/pay/payout.py`
- Create or modify: `api/application/pay/utr_callback.py`
- Create or modify: `api/application/pay/decimal_amount.py`
- Create or modify: `api/application/pay/raast_qr.py`

- [ ] **Step 1: 从 pk_project 复制 pay 业务文件**

Run:

```bash
for f in pay.py collection.py dispatch.py payout.py utr_callback.py decimal_amount.py raast_qr.py; do cp "/Users/tear/pk_project/api/application/pay/$f" "api/application/pay/$f"; done
```

- [ ] **Step 2: 编译验证 pay 模块**

Run:

```bash
python3 -m py_compile api/application/pay/pay.py api/application/pay/collection.py api/application/pay/dispatch.py api/application/pay/payout.py api/application/pay/utr_callback.py api/application/pay/decimal_amount.py api/application/pay/raast_qr.py
```

Expected: exit 0.

### Task 2: 同步 worker 模块

**Files:**
- Create or modify: `api/jobs/common/`
- Create or modify: `api/jobs/easypaisa/common/`
- Create or modify: `api/jobs/easypaisa/payout/`
- Modify: `api/jobs/easypaisa/auto_payout.py`
- Modify: `api/jobs/easypaisa/easypaisa_monitor.py`
- Create or modify: `api/jobs/jazzcash/payout/`
- Modify: `api/jobs/jazzcash/jazzcash_auto_payout.py`
- Modify: `api/jobs/jazzcash/jazzcash_monitor.py`
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: `api/jobs/Jazzcashpay_v2.py`
- Modify: `api/jobs/update_payment_balance.py`

- [ ] **Step 1: 复制 worker 文件**

Run:

```bash
mkdir -p api/jobs/common api/jobs/easypaisa/common api/jobs/easypaisa/payout api/jobs/jazzcash/payout
cp /Users/tear/pk_project/api/jobs/common/__init__.py api/jobs/common/__init__.py
cp /Users/tear/pk_project/api/jobs/common/logging_setup.py api/jobs/common/logging_setup.py
cp /Users/tear/pk_project/api/jobs/easypaisa/common/*.py api/jobs/easypaisa/common/
cp /Users/tear/pk_project/api/jobs/easypaisa/payout/*.py api/jobs/easypaisa/payout/
cp /Users/tear/pk_project/api/jobs/jazzcash/payout/*.py api/jobs/jazzcash/payout/
cp /Users/tear/pk_project/api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/auto_payout.py
cp /Users/tear/pk_project/api/jobs/easypaisa/easypaisa_monitor.py api/jobs/easypaisa/easypaisa_monitor.py
cp /Users/tear/pk_project/api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_auto_payout.py
cp /Users/tear/pk_project/api/jobs/jazzcash/jazzcash_monitor.py api/jobs/jazzcash/jazzcash_monitor.py
cp /Users/tear/pk_project/api/jobs/pakistanpay_v2.py api/jobs/pakistanpay_v2.py
cp /Users/tear/pk_project/api/jobs/Jazzcashpay_v2.py api/jobs/Jazzcashpay_v2.py
cp /Users/tear/pk_project/api/jobs/update_payment_balance.py api/jobs/update_payment_balance.py
```

- [ ] **Step 2: 编译验证 worker**

Run:

```bash
python3 -m py_compile api/jobs/common/logging_setup.py api/jobs/easypaisa/common/*.py api/jobs/easypaisa/payout/*.py api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/easypaisa_monitor.py api/jobs/jazzcash/payout/*.py api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_monitor.py api/jobs/pakistanpay_v2.py api/jobs/Jazzcashpay_v2.py api/jobs/update_payment_balance.py
```

Expected: exit 0.

### Task 3: 同步并运行重点测试

**Files:**
- Create or modify: `api/tests/test_decimal_amount.py`
- Create or modify: `api/tests/test_raast_qr.py`
- Create or modify: `api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py`
- Modify: `api/tests/easypaisa_runtime/test_statement_order_scheduler.py`

- [ ] **Step 1: 复制测试文件**

Run:

```bash
mkdir -p api/tests/easypaisa_runtime
cp /Users/tear/pk_project/api/tests/test_decimal_amount.py api/tests/test_decimal_amount.py
cp /Users/tear/pk_project/api/tests/test_raast_qr.py api/tests/test_raast_qr.py
cp /Users/tear/pk_project/api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py
cp /Users/tear/pk_project/api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py
```

- [ ] **Step 2: 运行重点测试**

Run:

```bash
python3 -m pytest api/tests/test_decimal_amount.py api/tests/test_raast_qr.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py -q
```

Expected: all selected tests pass.

### Task 4: 审计、文档和提交

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Create: `docs/superpowers/reports/2026-05-08-d7pay-pk-module-sync-report.md`

- [ ] **Step 1: 审计 D7pay 配置未被覆盖**

Run:

```bash
git diff --name-status | egrep 'ops/tenants/d7pay|config.example.py|apkdownload|admin-h5|merchant-h5|k8s|jenkins' || true
```

Expected: no tenant/deploy config changes from pk_project sync.

- [ ] **Step 2: GitNexus 变更审计**

Run:

```bash
gitnexus detect-changes
```

Expected: changed symbols match API pay and worker modules.

- [ ] **Step 3: 提交并推送**

Run:

```bash
git add api docs build.md err.md
git commit -m "refactor: sync d7pay api modules from pk project"
git push origin d7pay
```
