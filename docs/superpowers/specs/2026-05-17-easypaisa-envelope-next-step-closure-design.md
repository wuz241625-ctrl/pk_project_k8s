# EasyPaisa Envelope Next Step 闭环设计

## 背景

EasyPaisa v1.9 登录链路已经统一了主状态机和 `ACCOUNT_SELECTION_REQUIRED` / `NEEDS_RELOGIN` 的下一步语义，但源码扫描仍发现若干返回体只带 `phase` 或 `next_phase`，没有 `next_step`。这会让 App 在失败、冷却、幂等成功、选择完成等边缘路径里继续猜下一步动作。

## 头脑风暴

### 方案 A：只补主成功路径

只给 `verify_otp_http`、`verify_fingerprint_http`、`select_accts_http` 的成功响应补 `next_step`。改动小，但冷却、指纹失败、本地保存失败、历史 fallback 仍不闭环。

### 方案 B：所有带状态的返回体都补 `next_step`

凡是 `data` 中出现 `phase` 或 `next_phase`，都必须同时返回可执行的 `next_step`。新增扫描型测试守护这个协议，不改状态推进、不改 Redis / DB / 上游调用。

### 方案 C：重构统一 envelope builder

新增统一 response builder，所有接口集中调用。长期更干净，但 `easypaisa.py` 当前链路很长，短期会扩大影响面，容易把响应字段和状态推进一起扰动。

## 决策

采用方案 B。它能把当前缺口一次补齐，测试可直接防回归，且不改变业务流转，只补协议字段。

## 设计

- `OTP_VERIFIED` 对应 `next_step=upload_fingerprint`。
- `FINGERPRINT_VERIFIED` 对应 `next_step=second_login`。
- `ACCOUNT_SELECTION_REQUIRED` 对应 `next_step=select_accts`。
- `ACTIVE_SUCCESSFUL` 对应 `next_step=ready`。
- `AWAITING_PIN_CHANGE` 对应 `next_step=change_pin`。
- 历史 `_fallback_to_first_login` 的 `otpSent` 返回 `next_step=verify_otp`；失败返回 `next_step=pre_login`。
- 对 `fingerprintUploaded` 这种临时 phase 保持 `next_step=verify_fingerprint`。
- 对 `failed` 这种非状态机 phase 使用 `next_step=pre_login`，避免 App 无动作可走。

## 非目标

- 不删除 `_pre_login_second_time_chain`、`_fallback_to_first_login` 等历史辅助方法。
- 不改变状态机 `STATUS_TRANSITIONS`。
- 不改变 `upload_fingerprint`、`verify_fingerprint`、`secondLogin`、`queryAccountList` 的调用顺序。
- 不改变 MySQL / Redis 写入策略。

## 验收标准

- AC1：源码扫描中，EasyPaisa 所有直接返回体只要 `data` 含 `phase` 或 `next_phase`，就必须含 `next_step`。
- AC2：首次 OTP 成功与 loginStep1 direct success 返回 `next_step=upload_fingerprint`。
- AC3：verify fingerprint 成功返回 `phase=fingerprintVerified,next_step=second_login`。
- AC4：select accounts 成功返回 `phase=activeSuccessful,next_step=ready`。
- AC5：冷却、指纹失败、本地保存失败、PIN 修改拒绝、query accounts 成功等边缘返回体都有明确 `next_step`。
- AC6：EasyPaisa 回归、语法检查、GitNexus detect_changes 通过。
