# API 排错记录

## 0.1 不允许恢复 运行时 模块

现象：

- `api/application/easypaisa_运行时` 或 `api/application/jazzcash_运行时` 再次出现。
- 登录、派单、监控脚本重新 import 运行时 reader/service。
- D7pay K8s 配置重新使用 `旧运行配置` 命名。

处理：

- 删除 运行时 模块、脚本、SQL、测试和旧设计文档。
- EasyPaisa 代收派单读取 MySQL `collection_status`。
- EasyPaisa 代付派单读取 MySQL `payout_status`。
- JazzCashBusiness 使用当前业务主线，不写 运行时 session/snapshot/index。
- D7pay K8s 环境注入统一命名为 `d7pay-config` / `d7pay-secret`。

验证：

```bash
rg "旧服务类|旧读取类" api --glob '!*.md'
PYTHONPATH=api python3 -m py_compile main.py router_lakshmi.py application/pay/pay.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py
```
