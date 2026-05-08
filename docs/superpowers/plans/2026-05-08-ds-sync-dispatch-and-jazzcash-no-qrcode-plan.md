# 2026-05-08 代收同步派单与 JazzCash 无二维码实施计划

## Step 1: 用例锁定

- [x] 增加 JazzCash 不需要二维码、EasyPaisa 需要二维码的门禁测试。
- [x] 增加 `push_order()` 不能更新预插订单、必须成功后插入订单的静态守卫。
- [x] 增加 `/pay` 只构造订单数据、不提前写 `orders_ds` 的静态守卫。

验收命令：

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py -q
```

## Step 2: 调整 `/pay` 写表顺序

- [x] 将 `_create_order()` 改为 `_build_order_data()`。
- [x] 自有代收派单失败时不写失败订单。
- [x] 普通自有代收不再通过 `otherpay` 自动兜底。
- [x] 保留强制三方通道的显式落单入口，不影响自有代收链路。

## Step 3: 调整 `push_order()` 事务

- [x] 增加 `_insert_order_ds_in_tx(...)`。
- [x] 最终接单事务内先扣余额，再插入 `orders_ds(status=1)`。
- [x] 插入失败时回滚余额扣减。
- [x] 候选为空时统一返回 `{"success": False, "upi": "", "qrcode": ""}`。

## Step 4: 调整二维码语义

- [x] 新增 `_requires_collection_qrcode(...)`。
- [x] EasyPaisa 生成 `qrcode` 并写 Redis QR key。
- [x] JazzCash 不要求二维码，不读取 QR，不因为无 `account_iban` 被跳过。

## Step 5: 验收

- [x] targeted pytest 通过。
- [x] 代收派单相关回归通过。
- [x] `py_compile` 通过。
- [x] `git diff --check` 通过。

## 回滚

如需回滚，撤回本次提交即可恢复旧链路。注意旧链路会重新出现预写 `orders_ds(status=0)` 和派单失败改 `-1` 的行为。
