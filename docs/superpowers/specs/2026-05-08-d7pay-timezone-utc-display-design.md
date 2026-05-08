# D7pay UTC 存储与巴基斯坦展示时区设计

## 背景

D7pay 运行环境要求数据库、业务计算、锁、超时和调度保持 UTC，避免因为 Pod、MySQL、Redis 或宿主机时区漂移导致订单状态机不稳定。用户可见的默认日期、后台查询日界和上游需要展示时间的签名参数，按巴基斯坦时间 `Asia/Karachi` 解释。

## 方案选择

采用应用层转换方案：

- 存储和内部业务时间继续使用 UTC。
- admin、merchant、app 中“默认今天”的查询范围按 `Asia/Karachi` 自然日计算，再转成 UTC naive datetime 查询数据库。
- 上游查询签名参数里原来硬编码 `Asia/Shanghai` 的时间改为配置化展示时区。
- 不全局替换所有 `datetime.now()`，因为订单超时、锁、token 过期、Redis TTL 辅助计算仍属于 UTC/相对时间逻辑。

## 影响范围

- `api/application/timezone.py`
- `admin/application/timezone.py`
- `merchant/application/timezone.py`
- admin 和 merchant 的默认订单/流水/充值查询范围
- app 首页和代理统计里的今日起点
- OSPay/third 查询回调里的上游签名时间

## 验收标准

- `display_today_between()` 将巴基斯坦自然日转换为 UTC 查询范围。
- 后端 Python 业务代码不再出现 `Asia/Shanghai`。
- 后端 Python 业务代码不再出现 `datetime.today().date()`。
- 已有时区测试、admin 订单默认筛选测试通过。
- 改动文件可以通过 `py_compile`。

