# JazzCashBusiness loginStep2 冷却期语义修正设计

## 背景

JazzCashBusiness 上游没有独立的 `verifyFingerprint` action。采集端和后端的 `/api/v1/login/verify_fingerprint` 只是我方接口名；真实上游动作是 `loginStep1`、`loginStep2`、`secondLogin`。

`loginStep2` 返回 `JC-CPS-COOL-T01` 时，业务含义不是“指纹未验证”或“需要重新上传指纹”，而是“指纹/BVS 已通过，设备注册进入 120 分钟冷却期”。冷却期结束后不应再次调用 `loginStep2`，应直接调用 `secondLogin` 检查账户是否可用。

## 设计

后端唯一真相源改为：

```text
status=fingerprintVerified
last_error.code=FP_COOLDOWN
cd_until=当前时间+120分钟
fingerprint_path=/fingerprint/...
```

冷却期间：

- `/login/payment_status` 返回 `next_action=wait_cooldown`。
- `/login/verify_fingerprint` 直接返回 `FP_COOLDOWN`，不请求上游。
- App 展示“指纹已验证，设备冷却中”，不要求重新采集。

冷却结束后：

- 用户继续调用我方 `/login/verify_fingerprint`。
- 后端看到 `fingerprintVerified + FP_COOLDOWN + cd_until已过`，跳过 `loginStep2`，直接执行 `secondLogin`。
- 对已经在线上写成 `fingerprintUploaded + FP_COOLDOWN + cd_until已过` 的旧会话，先迁移为 `fingerprintVerified`，再执行 `secondLogin`。
- `secondLogin code=200` 后进入 `activeSuccessful`。
- `secondLogin` 仍返回冷却时，重新写入新的 `cd_until`，状态保持 `fingerprintVerified`。

## 非目标

- 不新增官方 JazzCash App 接口请求。
- 不改 App 对外 API 名字，继续复用 `/api/v1/login/verify_fingerprint`。
- 不改变 EasyPaisa 流程。

## 验收标准

- `loginStep2` 冷却分支写入 `fingerprintVerified`，并保留指纹文件路径。
- 冷却期内重复调用不请求 `loginStep2` 或 `secondLogin`。
- 冷却到期后直接请求 `secondLogin`，不再请求 `loginStep2`。
- 旧的 `fingerprintUploaded + FP_COOLDOWN` 冷却会话到期后也直接请求 `secondLogin`。
- `payment_status` 对 `fingerprintVerified + FP_COOLDOWN + cd_until未到` 返回 `wait_cooldown`。
- App 冷却文案不再说“Fingerprint is uploaded”，改为“Fingerprint verified”。
- 后端和 App 测试、静态检查通过。
