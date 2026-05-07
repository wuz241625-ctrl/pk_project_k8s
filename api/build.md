# API 构建说明

## 当前口径

- API 不再保留 `easypaisa_运行时` / `jazzcash_运行时` 模块。
- EasyPaisa 派单读取 MySQL `collection_status` / `payout_status`。
- JazzCashBusiness 回到业务主线实现，不再写 Redis 运行时 session/snapshot/index。
- D7pay 配置由 `config.example.py` 读取环境变量，K8s 通过 `d7pay-config` 与 `d7pay-secret` 注入。

## 构建检查

```bash
PYTHONPATH=api python3 -m py_compile main.py router_lakshmi.py application/pay/pay.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py jobs/pakistanpay_v2.py jobs/easypaisa/easypaisa_monitor.py
```

## 验收测试

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_easypaisa_mysql_eligibility api.tests.test_easypaisa_wallet_status_dispatch api.tests.test_easypaisa_business_flow_v2 api.tests.test_easypaisa_legacy_state_retirement
```
