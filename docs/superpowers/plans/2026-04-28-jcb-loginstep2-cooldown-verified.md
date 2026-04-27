# JazzCashBusiness loginStep2 Cooldown Verified Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正 JCB `loginStep2` 冷却期语义：冷却代表指纹已通过，到期后直接 `secondLogin`。

**Architecture:** 后端继续复用我方 `/login/verify_fingerprint` 接口作为 App 按钮入口，但内部按 Redis session 的唯一真相源分支：冷却未到直接返回等待，冷却已到且已验证则跳过 `loginStep2` 执行 `secondLogin`。App 只更新展示文案和冷却 snapshot 默认状态。

**Tech Stack:** Python 3.12 unittest、Tornado 风格异步服务、Redis runtime snapshot、Flutter Riverpod。

---

### Task 1: 后端状态机测试先行

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/tests/test_jazzcash_business_flow_v2.py`

- [x] **Step 1: 写失败测试**

覆盖四个行为：

```python
test_verify_fingerprint_cooldown_marks_fingerprint_verified_and_waits
test_verify_fingerprint_during_cooldown_short_circuits_without_upstream
test_verify_fingerprint_after_cooldown_uses_second_login_without_login_step2
test_legacy_uploaded_cooldown_after_expiry_uses_second_login
test_payment_status_reports_wait_cooldown_for_verified_jcb_session
```

- [x] **Step 2: 运行测试确认失败**

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_verify_fingerprint_cooldown_marks_fingerprint_verified_and_waits \
  api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_verify_fingerprint_during_cooldown_short_circuits_without_upstream \
  api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_verify_fingerprint_after_cooldown_uses_second_login_without_login_step2 \
  api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_payment_status_reports_wait_cooldown_for_verified_jcb_session -v
```

Expected: FAIL，当前代码仍写 `fingerprintUploaded`，且到期后不会直接 `secondLogin`。

### Task 2: 后端实现语义修正

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/application/app/login/banks/jazzcash.py`

- [x] **Step 1: 冷却响应 next_phase 改为 `fingerprintVerified`**

`_build_fingerprint_cooldown_response()` 返回：

```python
'next_phase': LoginStatus.FINGERPRINT_VERIFIED
```

- [x] **Step 2: payment_status 支持 verified 冷却等待**

`_payment_status_next_action()` 对 `fingerprintUploaded` 和 `fingerprintVerified` 都识别冷却：

```python
status in (LoginStatus.FINGERPRINT_UPLOADED, LoginStatus.FINGERPRINT_VERIFIED)
```

- [x] **Step 3: 冷却未到短路写回 verified**

`verify_fingerprint_http()` 的 active cooldown 分支统一写：

```python
LoginStatus.FINGERPRINT_VERIFIED
```

- [x] **Step 4: 冷却到期后直接激活**

如果当前状态是 `fingerprintVerified` 且没有有效冷却，直接调用：

```python
return await self._activate_after_fingerprint(redis_key, session_data)
```

不调用 `_verify_fingerprint()`。

- [x] **Step 5: loginStep2 冷却和 secondLogin 冷却都保持 verified**

`verify_outcome == 'cooldown'` 和 `_activate_after_fingerprint()` 的 `IsInCoolDown` 分支都写 `LoginStatus.FINGERPRINT_VERIFIED`。

### Task 3: App 展示同步

**Files:**
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/onboarding/application/onboarding_controller.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/onboarding/presentation/fingerprint_page.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/test/onboarding_controller_test.dart`

- [x] **Step 1: 冷却 snapshot 默认状态改为 `fingerprintVerified`**

```dart
status: result.nextPhase ?? 'fingerprintVerified',
```

- [x] **Step 2: 冷却文案改为指纹已验证**

```dart
'Fingerprint verified. ${_cooldownText(...)}'
```

- [x] **Step 3: 更新测试期望**

JCB 冷却测试期望 `lastSnapshot.status == 'fingerprintVerified'`。

### Task 4: 文档、验证、部署

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/err.md`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/build.md`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/err.md`

- [x] **Step 1: 更新排错文档**

记录 `loginStep2` 冷却表示指纹已通过，冷却结束后直接 `secondLogin`。

- [x] **Step 2: 运行验收**

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest api.tests.test_jazzcash_business_flow_v2 -v
python3.12 -m py_compile api/application/app/login/banks/jazzcash.py
git diff --check
```

```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
export PATH=/Users/tear/sdk/flutter/bin:$PATH
flutter test test/exchange_api_response_parsing_test.dart test/onboarding_controller_test.dart
flutter analyze lib test
git diff --check
```

- [x] **Step 3: 提交推送并部署**

```bash
git push origin main
ssh root@34.92.65.29 'bash /opt/cicd/k8s/sh/deploy-api.sh'
```
