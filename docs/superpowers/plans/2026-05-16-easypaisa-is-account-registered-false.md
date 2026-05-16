# EasyPaisa isAccountRegistered False Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 EasyPaisa `isAccountRegistered code=403/data=false` 正确进入首次上号，而不是抛上游异常。

**Architecture:** 保持 `pre_login_http` 状态机不变，只修 `_is_account_registered()` 的响应语义映射，并用直接单元测试和 `pre_login` 集成测试覆盖 03009208353 的故障形态。

**Tech Stack:** Python async API, pytest, GitNexus, EasyPaisa v2.2 云机协议。

---

### Task 1: 影响面与红灯测试

**Files:**
- Modify: `api/tests/test_easypaisa_v19_acceptance.py`

- [x] **Step 1: GitNexus impact**

```bash
# target: _is_account_registered
# expected: LOW, direct caller pre_login_http
```

- [x] **Step 2: 写失败测试**

新增：

- `test_is_account_registered_403_false_means_not_registered`
- `test_is_account_registered_rejects_unexpected_codes`
- `test_pre_login_treats_unregistered_cloud_account_as_send_otp`

- [x] **Step 3: 运行红灯**

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_is_account_registered_403_false_means_not_registered api/tests/test_easypaisa_v19_acceptance.py::test_is_account_registered_rejects_unexpected_codes -q
```

期望：`403/data=false` 用例失败，因为旧代码抛 `NewApiError`。

### Task 2: 最小实现

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [x] **Step 1: 修改 `_is_account_registered()`**

规则：

```python
if code == 200 and data_field is True:
    return True
if code == 403 and data_field is False:
    return False
if code != 200:
    raise NewApiError(...)
return False
```

- [x] **Step 2: 跑新增测试**

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_is_account_registered_403_false_means_not_registered api/tests/test_easypaisa_v19_acceptance.py::test_is_account_registered_rejects_unexpected_codes api/tests/test_easypaisa_v19_acceptance.py::test_pre_login_treats_unregistered_cloud_account_as_send_otp -q
```

### Task 3: 文档与验收

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Create: `docs/superpowers/specs/2026-05-16-easypaisa-is-account-registered-false-design.md`
- Create: `docs/superpowers/plans/2026-05-16-easypaisa-is-account-registered-false.md`

- [x] **Step 1: 跑 EasyPaisa 登录回归**

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_change_pin.py api/tests/test_easypaisa_v19_urm90040.py -q
python3 -m pytest api/tests/test_easypaisa_v19_*.py -q
```

- [x] **Step 2: 编译检查**

```bash
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

- [ ] **Step 3: GitNexus staged 检查**

```bash
npx gitnexus detect-changes --repo pk_project_k8s --scope staged
```

- [ ] **Step 4: commit & push**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_acceptance.py api/build.md api/err.md docs/superpowers/specs/2026-05-16-easypaisa-is-account-registered-false-design.md docs/superpowers/plans/2026-05-16-easypaisa-is-account-registered-false.md
git commit -m "fix(easypaisa): treat unregistered cloud account as first login"
git push origin d7pay
```
