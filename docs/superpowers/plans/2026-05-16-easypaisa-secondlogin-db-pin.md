# EasyPaisa SecondLogin DB PIN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** EasyPaisa 普通 secondLogin 带 `pwd`，但除 change_pin 外，pwd 均从数据库 `Payment.pin` 读取。

**Architecture:** 保留 `_build_verify_account_request(session_data, with_pwd=True)` 的同步构建职责。新增一个异步 helper 在调用 `_call_second_login(..., with_pwd=True)` 前把 DB PIN 注入 `session_data['pinCode']`，并只在 `change_pin_http` 使用用户新输入 PIN。

**Tech Stack:** Python、pytest、SQLAlchemy ORM、GitNexus。

---

### Task 1: 回归测试

**Files:**

- Modify: `api/tests/test_easypaisa_v19_acceptance.py`
- Modify: `api/tests/test_easypaisa_v19_urm90040.py`
- Existing: `api/tests/test_easypaisa_v19_change_pin.py`

- [ ] **Step 1: ordinary second_login_http ignores request PIN**

新增测试：session 处于 `FINGERPRINT_VERIFIED`，请求里带 `pin='client_pin'`，mock `_query_payment()` 返回 `pin='db_pin'`，mock `_call_second_login()` 成功。断言 `_call_second_login(..., with_pwd=True)`，且传入 session 的 `pinCode == 'db_pin'`。

- [ ] **Step 2: pre_login second-time chain uses bound DB PIN**

更新二次上号成功测试：`bound_payment` 带 `pin='db_pin'`，session 里放一个不同的 `pinCode='client_pin'`。断言 `_call_second_login(..., with_pwd=True)`，且 session pinCode 被覆盖为 `db_pin`。

- [ ] **Step 3: fallback chain uses DB PIN**

更新 fallback 成功测试：`_query_payment()` 返回 `pin='db_pin'`，session 里放 `pinCode='client_pin'`。断言 `_call_second_login(..., with_pwd=True)`，且 session pinCode 被覆盖为 `db_pin`。

- [ ] **Step 4: verify red**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_urm90040.py -q
```

Expected: 新增/调整测试失败，显示 secondLogin 未使用 DB PIN 或未 `with_pwd=True`。

### Task 2: 实现 DB PIN 注入

**Files:**

- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 新增 helper**

新增 `_hydrate_second_login_pin_from_db(session_data, payment=None)`：

- 优先用传入 `payment['pin']`。
- 没有传入 PIN 时，通过 `session_data['real_payment_id']` 或 `session_data['id']` 调 `_query_payment()`。
- 读取到 PIN 后覆盖 `session_data['pinCode']` 并返回 `True`。
- 读取不到时记录 warning 并返回 `False`。

- [ ] **Step 2: 改 secondLogin 调用点**

- `_pre_login_second_time_chain`：先 hydrate，成功后 `_call_second_login(session_data, with_pwd=True)`。
- `_verify_otp_fallback_chain`：`_query_payment()` 已经读到 payment，先 hydrate，成功后 `_call_second_login(session_data, with_pwd=True)`。
- `second_login_http`：先 hydrate，成功后 `_call_second_login(session_data, with_pwd=True)`。
- `change_pin_http`：不接 helper，保持用户新 PIN 路径。

- [ ] **Step 3: verify green**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_change_pin.py api/tests/test_easypaisa_v19_urm90040.py -q
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

Expected: 全部通过。

### Task 3: 文档与提交

**Files:**

- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `docs/superpowers/specs/2026-05-16-easypaisa-secondlogin-db-pin-design.md`
- Modify: `docs/superpowers/plans/2026-05-16-easypaisa-secondlogin-db-pin.md`

- [ ] **Step 1: 文档同步**

在 `api/build.md` 记录本轮验收命令；在 `api/err.md` 记录“普通 secondLogin 不应使用客户端 PIN，必须读 DB PIN”的排错规则。

- [ ] **Step 2: detect changes**

Run:

```bash
npx gitnexus detect-changes --repo pk_project_k8s --scope staged
```

Expected: 变更范围只涉及 EasyPaisa secondLogin PIN 来源、相关测试和文档。

- [ ] **Step 3: commit and push**

Run:

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_urm90040.py api/build.md api/err.md docs/superpowers/specs/2026-05-16-easypaisa-secondlogin-db-pin-design.md docs/superpowers/plans/2026-05-16-easypaisa-secondlogin-db-pin.md
git commit -m "fix(easypaisa): use db pin for second login pwd"
git push origin d7pay
```
