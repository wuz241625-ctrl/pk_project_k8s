# EasyPaisa 登录分流（按账号类别）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `pre_login_http` 改为按账号类别分流——已绑定 Payment 走 secondLogin-first（失败回退 loginStep1），新号走 loginStep1-first，硬性不再用 `isAccountRegistered` 做分流，并加固 loginStep1 非 100/200 返回码。

**Architecture:** 新增两个 outcome 风格的辅助方法 `_perform_loginstep1`（loginStep1 非 raise 分类器）与 `_try_secondlogin_fastpath`（已绑定号 secondLogin 探测，复用当前已有 `_call_second_login(with_pwd=True)`、`_call_query_account_list`、`_update_session_status`）。`pre_login_http` 写完 session 后：`bound_payment` 命中先试 fastpath，命中即返回、否则回退 loginStep1；新号直接 loginStep1。当前 d7pay 没有 `_post_secondlogin_query_accts` 或 `_second_login_chain_from_pre_login`，旧 `_pre_login_second_time_chain` 仅作为历史辅助保留，不再由 `pre_login_http` 调用。

**Tech Stack:** Python 3 / asyncio、`unittest` + `unittest.mock`、pytest 运行；改动单文件 `api/application/app/login/banks/easypaisa.py` 及 `api/tests/` 测试。

**设计依据：** `docs/superpowers/specs/2026-05-17-easypaisa-login-branching-by-account-class-design.md`

**约定：** 所有 `pytest` 命令在仓库根执行：`(cd api && python3 -m pytest <args>)`。改动前后参照该 spec 的 §6 错误契约表与 §8 验收标准（AC1–AC6）。

---

### Task 1: 新增 `_perform_loginstep1` 分类器

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（紧接 `_perform_second_login` 方法之后插入新方法；定位锚点：`grep -n "return {'outcome': 'upstream_error', 'message': message or response.text}" api/application/app/login/banks/easypaisa.py` 得到的行即 `_perform_second_login` 末行，在其后、`@staticmethod`/`_is_second_login_relogin_response` 之前插入）
- Test: `api/tests/test_easypaisa_v19_loginstep1_classifier.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `api/tests/test_easypaisa_v19_loginstep1_classifier.py`：

```python
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

API_ROOT = str(Path(__file__).resolve().parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from application.app.login.banks.easypaisa import EasyPaisa


def _make_ep():
    handler = MagicMock()
    handler.current_user = MagicMock(id=33049)
    ep = EasyPaisa(handler)
    ep._build_send_otp_request = MagicMock(return_value="enc")
    ep._log_response = MagicMock()
    ep._mark_payment_official_501_offline = AsyncMock(return_value=True)
    return ep


def _resp(code):
    return SimpleNamespace(
        status_code=200,
        text=json.dumps({"code": code, "msg": f"msg{code}", "data": None}),
    )


SESSION = {"id": "533264", "payment_id": "533264", "phone": "03445021275", "pinCode": "11223"}


class LoginStep1ClassifierTests(unittest.TestCase):
    def test_code_200_is_direct_success(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(200))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "direct_success")
            self.assertEqual(out["code"], 200)
        asyncio.run(run())

    def test_code_100_is_otp_sent(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(100))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "otp_sent")
        asyncio.run(run())

    def test_code_501_offline_and_marks_offline(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(501))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "offline_501")
            ep._mark_payment_official_501_offline.assert_awaited_once()
        asyncio.run(run())

    def test_code_423_is_server_busy(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(423))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "server_busy")
        asyncio.run(run())

    def test_code_503_is_network_error(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(503))
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "network_error")
        asyncio.run(run())

    def test_code_403_and_500_are_rejected(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=_resp(403))
            self.assertEqual((await ep._perform_loginstep1(dict(SESSION)))["outcome"], "rejected")
            ep.retry_make_request = MagicMock(return_value=_resp(500))
            self.assertEqual((await ep._perform_loginstep1(dict(SESSION)))["outcome"], "rejected")
        asyncio.run(run())

    def test_empty_response_is_network_error(self):
        async def run():
            ep = _make_ep()
            ep.retry_make_request = MagicMock(return_value=None)
            out = await ep._perform_loginstep1(dict(SESSION))
            self.assertEqual(out["outcome"], "network_error")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_loginstep1_classifier.py -q)`
Expected: FAIL — `AttributeError: 'EasyPaisa' object has no attribute '_perform_loginstep1'`

- [ ] **Step 3: 实现 `_perform_loginstep1`**

在 `_perform_second_login` 方法体结束之后、`@staticmethod def _is_second_login_relogin_response` 之前，插入：

```python
    async def _perform_loginstep1(self, session_data):
        """loginStep1 非 raise 分类器（spec §4）。

        平行 _perform_second_login 的 outcome 模式，供 pre_login_http 账号类别分流使用。
        返回 {'outcome': str, 'code': int|None, 'message': str}
        outcome ∈ {'direct_success','otp_sent','offline_501','server_busy','rejected','network_error'}
        """
        funcName = 'loginStep1分类'
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_send_otp_request(session_data)

        response = self.retry_make_request(method='POST', url=url, data=request_data)
        self._log_response(funcName, response)

        if not response:
            return {'outcome': 'network_error', 'code': None, 'message': 'empty response'}
        if response.status_code != 200:
            return {'outcome': 'network_error', 'code': None, 'message': f'http {response.status_code}'}

        response_data = self._decode_indus_response(funcName, response.text)
        if not isinstance(response_data, dict):
            return {'outcome': 'rejected', 'code': None, 'message': response.text}

        code = response_data.get('code')
        msg = response_data.get('msg', '')

        if code == 501:
            await self._mark_payment_official_501_offline(
                session_data.get('id') or session_data.get('payment_id'),
                f'loginStep1 returned 501: {msg}',
            )
            return {'outcome': 'offline_501', 'code': 501, 'message': msg}
        if code == 200:
            return {'outcome': 'direct_success', 'code': 200, 'message': msg}
        if code == 100:
            return {'outcome': 'otp_sent', 'code': 100, 'message': msg}
        if code == 423:
            return {'outcome': 'server_busy', 'code': 423, 'message': msg}
        if code == 503:
            return {'outcome': 'network_error', 'code': 503, 'message': msg}
        return {'outcome': 'rejected', 'code': code, 'message': msg}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_loginstep1_classifier.py -q)`
Expected: PASS（7 passed）

- [ ] **Step 5: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_loginstep1_classifier.py
git commit -m "feat(easypaisa): add _perform_loginstep1 non-raising classifier"
```

---

### Task 2: 用 `_try_secondlogin_fastpath` 落地已绑定账号 fastpath

> 落地差异说明：迁入计划早期版本提到替换 `_second_login_chain_from_pre_login`、复用 `_post_secondlogin_query_accts`。当前 d7pay 仓库实际没有这两个符号；实现直接新增 `_try_secondlogin_fastpath` 并复用 `_call_second_login(with_pwd=True)`、`_call_query_account_list`、`_update_session_status`。以下历史步骤只保留当时 TDD 设计脉络，不作为当前代码定位依据。

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（当前落地为新增 `_try_secondlogin_fastpath`；不存在 `_second_login_chain_from_pre_login`、`_post_secondlogin_query_accts` 或 `_fallback_chain_after_verify_otp`）
- Test: `api/tests/test_easypaisa_v19_fastpath.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `api/tests/test_easypaisa_v19_fastpath.py`：

```python
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

API_ROOT = str(Path(__file__).resolve().parents[1])
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from application.app.login.banks.easypaisa import EasyPaisa, LoginStatus


class FakeRedis:
    def __init__(self):
        self.storage = {}
        self.ttl_map = {}

    async def get(self, key):
        return self.storage.get(key)

    async def setex(self, key, ttl, value):
        self.storage[key] = value
        self.ttl_map[key] = ttl
        return True


def _make_ep():
    handler = MagicMock()
    handler.current_user = MagicMock(id=33049)
    ep = EasyPaisa(handler)
    ep.redis = FakeRedis()
    ep._persist_session_data = AsyncMock(return_value=ep.expire_time_login_pending)
    return ep


def _session():
    return {
        "status": LoginStatus.PRE_LOGIN_CREATED,
        "id": "533264",
        "payment_id": "533264",
        "phone": "03445021275",
        "bankname": "easypaisa",
        "pinCode": "11223",
    }


REDIS_KEY = "pre_login_easypaisa_533264"
BOUND = {"id": 533264, "phone": "03445021275", "pin": "11223"}


class FastpathTests(unittest.TestCase):
    def test_success_delegates_to_post_secondlogin_query_accts(self):
        async def run():
            ep = _make_ep()
            ep._perform_second_login = AsyncMock(return_value={"outcome": "success"})
            ep._post_secondlogin_query_accts = AsyncMock(return_value={
                "status": "success",
                "data": {"phase": LoginStatus.ACCOUNT_SELECTION_REQUIRED, "next_step": "select_accts"},
            })
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            ep._post_secondlogin_query_accts.assert_awaited_once()
            self.assertEqual(out["data"]["phase"], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
        asyncio.run(run())

    def test_needs_pin_change_returns_awaiting_pin_envelope(self):
        async def run():
            ep = _make_ep()
            ep._perform_second_login = AsyncMock(return_value={"outcome": "needs_pin_change"})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertEqual(out["data"]["code"], "SL_NEEDS_PIN_CHANGE")
            self.assertEqual(out["data"]["phase"], LoginStatus.AWAITING_PIN_CHANGE)
        asyncio.run(run())

    def test_cooldown_keeps_pre_login_state(self):
        async def run():
            ep = _make_ep()
            ep._perform_second_login = AsyncMock(return_value={"outcome": "cooldown"})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertEqual(out["data"]["code"], "SL_COOLDOWN")
            self.assertEqual(out["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)
        asyncio.run(run())

    def test_needs_relogin_returns_none_for_fallthrough(self):
        async def run():
            ep = _make_ep()
            ep._perform_second_login = AsyncMock(return_value={"outcome": "needs_relogin"})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertIsNone(out)
        asyncio.run(run())

    def test_urm90040_returns_none_for_fallthrough(self):
        async def run():
            ep = _make_ep()
            ep._perform_second_login = AsyncMock(
                return_value={"outcome": "session_expired", "message": "URM90040"})
            out = await ep._try_secondlogin_fastpath(REDIS_KEY, _session(), BOUND)
            self.assertIsNone(out)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_fastpath.py -q)`
Expected: FAIL — `AttributeError: 'EasyPaisa' object has no attribute '_try_secondlogin_fastpath'`

- [ ] **Step 3: 替换死代码为 `_try_secondlogin_fastpath`**

把整个 `_second_login_chain_from_pre_login` 方法（`async def _second_login_chain_from_pre_login(` 起，到该函数返回块结束、`async def _fallback_chain_after_verify_otp` 之前）整体替换为：

```python
    async def _try_secondlogin_fastpath(
        self, redis_key: str, session_data: dict, bound_payment,
    ):
        """已绑定 Payment 的 secondLogin-first 快路径（spec §3/§4）。

        返回：
        - dict → 命中，调用方直接 return 该 envelope
        - None → 探测判定需重新上号，调用方回退 loginStep1
        """
        funcName = '_try_secondlogin_fastpath'
        sl_result = await self._perform_second_login(session_data, with_pwd=True)
        outcome = sl_result.get('outcome')

        if outcome == 'success':
            self.logger.info(f'{self._log_key(funcName)} secondLogin 成功，续推 queryAccountList')
            return await self._post_secondlogin_query_accts(redis_key, session_data)

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
            self.logger.info(
                f'{self._log_key(funcName)} secondLogin 冷却中，状态保持 PRE_LOGIN_CREATED'
            )
            return {
                'status': 'error',
                'message': 'secondLogin 冷却中',
                'data': {
                    'code': 'SL_COOLDOWN',
                    'phase': LoginStatus.PRE_LOGIN_CREATED,
                    'cd_until': sl_result.get('cd_until', 0),
                    'id': session_data.get('id'),
                    'next_step': 'pre_login',
                },
            }

        # needs_relogin / session_expired / URM90040 / upstream_error → 回退 loginStep1
        self.logger.info(
            f'{self._log_key(funcName)} secondLogin outcome={outcome} '
            f'msg={sl_result.get("message")} → 回退 loginStep1'
        )
        return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_fastpath.py -q)`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_fastpath.py
git commit -m "feat(easypaisa): replace dead _second_login_chain_from_pre_login with _try_secondlogin_fastpath"
```

---

### Task 3: 重写 `pre_login_http` 为按账号类别分流

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`（替换 `pre_login_http` 内的分流块）
- Test: `api/tests/test_easypaisa_v19_pre_login.py`（追加新用例）

替换范围定位：在 `pre_login_http` 内，`grep -n "会话数据已存储到Redis" api/application/app/login/banks/easypaisa.py` 之后的下一行 `            local_zip_path = None` 起，到 loginStep1 code=100 分支的 `            return result`（其后紧跟 `        except NewApiError:`）止——这一整段全部替换。

- [ ] **Step 1: 写失败测试**

在 `api/tests/test_easypaisa_v19_pre_login.py` 的 `PreLoginV19Tests` 类内追加：

```python
    def test_new_number_uses_perform_loginstep1_not_send_otp(self):
        async def run():
            ep = _make_easypaisa()
            ep._verify_payment_password_bcrypt = AsyncMock()
            ep._check_login_failed_attempts = AsyncMock(return_value=False)
            ep._get_payment_interface_lock = AsyncMock(
                return_value={"lock_id": "x", "lock_value": "y"})
            ep._release_payment_interface_lock = AsyncMock()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "otp_sent", "code": 100, "message": "otp"})
            ep._send_otp = AsyncMock()
            ep._try_secondlogin_fastpath = AsyncMock()

            with patch.object(ep, '_check_payment', new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http({
                    "bankname": "easypaisa",
                    "phone": "03999999999",
                    "password": "trade_pwd",
                    "pin": "14725",
                    "name": "Test",
                    "step": "complete_login",
                })

            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_SENT)
            self.assertEqual(result["data"]["next_step"], "verify_otp")
            ep._perform_loginstep1.assert_awaited_once()
            ep._send_otp.assert_not_awaited()
            ep._try_secondlogin_fastpath.assert_not_awaited()
        asyncio.run(run())

    def test_new_number_direct_success_no_local_fp_returns_fingerprint_upload(self):
        async def run():
            ep = _make_easypaisa()
            ep._verify_payment_password_bcrypt = AsyncMock()
            ep._check_login_failed_attempts = AsyncMock(return_value=False)
            ep._get_payment_interface_lock = AsyncMock(
                return_value={"lock_id": "x", "lock_value": "y"})
            ep._release_payment_interface_lock = AsyncMock()
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "direct_success", "code": 200, "message": "ok"})
            ep._save_payment = AsyncMock(return_value=778899)

            with patch.object(ep, '_check_payment', new=AsyncMock(return_value=None)):
                result = await ep.pre_login_http({
                    "bankname": "easypaisa",
                    "phone": "03999999999",
                    "password": "trade_pwd",
                    "pin": "14725",
                    "name": "Test",
                    "step": "complete_login",
                })

            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_VERIFIED)
            self.assertEqual(result["data"]["next_step"], "upload_fingerprint")
            self.assertEqual(result["data"]["next_phase"], "fingerprintUploadRequired")
        asyncio.run(run())
```

- [ ] **Step 2: 跑测试确认失败**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login.py -q -k "perform_loginstep1_not_send_otp or direct_success_no_local_fp")`
Expected: FAIL — 现 a9ed9428 代码调 `_send_otp` 而非 `_perform_loginstep1`，`_perform_loginstep1.assert_awaited_once()` 抛 AssertionError

- [ ] **Step 3: 替换 `pre_login_http` 分流块**

把 Step 定位的整段替换为：

```python
            # ── 账号类别分流（spec §2/§3）──────────────────────────────
            # 已绑定 Payment：secondLogin-first，失败回退 loginStep1
            # 新号：loginStep1-first
            # 硬性约束：禁止用 isAccountRegistered 做分流
            if bound_payment:
                fastpath_result = await self._try_secondlogin_fastpath(
                    redis_key, session_data, bound_payment,
                )
                if fastpath_result is not None:
                    self.logger.info(
                        f'{self._log_key(funcName)} secondLogin 快路径命中: {fastpath_result}'
                    )
                    return fastpath_result
                self.logger.info(
                    f'{self._log_key(funcName)} secondLogin 探测判定需重新上号，回退 loginStep1'
                )

            # loginStep1 路径（新号，或已绑定号 secondLogin 探测回退）
            local_zip_path = None
            if bound_payment:
                if isinstance(bound_payment, dict):
                    local_zip_path = bound_payment.get('fingerprint_path')
                else:
                    local_zip_path = getattr(bound_payment, 'fingerprint_path', None)
                if isinstance(local_zip_path, str) and local_zip_path.strip() and os.path.exists(local_zip_path):
                    local_zip_path = local_zip_path.strip()
                    session_data['is_new_user'] = False
                    session_data['reuse_local_fingerprint_after_otp'] = True
                    session_data['local_fingerprint_path'] = local_zip_path
                    await self._persist_session_data(redis_key, session_data)
                    self.logger.info(
                        f'{self._log_key(funcName)} 发现本地 payment 指纹，'
                        f'loginStep1 后可复用: payment_id={payment_id}'
                    )
                else:
                    local_zip_path = None

            ls1 = await self._perform_loginstep1(session_data)
            outcome = ls1.get('outcome')

            if outcome == 'direct_success':
                self._assert_status_transition(
                    session_data,
                    LoginStatus.PRE_LOGIN_CREATED,
                    LoginStatus.OTP_VERIFIED,
                    funcName,
                )
                self.logger.info(
                    f'{self._log_key(funcName)} loginStep1 code=200，无需OTP，'
                    f'直接进入 OTP_VERIFIED'
                )

                real_payment_id = await self._save_payment(session_data, name=name)
                if not real_payment_id:
                    raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')

                old_payment_id = self._normalize_payment_id(payment_id)
                real_payment_id_text = self._normalize_payment_id(real_payment_id)
                old_redis_key = redis_key
                redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id_text)
                if old_redis_key != redis_key:
                    await self.redis.delete(old_redis_key)

                login_lock_payment_key = self._login_lock_payment_key(real_payment_id)
                await self.redis.setex(login_lock_payment_key, self.lock_time_login_duplicate_avoid, 1)

                login_lock_phone_key = self._login_lock_phone_key(phone)
                await self.redis.setex(login_lock_phone_key, self.lock_time_login_duplicate_avoid, 1)

                now_ts = int(time.time())
                session_data.update({
                    'id': real_payment_id,
                    'redis_key': redis_key,
                    'real_payment_id': real_payment_id,
                    'selected_upi': phone,
                    'upi_list': [phone],
                    'completion_time': now_ts,
                    'last_error': None,
                    'previous_payment_id': old_payment_id,
                    'login_step1_direct_success': True,
                })
                se_until = await self._update_session_status(redis_key, session_data, LoginStatus.OTP_VERIFIED)

                if local_zip_path:
                    self.logger.info(
                        f'{self._log_key(funcName)} loginStep1 code=200 且本地指纹存在，'
                        f'服务端续推 upload_data/verifyFingerprint/secondLogin/queryAccountList'
                    )
                    return await self._fallback_chain_after_verify_otp(redis_key, session_data, local_zip_path)

                result = {
                    'status': 'success',
                    'message': 'loginStep1直接登录成功，本地无指纹，请重新采集',
                    'data': {
                        'id': real_payment_id_text,
                        'phase': LoginStatus.OTP_VERIFIED,
                        'se_until': se_until,
                        'next_step': 'upload_fingerprint',
                        'next_phase': 'fingerprintUploadRequired',
                        'payment_id': real_payment_id,
                        'previous_payment_id': old_payment_id,
                    },
                }
                self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
                return result

            if outcome == 'otp_sent':
                self._assert_status_transition(
                    session_data,
                    LoginStatus.PRE_LOGIN_CREATED,
                    LoginStatus.OTP_SENT,
                    funcName,
                )
                await self._update_session_status(
                    redis_key, session_data, LoginStatus.OTP_SENT,
                    {
                        'sendOTPTime': int(time.time()),
                        'resend_count': 0,
                        'last_error': None,
                    }
                )

                result = {
                    'status': 'success',
                    'message': 'OTP发送成功，请输入收到的验证码',
                    'data': {
                        'id': payment_id,
                        'phase': LoginStatus.OTP_SENT,
                        'next_step': 'verify_otp',
                        'next_status': LoginStatus.OTP_VERIFIED,
                        'phone': phone,
                        'is_new_user': bool(session_data.get('is_new_user', True)),
                        'expires_in': 60,
                        'instruction': f'请查看手机 {phone} 收到的OTP验证码短信',
                    },
                }
                self.logger.info(f'{self._log_key(funcName)} loginStep1 code=100 返回结果: {result}')
                return result

            if outcome == 'offline_501':
                self.logger.error(
                    f'{self._log_key(funcName)} loginStep1 返回 501，下线 + 终态: {ls1.get("message")}'
                )
                return await self._force_terminal_needs_relogin(
                    redis_key, session_data,
                    reason=f'loginStep1 returned 501: {ls1.get("message")}',
                    error_code='SL_NEEDS_RELOGIN',
                )

            if outcome == 'server_busy':
                self.logger.warning(
                    f'{self._log_key(funcName)} loginStep1 返回 423，可重试: {ls1.get("message")}'
                )
                return {
                    'status': 'error',
                    'message': 'EasyPaisa 云机繁忙，请稍后重试',
                    'data': {
                        'code': 'EP_RETRY',
                        'phase': LoginStatus.PRE_LOGIN_CREATED,
                        'id': payment_id,
                        'next_step': 'pre_login',
                    },
                }

            # rejected / network_error / 其他
            self.logger.error(
                f'{self._log_key(funcName)} loginStep1 上游错误 outcome={outcome} msg={ls1.get("message")}'
            )
            return {
                'status': 'error',
                'message': ls1.get('message') or 'loginStep1 上游错误',
                'data': {
                    'code': 'EP_UPSTREAM_ERROR',
                    'phase': LoginStatus.PRE_LOGIN_CREATED,
                    'id': payment_id,
                    'next_step': 'pre_login',
                },
            }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login.py -q -k "perform_loginstep1_not_send_otp or direct_success_no_local_fp")`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_pre_login.py
git commit -m "feat(easypaisa): pre_login_http branch by account class (secondLogin-first for bound, loginStep1-first for new)"
```

---

### Task 4: 已绑定号 secondLogin 快路径集成测试

**Files:**
- Test: `api/tests/test_easypaisa_v19_pre_login.py`（追加用例）

`_make_easypaisa()` 的 `_check_payment` 默认返回 `None`；本任务用 `patch.object(ep, '_check_payment', AsyncMock(return_value={...}))` 注入命中的 `bound_payment`（含 `pin`，`wallet_status=0`），并把 `fake_payment.pin` 已为 `"11223"`，使 `pre_login_http` 进入 `bound_payment` 分支。

- [ ] **Step 1: 写失败测试**

在 `PreLoginV19Tests` 类内追加：

```python
    def _bound(self):
        return {
            "id": 533264,
            "phone": "03445021275",
            "user_id": 33049,
            "pin": "11223",
            "wallet_status": 0,
            "fingerprint_path": None,
        }

    def _prep_bound(self, ep):
        ep._verify_payment_password_bcrypt = AsyncMock()
        ep._check_login_failed_attempts = AsyncMock(return_value=False)
        ep._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "x", "lock_value": "y"})
        ep._release_payment_interface_lock = AsyncMock()
        ep._perform_loginstep1 = AsyncMock()

    def test_bound_secondlogin_success_skips_loginstep1(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_bound(ep)
            ep._try_secondlogin_fastpath = AsyncMock(return_value={
                "status": "success",
                "data": {"phase": LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                         "next_step": "select_accts"},
            })
            with patch.object(ep, '_check_payment', new=AsyncMock(return_value=self._bound())):
                result = await ep.pre_login_http({
                    "bankname": "easypaisa", "phone": "03445021275",
                    "password": "trade_pwd", "name": "Test",
                    "step": "complete_login", "payment_id": "533264",
                })
            self.assertEqual(result["data"]["phase"], LoginStatus.ACCOUNT_SELECTION_REQUIRED)
            ep._try_secondlogin_fastpath.assert_awaited_once()
            ep._perform_loginstep1.assert_not_awaited()
        asyncio.run(run())

    def test_bound_secondlogin_fallthrough_falls_to_loginstep1(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_bound(ep)
            ep._try_secondlogin_fastpath = AsyncMock(return_value=None)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "otp_sent", "code": 100, "message": "otp"})
            with patch.object(ep, '_check_payment', new=AsyncMock(return_value=self._bound())):
                result = await ep.pre_login_http({
                    "bankname": "easypaisa", "phone": "03445021275",
                    "password": "trade_pwd", "name": "Test",
                    "step": "complete_login", "payment_id": "533264",
                })
            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_SENT)
            ep._try_secondlogin_fastpath.assert_awaited_once()
            ep._perform_loginstep1.assert_awaited_once()
        asyncio.run(run())

    def test_bound_secondlogin_needs_pin_change_envelope(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_bound(ep)
            ep._try_secondlogin_fastpath = AsyncMock(return_value={
                "status": "error",
                "data": {"code": "SL_NEEDS_PIN_CHANGE",
                         "phase": LoginStatus.AWAITING_PIN_CHANGE,
                         "next_step": "change_pin"},
            })
            with patch.object(ep, '_check_payment', new=AsyncMock(return_value=self._bound())):
                result = await ep.pre_login_http({
                    "bankname": "easypaisa", "phone": "03445021275",
                    "password": "trade_pwd", "name": "Test",
                    "step": "complete_login", "payment_id": "533264",
                })
            self.assertEqual(result["data"]["code"], "SL_NEEDS_PIN_CHANGE")
            ep._perform_loginstep1.assert_not_awaited()
        asyncio.run(run())
```

- [ ] **Step 2: 跑测试确认通过（Task 3 实现后这些应直接通过）**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login.py -q -k "bound_secondlogin")`
Expected: PASS（3 passed）。若 FAIL，按断言信息修正 Task 3 分流块（这些用例锁定 §3 流程与 §6 契约）

- [ ] **Step 3: 提交**

```bash
git add api/tests/test_easypaisa_v19_pre_login.py
git commit -m "test(easypaisa): bound-payment secondLogin fastpath integration cases"
```

---

### Task 5: loginStep1 错误码集成测试（§6 契约表）

**Files:**
- Test: `api/tests/test_easypaisa_v19_pre_login.py`（追加用例）

- [ ] **Step 1: 写测试**

在 `PreLoginV19Tests` 类内追加：

```python
    def _prep_new(self, ep):
        ep._verify_payment_password_bcrypt = AsyncMock()
        ep._check_login_failed_attempts = AsyncMock(return_value=False)
        ep._get_payment_interface_lock = AsyncMock(
            return_value={"lock_id": "x", "lock_value": "y"})
        ep._release_payment_interface_lock = AsyncMock()

    async def _call_new(self, ep):
        with patch.object(ep, '_check_payment', new=AsyncMock(return_value=None)):
            return await ep.pre_login_http({
                "bankname": "easypaisa", "phone": "03999999999",
                "password": "trade_pwd", "pin": "14725", "name": "Test",
                "step": "complete_login",
            })

    def test_loginstep1_501_forces_needs_relogin_and_offline(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_new(ep)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "offline_501", "code": 501, "message": "AccountInvalid"})
            result = await self._call_new(ep)
            self.assertEqual(result["data"]["phase"], LoginStatus.NEEDS_RELOGIN)
            self.assertEqual(result["data"]["code"], "SL_NEEDS_RELOGIN")
        asyncio.run(run())

    def test_loginstep1_423_returns_ep_retry_keeps_pre_login(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_new(ep)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "server_busy", "code": 423, "message": "busy"})
            result = await self._call_new(ep)
            self.assertEqual(result["data"]["code"], "EP_RETRY")
            self.assertEqual(result["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)
            self.assertEqual(result["data"]["next_step"], "pre_login")
        asyncio.run(run())

    def test_loginstep1_rejected_returns_upstream_error(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_new(ep)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "rejected", "code": 500, "message": "CommonError"})
            result = await self._call_new(ep)
            self.assertEqual(result["data"]["code"], "EP_UPSTREAM_ERROR")
            self.assertEqual(result["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)
        asyncio.run(run())

    def test_loginstep1_network_error_returns_upstream_error(self):
        async def run():
            ep = _make_easypaisa()
            self._prep_new(ep)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "network_error", "code": 503, "message": "NetworkError"})
            result = await self._call_new(ep)
            self.assertEqual(result["data"]["code"], "EP_UPSTREAM_ERROR")
            self.assertEqual(result["data"]["phase"], LoginStatus.PRE_LOGIN_CREATED)
        asyncio.run(run())
```

- [ ] **Step 2: 跑测试确认通过**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login.py -q -k "loginstep1_501 or loginstep1_423 or loginstep1_rejected or loginstep1_network")`
Expected: PASS（4 passed）

- [ ] **Step 3: 提交**

```bash
git add api/tests/test_easypaisa_v19_pre_login.py
git commit -m "test(easypaisa): loginStep1 error-code contract cases (501/423/rejected/network)"
```

---

### Task 6: 修复被重构破坏的存量测试 + 不变量守护测试

**Files:**
- Modify: `api/tests/test_easypaisa_v19_pre_login.py`（修复 `test_wallet_offline_payment_id_can_start_relogin_session` 等引用旧符号的用例）
- Test: `api/tests/test_easypaisa_v19_branching_invariants.py`（新建：AC2 / AC6 守护）

- [ ] **Step 1: 跑全量 easypaisa 套件，列出失败**

Run: `(cd api && python3 -m pytest tests/ -q -k easypaisa)`
Expected: 出现 FAIL，集中在引用已删除的 `_second_login_chain_from_pre_login` 或假定 `pre_login_http` 调 `_send_otp`/`_is_account_registered` 的旧用例（已知至少 `test_easypaisa_v19_pre_login.py::PreLoginV19Tests::test_wallet_offline_payment_id_can_start_relogin_session`）。

> **已知预存在失败（执行期实测确认）：** 以下 3 个 e2e 用例在 `a255f49e`（计划提交、实现开始前）即已 FAIL，根因是用户提交 `a9ed9428` 改写 pre_login 分流后这些 e2e fixture 未给 bound payment 提供 `pin`，触发 `pre_login_http` 抛 `NewApiError('Payment PIN missing for bound wallet')`。**非 T1/T2 引入的回归**，但 AC1 要求全绿，故必须在本任务一并修复：
> - `test_easypaisa_v19_e2e.py::U3_SecondLoginDoesNotErrorTests::test_returns_ready_without_state_transition_error`
> - `test_easypaisa_v19_e2e.py::U20_LocalZipMissingRoutesToFingerprintUpload::test_routes_to_fingerprint_reupload`
> - `test_easypaisa_v19_e2e.py::U21_ResidualOtpVerifiedResumeTests::test_returns_resumed_envelope`
>
> 另：T2 已删除 `test_easypaisa_v19_pre_login.py` 中调用死方法的 `SecondLoginChainNoFingerprintPrefixTests`（commit `8b5fe78a`）；但 `test_easypaisa_v19_pre_login.py` 与 `test_easypaisa_business_flow_v2.py` 中仍有约 16 处 `ep._second_login_chain_from_pre_login = AsyncMock()` / `.assert_not_awaited()` 良性桩（当前因 MagicMock 自动建属性而 PASS），须在 Step 3 一并清理（AC6 要求全仓库零残留引用）。

- [ ] **Step 2: 修复 `test_wallet_offline_payment_id_can_start_relogin_session`**

将该方法体替换为（去掉对 `_send_otp` / `_is_account_registered` / `_second_login_chain_from_pre_login` 的旧 mock 与断言，改用新分流符号；该用例的 `_check_payment` 返回 `wallet_status:0` 的 bound payment，故走 fastpath 回退 loginStep1）：

```python
    def test_wallet_offline_payment_id_can_start_relogin_session(self):
        async def run():
            ep = _make_easypaisa()
            ep._verify_payment_password_bcrypt = AsyncMock()
            ep._check_login_failed_attempts = AsyncMock(return_value=False)
            ep._get_payment_interface_lock = AsyncMock(
                return_value={"lock_id": "x", "lock_value": "y"}
            )
            ep._release_payment_interface_lock = AsyncMock()
            ep._try_secondlogin_fastpath = AsyncMock(return_value=None)
            ep._perform_loginstep1 = AsyncMock(
                return_value={"outcome": "otp_sent", "code": 100, "message": "otp"})

            with patch.object(ep, '_check_payment', new=AsyncMock(return_value={
                "id": 533264,
                "phone": "03445021275",
                "user_id": 33049,
                "pin": "11223",
                "wallet_status": 0,
            })):
                result = await ep.pre_login_http({
                    "bankname": "easypaisa",
                    "phone": "03445021275",
                    "password": "trade_pwd",
                    "pin": "14725",
                    "name": "Test",
                    "step": "complete_login",
                    "payment_id": "533264",
                })

            self.assertEqual(result["data"]["next_step"], "verify_otp")
            self.assertEqual(result["data"]["phase"], LoginStatus.OTP_SENT)
            ep._try_secondlogin_fastpath.assert_awaited_once()
            ep._perform_loginstep1.assert_awaited_once()

        asyncio.run(run())
```

- [ ] **Step 3: 修复其余失败用例**

对 Step 1 列出的每个剩余 FAIL 套用以下规则：

1. 断言/mock 引用 `_second_login_chain_from_pre_login` → 改为 `_try_secondlogin_fastpath`（含 Step 1 备注的约 16 处良性桩：`= AsyncMock()` / `.assert_not_awaited()`，逐处替换或删除，使全仓库 grep 该旧名零命中——AC6）。
2. 假定 `pre_login_http` 调 `_send_otp` → 改为 `_perform_loginstep1`（按 §4 outcome 形态返回 `{"outcome": ..., "code": ..., "message": ...}`）。
3. 假定旧“新号 isAccountRegistered 分流” → 按 §3 新流程更新期望。
4. **已知 3 个 e2e 用例**（U3 / U20 / U21，见 Step 1 备注）：根因是 fixture 的 bound payment 缺 `pin`，使 `pre_login_http` 在 §2 已绑定钱包 PIN 闸门处抛 `'Payment PIN missing for bound wallet'`。修复方式：在这些 e2e 用例构造 bound payment 的 fixture 处补 `"pin": "11223"`（与既有 `_make_easypaisa` 的 `fake_payment.pin` 一致），并按 §3 新分流更新断言（已绑定号先走 `_try_secondlogin_fastpath`；用例需 mock `_try_secondlogin_fastpath` / `_perform_loginstep1` 使其断言的目标流程成立）。逐个用例对照其原意（U3：secondLogin 成功不报状态机错误 → fastpath success 返回 ACCOUNT_SELECTION_REQUIRED；U20：本地 ZIP 缺失 → fastpath 回退 loginStep1 且 `_perform_loginstep1` 返回 `direct_success` 无本地指纹 → fingerprintUploadRequired；U21：残留 OTP_VERIFIED session 复用 → 走 `_check_residual_session` 路径，pin 闸门前即命中复用，确认补 pin 后断言仍成立）。

逐个改完后重跑该文件确认绿。

Run（每修一个文件后）：`(cd api && python3 -m pytest tests/<该文件> -q)`
Expected: PASS

- [ ] **Step 4: 新建不变量守护测试（AC2 + AC6）**

新建 `api/tests/test_easypaisa_v19_branching_invariants.py`：

```python
import re
import sys
import unittest
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
SRC = API_ROOT / "application" / "app" / "login" / "banks" / "easypaisa.py"


class BranchingInvariantTests(unittest.TestCase):
    def setUp(self):
        self.src = SRC.read_text(encoding="utf-8")

    def test_ac6_dead_chain_symbol_fully_removed(self):
        self.assertNotIn(
            "_second_login_chain_from_pre_login", self.src,
            "AC6: dead _second_login_chain_from_pre_login must be fully removed",
        )

    def test_ac2_pre_login_http_does_not_call_is_account_registered(self):
        m = re.search(r"async def pre_login_http\(self.*?\n    async def ", self.src, re.S)
        self.assertIsNotNone(m, "pre_login_http body not found")
        body = m.group(0)
        self.assertNotIn(
            "_is_account_registered", body,
            "AC2: pre_login_http must not call _is_account_registered for branching",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: 跑不变量测试确认通过**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_branching_invariants.py -q)`
Expected: PASS（2 passed）

- [ ] **Step 6: 提交**

```bash
git add api/tests/
git commit -m "test(easypaisa): fix regressions from branching refactor + AC2/AC6 invariant guards"
```

---

### Task 7: 验收（AC1–AC6）与收尾

**Files:** 无源码改动（仅验证）

- [ ] **Step 1: 全量 easypaisa 套件全绿（AC1）**

Run: `(cd api && python3 -m pytest tests/ -q -k easypaisa)`
Expected: PASS，0 failed（含本计划新增 4 个文件 + 既有 23 文件用例）

- [ ] **Step 2: AC2/AC6 守护**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_branching_invariants.py -q)`
Expected: PASS（2 passed）

- [ ] **Step 3: AC3 调用顺序断言已覆盖**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login.py -q -k "skips_loginstep1 or fallthrough_falls_to_loginstep1")`
Expected: PASS（绑定健康号零 `_perform_loginstep1`；探测失败号确实落 `_perform_loginstep1`）

- [ ] **Step 4: AC4 错误契约表逐行覆盖**

Run: `(cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login.py tests/test_easypaisa_v19_fastpath.py -q -k "secondlogin or loginstep1_501 or loginstep1_423 or loginstep1_rejected or loginstep1_network or direct_success_no_local_fp or perform_loginstep1_not_send_otp")`
Expected: PASS——覆盖 §6 每一行（success / needs_pin_change / cooldown / 落 loginStep1 / 200+无本地指纹 / 100 / 501 / 423 / 403·500·503）

- [ ] **Step 5: AC5 回归 + 状态机无 diff**

Run: `(cd api && python3 -m pytest tests/ -q -k "easypaisa and (second_login or change_pin or session_resume or urm90040 or state_machine)")`
Then Run: `git diff a9ed9428 -- api/application/app/login/banks/easypaisa.py | grep -n "STATUS_TRANSITIONS" || echo "STATUS_TRANSITIONS 定义无 diff"`
Expected: 测试 PASS；grep 输出 `STATUS_TRANSITIONS 定义无 diff`（仅允许出现在不相关上下文，定义块本身未改）

- [ ] **Step 6: 最终提交（如有未提交的验证脚注/微调）**

```bash
git status --porcelain
git add -A docs/superpowers/ api/
git commit -m "chore(easypaisa): finalize account-class branching (AC1-AC6 green)" || echo "nothing to commit"
```

---

## Self-Review

**1. Spec coverage（对照 spec 各节）：**
- §2 决策表（已绑定 secondLogin-first / 新号 loginStep1-first / 禁用 isAccountRegistered）→ Task 3 分流块 + Task 6 AC2 守护
- §3 架构（fastpath 命中返回 / 回退 loginStep1）→ Task 2 + Task 3 + Task 4
- §4 组件（`_try_secondlogin_fastpath`、`_perform_loginstep1`、`_send_otp` 不动、死代码消除）→ Task 1/2/3；`_send_otp` 全程未修改（仅新增 `_perform_loginstep1`）
- §5 状态机不改 → Task 7 Step 5 grep 守护
- §6 错误契约 9 行 → Task 4/5 + Task 7 Step 4 显式映射
- §7 测试策略 10 项 → Task 1/2/4/5/6 覆盖（含 mock retry_make_request、复用既有套件、回归项）
- §8 AC1–AC6 → Task 7 Step 1–5；AC6/AC2 另有 Task 6 单测固化
- §9 范围边界（不改 `_send_otp`/下游 URM90040/`STATUS_TRANSITIONS`/其余对外契约）→ 计划未触碰这些符号，Task 7 Step 5 守护

**2. Placeholder scan：** 无 TBD/TODO；每个改码步骤含完整代码；命令含预期输出。Task 6 Step 3 为“对剩余 FAIL 逐个套用三条已明确的替换规则”，规则具体（符号 A→B 映射），非占位。

**3. Type consistency：** `_perform_loginstep1` 返回键 `outcome/code/message` 在 Task 1 定义、Task 3/5 消费一致；`outcome` 取值集合（direct_success/otp_sent/offline_501/server_busy/network_error/rejected）Task 1↔Task 3↔Task 5 一致。`_try_secondlogin_fastpath(redis_key, session_data, bound_payment)` 签名 Task 2 定义、Task 3/4 调用一致；返回 `dict|None` 语义 Task 2↔Task 3 一致。错误码字符串 `SL_NEEDS_RELOGIN/EP_RETRY/EP_UPSTREAM_ERROR/SL_NEEDS_PIN_CHANGE/SL_COOLDOWN` 在分流块与测试断言间逐字一致。

---

## Execution Record（2026-05-17 d7pay）

当前仓库与迁入计划存在三处实际差异，执行时已按设计目标适配：

- 当前仓库没有 `api/tests/test_easypaisa_v19_pre_login.py`、`test_easypaisa_v19_second_login.py`、`test_easypaisa_business_flow_v2.py`，对应覆盖落到新增 `test_easypaisa_v19_pre_login_branching.py` 与既有 `test_easypaisa_v19_acceptance.py`。
- 当前仓库没有 `_second_login_chain_from_pre_login` / `_post_secondlogin_query_accts`；新增 `_try_secondlogin_fastpath` 直接复用 `_call_second_login(with_pwd=True)`、`_call_query_account_list`、`_update_session_status`。旧 `_pre_login_second_time_chain` 保留但不再由 `pre_login_http` 调用。
- `TimeOutGuard` 曾作为 d7pay 既有回归测试依赖被临时恢复；后续确认 timeout jobs 已由 `/Users/tear/pk-go-worker` 接管，因此兼容类与旧语义测试已在 `2026-05-17-timeoutguard-retirement.md` 中退役。

完成项：

- [x] Task 1：新增 `_perform_loginstep1` 分类器与 `test_easypaisa_v19_loginstep1_classifier.py`。
- [x] Task 2：新增 `_try_secondlogin_fastpath` 与 `test_easypaisa_v19_fastpath.py`。
- [x] Task 3/4/5：`pre_login_http` 改为按账号类别分流，并由 `test_easypaisa_v19_pre_login_branching.py` 覆盖新号、已绑定 fastpath、fallthrough、501/423/rejected/network_error。
- [x] Task 6：新增 AC2/AC6 守护 `test_easypaisa_v19_branching_invariants.py`，并更新旧 `isAccountRegistered` 分流断言。
- [x] Task 7：`cd api && python3 -m pytest tests/ -q -k easypaisa` 通过，结果 `153 passed, 152 deselected`。

待本次提交前最终复跑命令：

```bash
cd api && python3 -m pytest tests/ -q -k easypaisa
cd api && python3 -m pytest tests/test_easypaisa_v19_branching_invariants.py -q
cd api && python3 -m pytest tests/test_easypaisa_v19_pre_login_branching.py tests/test_easypaisa_v19_fastpath.py -q
```
