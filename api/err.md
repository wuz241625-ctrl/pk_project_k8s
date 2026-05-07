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

## 0.2 业务同步时不能把运行层带回

现象：

- 从 `/Users/tear/pk_project` 同步业务后，重新出现旧英文运行层 key、旧读取类或旧服务类。
- JCB v1.6 代码缺少 `application/jazzcash_gateway.py`，导致 `from application.jazzcash_gateway import ...` 失败。
- PayFast 代收跳转已合入，但 `thirdPart.py` 没有 `payfast_payment`。

处理：

- JCB/PayFast/Lakshmi API 业务可以参考 `/Users/tear/pk_project`。
- EasyPaisa 与 Admin 收款资料列表只保留 MySQL 最终状态和旧 Redis 投影清理，不恢复运行层 key。
- D7pay API 配置必须保留 `JAZZCASH_API_VERSION=v1.6`，默认值在 `api/config.example.py`。

验证：

```bash
rg "旧服务类|旧读取类" api --glob '!*.md'
PYTHONPATH=api python3 -m py_compile application/jazzcash_gateway.py application/app/login/banks/jazzcash.py application/pay/order.py application/pay/thirdPart.py jobs/jazzcash/jazzcash_auto_payout.py
```
