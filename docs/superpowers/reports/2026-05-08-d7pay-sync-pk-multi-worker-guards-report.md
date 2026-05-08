# D7pay 同步 PK 多 Worker 防护报告

## 背景

本次同步 `/Users/tear/pk_project` 最新业务改动到 `pk_project_k8s` 的 `d7pay` 分支，目标是让 D7pay 跟上 PK 项目的 EasyPaisa 多 worker 防护、代收订单匹配、回调幂等和数据库索引改动。

## 同步范围

- `api/application/pay/dispatch.py`
  - 锁后重新校验钱包、代收、人工锁定、认证、账号字段。
  - EasyPaisa 代收通道按 `account_type` 区分手机号和账号字段。
  - 同时接单上限改为达到上限即拒绝。
- `api/application/pay/order.py`
  - Redis 锁统一改为 `SET NX EX` 原子写入，避免 `setnx` 成功但 `expire` 失败形成无 TTL 锁。
- `api/application/websocket/callback.py`
  - 代收成功匹配只允许 `status=2` 的待确认订单，并在事务内 `FOR UPDATE` 锁定。
- `api/jobs/easypaisa/common/redis_client.py`
  - worker 锁改为原子 `SET NX EX`，并清理无 TTL 异常锁。
- `api/jobs/pakistanpay_v2.py`
  - EasyPaisa 账单扫描并发数改为配置项 `easypaisa_statement_concurrent_limit`，默认 3。
  - CREDIT 流水必须匹配 `status=2` 待确认订单的金额和付款手机号后才回调。
  - EasyPaisa 流水引用优先使用官方 `extOrderNo`，避免把本地 `orderNo` 当成真实流水号。
- `api/sql/20260508_add_orders_ds_phone_match_index.sql`
  - 新增代收按钱包、付款手机号、金额、状态、时间匹配的复合索引脚本。
- `api/migrations/20260508170000_add_orders_ds_merchant_code_unique/migration.sql`
  - 新增 `orders_ds(merchant_id, merchant_code)` 唯一索引迁移脚本，重复数据存在时跳过。
- `api/migrations/20240327134145_initial/migration.sql`
  - 初始化 schema 同步唯一索引定义。
- 测试同步：
  - `api/tests/test_easypaisa_multi_worker_guards.py`
  - `api/tests/test_statement_callback_mysql_idempotency.py`

## 未同步范围

- 未同步 `api/sql/runtime_init_from_remote_config.sql`。
- 原因：D7pay 当前方向是不重新引入 runtime 旧兼容初始化脚本，避免把已清理的 runtime 残留带回来。

## 验收标准

- 目标业务文件与 `/Users/tear/pk_project` 对应文件一致。
- D7pay 租户配置、域名、部署脚本不被 PK 配置覆盖。
- 多 worker 防护相关测试通过。
- GitNexus 变更检查只覆盖预期的派单、回调、账单扫描和 Redis 锁路径。

## 验收结果

- 已确认同步文件不包含 D7pay 域名、租户常量或部署配置覆盖。
- 已保留 D7pay 不引入 runtime 初始化脚本的方向。
- `python3 -m py_compile api/application/pay/dispatch.py api/application/pay/order.py api/application/websocket/callback.py api/jobs/easypaisa/common/redis_client.py api/jobs/pakistanpay_v2.py api/tests/test_easypaisa_multi_worker_guards.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py` 通过。
- `python3 -m pytest api/tests/test_easypaisa_multi_worker_guards.py api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_ds_dispatch_candidate_sql.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py -q` 通过：40 passed。
- `python3 -m pytest api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py -q` 通过：86 passed。
- 合并执行上述受影响测试通过：127 passed。
- GitNexus detect changes 风险为 high，原因是命中 `push_order` 和 `grabstatement` 核心支付流程； affected processes 符合本次同步预期。
