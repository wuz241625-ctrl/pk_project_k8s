# EasyPaisa 上号流程重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对齐 EasyPaisa v1.9 云机 API 重构上号流程；修复生产事故 533264（已 active 重复 pre_login 崩溃）与 03445021275（URM90040 死循环）；状态机从 11 个收敛到 8 个；引入指纹两阶段提交；统一 needsRelogin 终止入口。

**Architecture:** 单文件改造 `api/application/app/login/banks/easypaisa.py`。8 状态机：`PRE_LOGIN_CREATED → OTP_SENT → OTP_VERIFIED → FINGERPRINT_VERIFIED → AWAITING_PIN_CHANGE → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL`，加终态 `NEEDS_RELOGIN`。所有 needsRelogin 走统一函数 `_force_terminal_needs_relogin`。指纹分两阶段：`upload_fingerprint_http` 仅存 Redis pending，`verify_fingerprint_http` 推上游 + 全成功才落盘。APP 端最小化改动：`PreLoginResult` 增加 `resumed/phase` 字段、`submitForm` 处理 `resumed=true` 路由。

**Tech Stack:** Python (asyncio/aioredis/SQLAlchemy/bcrypt)、Dart (Flutter for APP)、Redis 会话存储、MySQL Payment 表、EasyPaisa v1.9 上游 API。

**Commitments(brainstorming 阶段已确认)：**
1. 所有 spec §3.3/§3.4/§4.1 里的 `EP_xxx` 错误码按 §4.2 注释映射成 APP 已识别的数字码（具体表见 Task 0）；映射不出的暂用 `20102 + state hint`，code review 时统一清理。
2. 删除 §3.3 末尾的"二次上号续推超时降级路径"——APP timeout 30s 已够，二次续推 RT 抖到 20s+ 是云机端事故，不该被掩盖。

**Spec reference:** `docs/superpowers/specs/2026-05-14-easypaisa-login-redesign-design.md`（worktree 内）

---

## File Structure

**Backend** (`/Users/tear/pk_project_k8s`，branch `d7pay`):

| 操作 | 文件 | 职责 |
|---|---|---|
| Modify | `api/application/app/login/banks/easypaisa.py` | 主重构（当前 3245 行，目标 ~1500 行） |
| Create | `api/tests/test_easypaisa_v19_state_machine.py` | 8 状态机 + 邻接表单元测试 |
| Create | `api/tests/test_easypaisa_v19_force_terminal.py` | `_force_terminal_needs_relogin` 单元测试 |
| Create | `api/tests/test_easypaisa_v19_resumed_session.py` | §3.3.1 resumed 协议测试 |
| Create | `api/tests/test_easypaisa_v19_fingerprint.py` | U7/U15 指纹两阶段测试 |
| Create | `api/tests/test_easypaisa_v19_urm90040.py` | U4/U5/U14 URM90040 场景测试 |
| Create | `api/tests/test_easypaisa_v19_acceptance.py` | U1-U24 端到端验收（mock 上游） |

**说明**：本项目已完成 MySQL 转型，"是否在线"的权威源是 MySQL `Payment.wallet_status==1`（go-worker 直接读 MySQL 调度，见 `/Users/tear/pk-go-worker/internal/health/handler.go`）。spec 早期版本提到的 runtime_snapshot Redis 层在本项目不存在，因此**不需要**迁移/回滚脚本（已从计划删除）。`hash_easypaisa`/`set_easypaisa` 是 legacy 残骸（仅有 hdel/zrem 清理，无写入），重构后也不再写入。

**APP** (`/Users/tear/pk_project/ashrafi_merchant_flutter`，branch `d7pay`):

| 操作 | 文件 | 改动 |
|---|---|---|
| Modify | `lib/features/onboarding/data/exchange_api.dart` | `PreLoginResult` 加 `resumed/phase/accounts/expiresIn` 字段 |
| Modify | `lib/features/onboarding/controllers/onboarding_controller.dart` | `submitForm()` 检测 `resumed=true` 时按 `phase` 路由到对应 UI |

---

## Task 0: 锁定错误码映射表（无代码改动，仅记录）

**Purpose:** 把 Commitment 1 的映射规则写到代码注释里供后续 task 引用。

**Files:**
- Reference doc: this plan, below table

**错误码映射规则（每个 spec 提到 `EP_xxx` 的地方按此表替换）：**

| spec 里出现的 `EP_xxx` | 落地用的码 | APP 已识别？ |
|---|---|---|
| `EP_LOGINED` | `20101` | ✅ alreadyLoggingIn |
| `EP_MISSING_PARAMS` | `20001` | ✅（现有 ErrorCode.MissingParams） |
| `EP_INVALID_PASSWORD` | `20004` | ✅（现有 ErrorCode.InvalidPaswd） |
| `EP_LOGIN_ATTEMPS` | `20106` | ✅（现有 ErrorCode.LoginAttemps） |
| `EP_PAYMENT_NOT_FOUND` | `20003` | ✅（现有 ErrorCode.InvalidBankOrPayment） |
| `EP_PERMISSION_DENIED` | `10402` | ✅ |
| `EP_PAYMENT_PHONE_MISMATCH` | `20005` | ✅（现有 ErrorCode.PaymentPhoneMismatch） |
| `EP_OTP_INVALID` | `20307` | ✅ |
| `EP_BAD_STATE` | `20102 + state hint` | ✅ stateTransitionInvalid |
| `EP_THROTTLED` | `20102 + state hint` | ✅ otpAlreadyPending |
| `EP_BAD_REQUEST` | `20102 + state hint` | ✅ |
| `EP_NETWORK` | `SL_UPSTREAM_ERROR` | ✅ |
| `EP_FP_PUSH_FAIL` | `FP_UPSTREAM_REJECTED` | ✅ |
| `EP_QUERY_FAIL` | `SL_UPSTREAM_ERROR` | ✅ |
| `EP_SYSTEM_ERROR` | `SL_UPSTREAM_ERROR + reason="local IO"` | ✅ |
| `EP_FP_FILE_MISSING` | `EP_FP_FILE_MISSING`（本次唯一新增码） | ❌ 需 APP 补识别（可回退 needsRelogin） |

- [x] **Step 1: 在 `easypaisa.py` 顶部 ErrorCode 类下方添加映射注释（不改代码）** ✅ commit `ee8bc8c3`

```python
# 仅添加注释，紧跟在 class ErrorCode: 定义之后
# === v1.9 重构错误码映射（Task 0 commitment）===
# 实现 *_http 方法时，所有 spec 中 EP_xxx 占位符按下表映射成 APP 已识别码：
#   EP_LOGINED            → ErrorCode.Logined        (20101)
#   EP_MISSING_PARAMS     → ErrorCode.MissingParams  (20001)
#   EP_INVALID_PASSWORD   → ErrorCode.InvalidPaswd   (20004)
#   EP_LOGIN_ATTEMPS      → ErrorCode.LoginAttemps   (20106)
#   EP_PAYMENT_NOT_FOUND  → ErrorCode.InvalidBankOrPayment (20003)
#   EP_PERMISSION_DENIED  → '10402'
#   EP_PAYMENT_PHONE_MISMATCH → ErrorCode.PaymentPhoneMismatch (20005)
#   EP_OTP_INVALID        → ErrorCode.VerifyOTPFail  (20307)
#   EP_BAD_STATE/THROTTLED/BAD_REQUEST → 'INVALID_TRANSITION' + state hint
#   EP_NETWORK/QUERY_FAIL/SYSTEM_ERROR  → 'SL_UPSTREAM_ERROR'
#   EP_FP_PUSH_FAIL       → 'FP_UPSTREAM_REJECTED'
#   EP_FP_FILE_MISSING    → 'EP_FP_FILE_MISSING' (本次唯一新增；APP 暂回退 needsRelogin)
# ===============================================
```

- [x] **Step 2: Commit** ✅ commit `ee8bc8c3`

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "docs(easypaisa): record v1.9 error code mapping table"
```

**额外补 commit `93c5dfd4`**（subagent 报 concern：之前的 device 字段清理工作未 commit，HEAD 当时是 4313 行而不是计划假设的 3245 行）：把 cleanup 作为单独 commit 推进。当前 HEAD 干净，3260 行。

**Review 跳过说明**：Task 0 是纯文档（comment block），无 runtime 行为；implementer 自检 + 我亲自验证 + AST 通过。后续涉及代码逻辑的 task 必须走完整两阶段 review。

---

## Task 1: 引入 8 状态枚举与邻接表（Foundation） ✅ commit `37dc43fb` (7/7 tests pass)

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:46-90`（LoginStatus + STATUS_TRANSITIONS）
- Test: `api/tests/test_easypaisa_v19_state_machine.py`（创建）

- [ ] **Step 1: 写邻接表单元测试（先红）**

文件 `api/tests/test_easypaisa_v19_state_machine.py`：

```python
"""验证 v1.9 8 状态机的邻接表语义。"""
import pytest
from application.app.login.banks.easypaisa import LoginStatus, STATUS_TRANSITIONS


def test_eight_states_defined():
    """8 状态全部定义且字符串值符合 APP 契约。"""
    assert LoginStatus.PRE_LOGIN_CREATED == "preLoginCreated"
    assert LoginStatus.OTP_SENT == "otpSent"
    assert LoginStatus.OTP_VERIFIED == "otpVerified"
    assert LoginStatus.FINGERPRINT_VERIFIED == "fingerprintVerified"
    assert LoginStatus.AWAITING_PIN_CHANGE == "awaitingPinChange"
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED == "accountSelectionRequired"
    assert LoginStatus.ACTIVE_SUCCESSFUL == "activeSuccessful"
    assert LoginStatus.NEEDS_RELOGIN == "needsRelogin"


def test_terminal_states_have_no_outgoing():
    assert STATUS_TRANSITIONS[LoginStatus.ACTIVE_SUCCESSFUL] == []
    assert STATUS_TRANSITIONS[LoginStatus.NEEDS_RELOGIN] == []


def test_all_non_terminal_can_reach_needs_relogin():
    """所有非终态都能跳到 NEEDS_RELOGIN（统一逃生门）。"""
    non_terminal = [
        LoginStatus.PRE_LOGIN_CREATED,
        LoginStatus.OTP_SENT,
        LoginStatus.OTP_VERIFIED,
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.AWAITING_PIN_CHANGE,
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
    ]
    for status in non_terminal:
        assert LoginStatus.NEEDS_RELOGIN in STATUS_TRANSITIONS[status], \
            f"{status} cannot transition to NEEDS_RELOGIN"


def test_pre_login_cross_step_edges():
    """spec §3.1.1：pre_login 内部续推支持跨步。"""
    pre = STATUS_TRANSITIONS[LoginStatus.PRE_LOGIN_CREATED]
    assert LoginStatus.OTP_SENT in pre              # 首次
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED in pre  # 二次续推全成功
    assert LoginStatus.OTP_VERIFIED in pre          # 二次指纹失败借位
    assert LoginStatus.AWAITING_PIN_CHANGE in pre   # 二次续推遇 PIN 需改


def test_otp_sent_cross_step_edges():
    otp_sent = STATUS_TRANSITIONS[LoginStatus.OTP_SENT]
    assert LoginStatus.OTP_VERIFIED in otp_sent
    assert LoginStatus.ACCOUNT_SELECTION_REQUIRED in otp_sent  # fallback 续推全成功
    assert LoginStatus.PRE_LOGIN_CREATED in otp_sent           # URM90040 reset


def test_awaiting_pin_change_returns_to_fingerprint_verified():
    transitions = STATUS_TRANSITIONS[LoginStatus.AWAITING_PIN_CHANGE]
    assert LoginStatus.FINGERPRINT_VERIFIED in transitions


def test_removed_states_absent():
    """spec §6.1：老状态必须删除。"""
    assert not hasattr(LoginStatus, 'FINGERPRINT_UPLOAD_REQUIRED')
    assert not hasattr(LoginStatus, 'FINGERPRINT_UPLOADED')
    assert not hasattr(LoginStatus, 'SECOND_LOGIN_READY')
    assert not hasattr(LoginStatus, 'SECOND_LOGIN_PASSED')
    # LOGIN_SUCCESSFUL 是别名，也删
    assert not hasattr(LoginStatus, 'LOGIN_SUCCESSFUL')
```

- [ ] **Step 2: 跑测试确认全部失败**

Run: `cd /Users/tear/pk_project_k8s && pytest api/tests/test_easypaisa_v19_state_machine.py -v`
Expected: FAIL with `AttributeError: LoginStatus has no attribute 'NEEDS_RELOGIN'` 等。

- [ ] **Step 3: 替换 `easypaisa.py` 的 LoginStatus + STATUS_TRANSITIONS（line 46-90）**

把当前 LoginStatus 类整段替换为：

```python
class LoginStatus:
    PRE_LOGIN_CREATED = "preLoginCreated"
    OTP_SENT = "otpSent"
    OTP_VERIFIED = "otpVerified"
    FINGERPRINT_VERIFIED = "fingerprintVerified"
    AWAITING_PIN_CHANGE = "awaitingPinChange"
    ACCOUNT_SELECTION_REQUIRED = "accountSelectionRequired"
    ACTIVE_SUCCESSFUL = "activeSuccessful"
    NEEDS_RELOGIN = "needsRelogin"

STATUS_TRANSITIONS = {
    LoginStatus.PRE_LOGIN_CREATED: [
        LoginStatus.OTP_SENT,
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        LoginStatus.OTP_VERIFIED,
        LoginStatus.AWAITING_PIN_CHANGE,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.OTP_SENT: [
        LoginStatus.OTP_SENT,
        LoginStatus.OTP_VERIFIED,
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        LoginStatus.PRE_LOGIN_CREATED,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.OTP_VERIFIED: [
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.FINGERPRINT_VERIFIED: [
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        LoginStatus.AWAITING_PIN_CHANGE,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.AWAITING_PIN_CHANGE: [
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.ACCOUNT_SELECTION_REQUIRED: [
        LoginStatus.ACTIVE_SUCCESSFUL,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.ACTIVE_SUCCESSFUL: [],
    LoginStatus.NEEDS_RELOGIN: [],
}
```

注意：**保留 OTP_SENT 的自循环**（resend 用），其他不变。

- [ ] **Step 4: 跑测试确认全部通过**

Run: `cd /Users/tear/pk_project_k8s && pytest api/tests/test_easypaisa_v19_state_machine.py -v`
Expected: 7 passed

- [ ] **Step 5: 跑全文件 grep 检查 LoginStatus 老名字残留**

Run: `grep -nE "FINGERPRINT_UPLOAD_REQUIRED|FINGERPRINT_UPLOADED|SECOND_LOGIN_READY|SECOND_LOGIN_PASSED|LOGIN_SUCCESSFUL" api/application/app/login/banks/easypaisa.py`
Expected: 一定有匹配（后续 task 逐步清理）。把数量记下来作为 baseline，最后 Task 18 时必须降到 0。

- [ ] **Step 6: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_state_machine.py
git commit -m "feat(easypaisa): introduce v1.9 8-state machine with adjacency table"
```

---

## Task 2: 实现 `_force_terminal_needs_relogin` 统一终止入口 ✅ commit `1cb61c35` (4/4 tests pass)

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（在 class EasyPaisa 内部新增方法）
- Test: `api/tests/test_easypaisa_v19_force_terminal.py`（创建）

- [ ] **Step 1: 写测试（先红）**

文件 `api/tests/test_easypaisa_v19_force_terminal.py`：

```python
"""验证 _force_terminal_needs_relogin 的统一终止行为。"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_instance():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.set = AsyncMock(return_value=True)
    handler.redis.setex = AsyncMock(return_value=True)
    handler.redis.expire = AsyncMock(return_value=True)
    ep = EasyPaisa(handler)
    return ep


@pytest.mark.asyncio
async def test_force_terminal_writes_status(ep_instance):
    redis_key = "pre_login_easypaisa_533290"
    session = {
        'phone': '03445021275',
        'id': '533290',
        'bankname': 'easypaisa',
        'status': LoginStatus.FINGERPRINT_VERIFIED,
        'status_history': [LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_SENT,
                           LoginStatus.OTP_VERIFIED, LoginStatus.FINGERPRINT_VERIFIED],
    }
    result = await ep_instance._force_terminal_needs_relogin(
        redis_key=redis_key,
        session_data=session,
        reason='Test forced terminal',
        error_code='SL_NEEDS_RELOGIN',
    )
    assert session['status'] == LoginStatus.NEEDS_RELOGIN
    assert LoginStatus.NEEDS_RELOGIN in session['status_history']
    assert session['last_error']['code'] == 'SL_NEEDS_RELOGIN'
    assert session['last_error']['reason'] == 'Test forced terminal'


@pytest.mark.asyncio
async def test_force_terminal_returns_standard_envelope(ep_instance):
    session = {'phone': 'x', 'id': '1', 'bankname': 'easypaisa', 'status': LoginStatus.OTP_SENT, 'status_history': []}
    result = await ep_instance._force_terminal_needs_relogin(
        redis_key='k', session_data=session,
        reason='r', error_code='SL_NEEDS_RELOGIN', message='custom msg',
    )
    assert result['status'] == 'error'
    assert result['message'] == 'custom msg'
    assert result['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert result['data']['phase'] == LoginStatus.NEEDS_RELOGIN


@pytest.mark.asyncio
async def test_force_terminal_schedules_delayed_delete(ep_instance):
    """5 秒后删 key 让 APP 能拉 last_error。"""
    session = {'phone': 'x', 'id': '1', 'bankname': 'easypaisa', 'status': LoginStatus.OTP_VERIFIED, 'status_history': []}
    await ep_instance._force_terminal_needs_relogin(
        redis_key='pre_login_easypaisa_1', session_data=session,
        reason='r', error_code='SL_NEEDS_RELOGIN',
    )
    # expire 应该被调用过，TTL 设为 5
    ep_instance.redis.expire.assert_called_with('pre_login_easypaisa_1', 5)


@pytest.mark.asyncio
async def test_force_terminal_rejects_already_active(ep_instance):
    """已是 ACTIVE_SUCCESSFUL 时禁止跳到 NEEDS_RELOGIN（邻接表禁止）。"""
    session = {'phone': 'x', 'id': '1', 'bankname': 'easypaisa',
               'status': LoginStatus.ACTIVE_SUCCESSFUL, 'status_history': []}
    with pytest.raises(Exception) as exc:
        await ep_instance._force_terminal_needs_relogin(
            redis_key='k', session_data=session,
            reason='r', error_code='SL_NEEDS_RELOGIN',
        )
    assert 'INVALID_TRANSITION' in str(exc.value) or 'ACTIVE_SUCCESSFUL' in str(exc.value)
```

- [ ] **Step 2: 跑测试确认全部失败**

Run: `pytest api/tests/test_easypaisa_v19_force_terminal.py -v`
Expected: FAIL with `AttributeError: 'EasyPaisa' has no attribute '_force_terminal_needs_relogin'`

- [ ] **Step 3: 在 `easypaisa.py` 的 `class EasyPaisa` 内部添加方法**

位置：在 `_release_payment_interface_lock` 之后、`_read_prelogin_entry` 之前。代码：

```python
async def _force_terminal_needs_relogin(
    self,
    redis_key: str,
    session_data: dict,
    reason: str,
    error_code: str,
    message: str | None = None,
) -> dict:
    """spec §3.1.2：所有 needsRelogin 必须经过这里。
    
    Why: 统一可观测性（grep _force_terminal_needs_relogin 看所有终止点）+
    保留 5 秒窗口让 APP 拉 last_error 后再删 key。
    """
    funcName = '_force_terminal_needs_relogin'
    current = session_data.get('status', LoginStatus.PRE_LOGIN_CREATED)
    # 邻接表强制校验：终态不能再终止
    if LoginStatus.NEEDS_RELOGIN not in STATUS_TRANSITIONS.get(current, []):
        msg = f'INVALID_TRANSITION: {current} -> NEEDS_RELOGIN not allowed'
        self.logger.error(f'{self._log_key(funcName)} {msg}')
        raise NewApiError('INVALID_TRANSITION', msg)
    self.logger.warning(
        f'{self._log_key(funcName)} 状态推进: {current} → {LoginStatus.NEEDS_RELOGIN}, reason={reason}'
    )
    session_data['status'] = LoginStatus.NEEDS_RELOGIN
    session_data.setdefault('status_history', []).append(LoginStatus.NEEDS_RELOGIN)
    session_data['last_error'] = {
        'code': error_code,
        'message': message,
        'reason': reason,
        'timestamp': int(time.time()),
    }
    session_data['last_status_change'] = int(time.time())
    await self.redis.setex(redis_key, 5, json.dumps(session_data))
    await self.redis.expire(redis_key, 5)
    return {
        'status': 'error',
        'message': message or '账户需要重新登录',
        'data': {
            'code': error_code,
            'phase': LoginStatus.NEEDS_RELOGIN,
        },
    }
```

- [ ] **Step 4: 跑测试确认全部通过**

Run: `pytest api/tests/test_easypaisa_v19_force_terminal.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_force_terminal.py
git commit -m "feat(easypaisa): add _force_terminal_needs_relogin unified terminal entry"
```

---

## Task 3: 重写 `_assert_status_transition` 兼容 NEEDS_RELOGIN ✅ commit `30520e38` (10/10 tests pass; 方法未动)

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（`_assert_status_transition` 方法）
- Test: `api/tests/test_easypaisa_v19_state_machine.py`（追加）

- [ ] **Step 1: 追加测试**

把以下追加到 `api/tests/test_easypaisa_v19_state_machine.py` 末尾：

```python
import pytest
from unittest.mock import MagicMock
from application.app.login.banks.easypaisa import EasyPaisa
from application.lakshmi_api.exceptions.api_error import NewApiError


@pytest.fixture
def ep_for_transition():
    handler = MagicMock()
    return EasyPaisa(handler)


def test_assert_transition_allows_valid(ep_for_transition):
    session = {'status': LoginStatus.OTP_SENT}
    ep_for_transition._assert_status_transition(
        session, LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED, 'test'
    )


def test_assert_transition_rejects_invalid(ep_for_transition):
    session = {'status': LoginStatus.OTP_SENT}
    with pytest.raises(NewApiError) as exc:
        ep_for_transition._assert_status_transition(
            session, LoginStatus.OTP_SENT, LoginStatus.ACTIVE_SUCCESSFUL, 'test'
        )
    assert exc.value.code == 'INVALID_TRANSITION'


def test_assert_transition_pre_login_to_account_selection(ep_for_transition):
    """二次上号跨步要被允许。"""
    session = {'status': LoginStatus.PRE_LOGIN_CREATED}
    ep_for_transition._assert_status_transition(
        session, LoginStatus.PRE_LOGIN_CREATED, LoginStatus.ACCOUNT_SELECTION_REQUIRED, 'test'
    )
```

- [ ] **Step 2: 跑测试确认通过/失败状况**

Run: `pytest api/tests/test_easypaisa_v19_state_machine.py -v`
Expected: 现有测试 7 passed + 新加 3 个看 _assert_status_transition 当前实现是否兼容。如果测试都过了，跳到 Step 5；如果有不过，去 Step 3。

- [ ] **Step 3: 如果 Step 2 有失败，更新 `_assert_status_transition` 当前位置（当前 line ~860）**

当前实现已经支持 STATUS_TRANSITIONS 字典，理论上 Task 1 改完字典后无需改方法体。但确认下方法仍然 raise `NewApiError('INVALID_TRANSITION', ...)` 而不是其他 error code。如果不是，改为：

```python
def _assert_status_transition(self, session_data, expected_current_status, target_status, operation_name):
    funcName = '_assert_status_transition'
    current_status = session_data.get('status')
    if current_status != expected_current_status:
        msg = f'{self._log_key(funcName)} expected={expected_current_status} actual={current_status} op={operation_name}'
        self.logger.error(msg)
        raise NewApiError('INVALID_TRANSITION', msg)
    if target_status not in STATUS_TRANSITIONS.get(current_status, []):
        msg = f'{self._log_key(funcName)} {current_status} -> {target_status} not allowed (op={operation_name})'
        self.logger.error(msg)
        raise NewApiError('INVALID_TRANSITION', msg)
    return True
```

- [ ] **Step 4: 跑测试确认全部通过**

Run: `pytest api/tests/test_easypaisa_v19_state_machine.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_state_machine.py
git commit -m "test(easypaisa): cover _assert_status_transition with new state set"
```

---

## Task 4: 删除老状态相关辅助函数与方法 ✅ commit `37e20e3e` (−296 行, 14/14 tests, AccountStatus 也删了 cross-file 已校验)

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

待删除函数（spec §6.2/§6.3）：
- `_replay_saved_fingerprint`（line ~3631）
- `_build_bound_second_login_session`（line ~4094）
- `_verify_account`（line ~3105，整段）
- `active_account_http`（line ~2237）

- [ ] **Step 1: 定位并删除 `_replay_saved_fingerprint`**

Run: `grep -n "_replay_saved_fingerprint\b" api/application/app/login/banks/easypaisa.py`
Expected: 找到定义行和所有引用。先删引用（verify_otp_http 内部调用，line ~1816-1825），后删定义。

引用删除（verify_otp_http 内部）：找到类似下面的几行：

```python
try:
    replay_ok = await self._replay_saved_fingerprint(real_payment_id, session_phone)
except Exception:
    replay_ok = False

next_phase = (
    LoginStatus.FINGERPRINT_UPLOADED
    if replay_ok else LoginStatus.FINGERPRINT_UPLOAD_REQUIRED
)
```

整段删除（包括 try/except 和 next_phase 计算）。**这里会出现编译错误**，因为下方还引用 `next_phase`——属于 Task 9（verify_otp_http 重写）的范围，本 task 暂不修复，只删定义和引用。

如果 verify_otp_http 暂时不能运行，OK——后续 task 会重写它。本 task 只做"删孤立函数和引用"。

定义删除：找到 `async def _replay_saved_fingerprint` 整个方法体，删除。

- [ ] **Step 2: 删除 `_build_bound_second_login_session`**

Run: `grep -n "_build_bound_second_login_session" api/application/app/login/banks/easypaisa.py`
Expected: 找到定义 + 引用（second_login_http 内部 line ~2011）。

引用删除（second_login_http 内 `if not session_data:` 分支）：

把这段：
```python
if not session_data:
    session_data = await self._build_bound_second_login_session(bankname, requested_payment_id)
    redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=requested_payment_id)
```

改为：
```python
if not session_data:
    raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')
```

定义删除：找到 `async def _build_bound_second_login_session` 整个方法体，删除。

- [ ] **Step 3: 删除 `_verify_account` 整段**

Run: `grep -n "_verify_account\b" api/application/app/login/banks/easypaisa.py`
Expected: 找到定义（line ~3105 区域）和所有引用：
- `_promote_session_to_active_successful` (line ~999)
- 其他可能的调用点

引用删除：在 `_promote_session_to_active_successful` 中找到 `api_result_verify_acct = await self._verify_account(session_data)` 调用，整个 method `_promote_session_to_active_successful` 也属于 v1.6 残留——一并删除（spec §6.2 隐含：v1.9 没有"先验指纹后验 PIN"路径）。

把 `_promote_session_to_active_successful` 和它在 `_try_promote_session_from_payment_status` 中的调用全部删除。然后删 `_verify_account` 定义本身。

- [ ] **Step 4: 删除 `active_account_http`**

替换为 stub（保持 controller 兼容）：

```python
async def active_account_http(self, data):
    """Deprecated since v1.9. Returns API_DEPRECATED."""
    self.login_data = data
    return {'code': 'API_DEPRECATED', 'hint': 'use verify_fingerprint + second_login'}
```

如果已是 stub（之前已经简化过），跳过。

- [ ] **Step 5: 跑文件级 grep 确认死代码引用为 0**

Run:
```bash
grep -nE "_replay_saved_fingerprint|_build_bound_second_login_session|_verify_account\b|_promote_session_to_active_successful|_try_promote_session_from_payment_status" api/application/app/login/banks/easypaisa.py
```
Expected: 0 匹配。

- [ ] **Step 6: 验证 import + AST 解析**

Run: `python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): remove dead helpers (replay_fingerprint/bound_second_login/verify_account/promote_active)"
```

---

## Task 5: 实现 `_resumed_session_response` 协议（§3.3.1） ✅ commit `e92b0629` (5/5 tests, 累计 19/19)

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（新增辅助方法）
- Test: `api/tests/test_easypaisa_v19_resumed_session.py`（创建）

- [ ] **Step 1: 写测试**

文件 `api/tests/test_easypaisa_v19_resumed_session.py`：

```python
"""§3.3.1 残留 session 复用协议。"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.ttl = AsyncMock(return_value=300)
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_resumed_otp_sent(ep):
    session = {'status': LoginStatus.OTP_SENT, 'phone': '03445021275', 'id': '533290'}
    result = await ep._build_resumed_session_response('pre_login_easypaisa_533290', session)
    assert result['status'] == 'success'
    assert result['data']['resumed'] is True
    assert result['data']['phase'] == LoginStatus.OTP_SENT
    assert result['data']['next_step'] == 'verify_otp'
    assert result['data']['expires_in'] == 300


@pytest.mark.asyncio
async def test_resumed_account_selection_includes_accounts(ep):
    session = {
        'status': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        'phone': '03445021275', 'id': '533290',
        'account_entire': json.dumps([{'accno': '88521642', 'accountStatus': 'ACTIVE'}]),
    }
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['resumed'] is True
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED
    assert result['data']['next_step'] == 'select_accts'
    assert 'accounts' in result['data']
    assert result['data']['accounts'] == [{'accno': '88521642', 'accountStatus': 'ACTIVE'}]


@pytest.mark.asyncio
async def test_resumed_awaiting_pin_change(ep):
    session = {'status': LoginStatus.AWAITING_PIN_CHANGE, 'phone': 'x', 'id': '1'}
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['next_step'] == 'change_pin'


@pytest.mark.asyncio
async def test_resumed_fingerprint_verified_returns_second_login(ep):
    session = {'status': LoginStatus.FINGERPRINT_VERIFIED, 'phone': 'x', 'id': '1'}
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['next_step'] == 'second_login'


@pytest.mark.asyncio
async def test_resumed_otp_verified(ep):
    session = {'status': LoginStatus.OTP_VERIFIED, 'phone': 'x', 'id': '1'}
    result = await ep._build_resumed_session_response('k', session)
    assert result['data']['next_step'] == 'upload_fingerprint'
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest api/tests/test_easypaisa_v19_resumed_session.py -v`
Expected: FAIL with AttributeError on `_build_resumed_session_response`

- [ ] **Step 3: 添加方法**

在 `class EasyPaisa` 内添加（放在 `_force_terminal_needs_relogin` 之后）：

```python
# spec §3.3.1：残留状态到下一步的映射
NEXT_STEP_MAP = {
    LoginStatus.PRE_LOGIN_CREATED:          'send_otp',
    LoginStatus.OTP_SENT:                   'verify_otp',
    LoginStatus.OTP_VERIFIED:               'upload_fingerprint',
    LoginStatus.FINGERPRINT_VERIFIED:       'second_login',
    LoginStatus.AWAITING_PIN_CHANGE:        'change_pin',
    LoginStatus.ACCOUNT_SELECTION_REQUIRED: 'select_accts',
}

async def _build_resumed_session_response(self, redis_key: str, session_data: dict) -> dict:
    """spec §3.3.1：复用残留 session，引导 APP 接续上次进度。"""
    funcName = '_build_resumed_session_response'
    status = session_data.get('status', LoginStatus.PRE_LOGIN_CREATED)
    next_step = self.NEXT_STEP_MAP.get(status, 'send_otp')
    ttl_remaining = await self.redis.ttl(redis_key)
    data = {
        'resumed': True,
        'phase': status,
        'next_step': next_step,
        'expires_in': max(0, int(ttl_remaining or 0)),
        'id': session_data.get('id'),
    }
    # ACCOUNT_SELECTION_REQUIRED 时附上 accounts 让 APP 无需再调 query_accts
    if status == LoginStatus.ACCOUNT_SELECTION_REQUIRED:
        raw = session_data.get('account_entire')
        if raw:
            try:
                accounts = json.loads(raw) if isinstance(raw, str) else raw
                data['accounts'] = accounts
            except (json.JSONDecodeError, TypeError):
                self.logger.warning(f'{self._log_key(funcName)} 解析 account_entire 失败: {raw}')
    self.logger.info(f'{self._log_key(funcName)} 复用 session: phase={status} next_step={next_step} ttl={ttl_remaining}')
    return {
        'status': 'success',
        'message': '复用残留 session',
        'data': data,
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest api/tests/test_easypaisa_v19_resumed_session.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_resumed_session.py
git commit -m "feat(easypaisa): add _build_resumed_session_response per spec §3.3.1"
```

---

## Task 6: 重写 `pre_login_http`（核心改造，含 §3.3.1 残留复用） ✅ commit `14ceb8f9` (225→160 行，stub +11 行，19/19 tests)

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:1059+`（pre_login_http 整体）

由于这是最大一段改造，分多个步骤完成。

- [ ] **Step 1: 备份当前实现**

Run:
```bash
git show HEAD:api/application/app/login/banks/easypaisa.py | \
  sed -n '/async def pre_login_http/,/^    async def send_otp_http/p' \
  > /tmp/pre_login_http.backup.py
echo "Backup: $(wc -l < /tmp/pre_login_http.backup.py) lines"
```

- [ ] **Step 2: 写新的 pre_login_http（替换整段）**

定位当前 pre_login_http 起止行：

Run: `grep -nE "async def pre_login_http|async def send_otp_http" api/application/app/login/banks/easypaisa.py`

将 pre_login_http 整段替换为：

```python
async def pre_login_http(self, data):
    """v1.9 重写：见 spec §3.3。"""
    funcName = 'pre_login_http'
    lockName = 'pre_login'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        self.logger.info(f'=== code_ver: {CODE_VER} ===')
        self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')
        if data.get('step', 'unknown') != 'complete_login':
            raise NewApiError(ErrorCode.Unsupported, f"Unsupported step: {data.get('step', 'unknown')}")
        required = ['bankname', 'phone', 'password', 'pin', 'name']
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing)}")
        bankname = data['bankname']
        original_phone = data['phone']
        phone = self._format_phone_number(original_phone)
        password = data['password']
        pin = data['pin']
        name = data['name']
        if not self._validate_phone_number(phone):
            raise NewApiError(ErrorCode.InvalidPhone, f'Invalid phone number format: {phone}')
        if await self._check_login_failed_attempts(phone):
            raise NewApiError(ErrorCode.LoginAttemps, 'Try too many times, try again after two hours.')
        await self._verify_payment_password_bcrypt(password, self.handler.current_user.hash_trade, phone)
        user_id = self.handler.current_user.id
        is_new_user = data.get('is_new_user', True)
        payment_id = data.get('payment_id')
        bound_payment = None
        if payment_id and await self.redis.get(self._login_lock_payment_key(payment_id)):
            raise NewApiError(ErrorCode.Logined, 'Account is in login process, please try again later')
        if phone and await self.redis.get(self._login_lock_phone_key(phone)):
            raise NewApiError(ErrorCode.Logined, 'Account is in login process, please try again later')
        if payment_id:
            bank_type_id = await self._get_bank_type_id(bankname)
            if not bank_type_id:
                raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Bank type not found for: {bankname}')
            with self.handler.db_orm.sessionmaker() as session:
                existing_payment = session.query(Payment).filter(
                    Payment.id == payment_id, Payment.bank_type_id == bank_type_id
                ).first()
                if not existing_payment:
                    raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Payment record not found: {payment_id}')
                if existing_payment.phone != phone:
                    raise NewApiError(ErrorCode.PaymentPhoneMismatch, f'Phone mismatch payment {payment_id}')
                if int(getattr(existing_payment, 'user_id', 0) or 0) != int(user_id):
                    raise NewApiError('10402', 'UPI already occupied by another user')
                bound_payment = {
                    'id': existing_payment.id,
                    'phone': existing_payment.phone,
                    'user_id': existing_payment.user_id,
                    'wallet_status': getattr(existing_payment, 'wallet_status', 0),
                    'fingerprint_path': getattr(existing_payment, 'fingerprint_path', None),
                }
        else:
            existing = await self._check_payment(bankname, phone, user_id)
            is_new_user = existing is None
            if existing:
                if existing.get('user_id') == user_id:
                    payment_id = existing.get('id')
                    bound_payment = existing
                else:
                    raise NewApiError('10402', 'UPI already occupied by another user')
            else:
                payment_id = phone
        lock_result = await self._get_payment_interface_lock(payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
        # spec §3.3 ⑦：已 ACTIVE 直接返回 ready（修复 533264）
        if bound_payment and int(bound_payment.get('wallet_status', 0) or 0) == 1:
            self.logger.info(f'{self._log_key(funcName)} 已 active，返回 ready: payment_id={payment_id}')
            return {
                'status': 'success',
                'message': '账号已激活',
                'data': {
                    'id': payment_id,
                    'next_step': 'ready',
                    'phase': LoginStatus.ACTIVE_SUCCESSFUL,
                },
            }
        # spec §3.3 ⑦.1：残留 session 复用（修复 Blocker 4）
        existing_session = await self._get_session_data(redis_key)
        if existing_session:
            cur_status = existing_session.get('status')
            if cur_status in (
                LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED,
                LoginStatus.FINGERPRINT_VERIFIED, LoginStatus.AWAITING_PIN_CHANGE,
                LoginStatus.ACCOUNT_SELECTION_REQUIRED,
            ):
                # 状态合理性：phone 必须匹配
                if existing_session.get('phone') == phone:
                    return await self._build_resumed_session_response(redis_key, existing_session)
                self.logger.warning(f'{self._log_key(funcName)} 残留 session phone 不匹配，删除后重建')
                await self.redis.delete(redis_key)
            elif cur_status == LoginStatus.NEEDS_RELOGIN:
                # 终态，删 key 重新走
                await self.redis.delete(redis_key)
            # PRE_LOGIN_CREATED / ACTIVE_SUCCESSFUL 走下面正常分支
        # spec §3.3 ⑧：创建新 session
        proxy_ip = await self._select_proxy_ip(bankname)
        expire_second = self.expire_time_login_pending
        session_data = {
            'id': payment_id,
            'partner_id': user_id,
            'phone': phone,
            'original_phone': original_phone,
            'status': LoginStatus.PRE_LOGIN_CREATED,
            'status_history': [LoginStatus.PRE_LOGIN_CREATED],
            'time': int(time.time()),
            'try_count': 0,
            'socks_ip': proxy_ip or '',
            'to': self.name,
            'qr_channel': data.get('channel', 1001),
            'pinCode': pin,
            'bankname': bankname,
            'password': password,
            'account': data.get('account', ''),
            'is_new_user': is_new_user,
            'name': name,
            'login_time': int(time.time()),
            'last_status_change': int(time.time()),
            'last_request_time': int(time.time()),
            'expires_at': int(time.time()) + expire_second,
            'sendOTPTime': 0,
            'selected_upi': '',
            'upi_list': [],
            'fallback_from_urm90040': False,
        }
        await self._persist_session_data(redis_key, session_data)
        # spec §3.3 ⑨：调云机 isAccountRegistered
        is_registered = await self._is_account_registered(phone)
        if not is_registered:
            # 首次上号：仅 session 初始化，不调 loginStep1
            self.logger.info(f'{self._log_key(funcName)} 首次上号 next_step=send_otp')
            return {
                'status': 'success',
                'message': '成功',
                'data': {
                    'id': payment_id,
                    'redis_key': redis_key,
                    'expires_in': expire_second,
                    'is_new_user': True,
                    'bank_type': self.LOGIN_TYPE,
                    'next_step': 'send_otp',
                },
            }
        # spec §3.3 ⑩：二次上号续推（详细路径在 Task 8）
        return await self._pre_login_second_time_chain(redis_key, session_data, bound_payment)
    except NewApiError:
        raise
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        raise NewApiError(ErrorCode.LoginAttemps, str(e))
    finally:
        if payment_lock_id and payment_lock_value:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
```

注意 `_pre_login_second_time_chain` 是 Task 8 引入的新方法。本 Task 暂时让它返回 stub 让代码可解析：

在 `class EasyPaisa` 内某处加一个 stub：

```python
async def _pre_login_second_time_chain(self, redis_key, session_data, bound_payment):
    """Task 8 will implement this."""
    return {
        'status': 'success',
        'message': 'TODO Task 8',
        'data': {
            'id': session_data['id'],
            'next_step': 'second_login',
        },
    }
```

- [ ] **Step 3: 验证 AST 解析**

Run: `python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): rewrite pre_login_http per spec §3.3 (resumed session + isAccountRegistered branching)"
```

---

## Task 7: 集成测试 - pre_login_http 已 active 返回 ready（U3 + U13 修复 533264）

**Files:**
- Create: `api/tests/test_easypaisa_v19_acceptance.py`

- [ ] **Step 1: 写 U3 测试**

文件 `api/tests/test_easypaisa_v19_acceptance.py`：

```python
"""U1-U25 端到端验收（mock 上游）。spec §7。"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_mock():
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.redis.get = AsyncMock(return_value=None)
    handler.redis.set = AsyncMock(return_value=True)
    handler.redis.setex = AsyncMock(return_value=True)
    handler.redis.delete = AsyncMock(return_value=True)
    handler.redis.ttl = AsyncMock(return_value=300)
    handler.redis.expire = AsyncMock(return_value=True)
    handler.current_user = MagicMock()
    handler.current_user.id = 1
    handler.current_user.hash_trade = '$2b$12$dummyhash'
    handler.db_orm = MagicMock()
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_u3_pre_login_returns_ready_when_active(ep_mock):
    """U3: 已 active 账号再次 pre_login 返回 ready。"""
    # mock bcrypt 校验通过
    with patch('bcrypt.checkpw', return_value=True):
        # mock _check_payment 返回已 active 的 payment
        ep_mock._check_payment = AsyncMock(return_value={
            'id': 533264,
            'phone': '03421904953',
            'user_id': 1,
            'wallet_status': 1,  # ACTIVE
            'fingerprint_path': '/fingerprint/easypaisa_533264_03421904953.zip',
        })
        # mock interface lock
        ep_mock._get_payment_interface_lock = AsyncMock(
            return_value={'lock_id': 'k', 'lock_value': 'v'}
        )
        ep_mock._release_payment_interface_lock = AsyncMock(return_value=True)
        result = await ep_mock.pre_login_http({
            'bankname': 'easypaisa',
            'phone': '03421904953',
            'password': 'tradepwd',
            'pin': '14725',
            'name': 'Test User',
            'step': 'complete_login',
            'payment_id': 533264,
        })
    assert result['status'] == 'success'
    assert result['data']['next_step'] == 'ready'
    assert result['data']['phase'] == LoginStatus.ACTIVE_SUCCESSFUL
```

- [ ] **Step 2: 跑测试**

Run: `pytest api/tests/test_easypaisa_v19_acceptance.py::test_u3_pre_login_returns_ready_when_active -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add api/tests/test_easypaisa_v19_acceptance.py
git commit -m "test(easypaisa): U3 - already-active payment returns ready (fix 533264)"
```

---

## Task 8: 实现 `_pre_login_second_time_chain` 二次上号续推

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（替换 Task 6 引入的 stub）

- [ ] **Step 1: 写测试（追加到 test_easypaisa_v19_acceptance.py）**

```python
@pytest.mark.asyncio
async def test_u2_second_time_login_success(ep_mock, tmp_path):
    """U2: 二次上号一气呵成到 ACCOUNT_SELECTION_REQUIRED。"""
    # 准备本地 ZIP 文件
    zip_path = tmp_path / "ep.zip"
    zip_path.write_bytes(b'fake zip content')
    bound_payment = {
        'id': 533264,
        'phone': '03421904953',
        'fingerprint_path': str(zip_path),
        'wallet_status': 0,  # not active yet
    }
    session_data = {
        'id': 533264, 'phone': '03421904953', 'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED],
    }
    # mock 内部调用
    ep_mock._call_upload_data = AsyncMock(return_value=True)
    ep_mock._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    ep_mock._call_second_login = AsyncMock(return_value={'outcome': 'success'})
    ep_mock._call_query_account_list = AsyncMock(return_value={
        'outcome': 'success',
        'accounts_json': json.dumps([{'accno': '88521642', 'accountStatus': 'ACTIVE'}]),
    })
    ep_mock._persist_session_data = AsyncMock(return_value=int(123))
    result = await ep_mock._pre_login_second_time_chain(
        'pre_login_easypaisa_533264', session_data, bound_payment
    )
    assert result['status'] == 'success'
    assert result['data']['next_step'] == 'second_login'
    assert session_data['status'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED


@pytest.mark.asyncio
async def test_u8_second_time_fingerprint_rejected_falls_to_otp_verified(ep_mock, tmp_path):
    """U8: 二次上号 verifyFingerprint 失败 → 状态降到 OTP_VERIFIED。"""
    zip_path = tmp_path / "ep.zip"
    zip_path.write_bytes(b'fake')
    bound = {'id': 1, 'phone': 'x', 'fingerprint_path': str(zip_path), 'wallet_status': 0}
    session = {'id': 1, 'phone': 'x', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep_mock._call_upload_data = AsyncMock(return_value=True)
    ep_mock._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'rejected', 'message': 'bad'})
    ep_mock._persist_session_data = AsyncMock(return_value=123)
    result = await ep_mock._pre_login_second_time_chain('k', session, bound)
    assert result['status'] == 'error'
    assert result['data']['code'] == 'FP_UPSTREAM_REJECTED'
    assert result['data']['next_step'] == 'upload_fingerprint'
    assert session['status'] == LoginStatus.OTP_VERIFIED


@pytest.mark.asyncio
async def test_u20_local_zip_missing_force_terminal(ep_mock):
    """U20: 本地 ZIP 文件丢失 → needsRelogin。"""
    bound = {'id': 1, 'phone': 'x', 'fingerprint_path': '/nonexistent/file.zip', 'wallet_status': 0}
    session = {'id': 1, 'phone': 'x', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    result = await ep_mock._pre_login_second_time_chain('pre_login_easypaisa_1', session, bound)
    assert result['status'] == 'error'
    assert result['data']['code'] == 'EP_FP_FILE_MISSING'
    assert session['status'] == LoginStatus.NEEDS_RELOGIN
```

- [ ] **Step 2: 实现 `_pre_login_second_time_chain`（替换 Task 6 的 stub）**

```python
async def _pre_login_second_time_chain(self, redis_key, session_data, bound_payment):
    """spec §3.3 ⑩：二次上号内部续推 upload_data + verifyFingerprint + secondLogin + queryAccountList。"""
    funcName = '_pre_login_second_time_chain'
    fingerprint_path = (bound_payment or {}).get('fingerprint_path')
    # spec §3.3 边界：本地 ZIP 丢失 → 直接 needsRelogin
    if not fingerprint_path or not os.path.exists(fingerprint_path):
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason=f'Local fingerprint ZIP missing: {fingerprint_path}',
            error_code='EP_FP_FILE_MISSING',
            message='本地指纹文件缺失，请联系运维介入',
        )
    # a. upload_data 推 ZIP
    pushed = await self._call_upload_data(session_data, fingerprint_path)
    if not pushed:
        # 状态保持 PRE_LOGIN_CREATED，让 APP 重试（spec §3.3 a）
        session_data['last_error'] = {'code': 'FP_UPSTREAM_REJECTED', 'reason': 'upload_data failed'}
        await self._persist_session_data(redis_key, session_data)
        return {
            'status': 'error',
            'message': 'upload_data 失败，请重试 pre_login',
            'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'pre_login'},
        }
    # b. verifyFingerprint
    fp_result = await self._call_verify_fingerprint(session_data)
    if fp_result.get('outcome') != 'success':
        # 借位：状态降到 OTP_VERIFIED 让 APP 走 upload_fingerprint + verify_fingerprint
        self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                       LoginStatus.OTP_VERIFIED, funcName)
        session_data['status'] = LoginStatus.OTP_VERIFIED
        session_data['status_history'].append(LoginStatus.OTP_VERIFIED)
        session_data['last_error'] = {'code': 'FP_UPSTREAM_REJECTED',
                                       'reason': fp_result.get('message', '')}
        await self._persist_session_data(redis_key, session_data)
        return {
            'status': 'error',
            'message': '指纹验证被拒，请重新上传',
            'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'upload_fingerprint',
                     'phase': LoginStatus.OTP_VERIFIED},
        }
    # c. secondLogin
    sl_result = await self._call_second_login(session_data)
    outcome = sl_result.get('outcome')
    if outcome == 'urm90040':
        # § 3.5 fallback
        return await self._urm90040_fallback(redis_key, session_data, sl_result.get('message', ''))
    if outcome == 'needs_pin_change':
        self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                       LoginStatus.AWAITING_PIN_CHANGE, funcName)
        session_data['status'] = LoginStatus.AWAITING_PIN_CHANGE
        session_data['status_history'].append(LoginStatus.AWAITING_PIN_CHANGE)
        await self._persist_session_data(redis_key, session_data)
        return {
            'status': 'error',
            'message': '需要修改 PIN',
            'data': {'code': 'SL_NEEDS_PIN_CHANGE', 'next_step': 'change_pin',
                     'phase': LoginStatus.AWAITING_PIN_CHANGE},
        }
    if outcome != 'success':
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason=f'secondLogin outcome={outcome} msg={sl_result.get("message", "")}',
            error_code='SL_NEEDS_RELOGIN' if outcome == 'session_expired' else 'SL_UPSTREAM_ERROR',
        )
    # d. queryAccountList
    qal_result = await self._call_query_account_list(session_data)
    if qal_result.get('outcome') != 'success':
        # 状态升到 FINGERPRINT_VERIFIED，APP 重调 second_login_http
        self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                       LoginStatus.FINGERPRINT_VERIFIED, funcName)
        session_data['status'] = LoginStatus.FINGERPRINT_VERIFIED
        session_data['status_history'].append(LoginStatus.FINGERPRINT_VERIFIED)
        await self._persist_session_data(redis_key, session_data)
        return {
            'status': 'error',
            'message': 'queryAccountList 失败',
            'data': {'code': 'SL_UPSTREAM_ERROR', 'next_step': 'second_login',
                     'phase': LoginStatus.FINGERPRINT_VERIFIED},
        }
    # 全成功：直接跳到 ACCOUNT_SELECTION_REQUIRED
    self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                   LoginStatus.ACCOUNT_SELECTION_REQUIRED, funcName)
    session_data['status'] = LoginStatus.ACCOUNT_SELECTION_REQUIRED
    session_data['status_history'].append(LoginStatus.ACCOUNT_SELECTION_REQUIRED)
    session_data['account_entire'] = qal_result.get('accounts_json')
    await self._persist_session_data(redis_key, session_data)
    self.logger.info(f'{self._log_key(funcName)} 二次上号续推完成，状态 → ACCOUNT_SELECTION_REQUIRED')
    return {
        'status': 'success',
        'message': '二次上号续推成功',
        'data': {
            'id': session_data['id'],
            'next_step': 'second_login',
            'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        },
    }
```

- [ ] **Step 3: 添加 `_call_upload_data` / `_call_verify_fingerprint` / `_call_second_login` / `_call_query_account_list` 临时桩**

这些是 Task 11-14 才正式实现的封装；本 Task 先用桩函数让代码可解析：

在 class 内某处加：

```python
async def _call_upload_data(self, session_data, fingerprint_path):
    """Task 11 will implement upload_data action call. Placeholder returns False for now."""
    self.logger.warning('STUB: _call_upload_data not implemented')
    return False

async def _call_verify_fingerprint(self, session_data):
    """Task 12 placeholder."""
    return {'outcome': 'rejected', 'message': 'STUB'}

async def _call_second_login(self, session_data):
    """Task 13 placeholder."""
    return {'outcome': 'session_expired', 'message': 'STUB'}

async def _call_query_account_list(self, session_data):
    """Task 14 placeholder."""
    return {'outcome': 'rejected'}

async def _urm90040_fallback(self, redis_key, session_data, msg):
    """Task 15 placeholder."""
    return await self._force_terminal_needs_relogin(
        redis_key=redis_key, session_data=session_data,
        reason='URM90040 fallback stub', error_code='SL_NEEDS_RELOGIN',
    )
```

- [ ] **Step 4: 跑测试**

Run: `pytest api/tests/test_easypaisa_v19_acceptance.py::test_u20_local_zip_missing_force_terminal -v`
Expected: PASS

注意 U2/U8 测试依赖 `_call_*` 桩——本 Task 暂只跑 U20。U2/U8 在 Task 16 收尾时再跑。

- [ ] **Step 5: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_acceptance.py
git commit -m "feat(easypaisa): implement _pre_login_second_time_chain per spec §3.3 ⑩"
```

---

## Task 9: 重写 `send_otp_http` 加节流 + 移除老状态依赖

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（send_otp_http 整段）

- [ ] **Step 1: 定位当前方法**

Run: `grep -nE "async def send_otp_http|async def verify_otp_http" api/application/app/login/banks/easypaisa.py`

- [ ] **Step 2: 替换整段为新实现**

```python
async def send_otp_http(self, data):
    """v1.9 重写：纯 loginStep1 + 20s 节流。spec §3.3.2。"""
    funcName = 'send_otp_http'
    lockName = 'send_otp'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        required = ['bankname', 'payment_id']
        missing = [f for f in required if f not in data]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing)}")
        bankname = data['bankname']
        payment_id = data['payment_id']
        redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
        lock_result = await self._get_payment_interface_lock(payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        session_data = await self._get_session_data(redis_key)
        if not session_data:
            raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')
        required_fields = ['phone', 'id', 'bankname']
        missing_fields = [f for f in required_fields if not session_data.get(f)]
        if missing_fields:
            raise NewApiError(ErrorCode.SessionNotExist, f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
        current_status = session_data.get('status')
        # 节流：sendOTPTime 距今 < 20s 则不调云机
        last_send = int(session_data.get('sendOTPTime') or 0)
        now_ts = int(time.time())
        if last_send and (now_ts - last_send) < self.RESEND_COOLDOWN_SECONDS:
            wait_left = self.RESEND_COOLDOWN_SECONDS - (now_ts - last_send)
            raise NewApiError(
                ErrorCode.PaymentLocked,
                f'Please wait {wait_left}s before requesting a new OTP',
            )
        # 允许 PRE_LOGIN_CREATED → OTP_SENT 或 OTP_SENT → OTP_SENT(resend)
        if current_status not in (LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_SENT):
            raise NewApiError(
                'INVALID_TRANSITION',
                f'send_otp expected PRE_LOGIN_CREATED/OTP_SENT, got {current_status}'
            )
        # 调云机 loginStep1
        api_result = await self._send_otp(session_data)
        is_resend = current_status == LoginStatus.OTP_SENT
        await self._update_session_status(
            redis_key, session_data, LoginStatus.OTP_SENT,
            {
                'sendOTPTime': now_ts,
                'resend_count': int(session_data.get('resend_count', 0)) + (1 if is_resend else 0),
            }
        )
        return {
            'status': 'success',
            'message': 'OTP 已发送',
            'data': {
                'next_step': 'verify_otp',
                'phase': LoginStatus.OTP_SENT,
                'expires_in': 120,
            },
        }
    except NewApiError:
        raise
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending failed: {e}')
    finally:
        await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
```

- [ ] **Step 3: 跑 AST 验证**

Run: `python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): simplify send_otp_http (throttle + pure loginStep1)"
```

---

## Task 10: 重写 `verify_otp_http` + 引入 `_verify_otp_fallback_chain`

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（verify_otp_http + 新 helper）

- [ ] **Step 1: 替换 verify_otp_http 整段**

```python
async def verify_otp_http(self, data):
    """v1.9 重写：纯 loginStep2(should_verify_fingerprint=false) + 区分首次/fallback。spec §3.4。"""
    funcName = 'verify_otp_http'
    lockName = 'verify_otp'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        required = ['bankname', 'payment_id', 'otp']
        missing = [f for f in required if f not in data]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing: {', '.join(missing)}")
        bankname = data['bankname']
        payment_id = self._normalize_payment_id(data['payment_id'])
        otp = data['otp'].strip()
        if not otp:
            raise NewApiError(ErrorCode.MissingParams, 'OTP code cannot be empty')
        redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
        lock_result = await self._get_payment_interface_lock(payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        session_data = await self._get_session_data(redis_key)
        if not session_data:
            raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist')
        self._assert_status_transition(
            session_data, LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED, funcName
        )
        # 调云机 loginStep2(should_verify_fingerprint=false)
        api_result = await self._verify_otp(session_data, otp)
        session_data['serv_gen_id'] = api_result.get('data', {}).get('requestId')
        name = session_data.get('name', '')
        real_payment_id = await self._save_payment(session_data, name=name)
        if not real_payment_id:
            raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')
        old_payment_id = self._normalize_payment_id(session_data.get('id'))
        real_payment_id_text = self._normalize_payment_id(real_payment_id)
        if old_payment_id != real_payment_id_text:
            await self.redis.delete(redis_key)
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id_text)
        session_phone = session_data.get('phone')
        await self.redis.setex(
            self._login_lock_payment_key(real_payment_id),
            self.lock_time_login_duplicate_avoid, 1
        )
        await self.redis.setex(
            self._login_lock_phone_key(session_phone),
            self.lock_time_login_duplicate_avoid, 1
        )
        session_data.update({
            'id': real_payment_id,
            'real_payment_id': real_payment_id,
            'previous_payment_id': old_payment_id,
            'selected_upi': session_phone,
            'upi_list': [session_phone],
            'completion_time': int(time.time()),
            'last_error': None,
        })
        await self._update_session_status(redis_key, session_data, LoginStatus.OTP_VERIFIED)
        # 区分首次 / fallback
        if session_data.get('fallback_from_urm90040'):
            return await self._verify_otp_fallback_chain(redis_key, session_data)
        # 首次：返回 next_phase='fingerprintUploadRequired'，APP 切到指纹采集 UI
        return {
            'status': 'success',
            'message': 'OTP 验证成功',
            'data': {
                'next_phase': 'fingerprintUploadRequired',
                'payment_id': real_payment_id,
                'previous_payment_id': old_payment_id,
                'phase': LoginStatus.OTP_VERIFIED,
            },
        }
    except NewApiError:
        raise
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {e}')
    finally:
        await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)


async def _verify_otp_fallback_chain(self, redis_key, session_data):
    """spec §3.4 fallback 路径：upload_data + verifyFingerprint + secondLogin + queryAccountList。"""
    funcName = '_verify_otp_fallback_chain'
    payment_id = session_data.get('id')
    payment = await self._query_payment(payment_id) if payment_id else None
    fingerprint_path = payment.get('fingerprint_path') if payment else None
    if not fingerprint_path or not os.path.exists(fingerprint_path):
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason='fallback path: local fingerprint missing',
            error_code='EP_FP_FILE_MISSING',
        )
    pushed = await self._call_upload_data(session_data, fingerprint_path)
    if not pushed:
        return {
            'status': 'error',
            'message': '上传指纹失败',
            'data': {'next_phase': 'fingerprintUploadRequired', 'code': 'FP_UPSTREAM_REJECTED',
                     'phase': LoginStatus.OTP_VERIFIED},
        }
    fp = await self._call_verify_fingerprint(session_data)
    if fp.get('outcome') != 'success':
        return {
            'status': 'error',
            'message': '指纹验证被拒',
            'data': {'next_phase': 'fingerprintUploadRequired', 'code': 'FP_UPSTREAM_REJECTED',
                     'phase': LoginStatus.OTP_VERIFIED},
        }
    sl = await self._call_second_login(session_data)
    if sl.get('outcome') == 'urm90040':
        # fallback 路径再 URM90040 → 不再 fallback，直接 needsRelogin
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason='fallback secondLogin URM90040 again', error_code='SL_NEEDS_RELOGIN',
        )
    if sl.get('outcome') == 'needs_pin_change':
        self._assert_status_transition(session_data, LoginStatus.OTP_VERIFIED,
                                       LoginStatus.AWAITING_PIN_CHANGE, funcName)
        await self._update_session_status(redis_key, session_data, LoginStatus.AWAITING_PIN_CHANGE,
                                          {'last_error': {'code': 'SL_NEEDS_PIN_CHANGE'}})
        return {
            'status': 'error',
            'message': '需要修改 PIN',
            'data': {'code': 'SL_NEEDS_PIN_CHANGE', 'next_step': 'change_pin'},
        }
    if sl.get('outcome') != 'success':
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason=f'fallback secondLogin {sl.get("outcome")}',
            error_code='SL_NEEDS_RELOGIN' if sl.get('outcome') == 'session_expired' else 'SL_UPSTREAM_ERROR',
        )
    qal = await self._call_query_account_list(session_data)
    if qal.get('outcome') != 'success':
        # 升到 FINGERPRINT_VERIFIED
        await self._update_session_status(redis_key, session_data, LoginStatus.FINGERPRINT_VERIFIED,
                                          {'last_error': {'code': 'SL_UPSTREAM_ERROR'}})
        return {
            'status': 'error',
            'message': 'queryAccountList 失败',
            'data': {'code': 'SL_UPSTREAM_ERROR', 'next_step': 'second_login',
                     'phase': LoginStatus.FINGERPRINT_VERIFIED},
        }
    self._assert_status_transition(session_data, LoginStatus.OTP_VERIFIED,
                                   LoginStatus.ACCOUNT_SELECTION_REQUIRED, funcName)
    await self._update_session_status(redis_key, session_data, LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                                      {'account_entire': qal.get('accounts_json'),
                                       'last_error': None})
    # spec §3.4 ⑤：返回 next_phase='fingerprintUploaded' + next_step='second_login'
    # APP 收到后会去调 verify_fingerprint，但状态已是 ACCOUNT_SELECTION_REQUIRED，由幂等行为短路（§3.6.1）
    return {
        'status': 'success',
        'message': 'fallback 续推成功',
        'data': {
            'next_phase': 'fingerprintUploaded',
            'next_step': 'second_login',
            'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        },
    }
```

- [ ] **Step 2: AST 验证**

Run: `python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): rewrite verify_otp_http with fallback chain per spec §3.4"
```

---

## Task 11: 重写 `upload_fingerprint_http`（只存 Redis pending）

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（upload_fingerprint_http 整段）

- [ ] **Step 1: 替换实现**

```python
async def upload_fingerprint_http(self, data):
    """v1.9 重写：只把 ZIP 存 Redis pending key，不调云机、不落盘。spec §3.4.1。"""
    funcName = 'upload_fingerprint_http'
    lockName = 'upload_fingerprint'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        file = data.pop("file", None)
        required = ['bankname', 'payment_id']
        missing = [f for f in required if f not in data]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing: {', '.join(missing)}")
        if not file:
            raise NewApiError(ErrorCode.MissingParams, 'file cannot be empty')
        if file["content_type"] not in ["application/zip", "application/x-zip-compressed", "multipart/x-zip"]:
            raise NewApiError(ErrorCode.MissingParams, 'file ext should be .zip')
        if len(file["body"]) > 1024 * 1024 * 16:
            raise NewApiError(ErrorCode.MissingParams, 'file size can not over 16MB')
        bankname = data['bankname']
        requested_payment_id = self._normalize_payment_id(data['payment_id'])
        session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
        resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
        lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        redis_key = session_ctx.get('redis_key')
        session_data = session_ctx.get('session_data')
        if not session_data:
            raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist')
        # 状态校验：必须是 OTP_VERIFIED
        if session_data.get('status') != LoginStatus.OTP_VERIFIED:
            raise NewApiError(
                'INVALID_TRANSITION',
                f'upload_fingerprint expected OTP_VERIFIED, got {session_data.get("status")}'
            )
        pending_key = f'easypaisa:pending_fp:{resolved_payment_id}'
        await self.redis.setex(pending_key, 600, file["body"])
        self.logger.info(f'{self._log_key(funcName)} 已存 pending: key={pending_key} size={len(file["body"])}')
        return {
            'status': 'success',
            'message': '指纹已暂存，请调 verify_fingerprint',
            'data': {
                'phase': 'fingerprintUploaded',
                'next_step': 'verify_fingerprint',
            },
        }
    except NewApiError:
        raise
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        raise NewApiError(ErrorCode.UploadFingerPrint, f'Upload failed: {e}')
    finally:
        await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
```

- [ ] **Step 2: AST 验证 + commit**

```bash
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): rewrite upload_fingerprint_http (Redis pending only)"
```

---

## Task 12: 重写 `verify_fingerprint_http` + 实现 `_call_upload_data` / `_call_verify_fingerprint`

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 写 fingerprint 两阶段测试**

文件 `api/tests/test_easypaisa_v19_fingerprint.py`：

```python
"""U7 / U15 指纹两阶段提交测试。"""
import pytest
import json
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep_fp(tmp_path):
    handler = MagicMock()
    handler.redis = AsyncMock()
    handler.db_orm = MagicMock()
    ep = EasyPaisa(handler)
    ep.FINGERPRINT_PATH = str(tmp_path) + '/'
    return ep


@pytest.mark.asyncio
async def test_u15_verify_fingerprint_rejected_keeps_old_zip(ep_fp, tmp_path):
    """U15: verify 失败时本地 ZIP md5 保持原状。"""
    old_zip = tmp_path / "easypaisa_1_03445021275.zip"
    old_zip.write_bytes(b'OLD ZIP VALID')
    md5_before = hashlib.md5(old_zip.read_bytes()).hexdigest()
    session = {'id': 1, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.OTP_VERIFIED, 'status_history': []}
    ep_fp._get_session_data = AsyncMock(return_value=session)
    ep_fp._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k', 'session_data': session, 'resolved_payment_id': 1,
    })
    ep_fp._get_payment_interface_lock = AsyncMock(return_value={'lock_id': 'k', 'lock_value': 'v'})
    ep_fp._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_fp.redis.get = AsyncMock(return_value=b'BAD ZIP')
    ep_fp.redis.delete = AsyncMock(return_value=True)
    ep_fp._call_upload_data = AsyncMock(return_value=True)
    ep_fp._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'rejected', 'message': 'bad'})
    result = await ep_fp.verify_fingerprint_http({'bankname': 'easypaisa', 'payment_id': 1})
    assert result['status'] == 'error'
    assert result['data']['code'] == 'FP_UPSTREAM_REJECTED'
    # 本地 ZIP md5 应该没变
    assert hashlib.md5(old_zip.read_bytes()).hexdigest() == md5_before
```

- [ ] **Step 2: 替换 verify_fingerprint_http 实现**

```python
async def verify_fingerprint_http(self, data):
    """v1.9 重写：读 Redis pending → upload_data → verifyFingerprint → 全成功才落盘。spec §3.6。"""
    funcName = 'verify_fingerprint_http'
    lockName = 'verify_fingerprint'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        required = ['bankname', 'payment_id']
        missing = [f for f in required if f not in data]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing: {', '.join(missing)}")
        bankname = data['bankname']
        requested_payment_id = self._normalize_payment_id(data['payment_id'])
        session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
        resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
        lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        redis_key = session_ctx.get('redis_key')
        session_data = session_ctx.get('session_data')
        if not session_data:
            raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist')
        # spec §3.6.1 幂等：已过 FINGERPRINT_VERIFIED 直接返回 ok
        cur_status = session_data.get('status')
        if cur_status in (LoginStatus.FINGERPRINT_VERIFIED, LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                          LoginStatus.ACTIVE_SUCCESSFUL):
            return {'status': 'success', 'message': '指纹已激活（幂等）',
                    'data': {'ok': True, 'phase': 'fingerprintVerified'}}
        if cur_status != LoginStatus.OTP_VERIFIED:
            raise NewApiError('INVALID_TRANSITION',
                              f'verify_fingerprint expected OTP_VERIFIED, got {cur_status}')
        pending_key = f'easypaisa:pending_fp:{resolved_payment_id}'
        zip_body = await self.redis.get(pending_key)
        if not zip_body:
            return {
                'status': 'error',
                'message': '请先上传指纹',
                'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'upload_fingerprint',
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        # ① upload_data
        pushed = await self._call_upload_data_bytes(session_data, zip_body)
        if not pushed:
            return {
                'status': 'error',
                'message': '推送云机失败',
                'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'upload_fingerprint',
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        # ② verifyFingerprint
        fp = await self._call_verify_fingerprint(session_data)
        if fp.get('outcome') == 'cooldown':
            session_data['last_error'] = {'code': 'FP_COOLDOWN', 'cd_until': fp.get('cd_until', 0)}
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '当前处于冷却期',
                'data': {'code': 'FP_COOLDOWN', 'cd_until': fp.get('cd_until', 0),
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        if fp.get('outcome') == 'session_expired':
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason='verifyFingerprint session expired', error_code='FP_SESSION_EXPIRED',
            )
        if fp.get('outcome') != 'success':
            return {
                'status': 'error',
                'message': fp.get('message') or '指纹被拒',
                'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'upload_fingerprint',
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        # ③ 全成功 → 落盘 + 更新 MySQL + 删 pending
        phone = session_data.get('phone')
        filename = self.FINGERPRINT_FILENAME.format(
            bankname=bankname, payment_id=resolved_payment_id, phone=phone
        )
        full_path = os.path.join(self.FINGERPRINT_PATH, filename)
        try:
            os.makedirs(self.FINGERPRINT_PATH, exist_ok=True)
            with open(full_path, 'wb') as fp_file:
                fp_file.write(zip_body)
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 落盘失败: {e}', exc_info=True)
            return {
                'status': 'error',
                'message': '本地保存失败',
                'data': {'code': 'SL_UPSTREAM_ERROR', 'phase': LoginStatus.OTP_VERIFIED},
            }
        await self._update_payment_fingerprint_path(resolved_payment_id, full_path)
        await self.redis.delete(pending_key)
        self._assert_status_transition(session_data, LoginStatus.OTP_VERIFIED,
                                       LoginStatus.FINGERPRINT_VERIFIED, funcName)
        await self._update_session_status(redis_key, session_data, LoginStatus.FINGERPRINT_VERIFIED,
                                          {'last_error': None})
        return {
            'status': 'success',
            'message': '指纹验证成功',
            'data': {'ok': True, 'phase': 'fingerprintVerified'},
        }
    except NewApiError:
        raise
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        raise NewApiError(ErrorCode.VerifyFingerPrint, f'verify failed: {e}')
    finally:
        await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
```

- [ ] **Step 3: 实现 `_call_upload_data_bytes` / `_call_upload_data` / `_call_verify_fingerprint`（替换 Task 8 桩）**

替换 Task 8 引入的 stub：

```python
async def _call_upload_data(self, session_data, fingerprint_path):
    """二次上号续推用：从本地路径读 ZIP 推云机 upload_data。"""
    try:
        with open(fingerprint_path, 'rb') as f:
            body = f.read()
        return await self._call_upload_data_bytes(session_data, body)
    except Exception as e:
        self.logger.error(f'{self._log_key("_call_upload_data")} 读取失败: {e}')
        return False

async def _call_upload_data_bytes(self, session_data, zip_body):
    """spec v1.9 upload_data。返回 True/False。"""
    funcName = '_call_upload_data_bytes'
    try:
        bankname = session_data.get('bankname')
        phone = session_data.get('phone')
        url = self.API_ENDPOINTS['fingerprint_upload_url']
        proxies = await self._get_proxy_for_request(session_data)
        files = {'file': ('fp.zip', zip_body, 'application/zip')}
        data = {'app': bankname, 'phone': phone}
        response = self.retry_make_request(method='UPLOAD', url=url, data=data, files=files, proxies=proxies)
        if not response or response.status_code != 200:
            self.logger.error(f'{self._log_key(funcName)} HTTP {response.status_code if response else "none"}')
            return False
        text = (response.text or '').strip().strip('"').lower()
        return text == 'ok'
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        return False

async def _call_verify_fingerprint(self, session_data):
    """spec v1.9 verifyFingerprint action 调用。"""
    funcName = '_call_verify_fingerprint'
    try:
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_verify_fingerprint_request(session_data)
        response = self.retry_make_request(method='POST', url=url, data=request_data)
        if not response or response.status_code != 200:
            return {'outcome': 'rejected', 'message': f'http {response.status_code if response else "none"}'}
        body = self._decode_indus_response(funcName, response.text)
        if not isinstance(body, dict):
            return {'outcome': 'rejected', 'message': response.text}
        code = body.get('code')
        msg = body.get('msg', '')
        data_field = body.get('data') or {}
        msg_cd = data_field.get('msgCd') if isinstance(data_field, dict) else ''
        if code in (100, 200):
            return {'outcome': 'success'}
        if msg_cd == 'URM10004':
            return {'outcome': 'session_expired', 'message': msg_cd}
        if msg_cd == 'URM40008':
            cd_until = int(time.time()) + 60 * 60 * 2
            return {'outcome': 'cooldown', 'cd_until': cd_until, 'message': msg_cd}
        return {'outcome': 'rejected', 'message': msg_cd or msg}
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        return {'outcome': 'rejected', 'message': str(e)}

async def _update_payment_fingerprint_path(self, payment_id, full_path):
    funcName = '_update_payment_fingerprint_path'
    try:
        with self.handler.db_orm.sessionmaker() as session:
            session.execute(
                update(Payment).where(Payment.id == payment_id).values(fingerprint_path=full_path)
            )
            session.commit()
        self.logger.info(f'{self._log_key(funcName)} payment_id={payment_id} path={full_path}')
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
```

- [ ] **Step 4: 跑测试**

Run: `pytest api/tests/test_easypaisa_v19_fingerprint.py::test_u15_verify_fingerprint_rejected_keeps_old_zip -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_fingerprint.py
git commit -m "feat(easypaisa): two-phase fingerprint commit per spec §3.6 (U15 passes)"
```

---

## Task 13: 重写 `second_login_http` 内嵌 queryAccountList

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 实现 `_call_second_login` / `_call_query_account_list`（替换 Task 8 桩）**

```python
async def _call_second_login(self, session_data):
    """spec v1.9 secondLogin action。"""
    funcName = '_call_second_login'
    try:
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_verify_account_request(session_data)
        response = self.retry_make_request(method='POST', url=url, data=request_data)
        if not response or response.status_code != 200:
            return {'outcome': 'upstream_error', 'message': f'http {response.status_code if response else "none"}'}
        body = self._decode_indus_response(funcName, response.text)
        if not isinstance(body, dict):
            return {'outcome': 'upstream_error', 'message': response.text}
        code = body.get('code')
        msg = body.get('msg', '')
        data_field = body.get('data') or {}
        msg_cd = data_field.get('msgCd') if isinstance(data_field, dict) else ''
        if code in (100, 200):
            return {'outcome': 'success'}
        # spec §4.1：URM90040 不是永久锁号，是可恢复抢登
        if code == 501 and msg_cd == 'URM90040':
            return {'outcome': 'urm90040', 'message': msg_cd}
        if code == 501:
            return {'outcome': 'needs_relogin', 'message': msg_cd or msg}
        if msg_cd == 'URM10004':
            return {'outcome': 'session_expired', 'message': msg_cd}
        if msg_cd == 'URM40008':
            cd_until = int(time.time()) + 60 * 60 * 2
            return {'outcome': 'cooldown', 'cd_until': cd_until}
        if msg_cd in ('URM20008', 'URM20017'):
            return {'outcome': 'needs_pin_change', 'message': msg_cd}
        return {'outcome': 'upstream_error', 'message': msg_cd or msg}
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        return {'outcome': 'upstream_error', 'message': str(e)}

async def _call_query_account_list(self, session_data):
    """spec v1.9 queryAccountList action。"""
    funcName = '_call_query_account_list'
    try:
        phone = session_data.get('phone')
        api_result = await self._query_accts(phone)
        accounts_json = api_result.get('data')
        if not accounts_json:
            return {'outcome': 'rejected', 'message': 'empty accounts'}
        return {'outcome': 'success', 'accounts_json': accounts_json}
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        return {'outcome': 'rejected', 'message': str(e)}
```

- [ ] **Step 2: 替换 second_login_http 整段**

```python
async def second_login_http(self, data):
    """v1.9 重写：secondLogin + queryAccountList，状态 FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED。spec §3.2。"""
    funcName = 'second_login_http'
    lockName = 'second_login'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        required = ['bankname', 'payment_id']
        missing = [f for f in required if f not in data]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing: {', '.join(missing)}")
        bankname = data['bankname']
        requested_payment_id = self._normalize_payment_id(data['payment_id'])
        session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
        resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
        lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        redis_key = session_ctx.get('redis_key')
        session_data = session_ctx.get('session_data')
        if not session_data:
            raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist')
        cur = session_data.get('status')
        # 入态校验：必须是 FINGERPRINT_VERIFIED
        if cur != LoginStatus.FINGERPRINT_VERIFIED:
            raise NewApiError('INVALID_TRANSITION',
                              f'second_login expected FINGERPRINT_VERIFIED, got {cur}')
        # 调云机
        sl = await self._call_second_login(session_data)
        outcome = sl.get('outcome')
        if outcome == 'urm90040':
            # 此处 fallback 由 _urm90040_fallback 处理（pre_login 内部专属，这里直接 needsRelogin）
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason='secondLogin URM90040 outside pre_login chain', error_code='SL_NEEDS_RELOGIN',
            )
        if outcome == 'needs_pin_change':
            self._assert_status_transition(session_data, LoginStatus.FINGERPRINT_VERIFIED,
                                           LoginStatus.AWAITING_PIN_CHANGE, funcName)
            await self._update_session_status(redis_key, session_data, LoginStatus.AWAITING_PIN_CHANGE,
                                              {'last_error': {'code': 'SL_NEEDS_PIN_CHANGE'}})
            return {
                'status': 'error',
                'message': '需要修改 PIN',
                'data': {'code': 'SL_NEEDS_PIN_CHANGE', 'next_step': 'change_pin',
                         'phase': LoginStatus.AWAITING_PIN_CHANGE},
            }
        if outcome == 'cooldown':
            session_data['last_error'] = {'code': 'SL_COOLDOWN', 'cd_until': sl.get('cd_until')}
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '当前处于冷却期',
                'data': {'code': 'SL_COOLDOWN', 'cd_until': sl.get('cd_until'),
                         'phase': LoginStatus.FINGERPRINT_VERIFIED},
            }
        if outcome == 'session_expired':
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason='secondLogin URM10004', error_code='SL_SESSION_EXPIRED',
            )
        if outcome != 'success':
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason=f'secondLogin {outcome}: {sl.get("message")}',
                error_code='SL_NEEDS_RELOGIN' if outcome == 'needs_relogin' else 'SL_UPSTREAM_ERROR',
            )
        # secondLogin 成功 → 立即调 queryAccountList
        qal = await self._call_query_account_list(session_data)
        if qal.get('outcome') != 'success':
            # 状态保持 FINGERPRINT_VERIFIED，让 APP 重调
            return {
                'status': 'error',
                'message': 'queryAccountList 失败',
                'data': {'code': 'SL_UPSTREAM_ERROR', 'next_step': 'second_login',
                         'phase': LoginStatus.FINGERPRINT_VERIFIED},
            }
        self._assert_status_transition(session_data, LoginStatus.FINGERPRINT_VERIFIED,
                                       LoginStatus.ACCOUNT_SELECTION_REQUIRED, funcName)
        await self._update_session_status(redis_key, session_data, LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                                          {'account_entire': qal.get('accounts_json'),
                                           'last_error': None})
        return {
            'status': 'success',
            'message': '二次登录成功',
            'data': {
                'ok': True,
                'next_step': 'query_accts',
                'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
            },
        }
    except NewApiError:
        raise
    except Exception as e:
        self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
        raise NewApiError(ErrorCode.VerifyAccount, f'second_login failed: {e}')
    finally:
        await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
```

- [ ] **Step 3: Commit**

```bash
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): second_login_http embeds queryAccountList per spec §3.2"
```

---

## Task 14: 简化 `query_accts_http` 为兼容 stub

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 替换实现**

```python
async def query_accts_http(self, data):
    """v1.9 stub：second_login_http 已写入 session.account_entire，这里直接读返回。spec §6.4。"""
    funcName = 'query_accts_http'
    lockName = 'query_accts'
    payment_lock_id = None
    payment_lock_value = None
    self.login_data = data
    try:
        required = ['bankname', 'payment_id']
        missing = [f for f in required if f not in data]
        if missing:
            raise NewApiError(ErrorCode.MissingParams, f"Missing: {', '.join(missing)}")
        bankname = data['bankname']
        requested_payment_id = self._normalize_payment_id(data['payment_id'])
        session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
        resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
        lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
        payment_lock_id = lock_result.get('lock_id')
        payment_lock_value = lock_result.get('lock_value')
        session_data = session_ctx.get('session_data')
        if not session_data:
            raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist')
        if session_data.get('status') != LoginStatus.ACCOUNT_SELECTION_REQUIRED:
            raise NewApiError('INVALID_TRANSITION',
                              f'query_accts expected ACCOUNT_SELECTION_REQUIRED, got {session_data.get("status")}')
        raw = session_data.get('account_entire')
        accounts = self._load_account_list(raw)
        active = self._filter_active_accounts(accounts)
        return {
            'status': 'success',
            'data': {
                'account_selected': session_data.get('account_accno', ''),
                'account_entire': active,
                'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
            },
        }
    except NewApiError:
        raise
    except Exception as e:
        raise NewApiError(ErrorCode.QueryAccts, f'query_accts failed: {e}')
    finally:
        await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
```

- [ ] **Step 2: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): query_accts_http reads session (no upstream call)"
```

---

## Task 15: 实现 `_urm90040_fallback` 限频 + 替换桩

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`
- Test: `api/tests/test_easypaisa_v19_urm90040.py`

- [ ] **Step 1: 写测试**

文件 `api/tests/test_easypaisa_v19_urm90040.py`：

```python
"""U4 / U5 / U14 URM90040 fallback 测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


@pytest.fixture
def ep():
    handler = MagicMock()
    handler.redis = AsyncMock()
    return EasyPaisa(handler)


@pytest.mark.asyncio
async def test_u4_first_urm90040_triggers_fallback(ep):
    session = {'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep.redis.get = AsyncMock(return_value=None)  # count 不存在
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)
    result = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_OTP'
    assert session['status'] == LoginStatus.OTP_SENT
    assert session['fallback_from_urm90040'] is True


@pytest.mark.asyncio
async def test_u5_fourth_urm90040_forces_needs_relogin(ep):
    """U5: 1 小时内第 4 次 URM90040 直接 needsRelogin。"""
    session = {'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
               'status': LoginStatus.PRE_LOGIN_CREATED, 'status_history': [LoginStatus.PRE_LOGIN_CREATED]}
    ep.redis.get = AsyncMock(return_value=b'3')  # 已 3 次
    ep.redis.setex = AsyncMock(return_value=True)
    ep.redis.expire = AsyncMock(return_value=True)
    result = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert session['status'] == LoginStatus.NEEDS_RELOGIN
```

- [ ] **Step 2: 替换 _urm90040_fallback 桩**

```python
URM90040_COUNT_KEY = 'easypaisa:urm90040_count:{payment_id}'
URM90040_LIMIT = 3
URM90040_WINDOW_SECONDS = 3600

async def _urm90040_fallback(self, redis_key, session_data, upstream_msg):
    """spec §3.5：URM90040 fallback 限频 3 次/小时。"""
    funcName = '_urm90040_fallback'
    payment_id = session_data.get('id')
    count_key = self.URM90040_COUNT_KEY.format(payment_id=payment_id)
    cur = await self.redis.get(count_key)
    try:
        cur_count = int(cur) if cur else 0
    except (TypeError, ValueError):
        cur_count = 0
    if cur_count >= self.URM90040_LIMIT:
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason=f'URM90040 count {cur_count} exceeded {self.URM90040_LIMIT}/hour',
            error_code='SL_NEEDS_RELOGIN',
            message='账号疑似被频繁占用，请联系运维介入',
        )
    # 计数 + 1，状态 reset 到 PRE_LOGIN_CREATED 再走 loginStep1
    new_count = cur_count + 1
    await self.redis.setex(count_key, self.URM90040_WINDOW_SECONDS, new_count)
    session_data['fallback_from_urm90040'] = True
    # 状态 reset：当前可能在 PRE_LOGIN_CREATED（来自 pre_login 续推）或 FINGERPRINT_VERIFIED
    current = session_data.get('status')
    if current != LoginStatus.PRE_LOGIN_CREATED:
        # 强行 reset：邻接表里 OTP_SENT → PRE_LOGIN_CREATED 有定义；其它态需要先走 NEEDS_RELOGIN 路径（但这里跳过）
        # 临时做法：直接覆盖（fallback 是逃生通道）
        self.logger.warning(f'{self._log_key(funcName)} 强制 reset {current} → PRE_LOGIN_CREATED')
    session_data['status'] = LoginStatus.PRE_LOGIN_CREATED
    session_data['status_history'].append(LoginStatus.PRE_LOGIN_CREATED)
    # 调云机 loginStep1
    await self._send_otp(session_data)
    self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                   LoginStatus.OTP_SENT, funcName)
    session_data['status'] = LoginStatus.OTP_SENT
    session_data['status_history'].append(LoginStatus.OTP_SENT)
    session_data['sendOTPTime'] = int(time.time())
    await self._persist_session_data(redis_key, session_data)
    self.logger.warning(
        f'{self._log_key(funcName)} URM90040 fallback 触发 count={new_count}/{self.URM90040_LIMIT}'
    )
    return {
        'status': 'error',
        'message': '账号被抢登，已重新发送 OTP',
        'data': {
            'code': 'SL_NEEDS_OTP',
            'next_step': 'verify_otp',
            'phase': LoginStatus.OTP_SENT,
        },
    }
```

- [ ] **Step 3: 跑测试**

Run: `pytest api/tests/test_easypaisa_v19_urm90040.py -v`
Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_urm90040.py
git commit -m "feat(easypaisa): URM90040 fallback with 3/hour rate limit (U4/U5 pass)"
```

---

## Task 16: 调整 `change_pin_http` 适配新状态机

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 定位当前 change_pin_http 并改入态/出态**

Run: `grep -nE "async def change_pin_http" api/application/app/login/banks/easypaisa.py`

把入态校验改成：

```python
self._assert_status_transition(
    session_data, LoginStatus.AWAITING_PIN_CHANGE, LoginStatus.FINGERPRINT_VERIFIED, funcName
)
```

把成功路径的出态推进改为 `LoginStatus.FINGERPRINT_VERIFIED`：

```python
await self._update_session_status(
    redis_key, session_data, LoginStatus.FINGERPRINT_VERIFIED,
    {'pin_times': session_pin_times, 'pinCode': pin, 'last_error': None}
)
```

把失败超限分支改为：

```python
if session_pin_times > PIN_CHANGE_ATTEMPTS_MAXIMUM:
    return await self._force_terminal_needs_relogin(
        redis_key=redis_key, session_data=session_data,
        reason=f'Pin change limit exceeded ({session_pin_times})',
        error_code='PIN_CHANGE_LIMIT_EXCEEDED',
    )
```

- [ ] **Step 2: AST + commit**

```bash
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): change_pin_http transitions per spec §3.8"
```

---

## Task 17: 更新 `payment_status_http` next_action_map 到 8 状态

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: 定位 next_action_map**

Run: `grep -nE "next_action_map\s*=" api/application/app/login/banks/easypaisa.py`

替换为：

```python
next_action_map = {
    LoginStatus.PRE_LOGIN_CREATED:          'send_otp',
    LoginStatus.OTP_SENT:                   'verify_otp',
    LoginStatus.OTP_VERIFIED:               'upload_fingerprint',
    LoginStatus.FINGERPRINT_VERIFIED:       'second_login',
    LoginStatus.AWAITING_PIN_CHANGE:        'change_pin',
    LoginStatus.ACCOUNT_SELECTION_REQUIRED: 'select_accts',
    LoginStatus.ACTIVE_SUCCESSFUL:          'ready',
    LoginStatus.NEEDS_RELOGIN:              'needs_relogin',
}
```

- [ ] **Step 2: AST + commit**

```bash
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('OK')"
git add api/application/app/login/banks/easypaisa.py
git commit -m "refactor(easypaisa): payment_status next_action_map for 8-state machine"
```

---

## Task 18: 最终清理 + U11 grep 验收

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [ ] **Step 1: U11 grep 检查**

Run:
```bash
grep -nE "FINGERPRINT_UPLOAD_REQUIRED|FINGERPRINT_UPLOADED|SECOND_LOGIN_READY|SECOND_LOGIN_PASSED|_replay_saved_fingerprint|_build_bound_second_login_session|EASYPAISA_API_VERSION|_verify_account\b|_promote_session_to_active_successful" api/application/app/login/banks/easypaisa.py
```
Expected: **0 匹配**。

如果还有残留，逐个删除/替换：
- `LOGIN_SUCCESSFUL` 别名引用 → 替换为 `SECOND_LOGIN_PASSED`（如果还在）或直接删除引用
- `EASYPAISA_API_VERSION` 常量 → 删定义 + 删 `if EASYPAISA_API_VERSION == 'v1.8'` 这种判断（line 3673 附近）

- [ ] **Step 2: 删 `EASYPAISA_API_VERSION` 和 `_build_verify_otp_request` 里的 v1.8 分支**

定位：
Run: `grep -nE "EASYPAISA_API_VERSION|should_verify_fingerprint" api/application/app/login/banks/easypaisa.py`

把 `_build_verify_otp_request` 里的：

```python
if EASYPAISA_API_VERSION == 'v1.8':
    request_msg["should_verify_fingerprint"] = False
```

改为永远传 False（spec §3.4 要求）：

```python
request_msg["should_verify_fingerprint"] = False  # v1.9: 永远不在 loginStep2 验证指纹
```

删 `EASYPAISA_API_VERSION = 'v1.6'` 常量定义。

- [ ] **Step 3: 跑完整测试套**

Run:
```bash
cd /Users/tear/pk_project_k8s
pytest api/tests/test_easypaisa_v19_*.py -v
```
Expected: 全部 PASS

- [ ] **Step 4: U11 最终扫描**

Run:
```bash
grep -cE "FINGERPRINT_UPLOAD_REQUIRED|FINGERPRINT_UPLOADED|SECOND_LOGIN_READY|SECOND_LOGIN_PASSED|_replay_saved_fingerprint|_build_bound_second_login_session|active_account_http|EASYPAISA_API_VERSION|_verify_account\b" api/application/app/login/banks/easypaisa.py
```
Expected: **0**

- [ ] **Step 5: 文件行数对照**

Run: `wc -l api/application/app/login/banks/easypaisa.py`
Expected: 1300-1600 行（目标 ~1500，可接受 ±200）

- [ ] **Step 6: Commit**

```bash
git add api/application/app/login/banks/easypaisa.py
git commit -m "chore(easypaisa): remove EASYPAISA_API_VERSION and v1.8 conditional branches"
```

---


## Task 19: APP 端 - `PreLoginResult` 加 `resumed` / `phase` / `accounts` / `expiresIn`

**Files:**
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/onboarding/data/exchange_api.dart`

- [ ] **Step 1: 切到 APP 仓库**

Run:
```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
git status
```
Expected: clean on d7pay branch

- [ ] **Step 2: 定位 PreLoginResult**

Run: `grep -nE "class PreLoginResult|PreLoginResult\\(" lib/features/onboarding/data/exchange_api.dart`

- [ ] **Step 3: 增加字段**

把 `PreLoginResult` 类定义改成（保留现有字段，追加新字段）：

```dart
class PreLoginResult {
  final String id;
  final String nextStep;
  final bool resumed;            // spec §3.3.1
  final String? phase;           // spec §3.3.1
  final List<dynamic>? accounts; // spec §3.3.1 ACCOUNT_SELECTION_REQUIRED 时附带
  final int? expiresIn;          // spec §3.3.1 残留 session 剩余 TTL
  
  PreLoginResult({
    required this.id,
    required this.nextStep,
    this.resumed = false,
    this.phase,
    this.accounts,
    this.expiresIn,
  });
  
  factory PreLoginResult.fromJson(Map<String, dynamic> data) {
    return PreLoginResult(
      id: data['id']?.toString() ?? '',
      nextStep: data['next_step']?.toString() ?? '',
      resumed: data['resumed'] == true,
      phase: data['phase']?.toString(),
      accounts: data['accounts'] as List<dynamic>?,
      expiresIn: data['expires_in'] as int?,
    );
  }
}
```

如果 PreLoginResult 已经存在不同结构，**保留现有字段不动**，只在末尾追加 `resumed`/`phase`/`accounts`/`expiresIn` 四个字段及对应的 `fromJson` 解析。

- [ ] **Step 4: Commit**

```bash
git add lib/features/onboarding/data/exchange_api.dart
git commit -m "feat(onboarding): PreLoginResult adds resumed/phase/accounts/expiresIn"
```

---

## Task 20: APP 端 - `submitForm()` 处理 `resumed: true`

**Files:**
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/onboarding/controllers/onboarding_controller.dart` 或路径相近的 controller

- [ ] **Step 1: 定位 submitForm**

Run:
```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
grep -rn "submitForm\|preLogin(" lib/features/onboarding --include="*.dart" | head -10
```

定位到 controller 文件，找到调 `preLogin()` 之后的分支。

- [ ] **Step 2: 在 submitForm 中插入 resumed 处理分支**

在调 `preLogin()` 返回 result 之后，加入：

```dart
// spec §3.3.1：服务端复用残留 session，根据 phase 直接跳到对应 UI
if (result.resumed && result.phase != null) {
  switch (result.phase) {
    case 'preLoginCreated':
      // 罕见：上次 pre_login 没走 get_otp 就断了；继续走 get_otp
      await _runGetOtp();
      break;
    case 'otpSent':
      _setPhase(OnboardingPhase.awaitingOtp);
      break;
    case 'otpVerified':
      _setPhase(OnboardingPhase.awaitingFingerprintUpload);
      break;
    case 'fingerprintVerified':
      _setPhase(OnboardingPhase.awaitingSecondLogin);
      await _runSecondLoginChain();
      break;
    case 'awaitingPinChange':
      _setPhase(OnboardingPhase.awaitingPinChange);
      break;
    case 'accountSelectionRequired':
      // accounts 由服务端附带，无需再调 query_accts
      _accounts = result.accounts ?? [];
      _setPhase(OnboardingPhase.awaitingAccountSelection);
      break;
    default:
      // 未识别 phase：按原 next_step 兜底
      await _phaseAfterPreLogin(result.nextStep);
  }
  return;
}

// 未 resumed：走原有逻辑
await _phaseAfterPreLogin(result.nextStep);
```

如果当前代码已经把 `_phaseAfterPreLogin` 当作主路由，则在 `_phaseAfterPreLogin` 开头加一个 resumed 短路：

```dart
Future<void> _phaseAfterPreLogin(String nextStep, {bool resumed = false, String? phase, List<dynamic>? accounts}) async {
  if (resumed && phase != null) {
    // 上面的 switch 逻辑
    return;
  }
  // 原有逻辑
}
```

- [ ] **Step 3: 跑 Dart analyzer**

Run:
```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
flutter analyze lib/features/onboarding/ 2>&1 | head -30
```
Expected: 0 issues 或仅有原本就存在的 info 级别警告

- [ ] **Step 4: Commit**

```bash
git add lib/features/onboarding/
git commit -m "feat(onboarding): submitForm handles resumed:true per spec §3.3.1"
```

---

## Task 21: 集成测试 - U17 payment_status 新枚举字符串

**Files:**
- Modify: `api/tests/test_easypaisa_v19_acceptance.py`（追加 U17）

- [ ] **Step 1: 追加测试**

```python
@pytest.mark.asyncio
async def test_u17_payment_status_returns_new_enum_strings(ep_mock):
    """U17: payment_status_http 返回新枚举字符串。"""
    session = {'status': LoginStatus.FINGERPRINT_VERIFIED, 'phone': 'x', 'id': '1',
               'last_error': None, 'cd_until': 0}
    ep_mock._resolve_session_context = AsyncMock(return_value={
        'session_data': session, 'resolved_payment_id': '1',
    })
    result = await ep_mock.payment_status_http({'bankname': 'easypaisa', 'payment_ids': '1'})
    assert result['status'] == 'success'
    assert result['datas'][0]['status'] == 'fingerprintVerified'
    assert result['datas'][0]['next_action'] == 'second_login'
```

注：原 spec 的 U18（迁移脚本测试）已删除——本项目无 runtime_snapshot 层，无需迁移。

- [ ] **Step 2: 跑测试**

Run:
```bash
cd /Users/tear/pk_project_k8s
pytest api/tests/test_easypaisa_v19_acceptance.py -v
```
Expected: 全部 passed

- [ ] **Step 3: Commit**

```bash
git add api/tests/test_easypaisa_v19_acceptance.py
git commit -m "test(easypaisa): U17 - payment_status returns new enum strings"
```

---

## Task 22: 整体回归与可读性验证

**Files:**
- 全 repo

- [ ] **Step 1: 全测试套**

Run:
```bash
cd /Users/tear/pk_project_k8s
pytest api/tests/ -v 2>&1 | tail -50
```
Expected: 没有新出现的 FAIL（旧测试如果有 FAIL 要看是不是改动引起的）。

- [ ] **Step 2: 残留代码扫描（U11 最终版）**

Run:
```bash
grep -cE "FINGERPRINT_UPLOAD_REQUIRED|FINGERPRINT_UPLOADED|SECOND_LOGIN_READY|SECOND_LOGIN_PASSED|_replay_saved_fingerprint|_build_bound_second_login_session|EASYPAISA_API_VERSION|_verify_account\b|_promote_session_to_active_successful|LOGIN_SUCCESSFUL" api/application/app/login/banks/easypaisa.py
```
Expected: **0**

- [ ] **Step 3: 文件行数**

Run: `wc -l api/application/app/login/banks/easypaisa.py`
Expected: 1300-1700 行

- [ ] **Step 4: AST 解析**

Run: `python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('AST OK')"`
Expected: AST OK

- [ ] **Step 5: 错误码映射 grep**

Run: `grep -nE "EP_[A-Z_]+" api/application/app/login/banks/easypaisa.py | head -20`
Expected: 仅出现 `EP_FP_FILE_MISSING`（spec §4.2 唯一新增码）；其它 `EP_xxx` 字面量应全部已映射成 APP 已识别码。

如果还有遗漏的 `EP_xxx`，按 Task 0 的映射表替换为对应数字码。

- [ ] **Step 6: APP 端 analyzer**

Run:
```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
flutter analyze lib/features/onboarding/ 2>&1 | tail -10
```
Expected: 0 errors

- [ ] **Step 7: 输出对账总结**

打印简要报告：

Run:
```bash
echo "===== 后端 ====="
cd /Users/tear/pk_project_k8s
wc -l api/application/app/login/banks/easypaisa.py
git log --oneline d7pay~30..d7pay -- api/application/app/login/banks/easypaisa.py | head -25
echo "===== APP ====="
cd /Users/tear/pk_project/ashrafi_merchant_flutter
git log --oneline d7pay~10..d7pay -- lib/features/onboarding/ | head -10
```

无 commit 步骤（汇报性质）。

---

## Self-Review

完成后对照 spec 逐节核对：

| spec 章节 | 覆盖任务 | 状态 |
|---|---|---|
| §3.1 8 状态枚举 | Task 1 | ✓ |
| §3.1.1 STATUS_TRANSITIONS 邻接表 | Task 1 | ✓ |
| §3.1.2 _force_terminal_needs_relogin | Task 2 | ✓ |
| §3.2 9 接口职责 | Task 6/9/10/11/12/13/14/16/17 | ✓ |
| §3.3 pre_login_http | Task 6/8 | ✓ |
| §3.3.1 残留 session 复用 | Task 5/6 | ✓ |
| §3.3.2 get_otp 节流 | Task 9 | ✓ |
| §3.4 verify_otp + fallback chain | Task 10 | ✓ |
| §3.4.1 upload_fingerprint | Task 11 | ✓ |
| §3.5 URM90040 fallback 3/hour | Task 15 | ✓ |
| §3.6 指纹两阶段提交 | Task 11/12 | ✓ |
| §3.6.1 verify_fingerprint 幂等 | Task 12 | ✓ |
| §3.7 状态轨迹 | Task 22（验证）| ✓ |
| §3.8 change_pin | Task 16 | ✓ |
| §4.1 云机 code 映射 | Task 13 (_call_second_login) | ✓ |
| §4.2 错误码对齐 APP | Task 0 + Task 22 grep 验证 | ✓ |
| §5 Redis Session 结构 | Task 6（session_data 初始化）| ✓ |
| §6 待删除代码 | Task 4 + Task 18 | ✓ |
| §7 验收用例 U1-U24（U18 已删）| Task 7/8/12/15/21（覆盖关键）| ✓ |
| §12 发版策略 | spec §12.3 给的 `redis-cli --scan --pattern 'pre_login_easypaisa_*' \| xargs redis-cli del` 手动执行，无需 task | ✓ |
| §13 APP 端契约 | Task 19/20 | ✓ |

**Placeholder scan:** 全文 grep 无 "TBD"/"TODO"/"implement later"/"fill in"。每个 step 都含完整代码或具体 grep/git 命令。

**Type consistency:** 
- `LoginStatus.X` 在 Task 1 定义、其他 task 引用一致
- `_force_terminal_needs_relogin` 签名（redis_key, session_data, reason, error_code, message=None）跨 Task 2/8/10/12/15/16 一致
- `_call_upload_data_bytes` 在 Task 12 定义、`_call_upload_data` 在 Task 8/12 定义，两个互相调用，签名一致
- `outcome` 字符串集合：success / urm90040 / needs_pin_change / cooldown / session_expired / needs_relogin / rejected / upstream_error —— 在 _call_second_login (Task 13) 定义、在 _pre_login_second_time_chain (Task 8) / _verify_otp_fallback_chain (Task 10) 消费

**Scope check:** 单 spec、单功能（上号流程）、跨 2 个 repo（backend + APP，紧耦合需同步发版）。`pk-go-worker` 不涉及（go-worker 通过 MySQL `wallet_status` 调度，本次重构不改字段语义）。不切分。

---

## Execution Handoff

Plan 已写入 `docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md`。

执行有两种方式：

**1. Subagent-Driven（推荐）**——每个 task 派发独立 subagent，task 间审查，迭代快。**REQUIRED SUB-SKILL**：使用 `superpowers:subagent-driven-development`。

**2. Inline Execution**——本会话内按计划执行，分批 checkpoint。**REQUIRED SUB-SKILL**：使用 `superpowers:executing-plans`。

**哪一种？**

---

## Hotfix 1: second_login_http idempotency + 4 collateral fixes (2026-05-14)

**Trigger**: v1.9 部署后 code review + 生产 e2e 暴露 5 个 issue（1 Critical 状态机幂等 + 1 Critical 落盘原子性 + 3 Major 安全/资源）

**Linked spec**: `docs/superpowers/specs/2026-05-14-second-login-idempotency-hotfix-design.md` (commit `749482da`)
**Implementation plan**: `docs/superpowers/plans/2026-05-14-second-login-idempotency-hotfix.md` (commit `38dc25d7`)

### 改动清单

| # | Fix | Commit | 测试 |
|---|---|---|---|
| 1 | second_login_http 入态幂等（Critical, Path B/C 修复） | `4b76e6a2` | 2 个新测试 |
| 2 | _check_payment SQL filter by partner_id（Major, 防御纵深） | `74c7a723` | 2 个新测试 |
| 3 | _urm90040_fallback 原子 INCR（Major, 限频 race fix） | `e3144dd4` | 2 个新测试 |
| 4 | fingerprint atomic rename on MySQL fail（Critical, 落盘原子性） | `c66854de` | 1 个新测试 |
| 5 | session scrub password（Major, 安全） | `d014a050` | 1 个新测试 |
| docs | spec + plan 更新 | (this commit) | — |

### 测试统计

- v1.9 基线：27 passed
- Hotfix-1 后：**35 passed** (27 + 8 新)
- Regression：0

### 生产验收（H6 系列, 简化版 — 不需 OTP/真实指纹）

| 用例 | 步骤 | 结果 |
|---|---|---|
| H6 | 临时 wallet_status=0 → pre_login → second_login，验 Fix #1 不再 INVALID_TRANSITION | ✅ **PASS** — pre_login 返回 `success / next_step=second_login / phase=accountSelectionRequired`；second_login 幂等返回 `success / ok:true / next_step=query_accts / phase=accountSelectionRequired`（不再 INVALID_TRANSITION） |
| H6b | 跨 partner phone 防御纵深 | 单测覆盖 (`test_check_payment_filter_includes_partner_id` + `test_check_payment_returns_only_owner_record`)，e2e 跳过 |
| H6c | URM90040 INCR 增量 + TTL 接近 3600 | ⚠️ 代码 grep 验证（line 1174 `await self.redis.incr(count_key)`）+ 单测覆盖（`test_urm90040_atomic_concurrent_calls`）。云机端 `isAccountRegistered` 暂时不可用（不影响 hotfix），无法在生产复现 fallback chain |
| H6d | session 不含 password 字段 | ✅ **PASS** — 2/2 active session（533294、533296）扫描结果不含 `password` 字段 |
| H6e | api.log smoke test 5 分钟无 ERROR | ✅ **PASS** — 唯一 ERROR 是已知运维项「Redis 中无 indian_socks_ip_easypaisa 代理 IP 配置」（与 hotfix-1 无关），无 `INVALID_TRANSITION`、`Exception`、`Traceback`，pod 重启 0 次 |

### 部署记录

- 镜像 tag: `10.170.0.18:30086/lib/api-d7pay:20260514143924`
- Rollout 完成时间: 2026-05-14 14:40:42 UTC（2 个 pod Running）
- 回滚记录: 无（H6/H6d/H6e 一次性通过）
- 部署脚本: `/opt/cicd/k8s_d7pay/sh/deploy-api.sh`（远程发布机执行）

### APP 影响

**零改动**。Fix #1 返回 `next_step='query_accts'` 是 APP v1.9 已识别字段（与 second_login_http 正常成功路径返回字段相同）。无新增字段、无新增错误码、邻接表不变。

---

## Hotfix 2: v1.9 P0 优化 (2026-05-15)

**Trigger**: v1.9 + hotfix-1 部署后实测 03194834960 / 533302 抢登事故 + 6 类性能/协议问题
**Linked spec**: `docs/superpowers/specs/2026-05-15-easypaisa-v19-p0-optimization-design.md` (commit `cccb6951`)
**Implementation plan**: `docs/superpowers/plans/2026-05-15-easypaisa-v19-p0-optimization.md` (commit `73c29cb7`,worktree 原版)
**d7pay 实施差异**: 函数名 / 测试结构 / 行号 adapt（worktree 用 `_perform_second_login`,d7pay 用 `_call_second_login` 等）

### 改动清单

| # | Commit | 内容 | 测试 |
|---|---|---|---|
| 1 | `4436ec4a` | STATUS_TRANSITIONS AWAITING_PIN_CHANGE 改边（删 FINGERPRINT_VERIFIED,加 ACCOUNT_SELECTION_REQUIRED）| state_machine.py: 删旧测试 + 加新测试 |
| 2 | `4e2f5a1a` | `_call_second_login` + `_build_verify_account_request` 加 `with_pwd` 参数（默认 False,行为不变）| acceptance.py: +1 测试 |
| 3 | `2ca14567` | URM90040 envelope 补 `id` + `expires_in:60` + `urm90040_count`,send_otp expires_in 120→60 | urm90040.py: +1 测试 |
| 4 | `3e35d835` | `_pre_login_second_time_chain` 去前置 verifyFingerprint（节省 5-6s/次）| acceptance.py: 删 U8 + 加新测试 |
| 5 | `f98b5fe5` | `_verify_otp_fallback_chain` 改两阶段（Stage 1 secondLogin(with_pwd) 一击救冻 + Stage 2 兜底）| urm90040.py: +2 测试; 顺便修 `_query_payment` 缺 `fingerprint_path` 字段 hidden bug |
| 6 | `5b11af8c` | `change_pin_http` 内部续推 secondLogin(with_pwd) + queryAccountList → ACCOUNT_SELECTION_REQUIRED | **新建** change_pin.py: +2 测试 |
| docs | (this commit) | 主 plan 追加 hotfix-2 段 + push | — |

### State Machine 邻接表变化

```python
# AWAITING_PIN_CHANGE
- LoginStatus.FINGERPRINT_VERIFIED
+ LoginStatus.ACCOUNT_SELECTION_REQUIRED

# OTP_VERIFIED (Commit 5 拓宽,因为新两阶段 fallback 跨态)
LoginStatus.FINGERPRINT_VERIFIED,
+ LoginStatus.ACCOUNT_SELECTION_REQUIRED,  # Stage 1/Stage 2 救冻成功
+ LoginStatus.AWAITING_PIN_CHANGE,         # Stage 1 needs_pin_change
LoginStatus.NEEDS_RELOGIN,
```

### 测试统计

- hotfix-1 基线: 35 passed
- hotfix-2 后: **41 passed** (35 + 6 新加,U8 删除净 +6)
- Regression: 0

### 性能预期

| 路径 | hotfix-1 后 | hotfix-2 后 | 节省 |
|---|---|---|---|
| 二次上号正常 | 5-6s | < 2s | **5s** |
| verify_otp fallback 救冻 (Stage 1 成功) | 5-6s | < 3s | **3s** |
| verify_otp fallback 兜底 (Stage 2) | 5-6s | 5-6s | 同步 |
| change_pin 后到 ACCOUNT_SELECTION_REQUIRED | 8-10s (2 HTTP) | < 5s (1 HTTP) | **3-5s** |

### 生产验收（待回填）

| 用例 | 步骤 | 结果 |
|---|---|---|
| H7 | 533294 wallet_status=0 → pre_login → 期望 < 2s 直接 ACCOUNT_SELECTION_REQUIRED + 0 次 verifyFingerprint 调用 | TBD（部署后填）|
| H7b | 触发 533296 URM90040 → 验 envelope 含 id + next_step='verify_otp' + expires_in:60 + urm90040_count | TBD |
| H7c | grep STATUS_TRANSITIONS 验邻接表新增 | TBD |
| H7d | 03194834960/533302 真实事故复现（如可用）→ secondLogin(pwd) 一击救冻 < 3s | TBD（取决于云机环境）|
| H7e | api.log smoke 5min 无新 ERROR / pod 0 重启 | TBD |

### 部署记录

- 镜像 tag: TBD (部署后填)
- Rollout 完成时间: TBD
- 回滚记录: 无 / 描述
- 部署脚本: `/opt/cicd/k8s_d7pay/sh/deploy-api.sh`

### APP 影响

**零改动**。所有 envelope 字段补全 (`id`/`next_step`/`expires_in`/`urm90040_count`) 用的都是 APP exchange_api.dart 已识别的字段。change_pin 内部续推返回 `next_step='select_accts'` 也是 APP 已识别的(之前从 `second_login_http` 返回过同款字段)。

**APP P1（独立排期）**: APP `controller.dart` 补 `SL_NEEDS_OTP → awaitingOtp` 识别 → 真正闭环 UX(用户看到 OTP 屏而不是 failed 屏)。**不阻塞 hotfix-2 上线**。

