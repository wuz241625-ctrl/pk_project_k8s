# D7pay UTC 业务时间与巴基斯坦展示时区设计

## 目标

D7pay 托管实例的业务存储时间统一保持 UTC，应用层在面向用户展示、报表边界和上游接口参数时转换为巴基斯坦时间 `Asia/Karachi`。这样 MySQL、Redis、容器运行时和跨服务计算保持稳定 UTC，同时客户看到的时间符合巴基斯坦业务语境。

## 范围

- D7pay runtime ConfigMap 声明 `BUSINESS_TIMEZONE=UTC` 和 `APP_DISPLAY_TIMEZONE=Asia/Karachi`。
- 不新增 MySQL、Redis、H5、apkdownload 的 `TZ` patch，不修改 MySQL `default-time-zone`。
- `api/admin/merchant` 增加统一时区工具：UTC 用于业务存储，巴基斯坦时间用于展示和对外参数。
- API/admin 里用于第三方查询参数的硬编码 `Asia/Shanghai` 改为应用显示时区。
- 本地 Docker 示例从旧印度时区改为 UTC，避免开发环境继续写入非 UTC 时间。

## 非目标

- 不修改宿主机系统时区。
- 不改 `pk` namespace 的配置。
- 不重写历史订单时间。
- 不把 MySQL 或 Redis 改成巴基斯坦系统时区。
- 不一次性重构全项目所有 `datetime.now()`；业务写库仍依赖 UTC 运行时，展示/对外边界使用转换工具。

## 验收标准

- `python3 ops/tenants/d7pay/verify_release_contract.py` 通过，并检查 D7pay 时区合同。
- `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release` 通过。
- `PYTHONPATH=api python3 -m unittest api.tests.test_timezone_policy` 通过。
- `PYTHONPATH=admin python3 -m unittest admin.tests.test_timezone_policy` 通过。
- `PYTHONPATH=merchant python3 -m unittest merchant.tests.test_timezone_policy` 通过。
- `rg -n "Asia/(Shanghai|Kolkata)" api admin merchant ops/tenants/d7pay api/docker api/docker-compose.yml` 不再命中业务代码和 D7pay 配置。
- 线上 MySQL master/slave 保持 UTC：`now()` 与 `utc_timestamp()` 一致或只存在秒级执行差。
- 上游查询参数和展示边界使用 `APP_DISPLAY_TIMEZONE=Asia/Karachi` 输出。
