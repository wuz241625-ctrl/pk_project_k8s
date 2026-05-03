# EasyPaisa Layer Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 固化 EasyPaisa 分层真相源边界，防止 Pakistanpay worker 和 admin runtime service 继续跨层读取或散落写入下游投影。

**Architecture:** 保留现有 `application/easypaisa_runtime` 作为 runtime 写入口。Pakistanpay worker 只读 `hash_easypaisa` / `set_easypaisa` 任务投影和 worker 私有缓存；legacy bridge 投影只由 runtime service/bridge 维护。

**Tech Stack:** Python 3.12, unittest, Redis fake, 现有 EasyPaisa runtime service。

---

### Task 1: 写边界回归测试

**Files:**
- Modify: `api/tests/easypaisa_runtime/test_sync_runtime_service.py`

- [x] **Step 1: 写失败测试**

在 `EasyPaisaJobsRuntimeIntegrationTests` 增加 `test_pakistanpay_read_cache_does_not_read_legacy_bridge_projection`。测试用 guarded redis 拒绝访问 `login_on_easypaisa_*`、`payment_online_*`、`payment_active_*`、`kick_off_*`，调用 `read_cache()` 后要求没有错误日志。

- [x] **Step 2: 验证失败**

Run:

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m unittest tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaJobsRuntimeIntegrationTests.test_pakistanpay_read_cache_does_not_read_legacy_bridge_projection -v
```

Expected: FAIL，原因是旧 `read_cache()` 仍读取 legacy bridge 投影并记录错误。

Actual: FAIL，错误指向 `login_on_easypaisa_533280` legacy bridge 投影读取。

### Task 2: 最小实现

**Files:**
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: `admin/application/easypaisa_runtime/service.py`

- [x] **Step 1: 收口 Pakistanpay read_cache**

删除 `read_cache()` 内对 legacy key 的读取和日志，只保留 `self.set_key`、`self.hash_key`、worker 锁、`upi_active_payment`、`easypaisa_device` 等 worker 自有调试信息。

- [x] **Step 2: 收口 admin raw job key**

把 `admin/application/easypaisa_runtime/service.py` 的 `hdel("hash_easypaisa", ...)` 和 `zrem("set_easypaisa", ...)` 改为 `keyspace.JOB_HASH` / `keyspace.JOB_SET`。

- [x] **Step 3: 验证测试转绿**

Run:

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m unittest tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaJobsRuntimeIntegrationTests.test_pakistanpay_read_cache_does_not_read_legacy_bridge_projection -v
```

Expected: PASS。

Actual: PASS。

### Task 3: 静态边界验收

**Files:**
- Create: `api/tests/test_easypaisa_layer_boundaries.py`

- [x] **Step 1: 写静态边界测试**

扫描 `api` 和 `admin` 生产 Python 文件，排除 `tests`、`vendor`、`__pycache__`，断言 `hash_easypaisa` / `set_easypaisa` raw 字符串只存在于 EasyPaisa runtime `keyspace.py`。

- [x] **Step 2: 运行边界测试**

Run:

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m unittest tests.test_easypaisa_layer_boundaries -v
```

Expected: PASS。

Actual: PASS。

### Task 4: 文档与总体验收

**Files:**
- Modify: `api/README.md`
- Modify: `api/build.md`
- Modify: `err.md`

- [x] **Step 1: 更新文档**

记录 EasyPaisa 分层真相源、Pakistanpay worker 只读 job 投影、legacy bridge 只作兼容投影，以及本轮验证命令。

- [x] **Step 2: 运行目标测试**

Run:

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m py_compile jobs/pakistanpay_v2.py application/easypaisa_runtime/*.py ../admin/application/easypaisa_runtime/*.py
python3 -m unittest tests.test_easypaisa_layer_boundaries tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaJobsRuntimeIntegrationTests.test_pakistanpay_read_cache_does_not_read_legacy_bridge_projection tests.test_order_push_easypaisa_runtime_guard -v
python3 -m pytest tests/easypaisa_runtime/test_reader.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/test_easypaisa_business_flow_v2.py -q
```

Expected: 所有命令 exit 0。

Actual:

- `python3 -m py_compile jobs/pakistanpay_v2.py application/easypaisa_runtime/*.py ../admin/application/easypaisa_runtime/*.py` exit 0。
- `python3 -m unittest tests.test_easypaisa_layer_boundaries ... tests.test_order_push_easypaisa_runtime_guard -v`：8 tests OK。
- `python3 -m pytest tests/easypaisa_runtime/test_reader.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/test_easypaisa_business_flow_v2.py -q`：138 passed，4 warnings。

- [ ] **Step 3: 提交并推送**

Run:

```bash
git status --short
git add docs/superpowers/specs/2026-05-03-easypaisa-layer-boundary-design.md docs/superpowers/plans/2026-05-03-easypaisa-layer-boundary.md api/tests/easypaisa_runtime/test_sync_runtime_service.py api/tests/test_easypaisa_layer_boundaries.py api/jobs/pakistanpay_v2.py admin/application/easypaisa_runtime/service.py api/README.md api/build.md err.md
git commit -m "fix: enforce easypaisa layer boundaries"
git push
```

Expected: push 成功。
