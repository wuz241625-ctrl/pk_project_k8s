# EasyPaisa activeSuccessful 同步设计

## 背景

线上 `03009208353 / payment_id=533299` 已经走到 EasyPaisa `activeSuccessful`，但曾出现 `payment.status=0`、runtime `collect_enabled=false` 的状态漂移。排查确认不是人工禁用，而是账户选择完成路径先调用 `_update_payment()`，后把 session 推进到 `activeSuccessful`；同时 runtime 在中间态写过 `collect_enabled=false` 后，激活成功没有显式恢复采集/派单开关。

## 业务判断

EasyPaisa 上号成功以 `activeSuccessful` 为准。进入该状态表示银行登录态可用、账户已选择、指纹链路已完成。业务上新号成功后应默认启用收款资料，并允许采集账单；代收/代付派单再受 `payment.status`、`certified`、`manual_status`、健康暂停等业务开关约束。

本次修复只处理 EasyPaisa 上号成功链路，不改变后台手动禁用、人工锁定、健康检查暂停的语义。

## 方案

1. 在 `select_accts_http()` 账户选择成功时，先构造“即将 activeSuccessful”的 payment 更新数据，让 `_update_payment()` 能同步写入 `payment.status=1`。
2. 再调用 `_update_session_status(..., activeSuccessful, ...)` 持久化 Redis session 和 runtime snapshot。
3. 在 `_sync_runtime_state()` 处理 `activeSuccessful` 时，显式传入 `collect_enabled=true`、`ds_order_enabled=true`、`df_order_enabled=true`，避免继承 `accountSelectionRequired` 阶段的 false。
4. 保留既有后台/admin/app 开关入口，后续如果用户手动禁用或人工锁定，仍由对应入口把派单状态关闭。

## 验收标准

- 账户选择路径进入 `activeSuccessful` 时，传给 `_update_payment()` 的 session 状态必须已经是 `activeSuccessful`。
- 账户选择路径完成后 runtime snapshot 必须满足：`online=true`、`collect_enabled=true`、`ds_order_enabled=true`、`df_order_enabled=true`、`dispatch_ds=true`、`dispatch_df=true`。
- 既有 EasyPaisa business-flow v2 测试通过。
- 既有 EasyPaisa runtime service 测试通过。
- 文档记录本次问题根因、修复方式和验证命令。
