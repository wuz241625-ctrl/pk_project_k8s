# API 构建与业务口径

## 当前口径

- EasyPaisa、JazzCashBusiness 不再使用独立 运行时 模块。
- 账号可收款、可代付、可采集以 MySQL `payment` 表业务字段为准。
- Redis 只保留旧队列和临时投影，例如 `payment_online_*`、`payment_active_*`、`hash_easypaisa`、`set_easypaisa`，不能作为最终真相源。
- D7pay 运行配置从 `config.example.py` 读取环境变量，Jenkins/K8s 通过 `d7pay-config` 和 `d7pay-secret` 注入。

## 构建

```bash
python3 -m py_compile main.py router.py router_lakshmi.py application/pay/pay.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py jobs/pakistanpay_v2.py
```

## 验收

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_easypaisa_mysql_eligibility api.tests.test_easypaisa_wallet_status_dispatch api.tests.test_easypaisa_business_flow_v2
```
