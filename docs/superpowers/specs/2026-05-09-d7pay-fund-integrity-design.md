# D7pay 资金一致性约束设计

## 背景

D7pay 当前已能运行，但资金链路不能只依赖应用层判断。线上只读核查显示：

- `orders_df.code` 唯一，但 `merchant_id + merchant_code` 只是普通索引。
- `orders_ds.trans_id` 只是普通索引。
- `bank_record.trans_id` 和 `bank_record.utr` 都只是普通索引；`utr` 维度已有重复，不能作为唯一真相。
- `balance_record.code` 只是普通索引，余额变更缺少数据库层幂等保护。

## 方案

采用“数据库唯一约束 + 余额幂等表”的方案。

1. `orders_df` 增加 `uk_orders_df_merchant_code`，约束同一商户的商户代付单号只能产生一笔平台订单。
2. `orders_ds` 增加不可见生成列 `orders_ds_trans_id_unique = NULLIF(trans_id, '')`，再对该列加唯一索引，允许空值多条，非空官方交易号唯一。
3. `bank_record` 增加不可见生成列 `bank_record_trans_id_unique = NULLIF(trans_id, '')`，再对 `payment_id + trade_type + bank_record_trans_id_unique` 加唯一索引，按钱包、交易方向和官方流水去重。
4. 增加 `balance_record_idempotency` 表，核心余额变更入口先 `INSERT IGNORE` 抢业务幂等键；抢不到表示重复业务事件，直接返回成功但不再次改余额。

## 不做的事

- 不对 `bank_record.utr` 加唯一约束，因为当前线上已有重复，且 Pakistan 业务中 `utr` 可能是付款手机号，不是官方唯一流水。
- 不对 `balance_record` 直接加粗暴组合唯一，避免误伤合法的同金额多次人工调整。
- 不修改线上数据；迁移 SQL 发现重复时会跳过对应唯一约束。

## 验收标准

- 新增迁移 SQL 可重复执行，且包含重复数据保护。
- 核心 API/Admin/Merchant/EP/JCB 余额变更入口都先抢 `balance_record_idempotency`。
- `code` 为空或旧兼容 `0` 时不启用余额幂等，避免历史零 code 场景误伤。
- 本地合同测试、相关回调/代付测试和 py_compile 通过。
