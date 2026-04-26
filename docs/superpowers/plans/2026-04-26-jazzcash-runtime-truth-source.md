# JazzCashBusiness Runtime Truth Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 JazzCashBusiness 的上号、采集、代收和代付运行态遵循 runtime 唯一真相源。

**Architecture:** 新增 `jazzcash_runtime`，与 EasyPaisa runtime 的 key 语义对齐但独立命名。API 和 admin 对 JazzCashBusiness 的在线、代收、代付判断统一读 snapshot/index，legacy Redis 队列只作为派生投影。

**Tech Stack:** Python 3.12, Tornado, Redis, unittest/pytest, 现有 EasyPaisa runtime 模式。

---

### Task 1: API runtime 单元测试

**Files:**
- Create: `api/tests/jazzcash_runtime/test_runtime_service.py`
- Create: `api/tests/jazzcash_runtime/test_reader.py`
- Modify: `api/tests/test_order_push_easypaisa_runtime_guard.py`

- [ ] 写失败测试：JazzCash `mark_active_successful()` 应写 snapshot/index 并投影 legacy。
- [ ] 写失败测试：JazzCash reader 在 snapshot 存在时必须忽略脏 `payment_online_*`。
- [ ] 写失败测试：JazzCash 代收派单守卫在 runtime 关闭时拒绝脏 legacy。
- [ ] 运行：

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.test_order_push_easypaisa_runtime_guard -v
```

期望：新增测试因 `application.jazzcash_runtime` 缺失或旧逻辑信任 legacy 而失败。

### Task 2: API runtime 实现

**Files:**
- Create: `api/application/jazzcash_runtime/__init__.py`
- Create: `api/application/jazzcash_runtime/keyspace.py`
- Create: `api/application/jazzcash_runtime/flags.py`
- Create: `api/application/jazzcash_runtime/legacy_bridge.py`
- Create: `api/application/jazzcash_runtime/runtime_service.py`
- Create: `api/application/jazzcash_runtime/sync_runtime_service.py`
- Create: `api/application/jazzcash_runtime/reader.py`

- [ ] 复制 EasyPaisa runtime 的最小语义到 JazzCash 独立 keyspace。
- [ ] `mark_active_successful()` 写 `online/collect_enabled/ds_order_enabled/df_order_enabled/dispatch_ds/dispatch_df/channels/session_phase`。
- [ ] `force_offline()` 和 `force_reset()` 清 runtime index、session、job hash/set、legacy 在线队列。
- [ ] reader 在 runtime read enabled 且无 snapshot 时返回离线。
- [ ] 运行 Task 1 测试，期望通过。

### Task 3: API 调用点收口

**Files:**
- Modify: `api/application/app/login/banks/jazzcash.py`
- Modify: `api/application/lakshmi_api/controllers/upi_controller.py`
- Modify: `api/application/app/my/my.py`
- Modify: `api/application/pay/pay.py`
- Modify: `api/application/lakshmi_api/services/payments/e_wallet_handler.py`
- Modify: `api/jobs/Jazzcashpay_v2.py`
- Modify: `api/jobs/jazzcash/jazzcash_monitor.py`
- Modify: `api/jobs/jazzcash/jazzcash_auto_payout.py`

- [ ] 登录激活成功改调用 `JazzCashRuntimeService.mark_active_successful()`。
- [ ] app/my 与 UPI controller 对 bank type 98 改读 `JazzCashRuntimeReader`。
- [ ] 代收派单 helper 对 bank type 98 改读 JazzCash runtime。
- [ ] JazzCash jobs 上下线通过 `SyncJazzCashRuntimeService` 写主状态。
- [ ] 自动代付选择账号前读 runtime `dispatch_df`。

### Task 4: Admin 测试与实现

**Files:**
- Create: `admin/application/jazzcash_runtime/__init__.py`
- Create: `admin/application/jazzcash_runtime/keyspace.py`
- Create: `admin/application/jazzcash_runtime/flags.py`
- Create: `admin/application/jazzcash_runtime/reader.py`
- Create: `admin/application/jazzcash_runtime/service.py`
- Create: `admin/tests/test_jazzcash_runtime_reader.py`
- Modify: `admin/application/partner/partner.py`

- [ ] 写失败测试：admin JazzCash 列表字段来自 snapshot 而非 legacy。
- [ ] 写失败测试：admin `force_reset()` 清 runtime 与 legacy 残留。
- [ ] 修改 `partner.py` 的列表、筛选、monitor 开关、resettingPayment。
- [ ] 运行：

```bash
PYTHONPATH=admin python3.12 -m unittest admin.tests.test_jazzcash_runtime_reader -v
```

期望：测试通过。

### Task 5: 文档与验收

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `admin/build.md`
- Modify: `admin/err.md`

- [ ] 写入 JazzCash runtime 本地验证命令。
- [ ] 写入 “legacy 队列脏数据不再作为真相源” 排错说明。
- [ ] 运行 API/Admin py_compile。
- [ ] 运行新增 runtime 单测和相关既有 EasyPaisa 回归测试。
- [ ] `git status` 确认只包含本任务相关文件。
- [ ] commit 并 push 当前分支。
