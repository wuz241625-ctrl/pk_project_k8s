# Admin 排错记录

## 0.1 不允许恢复 运行时 模块

现象：

- `admin/application/easypaisa_运行时` 或 `admin/application/jazzcash_运行时` 再次出现。
- Admin 收款资料列表重新 import 运行时 reader/service。

处理：

- 删除 运行时 模块和相关测试。
- 收款资料展示以 MySQL `payment.wallet_status`、`collection_status`、`payout_status` 为最终业务字段。
- `bank_type` / `bank_type_id` 为 `97` 或 `98` 的收款资料都属于 MySQL 最终态展示，不能再被 `payment_online_ds` / `payment_online_df` 覆盖。
- Redis 只用于兼容旧队列，不能作为最终业务状态。

验证：

```bash
rg "旧服务类|旧读取类" admin --glob '!*.md'
PYTHONPATH=admin python3 -m py_compile main.py router.py application/partner/partner.py application/order/order.py
```

## 0.2 bank_record 废除后又被重复采集

现象：

- admin 废除一条 `bank_record.callback=0` 流水后，同一官方流水后续又被 worker 采集出一条新记录。
- 运营后续可能拿新记录再次补单/核销，造成同一官方交易号存在多个可处理入口。

根因：

- 废除时如果修改 `utr/trans_id`，会释放 `payment_id + trade_type + trans_id` 幂等键。
- worker 采集未匹配流水时按原始 `trans_id` 查重，旧记录已被改名时无法命中。

处理：

- 废除只更新 `invalid=1` 和 `memo`，保留原始 `utr/trans_id`。
- 商户后续确认已付款时，不新增同一官方流水，也不先恢复流水；直接在代收普通补单接口用订单号和官方 `trans_id` 核销。
- 普通补单接口会按 `trans_id + 订单金额` 选中 `callback=0 AND trade_type=1 AND invalid IN (0,1)` 的流水；废除流水被选中后会写回 `callback=1, invalid=0, order_code=订单号`。
- 补单成功后，订单的 `utr/trans_id` 均来自选中的 `bank_record`；三方补单仍按现有 `utr`/付款手机号逻辑查询第三方，不在这里处理。
- 补单后的资金事务继续沿用现有逻辑：超时/非本码商订单扣码商，商户加款，订单状态置成功并通知商户。
- `/partner/restorebank_recoed` 已取消；历史环境如存在该权限，执行 `api/sql/20260515_disable_bank_record_restore_permission.sql` 禁用。

验证：

```bash
PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore admin.tests.test_manual_settle_bank_record
```
