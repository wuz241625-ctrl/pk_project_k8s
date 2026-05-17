# EasyPaisa 登录分流改造：按账号类别分流（已绑定 secondLogin-first 回退 loginStep1；新号 loginStep1-first）

- 日期：2026-05-17
- 范围：`api/application/app/login/banks/easypaisa.py` 的 `pre_login_http` 分流逻辑及其支撑函数
- 方案：B —— 按账号类别分流（已绑定 secondLogin-first，失败回退 loginStep1；新号 loginStep1-first）+ loginStep1 非 100/200 加固；硬性禁用 isAccountRegistered 分流

## 1. 背景与问题

旧设计（a9ed9428 之前）在 `pre_login_http` 用 `_is_account_registered`（云机 `isAccountRegistered` 接口）做注册分流：

- `true` → 走 secondLogin 续推
- `false` → 走 loginStep1 + loginStep2 首次上号

线上观察到 `isAccountRegistered` 对同一账号在短时间内返回值反复抖动（true/false flapping），导致分流走错方向。

根因不是接口坏，而是语义错位：

- 按 EasyPaisa v2.2 文档第 108-113 行，`isAccountRegistered` 返回 `false` 的定义是 **“云机不存在或账户未完成云机绑定流程”**——其中 **“云机不存在”** 包含“曾绑定但云机实体被资源池回收”的情况。
- 它是“此刻是否有云机实例正绑着该号”的**实时探针**，不是“该号是否曾上过号”的**持久标志**。云机池化回收使其天然抖动。
- 旧流程“先 check（isAccountRegistered）再 act（loginStep1/secondLogin）”两次调用之间存在状态漂移窗口（check/act 竞态），这才是分流走错的直接原因。

提交 a9ed9428 已把 `pre_login_http` 改为直接调 `loginStep1`（`_send_otp`）、按云机返回 `code` 200/100 分流，删除了 `_is_account_registered`。本设计在此基础上**细化为按账号类别分流**（已绑定号补 secondLogin-first 快路径），并把“禁用 isAccountRegistered 分流”固化为不变量、加固 loginStep1 非 100/200 处理。

## 2. 决策与依据

**核心决策：按账号类别分流，不是单一的全局 “X-first”。**

| 账号类别 | 判定 | 首选 | 失败回退 |
|---|---|---|---|
| 已绑定 Payment | DB 有 payment 记录且有 pin（`bound_payment` 命中） | `secondLogin`-first（探测实时可用） | 非 `success`/`needs_pin_change`/`cooldown` → 落 `loginStep1` |
| 新号 | 无 `bound_payment` | `loginStep1`-first（→`100` 发 OTP / →`200` 设备复用直登） | —（loginStep1 非 100/200 见 §6） |

**硬性约束（不变量）：禁止使用 `isAccountRegistered` 做分流。** 根因见 §1——它是“此刻云机是否绑着该号”的实时探针而非持久标志，云机池化回收使其天然抖动；且“先 check 再 act”存在状态漂移竞态。本设计任何路径都不得调用 `_is_account_registered` 做分流（AC2 守护）。

依据：

- 已绑定健康号重新上线时，`secondLogin` 正是文档 64-66 行 “registered → secondLogin 检查实时可用状态” 的本意（云机已存该绑定设备指纹），成功即零打扰直达账户选择。故已绑定号 secondLogin-first。
- 新号无云机实体，`secondLogin` 对未注册号的返回文档未定义；必须 `loginStep1` + `loginStep2` 首次分配云机并登录。故新号 loginStep1-first。
- 运营事实：已上过号的健康账户 `loginStep1` 绝大多数返回 `code:200`（设备复用生效），且 `code:200/100` 是确定性指令而非参考值。故已绑定号 secondLogin 探测判定需重新上号时，回退 `loginStep1` 代价低、安全。
- a9ed9428 已删除 `_is_account_registered` 并改为调 `loginStep1` 分流；本设计在其基础上**细化为按账号类别分流**：为已绑定号补 secondLogin-first 快路径，并把“禁用 isAccountRegistered”固化为不变量。

**有意的行为变更（核心收益，非缺陷）：** secondLogin 快路径成功时，已绑定健康号直接进入 `ACCOUNT_SELECTION_REQUIRED`，**本 session 不再采集/校验指纹**。这是文档预期的 registered 分支行为，区别于 a9ed9428 对所有号“先 loginStep1、再永远走指纹”。

被否决的备选：

- 全局 loginStep1-first（a9ed9428 原样）：已绑定健康号也强制走 loginStep1 + 指纹链，浪费更廉价的 secondLogin 路径，且偏离文档 registered 语义。
- 全局 secondLogin-first（含新号）：依赖“对从未注册号调 secondLogin 的返回”——文档未定义，需真实号 e2e 验证，超出本次验收范围。
- 保留 `isAccountRegistered` + 本地态加固：未消除 flapping/竞态根因，违反本设计硬性约束。

## 3. 架构总览

`pre_login_http` 写完 session 后，按账号类别分流（已绑定 secondLogin-first 回退 loginStep1；新号 loginStep1-first）：

```
pre_login_http (session 已建)
  │
  ├─ bound_payment 存在(已绑定 + 有 DB pin)?
  │     YES → _try_secondlogin_fastpath()              零打扰快路径
  │            ├─ success      → queryAccts → ACCOUNT_SELECTION_REQUIRED  返回
  │            ├─ needs_pin    → AWAITING_PIN_CHANGE                       返回
  │            ├─ cooldown     → SL_COOLDOWN（状态留 PRE_LOGIN_CREATED）   返回
  │            └─ 其他(relogin/URM90040/upstream) → 落 loginStep1
  │     NO（新号）→ 直接 loginStep1
  │
  └─ _perform_loginstep1()   非 raise 分类器
        ├─ 200 直登 → OTP_VERIFIED → (本地有指纹? 服务端续推链 : fingerprintUploadRequired)
        ├─ 100 OTP  → OTP_SENT → APP verify_otp
        ├─ 501      → 下线 + 终态 NEEDS_RELOGIN
        ├─ 423      → 可重试信封 EP_RETRY（状态留 PRE_LOGIN_CREATED）
        └─ 403/500/503 → 带 code 干净错误（状态留 PRE_LOGIN_CREATED）
```

不变量：secondLogin 快路径任何非 `success/needs_pin_change/cooldown` 的结果都**不杀 session**，而是落到 loginStep1 重新上号。这替代了旧 pre_login 链中的内部 URM90040 发 OTP hack；当前 d7pay 代码没有 `_urm90040_fallback_from_pre_login`，下游保留的是 `_urm90040_fallback` 与 `_verify_otp_fallback_chain`。

## 4. 组件改动

| 组件 | 类型 | 说明 |
|---|---|---|
| `_try_secondlogin_fastpath(redis_key, session_data, bound_payment)` | 新增 fastpath | 当前仓库没有 `_post_secondlogin_query_accts`，落地实现复用既有 `_call_second_login(with_pwd=True)` + `_call_query_account_list` + `_update_session_status`。`success`→`ACCOUNT_SELECTION_REQUIRED`；`needs_pin_change`→AWAITING_PIN_CHANGE 信封；`cooldown`→SL_COOLDOWN 信封；其他一切（needs_relogin/session_expired/URM90040/upstream_error/queryAccountList失败）→返回哨兵 `None`，由调用方落 loginStep1。**不**再调 `_force_terminal_needs_relogin`；也不存在旧 `_urm90040_fallback_from_pre_login`。 |
| `_perform_loginstep1(session_data)` | 新增 | 平行 `_perform_second_login` 的 outcome 模式。复用 `_build_send_otp_request` + `_decode_indus_response`，**不 raise**，返回 `{'outcome': 'direct_success'｜'otp_sent'｜'offline_501'｜'server_busy'｜'rejected'｜'network_error', 'code': int, 'message': str}`。`code==501` 时内部仍调 `_mark_payment_official_501_offline`。 |
| `_send_otp` | 不动 | 仍服务 `send_otp_http`（重发节流）与 `_urm90040_fallback` 内部发 OTP。零回归。 |
| `pre_login_http` 分流块（约 1865–1986 行） | 重写 | 按 §3 账号类别分流编排。loginStep1 的 200/100 happy path 逻辑与 a9ed9428 等价保留（save_payment、redis_key 迁移、双锁、续推链 / fingerprintUploadRequired 信封不变），仅把“非 100/200 → raise SendOTPFail”换成 `_perform_loginstep1` 的 outcome 分支。 |
| `_second_login_chain_from_pre_login` | 消除 | a9ed9428 后唯一调用点已删，现为死代码（已 grep 确认仅自身定义）。改造为 `_try_secondlogin_fastpath`，不保留旧名。 |

下游 URM90040 兜底不动：当前 d7pay 实际入口是 `_urm90040_fallback`，由 `_try_secondlogin_fastpath` / `_verify_otp_fallback_chain` 等链路在需要时触发；当前代码没有 `_fallback_chain_after_verify_otp`、`_urm90040_fallback_from_pre_login`、`_second_login_chain_from_pre_login` 或 `_post_secondlogin_query_accts`。

> 落地记录（2026-05-17）：当前 d7pay 仓库实际保留的是旧辅助 `_pre_login_second_time_chain`，没有 `_second_login_chain_from_pre_login` 和 `_post_secondlogin_query_accts`。本次未删除 `_pre_login_second_time_chain`，只让 `pre_login_http` 不再调用它，避免扩大既有下游测试/历史辅助的变更面；AC2/AC6 由 `test_easypaisa_v19_branching_invariants.py` 守护。

## 5. 状态机

`STATUS_TRANSITIONS`（当前约 106-141 行）**无需修改**：从 `PRE_LOGIN_CREATED` 出发的目标态 `OTP_SENT` / `OTP_VERIFIED` / `ACCOUNT_SELECTION_REQUIRED` / `AWAITING_PIN_CHANGE` / `NEEDS_RELOGIN` 已全部允许。`cooldown` / `423` / `403/500/503` 保持 `PRE_LOGIN_CREATED` 不变更状态，使 APP 重试 `pre_login` 幂等。

## 6. 错误处理契约

| 场景 | 结束状态 | 返回 code | next_step | 杀 session |
|---|---|---|---|---|
| secondLogin 探测 success | ACCOUNT_SELECTION_REQUIRED | — | select_accts | 否 |
| secondLogin needs_pin_change | AWAITING_PIN_CHANGE | SL_NEEDS_PIN_CHANGE | change_pin | 否 |
| secondLogin cooldown | PRE_LOGIN_CREATED | SL_COOLDOWN | 稍后重试 pre_login | 否 |
| secondLogin 其他失败 | （落 loginStep1） | — | — | 否 |
| loginStep1 200 + 本地指纹 | 续推链终态 | — | select_accts | 否 |
| loginStep1 200 无本地指纹 | OTP_VERIFIED | — | upload_fingerprint | 否 |
| loginStep1 100 | OTP_SENT | — | verify_otp | 否 |
| loginStep1 501 | NEEDS_RELOGIN | SL_NEEDS_RELOGIN | （终态） | 是（+下线） |
| loginStep1 423 | PRE_LOGIN_CREATED | EP_RETRY | 重试 pre_login | 否 |
| loginStep1 403/500/503 | PRE_LOGIN_CREATED | EP_UPSTREAM_ERROR | 重试 pre_login | 否 |

`retry_make_request` 自带的传输层重试不变；`423` 在其重试耗尽后才返回 `EP_RETRY` 信封。错误码语义依据 EasyPaisa v2.2 文档第 38-47 行（401 SessionInvalid / 403 CheckParam / 423 ServerBusy / 500 CommonError / 501 AccountInvalid / 503 NetworkError）。

## 7. 测试策略

手段：mock `retry_make_request` 注入云机响应，覆盖每条分支。复用/扩展现有套件：`test_easypaisa_v19_pre_login.py`、`test_easypaisa_v19_second_login.py`、`test_easypaisa_v19_urm90040.py`、`test_easypaisa_business_flow_v2.py`、`test_easypaisa_v19_state_machine.py`、`test_easypaisa_501_offline.py`。

用例：

1. 新号 + loginStep1=100 → OTP_SENT；断言未调 secondLogin
2. 新号 + loginStep1=200 无本地指纹 → fingerprintUploadRequired
3. 绑定号 + secondLogin=200 → ACCOUNT_SELECTION_REQUIRED；断言未调 loginStep1（零打扰）
4. 绑定号 + secondLogin needs_pin_change → AWAITING_PIN_CHANGE
5. 绑定号 + secondLogin cooldown → SL_COOLDOWN，状态仍 PRE_LOGIN_CREATED
6. 绑定号 + secondLogin URM90040/needs_relogin → 落 loginStep1=200+本地指纹 → 续推链成功
7. loginStep1=501 → `_mark_payment_official_501_offline` 被调 + NEEDS_RELOGIN
8. loginStep1=423 → EP_RETRY，状态 PRE_LOGIN_CREATED
9. loginStep1=403/500/503 → EP_UPSTREAM_ERROR，状态 PRE_LOGIN_CREATED
10. 回归：`second_login_http` / `change_pin_http` / 残留 session 复用 / 下游 URM90040 fallback 现有测试保持绿

## 8. 验收标准

- **AC1**：全量 easypaisa 测试套件（现有 23 个文件 + 本设计新增用例）`pytest` 全绿。
- **AC2**：`pre_login_http` 不再调用 `_is_account_registered`（测试用 grep/源码断言守护，防回归）。
- **AC3**：§7 用例 3 与 6 显式断言调用顺序——绑定健康号零 `loginStep1` 调用；探测失败号确实落到 `loginStep1`。
- **AC4**：§6 错误契约表每一行都有对应通过用例，断言 state + code + next_step + 是否杀 session。
- **AC5**：§7 用例 10 回归零失败；`STATUS_TRANSITIONS` 定义无 diff。
- **AC6**：`_second_login_chain_from_pre_login` 消除后全仓库无残留引用（grep 断言）。

## 9. 风险与假设

- 假设：secondLogin 对已绑定账号的返回码语义符合 EasyPaisa v2.2 文档与现有 `_perform_second_login`（4015 行）的 outcome 映射。验收以 mock 单元/集成测试为准（用户已确认 e2e 不在本次验收范围）。
- 风险：loginStep1 对健康号返回 200 的比例只影响“secondLogin 探测判定重上号后的回退路径”及新号上号体验；已绑定健康号走 secondLogin-first 零打扰，不依赖该比例。若比例显著偏低，仅回退/新号路径更多走 OTP，降级影响有限且可观测。
- 范围边界：不改 `_send_otp`、不改下游 `_urm90040_fallback`、不改 `STATUS_TRANSITIONS`、不改 verify_otp/verify_fingerprint/second_login/change_pin/select_accts 的对外契约。

## 10. 验收记录（2026-05-17）

- 新增测试：`test_easypaisa_v19_loginstep1_classifier.py`、`test_easypaisa_v19_fastpath.py`、`test_easypaisa_v19_pre_login_branching.py`、`test_easypaisa_v19_branching_invariants.py`。
- 回归适配：`test_pre_login_ignores_cloud_registration_probe_and_uses_loginstep1` 明确断言 `pre_login_http` 不再调用 `_is_account_registered`。
- 后续清理：`TimeOutGuard` 已确认由 `/Users/tear/pk-go-worker` 的 timeout jobs 接管，兼容类和旧语义测试已退役；见 `2026-05-17-timeoutguard-retirement-design.md`。
- 验收命令：`cd api && python3 -m pytest tests/ -q -k easypaisa`，结果 `153 passed, 152 deselected`。
