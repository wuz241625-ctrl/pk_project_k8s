# JazzCashBusiness 采集端唯一真相源设计

## 背景

复查 JazzCashBusiness 三个脚本后，确认派单入口已经逐步收口到 `jazzcash_runtime`，但采集端 `api/jobs/Jazzcashpay_v2.py` 仍存在两个绕过点：

- `hash_jazzcash` / `set_jazzcash` 仍可驱动 worker 直接采集。
- `pre_login_jazzcash_*` 激活成功后仍直接写旧 job 队列。

用户确认 JazzCashBusiness 的代付不能脱离采集能力：上游代付接口可能返回异常或不可信状态，系统需要继续采集账单进行最终对账。因此 JCB 的业务不采用“可代付但不可采集”模型。

## 头脑风暴方案

### 方案 A：只在 worker 入口检查 runtime

优点是改动最小。缺点是 `pre_login` 和 `update_key()` 仍直接维护旧 job 队列，旧队列仍像主状态，后续容易再次漂移。

### 方案 B：把采集 job 写入统一放进 `SyncJazzCashRuntimeService`

优点是采集端所有 job 写入都经过同一个 runtime 服务，`hash_jazzcash` / `set_jazzcash` 明确降级为 runtime 派生投影。缺点是需要补同步 runtime 服务方法和 worker 测试。

### 方案 C：重构三个 JCB 脚本共享完整策略层

优点是一次性统一采集、健康检查、代付。缺点是影响面大，当前需求只要求采集端，容易把风险扩大。

## 采用方案

采用方案 B。采集端先闭环，不重构健康检查和代付脚本。

## 状态模型

- `online=true` 且 `collect_enabled=true`：允许采集账单。
- `ds_order_enabled=true`：允许代收派单。
- `df_order_enabled=true`：允许代付派单。
- JCB 约束：`collect_enabled=false` 时，`ds_order_enabled` 和 `df_order_enabled` 必须同时为 `false`。
- DB `payment.status != 1` 或 `certified != 1` 时，保留采集，但关闭代收/代付派单，用于后续对账。
- DB 查不到账号时，视为 offline，清理采集 job。

## 改动范围

- `api/application/jazzcash_runtime/sync_runtime_service.py`
  - 增加 `is_collection_online()`。
  - 增加 `sync_collection_job_state()`，统一写 runtime snapshot、runtime index、legacy bridge、`hash_jazzcash`、`set_jazzcash`。
- `api/jobs/Jazzcashpay_v2.py`
  - 增加 payment DB 策略读取。
  - `on_off(1)` 按 DB 策略写 runtime，不再无条件开启 DS/DF。
  - `update_key()` 改走 `sync_collection_job_state()`。
  - `process_single_member_async()` 采集前先检查 runtime，runtime 禁采时清理旧 job 并跳过。
  - `pre_login` 激活成功推进采集时改走 runtime 服务，不再直接写旧队列。
  - 旧 `login_off_jazzcash_*` 标记不再作为主真相源强制下线，只清理标记并继续按 runtime 策略处理。

## 验收标准

- `sync_collection_job_state()` 能写入 JCB runtime snapshot、采集索引、legacy bridge、`hash_jazzcash`、`set_jazzcash`。
- 当 `collect_enabled=false` 时，JCB runtime 必须同时关闭 DS/DF，并清理采集 job。
- worker 遇到 runtime 已禁采的旧 `hash_jazzcash` / `set_jazzcash` 残留时，不调用上游账单采集。
- `pre_login_jazzcash_*` 的 `activeSuccessful` 推进必须通过 runtime 写入 job 队列。
- JCB `payment.status/certified` 非接单状态时，保留采集但关闭 DS/DF。
- JCB 相关单测、语法编译、`git diff --check` 全部通过。
