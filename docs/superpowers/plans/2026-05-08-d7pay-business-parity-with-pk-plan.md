# D7pay Business Parity With Pk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D7pay 后端的钱包状态、代收下单、派单、采集、代付业务逻辑同步到 pk_project，同时保留 D7pay 的 IP、时区、env 和 K8s 发布边界。

**Architecture:** 以 `/Users/tear/pk_project` 作为业务真相源复制指定业务文件；不复制 D7pay 保护边界文件。同步后用文件一致性、关键词保护、单测和 GitNexus 检测确认范围。

**Tech Stack:** Python Tornado 后端、Redis、MySQL、pytest/unittest、GitNexus、D7pay K8s release contract。

---

### Task 1: 复制业务文件

**Files:**
- Modify: `api/application/pay/pay.py`
- Modify: `api/application/pay/dispatch.py`
- Modify: `api/application/pay/order.py`
- Modify: `api/application/websocket/callback.py`
- Modify: `api/application/websocket/monitor.py`
- Modify: `api/application/app/login/banks/easypaisa.py`
- Modify: `api/application/app/login/banks/jazzcash.py`
- Modify: `api/application/lakshmi_api/controllers/deposit_orders_controller.py`
- Modify: `api/jobs/easypaisa/auto_payout.py`
- Modify: `api/jobs/Jazzcashpay_v2.py`
- Modify: `api/jobs/update_payment_balance.py`
- Modify: `api/router.py`

- [ ] **Step 1: 复制 pk_project 业务文件**

```bash
cp /Users/tear/pk_project/api/application/pay/pay.py api/application/pay/pay.py
cp /Users/tear/pk_project/api/application/pay/dispatch.py api/application/pay/dispatch.py
cp /Users/tear/pk_project/api/application/pay/order.py api/application/pay/order.py
cp /Users/tear/pk_project/api/application/websocket/callback.py api/application/websocket/callback.py
cp /Users/tear/pk_project/api/application/websocket/monitor.py api/application/websocket/monitor.py
cp /Users/tear/pk_project/api/application/app/login/banks/easypaisa.py api/application/app/login/banks/easypaisa.py
cp /Users/tear/pk_project/api/application/app/login/banks/jazzcash.py api/application/app/login/banks/jazzcash.py
cp /Users/tear/pk_project/api/application/lakshmi_api/controllers/deposit_orders_controller.py api/application/lakshmi_api/controllers/deposit_orders_controller.py
cp /Users/tear/pk_project/api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/auto_payout.py
cp /Users/tear/pk_project/api/jobs/Jazzcashpay_v2.py api/jobs/Jazzcashpay_v2.py
cp /Users/tear/pk_project/api/jobs/update_payment_balance.py api/jobs/update_payment_balance.py
cp /Users/tear/pk_project/api/router.py api/router.py
```

- [ ] **Step 2: 确认复制文件一致**

```bash
for f in api/application/pay/pay.py api/application/pay/dispatch.py api/application/pay/order.py api/application/websocket/callback.py api/application/websocket/monitor.py api/application/app/login/banks/easypaisa.py api/application/app/login/banks/jazzcash.py api/application/lakshmi_api/controllers/deposit_orders_controller.py api/jobs/easypaisa/auto_payout.py api/jobs/Jazzcashpay_v2.py api/jobs/update_payment_balance.py api/router.py; do cmp -s "/Users/tear/pk_project/$f" "$f" || exit 1; done
```

Expected: exit code `0`.

### Task 2: 同步测试和文档

**Files:**
- Create: `api/tests/test_crawl_frequently_retirement.py`
- Create: `api/tests/test_update_payment_balance_retirement.py`
- Create: `api/tests/test_jazzcash_mysql_statement_scheduler.py`
- Create/Modify: related docs under `docs/superpowers/`

- [ ] **Step 1: 复制测试**

```bash
cp /Users/tear/pk_project/api/tests/test_crawl_frequently_retirement.py api/tests/test_crawl_frequently_retirement.py
cp /Users/tear/pk_project/api/tests/test_update_payment_balance_retirement.py api/tests/test_update_payment_balance_retirement.py
cp /Users/tear/pk_project/api/tests/test_jazzcash_mysql_statement_scheduler.py api/tests/test_jazzcash_mysql_statement_scheduler.py
```

- [ ] **Step 2: 复制本次相关文档**

```bash
cp /Users/tear/pk_project/docs/superpowers/plans/2026-05-08-crawl-frequently-retirement-plan.md docs/superpowers/plans/2026-05-08-crawl-frequently-retirement-plan.md
cp /Users/tear/pk_project/docs/superpowers/reports/2026-05-08-crawl-frequently-retirement-report.md docs/superpowers/reports/2026-05-08-crawl-frequently-retirement-report.md
cp /Users/tear/pk_project/docs/superpowers/plans/2026-05-08-successbot-restore-plan.md docs/superpowers/plans/2026-05-08-successbot-restore-plan.md
cp /Users/tear/pk_project/docs/superpowers/reports/2026-05-08-successbot-restore-report.md docs/superpowers/reports/2026-05-08-successbot-restore-report.md
cp /Users/tear/pk_project/docs/superpowers/plans/2026-05-08-wallet-dead-code-cleanup-plan.md docs/superpowers/plans/2026-05-08-wallet-dead-code-cleanup-plan.md
cp /Users/tear/pk_project/docs/superpowers/reports/2026-05-08-wallet-dead-code-cleanup-report.md docs/superpowers/reports/2026-05-08-wallet-dead-code-cleanup-report.md
cp /Users/tear/pk_project/docs/superpowers/plans/2026-05-08-ds-dispatch-nowait-transaction-plan.md docs/superpowers/plans/2026-05-08-ds-dispatch-nowait-transaction-plan.md
cp /Users/tear/pk_project/docs/superpowers/reports/2026-05-08-ds-dispatch-nowait-transaction-report.md docs/superpowers/reports/2026-05-08-ds-dispatch-nowait-transaction-report.md
cp /Users/tear/pk_project/docs/superpowers/specs/2026-05-08-ds-dispatch-nowait-transaction-design.md docs/superpowers/specs/2026-05-08-ds-dispatch-nowait-transaction-design.md
cp /Users/tear/pk_project/docs/superpowers/plans/2026-05-08-ds-sync-dispatch-and-jazzcash-no-qrcode-plan.md docs/superpowers/plans/2026-05-08-ds-sync-dispatch-and-jazzcash-no-qrcode-plan.md
cp /Users/tear/pk_project/docs/superpowers/reports/2026-05-08-ds-sync-dispatch-and-jazzcash-no-qrcode-report.md docs/superpowers/reports/2026-05-08-ds-sync-dispatch-and-jazzcash-no-qrcode-report.md
cp /Users/tear/pk_project/docs/superpowers/specs/2026-05-08-ds-sync-dispatch-and-jazzcash-no-qrcode-design.md docs/superpowers/specs/2026-05-08-ds-sync-dispatch-and-jazzcash-no-qrcode-design.md
```

### Task 3: 验证 D7pay 保护边界

**Files:**
- Verify: `api/application/base.py`
- Verify: `admin/application/base.py`
- Verify: `merchant/application/base.py`
- Verify: `admin/application/order/order.py`
- Verify: `merchant/application/order/order.py`

- [ ] **Step 1: 验证 IP 和时区关键字仍存在**

```bash
rg -n "resolve_client_ip" api/application/base.py admin/application/base.py merchant/application/base.py
rg -n "display_today_between" admin merchant api -g '*.py'
```

Expected: 两条命令都有匹配。

- [ ] **Step 2: 验证不出现已退役采集加速 key**

```bash
rg -n "crawl_frequently_" api -g '*.py'
```

Expected: 无匹配。

### Task 4: 验收测试

**Files:**
- Test: `api/tests/test_crawl_frequently_retirement.py`
- Test: `api/tests/test_update_payment_balance_retirement.py`
- Test: `api/tests/test_jazzcash_mysql_statement_scheduler.py`
- Test: existing payout/dispatch/timezone/client-ip tests

- [ ] **Step 1: 编译业务文件**

```bash
python3 -m py_compile api/application/pay/pay.py api/application/pay/dispatch.py api/application/pay/order.py api/application/websocket/callback.py api/application/websocket/monitor.py api/application/app/login/banks/easypaisa.py api/application/app/login/banks/jazzcash.py api/application/lakshmi_api/controllers/deposit_orders_controller.py api/jobs/easypaisa/auto_payout.py api/jobs/Jazzcashpay_v2.py api/jobs/update_payment_balance.py api/router.py
```

Expected: exit code `0`。

- [ ] **Step 2: 跑业务回归**

```bash
python3 -m pytest api/tests/test_crawl_frequently_retirement.py api/tests/test_update_payment_balance_retirement.py api/tests/test_jazzcash_mysql_statement_scheduler.py api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_jazzcash_bill_worker_final_state.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_client_ip.py api/tests/test_timezone_policy.py admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
```

Expected: 全部通过。

- [ ] **Step 3: 跑 D7pay 发布契约**

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

Expected: `D7pay release contract OK`。

### Task 5: GitNexus、提交和推送

- [ ] **Step 1: 更新 GitNexus 索引并检测变更**

```bash
npx gitnexus analyze
```

Then run GitNexus detect changes on staged changes.

- [ ] **Step 2: 提交并推送**

```bash
git add <同步文件和文档>
git commit -m "fix: sync d7pay business flow with pk project"
git push origin d7pay
```

Expected: 推送成功到 `origin/d7pay`。
