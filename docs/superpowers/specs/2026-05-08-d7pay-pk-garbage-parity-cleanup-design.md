# D7pay 参考 pk_project 垃圾清理设计

## 目标

按文件系统直接参考 `/Users/tear/pk_project` 当前代码，清理 D7pay 分支中已经不属于当前租户业务链路的旧印度钱包、PhonePe 和旧 Redis 维护残留，让 D7pay 只保留 EasyPaisa / JazzCashBusiness 相关运行链路。

## 清理范围

- 删除旧印度钱包 service：Freecharge、PhonePe、Mobikwik、Airtel、Amazon、Indus、ULCASH、Jio、Maha。
- 删除 `api/application/phonepe/` 及 `/phonepe/*` 路由。
- 删除旧 Redis 维护脚本：`check_proxy.py`、`clear_redis_dsdf.py`、`clear_redis_inactive_payment.py`、`collect_partner_status.py`、`order_push.py`、`weight.py`。
- 删除旧银行 SQL 和 PhonePe 静态图标。
- 同步 pk_project 当前文件中已经收口的注册表、App 控制器、派单、worker 和 Admin 重置逻辑。

## 保留范围

- 保留 D7pay 租户配置：`config.example.py`、`client_ip.py`、`timezone.py`、`ops/tenants/d7pay/`、Jenkins/K8s 相关文件。
- 保留 `api/application/lakshmi_api` 目录本身，因为它仍承载 Flutter App `/v1` 登录、上号、订单和 websocket 接口。
- 保留通用三方回调和 PayFast/JCB/EasyPaisa 当前业务文件。

## 验收标准

- 被删除的旧模块不再被 Git 跟踪。
- `rg` 查不到旧 service class、`application.phonepe`、`/phonepe`、旧 Indus/Amazon 专用路由引用。
- API 核心文件可以通过 `py_compile`。
- EasyPaisa/JazzCash 相关定向测试通过。
- 文档说明当前清理边界，不再写“PhonePe 仍不能清理”的旧口径。
