# Merchant 构建说明

## 当前口径

- Merchant 不依赖 运行时 模块。
- D7pay 配置由 `config.example.py` 读取环境变量，K8s 通过 `d7pay-config` 与 `d7pay-secret` 注入。

## 构建检查

```bash
PYTHONPATH=merchant python3 -m py_compile main.py router.py application/base.py application/order/order.py application/setting/setting.py
```

## 验收测试

```bash
PYTHONPATH=merchant python3 -m unittest merchant.tests.test_client_ip merchant.tests.test_timezone_policy
```
