# 2026-05-08 代收同步派单与 JazzCash 无二维码设计

## 背景

当前 `/pay` 代收链路存在两个混淆点：

1. 先插入 `orders_ds(status=0)`，再调用 `push_order()` 找码。派单失败时再把订单改成 `-1`，这让同步派单变成了“先有订单、后找码”的异步味道。
2. EasyPaisa 动态二维码依赖 `account_iban` 生成，但 `account_iban` 不是二维码字段本身。JazzCash 当前不支持二维码，因此不能因为没有 IBAN 或 QR 就跳过 JazzCash。

## 目标

- 自有代收必须是同步派单：派单成功才写 `orders_ds`。
- 派单失败直接返回失败，不预写失败订单，不走 `otherpay` 兜底延长耗时。
- 订单插入必须与码商余额扣减在同一个 MySQL 事务里完成，保证不超售和不脏写订单。
- EasyPaisa 的二维码输出语义使用 `qrcode`；`account_iban` 只作为生成二维码的底层材料。
- JazzCash 明确不需要二维码，不进入 QR 生成和 QR 校验链路。

## 设计

`Pay.post()` 只做参数、商户、通道和费率校验，然后调用 `_build_order_data()` 构造订单数据，不再提前插入 `orders_ds`。

`push_order()` 先通过候选 SQL 获取可接单码，再逐个做业务校验。进入最终接单事务后，固定顺序是：

1. `FOR UPDATE NOWAIT` 锁定 `partner` 和 `payment`。
2. 锁后复核码商状态、码状态、余额、限额。
3. 扣减码商余额。
4. `INSERT orders_ds(status=1, payment_id=..., partner_id=...)`。
5. 提交事务。

任一步失败都 `rollback` 并换下一个候选；候选耗尽时直接返回失败，不写 `orders_ds`。

二维码口径由 `_requires_collection_qrcode(payment, bank)` 决定：

- EasyPaisa：需要二维码；派单前生成 `qrcode`，生成失败则跳过该码。
- JazzCash：不支持二维码；不生成、不校验、不返回 `qrcode`。
- 其他未知银行：默认不要求二维码，避免把 EasyPaisa 专属规则扩散到其他钱包。

## 验收标准

- `Pay.post()` 不再调用 `_create_order()` 或提前 `create_result('orders_ds', ...)`。
- `push_order()` 内不再执行 `UPDATE orders_ds ... WHERE code=%s AND status=0`。
- `push_order()` 必须先 `change_balance()`，再 `_insert_order_ds_in_tx(...)`。
- EasyPaisa 成功派单返回 `qrcode` 并写 `order_ds_third_qr_{code}`。
- JazzCash 成功派单 `qrcode=''`，且日志显示不需要二维码。
- 派单失败返回失败消息，不写 `orders_ds(status=0/-1)`。
