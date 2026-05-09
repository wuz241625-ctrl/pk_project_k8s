# D7pay 资金一致性约束处理报告

## 处理内容

- 新增 `api/sql/20260509_add_fund_integrity_constraints.sql`。
  - `orders_df(merchant_id, merchant_code)` 唯一约束。
  - `orders_ds.trans_id` 非空唯一约束，空值通过不可见生成列保留多条兼容。
  - `bank_record(payment_id, trade_type, trans_id)` 非空业务唯一约束。
  - `balance_record_idempotency` 余额流水幂等表。
- 新增 `balance_idempotency.py` helper，并接入：
  - `api/application/base.py`
  - `admin/application/base.py`
  - `merchant/application/base.py`
  - `api/jobs/easypaisa/payout/settlement.py`
  - `api/jobs/jazzcash/payout/settlement.py`

## 线上只读核查结论

- `orders_df` 当前 0 行，无 `merchant_id + merchant_code` 重复。
- `orders_ds` 当前 0 行，无非空 `trans_id` 重复。
- `bank_record` 当前 38 行，非空 `trans_id` 无重复；`utr` 有 2 组重复，因此不使用 `utr` 做唯一约束。
- `balance_record` 当前 0 行，无重复。

## 上线注意事项

1. 先备份 MySQL。
2. 先执行 `api/sql/20260509_add_fund_integrity_constraints.sql`，再发布应用镜像。
3. 如果迁移输出 `unique index add skipped because duplicates exist`，先只读查重并清理业务脏数据后再补唯一索引。
4. 迁移表不存在时，代码会兼容跳过余额幂等保护，避免先发代码造成余额接口不可用；正式上线必须执行迁移。

## 验收命令

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_fund_integrity_contract.py -q
PYTHONPATH=api python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_fund_integrity_contract.py -q
python3 -m py_compile api/application/balance_idempotency.py admin/application/balance_idempotency.py merchant/application/balance_idempotency.py api/application/base.py admin/application/base.py merchant/application/base.py api/jobs/easypaisa/payout/settlement.py api/jobs/jazzcash/payout/settlement.py
```
