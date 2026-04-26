# JazzCash OTP 后指纹验证设计

## 背景

用户要求 JCB（当前代码中对应 JazzCash）改成“发送验证码 → 验证验证码 → 验证指纹 → 激活成功”。复核后确认 JazzCash 上游没有独立 `verifyFingerprint` action，`loginStep2` 本身就是指纹验证；旧实现把 `loginStep2` 挂在 `verify_otp` 上，导致 OTP 页面实际在做指纹验证，Flutter 又把 JazzCash OTP 成功接到旧 `/active_account` 收尾。

## 设计

JazzCash 后端切到 `v1.5` send-OTP-first 模式：`pre_login` 只决定进入 `send_otp`，`verify_otp` 只做 OTP 非空检查和本地 session 推进，不调用 JazzCash 上游，并返回 `next_phase=fingerprintUploadRequired` 或 `fingerprintUploaded`。OTP 后的指纹上传允许从 `fingerprintUploadRequired` 进入 `fingerprintUploaded`。

新增 JazzCash `/login/verify_fingerprint` 分支：公开接口名保持 `verify_fingerprint`，但内部调用上游 `loginStep2` 验证指纹；成功后执行 JazzCash secondLogin 取账号信息，最后把 session 推进到 `activeSuccessful`，更新 `payment` 与 Redis 在线队列。旧 `/login/active_account` 暂保留兼容，但新 Flutter 不再调用。

Flutter 端按 EasyPaisa 的 phase 模型处理 JazzCash：OTP 成功后需要指纹则进入采集页，指纹已上传则直接调用 `verify_fingerprint`。JazzCash 的 `verify_fingerprint` 成功即进入 `activeSuccess`，不会继续调用 EasyPaisa 专属的 `second_login/query_accts/select_accts`。

## 验收标准

1. JazzCash 不配置上游 `verify_fingerprint` action。
2. JazzCash `_build_verify_fingerprint_request()` 生成 `action=loginStep2`，payload 只携带 `account_id`。
3. JazzCash `verify_otp_http()` 不调用任何 JazzCash 上游，也不调用 `_verify_account()`，返回 `next_phase=fingerprintUploadRequired/fingerprintUploaded`。
4. JazzCash OTP 后可以上传指纹，并把 Redis session 推进到 `fingerprintUploaded`。
5. `/api/v1/login/verify_fingerprint` 支持 `bankname=jazzcash`，成功后返回 `phase=activeSuccessful`。
6. Flutter JazzCash 新链路为 `requestOtp → submitOtp → uploadFingerprint/verifyFingerprint → activeSuccess`。
7. Flutter JazzCash 不调用 `active_account`、`second_login`、`query_accts`。
8. 后端单测、Flutter 单测、静态分析、APK 构建和安装验证通过。
