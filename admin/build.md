# Admin 构建说明

## 当前口径

- Admin 不再依赖 EasyPaisa/JazzCashBusiness 运行时 模块。
- 收款资料在线、代付在线展示以 MySQL `payment` 业务字段和旧 Redis 队列兼容口径为准。
- D7pay 配置由 `config.example.py` 读取环境变量，K8s 通过 `d7pay-config` 与 `d7pay-secret` 注入。

## 构建检查

```bash
PYTHONPATH=admin python3 -m py_compile main.py router.py application/partner/partner.py application/order/order.py application/order/auto_payout.py
```

## 验收测试

```bash
PYTHONPATH=admin python3 -m unittest admin.tests.test_count_balance admin.tests.test_client_ip admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter
```
