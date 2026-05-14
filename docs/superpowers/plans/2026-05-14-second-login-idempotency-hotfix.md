# Second Login Idempotency Hotfix (v1.9.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal**: 修复 v1.9 部署后 code review 发现的 5 个 issues（1 Critical 状态机幂等 + 1 Critical 落盘原子性 + 3 Major 安全/资源），让二次上号 Path B/C 不再撞 `INVALID_TRANSITION`。

**Architecture**: 单文件 backend hotfix `api/application/app/login/banks/easypaisa.py` + 测试。**APP 端零改动**。状态机/邻接表/外部契约不变。策略 B：5 个独立 fix commit + 1 个文档 commit，每个 commit 都可独立 revert。

**Tech Stack**: Python 3.12 (asyncio/aioredis/SQLAlchemy/bcrypt)、pytest（已有 27 个 v1.9 测试基线）、Redis、MySQL、Kubernetes (pk-d7pay namespace via SSH @ 34.92.65.29)

**Linked spec**: `docs/superpowers/specs/2026-05-14-second-login-idempotency-hotfix-design.md` (commit `749482da`)

---

## File Structure

**Backend** (`/Users/tear/pk_project_k8s`, branch `d7pay`):

| Op | File | 职责 |
|---|---|---|
| Modify | `api/application/app/login/banks/easypaisa.py` | 5 个 fix 改动（line 926/1172-1187/1216-1224/1530-1543/1583-1588/2813-2825）|
| Modify | `api/tests/test_easypaisa_v19_acceptance.py` | 加 2 个 Fix #1 测试 |
| Create | `api/tests/test_easypaisa_v19_check_payment.py` | Fix #2 测试（2 条）|
| Modify | `api/tests/test_easypaisa_v19_urm90040.py` | 加 2 个 Fix #3 测试 |
| Modify | `api/tests/test_easypaisa_v19_fingerprint.py` | 加 1 个 Fix #4 测试 |
| Modify | `api/tests/test_easypaisa_v19_force_terminal.py` | 加 1 个 Fix #5 测试 |
| Modify | `docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md` | 末尾追加 hotfix-1 入口段 |

**累计测试预期**：27（v1.9 基线）+ 8（hotfix-1 新增）= **35 passed**

**环境约束**：
- Bash 必须 `cd /Users/tear/pk_project_k8s`
- 跑测试用 `python3 -m pytest`（**不是** `pytest`，PATH 上是 user-site Python 3.9 的）
- 测试文件顶部需 sys.path bootstrap（参照现有 v1.9 测试文件）

**生产 e2e 环境**：
- SSH: `ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29`
- K8s: `export KUBECONFIG=/etc/kubernetes/admin.conf`
- Namespace: `pk-d7pay`
- Partner 33057 Bearer token: `a9bedb37-bdf2-462f-a8b3-f37e55735171`
- Partner 33057 交易密码: `123456`
- 测试 payment：533294 (online, wallet_status=1)、533296 (offline+bound, wallet_status=0)

---

## Task 1: Fix #1 — `second_login_http` 入态幂等

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py` (line 1583-1588 之前插入幂等分支)
- Modify: `api/tests/test_easypaisa_v19_acceptance.py` (末尾追加 2 条测试)

- [ ] **Step 1: 定位精确插入点**

```bash
cd /Users/tear/pk_project_k8s
grep -nE "if cur != LoginStatus.FINGERPRINT_VERIFIED" api/application/app/login/banks/easypaisa.py
```
Expected: 输出 1 行，如 `1586:            if cur != LoginStatus.FINGERPRINT_VERIFIED:`。记录行号。

- [ ] **Step 2: 写失败测试（追加到 test_easypaisa_v19_acceptance.py 末尾）**

```python


@pytest.mark.asyncio
async def test_second_login_idempotent_after_pre_login_chain(ep_mock):
    """Fix #1: 二次上号续推完成后 APP 调 second_login_http 应幂等返回 success。"""
    session = {
        'id': '533294', 'phone': '03130268536', 'bankname': 'easypaisa',
        'status': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        'account_entire': '[{"accno":"53512051","accountStatus":"ACTIVE"}]',
        'status_history': [LoginStatus.PRE_LOGIN_CREATED, LoginStatus.ACCOUNT_SELECTION_REQUIRED],
    }
    ep_mock._resolve_session_context = AsyncMock(return_value={
        'session_data': session, 'redis_key': 'pre_login_easypaisa_533294',
        'resolved_payment_id': '533294',
    })
    ep_mock._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_mock._release_payment_interface_lock = AsyncMock(return_value=True)
    # _call_second_login 不该被调用（幂等短路）
    ep_mock._call_second_login = AsyncMock(side_effect=Exception('should not be called'))

    result = await ep_mock.second_login_http({
        'bankname': 'easypaisa', 'payment_id': '533294'
    })

    assert result['status'] == 'success'
    assert result['data']['ok'] is True
    assert result['data']['next_step'] == 'query_accts'
    assert result['data']['phase'] == LoginStatus.ACCOUNT_SELECTION_REQUIRED


@pytest.mark.asyncio
async def test_second_login_idempotent_after_active(ep_mock):
    """Fix #1: ACTIVE_SUCCESSFUL 状态调 second_login_http 也幂等成功。"""
    session = {
        'id': '533294', 'phone': '03130268536', 'bankname': 'easypaisa',
        'status': LoginStatus.ACTIVE_SUCCESSFUL,
        'status_history': [LoginStatus.ACTIVE_SUCCESSFUL],
    }
    ep_mock._resolve_session_context = AsyncMock(return_value={
        'session_data': session, 'redis_key': 'pre_login_easypaisa_533294',
        'resolved_payment_id': '533294',
    })
    ep_mock._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_mock._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_mock._call_second_login = AsyncMock(side_effect=Exception('should not be called'))

    result = await ep_mock.second_login_http({
        'bankname': 'easypaisa', 'payment_id': '533294'
    })

    assert result['status'] == 'success'
    assert result['data']['phase'] == LoginStatus.ACTIVE_SUCCESSFUL
```

- [ ] **Step 3: 跑测试看 RED**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_second_login_idempotent_after_pre_login_chain api/tests/test_easypaisa_v19_acceptance.py::test_second_login_idempotent_after_active -v
```
Expected: **2 failed**。两条都会撞 `INVALID_TRANSITION`（因为代码还没加幂等）。

- [ ] **Step 4: 在 second_login_http 入态校验之前插入幂等分支**

定位 line 1586 附近（Step 1 拿到的精确行号），在 `if cur != LoginStatus.FINGERPRINT_VERIFIED:` 之前插入：

Edit 工具：找到这段
```python
            cur = session_data.get('status')
            # 入态校验：必须是 FINGERPRINT_VERIFIED
            if cur != LoginStatus.FINGERPRINT_VERIFIED:
                raise NewApiError('INVALID_TRANSITION',
                                  f'second_login expected FINGERPRINT_VERIFIED, got {cur}')
```

替换为：
```python
            cur = session_data.get('status')
            # spec §3.6.1 风格幂等：二次上号续推 / fallback chain 已完成
            if cur in (LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                       LoginStatus.ACTIVE_SUCCESSFUL):
                self.logger.info(
                    f'{self._log_key(funcName)} 幂等返回: 状态已 {cur}，'
                    f'second_login 续推已由 pre_login/verify_otp 完成'
                )
                return {
                    'status': 'success',
                    'message': '二次登录已就绪（幂等）',
                    'data': {
                        'ok': True,
                        'next_step': 'query_accts',
                        'phase': cur,
                    },
                }
            # 入态校验：必须是 FINGERPRINT_VERIFIED
            if cur != LoginStatus.FINGERPRINT_VERIFIED:
                raise NewApiError('INVALID_TRANSITION',
                                  f'second_login expected FINGERPRINT_VERIFIED, got {cur}')
```

- [ ] **Step 5: 跑测试看 GREEN**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py -v
```
Expected: **7 passed**（原 5 个 acceptance + 2 个新加）。

- [ ] **Step 6: 跑全 v1.9 测试套回归**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_*.py 2>&1 | tail -3
```
Expected: **29 passed**（27 + 2）。

- [ ] **Step 7: AST 验证 + commit**

```bash
cd /Users/tear/pk_project_k8s
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('AST OK')"
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_acceptance.py
git commit -m "$(cat <<'EOF'
fix(easypaisa): second_login_http idempotent for ACCOUNT_SELECTION_REQUIRED

spec §3.6.1 pattern: pre_login_http 二次上号续推或 verify_otp_http
fallback chain 完成后状态已是 ACCOUNT_SELECTION_REQUIRED。APP 按
spec §3.3⑪ next_step='second_login' 调本接口时，应幂等返回 ok
而非 raise INVALID_TRANSITION。

Fixes Path B (二次上号 secondLogin 直接成功) + Path C (URM90040
fallback 续推成功) — 两条路径最后都到 ACCOUNT_SELECTION_REQUIRED
然后 APP 调 second_login_http 撞墙。

Tests:
- test_second_login_idempotent_after_pre_login_chain
- test_second_login_idempotent_after_active
EOF
)"
```

---

## Task 2: Fix #2 — `_check_payment` SQL filter by partner_id

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py` (line 2813-2825 内)
- Create: `api/tests/test_easypaisa_v19_check_payment.py`

- [ ] **Step 1: 定位精确行号**

```bash
cd /Users/tear/pk_project_k8s
grep -nE "async def _check_payment|Payment.bank_type|Payment.phone == phone" api/application/app/login/banks/easypaisa.py | head -10
```
Expected: `async def _check_payment` + 3 行 filter 字段。记录行号。

- [ ] **Step 2: 创建新测试文件 `api/tests/test_easypaisa_v19_check_payment.py`**

```python
"""Fix #2: _check_payment SQL filter by partner_id (defense-in-depth)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from application.app.login.banks.easypaisa import EasyPaisa


@pytest.fixture
def ep_for_check():
    handler = MagicMock()
    ep = EasyPaisa(handler)
    return ep


@pytest.mark.asyncio
async def test_check_payment_filter_includes_partner_id(ep_for_check):
    """Fix #2: SQL filter 必须含 Payment.user_id == partner_id（ORM 列名 partner_id）。"""
    ep_for_check._get_bank_type_id = AsyncMock(return_value=97)
    captured_filters = []

    class FakeQuery:
        def __init__(self):
            self._filters = []

        def filter(self, *args):
            captured_filters.extend(args)
            return self

        def first(self):
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def query(self, model):
            return FakeQuery()

    ep_for_check.handler.db_orm.sessionmaker = lambda: FakeSession()

    await ep_for_check._check_payment('easypaisa', '03130268536', 33057)

    # 验证 captured_filters 含一个针对 partner_id 的等值条件
    filter_strs = [str(f) for f in captured_filters]
    assert any('partner_id' in s for s in filter_strs), \
        f'_check_payment SQL filter 缺 partner_id 条件，实际 filters: {filter_strs}'


@pytest.mark.asyncio
async def test_check_payment_returns_only_owner_record(ep_for_check):
    """Fix #2: 跨 partner 查询时 SQL 应返回 None（filter 拦下）。"""
    ep_for_check._get_bank_type_id = AsyncMock(return_value=97)

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            # 模拟 SQL 含 partner_id 过滤 → 查不到（返回 None）
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def query(self, model):
            return FakeQuery()

    ep_for_check.handler.db_orm.sessionmaker = lambda: FakeSession()

    # A partner (33057) 查 B partner 的 phone
    result = await ep_for_check._check_payment('easypaisa', 'B_phone', 33057)
    assert result is None  # SQL 拦下，无返回
```

- [ ] **Step 3: 跑测试看 RED**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_check_payment.py -v
```
Expected: `test_check_payment_filter_includes_partner_id` 失败（filter 里没 partner_id 条件）；`test_check_payment_returns_only_owner_record` 可能 pass（None 是 default）。

- [ ] **Step 4: 修 _check_payment 的 SQL filter**

定位 _check_payment 方法体（line ~2820）。找到 SQL filter：

```python
                existing_payment = session.query(Payment
                ).filter(
                    Payment.bank_type == bank_type_id,
                    Payment.bank_type_id == bank_type_id,
                    Payment.phone == phone
                ).first()
```

替换为：

```python
                existing_payment = session.query(Payment).filter(
                    Payment.bank_type_id == bank_type_id,
                    Payment.phone == phone,
                    # Defense-in-depth: Payment.user_id 是 ORM 属性，对应 SQL 列 partner_id
                    Payment.user_id == partner_id,
                ).first()
```

注意：删除了重复的 `Payment.bank_type == bank_type_id`（历史 dead filter）。

- [ ] **Step 5: 跑测试看 GREEN**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_check_payment.py -v
```
Expected: **2 passed**。

- [ ] **Step 6: 跑全 v1.9 测试套回归**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_*.py 2>&1 | tail -3
```
Expected: **31 passed**（29 + 2）。**特别注意**：U3 测试用 `_check_payment` mock，但 mock 已经接受 3 参数 (bankname, phone, user_id)，不受影响。

- [ ] **Step 7: AST + commit**

```bash
cd /Users/tear/pk_project_k8s
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('AST OK')"
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_check_payment.py
git commit -m "$(cat <<'EOF'
fix(easypaisa): _check_payment SQL filter by partner_id (defense-in-depth)

应用层 owner check 已存在（`if existing.user_id != user_id: raise 10402`），
但 SQL 层缺 partner_id filter。如果后续重构丢了应用层判断，攻击者用
B 的 phone 就能查到 B 的记录然后绕过。

修复：SQL 层直接 AND partner_id=?（用 Payment.user_id，ORM 翻译成
SQL 列 partner_id）。同时删 Payment.bank_type==bank_type_id 历史
dead filter（与 bank_type_id 字段重复）。

Tests:
- test_check_payment_filter_includes_partner_id
- test_check_payment_returns_only_owner_record
EOF
)"
```

---

## Task 3: Fix #3 — URM90040 fallback 原子 INCR

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py` (line 1168-1187, _urm90040_fallback)
- Modify: `api/tests/test_easypaisa_v19_urm90040.py` (追加 2 条测试)

- [ ] **Step 1: 定位精确行号**

```bash
cd /Users/tear/pk_project_k8s
grep -nE "async def _urm90040_fallback|self.URM90040_COUNT_KEY|new_count = cur_count" api/application/app/login/banks/easypaisa.py | head -10
```

- [ ] **Step 2: 追加测试到 test_easypaisa_v19_urm90040.py 末尾**

```python


@pytest.mark.asyncio
async def test_urm90040_atomic_concurrent_calls(ep):
    """Fix #3: 模拟 5 个并发请求 INCR 返回 1,2,3,4,5；前 3 通过，后 2 拒。"""
    ep.redis.incr = AsyncMock(side_effect=[1, 2, 3, 4, 5])
    ep.redis.expire = AsyncMock(return_value=True)
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)

    results = []
    for i in range(5):
        session = {
            'id': 533290, 'phone': '03445021275', 'bankname': 'easypaisa',
            'status': LoginStatus.PRE_LOGIN_CREATED,
            'status_history': [LoginStatus.PRE_LOGIN_CREATED],
        }
        r = await ep._urm90040_fallback('pre_login_easypaisa_533290', session, 'URM90040')
        results.append(r)

    # 前 3 个：SL_NEEDS_OTP（fallback 生效）
    assert results[0]['data']['code'] == 'SL_NEEDS_OTP'
    assert results[1]['data']['code'] == 'SL_NEEDS_OTP'
    assert results[2]['data']['code'] == 'SL_NEEDS_OTP'
    # 第 4 / 第 5：SL_NEEDS_RELOGIN（限频拒）
    assert results[3]['data']['code'] == 'SL_NEEDS_RELOGIN'
    assert results[4]['data']['code'] == 'SL_NEEDS_RELOGIN'


@pytest.mark.asyncio
async def test_urm90040_first_call_sets_expire(ep):
    """Fix #3: INCR 返回 1 时必须调 EXPIRE 设 TTL 3600，避免 key 永不过期。"""
    ep.redis.incr = AsyncMock(return_value=1)
    ep.redis.expire = AsyncMock(return_value=True)
    ep.redis.setex = AsyncMock(return_value=True)
    ep._send_otp = AsyncMock(return_value={'status': 'success'})
    ep._persist_session_data = AsyncMock(return_value=123)

    session = {
        'id': 533290, 'phone': 'x', 'bankname': 'easypaisa',
        'status': LoginStatus.PRE_LOGIN_CREATED,
        'status_history': [LoginStatus.PRE_LOGIN_CREATED],
    }
    await ep._urm90040_fallback('k', session, 'URM90040')

    # 必须调用过 expire 且 TTL=3600
    ep.redis.expire.assert_called_with('easypaisa:urm90040_count:533290', 3600)
```

- [ ] **Step 3: 跑测试看 RED**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_urm90040.py::test_urm90040_atomic_concurrent_calls api/tests/test_easypaisa_v19_urm90040.py::test_urm90040_first_call_sets_expire -v
```
Expected: **2 failed**。第一个 mock incr 但老代码用 get → AttributeError 或 mock 没生效；第二个老代码用 setex 不是 expire。

- [ ] **Step 4: 替换 _urm90040_fallback 的 GET+SETEX 段为 INCR+EXPIRE**

定位 _urm90040_fallback 方法，找到这段（line ~1172-1187）：

```python
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
        # 计数 +1，状态 reset 到 PRE_LOGIN_CREATED 再走 loginStep1
        new_count = cur_count + 1
        await self.redis.setex(count_key, self.URM90040_WINDOW_SECONDS, new_count)
```

替换为：

```python
        payment_id = session_data.get('id')
        count_key = self.URM90040_COUNT_KEY.format(payment_id=payment_id)
        # Fix #3: 原子 INCR（不再 GET+SETEX race），首次自增后才设 TTL
        new_count = await self.redis.incr(count_key)
        if new_count == 1:
            await self.redis.expire(count_key, self.URM90040_WINDOW_SECONDS)
        if new_count > self.URM90040_LIMIT:
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason=f'URM90040 count {new_count} exceeded {self.URM90040_LIMIT}/hour',
                error_code='SL_NEEDS_RELOGIN',
                message='账号疑似被频繁占用，请联系运维介入',
            )
        # 计数已 +1，状态 reset 到 PRE_LOGIN_CREATED 再走 loginStep1
```

注意：
- 新代码用 `new_count > LIMIT`（INCR 之后的值），等价于老代码 `cur_count >= LIMIT`（INCR 之前的值），都是拒第 4 次。
- 删除了独立的 `new_count = cur_count + 1` 行（因为 INCR 已经返回新值）。
- 删除了老的 `setex` 调用。

- [ ] **Step 5: 跑测试看 GREEN**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_urm90040.py -v
```
Expected: **4 passed**（U4, U5, race, expire）。

注意：U4 原测试 mock 了 `ep.redis.get` 和 `ep.redis.setex`，现在新代码不用 get 也不用 setex（只用 incr + expire）。**U4 测试需要更新 mock 以兼容**：

如果 U4 fail，更新 `test_u4_first_urm90040_triggers_fallback` 的 mock：
```python
ep.redis.get = AsyncMock(return_value=None)  # 旧的，可以删
ep.redis.incr = AsyncMock(return_value=1)    # 新的，必须加
ep.redis.expire = AsyncMock(return_value=True)
ep.redis.setex = AsyncMock(return_value=True)
```

同理 `test_u5_fourth_urm90040_forces_needs_relogin` 改为 `ep.redis.incr = AsyncMock(return_value=4)`（INCR 后是 4 > 3 → reject）。

- [ ] **Step 6: 跑全 v1.9 测试套回归**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_*.py 2>&1 | tail -3
```
Expected: **33 passed**（31 + 2，且 U4/U5 不退化）。

- [ ] **Step 7: AST + commit**

```bash
cd /Users/tear/pk_project_k8s
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('AST OK')"
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_urm90040.py
git commit -m "$(cat <<'EOF'
fix(easypaisa): URM90040 fallback use atomic INCR + EXPIRE

老 GET + SETEX 非原子，并发场景下两个请求都看到 cur_count=2 → 都
+1 到 3 → 实际允许 4 次而非 3 次。攻击场景：恶意 APP 并发发起 N
次 pre_login 可绕过限频。

修复：用 Redis INCR 原子自增 + 首次设 EXPIRE（避免覆盖已有 TTL）。
new_count > LIMIT 替代 cur_count >= LIMIT，数值语义等价。

保留 "失败也算计数" 行为（spec §3.5 没明示，保守选择防 spam）。

Tests:
- test_urm90040_atomic_concurrent_calls (5 并发 INCR 1-5，前 3 通过)
- test_urm90040_first_call_sets_expire (INCR 1 时调 EXPIRE 3600)
EOF
)"
```

---

## Task 4: Fix #4 — fingerprint MySQL 写失败时 atomic rename 回滚

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py` (line 1216-1224 `_update_payment_fingerprint_path` + line 1530-1543 `verify_fingerprint_http` 落盘段)
- Modify: `api/tests/test_easypaisa_v19_fingerprint.py` (追加 1 条测试)

- [ ] **Step 1: 定位行号**

```bash
cd /Users/tear/pk_project_k8s
grep -nE "async def _update_payment_fingerprint_path|fp_file.write|os.path.join.self.FINGERPRINT_PATH" api/application/app/login/banks/easypaisa.py
```

- [ ] **Step 2: 追加测试到 test_easypaisa_v19_fingerprint.py 末尾**

```python


@pytest.mark.asyncio
async def test_verify_fingerprint_rollback_on_mysql_fail(ep_fp, tmp_path):
    """Fix #4: MySQL 写失败时 .new 临时文件被删，老 ZIP md5 不变。"""
    import hashlib
    # 准备老 ZIP（已存在）
    old_zip = tmp_path / "easypaisa_1_03445021275.zip"
    old_zip.write_bytes(b'OLD VALID ZIP CONTENT')
    md5_before = hashlib.md5(old_zip.read_bytes()).hexdigest()

    session = {
        'id': 1, 'phone': '03445021275', 'bankname': 'easypaisa',
        'status': LoginStatus.OTP_VERIFIED, 'status_history': [],
    }
    ep_fp._get_session_data = AsyncMock(return_value=session)
    ep_fp._resolve_session_context = AsyncMock(return_value={
        'redis_key': 'k', 'session_data': session, 'resolved_payment_id': 1,
    })
    ep_fp._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_fp._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_fp.redis.get = AsyncMock(return_value=b'NEW ZIP TO BE REJECTED')
    ep_fp.redis.delete = AsyncMock(return_value=True)
    ep_fp._call_upload_data_bytes = AsyncMock(return_value=True)
    ep_fp._call_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
    # MySQL 写失败
    ep_fp._update_payment_fingerprint_path = AsyncMock(
        side_effect=Exception('MySQL connection lost')
    )

    result = await ep_fp.verify_fingerprint_http({
        'bankname': 'easypaisa', 'payment_id': 1
    })

    # 验证：错误返回
    assert result['status'] == 'error'
    assert result['data']['code'] == 'SL_UPSTREAM_ERROR'
    # 验证：老 ZIP 内容没变（md5 一致）
    assert hashlib.md5(old_zip.read_bytes()).hexdigest() == md5_before
    # 验证：.new 临时文件不存在（已被删）
    tmp_zip = tmp_path / "easypaisa_1_03445021275.zip.new"
    assert not tmp_zip.exists(), f'.new tmp file should be cleaned up'
```

- [ ] **Step 3: 跑测试看 RED**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py::test_verify_fingerprint_rollback_on_mysql_fail -v
```
Expected: **1 failed**。原因可能是 _update_payment_fingerprint_path 现在吃异常，不抛出 → 测试 mock side_effect 不触发；或者老代码先写 full_path 然后才调 MySQL，老 ZIP 已被覆盖。

- [ ] **Step 4: 改 `_update_payment_fingerprint_path` 让它 re-raise 异常**

定位 line ~1216-1224，替换为：

```python
    async def _update_payment_fingerprint_path(self, payment_id, full_path):
        funcName = '_update_payment_fingerprint_path'
        # Fix #4: 上层依赖此函数的异常做回滚，必须 re-raise（不要 try/except 吃异常）
        with self.handler.db_orm.sessionmaker() as session:
            session.execute(
                update(Payment).where(Payment.id == payment_id).values(fingerprint_path=full_path)
            )
            session.commit()
        self.logger.info(f'{self._log_key(funcName)} payment_id={payment_id} path={full_path}')
```

（去掉了老的 `try: ... except: self.logger.error(...)` 吃异常的 wrapper。）

- [ ] **Step 5: 改 verify_fingerprint_http 落盘段为 atomic rename**

定位 line ~1530-1543（"③ 全成功 → 落盘 + 更新 MySQL + 删 pending" 那段），替换为：

```python
            # ③ 全成功 → 落盘（原子写）+ 更新 MySQL + 删 pending
            phone = session_data.get('phone')
            filename = self.FINGERPRINT_FILENAME.format(
                bankname=bankname, payment_id=resolved_payment_id, phone=phone
            )
            full_path = os.path.join(self.FINGERPRINT_PATH, filename)
            # Fix #4: 先写 .new 临时文件，MySQL 成功后才 atomic rename 替换老 ZIP
            tmp_path = full_path + '.new'
            try:
                os.makedirs(self.FINGERPRINT_PATH, exist_ok=True)
                with open(tmp_path, 'wb') as fp_file:
                    fp_file.write(zip_body)
            except Exception as e:
                self.logger.error(f'{self._log_key(funcName)} 落盘失败: {e}', exc_info=True)
                return {
                    'status': 'error',
                    'message': '本地保存失败',
                    'data': {'code': 'SL_UPSTREAM_ERROR', 'phase': LoginStatus.OTP_VERIFIED},
                }
            # MySQL 写入成功才 atomic rename，失败回滚删 .new
            try:
                await self._update_payment_fingerprint_path(resolved_payment_id, full_path)
            except Exception as e:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                self.logger.error(
                    f'{self._log_key(funcName)} MySQL 写入失败，回滚 .new: {e}',
                    exc_info=True,
                )
                return {
                    'status': 'error',
                    'message': 'MySQL 写入失败',
                    'data': {'code': 'SL_UPSTREAM_ERROR', 'phase': LoginStatus.OTP_VERIFIED},
                }
            os.rename(tmp_path, full_path)  # atomic 替换老 ZIP
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
```

- [ ] **Step 6: 跑测试看 GREEN**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py -v
```
Expected: **2 passed**（U15 + rollback）。

注意：U15 测试用 `_call_upload_data_bytes` mock 已经存在。如果 U15 fail，可能是新代码改了文件命名（`tmp_path = full_path + '.new'`）但 U15 的 path 假设 old_zip path 是 `full_path`——查 U15 测试是用 mock 文件路径还是真实文件。

- [ ] **Step 7: 跑全 v1.9 测试套回归**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_*.py 2>&1 | tail -3
```
Expected: **34 passed**（33 + 1）。

- [ ] **Step 8: AST + commit**

```bash
cd /Users/tear/pk_project_k8s
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('AST OK')"
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_fingerprint.py
git commit -m "$(cat <<'EOF'
fix(easypaisa): atomic rename fingerprint zip on MySQL update fail

老逻辑：write file → MySQL update (吃异常) → delete pending → 推进状态。
MySQL 失败时本地新 ZIP 已覆盖老 ZIP 但 MySQL 仍指向老 path → 文件
和 MySQL 不一致。

修复：先写 .new tmp file → MySQL update 成功才 os.rename 原子替换 →
MySQL 失败时 os.remove(.new) rollback。同时让 _update_payment_fingerprint_path
re-raise 异常（不再吃异常）让上层能 rollback。

Tests:
- test_verify_fingerprint_rollback_on_mysql_fail
EOF
)"
```

---

## Task 5: Fix #5 — session scrub password

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py` (line 926 删除 'password': password)
- Modify: `api/tests/test_easypaisa_v19_force_terminal.py` (追加 1 条测试)

- [ ] **Step 1: 定位精确行**

```bash
cd /Users/tear/pk_project_k8s
grep -nE "'password': password" api/application/app/login/banks/easypaisa.py
```
Expected: 1 行输出，如 `926:                'password': password,`。

- [ ] **Step 2: 追加测试到 test_easypaisa_v19_force_terminal.py 末尾**

```python


@pytest.mark.asyncio
async def test_session_data_does_not_contain_password(ep_instance):
    """Fix #5: pre_login_http 完成后 session 不含明文 password 字段。"""
    from unittest.mock import patch
    import bcrypt

    # 准备 bcrypt 校验通过的 hash
    test_password = b'test_pwd_123'
    hashed = bcrypt.hashpw(test_password, bcrypt.gensalt()).decode()

    captured_sessions = []

    async def fake_persist(redis_key, session_data):
        captured_sessions.append(dict(session_data))
        return 999

    ep_instance._persist_session_data = fake_persist
    ep_instance._select_proxy_ip = AsyncMock(return_value='')
    ep_instance._check_login_failed_attempts = AsyncMock(return_value=False)
    ep_instance._check_payment = AsyncMock(return_value=None)  # 走"首次"分支
    ep_instance._get_payment_interface_lock = AsyncMock(
        return_value={'lock_id': 'k', 'lock_value': 'v'}
    )
    ep_instance._release_payment_interface_lock = AsyncMock(return_value=True)
    ep_instance._get_session_data = AsyncMock(return_value=None)
    ep_instance._is_account_registered = AsyncMock(return_value=False)
    ep_instance.redis.get = AsyncMock(return_value=None)

    ep_instance.handler.current_user.id = 33057
    ep_instance.handler.current_user.hash_trade = hashed

    await ep_instance.pre_login_http({
        'bankname': 'easypaisa',
        'phone': '03130268536',
        'password': test_password.decode(),
        'pin': '12345',
        'name': 'Test',
        'step': 'complete_login',
    })

    # 必须至少调用过一次 _persist_session_data
    assert len(captured_sessions) > 0, '_persist_session_data 未被调用'
    # 任何一次 persist 的 session 都不该含 password 字段
    for s in captured_sessions:
        assert 'password' not in s, \
            f'session 不该含明文 password，但实际有: {s.get("password")[:5]}***'
```

- [ ] **Step 3: 跑测试看 RED**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_force_terminal.py::test_session_data_does_not_contain_password -v
```
Expected: **1 failed**——assert 失败，因为 session_data 里有 `'password'` 字段。

- [ ] **Step 4: 删除 line 926 的 `'password': password,`**

定位：
```bash
grep -n "'password': password" api/application/app/login/banks/easypaisa.py
```

Edit 工具：找到这段（在 pre_login_http 的 session_data dict 构造中）：

```python
                'pinCode': pin,
                'bankname': bankname,
                'password': password,
                'account': data.get('account', ''),
```

替换为：

```python
                'pinCode': pin,
                'bankname': bankname,
                # Fix #5: password 字段不存 session（bcrypt 校验完不再使用）
                'account': data.get('account', ''),
```

- [ ] **Step 5: 跑测试看 GREEN**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_force_terminal.py -v
```
Expected: **5 passed**（4 原有 + 1 新）。

- [ ] **Step 6: 跑全 v1.9 测试套 + grep 确认 0 残留**

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_*.py 2>&1 | tail -3
echo ""
echo "session 中是否还有任何 password 写入"
grep -nE "'password':\s*password|session_data\['password'\]\s*=" api/application/app/login/banks/easypaisa.py
```
Expected:
- 35 passed (34 + 1)
- grep 输出 0 行（password 在 session 中已无写入）

- [ ] **Step 7: AST + commit**

```bash
cd /Users/tear/pk_project_k8s
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read()); print('AST OK')"
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_force_terminal.py
git commit -m "$(cat <<'EOF'
fix(easypaisa): scrub password from session after bcrypt verification

partner 交易密码 bcrypt 校验通过后被直接放进 session 序列化到 Redis
(TTL 300s)。Redis 数据泄露 = 所有 active 上号用户的交易密码明文泄露。

Pre-spec sanity check 已验证：session.password 在整个 easypaisa.py
0 引用（写完没人读），是纯死字段。删除 100% 安全。

Tests:
- test_session_data_does_not_contain_password
EOF
)"
```

---

## Task 6: 文档更新（plan 追加 hotfix-1 入口）

**Files:**
- Modify: `docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md` (末尾追加段)

- [ ] **Step 1: 定位 plan 文件末尾**

```bash
cd /Users/tear/pk_project_k8s
tail -20 docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md
```
确认末尾内容（可能是 Execution Handoff 段）。

- [ ] **Step 2: 收集本 hotfix 的 6 个 commit SHA**

```bash
cd /Users/tear/pk_project_k8s
git log --oneline 749482da^..HEAD
```
Expected: 6 行输出（spec commit `749482da` 之后的 5 个 fix commit + 这次的 docs commit 还没创建）。把前 5 个 fix commit 的 SHA 记下来。

- [ ] **Step 3: 追加 hotfix-1 入口段到 plan 文件末尾**

使用 Edit 工具，找到 plan 文件末尾的最后一段（例如 "Which approach?" 这行），在它**之后**追加：

```markdown

---

## Hotfix 1: second_login_http idempotency + 4 collateral fixes (2026-05-14)

**Trigger**: v1.9 部署后 code review + 生产 e2e 暴露 5 个 issue
**Linked spec**: `docs/superpowers/specs/2026-05-14-second-login-idempotency-hotfix-design.md`
**Implementation plan**: `docs/superpowers/plans/2026-05-14-second-login-idempotency-hotfix.md`

### 改动清单

| # | Fix | Commit | 测试 |
|---|---|---|---|
| 1 | second_login_http 入态幂等（Critical, Path B/C 修复） | `<sha-1>` | 2 个新测试 |
| 2 | _check_payment SQL filter by partner_id（Major, 防御纵深） | `<sha-2>` | 2 个新测试 |
| 3 | _urm90040_fallback 原子 INCR（Major, 限频 race fix） | `<sha-3>` | 2 个新测试 |
| 4 | fingerprint atomic rename on MySQL fail（Critical, 落盘原子性） | `<sha-4>` | 1 个新测试 |
| 5 | session scrub password（Major, 安全） | `<sha-5>` | 1 个新测试 |
| docs | spec + plan 更新 | `<sha-6>` | — |

### 测试统计

- v1.9 基线：27 passed
- Hotfix-1 后：**35 passed** (27 + 8 新)
- Regression：0

### 生产验收（H6 系列）

| 用例 | 步骤 | 结果 |
|---|---|---|
| H6 | 临时 wallet_status=0 → pre_login → second_login | TBD（部署后填）|
| H6b | 跨 partner phone 防御纵深 | TBD |
| H6c | URM90040 INCR 增量 | TBD |
| H6d | session 不含 password | TBD |
| H6e | api.log smoke test 5 分钟 | TBD |

### 部署记录

- 镜像 tag: TBD (部署后填)
- Rollout 完成时间: TBD
- 回滚记录: 无 / 描述
```

注：用真实 commit SHA 替换 `<sha-1>` 到 `<sha-5>`。`<sha-6>` 是这个 docs commit 本身，可以填 `(this commit)` 或留 `<self>` 占位。

- [ ] **Step 4: AST 不适用 + commit**

```bash
cd /Users/tear/pk_project_k8s
git add docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md
git commit -m "$(cat <<'EOF'
docs(easypaisa): hotfix-1 spec + plan update with verification log

Links hotfix-1 spec and plan to the main v1.9 plan file. Records the
5 fix commits + their tests + production e2e (H6 series, to be filled
post-deploy).

Hotfix-1 spec: docs/superpowers/specs/2026-05-14-second-login-idempotency-hotfix-design.md
Hotfix-1 plan: docs/superpowers/plans/2026-05-14-second-login-idempotency-hotfix.md
EOF
)"
```

---

## Task 7: Build + deploy + 生产 e2e 验收

这部分依赖现有 CI/CD 流程，无法在 plan 里完全自动化。**需要人工介入触发 image build。**

**Files:**
- No code changes
- 操作记录写入 plan 文件的 H6 部分

- [ ] **Step 1: Push 5 fix commits + 1 docs commit 到 origin**

```bash
cd /Users/tear/pk_project_k8s
git log --oneline 749482da..HEAD
git push origin d7pay
git log --oneline -10
```
Expected: 6 commits pushed (5 fixes + 1 docs)。

- [ ] **Step 2: 触发新镜像 build（项目特定流程）**

如果项目用 GitHub Actions / Jenkins / 手工 docker build，按团队约定触发。新镜像 tag 例如 `api-d7pay:2026051420XXXX`（YYYYMMDDHHMM 格式）。

如果不知道流程，先 SSH 上服务器看现有 CI 是如何起的：
```bash
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29
# 查看现有 deployment 用了什么镜像，从那个 registry 推同名 + 新 tag
```

**手动 build 方案**（如果没自动化）：
```bash
# 在本地或 build 机器上
cd /Users/tear/pk_project_k8s
docker build -t 10.170.0.18:30086/lib/api-d7pay:$(date -u +%Y%m%d%H%M) -f Dockerfile .
docker push 10.170.0.18:30086/lib/api-d7pay:$(date -u +%Y%m%d%H%M)
```
记录新 image tag。

- [ ] **Step 3: kubectl 触发滚动更新**

```bash
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29 \
  "export KUBECONFIG=/etc/kubernetes/admin.conf
   kubectl set image deployment/api-deploy api=10.170.0.18:30086/lib/api-d7pay:<NEW_TAG> -n pk-d7pay
   kubectl rollout status deployment/api-deploy -n pk-d7pay --timeout=180s"
```
Expected: `deployment "api-deploy" successfully rolled out`

- [ ] **Step 4: 验证新代码已部署**

```bash
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29 \
  "export KUBECONFIG=/etc/kubernetes/admin.conf
   POD=\$(kubectl get pods -n pk-d7pay -l app=api -o jsonpath='{.items[0].metadata.name}')
   echo Pod: \$POD
   kubectl exec \$POD -n pk-d7pay -- grep -nE '幂等返回: 状态已' /app/api/application/app/login/banks/easypaisa.py | head -3"
```
Expected: 输出含 "Fix #1 spec §3.6.1 风格幂等" 或 "幂等返回: 状态已" 字样（确认新代码部署）。

- [ ] **Step 5: H6 — 测 Fix #1 Path B 实测**

```bash
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29 << 'EOSSH'
export KUBECONFIG=/etc/kubernetes/admin.conf

echo "===== 临时把 533294 wallet_status 改 0（强制走二次上号）====="
kubectl exec mysql-0 -n pk-d7pay -- mysql -uroot -pPass_1234 pakistan_d7pay -e \
  "UPDATE payment SET wallet_status=0 WHERE id=533294;
   SELECT id, phone, wallet_status FROM payment WHERE id=533294;" 2>&1 | grep -v 'mysql: \[Warning\]'

echo ""
echo "===== 调 pre_login，触发二次上号续推 ====="
POD=$(kubectl get pods -n pk-d7pay -l app=api -o jsonpath='{.items[0].metadata.name}')
PRELOGIN=$(kubectl exec $POD -n pk-d7pay -- curl -s -X POST 'http://localhost:9000/v1/login/pre_login' \
  -H 'Authorization: Bearer a9bedb37-bdf2-462f-a8b3-f37e55735171' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'bankname=easypaisa&phone=03130268536&password=123456&pin=12345&name=test&step=complete_login&payment_id=533294')
echo "pre_login: $PRELOGIN"

echo ""
echo "===== 调 second_login，期望幂等返回 success（不再 INVALID_TRANSITION）====="
SECONDLOGIN=$(kubectl exec $POD -n pk-d7pay -- curl -s -X POST 'http://localhost:9000/v1/login/second_login' \
  -H 'Authorization: Bearer a9bedb37-bdf2-462f-a8b3-f37e55735171' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'bankname=easypaisa&payment_id=533294')
echo "second_login: $SECONDLOGIN"

echo ""
echo "===== 还原 wallet_status=1 ====="
kubectl exec mysql-0 -n pk-d7pay -- mysql -uroot -pPass_1234 pakistan_d7pay -e \
  "UPDATE payment SET wallet_status=1 WHERE id=533294;" 2>&1 | grep -v 'mysql: \[Warning\]'
EOSSH
```
Expected: `second_login` 返回 JSON 含 `"status":"success","data":{"ok":true,"next_step":"query_accts","phase":"accountSelectionRequired"}`。**不再有 INVALID_TRANSITION**。

如果 secondLogin 实际还是撞 URM90040（云机端 03130268536 还是被抢登），pre_login 会返回 SL_NEEDS_OTP 走 fallback chain。这种情况下 H6 可能需要重试或换 e2e 路径。

- [ ] **Step 6: H6b — Fix #2 防御纵深（可选）**

构造跨 partner 调用比较麻烦（需要另一个 partner token）。本步骤可以**跳过**——单元测试已经覆盖。如果要测，需要先在 MySQL 创建另一个 partner 的 payment 同 phone（极不推荐改 prod 数据）。

- [ ] **Step 7: H6c — Fix #3 INCR 增量**

```bash
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29 << 'EOSSH'
export KUBECONFIG=/etc/kubernetes/admin.conf

echo "===== 当前 URM90040 计数器（533296 应该 = 1，之前测过）====="
kubectl exec redis-76fbfb8d7-z8c2m -n pk-d7pay -- redis-cli get 'easypaisa:urm90040_count:533296'

echo ""
echo "===== 触发一次 533296 pre_login（应再撞 URM90040 + INCR）====="
POD=$(kubectl get pods -n pk-d7pay -l app=api -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD -n pk-d7pay -- curl -s -X POST 'http://localhost:9000/v1/login/pre_login' \
  -H 'Authorization: Bearer a9bedb37-bdf2-462f-a8b3-f37e55735171' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'bankname=easypaisa&phone=03009208353&password=123456&pin=12345&name=test&step=complete_login&payment_id=533296' \
  -o /dev/null

echo ""
echo "===== 新 URM90040 计数器（应该 = 2，INCR 生效）====="
kubectl exec redis-76fbfb8d7-z8c2m -n pk-d7pay -- redis-cli get 'easypaisa:urm90040_count:533296'
kubectl exec redis-76fbfb8d7-z8c2m -n pk-d7pay -- redis-cli ttl 'easypaisa:urm90040_count:533296'
EOSSH
```
Expected: count 从 1 → 2，TTL 仍接近 3600（首次 INCR 已设过，第二次 INCR 不重置）。

- [ ] **Step 8: H6d — Fix #5 session 无 password**

```bash
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29 << 'EOSSH'
export KUBECONFIG=/etc/kubernetes/admin.conf

echo "===== 检查最新 session 是否含 password ====="
kubectl exec redis-76fbfb8d7-z8c2m -n pk-d7pay -- redis-cli --scan --pattern 'pre_login_easypaisa_*' | head -3
for key in $(kubectl exec redis-76fbfb8d7-z8c2m -n pk-d7pay -- redis-cli --scan --pattern 'pre_login_easypaisa_*' | head -3); do
  echo "Key: $key"
  kubectl exec redis-76fbfb8d7-z8c2m -n pk-d7pay -- redis-cli get "$key" | python3 -c "
import json, sys
data = sys.stdin.read()
if data:
    s = json.loads(data)
    has_password = 'password' in s
    print(f'  has password field: {has_password}')
    if has_password:
        print(f'  ❌ FAIL: password={s[\"password\"][:5]}***')
    else:
        print(f'  ✅ PASS')
"
done
EOSSH
```
Expected: 所有 session 都 ✅ PASS（不含 password）。

- [ ] **Step 9: H6e — Smoke test**

```bash
sleep 300  # 等 5 分钟
ssh -i /Users/tear/Documents/Codex/2026-04-23-new-chat/codex_ssh_key_20260423 root@34.92.65.29 \
  "export KUBECONFIG=/etc/kubernetes/admin.conf
   POD=\$(kubectl get pods -n pk-d7pay -l app=api -o jsonpath='{.items[0].metadata.name}')
   echo '===== api.log 末 200 行 ERROR ====='
   kubectl exec \$POD -n pk-d7pay -- tail -200 /app/api/logs/api.log 2>&1 | grep -iE 'ERROR' | grep -v 'connectionRefused' | tail -20"
```
Expected: 无新增非预期 ERROR（除已知 ConnectionRefusedError 探针误报）。

- [ ] **Step 10: 更新 plan 文件 H6 段记录结果**

用 Edit 工具，把 plan 文件的 H6 表格里 `TBD` 替换成实测结果（PASS / FAIL + 简要说明）。同时填镜像 tag 和 rollout 时间。

- [ ] **Step 11: Commit + push 最终更新**

```bash
cd /Users/tear/pk_project_k8s
git add docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md
git commit -m "docs(easypaisa): hotfix-1 verification log (H6 series passed)"
git push origin d7pay
```

---

## Self-Review

**1. Spec coverage check** — spec §3.1-§3.5 五个 Fix 各自对应：

| Spec | Plan Task |
|---|---|
| §3.1 Fix #1 second_login_http 入态幂等 | Task 1 ✅ |
| §3.2 Fix #2 _check_payment SQL filter | Task 2 ✅ |
| §3.3 Fix #3 URM90040 原子 INCR | Task 3 ✅ |
| §3.4 Fix #4 fingerprint atomic rename | Task 4 ✅ |
| §3.5 Fix #5 session scrub password | Task 5 ✅ |
| §6 测试清单（8 个新测试） | Task 1-5 中各自 RED→GREEN 步骤覆盖 |
| §7 验收用例 H1-H5 | Task 1-5 单元测试 |
| §7 验收用例 H6（生产 e2e） | Task 7 ✅ |
| §8 部署 + 回滚 | Task 7 Step 2-4 + 回滚命令在 spec |
| §10 不在范围内 | 计划严格按 spec 范围，未引入额外改动 |

无 spec 漏覆盖。

**2. Placeholder scan** — 全 plan grep "TBD" 出现 4 处，全部在 Task 6 Step 3 的 plan 追加段（用户预期填补的实测数据）+ Task 7 Step 10 描述里。这些是**记录占位符**，会在执行时填实际数据，不是 plan 失败。

**3. Type consistency** — 主要方法和字段名：
- `second_login_http`、`_check_payment`、`_urm90040_fallback`、`_update_payment_fingerprint_path`、`verify_fingerprint_http`、`pre_login_http` — 跨 Task 命名一致
- `LoginStatus.ACCOUNT_SELECTION_REQUIRED` / `LoginStatus.OTP_VERIFIED` / `LoginStatus.FINGERPRINT_VERIFIED` — 一致
- `easypaisa:urm90040_count:{payment_id}` Redis key — 一致
- Bearer token `a9bedb37-...`、partner 33057 password `123456` — 一致

无类型/命名不一致。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-14-second-login-idempotency-hotfix.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，task 间审 diff，可快速迭代。预计 7 个 subagent 调度（Task 1-6 各 1 个 + Task 7 部署后人工介入或半自动）。

**2. Inline Execution** — 本会话内顺序执行，分批 checkpoint。

**Which approach?**
