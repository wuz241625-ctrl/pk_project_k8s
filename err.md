# 项目排错索引

## 0.1 D7pay 清理不用项目和 运行时 残留

本项目当前不再保留：

- `旧移动 H5`
- `Lakshmi UniApp 子模块`
- EasyPaisa/JazzCashBusiness 运行时 模块
- D7pay `旧运行配置` 配置命名

排查入口：

- [api/err.md](/Users/tear/pk_project_k8s/api/err.md)
- [admin/err.md](/Users/tear/pk_project_k8s/admin/err.md)
- [ops/tenants/d7pay/err.md](/Users/tear/pk_project_k8s/ops/tenants/d7pay/err.md)

## 0.2 D7pay 时区处理原则

现象：

- 后台默认“今天”查询使用服务器日期，和巴基斯坦自然日不一致。
- 上游查询签名时间残留 `Asia/Shanghai`。

处理：

- 数据库存储、锁、超时、调度继续按 UTC。
- 用户可见默认查询日界用 `display_today_between()` 从 `Asia/Karachi` 转 UTC。
- 上游展示时间使用 `display_now()`，不硬编码地区。

验收：

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_timezone_policy
PYTHONPATH=admin python3 -m unittest admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter
PYTHONPATH=merchant python3 -m unittest merchant.tests.test_timezone_policy
rg -n "Asia/Shanghai|datetime\\.today\\(\\)\\.date\\(\\)" api admin merchant -g '*.py'
```
