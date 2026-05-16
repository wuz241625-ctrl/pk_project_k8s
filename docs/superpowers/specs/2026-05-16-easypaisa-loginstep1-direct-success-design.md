# EasyPaisa loginStep1 直登成功兼容设计

## 背景

上游 `doc_EasyPaisa v2.2.txt` 明确 `loginStep1` 除了返回 `code=100` 表示需要 OTP，还可能因设备复用直接返回 `code=200`。`code=200` 表示云机已经登录成功，不需要用户继续提交 OTP。

当前 D7pay 的 EasyPaisa 指纹流程由本地 API 和 App 维护，不使用上游 `should_verify_fingerprint` 让云机代做指纹验证。因此本次只兼容 `loginStep1 code=200`，不改变指纹上传、`verifyFingerprint`、`secondLogin` 的本地链路。

## 方案

`_send_otp()` 继续调用上游 `loginStep1`，但把响应拆成两类：

- `code=100`：保持原行为，`send_otp_http` 推进到 `OTP_SENT`，App 继续输入 OTP。
- `code=200`：标记 `direct_login=True`，调用统一 helper 完成本地“OTP 已验证后”的状态推进。

统一 helper 负责：

- 保存或更新 `Payment`，继续把官方 PIN 写入 `payment.pin`。
- 如果临时 `payment_id` 从手机号变为真实 DB id，删除旧 key 并依赖现有 alias 机制兼容旧 id。
- 推进 session 到 `OTP_VERIFIED`。
- 首次登录返回 `next_phase=fingerprintUploadRequired`，由 App 上传指纹。
- URM90040 fallback 场景直接进入 `_verify_otp_fallback_chain()`，不再要求用户输入 OTP。

## 明确不做

- 不在 `loginStep1` 请求中加入 `should_verify_fingerprint`。
- 不跳过本地指纹 ZIP 上传与 `verifyFingerprint` 链路。
- 不改变 `secondLogin` 使用 DB `Payment.pin` 作为 `pwd` 的规则。

## 验收标准

- `send_otp_http` 收到 `loginStep1 code=200` 后返回 `fingerprintUploadRequired`，session 状态为 `OTP_VERIFIED`。
- URM90040 fallback 收到 `loginStep1 code=200` 后不返回 `SL_NEEDS_OTP`，而是继续 fallback 后续链路。
- `_build_send_otp_request()` 不包含 `should_verify_fingerprint`。
- EasyPaisa v1.9/v2.2 相关验收测试通过。
- `easypaisa.py` 语法编译通过。
