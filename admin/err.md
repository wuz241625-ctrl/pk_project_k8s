# Admin 排错记录

## 0.1 不允许恢复 运行时 模块

现象：

- `admin/application/easypaisa_运行时` 或 `admin/application/jazzcash_运行时` 再次出现。
- Admin 收款资料列表重新 import 运行时 reader/service。

处理：

- 删除 运行时 模块和相关测试。
- 收款资料展示以 MySQL `payment.wallet_status`、`collection_status`、`payout_status` 为最终业务字段。
- Redis 只用于兼容旧队列，不能作为最终业务状态。

验证：

```bash
rg "旧服务类|旧读取类" admin --glob '!*.md'
PYTHONPATH=admin python3 -m py_compile main.py router.py application/partner/partner.py application/order/order.py
```
