# EasyPaisa v1.9 P0 优化设计

- **日期**: 2026-05-15
- **背景**: v1.9 已上线（2026-05-14 ddd43d5e），生产暴露 4 类问题，全部由二次上号链路设计偏离 v1.9 文档导致
- **范围**: 仅改 `api/application/app/login/banks/easypaisa.py` 5 处函数 + spec 更新 + v19 测试。APP 端零改动
- **依赖**: 基于 2026-05-14 的 v1.9 总体 spec `2026-05-14-easypaisa-login-redesign-design.md`
- **真实验证**: 2026-05-15 手动调云机 `secondLogin(phone, pwd=11223)` 救 03194834960 一击解冻成功（云机 code=200）

---

## 1. 现状问题

线上 v1.9 部署后实测 03194834960 / payment 533302 抢登场景，暴露 6 个问题：

| # | 问题 | 影响 |
|---|---|---|
| 1 | 二次上号 `secondLogin` 前**必走** `upload_data + verifyFingerprint` | 浪费 5-6s/次，云机带宽，违反 v1.9 文档 line 50-90 流程 |
| 2 | `secondLogin` **不带 pwd** | URM90040 抢登没有"温和解冻"通道，直接走 OTP fallback |
| 3 | OTP `expires_in` 写 **120s** 实际只 60s | APP 误以为 OTP 还有时间，用户输的时候已过期（URM30105）|
| 4 | URM90040 fallback envelope 缺 `id` + `next_step` | APP exchange_api.dart line 193 抛 `pre_login_no_id` 错误，进 failed 屏（用户实测"APP 进入指纹页面"的根因）|
| 5 | `change_pin` 后 APP 还要再调 second_login_http | 多一次 HTTP 往返；且 change_pin 链路理论不需要再验指纹（PIN 错 ≠ 指纹错）|
| 6 | `verify_otp` fallback 续推固定走完整 upload+verify+secondLogin | URM90040 救冻其实只要 secondLogin 带 pwd 一次，浪费 5-6s |

## 2. 设计原则

**所有 `secondLogin` 调用都不前置 `verifyFingerprint`**：
- 云机端指纹绑定是一次性建立的（在 `loginStep2(should_verify_fingerprint=true)` 时）
- PIN 错 ≠ 指纹错；抢登 ≠ 指纹错
- 唯一保留完整 `upload_data + verifyFingerprint + secondLogin` 路径：**URM90040 fallback 兜底**（secondLogin 带 pwd 救冻仍失败时）

## 3. 改动总览

### 3.1 `pre_login_http` 二次链路（去前置指纹）

`_second_login_chain_from_pre_login` 重写为：

```
isAccountRegistered=true:
  ① secondLogin(account_id)  — 不带 pwd
     - success → queryAccountList → ACCOUNT_SELECTION_REQUIRED
     - URM90040 → 进 _urm90040_fallback_from_pre_login（loginStep1 发 OTP）
     - URM20008/URM20017 → AWAITING_PIN_CHANGE
     - needs_relogin / 其他 → NEEDS_RELOGIN
     - cooldown → SL_COOLDOWN（状态不动）
```

⚠️ **删除原 upload_data + verifyFingerprint 前置步骤**

### 3.2 `verify_otp_http` fallback 续推（带 pwd 救冻 + 兜底）

```
fallback_from_urm90040=true 且 loginStep2 成功:
  Stage 1: secondLogin(account_id, phone, pwd=session.pinCode)  — 带 pwd 救冻
     - success → queryAccountList → ACCOUNT_SELECTION_REQUIRED
     - URM90040 → 进 Stage 2
     - URM20008/URM20017 → AWAITING_PIN_CHANGE
     - 其他错 → NEEDS_RELOGIN

  Stage 2: 完整兜底（唯一保留 upload+verify 的地方）
     upload_data + verifyFingerprint + secondLogin(带 pwd) + queryAccountList
     - success → ACCOUNT_SELECTION_REQUIRED
     - 仍 URM90040 → counter++（>3 直接 NEEDS_RELOGIN，否则再次 fallback OTP）
```

### 3.3 `change_pin_http` 续推（不验指纹，直接 secondLogin）

```
APP change_pin(pin=用户输入的新 PIN):
  ① 入态校验 AWAITING_PIN_CHANGE
  ② changePinStep1
  ③ changePinStep2(newpin=新 PIN)
  ④ 写 MySQL.pin = 新 PIN
  ⑤ 续推: secondLogin(account_id, phone, pwd=新 PIN)
     - success → queryAccountList → ACCOUNT_SELECTION_REQUIRED
     - URM90040 → fallback OTP（罕见）
     - 其他错 → NEEDS_RELOGIN
  ⑥ 返回 {next_step:'select_accts', accounts:[...]}
```

⚠️ **不前置 upload_data / verifyFingerprint**；APP 不再需要调 `second_login_http`

### 3.4 `_urm90040_fallback_from_pre_login` envelope 补字段

```python
return {
    'status': 'error',
    'message': '账号被抢登，已重新发送 OTP，请输入验证码',
    'data': {
        'id': payment_id,           # 新增：APP exchange_api.dart line 193 必需
        'code': 'SL_NEEDS_OTP',
        'phase': LoginStatus.OTP_SENT,
        'next_step': 'verify_otp',  # 新增：APP _phaseAfterPreLogin 路由
        'expires_in': 60,           # 改：120 → 60（v1.9 实战值）
        'urm90040_count': new_count,
    },
}
```

### 3.5 `_build_verify_account_request` 加 `with_pwd` 参数

```python
def _build_verify_account_request(self, session_data, with_pwd: bool = False):
    phone = session_data.get('phone')
    request_msg = {"account_id": phone}
    if with_pwd:
        request_msg["phone"] = phone
        request_msg["pwd"] = session_data.get('pinCode', '')
    ...
```

`_perform_second_login` 增加 `with_pwd` 透传参数。调用方按场景传：

| 调用方 | with_pwd |
|---|---|
| `_second_login_chain_from_pre_login` 首次 secondLogin (3.1) | `False` |
| `verify_otp_http` fallback Stage 1 (3.2) | `True` |
| `verify_otp_http` fallback Stage 2 兜底 (3.2) | `True` |
| `change_pin_http` 续推 (3.3) | `True` |
| `second_login_http`（独立接口，残留 session 复用走这里）| `False`（保持现状）|

## 4. 状态机改动

```python
# STATUS_TRANSITIONS 仅改一条
LoginStatus.AWAITING_PIN_CHANGE: [
-   LoginStatus.FINGERPRINT_VERIFIED,        # 旧：change_pin 成功回到指纹验证态
+   LoginStatus.ACCOUNT_SELECTION_REQUIRED,  # 新：change_pin 内部续推到选账号
    LoginStatus.NEEDS_RELOGIN,
],
```

其他邻接关系不变。

## 5. envelope 协议规范

所有 `pre_login_http` 路径返回 envelope 必须包含：

| 字段 | 类型 | 强制 | 说明 |
|---|---|---|---|
| `status` | `success`/`error` | ✅ | 标准 |
| `message` | str | ✅ | 标准 |
| `data.id` | str/int | ✅ | APP exchange_api.dart 必需 |
| `data.phase` | LoginStatus 枚举字符串 | ✅ | |
| `data.next_step` | str | ✅ | 除非 phase=activeSuccessful 用 'ready' |
| `data.code` | str | （错误时）| 业务错误码 |
| `data.expires_in` | int | （OTP 相关）| 60（loginStep1 后）|
| `data.accounts` | array | （ACCOUNT_SELECTION_REQUIRED）| |
| `data.resumed` | bool | （残留 session 复用）| |
| `data.urm90040_count` | int | （fallback envelope）| |

## 6. 验收用例

### 6.1 功能 AC

| ID | 场景 | 期望 |
|---|---|---|
| AC1 | 二次上号正常账户 | pre_login 内部仅调 isAccountRegistered + secondLogin + queryAccountList = 3 次云机调用 → ACCOUNT_SELECTION_REQUIRED → select_accts → ACTIVE_SUCCESSFUL |
| AC2 | 二次上号 URM90040 第一次 | pre_login → secondLogin URM90040 → loginStep1 → 返回 `{id, code:'SL_NEEDS_OTP', next_step:'verify_otp', expires_in:60}`；counter=1 |
| AC3 | AC2 后 60s 内输对 OTP | verify_otp → loginStep2 成功 → secondLogin(带 pwd) 一次过 → queryAccountList → ACCOUNT_SELECTION_REQUIRED；**全程 0 次 upload_data / verifyFingerprint** |
| AC4 | AC3 中 secondLogin(带 pwd) 仍 URM90040 | 兜底走 upload_data + verifyFingerprint + secondLogin(带 pwd)；仍失败 → 再次 fallback OTP；counter>3 → NEEDS_RELOGIN |
| AC5 | URM20008/URM20017 PIN 错误 | pre_login → secondLogin URM20008 → AWAITING_PIN_CHANGE → APP 让用户输新 PIN → change_pin(新PIN) → changePinStep1+Step2+secondLogin(带新PIN)+queryAccountList → ACCOUNT_SELECTION_REQUIRED → select_accts → ACTIVE_SUCCESSFUL；**全程 0 次 upload_data / verifyFingerprint** |
| AC6 | URM90040 counter > 3 | 直接 NEEDS_RELOGIN（不发 OTP，不递归）|
| AC7 | 首次上号 | isAccountRegistered=false → 7 步流程完全不变（loginStep1+loginStep2+upload_fingerprint+verify_fingerprint+second_login+select_accts）|
| AC8 | 已 ACTIVE 重复 pre_login（533264）| runtime_snapshot=ACTIVE → 返回 `{next_step:'ready'}` 不创建 session |
| AC9 | 残留 session 复用 | NEXT_STEP_MAP 完全不变 |
| AC10 | 唯一保留 verifyFingerprint 路径 | 仅 verify_otp_http fallback Stage 2 兜底链中出现 verifyFingerprint 调用（在二次上号 / PIN 修改 / fallback Stage 1 都不出现）|

### 6.2 性能 AC

| ID | 场景 | 期望 |
|---|---|---|
| AC11 | 二次上号正常 pre_login 耗时 | **< 2s**（从 5-8s 缩到 2s，节省 5-6s）|
| AC12 | 二次上号 URM90040 → fallback OTP 耗时 | **< 3s** |
| AC13 | fallback secondLogin(带 pwd) 救冻耗时 | **< 3s**（loginStep2 + secondLogin 一次过）|
| AC14 | change_pin 整体耗时 | **< 8s**（含 step1+step2+secondLogin+queryAccountList）|

### 6.3 APP 协议 AC

| ID | 检查项 | 期望 |
|---|---|---|
| AC15 | pre_login 任意路径返回 envelope | 必含 `data.id` |
| AC16 | URM90040 fallback envelope | 必含 `next_step='verify_otp'`、`expires_in=60` |
| AC17 | change_pin 成功返回 | 必含 `data.id`、`data.next_step='select_accts'`、`data.accounts` |
| AC18 | APP `exchange_api.dart` `preLogin` | 不抛 `pre_login_no_id`，能解析所有路径 |
| AC19 | APP `_phaseAfterPreLogin` | 根据 next_step 正确路由（不进 default failed 屏）|

### 6.4 回归 AC

| ID | 检查项 | 期望 |
|---|---|---|
| AC20 | v19 测试套件 90+ tests | 全 PASS |
| AC21 | STATUS_TRANSITIONS 闭环 | 改一条边后仍闭环、ACTIVE_SUCCESSFUL/NEEDS_RELOGIN 仍是终态 |
| AC22 | `_force_terminal_needs_relogin` 调用点 | 仍统一终止，加上 verify_otp fallback Stage 2 失败时的新调用 |
| AC23 | NEXT_STEP_MAP | 不变 |
| AC24 | 老 v1.6 业务接口测试 | 不破坏（test_easypaisa_business_flow_v2 / test_easypaisa_timeout_guard 已 skip 老测试）|

### 6.5 03194834960 真实事故验收

| ID | 步骤 | 期望 |
|---|---|---|
| AC25 | 真实账号（被抢登中）调 pre_login | secondLogin URM90040 → fallback loginStep1 → APP 拿到完整 envelope（id + next_step）→ APP 切到 OTP 屏 + 60 秒倒计时 |
| AC26 | AC25 后 60s 内用户输 OTP | verify_otp → loginStep2 → secondLogin(带 pwd) 成功 → queryAccountList → ACCOUNT_SELECTION_REQUIRED；预期 < 3s，0 次指纹验证；账号恢复 |

## 7. 改动文件清单

| 文件 | 改动 |
|---|---|
| `api/application/app/login/banks/easypaisa.py` | 5 处函数（line 1069 / 1248 / 2097 / 2446 / 3824 附近）+ STATUS_TRANSITIONS（line 88-91） |
| `docs/superpowers/specs/2026-05-14-easypaisa-login-redesign-design.md` | §3.1.1 / §3.2 / §3.3 / §3.4 / §3.5 / §3.8 / §7 patch |
| `api/tests/test_easypaisa_v19_pre_login.py` | 二次链路 mock 改 |
| `api/tests/test_easypaisa_v19_urm90040.py` | envelope 字段检查 |
| `api/tests/test_easypaisa_v19_verify_otp.py` | fallback 续推路径改 |
| `api/tests/test_easypaisa_v19_state_machine.py` | STATUS_TRANSITIONS 期望值改 |
| `api/tests/test_easypaisa_v19_e2e.py` | U3/U5/U8/U16 mock 改；新增 AC11/AC25/AC26 复现 |
| `api/tests/test_easypaisa_v19_change_pin.py` | **新增**：change_pin 续推 secondLogin(带 pwd) + queryAccountList 验证 |

## 8. 部署计划

```
Step 1: 改代码（5 处函数 + STATUS_TRANSITIONS）
Step 2: 跑测试 pytest tests/test_easypaisa_v19_*.py，全 PASS
Step 3: scp easypaisa.py → /www/python/api/application/app/login/banks/
Step 4: 备份到 .backup_v19_p0_<timestamp>/
Step 5: 滚动重启 30 端口（用 /tmp/rolling_restart_api.sh）
Step 6: 观察 5 分钟日志，确认无 ERROR 增多
Step 7: 03194834960 / 533302 真实账号验证 AC25/AC26
```

回滚预案：上次 scp 的备份 `easypaisa.py.worktree`(+ git-HEAD) 仍在远程 `.backup_v19_handoff_20260514-224521/`。

## 9. 不在本次范围内

- `wallet_status=1` 写入（独立 P1 项）
- `change_pin_http` PIN_CHANGE_LIMIT_EXCEEDED 走 `_force_terminal_needs_relogin`（P2）
- 业务接口（queryBalance / queryBill / transfer）不动
- MySQL payment 表结构不动
- APP 端不改

## 10. 风险与回滚

### 风险

- v1.9 文档 line 193-202 原文只说"PIN 错误时支持设置新 PIN"，URM90040 救冻是经验外推
  - **已实证**：2026-05-15 手动调云机验证 `secondLogin(phone, pwd)` 救 URM90040 一击成功（code=200）
- `change_pin_http` 内部续推可能引入新失败路径
  - 兜底：仍可被 `_force_terminal_needs_relogin` 终止

### 回滚

- 上次备份：`/www/python/api/.backup_v19_handoff_20260514-224521/easypaisa.py.worktree`（含运维改动）+ `easypaisa.py.git-HEAD`（干净版）
- 本次部署前再备份一份 `.backup_v19_p0_<timestamp>/`
- 滚动重启可中断（kill 脚本 PID）

## 11. APP 端兼容性

- envelope 补 `id` + `next_step` → APP exchange_api.dart `preLogin()` 能正常解析（line 193-202 + line 200-204）
- `code='SL_NEEDS_OTP'` → APP 已在 `controller.dart` line 497 识别（虽然仅在 `_runSecondLoginChain` 里）
- `_phaseAfterPreLogin` 对 easypaisa + `next_step='verify_otp'` 走 default → `OnboardingPhase.preLogin`
  - 不是 `awaitingOtp`，但因 envelope `data.code='SL_NEEDS_OTP'` 是 ApiError，会进 catch → `_applyError`
  - `_applyError` 当前 default 走 `OnboardingPhase.failed` ← 这里 APP 端**可选补一个 SL_NEEDS_OTP → awaitingOtp 的识别**
  - 但即使不补，APP 至少不会再进入指纹屏（当前 bug），所以 P0 服务端修复仍价值显著
- APP 后续补识别 SL_NEEDS_OTP 是 P1（不在本次 P0 范围）
