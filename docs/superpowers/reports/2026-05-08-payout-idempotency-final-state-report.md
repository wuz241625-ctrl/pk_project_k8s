# 代付和采集幂等最终态收敛验收报告

## 变更范围

- `api/jobs/jazzcash/payout/order_lifecycle.py`
  - JazzCash 抢单时一次性 `orders_df.status=0 -> 1`，同时写入 `payment_id/partner_id`。
  - 移除转账成功后提前写 `status=3`。
  - 增加 `_mark_unknown()`、`_handle_402()`、`_reject_order()`，收敛失败状态机。
- `api/jobs/jazzcash/payout/settlement.py`
  - 成功结算改为 `WHERE code=%s AND status=1` 守卫下推进 `status=3`。
- `api/jobs/jazzcash/payout/transfer_executor.py`
  - `402` 不再按特定 `msgCd` 分叉；`423/503/未知` 不再标记可自动重试。
- `api/jobs/pakistanpay_v2.py`
  - 移除 Redis `if_callback_*` 回调去重。
- `api/jobs/Jazzcashpay_v2.py`
  - 移除 Redis `if_callback_*` 回调去重。

## 验收结果

### 单元测试

```bash
PYTHONPATH=api python3 -m unittest \
  api.tests.test_jazzcash_payout_state_machine \
  api.tests.test_statement_callback_mysql_idempotency \
  api.tests.test_jazzcash_auto_payout_v16 -v
```

结果：11 个测试通过。

```bash
PYTHONPATH=api python3 -m pytest api/jobs/easypaisa/tests/test_order_lifecycle.py -q
```

结果：27 个测试通过。

```bash
PYTHONPATH=api python3 -m pytest \
  api/tests/test_jazzcash_payout_state_machine.py \
  api/tests/test_statement_callback_mysql_idempotency.py \
  api/tests/test_jazzcash_auto_payout_v16.py -q
```

结果：11 个测试、7 个 subtests 通过。

### 编译检查

```bash
python3 -m py_compile \
  api/jobs/jazzcash/payout/order_lifecycle.py \
  api/jobs/jazzcash/payout/settlement.py \
  api/jobs/jazzcash/payout/transfer_executor.py \
  api/jobs/pakistanpay_v2.py \
  api/jobs/Jazzcashpay_v2.py
```

结果：通过。

### 静态清理检查

```bash
rg -n "if_callback|mark_transaction_callback|clean_if_callback_key|zscore\\(self\\.if_callback_key" \
  api/jobs/pakistanpay_v2.py api/jobs/Jazzcashpay_v2.py
```

结果：无命中。

```bash
rg -n "status IN \\(0, 1\\)|new_retry_count > 8|reject_msg_codes|msg_cd in reject_msg_codes" \
  api/jobs/jazzcash/payout/order_lifecycle.py \
  api/jobs/jazzcash/payout/settlement.py \
  api/jobs/jazzcash/payout/transfer_executor.py
```

结果：无命中。

```bash
git diff --check
```

结果：通过。

## 验收结论

本地代码已按当前原则收敛：

- JazzCash 代付不再提前写成功态。
- JazzCash 成功态由 settlement 以 `status=1` 守卫推进。
- JazzCash 只有 `402` 自动重试，第三次驳回；未知结果进入人工待确认。
- 账单采集不再用 Redis 集合作为“已回调”最终判断，重复入账依赖 MySQL 订单/流水幂等。
