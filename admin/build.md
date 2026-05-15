# Admin 构建说明

## 当前口径

- Admin 不再依赖 EasyPaisa/JazzCashBusiness 运行时 模块。
- EasyPaisa 与 JazzCashBusiness 收款资料在线、代收在线、代付在线展示以 MySQL `payment.wallet_status`、`collection_status`、`payout_status` 为准；旧 Redis 队列只兼容非最终态银行。
- PayFast 后台补单查询逻辑参考 `/Users/tear/pk_project`，无主动查询 API 时以回调写入的交易号为准。
- D7pay 配置由 `config.example.py` 读取环境变量，K8s 通过 `d7pay-config` 与 `d7pay-secret` 注入。

## 构建检查

```bash
PYTHONPATH=admin python3 -m py_compile main.py router.py application/partner/partner.py application/order/order.py application/order/query_third_order_status.py application/order/auto_payout.py
```

## 验收测试

```bash
PYTHONPATH=admin python3 -m unittest admin.tests.test_count_balance admin.tests.test_client_ip admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter admin.tests.test_partner_mysql_final_state admin.tests.test_bank_record_void_restore admin.tests.test_manual_settle_bank_record
```

## 银行流水废除后人工补单验收

```bash
PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore admin.tests.test_manual_settle_bank_record
```

验收口径：

- `/partner/delbank_recoed` 只把未回调流水置为 `invalid=1`，不修改 `utr/trans_id`。
- `/order/handleorder` 人工补单查询允许 `callback=0 AND trade_type=1 AND invalid IN (0,1)` 的银行流水。
- 人工补单消费流水时统一更新 `callback=1, invalid=0, order_code=订单号`，后续资金处理继续走既有扣码商、加商户、写成功订单事务。
- 不再提供 `/partner/restorebank_recoed`，误废除确认付款后直接在代收补单接口核销。
- 如果历史环境已经写入恢复权限，发布 admin 前执行 `api/sql/20260515_disable_bank_record_restore_permission.sql` 禁用残留权限。
