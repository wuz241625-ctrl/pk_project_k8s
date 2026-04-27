# EasyPaisa Active Success Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** EasyPaisa 账户选择进入 `activeSuccessful` 后，DB `payment.status` 与 runtime 采集/派单状态同步恢复为业务可用态。

**Architecture:** 保持现有 `EasyPaisa.select_accts_http()`、`_update_payment()`、`_sync_runtime_state()` 分层，不新增接口。用测试覆盖当前顺序 bug，再最小修改状态推进顺序和 runtime active 写入参数。

**Tech Stack:** Python 3.12, Tornado async handlers, SQLAlchemy update, Redis runtime snapshot, unittest。

---

### Task 1: 复现账户选择状态同步缺口

**Files:**
- Modify: `api/tests/test_easypaisa_business_flow_v2.py`

- [ ] **Step 1: 写失败测试**

在 `EasyPaisaBusinessFlowV2Tests` 增加用例：预先写入 `accountSelectionRequired` session 和同阶段 runtime snapshot，然后调用 `select_accts_http()`。测试捕获 `_update_payment()` 调用时的 session 状态，并断言 runtime active 后采集/派单开关全开。

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=api python3.12 -m unittest api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_select_accts_http_activates_payment_and_runtime_dispatch -v
```

Expected: 失败，原因是 `_update_payment()` 捕获到 `accountSelectionRequired` 或 runtime `collect_enabled=false`。

### Task 2: 修复 activeSuccessful 同步

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 调整 `select_accts_http()`**

账户选择校验通过后，构造 `payment_update_session = dict(session_data)`，写入 `status=LoginStatus.ACTIVE_SUCCESSFUL`、`account_accno`、`account_iban`、`last_error=None`，用这个对象调用 `_update_payment()`。

- [ ] **Step 2: 调整 active runtime 写入**

在 `_sync_runtime_state()` 的 `LoginStatus.ACTIVE_SUCCESSFUL` 分支调用 `mark_active_successful()` 时显式传：

```python
collect_enabled=True
ds_order_enabled=True
df_order_enabled=True
```

- [ ] **Step 3: 运行新增测试确认通过**

Run:

```bash
PYTHONPATH=api python3.12 -m unittest api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_select_accts_http_activates_payment_and_runtime_dispatch -v
```

Expected: PASS。

### Task 3: 回归验证和文档

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`

- [ ] **Step 1: 运行相关回归**

Run:

```bash
PYTHONPATH=api python3.12 -m unittest api.tests.test_easypaisa_business_flow_v2 -v
PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_runtime_service -v
```

Expected: PASS。

- [ ] **Step 2: 更新文档**

在 `api/build.md` 增加本轮验证命令；在 `api/err.md` 记录问题根因：账户选择路径先更新 payment、后更新 session，导致 `activeSuccessful` 未同步 DB/runtime。

- [ ] **Step 3: Git 收尾**

Run:

```bash
git status --short
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_business_flow_v2.py api/build.md api/err.md docs/superpowers/specs/2026-04-27-easypaisa-active-success-sync-design.md docs/superpowers/plans/2026-04-27-easypaisa-active-success-sync.md
git commit -m "fix: sync easypaisa active success state"
git push
```
