# EasyPaisa MySQL 资格源切换设计

日期：2026-05-07

## 背景

当前 EasyPaisa 已引入 `payment.wallet_status`、`payment.collection_status`、`payment.payout_status`，但运行中仍有 Redis runtime、legacy Redis 队列、采集 hash/zset、余额 zset、monitor 恢复逻辑参与判断。多套状态同时存在时，会出现关闭后仍接单、Redis 丢失后断派、501 下线后被补回、代付未知状态重复出款等资金风险。

本设计冻结一条原则：EasyPaisa 最终资格只读 MySQL，Redis 只能做临时态、锁、节流、可重建投影，不再做最终裁判。

## 目标

1. 上号、采集、代收、代付、monitor 的状态语义统一。
2. MySQL `payment` 成为 EasyPaisa 资格唯一真相源。
3. Redis 保留为临时运行辅助，但不决定账号是否可采集、可代收、可代付。
4. 先修 P0 资金风险，再逐步清理 legacy Redis 依赖。
5. 所有改动先在 `tc160` Docker 环境验证，不直接上线生产。

## 非目标

1. 本阶段不重构 JazzCash 或其他钱包。
2. 本阶段不一次性删除所有 Redis key。
3. 本阶段不新增复杂 runtime 表。
4. 本阶段不做 UI 重设计。

## 状态分层

| 层级 | 字段或介质 | 写入方 | 含义 |
|---|---|---|---|
| 钱包状态 | `payment.wallet_status` | worker/API 上号完成点/硬下线入口 | 钱包 API 当前是否可用 |
| 选中账号 | `payment.account_accno/account_iban/account_entire` | 上号 API、账号选择 API | 当前用于采集和转账的 EasyPaisa 子账号 |
| 代收业务状态 | `payment.collection_status` | API/Admin 用户或运营动作 | 是否允许代收派新单 |
| 代付业务状态 | `payment.payout_status` | API/Admin 用户或运营动作 | 是否允许代付派新单 |
| 历史兼容 | `status/certified/manual_status` | API/Admin 兼容层 | 历史启用、认证、人工锁定语义 |
| 临时运行态 | Redis | 各 worker | 锁、OTP、冷却、节流、临时暂停、可重建投影 |

硬边界：

- `wallet_status` 不能表示运营启用、禁用、人工锁定。
- `collection_status` 和 `payout_status` 不能表示钱包是否登录成功。
- Redis 不能作为 EasyPaisa 最终 eligibility 来源。
- monitor 不能恢复业务资格，不能把 Redis 状态反向覆盖 MySQL。

## 最终资格公式

### 上号成功

选择账号成功后必须写：

```text
wallet_status = 1
collection_status = 1
payout_status = 1
account_accno = selected accno
account_iban = selected IBAN
account_entire = upstream account list
```

原因：用户已确认上号成功后自动开启代收和代付业务。

### 采集账单

```text
wallet_status = 1
```

采集账单不看 `collection_status` 和 `payout_status`。`wallet_status=1` 已经包含“上号成功且选中账号”的语义；`account_accno` 是账号资料字段，不再作为资格条件重复判断。

### 代收派单

```text
collection_status = 1
AND channel 匹配
```

`collection_status` 是代收派单最终态，已经包含钱包、用户、人工、健康等结果；读面不得再拆开判断。

### 代付派单

```text
payout_status = 1
```

`payout_status` 是代付派单最终态，已经包含钱包、用户、健康等结果；读面不得再拆开判断。

### 健康暂停

423、5xx、网络抖动、上游超时：

```text
不修改 wallet_status
不清 account_accno
如需暂停派单，写 collection_status = 0
如需暂停派单，写 payout_status = 0
健康恢复后按 MySQL 配置重算 collection_status/payout_status
采集可继续重试或降频
```

501、session invalid、force logout、硬下线：

```text
wallet_status = 0
collection_status = 0
payout_status = 0
清理临时运行投影
```

## Redis 边界

### 允许保留

- OTP、短信验证码、pre_login 临时数据。
- 短 TTL 锁，例如单订单锁、单账号锁。
- 冷却和节流，例如 `send_orders_interval_*`。`crawl_frequently_*` 已退役，不能再作为账单调度信号。
- 3 分钟健康暂停标记只能作为观测/节流，不能作为派单读面的最终裁判。
- 可从 MySQL 重建的采集队列或余额排序缓存。

### 禁止作为最终裁判

- `payment_online_ds`
- `payment_online_df`
- `payment_active_{channel}`
- `payment_active_df`
- `easypaisa_runtime:snapshot:*`
- `easypaisa_runtime:index:*`
- `hash_easypaisa`
- `set_easypaisa`
- `hash_ep_monitor`
- `set_ep_monitor`
- `easypaisa_balance_sorted`
- `if_callback_easypaisa` 作为唯一幂等源

## 组件职责

### API 上号

- 负责上号、选择账号、写 `account_accno/account_iban/account_entire`。
- 上号成功点必须原子写 `wallet_status=1/collection_status=1/payout_status=1`。
- force logout 必须写 `wallet_status/collection_status/payout_status=0`，不能只写旧 `status/certified`。

### 代收 API

- 使用统一 MySQL eligibility 方法。
- EasyPaisa 候选 SQL 必须返回 eligibility 所需字段。
- 最终绑定 `orders_ds.payment_id` 时必须在同一事务或同一 SQL 中再次复核 eligibility。
- 当前线上只有 EasyPaisa，Redis active list 不再作为新资格链路的兼容候选来源。

### 代付 worker

- 订单来源仍是 MySQL `orders_df status=0`。
- 账号候选必须从 MySQL eligibility 查询开始。
- `easypaisa_balance_sorted` 只能排序，不能成为唯一候选源。
- 423、5xx、网络超时、解析失败、未知响应进入待确认，不自动重试出款。
- 明确成功后先进入待结算，账务事务成功后才最终成功和通知。

### 采集 worker

- 可短期保留 `hash_easypaisa/set_easypaisa` 作为可丢弃队列。
- 队列必须从 MySQL `wallet_status=1` 重建；`wallet_status=1` 已经包含选中账号成功的语义。
- Redis 旧账号不得覆盖 MySQL 关闭状态。
- Redis 丢失只影响调度间隔，不能影响“哪些账号应该可采集”。

### Monitor

- 只做健康检查、余额/限额观察、告警；如果要暂停派单，必须写 MySQL 最终 `collection_status/payout_status=0`。
- 不允许恢复 `hash_easypaisa/set_easypaisa` 作为业务动作。
- 不允许绕过最终态读面恢复 Redis 状态。
- 501 必须走统一硬下线入口写 `wallet_status/collection_status/payout_status=0`。

### Admin

- 业务启用：`collection_status=1/payout_status=1`，不改 `wallet_status`。
- 业务禁用：`collection_status=0/payout_status=0`，不改 `wallet_status`，不登出。
- 人工锁定：`collection_status=0`，`payout_status` 保持。
- 人工解锁：`collection_status=1`，`payout_status` 保持。
- 重置：清账号字段，并同步 `wallet_status/collection_status/payout_status=0`，避免展示短暂偏移。

## 错误策略

| 场景 | 钱包状态 | 业务状态 | 派单 | 采集 | 备注 |
|---|---|---|---|---|---|
| 上号成功 | `wallet_status=1` | DS/DF 都开启 | 允许 | 允许 | 自动开启 |
| 后台禁用 | 不变 | DS/DF 都关闭 | 禁止 | 允许 | 不登出 |
| 人工锁定 | 不变 | DS 关闭，DF 保持 | 禁止代收，允许代付 | 允许 | 已确认 |
| 501/session invalid | `wallet_status=0` | DS/DF 都关闭 | 禁止 | 禁止 | 硬下线 |
| 423/5xx/网络抖动 | 不变 | DS/DF 视暂停需要写 0，健康恢复后重算 | 暂停期间禁止 | 允许重试 | 不自动出款重试 |
| 重置 | `wallet_status=0` | DS/DF 都关闭 | 禁止 | 禁止 | 清账号 |

## 验收标准

1. 上号选择账号成功后，MySQL 中 `wallet_status/collection_status/payout_status` 全为 `1`，且账号字段完整。
2. `wallet_status=0` 时最终 `collection_status/payout_status` 同步为 0，不会被代收、代付、采集选中。
3. `collection_status=0` 的账号不会代收，但仍可采集。
4. `payout_status=0` 的账号不会代付，但仍可采集。
5. `manual_status=1` 的账号不会代收，但可代付。
6. 423/5xx/网络抖动如需暂停派单，必须写最终 `collection_status/payout_status`，不能只靠 Redis 临时态。
7. 501/session invalid/force logout 后 `wallet_status/collection_status/payout_status=0`，不会被 monitor 或 worker 自动补回。
8. 代收最终绑定订单时，账号在绑定瞬间仍必须满足 MySQL eligibility。
9. 代付未知状态不会自动重试出款，只进入待确认。
10. Redis 清空后，MySQL 可重建采集候选；Redis 旧值不能恢复已关闭账号。
11. EasyPaisa 最终资格不依赖 runtime snapshot/index、legacy online set/list、active list、余额 zset。
12. tc160 上专项单测、SQL 验证、日志扫错全部通过后才允许进入生产上线计划。

## 回滚原则

- 任何阶段发现代付未知状态、重复出款风险、代收误派风险，立即回滚该阶段代码。
- Redis 降权阶段不删除历史 key，只停止 EasyPaisa 读取其裁判权，降低回滚成本。
- 回滚后仍保留 MySQL 状态字段，不做 destructive migration。
