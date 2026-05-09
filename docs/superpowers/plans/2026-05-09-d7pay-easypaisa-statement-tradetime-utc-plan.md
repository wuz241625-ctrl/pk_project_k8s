# D7pay EasyPaisa tradeTime UTC 匹配计划

## 目标

MySQL 和系统时间保持 UTC，EasyPaisa 上游账单 `tradeTime` 按巴基斯坦时间解释。代收账单确认和代付账单观察在进入窗口比较前，必须先把 `tradeTime` 转换为 UTC naive datetime，再与数据库中的 `orders_ds.time_create` / `orders_df.time_accept` 比较。

## 头脑风暴结论

1. 不改 MySQL、Pod、宿主机或 Redis 时区，避免影响订单状态机、锁和 TTL。
2. 不把数据库时间转成巴基斯坦时间后再比较，避免在 SQL 结果和 Python 侧产生两个时间口径。
3. 采用单点边界转换：账单 worker 解析上游 `tradeTime` 时按 `APP_DISPLAY_TIMEZONE`，默认 `Asia/Karachi`，转换为 UTC 后进入既有窗口判断。

## 验收标准

- [x] 代收订单 `time_create=2026-05-08 07:00:00 UTC`，上游 `tradeTime=2026-05-08 12:03:00 Pakistan` 能匹配并回调。
- [x] 同一订单下，上游 `tradeTime=2026-05-08 12:09:00 Pakistan` 超出 8 分钟窗口，不回调。
- [x] 代付订单 `time_accept=2026-05-08 07:00:00 UTC`，上游 `tradeTime=2026-05-08T12:03:00 Pakistan` 能进入观测匹配且不触发代收回调。
- [x] 缺失或不可解析时间仍不匹配。
- [x] 数据库 UTC 存储、应用层巴基斯坦展示时区策略不变。
