# JazzCash OTP Fingerprint Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 JazzCash 上号链路改为发送验证码、验证验证码、验证指纹、激活成功。

**Architecture:** 后端沿用 JazzCash 银行驱动与 HTTP controller，把 OTP 提交和指纹验证拆成两个独立状态；JazzCash 上游没有 verifyFingerprint action，公开 `verify_fingerprint` 内部仍调用上游 `loginStep2` 验指纹。Flutter 沿用 EasyPaisa phase 模型，但 JazzCash 指纹成功后直接 activeSuccess。

**Tech Stack:** Python 3.12 unittest、Tornado handler、Redis session、Flutter/Riverpod、flutter_test。

---

### Task 1: 后端 JazzCash 状态机与 OTP 语义

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/application/app/login/banks/jazzcash.py`
- Test: `/Users/tear/pk_project_k8s/api/tests/test_jazzcash_business_flow_v2.py`

- [x] 写失败测试：确认 `JAZZCASH_API_VERSION == "v1.5"`。
- [x] 写失败测试：确认 JazzCash 不存在上游 `verify_fingerprint` action。
- [x] 写失败测试：确认 `_build_verify_fingerprint_request()` 使用 `action=loginStep2`。
- [x] 实现：新增指纹阶段状态，`verify_otp_http()` 不再调用 JazzCash 上游。
- [x] 运行：`python3.12 -m unittest api.tests.test_jazzcash_business_flow_v2 -v`。

### Task 2: 后端 OTP 后指纹阶段

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/application/app/login/banks/jazzcash.py`
- Test: `/Users/tear/pk_project_k8s/api/tests/test_jazzcash_business_flow_v2.py`

- [x] 写失败测试：`verify_otp_http()` 返回 `next_phase=fingerprintUploadRequired` 且不调用上游或 `_verify_account()`。
- [x] 写失败测试：OTP 后上传指纹把 session 推进到 `fingerprintUploaded`。
- [x] 实现：`verify_otp_http()` 保存 payment 后进入指纹阶段；`upload_fingerprint_http()` 接受 OTP 后状态。
- [x] 运行后端定向单测。

### Task 3: 后端 JazzCash verify_fingerprint 激活

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/application/app/login/banks/jazzcash.py`
- Modify: `/Users/tear/pk_project_k8s/api/application/lakshmi_api/controllers/http_login_controller.py`
- Test: `/Users/tear/pk_project_k8s/api/tests/test_jazzcash_business_flow_v2.py`

- [x] 写失败测试：`JazzCash.verify_fingerprint_http()` 成功后 activeSuccessful。
- [x] 写失败测试：HTTP controller 支持 `bankname=jazzcash`。
- [x] 实现：新增公开方法，内部用 `loginStep2` 验指纹、secondLogin、更新 payment 与 Redis 在线队列。
- [x] 运行后端定向单测。

### Task 4: Flutter JazzCash 新链路

**Files:**
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/onboarding/data/exchange_api.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/onboarding/application/onboarding_controller.dart`
- Test: `/Users/tear/pk_project/ashrafi_merchant_flutter/test/exchange_api_response_parsing_test.dart`
- Test: `/Users/tear/pk_project/ashrafi_merchant_flutter/test/onboarding_controller_test.dart`

- [x] 写失败测试：legacy `next_step=active_account` 不再直接成功。
- [x] 写失败测试：JazzCash OTP 后上传/验证指纹成功即 activeSuccess。
- [x] 写失败测试：JazzCash `fingerprintUploaded` 直接验指纹，不走 Veridium/secondLogin/query。
- [x] 实现：移除 activeAccount 分支，JazzCash 指纹成功直接 activeSuccess。
- [x] 运行 Flutter 定向测试。

### Task 5: 文档与最终验证

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/build.md`
- Modify: `/Users/tear/pk_project_k8s/api/err.md`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/README.md`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/docs/PAYMENTS.md`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/build.md`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/err.md`

- [x] 记录根因、处理方式和验收命令。
- [x] 运行后端全量相关测试。
- [x] 运行 Flutter test/analyze。
- [x] 构建生产域名 APK 并安装。
- [x] git commit && git push 两个仓库。
