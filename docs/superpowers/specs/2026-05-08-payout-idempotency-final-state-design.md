# 代付和采集幂等最终态收敛设计

## 目标

把当前 EasyPaisa/JazzCash 链路收敛到四条长期维护原则：

- 派单靠 MySQL 事务和状态守卫防超售。
- 采集靠 MySQL 订单/流水幂等防重复入账。
- 代付靠 `orders_df` 状态机防重复出款。
- 业务最终态落 MySQL，Redis 只做锁、缓存和临时调度信号。

## 范围

本次只修已排查到的不一致点，不做兼容式兜底扩散：

- JazzCash 代付成功态不能在 `order_lifecycle.py` 提前写 `status=3`。
- JazzCash 成功结算必须由 `settlement.py` 在 `WHERE status=1` 守卫下推进到 `status=3`。
- JazzCash 只有官方 `402` 允许重试，第三次 `402` 直接驳回；`500/503/423/无响应/异常` 都进入人工待确认 `status=2`。
- EasyPaisa/JazzCash 账单 worker 不再用 Redis `if_callback_*` 判断“是否已回调过”，重复账单由 MySQL `bank_record`、`orders_ds` 状态和交易号检查兜底。

## 非目标

- 不新增数据库表。
- 不改代收候选 SQL。
- 不新增 Redis Stream 或任务表。
- 不兼容旧印度钱包、旧在线队列和旧 WebSocket 业务最终态。

## 数据流

### JazzCash 代付

1. 查询 `orders_df.status=0` 的待处理订单。
2. 选中 `payment.payout_status=1` 的账号并获取 Redis 短锁。
3. MySQL 原子抢单：`orders_df status=0 -> 1`，同时写入 `payment_id/partner_id`。
4. 只有抢单成功后才调用官方转账。
5. 官方成功：进入 `settlement.handle_payout_success()`，在 `WHERE code=? AND status=1` 下结算并推进 `status=3`。
6. 官方 `402`：第 1、2 次回到 `status=0` 并增加 `retry_count`；第 3 次走驳回退款。
7. 其他未知结果：写 `status=2`，等待人工/账单确认，绝不自动回到待处理池。

### 采集回调

1. 账单 worker 扫到收入流水后每次都尝试回调内部接口。
2. `/order/Success` 对 EasyPaisa/JazzCash `New` 流水统一先抢 `success_busy_{trans_id}` 短锁，再查 MySQL `bank_record`，最后才进入 `callback.success_ds/success_df`。
3. 重复流水不再返回失败码给采集 worker：
   - `bank_record.callback=1` 表示流水已绑定订单，采集入口返回 `code=100` 幂等接收。
   - `bank_record.callback=0` 表示流水已采集但未绑定订单，只允许补单链路处理；采集入口返回 `code=100` 幂等接收，但不再重复推进业务回调。
4. 新流水仍由内部接口用 MySQL 幂等判断订单：
   - `orders_ds.status in (-1,1,2)`
   - `orders_ds.trans_id` 重复检查
   - 成功时写 `bank_record.callback=1/order_code`
   - 失败且需留痕时写 `bank_record.callback=0`
5. Redis 不再保存“已回调流水集合”，避免 Redis 丢失或过期导致业务语义变化。

## 验收标准

- `api.tests.test_jazzcash_payout_state_machine` 通过。
- `api.tests.test_statement_callback_mysql_idempotency` 通过。
- `api.tests.test_jazzcash_auto_payout_v16` 通过。
- `api/jobs/jazzcash/payout/order_lifecycle.py` 不再出现提前 `status IN (0, 1) -> 3`。
- `api/jobs/jazzcash/payout/settlement.py` 必须包含 `WHERE code=%s AND status=1`。
- `api/jobs/pakistanpay_v2.py` 和 `api/jobs/Jazzcashpay_v2.py` 不再出现 `if_callback_*` Redis 去重逻辑。
- `/order/Success` 的 EasyPaisa/JazzCash `New` 回调必须在 `callback.success_ds/success_df` 前获取 `success_busy_{trans_id}`。
- 重复 `bank_record` 必须返回 `code=100` 幂等接收，不能让 worker 反复重试；`callback=0` 只能留给补单链路。
