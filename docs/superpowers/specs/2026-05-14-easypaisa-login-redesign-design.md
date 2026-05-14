# EasyPaisa 上号流程重构设计

- **日期**: 2026-05-14
- **目标版本**: 对齐 EasyPaisa v1.9 云机 API
- **现状版本**: 代码中 `EASYPAISA_API_VERSION = 'v1.6'`
- **范围**: 仅上号链路（不动业务接口如 queryBalance/transfer/changePin）

## 1. 背景与问题

当前 `api/application/app/login/banks/easypaisa.py` 上号链路存在结构性问题：

- **状态机膨胀**：FINGERPRINT_UPLOAD_REQUIRED / FINGERPRINT_UPLOADED / FINGERPRINT_VERIFIED / SECOND_LOGIN_READY / SECOND_LOGIN_PASSED 等 9+ 状态相互纠缠
- **指纹流程混乱**：`_replay_saved_fingerprint` 嵌在 `verify_otp_http` 内部，让 OTP 接口承担了非自身职责
- **URM90040 死循环**：03445021275 的真实事故——secondLogin 报 URM90040 后无限循环 loginStep1→loginStep2，缺少限频
- **重复上号崩溃**：533264 的真实事故——已 active 账号再次调 pre_login 时，bound_payment 快速路径直接返回 `next_step:'second_login'`，触发"期望 fingerprintVerified，实际 activeSuccessful"状态转换错误
- **职责混淆**：`loginStep2` 同时承担 OTP 验证 + 指纹验证（取决于 `should_verify_fingerprint` 参数），导致错误难以归因

## 2. 设计目标

1. **接口职责单一**：每个上号 HTTP 接口只对应一个云机动作（或一段封闭的续推）
2. **状态机收敛**：用 8 个状态（含 AWAITING_PIN_CHANGE + NEEDS_RELOGIN 终态）覆盖三条主链路 + PIN 修改 + 强制下线路径
3. **故障可恢复**：所有指纹失败、OTP 失败、secondLogin 失败都有明确恢复路径，不出现死循环
4. **用户体验闭环**：失败时 APP 永远能拿到明确的 `next_step` 指引用户做下一步
5. **可对照 v1.9 文档**：每个云机调用直接映射到 v1.9 文档中的 action

## 3. 接口与状态机

### 3.1 状态枚举（8 状态）

| 状态 | 语义 | 是否终态 |
|---|---|---|
| `PRE_LOGIN_CREATED` | session 已建立，等待第一次驱动 | 否 |
| `OTP_SENT` | loginStep1 已发出 OTP，等用户输入 | 否 |
| `OTP_VERIFIED` | OTP 已通过 / 不需要 OTP，等待指纹激活 | 否 |
| `FINGERPRINT_VERIFIED` | verifyFingerprint 已通过，等待 secondLogin | 否 |
| `AWAITING_PIN_CHANGE` | secondLogin 返回 needs_pin_change，等用户改 PIN | 否 |
| `ACCOUNT_SELECTION_REQUIRED` | secondLogin + queryAccountList 已完成，等用户选 accno | 否 |
| `ACTIVE_SUCCESSFUL` | 上号完成 | **终态（成功）** |
| `NEEDS_RELOGIN` | 不可自动恢复（被锁号、session 过期、抢登失败超限等），需要人工或重新走 pre_login | **终态（失败）** |

**关键设计点（Blocker 5 修复）**：
- `NEEDS_RELOGIN` 是**真正的终态**，进入状态机邻接表（不再是"幽灵态"）
- 所有从其他状态进入 `NEEDS_RELOGIN` 都必须经过统一函数 `_force_terminal_needs_relogin(reason, error_code)`（见 §3.1.2）
- session 在进入 NEEDS_RELOGIN **之后才删除**——保留一个短暂时间窗（5 秒）方便 APP 拉取 last_error，然后 monitor cleanup 删 key
- 任何非终态都可以直接跳到 NEEDS_RELOGIN（这是合法的"逃生门"，但有统一入口）

### 3.1.1 STATUS_TRANSITIONS 邻接表

`_assert_status_transition` 严格按此表校验。任何跨步必须显式列出，否则状态推进会被拦下。

```python
STATUS_TRANSITIONS = {
    PRE_LOGIN_CREATED: [
        OTP_SENT,                       # pre_login 走首次分支
        ACCOUNT_SELECTION_REQUIRED,     # pre_login 二次内部续推：upload_data+verifyFingerprint+secondLogin+queryAccountList 全成功
        OTP_VERIFIED,                   # pre_login 二次续推：verifyFingerprint 失败的降级（借位）
        AWAITING_PIN_CHANGE,            # pre_login 二次续推：secondLogin 返回 needs_pin_change
        NEEDS_RELOGIN,                  # 任意失败（云机 501 非 URM90040、URM90040 计数超限、本地 ZIP 缺失）
    ],
    OTP_SENT: [
        OTP_VERIFIED,                   # verify_otp 首次分支
        ACCOUNT_SELECTION_REQUIRED,     # verify_otp fallback 续推全成功
        PRE_LOGIN_CREATED,              # URM90040 fallback 触发的 reset
        NEEDS_RELOGIN,                  # OTP 验证次数超限 / loginStep2 返回 501
    ],
    OTP_VERIFIED: [
        FINGERPRINT_VERIFIED,           # upload_fingerprint + verify_fingerprint 全成功
        NEEDS_RELOGIN,                  # verifyFingerprint 拒绝且重试超限（极端情况）
        # 普通指纹失败时状态不变（保持 OTP_VERIFIED）
    ],
    FINGERPRINT_VERIFIED: [
        ACCOUNT_SELECTION_REQUIRED,     # second_login 成功（含 queryAccountList）
        AWAITING_PIN_CHANGE,            # secondLogin 返回 needs_pin_change
        NEEDS_RELOGIN,                  # secondLogin 返回 501 非 URM90040 / URM90040 计数超限
    ],
    AWAITING_PIN_CHANGE: [
        FINGERPRINT_VERIFIED,           # change_pin_http 成功后回到指纹已验证态，APP 重调 second_login
        NEEDS_RELOGIN,                  # PIN_CHANGE_LIMIT_EXCEEDED
    ],
    ACCOUNT_SELECTION_REQUIRED: [
        ACTIVE_SUCCESSFUL,              # select_accts 成功
        NEEDS_RELOGIN,                  # select_accts 时云机突然返回 501（罕见）
    ],
    ACTIVE_SUCCESSFUL: [],              # 终态，无后续
    NEEDS_RELOGIN: [],                  # 终态，无后续
}
```

**跨步设计的理由**：
- `PRE_LOGIN_CREATED → ACCOUNT_SELECTION_REQUIRED`：二次上号 pre_login 内部一气呵成，外部观察就是跨过了 OTP/指纹/secondLogin 三个中间态
- `OTP_SENT → ACCOUNT_SELECTION_REQUIRED`：URM90040 fallback 的 verify_otp 内部一气呵成
- `PRE_LOGIN_CREATED → OTP_VERIFIED`：二次上号 verifyFingerprint 失败时把状态降到 OTP_VERIFIED 让 APP 走 upload_fingerprint 重试（借位，避免重走 OTP）
- `OTP_SENT → PRE_LOGIN_CREATED`：URM90040 fallback 触发时把状态打回起点重新走 loginStep1
- `* → NEEDS_RELOGIN`：所有非终态都可以跳到 NEEDS_RELOGIN，但必须经过 §3.1.2 统一函数

### 3.1.2 _force_terminal_needs_relogin 统一终止函数

**问题**：当前代码 `redis.delete(redis_key) + raise NewApiError(..., {'phase': 'needsRelogin'})` 这个模式在 5+ 处分散（line 1984/2144/2150/2167/2191 等）。每处都自己组装报错结构，缺乏统一可观测性。

**新方案**：所有"账户终结进入 needsRelogin"必须经过唯一函数：

```python
async def _force_terminal_needs_relogin(
    self,
    redis_key: str,
    session_data: dict,
    reason: str,                # 日志原因，如 "SecondLogin returned 501 URM00001"
    error_code: str,            # APP 错误码，如 "SL_NEEDS_RELOGIN" / "SL_UPSTREAM_ERROR"
    message: str | None = None, # 给用户的提示文案
):
    """
    统一终止入口。所有 needsRelogin 必须通过这里：
    ① 写状态推进日志：[funcName] 状态推进: {current} → NEEDS_RELOGIN, reason={reason}
    ② 更新 session.status = NEEDS_RELOGIN（不立即删，让 5 秒内 APP 仍可读 last_error）
    ③ session.last_error = {code, message, reason, timestamp}
    ④ 推送到 monitor 告警通道（按 reason 维度统计）
    ⑤ 调度 5 秒后异步删 redis_key（APP 在窗口内通过 payment_status_http 读 last_error）
    ⑥ 返回标准化错误体: {
         'status': 'error',
         'message': message or '账户需要重新登录',
         'data': {'code': error_code, 'phase': 'needsRelogin'}
       }

    禁止：
    - handler 直接调 redis.delete(redis_key) + 自己写 needsRelogin 错误体
    - handler 跳过 _assert_status_transition 强写状态
    """
```

**所有调用点列表**（重构时必须改成调这个函数）：
- pre_login_http 二次续推 secondLogin 501 非 URM90040 → `_force_terminal_needs_relogin(reason='secondLogin 501 + msgCd=URM..', error_code='SL_NEEDS_RELOGIN')`
- pre_login_http URM90040 计数超限 → `error_code='SL_NEEDS_RELOGIN', reason='URM90040 count exceeded'`
- verify_otp_http fallback 内 secondLogin 失败 → `error_code='SL_NEEDS_RELOGIN', reason='Fallback secondLogin failed'`
- verify_fingerprint_http session 过期 → `error_code='FP_SESSION_EXPIRED', reason='Session expired during verify'`
- second_login_http secondLogin 返回 needs_relogin → `error_code='SL_NEEDS_RELOGIN', reason='SecondLogin returned needs_relogin'`
- change_pin_http PIN_CHANGE_LIMIT_EXCEEDED → `error_code='PIN_CHANGE_LIMIT_EXCEEDED', reason='Pin change limit'`
- 二次上号本地 ZIP 文件丢失 → `error_code='EP_FP_FILE_MISSING', reason='Local ZIP file missing'`

**可观测性收益**：
- 单一 grep `_force_terminal_needs_relogin` 即可看到所有终止点
- 按 reason 聚合统计，能定位 "本周 URM90040 超限 N 次" 这类问题
- session 不立即删 → APP 在 5 秒内仍可读 last_error，避免 "知道失败了但不知道原因" 的盲态
- 单元测试只需 mock 一个函数验证终止行为，不用满 handler 找 redis.delete

### 3.2 接口职责

**重要：APP 端已在生产使用 9 个接口**（见 §13 APP 端真实调用清单）。本次重构**保留所有 9 个接口**，只修改内部行为，不合并接口、不删 controller 路由。

| 接口 | 入参 | 入态校验 | 出态 | 内部动作 |
|---|---|---|---|---|
| `pre_login_http` | `bankname/phone/password/pin/name/step`（+可选 `payment_id`） | 任意 | `PRE_LOGIN_CREATED`（首次）或 `ACCOUNT_SELECTION_REQUIRED`（二次） | ①**码商交易密码 bcrypt 校验** ②MySQL payment 权威校验 ③已 ACTIVE 返回 ready ④`isAccountRegistered` 分流：false → 仅创建 session，返回 `next_step:'send_otp'`；true → 内部续推（upload_data+verifyFingerprint+secondLogin+queryAccountList） |
| `get_otp_http` | `bankname/payment_id` | `PRE_LOGIN_CREATED` | `OTP_SENT` | 调云机 `loginStep1`；20s 节流，幂等重发 |
| `verify_otp_http` | `bankname/payment_id/otp` | `OTP_SENT` | `OTP_VERIFIED`（首次）或 `ACCOUNT_SELECTION_REQUIRED`（fallback） | `loginStep2(should_verify_fingerprint=false)`；fallback 标记则续推 4 步 |
| `upload_fingerprint_http` | `bankname/payment_id/phone` + multipart 字段 **`files`**（不是 `file`，对齐 APP exchange_api.dart line 245） | `OTP_VERIFIED` 或 `awaitingFingerprintUpload` | 不变（仍 `OTP_VERIFIED`） | 保存 ZIP 到 Redis pending（key=`easypaisa:pending_fp:{payment_id}` TTL 600s）；**不**写本地、**不**调云机。APP 传入 phone 仅做与 MySQL.phone 的合法性比对（不匹配返回 EP_PAYMENT_PHONE_MISMATCH），实际推云机用 MySQL.phone |
| `verify_fingerprint_http` | `bankname/payment_id` | `OTP_VERIFIED`（pending ZIP 存在） | `FINGERPRINT_VERIFIED` | ①读 Redis pending ZIP ②`upload_data` 推云机 ③`verifyFingerprint` 验证 ④**全成功才**落地 `/fingerprint/easypaisa_<payment>_<phone>.zip` + 写 MySQL `payment.fingerprint_path` + 删 Redis pending |
| `second_login_http` | `bankname/payment_id` | `FINGERPRINT_VERIFIED` | `ACCOUNT_SELECTION_REQUIRED` 或 `AWAITING_PIN_CHANGE` | `secondLogin` + `queryAccountList`；needs_pin_change → AWAITING_PIN_CHANGE |
| `change_pin_http` | `bankname/payment_id/pin` | `AWAITING_PIN_CHANGE` | `FINGERPRINT_VERIFIED` | `changePinStep1` → `changePinStep2`；APP 端自动重调 second_login_http（见 §3.8） |
| `query_accts_http` | `bankname/payment_id` | `ACCOUNT_SELECTION_REQUIRED` | 不变 | 读 `session.account_entire`（已由 second_login 填入）直接返回；不再调云机 queryAccountList |
| `select_accts_http` | `bankname/payment_id/accno` | `ACCOUNT_SELECTION_REQUIRED` | `ACTIVE_SUCCESSFUL` | 写 MySQL `payment.account_accno` + 加 `hash_easypaisa` + 删 Redis prelogin |
| `payment_status_http` | `bankname/payment_ids`（**复数**字段名，值为**逗号分隔字符串** `"id1,id2,id3"`，单 payment 也用逗号写法 `"id1"`） | 无 | 不动状态 | split(',') 解析 → 并发查询所有 payment 的 Redis prelogin session → 返回 `datas[]` 数组（即使单 payment）。每项含 `status` + `next_action` + `cd_until` + `error` |

**关键设计点**：
- **指纹两阶段**：APP 显式调 `upload_fingerprint` → `verify_fingerprint` 两步，与 APP 端 controller.dart 现有交互对齐（line 408 `_runPostFingerprintChain`）。upload 只暂存 Redis，verify 才真正推云机并落盘
- **OTP 独立步骤**：`pre_login` 不再内嵌 loginStep1。首次上号 APP 必须显式调 `get_otp`
- **二次上号续推**：`pre_login` 内部跑 4 步云机调用，状态直接跳到 `ACCOUNT_SELECTION_REQUIRED`（与 APP `_phaseAfterPreLogin` line 741 现有逻辑一致）
- **change_pin 后**：服务端把状态置为 `FINGERPRINT_VERIFIED`，APP 自己调 `second_login_http`（与 APP controller.dart line 665-668 现有逻辑一致）

### 3.3 pre_login_http 分支逻辑

**入参签名保持不变**：`bankname/phone/password/pin/name`（+可选 `payment_id`、`is_new_user`、`partner_id`）。首次注册时创建 payment 需要这些字段；controller 层不动。

```
进入:
  ① 必填字段校验 [bankname, phone, password, pin, name]，任何缺失 → EP_MISSING_PARAMS
  ② 手机号格式校验（_validate_phone_number 11位以03开头）
  ③ 交易密码 bcrypt 校验（_verify_payment_password_bcrypt）
     失败 → EP_INVALID_PASSWORD，触发登录失败计数
  ④ 登录失败计数检查（_check_login_failed_attempts），超限 → EP_LOGIN_ATTEMPS
  ⑤ payment-level / phone-level 双重 Redis 锁检查（避免并发上号）
     已锁 → EP_LOGINED

  ⑥ MySQL payment 权威校验:
     - 如果 data.payment_id 存在：
         payment 不存在 → EP_PAYMENT_NOT_FOUND
         partner_id 不匹配 → EP_PERMISSION_DENIED
         phone 与传入 data.phone 不一致 → EP_PAYMENT_PHONE_MISMATCH
     - 如果 data.payment_id 不存在（首次注册）：
         检查同 phone+partner_id 是否已存在 payment（避免重复创建）

  ⑦ 查 MySQL `Payment.wallet_status`：== 1（已 active）
     → 返回 {status:'success', data:{next_step:'ready', phase:'activeSuccessful'}}
     // 533264 的修复点；不走任何后续流程；不创建 session
     // 注：项目无 runtime_snapshot Redis 层；MySQL Payment.wallet_status 是"是否在线"的唯一权威来源。

  ⑦.1 残留 session 检测（关键：避免无声覆盖用户进度，见 §3.3.1）
     existing = redis.get(PRELOGIN_KEY)
     if existing 存在且 status 在 {OTP_SENT, OTP_VERIFIED, FINGERPRINT_VERIFIED,
                                    AWAITING_PIN_CHANGE, ACCOUNT_SELECTION_REQUIRED}:
       → 复用 session，**不覆盖**；读 existing.status 反查 NEXT_STEP_MAP
       → 返回 {status:'success', data:{
                 next_step: <对应状态的下一步>,
                 phase: existing.status,
                 resumed: true,                  // 标志：APP 知道这是接续
                 expires_in: redis_ttl_remaining // session 剩余秒数
              }}
       // APP 拿到 resumed:true 时可以根据 phase 直接跳到对应 UI 屏（接续上次进度）

     if existing 存在且 status == PRE_LOGIN_CREATED:
       → 视为"上次 pre_login 没走 get_otp 就断了"，直接覆盖（无进度可保留）

     if existing 存在且 status == ACTIVE_SUCCESSFUL 但 MySQL wallet_status != 1:
       → MySQL 已离线但 Redis 还残留成功态；删 prelogin key，进入 ⑧

  ⑧ 创建 Redis session（PRELOGIN_KEY），状态 PRE_LOGIN_CREATED
     session 内填入 phone/pinCode/partner_id/bankname/name
     // 此处不再有残留 session（被 ⑦.1 排除）

  ⑨ 调云机 isAccountRegistered(phone)

isAccountRegistered = false（首次上号）:
  ⑩ 仅完成 session 初始化，**不调 loginStep1**
  ⑪ 返回 {next_step:'send_otp', is_new_user:true, payment_id:<id>}
     // APP 收到后显式调 get_otp_http 让服务端发 OTP
     // 首次链路：APP 走 get_otp → verify_otp → upload_fingerprint → verify_fingerprint → second_login → select_accts

isAccountRegistered = true（二次上号）:
  // 前提：云机已注册 ↔ 我们必然存过 ZIP（云机永久托管，不会消失）
  // 边界：若本地 ZIP 文件被运维误删/磁盘故障 → 直接 needsRelogin 报警，等人工介入
  ⑩ 自动续推（注：APP 端 controller.dart line 741 已识别 `next_step:'second_login'` 并直接进入 secondLogin chain）:
     a. upload_data 推本地 ZIP
        失败 → 状态保持 PRE_LOGIN_CREATED，返回 EP_FP_PUSH_FAIL
     b. verifyFingerprint
        失败 → 状态跳到 OTP_VERIFIED（借位），返回 {next_step:'upload_fingerprint', code:'FP_UPSTREAM_REJECTED'}
        // 让用户走 upload_fingerprint + verify_fingerprint 重新激活指纹，无需重走 OTP
        // 错误码与 APP controller.dart line 431 已识别 'FP_UPSTREAM_REJECTED' 对齐
     c. secondLogin
        code=501 + msgCd=URM90040 → §3.5 fallback
        code=501 其他 msgCd → _force_terminal_needs_relogin(reason='secondLogin 501 msgCd=<x>', error_code='SL_NEEDS_RELOGIN')
        msgCd=URM20008/URM20017 → 状态 AWAITING_PIN_CHANGE，返回 {code:'SL_NEEDS_PIN_CHANGE'}（APP line 504 已识别）
        其他错（非 200 非 501） → _force_terminal_needs_relogin(reason='secondLogin upstream error', error_code='SL_UPSTREAM_ERROR')
        成功 → 进 d
     d. queryAccountList
        失败 → 状态升到 FINGERPRINT_VERIFIED
              返回 EP_QUERY_FAIL；APP 调 second_login_http 重试 secondLogin+queryAccountList
        成功 → 状态 ACCOUNT_SELECTION_REQUIRED
  ⑪ 返回 {next_step:'second_login'}
     // 注：APP 端 _phaseAfterPreLogin (line 741) 现有逻辑识别 'second_login' → awaitingSecondLogin → _runSecondLoginChain
     // 由于服务端已经把 queryAccountList 完成、状态已是 ACCOUNT_SELECTION_REQUIRED，APP 的 secondLogin 调用会拿到 success → query_accts → 选账号
     // 二次链路：APP 调 pre_login → second_login → query_accts → select_accts 四步

性能预期:
- 首次上号：pre_login 只做 session 初始化 + isAccountRegistered ≈ 1-2 秒
- 二次上号：pre_login 内部 4 步串行 ≈ 5-8 秒（峰值，受云机端 RT 影响）
  → APP 端必须设置 30 秒 client timeout
  → APP 端展示 "正在恢复账号..." loading 文案

性能不达标时的降级:
  二次上号续推超时（>20 秒未完成）→ 只完成 isAccountRegistered+secondLogin（跳过 queryAccountList）
  返回 {next_step:'query_accts'}；APP 自己调 query_accts_http
  （APP 现有 _runQueryAndSelect line 552 已支持）
```

### 3.3.1 残留 session 复用协议（解决"幽灵覆盖"问题）

**问题**：当前代码 (line 1444-1458) 对残留非 ACTIVE session 一律返回 `Logined3/Logined4` 错误，等于把用户锁死直到 TTL（10 分钟）过期。用户体验是"无法操作必须等"。

**新方案：复用 session + next_step 引导接续**

`NEXT_STEP_MAP`（残留状态 → APP 应调下一步）：

```python
NEXT_STEP_MAP = {
    PRE_LOGIN_CREATED:          'send_otp',           # APP 重新调 get_otp_http
    OTP_SENT:                   'verify_otp',         # APP 输 OTP
    OTP_VERIFIED:               'upload_fingerprint', # APP 重新采集指纹（如有 pending ZIP 可直接 verify）
    FINGERPRINT_VERIFIED:       'second_login',       # APP 调 second_login_http
    AWAITING_PIN_CHANGE:        'change_pin',         # APP 引导改 PIN
    ACCOUNT_SELECTION_REQUIRED: 'select_accts',       # APP 显示账号列表（用 session.account_entire）
}
```

**特殊处理**：
- 复用 session 时 **TTL 不刷新**（保持原过期时间，避免无限延长）
- 复用前必须做"状态合理性校验"：session.phone 必须等于 MySQL payment.phone，否则视为脏数据，删除后按 ⑧ 创建新 session
- 复用时**不重做交易密码 bcrypt 校验**（用户已校验过，重做反而拖慢；但如果用户密码改了用户体验稍差，可后续优化）

**APP 端协议**：
- 服务端响应增加 `resumed: true` 字段
- APP 检测到 `resumed: true` 后跳过表单页，直接根据 `phase` 跳到对应 UI 屏：
  - phase=`OTP_SENT` → /onboarding/otp
  - phase=`OTP_VERIFIED` → /onboarding/fingerprint
  - phase=`FINGERPRINT_VERIFIED` → 直接调 second_login_http
  - phase=`AWAITING_PIN_CHANGE` → /onboarding/change-pin
  - phase=`ACCOUNT_SELECTION_REQUIRED` → /onboarding/accounts（用 server 返回的 accounts）
- 服务端响应需带回 `accounts` 字段（仅 ACCOUNT_SELECTION_REQUIRED 时），让 APP 无需再调 query_accts 就能显示

**`account_entire` 复用**：当 phase == `ACCOUNT_SELECTION_REQUIRED` 时，从 session 读 `account_entire` 直接返回给 APP（与 query_accts_http stub 相同）

**APP 端改动需求**（最小化）：
- exchange_api.dart `PreLoginResult` 增加 `resumed: bool` 和 `phase: String` 字段
- onboarding_controller.dart `submitForm()` 在 `resumed: true` 时跳过常规 `_phaseAfterPreLogin` 逻辑，根据 phase 路由到对应 UI

**降级方案**（如 APP 端来不及改）：
- 如果 APP 没识别 `resumed`，照旧把 `next_step` 当成普通字段处理 → 调对应接口 → 状态本来就在那里，自然继续——**无故障 fallback**

### 3.3.2 get_otp_http 分支逻辑

```
进入:
  ① 必填字段校验 [bankname, payment_id]
  ② 状态校验 = PRE_LOGIN_CREATED；其他状态返回 EP_BAD_STATE
  ③ 节流检查：session.sendOTPTime 与当前时间差 < 20s → 返回 EP_THROTTLED（idempotent，不调云机）
  ④ 调云机 loginStep1
     code=100 → 状态 → OTP_SENT，更新 session.sendOTPTime
     code != 100 → 保持 PRE_LOGIN_CREATED，返回对应错误
  ⑤ 返回 {next_step:'verify_otp', expires_in:120}
```

### 3.4 verify_otp_http 分支逻辑

**对齐 APP 端**：APP 期望返回 `next_phase: 'fingerprintUploadRequired'` 或 `'fingerprintUploaded'`（见 exchange_api.dart line 30-46）。新设计：
- 首次上号 → `next_phase: 'fingerprintUploadRequired'`（APP 切到 `awaitingFingerprintUpload` UI，等用户采集指纹）
- fallback 路径全成功 → `next_step: 'select_accts'` 跳过指纹 UI（特殊路径）

```
进入:
  ① 校验状态 = OTP_SENT
  ② 调 loginStep2(otpcode, should_verify_fingerprint=false)
     OTP 错（URM30105 / 类似 msgCd）→ 状态保持 OTP_SENT，返回 EP_OTP_INVALID（错误码 20307，APP line 321 识别）
     成功 → 进 ③

session.is_new_user = true（首次上号）:
  ③ 状态 → OTP_VERIFIED
  ④ 返回 {next_phase:'fingerprintUploadRequired', payment_id:<id>}
     // APP 切到 awaitingFingerprintUpload UI，启动 Veridium 采集用户指纹

session.fallback_from_urm90040 = true（fallback 路径）:
  ③ 状态 → OTP_VERIFIED
  ④ 自动续推:
     a. upload_data 推本地 ZIP
        失败 → 状态保持 OTP_VERIFIED，返回 {next_phase:'fingerprintUploadRequired', code:'FP_UPSTREAM_REJECTED'}
        // 用户走 upload_fingerprint → verify_fingerprint 重做指纹
     b. verifyFingerprint
        失败 → 状态保持 OTP_VERIFIED，返回 {next_phase:'fingerprintUploadRequired', code:'FP_UPSTREAM_REJECTED'}
     c. secondLogin
        code=501 + msgCd=URM90040 → _force_terminal_needs_relogin(reason='fallback secondLogin URM90040 again', error_code='SL_NEEDS_RELOGIN')
        code=501 其他 msgCd → _force_terminal_needs_relogin(reason='fallback secondLogin 501 msgCd=<x>', error_code='SL_NEEDS_RELOGIN')
        msgCd=URM20008/URM20017 → 状态 AWAITING_PIN_CHANGE，返回 {code:'SL_NEEDS_PIN_CHANGE'}
        其他错 → _force_terminal_needs_relogin(reason='fallback secondLogin upstream', error_code='SL_UPSTREAM_ERROR')
        成功 → 进 d
     d. queryAccountList
        失败 → 状态升到 FINGERPRINT_VERIFIED，返回 EP_QUERY_FAIL；APP 调 second_login_http 重试
        成功 → 状态 ACCOUNT_SELECTION_REQUIRED
  ⑤ 返回 {next_phase:'fingerprintUploaded', next_step:'second_login'}
     // 注：APP 收到 'fingerprintUploaded' → 切到 verifyingFingerprint → 调 verify_fingerprint
     // 但服务端这一路径状态已是 ACCOUNT_SELECTION_REQUIRED，verify_fingerprint 调用应直接返回 ok（已激活）
     // 替代方案：返回特殊 next_phase（需要 APP 端扩展支持），让 APP 跳过指纹直接选账号

⚠ fallback 路径与 APP 现有逻辑的冲突点:
APP exchange_api.dart line 30-46 仅识别 `fingerprintUploaded` / `fingerprintUploadRequired` 两个 next_phase。
fallback 路径全成功后 APP 仍会调 verify_fingerprint，服务端在此场景下需要识别"状态已是 ACCOUNT_SELECTION_REQUIRED"并直接返回 ok（详见 §3.6.1 verify_fingerprint 幂等行为）。
```

### 3.4.1 upload_fingerprint_http 分支逻辑

**字段约定**：multipart 字段名必须是 **`files`**（复数，与 APP exchange_api.dart line 245 对齐）。当前代码 line 2409 用 `data.pop("file", None)` 是错的，重构时改为 `files`。

```
进入:
  ① 必填字段校验 [bankname, payment_id, phone, files]，缺任一 → EP_MISSING_PARAMS
  ② 状态校验 = OTP_VERIFIED；其他状态返回 EP_BAD_STATE
  ③ 文件类型校验（zip，content-type 是 application/zip）、大小校验（<16MB）
  ④ MySQL payment.phone 与入参 phone 比对（防越权写入指纹到他人账号）:
     不匹配 → EP_PAYMENT_PHONE_MISMATCH
     // 实际推云机时用 MySQL.phone（权威），APP 传的 phone 仅做合法性校验
  ⑤ 把 ZIP body 读到内存，存入 Redis pending key:
     easypaisa:pending_fp:{payment_id} TTL 600s
     // ZIP 字节数比 session 大，单独 key 存储
  ⑥ 状态保持 OTP_VERIFIED（不推进；APP UI 切到 verifyingFingerprint 等用户点验证）
  ⑦ 返回 {phase:'fingerprintUploaded', next_step:'verify_fingerprint'}
```

### 3.5 URM90040 fallback 策略

**触发**：`secondLogin` 在 pre_login_http 内部续推阶段返回 URM90040

```
key: easypaisa:urm90040_count:{payment_id}
TTL: 3600（1 小时）
上限: 3 次/小时

count ≤ 3:
  count += 1
  Redis session.fallback_from_urm90040 = true
  状态 reset → PRE_LOGIN_CREATED
  **服务端内部直接调 loginStep1 发 OTP（APP 不需要调 get_otp_http）**
  状态 → OTP_SENT
  返回 {next_step:'verify_otp', code:'SL_NEEDS_OTP', expires_in:120}
  // 之后 APP 拿到 SL_NEEDS_OTP，弹提示"账号被抢登已重新发 OTP"，直接进 OTP 屏
  // 用户输 OTP 调 verify_otp_http，走 fallback 分支（§3.4 fallback 路径）
  // 与当前代码 line 2158 行为一致——pre_login 内部自己调 _send_otp，不依赖 APP

count > 3:
  _force_terminal_needs_relogin(
      reason='URM90040 count exceeded 3/hour',
      error_code='SL_NEEDS_RELOGIN',
      message='账号疑似被频繁占用，请联系运维介入'
  )
```

### 3.6 指纹两阶段提交（upload + verify）

**原则**：APP 显式调两个接口完成指纹环节。
- `upload_fingerprint_http`：只接收 ZIP 存 Redis pending（详见 §3.4.1）
- `verify_fingerprint_http`：推云机 + 验证 + 成功才落盘

**verify_fingerprint_http 内部执行**：

```
verify_fingerprint_http(bankname, payment_id):
  ① 必填字段校验 [bankname, payment_id]
  ② 状态校验 = OTP_VERIFIED；其他状态见 §3.6.1 幂等行为
  ③ 从 MySQL 查 payment_id → 取 payment.phone（权威 phone）
     payment 不存在 → 返回 {code:'10301'}（APP paymentNotFound）
  ④ 读取 Redis pending key easypaisa:pending_fp:{payment_id}
     不存在 → 返回 {code:'FP_UPSTREAM_REJECTED', message:'No pending fingerprint'}
            // 用户被引导重新调 upload_fingerprint
  ⑤ 调云机 upload_data（使用 MySQL payment.phone 作为 phone 参数，不是 session 或 APP 传的）
       响应 != 'ok' → 返回 {code:'FP_UPSTREAM_REJECTED'}，pending 保留，老 ZIP 不动
  ⑥ 调云机 verifyFingerprint（同样用 MySQL payment.phone）
       code != 200 → 返回 {code:'FP_UPSTREAM_REJECTED', message:<msgCd>}，pending 保留，老 ZIP 不动
       URM40008 → 返回 {code:'FP_COOLDOWN', cd_until:<ts>}
  ⑦ 全成功 → 把 pending ZIP 落地到 /fingerprint/easypaisa_<payment>_<phone>.zip + 写 MySQL payment.fingerprint_path + 删 pending key
       落地失败 → 返回 {code:'EP_SYSTEM_ERROR'}，pending 保留（运维需人工补救）
  ⑧ 更新状态 → FINGERPRINT_VERIFIED
  ⑨ 返回 {ok:true, phase:'fingerprintVerified'}
```

**好处**：
- 与 APP 现有 controller.dart line 408 调用习惯对齐，零侵入
- 失败时老的本地权威 ZIP 100% 不被污染（验证通过才落盘）
- 用户失败重做 = 重启 Veridium 采集 → 重调 upload_fingerprint + verify_fingerprint
- pending ZIP 10 分钟自动过期，无需 GC

**失败可恢复矩阵**：

| 失败点 | 状态 | APP 收到 code | APP 行为（controller.dart 已识别） |
|---|---|---|---|
| pending 不存在（直接调 verify 没先 upload） | `OTP_VERIFIED` | `FP_UPSTREAM_REJECTED` | 切回 awaitingFingerprintUpload |
| upload_data 推失败 | `OTP_VERIFIED` | `FP_UPSTREAM_REJECTED` | 切回 awaitingFingerprintUpload |
| verifyFingerprint 拒绝 | `OTP_VERIFIED` | `FP_UPSTREAM_REJECTED` | line 431，切回 awaitingFingerprintUpload + 标 lastFailureCause |
| 云机冷却 | `OTP_VERIFIED` | `FP_COOLDOWN` | line 448，切到 inCooldown + 启动轮询 |
| Session 过期 | 删除 session | `FP_SESSION_EXPIRED` | line 441，切到 needsRelogin |
| 本地磁盘写失败 | `OTP_VERIFIED` | `EP_SYSTEM_ERROR` | 走默认错误分支 |
| 全成功 | `FINGERPRINT_VERIFIED` | `ok:true` | 进入 secondLogin chain |

### 3.6.1 verify_fingerprint_http 幂等行为

**问题**：fallback 路径（§3.4）的 verify_otp 内部续推成功后，状态已是 `ACCOUNT_SELECTION_REQUIRED`，APP 端仍会调 verify_fingerprint（因为它识别到 `next_phase: 'fingerprintUploaded'`）。这次调用怎么响应？

**方案**：verify_fingerprint_http 检测到状态已经过 `FINGERPRINT_VERIFIED`（即已是 `FINGERPRINT_VERIFIED` / `ACCOUNT_SELECTION_REQUIRED` / `ACTIVE_SUCCESSFUL`），直接返回 `{ok:true}` 不调云机（幂等）。这样 APP 流程畅通，避免重复推 ZIP 浪费云机带宽。

### 3.7 状态轨迹示意

所有路径"接口数"按 APP 显式调用次数计算（pre_login 内部续推算 1 次接口）。**upload_fingerprint 与 verify_fingerprint 严格成对出现**（§3.6 两阶段提交）。

```
首次上号（APP 调 7 个接口）:
  pre_login → get_otp → verify_otp → upload_fingerprint → verify_fingerprint → second_login → select_accts
  PRE_LOGIN_CREATED → OTP_SENT → OTP_VERIFIED →（pending ZIP 存 Redis）OTP_VERIFIED → FINGERPRINT_VERIFIED 
  → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL

二次上号（APP 调 2 个接口）:
  pre_login → select_accts
  PRE_LOGIN_CREATED → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL
  // pre_login 内部续推: upload_data + verifyFingerprint + secondLogin + queryAccountList

二次上号指纹失败（APP 调 5 个接口）:
  pre_login（内部 verifyFingerprint 失败 → 状态降到 OTP_VERIFIED） 
    → upload_fingerprint（暂存 pending ZIP） 
    → verify_fingerprint（推云机 + 落盘） 
    → second_login（secondLogin + queryAccountList） 
    → select_accts
  PRE_LOGIN_CREATED → OTP_VERIFIED → OTP_VERIFIED → FINGERPRINT_VERIFIED 
  → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL

URM90040 fallback（APP 调 4 个接口）:
  pre_login（secondLogin URM90040 → fallback reset → loginStep1） 
    → get_otp（如果服务端已发，APP 仍调一次幂等 / 或服务端在 fallback 时已发，APP 跳过此步） 
    → verify_otp（fallback 标记，内部续推 4 步全成功） 
    → select_accts
  PRE_LOGIN_CREATED → OTP_SENT → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL
  // verify_otp 内部续推: upload_data + verifyFingerprint + secondLogin + queryAccountList
  // 注：APP exchange_api.dart 没有"fallback 路径直接跳到 select_accts"的特殊分支，需要 §3.4 决定 verify_otp 返回值如何引导 APP

URM90040 fallback 指纹失败（APP 调 7 个接口）:
  pre_login → get_otp → verify_otp（内部 verifyFingerprint 失败 → 状态保持 OTP_VERIFIED） 
    → upload_fingerprint（暂存） 
    → verify_fingerprint（推云机 + 落盘） 
    → second_login 
    → select_accts
  PRE_LOGIN_CREATED → OTP_SENT → OTP_VERIFIED → FINGERPRINT_VERIFIED 
  → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL

PIN 错误（二次上号场景）:
  pre_login（内部 secondLogin 返回 needs_pin_change）
  PRE_LOGIN_CREATED → AWAITING_PIN_CHANGE
  ↓
  change_pin_http(step1+step2) 用户输入新 PIN
  AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED  // 跳回指纹已验证态
  ↓
  second_login_http（APP controller line 668 自动调用）
  FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED
  ↓
  select_accts_http → ACTIVE_SUCCESSFUL ✓

NEEDS_RELOGIN 终态（任意非终态都可触发，必经 _force_terminal_needs_relogin）:
  <任意非终态> → NEEDS_RELOGIN
  ↓
  5 秒内: APP 可调 payment_status 拉 last_error
  5 秒后: monitor cleanup 删除 Redis prelogin key
  ↓
  APP 引导用户重新走 pre_login（视为新一轮上号）

残留 session 复用（Blocker 4 修复）:
  APP 中途断了（如 OTP_VERIFIED 时关闭 APP）
  ↓ 3 分钟后用户重新打开 APP
  pre_login_http → 检测到残留 session.status=OTP_VERIFIED
  ↓
  返回 {resumed:true, phase:'otpVerified', next_step:'upload_fingerprint', expires_in:<剩余秒数>}
  ↓
  APP 跳到 /onboarding/fingerprint UI → 继续上传指纹 → 后续流程不变
```

### 3.7.1 路径与接口对应表（含状态转换可视化）

| 路径 | APP 接口序列 | 状态转换边 |
|---|---|---|
| **首次上号** | `pre_login` → `get_otp` → `verify_otp` → `upload_fingerprint` → `verify_fingerprint` → `second_login` → `select_accts` | `PRE_LOGIN_CREATED → OTP_SENT → OTP_VERIFIED → (OTP_VERIFIED) → FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL` |
| **二次上号** | `pre_login` → `select_accts` | `PRE_LOGIN_CREATED → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL` |
| **二次上号指纹失败** | `pre_login` → `upload_fingerprint` → `verify_fingerprint` → `second_login` → `select_accts` | `PRE_LOGIN_CREATED → OTP_VERIFIED → (OTP_VERIFIED) → FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL` |
| **URM90040 fallback** | `pre_login` → `verify_otp` → `select_accts` (服务端 pre_login 内部触发 loginStep1，APP 不调 get_otp) | `PRE_LOGIN_CREATED → OTP_SENT → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL` |
| **URM90040 fallback 指纹失败** | `pre_login` → `verify_otp` → `upload_fingerprint` → `verify_fingerprint` → `second_login` → `select_accts` | `PRE_LOGIN_CREATED → OTP_SENT → OTP_VERIFIED → (OTP_VERIFIED) → FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL` |
| **PIN 修改** | `pre_login` → `change_pin` → `second_login` → `select_accts` | `PRE_LOGIN_CREATED → AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED → ACTIVE_SUCCESSFUL` |
| **已 active 重复 pre_login** | `pre_login`（立即返回 ready） | （不动状态） |

**括号中的状态**（如 `(OTP_VERIFIED)`）表示 `upload_fingerprint` 完成后状态保持不变（不推进到 FINGERPRINT_VERIFIED），需要等 `verify_fingerprint` 推云机成功才推进。

### 3.8 change_pin_http 流程

**本次重构不修改 change_pin_http 实现**，但状态机要将它纳入。当前代码 line 2244 + controller line 234 已存在，仅需保留并对接新状态机。

**触发**：secondLogin 返回 `needs_pin_change`（来自 pre_login 内部续推 / fallback 内部续推 / 显式 second_login_http 调用三个路径之一）

**状态推进**：

```
触发点 → 设置状态 AWAITING_PIN_CHANGE，返回 {next_step:'change_pin'}
APP: change_pin_http(payment_id, new_pin)
  ① 校验状态 = AWAITING_PIN_CHANGE
  ② 调云机 changePinStep1 → 获 OTP
  ③ APP 用户输入 OTP
  ④ 调云机 changePinStep2(otp, new_pin) → PIN 已更新
  ⑤ 写 MySQL payment.pin = new_pin
  ⑥ 状态 AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED
  ⑦ 返回 {next_step:'second_login'}

之后 APP 调 second_login_http 重新走 secondLogin（此次用新 PIN）→ ACCOUNT_SELECTION_REQUIRED → select_accts → ACTIVE

PIN 修改失败:
- changePinStep1 失败 → 状态保持 AWAITING_PIN_CHANGE，返回 EP_CHANGE_PIN_FAIL，APP 重试
- changePinStep2 失败（OTP 错） → 同上，重试 step2 即可
- 多次失败超阈值（PIN_CHANGE_LIMIT_EXCEEDED） →
  _force_terminal_needs_relogin(reason='Pin change limit exceeded', error_code='PIN_CHANGE_LIMIT_EXCEEDED')
```

**注意事项**：
- change_pin_http 当前代码 step1+step2 是一个接口内同步走完，APP 输入 OTP 是中间环节（与 EasyPaisa changePin 接口拆分一致）
- 本次重构**不动 change_pin_http 内部实现**，但 STATUS_TRANSITIONS 要包含 `AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED` 这条边

### 3.9 数据来源权威表

**原则**：MySQL 是码商系统的唯一权威源。APP 传入的所有用户数据都必须与 MySQL 校验。云机端只持有 phone（作为 account_id）作为定位键，**所有 phone/pin 推送都从 MySQL 取**。

| 字段 | 权威源 | 在 pre_login 怎么用 | 在后续接口怎么用 |
|---|---|---|---|
| `phone` | MySQL `payment.phone` | 首次注册时由 APP 传入并写入 MySQL；二次/复用时从 MySQL 读取，**忽略 APP 入参**，仅用 APP 入参做校验（不匹配返回 EP_PAYMENT_PHONE_MISMATCH） | 所有云机调用（loginStep1/2、upload_data、verifyFingerprint、secondLogin、changePin）的 `account_id` 字段一律从 MySQL 取 |
| `pin` | MySQL `payment.pin` | 首次注册时由 APP 传入并写入 MySQL；二次/复用时**从 MySQL 读取**，忽略 APP 入参（避免 APP 缓存老 PIN）；change_pin 成功后更新 MySQL | secondLogin / changePinStep2 推送给云机的 PIN 一律从 MySQL 取 |
| `partner_id` | `self.handler.current_user.id`（认证用户） | pre_login 第一步取认证用户的 partner_id，写入 session.partner_id 和 MySQL（首次注册） | 所有后续接口校验 session.partner_id == handler.current_user.id（防越权） |
| `password`（码商交易密码） | MySQL `admin_user.hash_trade` | pre_login 第一步 bcrypt 校验失败 → EP_INVALID_PASSWORD（增加失败计数）；只在 pre_login 校验一次 | 其他接口不再校验（已有 session 等同已认证）|
| `fingerprint ZIP body` | Redis pending key（临时）/ 本地 `/fingerprint/easypaisa_<payment>_<phone>.zip`（落盘后） | N/A | upload_data 和 verifyFingerprint 推送的 ZIP body 一律从 Redis pending 或落盘文件读取，不从 APP 重传 |
| `account_accno`（选择的子账户） | MySQL `payment.account_accno`（select_accts 后写入） | 已 active 账号视为该 accno 当前活跃 | select_accts 入参 accno 必须在 session.account_entire 列表里（防越权写入）|

**APP 传入的"非权威字段"**（必须做合法性校验，但不作为最终值）：

| APP 入参 | 用途 | 校验失败如何处理 |
|---|---|---|
| `pre_login.phone` | 与 MySQL.phone 比对（payment_id 已存在时） | EP_PAYMENT_PHONE_MISMATCH |
| `pre_login.pin` | 首次注册时写入 MySQL；二次时**忽略**（与 MySQL.pin 不一致也不报错——用户可能在 EasyPaisa APP 改了，但我们这边业务上接受 MySQL.pin 直到 change_pin 成功）| 不校验 |
| `upload_fingerprint.phone` | 与 MySQL.phone 比对，防越权 | EP_PAYMENT_PHONE_MISMATCH |
| `select_accts.accno` | 必须在 session.account_entire 列表里 | EP_INVALID_ACCNO（新增） |
| `change_pin.pin` | 用户新 PIN，bcrypt 写入 MySQL | 不校验旧 PIN |

**接口实现统一规则**：

```python
# 反模式（禁止）：
async def some_http(self, data):
    phone = data['phone']  # ❌ 信任 APP
    await self._cloud_call(phone=phone)  # ❌ 传入云机

# 正确模式：
async def some_http(self, data):
    payment_id = data['payment_id']
    payment = await self._query_payment_by_id(payment_id)
    # 合法性校验（APP 入参 vs MySQL）
    if data.get('phone') and data['phone'] != payment.phone:
        raise NewApiError(EP_PAYMENT_PHONE_MISMATCH, ...)
    # 使用 MySQL 的权威值
    await self._cloud_call(phone=payment.phone)  # ✅ 用 MySQL.phone
```

## 4. 错误码映射

### 4.1 云机 code 到我们的处理

| 云机 code | 含义 | 处理 |
|---|---|---|
| 100 | continue | 推进状态 |
| 200 | success | 推进状态 |
| 401 | session 失效 | `_force_terminal_needs_relogin(error_code='SL_SESSION_EXPIRED')` |
| 402 | PaymentFail | 不会在上号链路出现 |
| 403 | 入参错 | 返回 EP_BAD_REQUEST，状态不变 |
| 423 | 云机忙 | sleep 2s 自动重试 1 次 |
| 500 | 业务错 | 按上下文细分（见 §4.2） |
| 501 + msgCd=URM90040 | **抢登（可恢复）** | 走 §3.5 fallback；**不视为永久锁号** |
| 501 其他 msgCd | 账号异常 | `_force_terminal_needs_relogin(error_code='SL_NEEDS_RELOGIN', reason='cloud 501 msgCd=<x>')` |
| 503 | 网络错 | 重试 2 次后返回 EP_NETWORK |

**特别说明**：v1.9 文档说"501 立即下线"，但生产日志显示 URM90040（抢登）也是 code 501，msg=`账户被抢登(Kindly verify your account through BVS)`，msgCd=`URM90040`。这种 501 是**可恢复**的（用户走一次 OTP 验证就好），必须按 msgCd 分流，**不能一律下线**。其他 msgCd 的 501（账号冻结、永久锁号）才走立即下线流程。

### 4.2 业务错误码（返回给 APP）

**对齐 APP 现有识别**：错误码全部使用 APP 端 `ApiError` (api_error.dart) 与 `_runPostFingerprintChain` / `_runSecondLoginChain` (onboarding_controller.dart) 已识别的字符串。新增码必须在 APP 端补识别。

**已识别（沿用，不动 APP）**：

| 错误码 | 含义 | APP 识别位置 | APP 行为 |
|---|---|---|---|
| `20101` | 上一次登录正在进行 | api_error.dart `alreadyLoggingIn` | 提示稍后再试 |
| `20102/03/04` | 已绑定/跨设备/OTP 中 | api_error.dart `alreadyLinked` | 弹 AlreadyLinkedDialog |
| `20102 + status transition` | OTP 节流 | api_error.dart `stateTransitionInvalid` | otpAlreadyPending 状态 |
| `20203` / `URM40008` | cooldown | api_error.dart `inCooldown` | 切 inCooldown |
| `20307` | OTP 错 | controller.dart line 321 | 留 awaitingOtp |
| `20310` / `URM20008` / `URM20017` | needs change PIN | api_error.dart `needsChangePin` | 切 awaitingPinChange |
| `66666` / `20201` / `URM10004` / `SL_NEEDS_RELOGIN` | 需重新登录 | api_error.dart `needsRelogin` | 切 needsRelogin |
| `10301` | payment 不存在 | api_error.dart `paymentNotFound` | 报错 |
| `10401` / `10402` | 跨码商占用 | api_error.dart | 拒绝 |
| `FP_UPSTREAM_REJECTED` | 指纹被拒 | controller.dart line 431 | 切回 awaitingFingerprintUpload + 标 lastFailureCause |
| `FP_SESSION_EXPIRED` | 指纹 session 过期 | controller.dart line 441 | 切 needsRelogin |
| `FP_COOLDOWN` | 指纹冷却 | controller.dart line 448 | 切 inCooldown + 启动 paymentStatus 轮询 |
| `SL_NEEDS_OTP` | URM90040 fallback 触发 | controller.dart line 497 | 切 awaitingOtp |
| `SL_NEEDS_PIN_CHANGE` | secondLogin 要求改 PIN | controller.dart line 504 | 切 awaitingPinChange |
| `SL_SESSION_EXPIRED` | secondLogin session 过期 | controller.dart line 511 | 切 needsRelogin |
| `SL_NEEDS_RELOGIN` | 云机下线 | controller.dart line 518 | 切 needsRelogin |
| `SL_COOLDOWN` | secondLogin 冷却 | controller.dart line 525 | 切 inCooldown |
| `SL_UPSTREAM_ERROR` | secondLogin 其他错 | controller.dart line 532 | 切 failed |
| `PIN_CHANGE_REJECTED` | PIN 修改被拒 | controller.dart line 671 | 留 awaitingPinChange |
| `PIN_CHANGE_LIMIT_EXCEEDED` | PIN 修改超限 | controller.dart line 679 | 切 needsRelogin |

**本次新增（APP 需要补识别）**：

| 错误码 | 含义 | APP 应做 |
|---|---|---|
| `EP_FP_FILE_MISSING` | 二次上号但本地 ZIP 文件丢失（运维事故） | 切 needsRelogin + 提示联系运维（可复用现有 needsRelogin UI） |

**注**：原 spec 自创的 `EP_PAYMENT_NOT_FOUND` / `EP_INVALID_PASSWORD` / `EP_OTP_INVALID` 等全部改用 APP 已识别的数字码（`10301` / `20203` / `20307`）。所有错误码必须经 APP 兼容性验证才发版（U17）。

## 5. Redis Session 结构

key: `easypaisa:prelogin:{payment_id}`，TTL 600 秒，ACTIVE 后立即删除。

```python
{
    'payment_id': '533290',
    'phone': '03445021275',
    'pinCode': '14725',
    'bankname': 'easypaisa',
    'partner_id': '...',
    'status': 'otpVerified',            # 8 个枚举之一
    'status_history': [...],            # 调试用
    'sendOTPTime': 1715600000,
    'last_status_change': 1715600060,
    'last_error': None,                 # 或 {'code':'EP_FP_INVALID', ...}
    'try_count': 0,
    'is_new_user': True | False,        # isAccountRegistered 结果（取反）
    'fallback_from_urm90040': False,    # URM90040 触发后置 true
    'account_entire': None,             # 二次/fallback 由 pre_login 或 verify_otp 内部填入
}
```

辅助 Redis key：
- `easypaisa:urm90040_count:{payment_id}` — TTL 3600，限 3 次/小时
- `easypaisa:pending_fp:{payment_id}` — TTL 600，upload_fingerprint_http 暂存 ZIP（详见 §3.6）

"是否已 active" 的权威来源是 **MySQL `Payment.wallet_status`**（== 1 即 active）。本项目无 runtime_snapshot Redis 层。

## 6. 待删除的代码（v1.6 残留）

### 6.1 常量与枚举
- `EASYPAISA_API_VERSION = 'v1.6'`
- `LoginStatus.FINGERPRINT_UPLOAD_REQUIRED`
- `LoginStatus.FINGERPRINT_UPLOADED`
- `LoginStatus.SECOND_LOGIN_READY`
- `LoginStatus.SECOND_LOGIN_PASSED`（second_login_http 出态改为 ACCOUNT_SELECTION_REQUIRED）
- `FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM`

### 6.2 内部函数（按当前代码 line 标号精确删除）

- `_replay_saved_fingerprint` (line 3631-3661)：功能并入 pre_login_http 内部续推（二次上号自动推 ZIP）
- `_build_bound_second_login_session` (line 4094-4128)：533264 根因，直接跳到 SECOND_LOGIN_READY 的快速路径源头
- `_verify_account` (line 3105-3247)：整段删除。v1.6 模式下的"先验指纹后验 PIN"分支在 v1.9 不再存在；指纹验证由独立 `_perform_verify_fingerprint` 接管，PIN 验证由 secondLogin 自带
- `verify_otp_http` 内部 `_verify_account` 调用 (line 1059)：直接删除该调用，OTP 验证仅做 loginStep2
- `active_account_http` (line 2237-2242)：已 deprecated 返回 API_DEPRECATED

### 6.3 内部函数（保留并简化）

- `_perform_verify_fingerprint` (line 3494-3565)：**保留**。这是 v1.9 verifyFingerprint action 的封装，由新 verify_fingerprint_http 调用（不再是 upload_fingerprint_http）。需要简化：删掉对 `_verify_account` 老接口风格的兼容代码，只保留纯 verifyFingerprint 调用与响应解析

### 6.4 接口（修改并保留）

| 接口 | 当前代码位置 | 重构改动要点 |
|---|---|---|
| `pre_login_http` | line 1231+ | 入参签名不变；删除 bound_payment 快速路径 (line 1396-1416)；增加 §3.3 描述的 9 步流程 + 二次上号内部续推 4 步 |
| `get_otp_http` (原 `send_otp_http`) | line 1594+ | 保留接口名；增加 §3.3.1 节流逻辑；不再依赖老状态枚举 |
| `verify_otp_http` | line 1700+ | 拆出首次 / fallback 分支；移除 `_verify_account` 调用 (line 1059) 与所有指纹相关代码 |
| `upload_fingerprint_http` | line 2401+ | 入态 `OTP_VERIFIED`、出态保持 `OTP_VERIFIED`；只做 ZIP 校验 + Redis pending 写入；**不调云机、不落盘**（见 §3.4.1 / §3.6） |
| `verify_fingerprint_http` | line 1920+ | 保留接口；入态 `OTP_VERIFIED`（pending ZIP 必须存在）、出态 `FINGERPRINT_VERIFIED`；内部读 Redis pending → upload_data 推云机 → verifyFingerprint 验证 → 全成功才落盘并推进状态（见 §3.6）；幂等行为见 §3.6.1。controller line 309 路由保留 |
| `second_login_http` | line 2050+ | 内部增加 queryAccountList 调用；处理 needs_pin_change 分支 → AWAITING_PIN_CHANGE |
| `query_accts_http` | line 2756+ | 方法体替换为读 `session.account_entire` 直接返回（兼容 stub）；不再调云机 queryAccountList；controller line 370 路由保留 |
| `change_pin_http` | line 2244+ | 内部实现不修改；适配新状态机（入态 `AWAITING_PIN_CHANGE`，出态 `FINGERPRINT_VERIFIED`） |
| `select_accts_http` | line 2756+ | 入态 `ACCOUNT_SELECTION_REQUIRED`、出态 `ACTIVE_SUCCESSFUL`；写 MySQL `Payment.wallet_status=1` + `account_accno` + `account_iban` + `account_type`；删 Redis prelogin。**不再写 `hash_easypaisa` / `set_easypaisa`**（这两个是 legacy cleanup-only Redis 残骸，已无 hset/zadd 操作，go-worker 直接读 MySQL `wallet_status`） |
| `payment_status_http` | line 2855+ | 直接返回新枚举字符串（APP 同步发版，不引兼容层）；status/next_action 来自 §3.1 8 状态机；`payment_ids` 复数入参字段名保持不变；读 Redis `pre_login_easypaisa_*` session 取 status + last_error |

## 7. 验收用例

| 编号 | 用例 | 步骤 | 预期 |
|---|---|---|---|
| U1 | 首次上号走通 | 全新 payment_id → pre_login → get_otp → verify_otp → upload_fp → verify_fp → second_login → select_accts | MySQL `Payment.wallet_status=1` + `account_accno`/`account_iban`/`account_type` 已写入；go-worker `SELECT ... WHERE wallet_status=1 AND manual_status=1 AND certified=1` 能查到该 payment |
| U2 | 二次上号走通 | 已 ACTIVE 账号下线后再 pre_login → select_accts | 两步内上号成功，跳过 OTP+指纹按钮 |
| U3 | 已 active 重复 pre_login | 已 active 账号再次 pre_login | 返回 `next_step:'ready'`，无 ERROR 日志（修复 533264）|
| U4 | URM90040 自恢复 | mock secondLogin URM90040 → fallback → verify_otp → select_accts | 一次性恢复成功，count=1 |
| U5 | URM90040 死循环防护 | 同 payment 1 小时内 4 次 URM90040 | 第 4 次直接 needsRelogin 报警（修复 03445021275）|
| U6 | OTP 错 | verify_otp 传错 OTP | 状态保持 OTP_SENT，返回 EP_OTP_INVALID |
| U7 | 指纹失败重传（详细行为追踪） | 准备已 active 过的 payment（本地有 valid ZIP，md5=A）。下线后从 OTP_VERIFIED 状态：1) 调 upload_fp 传 corrupted ZIP（B），返回成功（仅入 Redis pending），状态保持 OTP_VERIFIED；调 verify_fp → mock verifyFingerprint 拒绝 → 验证：状态保持 OTP_VERIFIED、本地 ZIP md5 仍为 A、云机被调用 1 次 upload_data + 1 次 verifyFingerprint、MySQL fingerprint_path 未变、Redis pending 仍保留。2) 调 upload_fp 传新 valid ZIP（C）（覆盖 pending），调 verify_fp → verifyFingerprint 通过 → 验证：状态变 FINGERPRINT_VERIFIED、本地 ZIP md5 变为 C、云机被调用第 2 次 upload_data + 第 2 次 verifyFingerprint、MySQL fingerprint_path 变为新路径、Redis pending 已删。3) 全程 trace_id grep 检查 4 类日志（入态校验、云机响应、状态推进、APP 返回）齐全。 | 满足全部断言 |
| U8 | 二次上号指纹失败 | mock pre_login 内部 verifyFingerprint 失败 | 状态降到 OTP_VERIFIED，APP 走 upload_fp → verify_fp → second_login → select_accts |
| U9 | fallback 指纹失败 | mock URM90040 fallback 内部 verifyFingerprint 失败 | 状态保持 OTP_VERIFIED，APP 走 upload_fp → verify_fp → second_login → select_accts |
| U10 | 501 非 URM90040 立即下线 | mock 接口返回 code 501 + msgCd≠URM90040 | MySQL `Payment.wallet_status=0`；legacy Redis `hash_easypaisa`/`set_easypaisa` 残骸顺手清理（hdel/zrem）；告警发出 |
| U10b | 501 + URM90040 不下线 | mock secondLogin 返回 code 501 + msgCd=URM90040 | 不下线，走 §3.5 fallback；count+=1 |
| U11 | 代码扫描 | grep `FINGERPRINT_UPLOAD_REQUIRED\|FINGERPRINT_UPLOADED\|SECOND_LOGIN_READY\|_replay_saved_fingerprint\|_build_bound_second_login_session\|active_account_http\|EASYPAISA_API_VERSION` | 0 匹配 |
| U12 | 03445021275 实例 | 真实账号跑 pre_login | 不再死循环，按 U4/U5 行为运行 |
| U13 | 533264 实例 | 真实账号已 active 后再调 pre_login | 不再出现"状态转换无效"错误 |
| U14 | URM90040 1 小时窗口衰减 | 第 1-3 次触发后等 1 小时再触发 | count 自动重置，再次允许 fallback |
| U15 | verify_fp 失败不污染本地 | 准备已有 valid ZIP 的 payment，调 upload_fp 传 corrupted ZIP（入 Redis pending），再调 verify_fp 让 verifyFingerprint 拒绝 | 本地 `/fingerprint/easypaisa_<phone>.zip` md5 与传入前相同（老 ZIP 未被覆盖）；Redis pending 仍保留供下次重传 |
| U16 | PIN 错误 → change_pin 闭环 | mock secondLogin 返回 needs_pin_change → APP 走 change_pin → second_login → select_accts | 状态序列 AWAITING_PIN_CHANGE → FINGERPRINT_VERIFIED → ACCOUNT_SELECTION_REQUIRED → ACTIVE；MySQL payment.pin 已更新 |
| U17 | 状态字符串契约 | payment_status_http 返回 | data 中 `status` 严格使用新 8 枚举字符串值，与 §3.1 一致 |
| U19 | pre_login 入参签名不变 | 用现有 APP 的 `bankname/phone/password/pin/name` 调用 | 入参解析正常，交易密码校验、登录失败计数、双 Redis 锁全部按原逻辑走 |
| U20 | 二次上号 ZIP 文件丢失 | MySQL fingerprint_path 存在但本地文件被 rm 删除，触发 pre_login | 走 `_force_terminal_needs_relogin(reason='Local ZIP file missing', error_code='EP_FP_FILE_MISSING')`；状态 NEEDS_RELOGIN；不尝试自动恢复 |
| U21 | 残留 session 复用（Blocker 4） | payment 中途断在 OTP_VERIFIED。3 分钟后 APP 重新调 pre_login | 返回 {resumed:true, phase:'otpVerified', next_step:'upload_fingerprint', expires_in:<剩余秒数>}；session.status_history 不被覆盖；交易密码 bcrypt 仍校验 |
| U22 | 残留 session 复用 - ACCOUNT_SELECTION_REQUIRED | payment 在 ACCOUNT_SELECTION_REQUIRED 断了 5 分钟后再 pre_login | 返回 {resumed:true, phase:'accountSelectionRequired', next_step:'select_accts', accounts:[...]}；APP 拿到 accounts 直接显示，无需再调 query_accts |
| U23 | needsRelogin 统一入口（Blocker 5） | 触发 5 种不同的 needsRelogin 场景 | 全部经过 `_force_terminal_needs_relogin`；每条 grep `_force_terminal_needs_relogin` 都有 reason 字段；session.last_error 在 5 秒内可读取；5 秒后 redis_key 被异步清理 |
| U24 | NEEDS_RELOGIN 邻接表约束 | 在 PRE_LOGIN_CREATED 跳到 NEEDS_RELOGIN（合法）、在 ACTIVE_SUCCESSFUL 试图跳到 NEEDS_RELOGIN（非法） | 第一次成功；第二次被 `_assert_status_transition` 拦下，抛 Invalid transition |
| U25 | NEEDS_RELOGIN 后 APP 拉取 last_error | needsRelogin 触发后 2 秒内 APP 调 payment_status_http | 返回 status='needsRelogin'，error 字段非空（含 reason + message） |
| U26 | 数据权威性（phone）| 1) upload_fingerprint 传 phone='03333333333'（与 MySQL.phone='03445021275' 不符）→ 返回 EP_PAYMENT_PHONE_MISMATCH。2) 改成传正确 phone，云机 upload_data 抓包显示 account_id 是 MySQL.phone 不是 APP 入参。 | 满足两个断言 |
| U27 | 数据权威性（accno）| 1) select_accts 传 accno='99999999'（不在 session.account_entire）→ 返回 EP_INVALID_ACCNO。2) 改传 session 中存在的 accno → 写入 MySQL 成功。| 满足两个断言 |
| U28 | multipart 字段名 | APP exchange_api.dart 用 FormData.fromMap({...'files': ...}) 调 upload_fingerprint | 服务端 200 接收（如服务端误用 'file' 单数，会 400）|
| U29 | payment_status 批量查询 | 传 payment_ids='5001,5002,5003' | 返回 datas[] 长度=3，每项含 status/cd_until/next_action |

## 8. 风险与回滚

### 8.1 风险
- **APP 端兼容性**：APP 端代码当前可能依赖 FINGERPRINT_UPLOAD_REQUIRED / FINGERPRINT_UPLOADED 等状态名，重构后 APP 需要同步更新对应分支
- **MySQL 中存量数据**：`payment.fingerprint_path` 字段保留，老数据可直接复用
- **运行中 session**：发布瞬间 Redis 里残留的 prelogin session 状态枚举值可能不匹配新状态机，需要发布前清理或加兼容映射

### 8.2 回滚策略
- 每个修改保持原文件结构，新分支独立分支开发
- 发布前在测试环境跑完 U1-U29 全部验收
- 灰度策略：先一台机器，观察 1 小时无新错误日志，再全量

### 8.3 实施时再决定的细节（不影响 spec 契约）

以下问题在写代码时再决定即可，不会影响 APP 协议、状态机骨架、数据结构：

| 项目 | 实施时决定 | 默认推荐 |
|---|---|---|
| change_pin_http step1+step2 内部协议 | 读代码确认是 1 次 HTTP 还是 2 次 | 维持现状 |
| `_force_terminal_needs_relogin` 5 秒延迟实现 | `EXPIRE key 5` 自然过期 vs `asyncio.create_task` 调度 | `EXPIRE 5` 最简单 |
| `inCooldown` 是否进 STATUS_TRANSITIONS | 实施时按情况决定 | 不进（保持 7 状态），由错误码标记 |
| Redis pending ZIP key 前缀来源 | 硬编码 vs `keyspace` 模块 | `keyspace` 模块 |
| URM90040 计数器 Redis 实现 | INCR+EXPIRE vs Lua script 原子 | INCR + EXPIRE（足够） |
| 日志格式（format / f-string / structlog） | 跟现有 codebase 风格 | 维持现状 |
| `_perform_verify_fingerprint` 内部重试次数 | 1 次 vs 2 次 | 1 次（与现有 retry_make_request 配合） |

## 9. 不在本次范围内

- 业务接口（queryBalance、queryBill、transfer）不动
- changePinStep1 / changePinStep2 流程不动
- MySQL payment 表结构不动（只复用现有字段）
- 多 partner_id 归属校验逻辑不动

## 10. 日志验证（基于 2026-05-14 真实生产日志）

设计中每个关键决策都有线上日志佐证。日志服务器：`/www/python/api/logs/api_900?.log` @ `34.96.148.205`。

### 10.1 URM90040 是 501 不是 500（影响 §4.1）

**真实样本**（533290, 03445021275, 12:27:13）:
```json
{"code":501,
 "msg":"账户被抢登(Kindly verify your account through BVS)",
 "data":{"requestId":"AGW1504075269090705410",
         "msgId":"URM1504075269279846400",
         "startDateTime":"2026-05-13T15:58:08.564",
         "routeInfo":"URM",
         "msgCd":"URM90040",
         "msgInfo":"Kindly verify your account through BVS"}}
```

**结论**：URM90040 必须按 msgCd 而不是 code 分流。code 501 既有"永久锁号"也有"抢登可恢复"，msgCd 才是唯一确定语义的字段。

### 10.2 533290 死循环（影响 §3.5 fallback 限频）

11:46 - 13:15 之间，`payment_status_http` 反复显示 `533290 status:secondLoginReady next_action:second_login`，跨度 1 小时 30 分钟。当前代码每次 `second_login_http` 都触发 URM90040，回到 `loginStep1` → `loginStep2(成功)` → `second_login(URM90040)` 循环。

13:15:31 `533290` 才彻底变成 `offline`（被 monitor 清掉）。

**结论**：URM90040 必须有 1 小时窗口限频（设计为 3 次/小时），否则会无限循环消耗 OTP 配额。

### 10.3 533264 bound_payment 快速路径（影响 §6.1 删除 line 1396-1416）

12:48:40、13:04:38、13:06:13 三次 `pre_login_http` 都命中"已绑定账号通过归属校验，返回 second_login"：
```python
{'status':'success', 'data':{
    'id':'533264',
    'redis_key':None,
    'next_step':'second_login',
    'is_new_user':False}}
```

每次都让 APP 重新走 `second_login_http`，但 533264 在 12:47:47 时已经是 `activeSuccessful` 状态（payment_status 显示）。这就是触发"期望 fingerprintVerified, 实际 activeSuccessful"状态转换错误的来源。

**结论**：pre_login_http 必须先查 MySQL `Payment.wallet_status`，== 1 时直接返回 ready，禁止走 bound_payment 快速路径。

### 10.4 v1.6 生产环境从未调用过 verifyFingerprint action（影响测试覆盖率）

生产日志里搜不到任何 `action:verifyFingerprint` 或 `upload_data` HTTP 请求。当前 v1.6 模式下 `should_verify_fingerprint=false` 让云机内部跳过指纹验证。

**结论**：v1.9 切换 + 启用 verifyFingerprint 是**第一次真正调用云机指纹接口**，需要灰度发布、密切观察云机端响应、准备好回滚开关。

### 10.5 isAccountRegistered 返回值（影响 §3.3）

**样本 1**（533264, 03421904953, 已注册）:
```json
{"code":200, "msg":"isAccountRegistered查询: pk_easypaisa_03421904953", "data":true}
```

**样本 2**（533290, 03445021275, 已注册但抢登）:
```json
{"code":200, "msg":"isAccountRegistered查询: pk_easypaisa_03445021275", "data":true}
```

**结论**：
- isAccountRegistered 的判定是云机端的"是否绑定过 EasyPaisa 账号"，**不代表账号当前在银行端是否可用**
- 即使 isAccountRegistered=true，secondLogin 仍可能因抢登/冻结失败
- v1.9 文档第 109-114 行的"data:false"是云机未绑定的标准响应，code=403。生产日志暂无该样本。

## 11. 系统状态（我方）vs 云机状态：失败处理边界

当前代码的一个隐性问题：把"云机端报错"和"我们系统状态异常"混在一起处理。重构后明确分开。

### 11.1 云机状态导致的失败（云机正常应答了一个失败结果）

| 现象 | 处理 |
|---|---|
| loginStep1 / loginStep2 返回非 200 | 走 §3.3-3.4 状态机分支 |
| secondLogin 返回 501 URM90040 | 走 §3.5 fallback |
| secondLogin 返回 501 其他 msgCd | needsRelogin 报警 |
| verifyFingerprint 返回非 200 | 状态保持 OTP_VERIFIED，APP 重传 ZIP |
| upload_data 返回 ≠ `ok` | 状态保持 OTP_VERIFIED，提示重试 |

### 11.2 我方系统状态导致的失败

| 现象 | 处理 |
|---|---|
| MySQL payment 不存在 | 返回 EP_PAYMENT_NOT_FOUND |
| Redis 不可达 / 写入失败 | 返回 EP_SYSTEM_ERROR，**不**调云机（避免 session 漂移） |
| MySQL payment.phone 为空 | 返回 EP_PAYMENT_PHONE_MISSING |
| MySQL payment 归属 partner_id 不匹配 | 返回 EP_PERMISSION_DENIED |
| 本地 `/fingerprint/` 目录不可写 | 返回 EP_SYSTEM_ERROR，**保留** Redis 临时 ZIP 不删 |
| MySQL `Payment.wallet_status` 读取失败 | 退化为乐观路径，按"未 active"处理（不阻塞用户上号） |

### 11.3 状态机 + 日志的最小可观测性

每个状态推进必须满足：

1. **入态校验失败**：日志格式 `[funcName] 状态转换无效: 期望 {expected_set}, 实际 {actual}`，并包含 `payment_id`、`trace_id`、当前 session_history。
2. **云机调用结果**：日志格式 `[funcName] 云机响应 action={action} code={code} msgCd={msgCd}`，便于按 msgCd 聚合。
3. **状态推进**：日志格式 `[funcName] 状态推进: {from} → {to}`。
4. **业务返回给 APP**：日志格式 `[funcName] 返回 APP: next_step={next_step} code={biz_code}`。

这 4 类日志合在一起，可以从 grep 单一 trace_id 完整还原一次上号的所有状态推进 + 云机调用 + 业务返回，方便排查类似 533290 / 533264 的真实事故。

## 12. 发版策略：服务端 + APP 同步发布

### 12.1 决策

不引入服务端兼容层。APP 与服务端**同步发版**，约定一致的状态字符串。

**理由**：
- 服务端能控制 APP 发版节奏
- 兼容层会让代码长期带 dead weight（实际上常常永远删不掉）
- 状态字符串变化只影响 `payment_status_http` 出口和 APP UI 字符串判断，单一调用点

### 12.2 发版前置任务

| 任务 | 责任方 | 时机 |
|---|---|---|
| APP 端更新所有状态字符串硬编码到新枚举 | APP 团队 | 与服务端同步开发，提前 1 周 demo |
| APP 端更新 `next_action` 字符串映射 | APP 团队 | 同上 |
| 清理残留 Redis `pre_login_easypaisa_*` 键（避免旧状态字符串困住新会话） | 后端 | 发版瞬间一次性清空 |
| 发版协调会确认所有 active payment（MySQL `wallet_status=1`）继续可用，不被重启冲掉 | 后端 + APP | 发版前 |

### 12.3 存量数据策略

本项目已完成 MySQL 转型，**没有 runtime_snapshot Redis 状态层**，所以也没有 Redis 状态字符串需要迁移。需要处理的只有 Redis `pre_login_easypaisa_*` 残留会话（TTL 600s 内可能还活着）：

**做法：发版瞬间一次性清空 `pre_login_easypaisa_*` 键**
- 上号中途的用户被迫重新调 pre_login（最多影响 600s 内正在上号的用户）
- 已 active 账号（MySQL `wallet_status=1`）不受影响——go-worker 继续按 MySQL 调度
- 必须在低峰期发版（如凌晨）

清空命令（手动 / 发版脚本均可）：
```bash
redis-cli --scan --pattern 'pre_login_easypaisa_*' | xargs -L 100 redis-cli del
```

`hash_easypaisa` / `set_easypaisa` 是 legacy 残骸，已无 hset/zadd 写入，发版无需特别处理。

### 12.4 发版顺序

1. APP 端打包新版本，提交应用市场审核（含完整状态机适配）
2. APP 新版本审核通过、铺量准备就绪
3. 在线峰值统计 - 选低峰窗口（建议凌晨 2-4 点 PKT）
4. 服务端发版（包含状态机重构）+ 执行 §12.3 的 Redis 清空命令
5. 灰度 1 台机器观察 1 小时
6. 全量发布
7. 应用市场强制更新（如果支持）或在 APP 内做不兼容提示

### 12.5 回滚策略

回滚只影响"发版瞬间在上号的用户"——他们的 Redis prelogin session 用了新枚举字符串，老服务端不认识。

**做法：回滚前再次清空 `pre_login_easypaisa_*` Redis 键**（同 §12.3 命令）。

MySQL `wallet_status=1` 的已 active 账号在回滚后继续可用——MySQL 字段值（0/1）没变，老服务端读它行为不变。**所以本次回滚不需要数据迁移脚本**。

## 13. APP 端真实调用清单（基于 ashrafi_merchant_flutter 仓库 grep）

### 13.1 APP 调用的 10 个上号接口

接口位于 `/api/v1/login/*`，调用代码位置 `lib/features/onboarding/data/exchange_api.dart`：

| APP 函数 | endpoint | 入参 | 出参关键字段 |
|---|---|---|---|
| `preLogin` (line 165) | `/api/v1/login/pre_login` | bankname/phone/name/password/pin/step/payment_id? | data.id, data.next_step |
| `getOtp` (line 207) | `/api/v1/login/get_otp` | bankname/payment_id | 无 |
| `verifyOtp` (line 216) | `/api/v1/login/verify_otp` | bankname/payment_id/otp | data.next_phase ∈ {fingerprintUploadRequired, fingerprintUploaded} |
| `uploadFingerprint` (line 236) | `/api/v1/login/upload_fingerprint` | multipart: bankname/payment_id/phone/files | 无（成功即可） |
| `verifyFingerprint` (line 260) | `/api/v1/login/verify_fingerprint` | bankname/payment_id | data.ok, data.code, data.cd_until, data.next_action, data.next_phase |
| `secondLogin` (line 292) | `/api/v1/login/second_login` | bankname/payment_id | data.ok, data.code, data.message |
| `changePin` (line 317) | `/api/v1/login/change_pin` | bankname/payment_id/pin | 无 |
| `queryAccts` (line 350) | `/api/v1/login/query_accts` | bankname/payment_id | data.account_selected, data.account_entire[] |
| `selectAccts` (line 371) | `/api/v1/login/select_accts` | bankname/payment_id/accno | 无 |
| `paymentStatus` (line 383) | `/api/v1/login/payment_status` | bankname/**payment_ids**（复数字符串） | datas[].status, datas[].cd_until, datas[].next_action |

### 13.2 APP 端 OnboardingPhase 与服务端 LoginStatus 映射

| APP `OnboardingPhase` | 服务端 `LoginStatus` | 触发点 |
|---|---|---|
| `preLogin` | `PRE_LOGIN_CREATED` | preLogin() 返回，未发 OTP |
| `awaitingOtp` | `OTP_SENT` | getOtp() 成功 / fallback 触发 |
| `awaitingFingerprintUpload` | `OTP_VERIFIED`（pending ZIP 不存在） | verifyOtp 返回 `next_phase: 'fingerprintUploadRequired'` |
| `verifyingFingerprint` | `OTP_VERIFIED`（pending ZIP 存在） | uploadFingerprint 成功，等用户点验证 |
| `awaitingSecondLogin` | `FINGERPRINT_VERIFIED` | verifyFingerprint 成功 / changePin 成功后 APP 自己设的 |
| `awaitingPinChange` | `AWAITING_PIN_CHANGE` | secondLogin 返回 SL_NEEDS_PIN_CHANGE |
| `awaitingAccountSelection` | `ACCOUNT_SELECTION_REQUIRED` | queryAccts 返回多账号 |
| `activeSuccess` | `ACTIVE_SUCCESSFUL` | selectAccts 成功 / 单账号自动选择 |
| `failed` | （任意，session 已删） | 不可恢复的失败 |
| `alreadyLinked` | （未创建 session） | preLogin 报 20102/03/04 |
| `needsRelogin` | （session 已删） | 各种 `needsRelogin` 错误码 |
| `inCooldown` | （任意） | FP_COOLDOWN / SL_COOLDOWN |
| `otpAlreadyPending` | `OTP_SENT` | getOtp 重复调用被节流 |

### 13.3 APP 端指纹的真实来源

**重要**：APP 端通过 `VeridiumChannel.collect()`（lib/core/native/veridium_channel.dart）调用 Android 原生 Veridium SDK 采集**用户真实生物指纹**：

```dart
class VeridiumResult {
  final String zipPath;      // 采集完打包的 ZIP 路径
  final bool hasLeftHand;    // 是否采集了左手
  final bool hasRightHand;   // 是否采集了右手
}
```

- 指纹 ZIP 是**真实生物指纹**（不是设备指纹）
- 失败重传 = APP 重新启动 Veridium 让用户再按一次指纹
- ZIP 由 Veridium SDK 打包生成，结构是云机/EasyPaisa 定义的标准格式

### 13.4 APP 端的码商交易密码

`password` 字段是**码商系统的交易密码**（非 EasyPaisa PIN）：
- 表单字段位置：`lib/features/onboarding/presentation/_form_shared.dart` line 310 `platform_trade_password_box`
- 校验位置：服务端 `_verify_payment_password_bcrypt`（pre_login_http line 1309）
- 存储位置：MySQL `admin_user.hash_trade`（bcrypt 哈希）
- **必须在 pre_login 首先校验**，校验失败触发登录失败计数器，连续多次失败锁定 2 小时
- 这是我方系统的鉴权层，**独立于云机 PIN**，云机不感知

### 13.5 APP 端发现的服务端真相

- APP 期望 `preLogin` 返回 `data.id`（不是 `payment_id`）— exchange_api.dart line 193 已兼容
- APP 期望 `payment_status` 入参字段名 `payment_ids`（复数）
- APP 期望 `payment_status` 返回 `datas[]` 数组（即使单 payment 也要包装）
- APP 期望 `verify_otp` 返回 `next_phase`（不是 `next_step`）— 已识别两种 fallback

### 13.6 APP 端不必修改的部分

由于所有错误码、状态名都对齐 APP 现有识别（§4.2），**理论上 APP 端零修改即可适配新服务端**。但仍建议：
- APP 端补识别新增的 `EP_FP_FILE_MISSING` 错误码（虽然可回退到 needsRelogin）
- APP 端验证 `getOtp` 在 PRE_LOGIN_CREATED 状态下能正常发 OTP（与服务端 §3.3.1 节流逻辑配合）

