# EasyPaisa v1.9 P0 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 v1.9 上线后暴露的 6 个生产问题：去掉二次上号/change_pin 的冗余指纹验证，给 secondLogin 加可选 pwd 字段救 URM90040 抢登，补全 URM90040 fallback envelope。

**Architecture:** 给 `_perform_second_login` 加可选 `with_pwd` 参数（透传到 `_build_verify_account_request`），按场景控制是否带 phone+pwd。`_second_login_chain_from_pre_login` 重写为先 secondLogin → 失败再补完整链。`change_pin_http` 内部续推 secondLogin(带新 pwd) + queryAccountList 到 ACCOUNT_SELECTION_REQUIRED。`_urm90040_fallback_from_pre_login` envelope 补 `id` + `next_step` + `expires_in=60`。

**Tech Stack:** Python 3.12 + asyncio + aioredis + SQLAlchemy + unittest + AsyncMock

---

## File Structure

| 文件 | 责任 | 改动 |
|---|---|---|
| `api/application/app/login/banks/easypaisa.py` | 生产代码 | 6 处函数 + STATUS_TRANSITIONS 一条边 |
| `api/tests/test_easypaisa_v19_state_machine.py` | 状态机邻接表测试 | AWAITING_PIN_CHANGE 边变更 |
| `api/tests/test_easypaisa_v19_pre_login.py` | pre_login 二次链路测试 | mock secondLogin 顺序改 |
| `api/tests/test_easypaisa_v19_urm90040.py` | URM90040 fallback envelope 测试 | 补 id + next_step + expires_in 字段检查 |
| `api/tests/test_easypaisa_v19_verify_otp.py` | verify_otp fallback 续推测试 | Stage 1 secondLogin 带 pwd / Stage 2 兜底 |
| `api/tests/test_easypaisa_v19_change_pin.py` | 新建：change_pin 续推测试 | secondLogin(带新 pwd) + queryAccountList |
| `api/tests/test_easypaisa_v19_e2e.py` | E2E 验收 | U3/U5/U8/U16 mock 改；新增 AC25/AC26 真实事故复现 |

**为什么这么拆**：每个 task 锁定一个独立函数 + 一个测试文件，可以独立验证、独立提交。Task 之间有依赖（Task 2 的 with_pwd 参数被 Task 4/5/6 用），按顺序执行。

---

## Task 1: STATUS_TRANSITIONS — AWAITING_PIN_CHANGE 改边

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:88-91`
- Test: `api/tests/test_easypaisa_v19_state_machine.py`

**目的：** change_pin 完成后状态直接进入 ACCOUNT_SELECTION_REQUIRED（不再回到 FINGERPRINT_VERIFIED 让 APP 多调一次 second_login）。

- [ ] **Step 1: 找到现有的 AWAITING_PIN_CHANGE 测试用例**

Run: `cd api && grep -nE "AWAITING_PIN_CHANGE|awaitingPinChange" tests/test_easypaisa_v19_state_machine.py`

Expected: 找到关于 AWAITING_PIN_CHANGE 邻接关系的测试方法。

- [ ] **Step 2: 写一个失败的测试**

将以下测试方法添加到 `api/tests/test_easypaisa_v19_state_machine.py` 中 `TransitionsTests` 类（或同级 class）内：

```python
def test_awaiting_pin_change_transitions_to_account_selection(self):
    """v1.9 P0: change_pin 成功后直接进入 ACCOUNT_SELECTION_REQUIRED（不再经 FINGERPRINT_VERIFIED）"""
    targets = STATUS_TRANSITIONS[LoginStatus.AWAITING_PIN_CHANGE]
    self.assertIn(LoginStatus.ACCOUNT_SELECTION_REQUIRED, targets,
                  'AWAITING_PIN_CHANGE 必须能转到 ACCOUNT_SELECTION_REQUIRED')
    self.assertNotIn(LoginStatus.FINGERPRINT_VERIFIED, targets,
                     'P0 改造：不再保留 AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED 边')
    self.assertIn(LoginStatus.NEEDS_RELOGIN, targets,
                  '终态逃生门仍保留')
```

- [ ] **Step 3: 跑测试看到失败**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_state_machine.py::TransitionsTests::test_awaiting_pin_change_transitions_to_account_selection -v`

Expected: FAIL — 当前 `STATUS_TRANSITIONS[AWAITING_PIN_CHANGE]` 含 FINGERPRINT_VERIFIED 不含 ACCOUNT_SELECTION_REQUIRED。

- [ ] **Step 4: 改 STATUS_TRANSITIONS**

修改 `api/application/app/login/banks/easypaisa.py:88-91`：

```python
    LoginStatus.AWAITING_PIN_CHANGE: [
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,  # change_pin 内部续推到选账号（v1.9 P0）
        LoginStatus.NEEDS_RELOGIN,
    ],
```

- [ ] **Step 5: 跑测试看到通过**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_state_machine.py -v`

Expected: PASS（新增测试 PASS，其他状态机测试不破坏）。

- [ ] **Step 6: 跑老测试检查回归**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -30`

Expected: 旧测试中如有依赖 `AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED` 的会失败，记下来；其他不破坏。

如果有失败测试，先列出来再继续。本 task 不修复——下游 task（Task 6 change_pin）会承接。

- [ ] **Step 7: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_state_machine.py
git commit -m "$(cat <<'EOF'
refactor(easypaisa): AWAITING_PIN_CHANGE goes directly to ACCOUNT_SELECTION_REQUIRED

v1.9 P0: change_pin will internally chain secondLogin+queryAccountList,
so the state machine no longer routes through FINGERPRINT_VERIFIED. Edge
removed: AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED.
EOF
)"
```

---

## Task 2: `_build_verify_account_request` 加 with_pwd 参数 + `_perform_second_login` 透传

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:3618-3653`（_perform_second_login）
- Modify: `api/application/app/login/banks/easypaisa.py:3824-3842`（_build_verify_account_request）
- Test: `api/tests/test_easypaisa_v19_pre_login.py`（加一个针对 with_pwd 的 unit 测试）

**目的：** secondLogin 调用方按需带 pwd（覆盖云机端缓存 PIN）。此 task 不改任何调用方，只让能力可用。

- [ ] **Step 1: 写一个失败的 unit 测试**

在 `api/tests/test_easypaisa_v19_pre_login.py` 文件末尾的 `if __name__ == "__main__"` 行之前，新加一个类：

```python
class SecondLoginWithPwdTests(unittest.TestCase):
    """v1.9 P0: _perform_second_login(with_pwd=True) 应该在请求体内带 phone + pwd"""

    def test_with_pwd_includes_phone_and_pwd_in_request(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            captured = {}

            def fake_request(method, url, data, **kwargs):
                captured['body'] = data
                resp = MagicMock()
                resp.status_code = 200
                resp.text = '{"code":200,"msg":"secondLogin成功","data":null}'
                resp.headers = {'Content-Type': 'application/json'}
                resp.encoding = 'utf-8'
                return resp

            ep.retry_make_request = fake_request
            session = {
                'phone': '03194834960',
                'pinCode': '11223',
                'bankname': 'easypaisa',
            }
            result = await ep._perform_second_login(session, with_pwd=True)
            self.assertEqual(result.get('outcome'), 'success')
            import base64, json as jsonlib
            data_field = captured['body'].split('&data=')[1].split('&sign=')[0]
            payload = jsonlib.loads(base64.b64decode(data_field).decode())
            inner = payload['payload']
            if isinstance(inner, str):
                inner = jsonlib.loads(inner)
            self.assertEqual(inner.get('account_id'), '03194834960')
            self.assertEqual(inner.get('phone'), '03194834960')
            self.assertEqual(inner.get('pwd'), '11223')
        asyncio.run(run())

    def test_default_no_pwd_keeps_only_account_id(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            captured = {}

            def fake_request(method, url, data, **kwargs):
                captured['body'] = data
                resp = MagicMock()
                resp.status_code = 200
                resp.text = '{"code":200,"msg":"ok","data":null}'
                resp.headers = {'Content-Type': 'application/json'}
                resp.encoding = 'utf-8'
                return resp

            ep.retry_make_request = fake_request
            session = {
                'phone': '03194834960',
                'pinCode': '11223',
                'bankname': 'easypaisa',
            }
            await ep._perform_second_login(session)
            import base64, json as jsonlib
            data_field = captured['body'].split('&data=')[1].split('&sign=')[0]
            payload = jsonlib.loads(base64.b64decode(data_field).decode())
            inner = payload['payload']
            if isinstance(inner, str):
                inner = jsonlib.loads(inner)
            self.assertEqual(inner.get('account_id'), '03194834960')
            self.assertNotIn('phone', inner, '默认调用不带 phone')
            self.assertNotIn('pwd', inner, '默认调用不带 pwd')
        asyncio.run(run())
```

- [ ] **Step 2: 跑测试看到失败**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_pre_login.py::SecondLoginWithPwdTests -v`

Expected: FAIL — 当前 `_perform_second_login` 没有 `with_pwd` 参数（TypeError）。

- [ ] **Step 3: 改 `_build_verify_account_request`**

修改 `api/application/app/login/banks/easypaisa.py:3824-3842`：

```python
    def _build_verify_account_request(self, session_data, with_pwd: bool = False):
        funcName = '构建账号验证'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, with_pwd: {with_pwd}')

        request_msg = {
            "account_id": phone,
        }
        if with_pwd:
            request_msg["phone"] = phone
            request_msg["pwd"] = session_data.get('pinCode', '')

        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['verify_account'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')

        return encoded_msg
```

- [ ] **Step 4: 改 `_perform_second_login` 接受并透传 with_pwd**

修改 `api/application/app/login/banks/easypaisa.py:3618-3621`：

```python
    async def _perform_second_login(self, session_data, with_pwd: bool = False):
        funcName = '二次登录'
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_verify_account_request(session_data, with_pwd=with_pwd)
```

其余函数体（line 3622-3653）保持不变。

- [ ] **Step 5: 跑测试看到通过**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_pre_login.py::SecondLoginWithPwdTests -v`

Expected: PASS（两个测试都通过）。

- [ ] **Step 6: 检查回归**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -15`

Expected: 不破坏任何旧测试（所有调用方仍用默认 with_pwd=False）。

- [ ] **Step 7: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_pre_login.py
git commit -m "$(cat <<'EOF'
feat(easypaisa): _perform_second_login accepts optional with_pwd to inject phone+pwd

When with_pwd=True, secondLogin request body becomes
{account_id, phone, pwd}, matching v1.9 doc line 193-202.
The cloud will update its cached PIN, which thaws URM90040 in one shot
(verified manually 2026-05-15 against 03194834960).

Default with_pwd=False keeps existing behavior — no caller changes yet.
EOF
)"
```

---

## Task 3: `_urm90040_fallback_from_pre_login` envelope 补字段

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:1248-1257`
- Test: `api/tests/test_easypaisa_v19_urm90040.py`

**目的：** APP exchange_api.dart 必需 `data.id` 才能解析 preLogin 响应；APP `_phaseAfterPreLogin` 用 `data.next_step` 路由；`expires_in` 从 120s 改 60s 匹配 v1.9 文档 OTP 实际有效期。

- [ ] **Step 1: 写一个失败的测试**

在 `api/tests/test_easypaisa_v19_urm90040.py` 现有 `Urm90040FallbackTests`（或同级）类中追加：

```python
def test_fallback_envelope_has_id_next_step_expires_in_60(self):
    """v1.9 P0: URM90040 fallback envelope 必须含 id + next_step + expires_in=60"""
    async def run():
        ep = _make()
        ep._send_otp = AsyncMock()
        ep._persist_session_data = AsyncMock()

        session = {
            'id': '533302',
            'phone': '03194834960',
            'pinCode': '11223',
            'status': LoginStatus.FINGERPRINT_VERIFIED,
            'status_history': [],
        }
        redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')
        result = await ep._urm90040_fallback_from_pre_login(redis_key, session)

        self.assertEqual(result['status'], 'error')
        data = result['data']
        self.assertEqual(data['code'], 'SL_NEEDS_OTP')
        self.assertEqual(data['id'], '533302', 'APP exchange_api line 193 必需 id')
        self.assertEqual(data['next_step'], 'verify_otp', 'APP _phaseAfterPreLogin 用 next_step')
        self.assertEqual(data['expires_in'], 60, 'v1.9 OTP 实际有效期 60s（不是 120）')
        self.assertEqual(data['phase'], LoginStatus.OTP_SENT)
    asyncio.run(run())
```

如果文件里没有 `_make()` 帮助函数，参考文件顶部已有的 FakeRedis + `_make()` 模式（已有 `Urm90040FallbackTests` 应该用过）。

- [ ] **Step 2: 跑测试看到失败**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_urm90040.py::Urm90040FallbackTests::test_fallback_envelope_has_id_next_step_expires_in_60 -v`

Expected: FAIL — 当前 envelope 缺 id / next_step；expires_in=120 不等 60。

- [ ] **Step 3: 改 envelope**

修改 `api/application/app/login/banks/easypaisa.py:1248-1257`：

```python
        return {
            'status': 'error',
            'message': '账号被抢登，已重新发送 OTP，请输入验证码',
            'data': {
                'id': payment_id,
                'code': 'SL_NEEDS_OTP',
                'phase': LoginStatus.OTP_SENT,
                'next_step': 'verify_otp',
                'expires_in': 60,
                'urm90040_count': new_count,
            },
        }
```

- [ ] **Step 4: 跑测试看到通过**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_urm90040.py -v`

Expected: PASS。

- [ ] **Step 5: 检查回归**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -15`

Expected: 老 E2E 用例 U5 可能因 envelope 形状变化失败，记下来（Task 7 会修）。其他不破坏。

- [ ] **Step 6: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_urm90040.py
git commit -m "$(cat <<'EOF'
fix(easypaisa): URM90040 fallback envelope adds id+next_step, expires_in 120→60

APP exchange_api.dart line 193 requires inner['id'] or it throws
pre_login_no_id. APP _phaseAfterPreLogin needs next_step to route.
v1.9 cloud OTP validity is 60s in practice (URM30105 expires past that);
the previous 120s misled APP UI countdown.

Root cause of users seeing "fingerprint page" after URM90040 fallback.
EOF
)"
```

---

## Task 4: `_second_login_chain_from_pre_login` 去掉前置 upload+verify

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:1069-1192`
- Test: `api/tests/test_easypaisa_v19_pre_login.py`

**目的：** 二次上号直接 secondLogin（不带 pwd）→ 失败按错误码分支：URM90040 进 fallback，URM20008 进 AWAITING_PIN_CHANGE，其他错进 NEEDS_RELOGIN。不再前置 upload_data + verifyFingerprint。

- [ ] **Step 1: 写一个失败的测试 — 二次上号直接 secondLogin 成功**

在 `api/tests/test_easypaisa_v19_pre_login.py` 文件末尾新加类：

```python
class SecondLoginChainNoFingerprintPrefixTests(unittest.TestCase):
    """v1.9 P0: pre_login 二次链路直接 secondLogin，不再前置 upload+verify"""

    def test_chain_does_not_call_upload_data_when_secondlogin_succeeds(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            ep.redis = FakeRedis()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'success', 'message': ''})
            ep._query_accts = AsyncMock(return_value={'data': '[{"accno":"96699538","accountStatus":"ACTIVE","IBAN":"PK87"}]'})
            ep._persist_session_data = AsyncMock()
            ep._update_payment = AsyncMock()

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'bankname': 'easypaisa', 'status': LoginStatus.PRE_LOGIN_CREATED,
                'status_history': [], 'fallback_from_urm90040': False,
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')
            result = await ep._second_login_chain_from_pre_login(redis_key, session, '/tmp/x.zip')

            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['data']['phase'], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            self.assertEqual(result['data']['next_step'], 'select_accts')
            ep._upload_fingerprint.assert_not_awaited()
            ep._perform_verify_fingerprint.assert_not_awaited()
            ep._perform_second_login.assert_awaited_once()
            args, kwargs = ep._perform_second_login.await_args
            self.assertFalse(kwargs.get('with_pwd', False), '二次链路首次 secondLogin 不带 pwd')
        asyncio.run(run())

    def test_chain_routes_urm90040_to_fallback(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            ep.redis = FakeRedis()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock()
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'session_expired', 'message': 'URM90040'})
            ep._urm90040_fallback_from_pre_login = AsyncMock(return_value={'status': 'error', 'data': {'code': 'SL_NEEDS_OTP'}})
            ep._persist_session_data = AsyncMock()

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'bankname': 'easypaisa', 'status': LoginStatus.PRE_LOGIN_CREATED,
                'status_history': [], 'fallback_from_urm90040': False,
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')
            result = await ep._second_login_chain_from_pre_login(redis_key, session, '/tmp/x.zip')

            ep._upload_fingerprint.assert_not_awaited()
            ep._perform_verify_fingerprint.assert_not_awaited()
            ep._urm90040_fallback_from_pre_login.assert_awaited_once()
            self.assertEqual(result['data']['code'], 'SL_NEEDS_OTP')
        asyncio.run(run())

    def test_chain_routes_urm20008_to_awaiting_pin_change(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            ep.redis = FakeRedis()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock()
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'needs_pin_change', 'message': 'URM20008'})
            ep._persist_session_data = AsyncMock()

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'bankname': 'easypaisa', 'status': LoginStatus.PRE_LOGIN_CREATED,
                'status_history': [], 'fallback_from_urm90040': False,
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')
            result = await ep._second_login_chain_from_pre_login(redis_key, session, '/tmp/x.zip')

            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['data']['code'], 'SL_NEEDS_PIN_CHANGE')
            self.assertEqual(session['status'], LoginStatus.AWAITING_PIN_CHANGE)
        asyncio.run(run())
```

- [ ] **Step 2: 跑测试看到失败**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_pre_login.py::SecondLoginChainNoFingerprintPrefixTests -v`

Expected: FAIL — 当前 `_second_login_chain_from_pre_login` 第一步就调 `_upload_fingerprint`。

- [ ] **Step 3: 重写 `_second_login_chain_from_pre_login`**

替换 `api/application/app/login/banks/easypaisa.py:1069-1192` 整个函数体（保留函数签名，函数内部完全重写）：

```python
    async def _second_login_chain_from_pre_login(
        self, redis_key: str, session_data: dict, local_zip_path: str,
    ) -> dict:
        """
        二次上号在 pre_login 内部续推（v1.9 P0 改造）：
        直接 secondLogin（不带 pwd）→ 失败按错误码分支。
        不再前置 upload_data + verifyFingerprint。
        local_zip_path 参数保留供后续兜底链路使用，但首次 secondLogin 不依赖它。
        """
        funcName = '_second_login_chain_from_pre_login'
        sl_result = await self._perform_second_login(session_data)
        outcome = sl_result.get('outcome')

        if outcome == 'session_expired' and sl_result.get('message') == 'URM90040':
            return await self._urm90040_fallback_from_pre_login(redis_key, session_data)

        if outcome == 'needs_pin_change':
            session_data['status'] = LoginStatus.AWAITING_PIN_CHANGE
            session_data.setdefault('status_history', []).append(LoginStatus.AWAITING_PIN_CHANGE)
            session_data['last_status_change'] = int(time.time())
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '需要修改 PIN',
                'data': {
                    'code': 'SL_NEEDS_PIN_CHANGE',
                    'phase': LoginStatus.AWAITING_PIN_CHANGE,
                    'next_step': 'change_pin',
                    'id': session_data.get('id'),
                },
            }

        if outcome == 'cooldown':
            return {
                'status': 'error',
                'message': 'secondLogin 冷却中',
                'data': {
                    'code': 'SL_COOLDOWN',
                    'cd_until': sl_result.get('cd_until', 0),
                    'id': session_data.get('id'),
                },
            }

        if outcome != 'success':
            return await self._force_terminal_needs_relogin(
                redis_key, session_data,
                reason=f'pre_login secondLogin outcome={outcome} msg={sl_result.get("message")}',
                error_code='SL_NEEDS_RELOGIN' if outcome == 'needs_relogin' else 'SL_UPSTREAM_ERROR',
            )

        # secondLogin 成功 → queryAccountList
        try:
            accts_api = await self._query_accts(session_data['phone'])
            accts_json = accts_api.get('data') or '[]'
            accts_data = json.loads(accts_json) if isinstance(accts_json, str) else accts_json
            active_accounts = [item for item in accts_data if str(item.get('accountStatus', '')).upper() == 'ACTIVE']
            if not active_accounts:
                return await self._force_terminal_needs_relogin(
                    redis_key, session_data,
                    reason='No active accounts returned',
                    error_code='SL_NEEDS_RELOGIN',
                )
            session_data['status'] = LoginStatus.ACCOUNT_SELECTION_REQUIRED
            session_data.setdefault('status_history', []).append(LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            session_data['account_entire'] = accts_json
            session_data['last_status_change'] = int(time.time())
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'success',
                'message': 'OK',
                'data': {
                    'id': session_data['id'],
                    'next_step': 'select_accts',
                    'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                    'accounts': active_accounts,
                },
            }
        except Exception as e:
            self.logger.warning(f'{self._log_key(funcName)} queryAccountList 失败: {e}')
            session_data['status'] = LoginStatus.FINGERPRINT_VERIFIED
            session_data.setdefault('status_history', []).append(LoginStatus.FINGERPRINT_VERIFIED)
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '查询账户列表失败，请重试 second_login',
                'data': {
                    'code': 'EP_QUERY_FAIL',
                    'phase': LoginStatus.FINGERPRINT_VERIFIED,
                    'id': session_data.get('id'),
                },
            }
```

注意：以前函数会先调 `await self._upload_fingerprint(...)` + `await self._perform_verify_fingerprint(...)`，现在删除。`local_zip_path` 参数保留以避免改调用方签名（Task 5 verify_otp fallback 兜底会用到）。

- [ ] **Step 4: 跑测试看到通过**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_pre_login.py -v`

Expected: PASS（新增 3 个测试 + 老测试中关于二次链路的部分可能要更新——记下来）。

- [ ] **Step 5: 检查回归**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -30`

Expected: 老 E2E U2/U8 / pre_login 二次链路相关测试可能失败（因为预期了 upload+verify 被调用）。记下来，Task 7 e2e 会修。

- [ ] **Step 6: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_pre_login.py
git commit -m "$(cat <<'EOF'
refactor(easypaisa): pre_login 2nd-login chain calls secondLogin directly (no fingerprint prefix)

v1.9 doc line 50-90 official 2nd-login flow:
  isAccountRegistered=true → secondLogin → (200) → done

We were calling upload_data + verifyFingerprint before secondLogin,
wasting 5-6s per attempt. Now matches doc: directly secondLogin, branch
on outcome:
  - success → queryAccountList → ACCOUNT_SELECTION_REQUIRED
  - URM90040 → _urm90040_fallback_from_pre_login (loginStep1 + OTP)
  - URM20008 → AWAITING_PIN_CHANGE (APP collects new PIN)
  - other → NEEDS_RELOGIN

local_zip_path arg kept for caller-signature compat (Task 5 fallback uses it).
EOF
)"
```

---

## Task 5: `verify_otp_http` fallback 续推改 Stage 1 secondLogin(带 pwd) → Stage 2 兜底

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:2097-2110`
- Test: `api/tests/test_easypaisa_v19_verify_otp.py`

**目的：** verify_otp 在 fallback_from_urm90040 路径下：先 secondLogin(带 pwd) 救冻 → 失败再走完整 upload+verify+secondLogin(带 pwd) 兜底。当前实现固定走完整链浪费 5-6s。

- [ ] **Step 1: 写失败测试 — Stage 1 直接成功不走 upload+verify**

在 `api/tests/test_easypaisa_v19_verify_otp.py` 加新类：

```python
class FallbackContinuationTests(unittest.TestCase):
    """v1.9 P0: verify_otp fallback 续推先 secondLogin(带 pwd)，失败才补 upload+verify"""

    def test_stage1_secondlogin_with_pwd_skips_upload_verify(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            ep.redis = FakeRedis()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'success', 'message': ''})
            ep._query_accts = AsyncMock(return_value={'data': '[{"accno":"96699538","accountStatus":"ACTIVE","IBAN":"PK87"}]'})
            ep._persist_session_data = AsyncMock()

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'bankname': 'easypaisa', 'status': LoginStatus.OTP_VERIFIED,
                'status_history': [], 'fallback_from_urm90040': True,
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')

            result = await ep._fallback_chain_after_verify_otp(
                redis_key, session, '/tmp/x.zip'
            )

            self.assertEqual(result['data']['phase'], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            ep._upload_fingerprint.assert_not_awaited()
            ep._perform_verify_fingerprint.assert_not_awaited()
            ep._perform_second_login.assert_awaited_once()
            args, kwargs = ep._perform_second_login.await_args
            self.assertTrue(kwargs.get('with_pwd', False), 'fallback Stage 1 必须带 pwd')
        asyncio.run(run())

    def test_stage2_falls_back_to_full_chain_when_pwd_retry_fails(self):
        async def run():
            handler = MagicMock()
            handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
            ep = EasyPaisa(handler)
            ep.redis = FakeRedis()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock(return_value={'outcome': 'success'})
            # Stage 1 失败 URM90040，Stage 2 成功
            ep._perform_second_login = AsyncMock(side_effect=[
                {'outcome': 'session_expired', 'message': 'URM90040'},
                {'outcome': 'success', 'message': ''},
            ])
            ep._query_accts = AsyncMock(return_value={'data': '[{"accno":"96699538","accountStatus":"ACTIVE","IBAN":"PK87"}]'})
            ep._persist_session_data = AsyncMock()

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'bankname': 'easypaisa', 'status': LoginStatus.OTP_VERIFIED,
                'status_history': [], 'fallback_from_urm90040': True,
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')

            result = await ep._fallback_chain_after_verify_otp(
                redis_key, session, '/tmp/x.zip'
            )

            self.assertEqual(result['data']['phase'], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            ep._upload_fingerprint.assert_awaited_once()
            ep._perform_verify_fingerprint.assert_awaited_once()
            self.assertEqual(ep._perform_second_login.await_count, 2)
            for call in ep._perform_second_login.await_args_list:
                args, kwargs = call
                self.assertTrue(kwargs.get('with_pwd', False), '两次都必须带 pwd')
        asyncio.run(run())
```

如果文件已有 `FakeRedis` / `_make` helpers，复用；否则在文件顶端追加（参考 test_easypaisa_v19_pre_login.py 同名 helper）。

- [ ] **Step 2: 跑测试看到失败**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_verify_otp.py::FallbackContinuationTests -v`

Expected: FAIL — `_fallback_chain_after_verify_otp` 方法不存在（AttributeError）。

- [ ] **Step 3: 新增 `_fallback_chain_after_verify_otp` helper + 修改 verify_otp_http**

在 `api/application/app/login/banks/easypaisa.py` 中（建议放在 `_second_login_chain_from_pre_login` 函数之后，约 line 1192 之后）添加新方法：

```python
    async def _fallback_chain_after_verify_otp(
        self, redis_key: str, session_data: dict, local_zip_path: str,
    ) -> dict:
        """
        verify_otp fallback 路径续推（v1.9 P0）：
        Stage 1: secondLogin(with_pwd=True) 救冻
        Stage 2: 失败兜底 upload_data + verifyFingerprint + secondLogin(with_pwd=True)
        """
        funcName = '_fallback_chain_after_verify_otp'

        # Stage 1: secondLogin 带 pwd 救冻
        sl1 = await self._perform_second_login(session_data, with_pwd=True)
        outcome1 = sl1.get('outcome')

        if outcome1 == 'success':
            return await self._post_secondlogin_query_accts(redis_key, session_data)

        if outcome1 == 'needs_pin_change':
            session_data['status'] = LoginStatus.AWAITING_PIN_CHANGE
            session_data.setdefault('status_history', []).append(LoginStatus.AWAITING_PIN_CHANGE)
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '需要修改 PIN',
                'data': {
                    'code': 'SL_NEEDS_PIN_CHANGE',
                    'phase': LoginStatus.AWAITING_PIN_CHANGE,
                    'next_step': 'change_pin',
                    'id': session_data.get('id'),
                },
            }

        if outcome1 == 'cooldown':
            return {
                'status': 'error',
                'message': 'secondLogin 冷却中',
                'data': {
                    'code': 'SL_COOLDOWN',
                    'cd_until': sl1.get('cd_until', 0),
                    'id': session_data.get('id'),
                },
            }

        if outcome1 != 'session_expired' or sl1.get('message') != 'URM90040':
            # 非 URM90040 的失败 → 直接终态
            return await self._force_terminal_needs_relogin(
                redis_key, session_data,
                reason=f'fallback Stage1 secondLogin outcome={outcome1} msg={sl1.get("message")}',
                error_code='SL_NEEDS_RELOGIN' if outcome1 == 'needs_relogin' else 'SL_UPSTREAM_ERROR',
            )

        # Stage 2: URM90040 仍存在 → 完整兜底
        self.logger.info(f'{self._log_key(funcName)} Stage 1 URM90040 → Stage 2 完整兜底')

        # (a) upload_data
        try:
            with open(local_zip_path, 'rb') as fp:
                file_body = fp.read()
            file_name = os.path.basename(local_zip_path)
            await self._upload_fingerprint(session_data, file_name, file_body)
        except Exception as e:
            self.logger.warning(f'{self._log_key(funcName)} Stage 2 upload_data 失败: {e}')
            return await self._force_terminal_needs_relogin(
                redis_key, session_data,
                reason=f'fallback Stage2 upload_data failed: {e}',
                error_code='EP_FP_PUSH_FAIL',
            )

        # (b) verifyFingerprint
        fp_result = await self._perform_verify_fingerprint(session_data)
        if fp_result.get('outcome') != 'success':
            return await self._force_terminal_needs_relogin(
                redis_key, session_data,
                reason=f'fallback Stage2 verifyFingerprint outcome={fp_result.get("outcome")}',
                error_code='FP_UPSTREAM_REJECTED',
            )

        # (c) secondLogin 带 pwd 再试一次
        sl2 = await self._perform_second_login(session_data, with_pwd=True)
        outcome2 = sl2.get('outcome')
        if outcome2 == 'success':
            return await self._post_secondlogin_query_accts(redis_key, session_data)
        if outcome2 == 'session_expired' and sl2.get('message') == 'URM90040':
            # 兜底仍 URM90040 → 再走 _urm90040_fallback（counter++）
            return await self._urm90040_fallback_from_pre_login(redis_key, session_data)
        return await self._force_terminal_needs_relogin(
            redis_key, session_data,
            reason=f'fallback Stage2 secondLogin outcome={outcome2} msg={sl2.get("message")}',
            error_code='SL_NEEDS_RELOGIN' if outcome2 == 'needs_relogin' else 'SL_UPSTREAM_ERROR',
        )

    async def _post_secondlogin_query_accts(
        self, redis_key: str, session_data: dict,
    ) -> dict:
        """secondLogin 成功后 queryAccountList + 推进状态到 ACCOUNT_SELECTION_REQUIRED"""
        funcName = '_post_secondlogin_query_accts'
        try:
            accts_api = await self._query_accts(session_data['phone'])
            accts_json = accts_api.get('data') or '[]'
            accts_data = json.loads(accts_json) if isinstance(accts_json, str) else accts_json
            active_accounts = [item for item in accts_data if str(item.get('accountStatus', '')).upper() == 'ACTIVE']
            if not active_accounts:
                return await self._force_terminal_needs_relogin(
                    redis_key, session_data,
                    reason='No active accounts returned',
                    error_code='SL_NEEDS_RELOGIN',
                )
            session_data['status'] = LoginStatus.ACCOUNT_SELECTION_REQUIRED
            session_data.setdefault('status_history', []).append(LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            session_data['account_entire'] = accts_json
            session_data['last_status_change'] = int(time.time())
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'success',
                'message': 'OK',
                'data': {
                    'id': session_data['id'],
                    'next_step': 'select_accts',
                    'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                    'accounts': active_accounts,
                },
            }
        except Exception as e:
            self.logger.warning(f'{self._log_key(funcName)} queryAccountList 失败: {e}')
            session_data['status'] = LoginStatus.FINGERPRINT_VERIFIED
            session_data.setdefault('status_history', []).append(LoginStatus.FINGERPRINT_VERIFIED)
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '查询账户列表失败，请重试 second_login',
                'data': {
                    'code': 'EP_QUERY_FAIL',
                    'phase': LoginStatus.FINGERPRINT_VERIFIED,
                    'id': session_data.get('id'),
                },
            }
```

修改 `verify_otp_http` 的 fallback 块 `api/application/app/login/banks/easypaisa.py:2097-2110`：

```python
            # fallback (URM90040) 路径：直接进 _fallback_chain_after_verify_otp
            self.logger.info(f'{self._log_key(funcName)} fallback_from_urm90040=True，进入 P0 续推')
            local_zip_path = await self._lookup_local_zip_path(real_payment_id)
            if not local_zip_path or not os.path.exists(local_zip_path):
                return await self._force_terminal_needs_relogin(
                    redis_key, session_data,
                    reason='Fallback path local ZIP missing',
                    error_code='EP_FP_FILE_MISSING',
                )
            chain_result = await self._fallback_chain_after_verify_otp(
                redis_key, session_data, local_zip_path,
            )
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {chain_result}')
            return chain_result
```

- [ ] **Step 4: 跑测试看到通过**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_verify_otp.py -v`

Expected: PASS。

- [ ] **Step 5: 检查回归**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -30`

Expected: 不破坏（Task 7 e2e 会修 U5 / U16）。

- [ ] **Step 6: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_verify_otp.py
git commit -m "$(cat <<'EOF'
feat(easypaisa): verify_otp fallback chain — Stage 1 secondLogin(with_pwd) → Stage 2 fallback

Replaces unconditional upload_data + verifyFingerprint + secondLogin chain
with a two-stage approach:

Stage 1: secondLogin(with_pwd=True) tries to thaw URM90040 via cloud-cached
PIN update (verified 2026-05-15 against 03194834960).

Stage 2 (only if Stage 1 still URM90040): full upload_data +
verifyFingerprint + secondLogin(with_pwd=True). Still URM90040 →
_urm90040_fallback_from_pre_login (counter++).

Saves 5-6s in the common case where pwd alone resolves the lock.
EOF
)"
```

---

## Task 6: `change_pin_http` 内部续推 secondLogin(带新 pwd) + queryAccountList

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py:2446-2601`
- Create: `api/tests/test_easypaisa_v19_change_pin.py`

**目的：** change_pin 成功后服务端续推 secondLogin(with_pwd=True, pwd=新PIN) + queryAccountList，状态直接推到 ACCOUNT_SELECTION_REQUIRED。APP 不再需要调 second_login_http。

- [ ] **Step 1: 创建新测试文件 + 写失败测试**

Create `api/tests/test_easypaisa_v19_change_pin.py`：

```python
"""
v1.9 P0: change_pin 内部续推 secondLogin(with_pwd) + queryAccountList。
状态从 AWAITING_PIN_CHANGE 直接到 ACCOUNT_SELECTION_REQUIRED。
"""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

API_ROOT = str(Path(__file__).resolve().parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl_map = {}
    async def get(self, key): return self.storage.get(key)
    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.storage:
            return False
        self.storage[key] = value
        if ex is not None:
            self.ttl_map[key] = ex
        return True
    async def setex(self, key, ttl, value):
        self.storage[key] = value
        self.ttl_map[key] = ttl
    async def incr(self, key):
        cur = int(self.storage.get(key, 0))
        self.storage[key] = str(cur + 1)
        return cur + 1
    async def expire(self, key, ttl):
        self.ttl_map[key] = ttl
        return 1
    async def ttl(self, key):
        return self.ttl_map.get(key, -2)
    async def delete(self, key):
        existed = key in self.storage
        self.storage.pop(key, None)
        self.ttl_map.pop(key, None)
        return 1 if existed else 0


def _make():
    handler = MagicMock()
    handler.current_user = MagicMock(id=33046, hash_trade='$2b$10$x')
    ep = EasyPaisa(handler)
    ep.redis = FakeRedis()
    ep.runtime_service = MagicMock()
    ep.runtime_service.read_snapshot = AsyncMock(return_value=None)
    ep._get_payment_interface_lock = AsyncMock(return_value={'lock_id': 'x', 'lock_value': 'y'})
    ep._release_payment_interface_lock = AsyncMock()
    return ep


class ChangePinContinuationTests(unittest.TestCase):
    """v1.9 P0: change_pin 续推 secondLogin(带新 pwd) + queryAccountList"""

    def test_change_pin_chains_to_account_selection(self):
        async def run():
            ep = _make()
            ep._resolve_session_context = AsyncMock(return_value={
                'resolved_payment_id': '533302',
                'redis_key': 'pre_login_easypaisa_533302',
                'session_data': {
                    'id': '533302',
                    'phone': '03194834960',
                    'pinCode': '11223',
                    'bankname': 'easypaisa',
                    'status': LoginStatus.AWAITING_PIN_CHANGE,
                    'status_history': [LoginStatus.AWAITING_PIN_CHANGE],
                    'pin_times': 0,
                },
                'is_aliased': False,
            })
            ep._change_pin = AsyncMock()
            ep._save_payment = AsyncMock()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock()
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'success'})
            ep._query_accts = AsyncMock(return_value={'data': '[{"accno":"96699538","accountStatus":"ACTIVE","IBAN":"PK87"}]'})
            ep._update_session_status = AsyncMock(return_value=int(__import__('time').time()) + 600)
            ep._persist_session_data = AsyncMock()
            ep._update_payment = AsyncMock()

            result = await ep.change_pin_http({
                'bankname': 'easypaisa',
                'payment_id': '533302',
                'pin': '88888',
            })

            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['data']['phase'], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            self.assertEqual(result['data']['next_step'], 'select_accts')
            self.assertIn('accounts', result['data'])
            # 关键：不调指纹相关
            ep._upload_fingerprint.assert_not_awaited()
            ep._perform_verify_fingerprint.assert_not_awaited()
            # secondLogin 必须带 pwd
            ep._perform_second_login.assert_awaited_once()
            args, kwargs = ep._perform_second_login.await_args
            self.assertTrue(kwargs.get('with_pwd', False), 'change_pin 续推 secondLogin 必须 with_pwd=True')
        asyncio.run(run())

    def test_change_pin_then_secondlogin_urm90040_falls_back_to_fallback(self):
        async def run():
            ep = _make()
            ep._resolve_session_context = AsyncMock(return_value={
                'resolved_payment_id': '533302',
                'redis_key': 'pre_login_easypaisa_533302',
                'session_data': {
                    'id': '533302',
                    'phone': '03194834960',
                    'pinCode': '11223',
                    'bankname': 'easypaisa',
                    'status': LoginStatus.AWAITING_PIN_CHANGE,
                    'status_history': [LoginStatus.AWAITING_PIN_CHANGE],
                    'pin_times': 0,
                },
                'is_aliased': False,
            })
            ep._change_pin = AsyncMock()
            ep._save_payment = AsyncMock()
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'session_expired', 'message': 'URM90040'})
            ep._urm90040_fallback_from_pre_login = AsyncMock(return_value={
                'status': 'error',
                'data': {'code': 'SL_NEEDS_OTP', 'id': '533302', 'next_step': 'verify_otp'},
            })
            ep._update_session_status = AsyncMock(return_value=int(__import__('time').time()) + 600)
            ep._persist_session_data = AsyncMock()

            result = await ep.change_pin_http({
                'bankname': 'easypaisa',
                'payment_id': '533302',
                'pin': '88888',
            })

            ep._urm90040_fallback_from_pre_login.assert_awaited_once()
            self.assertEqual(result['data']['code'], 'SL_NEEDS_OTP')
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: 跑测试看到失败**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_change_pin.py -v`

Expected: FAIL — 当前 change_pin_http 推到 FINGERPRINT_VERIFIED 后直接返回，没有续推 secondLogin。

- [ ] **Step 3: 改 change_pin_http 续推**

找到 `api/application/app/login/banks/easypaisa.py:2563-2585`（change_pin 成功后的代码块，从 `self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态')` 开始到 `return result`）。

替换为：

```python
            self.logger.info(f'{self._log_key(funcName)} changePin 成功，续推 secondLogin(with_pwd=True) + queryAccountList')

            # 写入新 PIN 到 session（覆盖云机端缓存 PIN）
            session_data['pinCode'] = pin

            # 续推 secondLogin(with_pwd=True)
            sl_result = await self._perform_second_login(session_data, with_pwd=True)
            outcome = sl_result.get('outcome')

            if outcome == 'session_expired' and sl_result.get('message') == 'URM90040':
                # 罕见：刚改完 PIN 又抢登。走 URM90040 fallback
                return await self._urm90040_fallback_from_pre_login(redis_key, session_data)

            if outcome != 'success':
                return await self._force_terminal_needs_relogin(
                    redis_key, session_data,
                    reason=f'change_pin 续推 secondLogin outcome={outcome} msg={sl_result.get("message")}',
                    error_code='SL_NEEDS_RELOGIN' if outcome == 'needs_relogin' else 'SL_UPSTREAM_ERROR',
                )

            # queryAccountList → ACCOUNT_SELECTION_REQUIRED
            try:
                accts_api = await self._query_accts(session_data['phone'])
                accts_json = accts_api.get('data') or '[]'
                accts_data = json.loads(accts_json) if isinstance(accts_json, str) else accts_json
                active_accounts = [item for item in accts_data if str(item.get('accountStatus', '')).upper() == 'ACTIVE']
                if not active_accounts:
                    return await self._force_terminal_needs_relogin(
                        redis_key, session_data,
                        reason='change_pin queryAccountList 无 active 账户',
                        error_code='SL_NEEDS_RELOGIN',
                    )

                await self._update_session_status(
                    redis_key,
                    session_data,
                    LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                    {
                        'pin_times': session_pin_times,
                        'pinCode': pin,
                        'account_entire': accts_json,
                        'last_error': None,
                    },
                )
                await self._update_payment(resolved_payment_id, session_data, account_entire=accts_json)

                result = {
                    'status': 'success',
                    'message': 'PIN修改并续推成功',
                    'data': {
                        'id': resolved_payment_id,
                        'maximum': PIN_CHANGE_ATTEMPTS_MAXIMUM,
                        'current': session_pin_times,
                        'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                        'next_step': 'select_accts',
                        'accounts': active_accounts,
                    },
                }
                self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
                return result
            except Exception as e:
                self.logger.warning(f'{self._log_key(funcName)} queryAccountList 失败: {e}')
                return await self._force_terminal_needs_relogin(
                    redis_key, session_data,
                    reason=f'change_pin queryAccountList exception: {e}',
                    error_code='EP_QUERY_FAIL',
                )
```

- [ ] **Step 4: 跑测试看到通过**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_change_pin.py -v`

Expected: PASS（2 个测试）。

- [ ] **Step 5: 检查回归**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -30`

Expected: 不破坏其他。如果 e2e U16 失败（旧 mock 设置 secondLogin 没有 with_pwd 期望），Task 7 修。

- [ ] **Step 6: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_change_pin.py
git commit -m "$(cat <<'EOF'
feat(easypaisa): change_pin internally chains secondLogin(with_pwd) + queryAccountList

After changePinStep2 succeeds, the cloud has cached the new PIN. We can
directly secondLogin(with_pwd=True, pwd=新PIN) without fingerprint
verification (PIN mismatch ≠ fingerprint mismatch). State machine edge
changes:
  AWAITING_PIN_CHANGE → ACCOUNT_SELECTION_REQUIRED

APP no longer needs to call second_login_http after change_pin —
saves one HTTP round-trip and 1-2s wall time.
EOF
)"
```

---

## Task 7: E2E 测试更新 + 全量回归

**Files:**
- Modify: `api/tests/test_easypaisa_v19_e2e.py`
- Verify: 全部 `api/tests/test_easypaisa_v19_*.py` 通过

**目的：** 更新 E2E 用例以匹配新流程（U2/U8/U16），新增 AC25/AC26 复现 03194834960 真实事故。

- [ ] **Step 1: 读现有 E2E 文件了解结构**

Run: `cd api && grep -nE "class U" tests/test_easypaisa_v19_e2e.py`

Expected: 列出现有 E2E 测试类。

- [ ] **Step 2: 写新增 AC25/AC26 测试（追加到文件末尾的 `if __name__ == "__main__"` 之前）**

```python
class AC25_Urm90040FallbackEnvelopeFieldsTests(unittest.TestCase):
    """AC25 (03194834960 复现): URM90040 fallback envelope 完整字段"""

    def test_envelope_has_id_next_step_expires_in_60(self):
        async def run():
            ep = _make_full()
            ep.redis.storage["easypaisa:urm90040_count:533302"] = "0"
            ep._send_otp = AsyncMock()
            ep._persist_session_data = AsyncMock()

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'status': LoginStatus.FINGERPRINT_VERIFIED, 'status_history': [],
                'bankname': 'easypaisa',
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')
            result = await ep._urm90040_fallback_from_pre_login(redis_key, session)

            self.assertEqual(result['status'], 'error')
            data = result['data']
            self.assertEqual(data['id'], '533302')
            self.assertEqual(data['code'], 'SL_NEEDS_OTP')
            self.assertEqual(data['next_step'], 'verify_otp')
            self.assertEqual(data['expires_in'], 60)
            self.assertEqual(data['phase'], LoginStatus.OTP_SENT)
        asyncio.run(run())


class AC26_SecondLoginPwdThawTests(unittest.TestCase):
    """AC26 (03194834960 复现): verify_otp fallback Stage 1 secondLogin(with_pwd) 一击解冻"""

    def test_stage1_pwd_skips_full_chain(self):
        async def run():
            ep = _make_full()
            ep._upload_fingerprint = AsyncMock()
            ep._perform_verify_fingerprint = AsyncMock()
            ep._perform_second_login = AsyncMock(return_value={'outcome': 'success', 'message': ''})
            ep._query_accts = AsyncMock(return_value={'data': '[{"accno":"96699538","accountStatus":"ACTIVE","IBAN":"PK87TMFB"}]'})

            session = {
                'id': '533302', 'phone': '03194834960', 'pinCode': '11223',
                'status': LoginStatus.OTP_VERIFIED, 'status_history': [],
                'bankname': 'easypaisa', 'fallback_from_urm90040': True,
            }
            redis_key = ep.PRELOGIN_KEY.format(bankname='easypaisa', payment_id='533302')
            result = await ep._fallback_chain_after_verify_otp(redis_key, session, '/tmp/x.zip')

            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['data']['phase'], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            self.assertEqual(result['data']['next_step'], 'select_accts')
            # 关键：Stage 1 一击解冻，0 次 upload / verify
            ep._upload_fingerprint.assert_not_awaited()
            ep._perform_verify_fingerprint.assert_not_awaited()
            ep._perform_second_login.assert_awaited_once()
            args, kwargs = ep._perform_second_login.await_args
            self.assertTrue(kwargs.get('with_pwd', False))
        asyncio.run(run())
```

- [ ] **Step 3: 修复 U16 (PIN 错误) E2E 用例**

读现有 U16 用例：

Run: `cd api && grep -n "U16\|change_pin\|needs_pin_change" tests/test_easypaisa_v19_e2e.py | head -10`

如果有 U16 类，定位它的 mock setup 并改成期望 change_pin 续推到 ACCOUNT_SELECTION_REQUIRED（不是 FINGERPRINT_VERIFIED）。

如果没有 U16，跳过此步。

如果 U16 存在但 mock 设置过时，修改：
- mock `_perform_second_login` 为 `AsyncMock(return_value={'outcome': 'success'})`
- mock `_query_accts` 返回有效账户
- assert 返回的 phase 是 `ACCOUNT_SELECTION_REQUIRED`

如果不确定文件状态，先跑现有 U16：

Run: `cd api && python -m pytest tests/test_easypaisa_v19_e2e.py -v -k "U16" 2>&1 | tail -20`

根据失败信息修复。

- [ ] **Step 4: 跑全套 v19 测试**

Run: `cd api && python -m pytest tests/test_easypaisa_v19_*.py -v 2>&1 | tail -40`

Expected: 全部 PASS。如果有失败，根据失败信息修复（多半是旧 mock 期望 upload+verify 被调用，删除这些断言即可）。

- [ ] **Step 5: 跑全部 easypaisa 测试做最终回归**

Run: `cd api && python -m pytest tests/test_easypaisa*.py -v 2>&1 | tail -30`

Expected: 新 v19 测试全 PASS；老 test_easypaisa_timeout_guard / test_ep_scan_channel 已知预存在失败可忽略（spec §9 范围外）。

- [ ] **Step 6: 自检 spec 覆盖**

Run: `cd api && grep -nE "with_pwd|_fallback_chain_after_verify_otp|_post_secondlogin_query_accts" application/app/login/banks/easypaisa.py | wc -l`

Expected: > 5 处出现，证明 with_pwd 参数和新 helper 都被引入。

- [ ] **Step 7: 提交**

```bash
git add api/tests/test_easypaisa_v19_e2e.py
git commit -m "$(cat <<'EOF'
test(easypaisa): E2E coverage for v1.9 P0 — AC25 envelope + AC26 pwd thaw

Reproduces 03194834960 incident: URM90040 fallback envelope completeness
(id, next_step, expires_in=60) and Stage 1 secondLogin(with_pwd) one-shot
thaw skipping upload_data + verifyFingerprint.

All v19 tests pass; pre-existing unrelated failures in timeout_guard /
ep_scan_channel remain (spec §9 out of scope).
EOF
)"
```

---

## Self-Review

**1. Spec coverage:**

| Spec 章节 | 实施 task | 覆盖 |
|---|---|---|
| §1 问题 #1-6 | Task 1-7 全部 | ✅ |
| §2 设计原则 | Task 4 (去前置指纹) + Task 5/6 (with_pwd) | ✅ |
| §3.1 pre_login 二次链路 | Task 4 | ✅ |
| §3.2 verify_otp fallback | Task 5 | ✅ |
| §3.3 change_pin 续推 | Task 6 | ✅ |
| §3.4 envelope 补字段 | Task 3 | ✅ |
| §3.5 with_pwd 参数 | Task 2 | ✅ |
| §4 STATUS_TRANSITIONS 改边 | Task 1 | ✅ |
| §5 envelope 协议规范 | Task 3 (强制 id/next_step) + Task 4 (其他路径) + Task 6 (change_pin) | ✅ |
| §6.1 AC1-AC10 | Task 4/5/6 单元测试 + Task 7 e2e | ✅ |
| §6.2 性能 AC11-AC14 | 性能为运行时观察，非 task 自动验证；上线后 grep 日志 RT 验证 | ⚠️ 部署期人工验 |
| §6.3 APP 协议 AC15-AC19 | Task 3 (envelope 含 id/next_step/expires_in) | ✅ |
| §6.4 回归 AC20-AC24 | Task 7 全套测试 | ✅ |
| §6.5 03194834960 AC25-AC26 | Task 7 e2e | ✅ |
| §7 文件清单 | 全部 task 覆盖；新建 test_easypaisa_v19_change_pin.py 在 Task 6 | ✅ |

**2. Placeholder scan:**

```bash
grep -nE "TODO|TBD|placeholder|FIXME|XXX" docs/superpowers/plans/2026-05-15-easypaisa-v19-p0-optimization.md
```

Expected: 0 matches in real plan steps.

**3. Type/method consistency:**

| 类型/方法 | 使用位置 | 一致性 |
|---|---|---|
| `_perform_second_login(session_data, with_pwd=False)` | Task 2 定义；Task 4/5/6 调用 | ✅ |
| `_build_verify_account_request(session_data, with_pwd=False)` | Task 2 定义 | ✅ |
| `_fallback_chain_after_verify_otp(redis_key, session_data, local_zip_path)` | Task 5 定义；test_easypaisa_v19_verify_otp.py 调用 | ✅ |
| `_post_secondlogin_query_accts(redis_key, session_data)` | Task 5 helper；Task 5 内部使用 | ✅ |
| URM90040 fallback envelope `data.id` / `data.next_step` / `data.expires_in` | Task 3 定义；Task 7 AC25 验证 | ✅ |

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-easypaisa-v19-p0-optimization.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, two-stage review between tasks (spec compliance + code quality), fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
