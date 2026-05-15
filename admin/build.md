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
PYTHONPATH=admin python3 -m unittest admin.tests.test_count_balance admin.tests.test_client_ip admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter admin.tests.test_partner_mysql_final_state admin.tests.test_bank_record_void_restore
```

## 银行流水废除/恢复验收

```bash
PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore
```

验收口径：

- `/partner/delbank_recoed` 只把未回调流水置为 `invalid=1`，不修改 `utr/trans_id`。
- `/partner/restorebank_recoed` 只恢复 `callback=0 AND invalid=1` 的流水。
- 恢复历史废除数据时，若 `utr/trans_id` 带 `_{id}` 后缀，先还原原始值并检查活跃重复流水。
- 发布 admin 前先执行 `api/sql/20260515_add_bank_record_restore_permission.sql`，避免新恢复接口因权限表缺路径而默认放行。
