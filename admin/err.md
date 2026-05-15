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
- 运营后续可能拿新记录再次补单/核销，造成“废除”没有真正挡住同一官方交易号。

根因：

- 废除时如果修改 `utr/trans_id`，会释放 `payment_id + trade_type + trans_id` 幂等键。
- worker 采集未匹配流水时按原始 `trans_id` 查重，旧记录已被改名时无法命中。

处理：

- 废除只更新 `invalid=1` 和 `memo`，保留原始 `utr/trans_id`。
- 商户后续确认已付款时，不新增同一官方流水，改用 `/partner/restorebank_recoed` 恢复原记录。
- 历史已经被改成 `原值_id` 的废除记录，恢复时还原原始值，并先检查是否已经存在活跃重复流水。
- 新增恢复接口后要执行 `api/sql/20260515_add_bank_record_restore_permission.sql`，否则 `BaseHandler.check_auth()` 找不到权限路径时会默认允许访问。

验证：

```bash
PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore
```
