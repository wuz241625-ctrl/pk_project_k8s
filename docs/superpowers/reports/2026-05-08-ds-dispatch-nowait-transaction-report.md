# 2026-05-08 代收派单 NOWAIT 事务验收报告

## 改动范围

- `api/application/pay/dispatch.py`
  - 新增 NOWAIT 锁冲突识别。
  - 新增 `partner -> payment` 固定顺序行锁。
  - 最终接单事务锁后重新校验码商余额、码状态、人工锁、`amount_top` 和外部码商未回调扣款流水。
  - 锁冲突时回滚并换下一个候选。
- `api/tests/test_ds_dispatch_candidate_sql.py`
  - 覆盖候选 SQL 不加锁。
  - 覆盖 NOWAIT 错误识别。
  - 覆盖锁 SQL 顺序和 `push_order()` 锁后扣款顺序。
- `api/build.md`
  - 增加 NOWAIT 事务验收命令。
- `api/err.md`
  - 增加热点锁等待排查口径。

## 验收标准

- 候选 SQL 不包含 `FOR UPDATE` 或 `NOWAIT`。
- 最终抢占事务包含 `partner FOR UPDATE NOWAIT` 和 `payment FOR UPDATE NOWAIT`。
- 锁顺序固定为 `partner -> payment`。
- MySQL `3572` 和 `1205` 被识别为锁冲突。
- 锁冲突不会扣余额，不会写订单状态，会继续换候选。
- `change_balance()` 位于锁成功和锁后复核之后。
- `orders_ds` 继续使用 `WHERE code=%s AND status=0` 做订单幂等推进。

## 验收命令

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py -q
PYTHONPATH=api python3 -m pytest \
  api/tests/test_ds_dispatch_candidate_sql.py \
  api/tests/test_easypaisa_mysql_eligibility.py \
  api/tests/test_easypaisa_wallet_status_dispatch.py \
  api/tests/test_ds_dispatch_push_order_new_retirement.py -q
python3 -m py_compile api/application/pay/dispatch.py api/application/pay/pay.py
git diff --check
```

## 结果

- `PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py -q`
  - 结果：`6 passed, 3 warnings`
- `PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_mysql_eligibility.py api/tests/test_easypaisa_wallet_status_dispatch.py api/tests/test_ds_dispatch_push_order_new_retirement.py -q`
  - 结果：`16 passed, 3 warnings`
- `python3 -m py_compile api/application/pay/dispatch.py api/application/pay/pay.py`
  - 结果：exit 0
- `git diff --check`
  - 结果：exit 0
