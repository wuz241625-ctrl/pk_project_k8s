# EasyPaisa State Flow Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 EasyPaisa 状态响应 envelope，让每个 phase 都返回真实状态和可执行 next_step。

**Architecture:** 不改状态机邻接表，只收敛 API 返回协议。用测试锁定 `needsRelogin`、`verify_fingerprint` 幂等和 `accountSelectionRequired` 三类闭环。

**Tech Stack:** Python async、pytest、GitNexus。

---

## 1. 文件

- Modify: `api/application/app/login/banks/easypaisa.py`
- Modify: `api/tests/test_easypaisa_v19_acceptance.py`
- Modify: `api/tests/test_easypaisa_v19_force_terminal.py`
- Modify: `api/tests/test_easypaisa_v19_fingerprint.py`
- Modify: `api/tests/test_easypaisa_v19_pre_login_branching.py`
- Modify: `api/tests/test_easypaisa_v19_urm90040.py`
- Modify: `api/build.md`
- Modify: `api/err.md`
- Create: `docs/superpowers/specs/2026-05-17-easypaisa-state-flow-closure-design.md`
- Create: `docs/superpowers/plans/2026-05-17-easypaisa-state-flow-closure.md`

## 2. 任务

- [x] **Step 1: 影响面分析**

GitNexus impact：

- `_force_terminal_needs_relogin`：CRITICAL，影响 pre_login、verify_otp、verify_fingerprint、second_login、change_pin 等统一终止出口。本次只增加响应字段，不改状态推进。
- `verify_fingerprint_http`：LOW。
- `second_login_http`：LOW。
- `_fallback_finish_with_query_accts`：LOW。

- [x] **Step 2: 写失败测试**

测试目标：

- `_force_terminal_needs_relogin()` 返回 `next_step=needs_relogin`。
- `verify_fingerprint_http()` 对 `ACCOUNT_SELECTION_REQUIRED` 幂等返回 `phase=accountSelectionRequired,next_step=select_accts`。
- `ACCOUNT_SELECTION_REQUIRED` 成功响应统一 `next_step=select_accts`。

执行记录：5 条目标测试先失败，其中 4 条命中预期协议缺口，1 条已符合新协议。

- [x] **Step 3: 实现协议收敛**

- 增加状态到下一步的统一 helper，复用 `NEXT_STEP_MAP` 并补充终态。
- `_force_terminal_needs_relogin()` 返回 `next_step=needs_relogin`。
- `verify_fingerprint_http()` 幂等短路按真实状态返回 phase/next_step。
- `second_login_http()` 和 `_fallback_finish_with_query_accts()` 返回 `select_accts`。
- 历史 `_pre_login_second_time_chain()` 返回也改成 `select_accts`，避免测试/文档路径继续扩散旧协议。

执行记录：目标测试转绿，结果 `5 passed`。

- [x] **Step 4: 验收**

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m pytest tests/test_easypaisa_v19_force_terminal.py tests/test_easypaisa_v19_fingerprint.py tests/test_easypaisa_v19_acceptance.py tests/test_easypaisa_v19_pre_login_branching.py tests/test_easypaisa_v19_urm90040.py -q
python3 -m pytest tests/ -q -k easypaisa
python3 -m py_compile application/app/login/banks/easypaisa.py
```

执行记录：

- `python3 -m pytest tests/test_easypaisa_v19_force_terminal.py tests/test_easypaisa_v19_fingerprint.py tests/test_easypaisa_v19_acceptance.py tests/test_easypaisa_v19_pre_login_branching.py tests/test_easypaisa_v19_urm90040.py -q`：`44 passed`。
- `python3 -m pytest tests/ -q -k easypaisa`：`157 passed, 152 deselected`。
- `python3 -m py_compile application/app/login/banks/easypaisa.py`：通过。
- `git diff --check`：通过。
- `rg` 检查：`ACCOUNT_SELECTION_REQUIRED` 成功路径已统一 `select_accts`；保留的 `second_login` 只用于 `FINGERPRINT_VERIFIED` 重试路径。

- [x] **Step 5: 提交前检测并 push**

```bash
git diff --check
```

然后运行 GitNexus `detect_changes(scope=staged)`，commit 并 push `origin d7pay`。

提交前检测记录：

- GitNexus staged detect_changes：risk level `high`。
- 命中原因：`_force_terminal_needs_relogin` 是统一终止出口，`second_login_http` / `verify_fingerprint_http` 是 App 直接入口。
- 已读流程：
  - `Second_login_http -> _get_pre_login_key`
  - `Verify_fingerprint_http -> _get_pre_login_key`
  - `Verify_fingerprint_http -> _get_binary_redis`
  - `Change_pin_http -> _get_pre_login_key`（GitNexus 返回 JazzCash trace，作为交叉提示记录）
- 风险控制：本次只改 response envelope 的 `phase/next_step`，不改状态推进、锁、Redis key、上游调用、DB 写入。
