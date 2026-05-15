# Bank Record 废除恢复设计

## 背景

D7pay 代收补单流水来自 `bank_record.callback=0`。当前 admin 的“废除”会把 `bank_record.invalid` 置为 `1`，同时把 `utr` 和 `trans_id` 改成带 `id` 后缀的值。这样可以让同一官方流水后续重新采集入库，但也释放了 `payment_id + trade_type + trans_id` 幂等键，导致“永久废除”语义下仍可能再次核销。

## 目标

- 废除未核销流水后，保留原始 `utr/trans_id`，防止同一官方流水重复采集入库。
- 误废除后通过“恢复”同一条 `bank_record` 回到可核销状态。
- 历史已经被改成 `原值_id` 的废除记录，恢复时尝试还原原始 `utr/trans_id`，并先做活跃重复检查。
- 已核销流水 `callback=1` 不允许废除或恢复。

## 方案

### 后端

- 修改 `/partner/delbank_recoed`：
  - 只允许 `callback=0` 的记录废除。
  - 废除时只更新 `invalid=1` 和 `memo`。
  - 不再修改 `utr` 和 `trans_id`。
- 新增 `/partner/restorebank_recoed`：
  - 只允许 `callback=0 AND invalid=1` 的记录恢复。
  - 若 `utr/trans_id` 以 `_{id}` 结尾，恢复时剥离后缀，兼容历史废除数据。
  - 若存在另一条 `payment_id + trade_type + trans_id + invalid=0` 的活跃流水，拒绝恢复，避免重复核销入口。
  - 更新 `invalid=0`，并追加恢复原因到 `memo`。
- 新增权限 SQL `api/sql/20260515_add_bank_record_restore_permission.sql`：
  - 发布 admin 前先执行，避免新路径在权限表不存在时被 `BaseHandler.check_auth()` 默认放行。

### 前端

- 银行流水列表保留原“废除”按钮。
- 当 `invalid=1 AND callback=0` 时显示 `↩️ 恢复`。
- 恢复按钮弹出确认框，传入 `id` 和可选备注，调用 `/partner/restorebank_recoed`。

## 验收标准

1. 废除 helper 不再生成 `utr/trans_id` 更新字段。
2. 恢复 helper 能把 `TXN_123` 在记录 `id=123` 时恢复为 `TXN`。
3. 恢复前会用 `payment_id + trade_type + trans_id + invalid=0` 判断活跃重复流水。
4. 前端银行流水页对 `invalid=1 AND callback=0` 显示恢复入口。
5. `admin` Python 单测通过。
6. `admin-h5` D7pay 构建通过。
7. 权限 SQL 存在 `/partner/restorebank_recoed` 的幂等插入。
8. GitNexus 变更检测只覆盖预期的 admin/admin-h5/api SQL 文档和代码。
