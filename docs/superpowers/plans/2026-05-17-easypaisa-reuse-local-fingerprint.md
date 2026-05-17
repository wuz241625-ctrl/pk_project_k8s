# EasyPaisa Reuse Local Fingerprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已绑定 EasyPaisa 账号在 `secondLogin` 快路径失败后优先复用 MySQL 已确认的本地旧指纹，旧指纹不可用时才让 App 重新 `upload_fingerprint`。

**Architecture:** 新增一个当前代码口径的旧指纹复用 helper，统一服务 `loginStep1 direct_success` 和 `verify_otp_http`。helper 串联 `upload_data`、`verifyFingerprint`、`secondLogin(with_pwd=True)`、`queryAccountList`，失败时回到上传指纹。

**Tech Stack:** Python async、pytest、unittest.mock、GitNexus。

---

## 1. 文件

- Modify: `api/application/app/login/banks/easypaisa.py`
- Modify: `api/tests/test_easypaisa_v19_pre_login_branching.py`
- Modify: `api/err.md`
- Modify: `api/build.md`
- Create: `docs/superpowers/specs/2026-05-17-easypaisa-reuse-local-fingerprint-design.md`
- Create: `docs/superpowers/plans/2026-05-17-easypaisa-reuse-local-fingerprint.md`

## 2. 任务

- [x] **Step 1: 影响面分析**

GitNexus impact：

- `pre_login_http`：LOW，直接入口 `PreLogin.post`。
- `verify_otp_http`：LOW，直接入口 `VerifyOtp.post`。
- `_verify_otp_fallback_chain`：LOW，影响 verify_otp fallback 流程。

- [x] **Step 2: 写失败测试**

在 `api/tests/test_easypaisa_v19_pre_login_branching.py` 增加：

- `test_bound_payment_otp_success_reuses_local_fingerprint`
- `test_bound_payment_direct_success_reuses_local_fingerprint_without_missing_helper`
- `test_bound_payment_local_fingerprint_rejected_routes_to_upload`

预期当前失败：

- OTP 成功分支仍返回 `fingerprintUploadRequired`。
- direct_success 分支调用不存在的 `_fallback_chain_after_verify_otp`。

执行记录：3 条测试先失败，分别命中 `otpVerified != accountSelectionRequired`、缺失 `_fallback_chain_after_verify_otp`、缺失 `_reuse_local_fingerprint_after_otp`。

- [x] **Step 3: 实现旧指纹复用 helper**

在 `EasyPaisa` 中新增 `_reuse_local_fingerprint_after_otp(redis_key, session_data, local_zip_path)`：

- 路径不存在：返回 `_route_to_fingerprint_upload`。
- `_call_upload_data` 失败：返回 `FP_UPSTREAM_REJECTED + next_step=upload_fingerprint`。
- `_call_verify_fingerprint` 非 success：返回 `FP_UPSTREAM_REJECTED + next_step=upload_fingerprint`。
- DB PIN 缺失：沿用 `_force_terminal_needs_relogin`。
- `secondLogin` 成功：调用 `_fallback_finish_with_query_accts`。
- `needs_pin_change/cooldown/其他失败` 沿用现有 fallback 语义。

- [x] **Step 4: 接入两个入口**

- `pre_login_http` 的 `direct_success + local_zip_path` 分支改为调用 `_reuse_local_fingerprint_after_otp`。
- `verify_otp_http` 在更新到 `OTP_VERIFIED` 后，如果 session 有 `reuse_local_fingerprint_after_otp/local_fingerprint_path`，调用 `_reuse_local_fingerprint_after_otp`。
- 无旧指纹标记时保持原 `fingerprintUploadRequired`。

执行记录：3 条新增测试已转绿，结果 `3 passed`。

- [x] **Step 5: 验收**

运行：

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m pytest tests/test_easypaisa_v19_pre_login_branching.py -q
python3 -m pytest tests/test_easypaisa_v19_acceptance.py tests/test_easypaisa_v19_urm90040.py tests/test_easypaisa_v19_fingerprint.py -q
python3 -m pytest tests/ -q -k easypaisa
python3 -m py_compile application/app/login/banks/easypaisa.py
```

执行记录：

- `python3 -m pytest tests/test_easypaisa_v19_pre_login_branching.py -q`：`11 passed`。
- `python3 -m pytest tests/test_easypaisa_v19_acceptance.py tests/test_easypaisa_v19_urm90040.py tests/test_easypaisa_v19_fingerprint.py -q`：`27 passed`。
- `python3 -m pytest tests/ -q -k easypaisa`：`156 passed, 152 deselected`。
- `python3 -m py_compile application/app/login/banks/easypaisa.py`：通过。
- `rg -n "_fallback_chain_after_verify_otp" api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_pre_login_branching.py`：无旧缺失方法引用。

- [ ] **Step 6: 提交前检查并 push**

```bash
git diff --check
```

然后运行 GitNexus `detect_changes(scope=staged)`，commit 并 push `origin d7pay`。

提交前检查记录：

- `git diff --check`：通过。
- GitNexus staged detect_changes：risk level `medium`，affected process 1：`Pre_login_http -> _get_pre_login_key`；已确认命中点来自 `pre_login_http` 入口变更，验收覆盖 `pre_login`、`verify_otp` 与 EasyPaisa 回归。
