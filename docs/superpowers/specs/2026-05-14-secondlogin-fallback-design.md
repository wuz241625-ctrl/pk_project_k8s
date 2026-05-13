# EasyPaisa secondLogin 失败回退到 loginStep1 设计

## 问题描述

当 `second_login_http` 调用云机 `secondLogin` 接口返回非成功状态码（501/423/503/网络错误）时：

1. Redis 会话状态停留在 `fingerprintVerified` 或 `secondLoginReady`，不推进也不回退
2. 登录锁（`login_lock_payment` / `login_lock_phone`）未释放
3. 客户端显示 `needsRelogin`，但调用 `restartViaFirstLogin()` 时被 `pre_login_http` 的重复登录检测拒绝
4. 用户只能等 Redis 会话 TTL（300s）过期后才能重试

## 目标

secondLogin 失败后，服务端自动回退到 loginStep1 流程，重新注册云机状态。客户端最小改动（~5行 Flutter）。

## 云机 secondLogin 状态码语义

| code | msg | 含义 | 处理策略 |
|------|-----|------|---------|
| 200 | success | 账户正常 | 正常推进 |
| 423 | ServerBusy | 云机正忙（并发） | sleep 2s 重试 1 次，仍失败则回退 |
| 501 | AccountInvalid | 被抢登 | 直接回退到 loginStep1 |
| 503 | NetworkError | 云机网络问题 | 直接回退到 loginStep1 |
| 401 | SessionInvalid | Session 失效 | 保持现有逻辑（session_expired） |
| HTTP 非200 / 空响应 | — | 网络不通/超时 | 直接回退到 loginStep1 |
| 解密失败 | — | 响应格式异常 | 直接回退到 loginStep1 |

注：`retry_make_request` 已内置 2 次 HTTP 重试，到达 outcome 判断时已经尝试过 2 次。

## 设计方案

### 新增方法：`_fallback_to_first_login`

```python
async def _fallback_to_first_login(self, session_data: dict, redis_key: str, reason: str) -> dict:
```

**职责**：清理当前失败的 secondLogin 会话，回退到 loginStep1 流程。

**步骤**（顺序很重要，先尝试 loginStep1 再清理旧 session）：

1. 从 `session_data` 提取必要字段：phone, payment_id, bankname, pinCode, partner_id, device_id 等
2. 调用 `_send_otp(session_data)` — 即云机 loginStep1
3. **loginStep1 成功**：
   - 覆盖写入 Redis 会话（同一个 redis_key），status=`otpSent`，复用原 payment_id，设置 TTL=300s
   - 释放登录锁：
     - `await self.redis.delete(self._login_lock_payment_key(payment_id))`
     - `await self.redis.delete(self._login_lock_phone_key(phone))`
   - 返回 `{status: 'success', data: {code: 'SL_RESTARTED', phase: 'otpSent'}}`
4. **loginStep1 失败**：
   - 不删除旧 session（保留现有状态，让客户端走 `needsRelogin` 路径）
   - 返回 `{status: 'error', data: {code: 'SL_UPSTREAM_ERROR', phase: 'failed'}}`

**新会话保留的字段**：
- `phone` — 手机号
- `payment_id` / `id` — 复用已有的 payment_id
- `bankname` — 银行标识
- `pinCode` — 用户 PIN（注意：代码中字段名是 pinCode 不是 pin）
- `partner_id` — 商户 ID
- `device_id` — 设备标识
- `app_version` — 客户端版本

**关键约束**：
- payment_id 必须复用已有的，不能新建（一个手机号只能有一个 payment_id）
- 新会话必须携带 payment_id，这样后续 verify_otp 时 `_save_payment` 走 update 路径
- `_send_otp` 需要 session_data 中包含 phone、pinCode、bankname 才能正确构建 loginStep1 请求
- **先尝试 loginStep1 再清理**：避免 loginStep1 也失败时用户处于无 session 状态
- **覆盖写入同一 redis_key**：消除删除旧 session 和创建新 session 之间的竞态窗口

### `second_login_http` 修改

在 outcome 处理分支中：

```python
if outcome == 'upstream_error':
    message = second_login_result.get('message', '')
    
    # 423: 云机正忙，sleep 2s 重试一次
    if self._is_server_busy(message):
        await asyncio.sleep(2)
        retry_result = await self._perform_second_login(session_data)
        if retry_result.get('outcome') == 'success':
            # 重试成功，正常推进到 secondLoginPassed
            session_data['status'] = 'secondLoginPassed'
            await self._persist_session_data(redis_key, session_data)
            return self._build_success_response(session_data)
        # 重试仍失败，回退
    
    # 501/503/网络错误/423重试失败：回退到 loginStep1
    fallback_result = await self._fallback_to_first_login(session_data, redis_key, reason=message)
    return fallback_result
```

**返回值设计**：

| 场景 | 返回 | 客户端行为 |
|------|------|-----------|
| fallback 成功（OTP 已发送） | `{status: 'error', data: {code: 'SL_RESTARTED', phase: 'otpSent'}}` | 跳转 OTP 输入页 |
| fallback 失败（loginStep1 也挂了） | `{status: 'error', data: {code: 'SL_UPSTREAM_ERROR', phase: 'failed'}}` | 显示 needsRelogin |

注：fallback 成功也用 `status: 'error'`，因为 Flutter `_isBusinessError` 检测 `status == 'error'` 后构建 `SecondLoginResult.failure(code: 'SL_RESTARTED')`，进入 switch 匹配。如果用 `status: 'success'`，Flutter 会解析为 `ok: true` 走 `_runQueryAndSelect()` 路径（错误）。

### 辅助方法

```python
def _is_server_busy(self, message: str) -> bool:
    """判断是否为 423 ServerBusy"""
    return '423' in str(message) or 'ServerBusy' in str(message)
```

### 状态转换

不需要修改 `STATUS_TRANSITIONS`。`_fallback_to_first_login` 直接覆盖写入同一 redis_key，新 session 从 `otpSent` 开始，不存在跨状态转换。

### 竞态条件处理

**问题**：如果先删除旧 session 再创建新 session，中间有时间窗口客户端可能读到空 session。

**解决**：
1. 先调用 `_send_otp` 确认 loginStep1 成功
2. 成功后直接覆盖写入同一 redis_key（`_persist_session_data` 是 SET 操作，天然原子）
3. 覆盖写入后再释放登录锁
4. 如果 loginStep1 失败，旧 session 保持不动，返回 `SL_UPSTREAM_ERROR`

### 重试策略总结

```
second_login_http 调用
  └→ _perform_second_login
       └→ retry_make_request (内置 2 次 HTTP 重试)
            ├→ code=200: 成功
            ├→ code=423: sleep 2s → 再调一次 _perform_second_login (又 2 次 HTTP 重试)
            │     ├→ 成功: 正常推进
            │     └→ 失败: _fallback_to_first_login
            ├→ code=501/503/网络错误: _fallback_to_first_login
            └→ code=401: 保持现有 session_expired 逻辑
```

最多 6 次 HTTP 请求后回退（首次 2 次 + 423 重试 2 次 + fallback loginStep1 2 次）。

### 客户端影响

**Flutter 最小改动（~5行）**。

`_runSecondLoginChain` 的 switch 中新增一个 case：

```dart
// onboarding_controller.dart — _runSecondLoginChain switch 内
case 'SL_RESTARTED':
  state = state.copyWith(
    busy: false,
    phase: OnboardingPhase.awaitingOtp,
    error: null,
  );
  return false;
```

**工作原理**：
- `second_login_http` 返回 `{status: 'error', data: {code: 'SL_RESTARTED', phase: 'otpSent'}}`
- Flutter `_isBusinessError` 检测到 `status == 'error'`，构建 `SecondLoginResult.failure(code: 'SL_RESTARTED')`
- switch 匹配 `'SL_RESTARTED'` → 设置 `awaitingOtp` → UI 跳到 OTP 输入页
- 用户收到新的 OTP 短信，输入后继续完成上号流程

**为什么不能零改动**：
- `_runSecondLoginChain` 是同步调用，不通过 polling 感知状态
- `startStatusPoll` 只检测 `activeSuccessful` 和 `inCooldown`
- 现有 default 分支映射到 `needsRelogin` → 用户点 "Restart" → `restartViaFirstLogin()` 会丢弃 payment_id（违反约束）

### 日志与监控

`_fallback_to_first_login` 内部记录：
- `self.logger.warning(f'secondLogin 失败({reason})，回退到 loginStep1, phone={phone}, payment_id={payment_id}')`
- 回退成功/失败都记录日志，便于排查

## 验收标准

1. **secondLogin 返回 501 时**：系统自动调用 loginStep1 → 用户收到新 OTP → 客户端自动跳到 OTP 页面 → 输入后完成上号
2. **secondLogin 返回 423 时**：系统 sleep 2s 重试一次 → 仍失败则回退 → 用户收到新 OTP
3. **secondLogin 返回 503/网络错误时**：系统直接回退 → 用户收到新 OTP
4. **回退后 payment_id 不变**：MySQL 中不会出现同一手机号的重复 payment 记录
5. **登录锁正确释放**：回退后用户不会被锁阻塞
6. **无竞态窗口**：覆盖写入同一 redis_key，客户端不会读到空 session
7. **loginStep1 也失败时**：保留旧 session 状态，返回 `SL_UPSTREAM_ERROR`，客户端走现有 `needsRelogin` 路径
8. **日志可追溯**：每次回退都有 warning 级别日志，包含 phone、payment_id、失败原因
9. **Flutter 改动最小**：仅在 `_runSecondLoginChain` switch 中新增 `SL_RESTARTED` case（~5行）

## 影响范围

| 文件 | 变更 |
|------|------|
| `api/application/app/login/banks/easypaisa.py` | 新增 `_fallback_to_first_login` 方法，修改 `second_login_http` 的 upstream_error 分支 |
| `onboarding_controller.dart` | `_runSecondLoginChain` 新增 `SL_RESTARTED` case（~5行） |
| Redis 状态机 | 无改动（STATUS_TRANSITIONS 不变） |
| MySQL | 无改动（复用已有 payment 记录） |
