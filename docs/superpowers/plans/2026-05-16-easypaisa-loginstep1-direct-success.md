# EasyPaisa loginStep1 Direct Success Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 兼容 EasyPaisa v2.2 `loginStep1 code=200` 直登成功，同时继续由本地维护指纹流程。

**Architecture:** `_send_otp()` 暴露 `direct_login` 标志，`send_otp_http` 和 `_urm90040_fallback` 共用 `_complete_login_step1_direct_success()`。直登成功统一保存 Payment、推进到 `OTP_VERIFIED`，首次登录返回指纹上传，fallback 登录继续内部续推。

**Tech Stack:** Python async API, pytest, GitNexus, EasyPaisa v1.9/v2.2 登录状态机。

---

### Task 1: 红灯测试

**Files:**
- Modify: `api/tests/test_easypaisa_v19_acceptance.py`
- Modify: `api/tests/test_easypaisa_v19_urm90040.py`

- [x] **Step 1: 写失败测试**

新增 `test_send_otp_http_direct_login_routes_to_fingerprint_upload`，断言 `send_otp_http` 在 `_send_otp(... direct_login=True)` 时返回 `fingerprintUploadRequired` 且 session 进入 `OTP_VERIFIED`。

新增 `test_urm90040_login_step1_direct_success_continues_fallback_chain`，断言 URM90040 fallback 的 `loginStep1` 直登成功时继续 `_verify_otp_fallback_chain()`。

- [x] **Step 2: 运行红灯**

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_send_otp_http_direct_login_routes_to_fingerprint_upload api/tests/test_easypaisa_v19_urm90040.py::test_urm90040_login_step1_direct_success_continues_fallback_chain -q
```

期望：两个测试失败，暴露旧代码仍按 OTP_SENT 处理 `code=200`。

### Task 2: 最小实现

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [x] **Step 1: `_send_otp()` 返回直登标记**

`code=100` 返回 `direct_login=False`，`code=200` 返回 `direct_login=True`。

- [x] **Step 2: 新增统一直登完成 helper**

`_complete_login_step1_direct_success()` 保存 Payment、维护 alias、写登录锁、推进 `OTP_VERIFIED`。

- [x] **Step 3: 接入两个入口**

`send_otp_http` 收到 `direct_login=True` 后返回指纹上传阶段；`_urm90040_fallback` 收到 `direct_login=True` 后继续 fallback 链路。

### Task 3: 防回归与文档

**Files:**
- Modify: `api/tests/test_easypaisa_v19_acceptance.py`
- Modify: `api/build.md`
- Modify: `api/err.md`

- [x] **Step 1: 加防回归测试**

`test_build_send_otp_request_does_not_use_upstream_fingerprint_flag` 断言 `loginStep1` 请求没有 `should_verify_fingerprint`。

- [x] **Step 2: 同步构建/排错文档**

在 `api/build.md` 加入 v2.2 直登验收命令；在 `api/err.md` 记录旧行为会把 `code=200` 错当成 OTP 已发送。

### Task 4: 验收与发布

**Files:**
- Verify only

- [x] **Step 1: 运行 EasyPaisa 登录相关测试**

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_change_pin.py api/tests/test_easypaisa_v19_urm90040.py -q
```

- [x] **Step 2: 编译检查**

```bash
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

- [x] **Step 3: GitNexus staged 检查**

```bash
npx gitnexus detect-changes --repo pk_project_k8s --scope staged
```

- [ ] **Step 4: commit & push**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_urm90040.py api/build.md api/err.md docs/superpowers/specs/2026-05-16-easypaisa-loginstep1-direct-success-design.md docs/superpowers/plans/2026-05-16-easypaisa-loginstep1-direct-success.md
git commit -m "fix(easypaisa): handle loginStep1 direct success"
git push origin d7pay
```
