# 2026-05-08 代收同步派单与 JazzCash 无二维码验收报告

## 改动摘要

- `/pay` 自有代收不再提前创建 `orders_ds`，只构造订单数据。
- `push_order()` 在最终 MySQL 事务里完成 `partner` 扣余额和 `orders_ds(status=1)` 插入。
- 派单失败不再落 `orders_ds(status=0/-1)`，直接返回失败。
- EasyPaisa 使用 `qrcode` 承载动态二维码结果；`account_iban` 只作为生成材料。
- JazzCash 不支持二维码，不进入二维码生成或校验链路。

## 验收结果

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py -q
```

结果：`13 passed`。

```bash
PYTHONPATH=api python3 -m pytest \
  api/tests/test_ds_dispatch_candidate_sql.py \
  api/tests/test_easypaisa_qr_payload.py \
  api/tests/test_easypaisa_mysql_eligibility.py \
  api/tests/test_easypaisa_wallet_status_dispatch.py \
  api/tests/test_ds_dispatch_push_order_new_retirement.py -q
```

结果：`23 passed`。

```bash
python3 -m py_compile api/application/pay/dispatch.py api/application/pay/pay.py api/application/pay/order.py
git diff --check
```

结果：均通过。

## 关键守卫

- `api/tests/test_ds_dispatch_candidate_sql.py::test_collection_qrcode_gate_is_easypaisa_only`
- `api/tests/test_ds_dispatch_candidate_sql.py::test_push_order_inserts_order_only_after_successful_dispatch`
- `api/tests/test_easypaisa_qr_payload.py::EasyPaisaQrPayloadTests::test_pay_builds_order_before_dispatch_without_pre_insert`

## 注意事项

强制三方通道仍然需要先落 `orders_ds`，因为三方处理函数会基于订单号回写三方字段。本次同步派单约束只针对 EasyPaisa/JazzCash 自有代收链路。
