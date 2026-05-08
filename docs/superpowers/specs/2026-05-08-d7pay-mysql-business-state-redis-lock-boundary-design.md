# D7pay MySQL 业务态与 Redis 锁边界设计

## 目标

D7pay 的钱包业务资格判断必须以 MySQL 业务态为准。Redis 只允许承担锁、临时缓存、幂等、通知、会话等辅助职责，不再作为“可代收、可采集、可代付、是否在线”的最终判断源。

## 范围

本次只处理仍会把旧 Redis 投影当作业务状态或历史清理入口的代码：

- `api/application/lakshmi_api/services/payments/e_wallet_handler.py`
- `api/application/base.py`
- `admin/application/order/order.py`

不处理历史 Redis 数据本身。旧 key 例如 `payment_online_df`、`payment_active_df`、`payment_active_channel_*` 的数据残留，后续由独立清理脚本处理。

## 业务规则

1. Lakshmi 钱包代付状态读取 `_read_mysql_business_status()`，最终使用 `can_dispatch_df(payment)` 判断。
2. 如果当前钱包类型已经切到 MySQL final status，但 MySQL 没有可用业务态，则返回不可代付，不降级读取 Redis。
3. `clear_active()` 不再扫描或清理 `payment_active_channel_*`。接单资格不依赖旧 active channel 投影。
4. 后台代付成功/取消后的 `requeue_df_if_online()` 不再清理或回写 `payment_active_df`。是否可继续代付由 MySQL `payout_status` 和 worker 资格查询决定。
5. Redis 仍可保留为锁和缓存，例如限频、订单锁、余额缓存、上号会话、通知队列等，但不能作为业务资格裁判。

## 非目标

- 不删除 Redis 配置、连接、余额缓存、锁和通知机制。
- 不清理线上历史 Redis key。
- 不改 IP 识别和时区展示。
- 不改 D7pay Jenkins、K8s、env、域名、APK 或前端配置。

## 验收标准

- `payment_online_df` 不出现在 Lakshmi `e_wallet_handler.py` 中。
- `payment_active_channel_` 不出现在 API `base.py` 中。
- `payment_active_df` 不出现在 Admin `order.py` 中。
- 新增测试先能证明旧实现失败，修改后通过。
- 既有 API/Admin/Merchant IP 和时区测试继续通过。
- D7pay release contract 继续通过。
