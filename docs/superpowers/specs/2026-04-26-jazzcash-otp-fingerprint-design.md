# JazzCash OTP 后指纹验证设计

## 背景

用户要求 JCB（当前代码中对应 JazzCash）改成“发送验证码 → 验证验证码 → 验证指纹 → 激活成功”。旧实现里 `verify_otp` 的 `loginStep2` 请求把 `should_verify_otpcode` 设为 `False`、`should_verify_fingerprint` 设为 `True`，导致 OTP 页面实际在做指纹验证；Flutter 又把 JazzCash OTP 成功接到旧 `/active_account` 收尾。

## 设计

JazzCash 后端切到 `v1.5` send-OTP-first 模式：`pre_login` 只决定进入 `send_otp`，`verify_otp` 只验证 OTP，并返回 `next_phase=fingerprintUploadRequired` 或 `fingerprintUploaded`。OTP 后的指纹上传允许从 `fingerprintUploadRequired` 进入 `fingerprintUploaded`。

新增 JazzCash `/login/verify_fingerprint` 分支：成功时先调用上游指纹验证，再内部执行 JazzCash secondLogin 取账号信息，最后把 session 推进到 `activeSuccessful`，更新 `payment` 与 Redis 在线队列。旧 `/login/active_account` 暂保留兼容，但新 Flutter 不再调用。

Flutter 端按 EasyPaisa 的 phase 模型处理 JazzCash：OTP 成功后需要指纹则进入采集页，指纹已上传则直接调用 `verify_fingerprint`。JazzCash 的 `verify_fingerprint` 成功即进入 `activeSuccess`，不会继续调用 EasyPaisa 专属的 `second_login/query_accts/select_accts`。

## 验收标准

1. JazzCash `_build_verify_otp_request()` 生成 `should_verify_otpcode=True` 且 `should_verify_fingerprint=False`。
2. JazzCash `verify_otp_http()` 不调用 `_verify_account()`，返回 `next_phase=fingerprintUploadRequired/fingerprintUploaded`。
3. JazzCash OTP 后可以上传指纹，并把 Redis session 推进到 `fingerprintUploaded`。
4. `/api/v1/login/verify_fingerprint` 支持 `bankname=jazzcash`，成功后返回 `phase=activeSuccessful`。
5. Flutter JazzCash 新链路为 `requestOtp → submitOtp → uploadFingerprint/verifyFingerprint → activeSuccess`。
6. Flutter JazzCash 不调用 `active_account`、`second_login`、`query_accts`。
7. 后端单测、Flutter 单测、静态分析、APK 构建和安装验证通过。
