# JazzCashBusiness 唯一真相源设计

## 背景

JazzCashBusiness 当前上号流程已经调整为 `sendOtp -> verifyOtp -> uploadFingerprint -> verifyFingerprint -> activeSuccessful`，其中 `verifyOtp` 只推进本地状态，真正上游指纹验证在 `loginStep2` 中完成。运行态仍直接写 `payment_online_ds`、`payment_online_df`、`payment_active_{channel}` 等 legacy Redis 键，admin 展示和 API 派单也会读取这些键，因此脏队列会被误当作真实在线状态。

## 目标

为 JazzCashBusiness 建立与 EasyPaisa 同级的 runtime 唯一真相源：

- `jazzcash_runtime:snapshot:{payment_id}` 记录账号运行态、采集态、代收派单、代付派单和渠道。
- `jazzcash_runtime:index:*` 维护在线、采集、代收派单、代付派单索引。
- `payment_online_ds`、`payment_online_df`、`payment_active_{channel}`、`login_on_jazzcash_*`、`hash_jazzcash`、`set_jazzcash` 只作为兼容旧派单/job 的派生投影。
- API 和 admin 判断 JazzCashBusiness 在线、代收、代付时先读 runtime；runtime 开启且无 snapshot 时不信任 legacy。

## 方案对比

### 方案 A：直接复用 EasyPaisa runtime

优点是代码量少；缺点是 bank id、key 前缀、job hash/set、登录锁语义会混在一起，排障时容易把 EasyPaisa 和 JazzCash 的状态互相污染。

### 方案 B：建立 JazzCash 独立 runtime，接口语义对齐 EasyPaisa

优点是边界清晰，后续可以单独清理 JazzCash 残留状态；缺点是需要在 API 与 admin 各放一套轻量 helper。推荐使用该方案。

### 方案 C：只修 admin/API 读取逻辑，继续让 jobs 直写 legacy

优点是改动小；缺点是写入端仍然多源，不能满足“唯一真相源”。

## 采用设计

采用方案 B。

API 侧新增 `application/jazzcash_runtime`：

- `keyspace.py`：定义 snapshot、session、index、legacy key 和 channel 规范化。
- `flags.py`：支持 `JAZZCASH_RUNTIME_READ_ENABLED`、`JAZZCASH_RUNTIME_WRITE_ENABLED`，默认开启。
- `runtime_service.py`：异步服务，负责登录链、API 开关、force offline/reset 的主状态写入与 legacy bridge 投影。
- `sync_runtime_service.py`：同步服务，供 `Jazzcashpay_v2.py`、`jobs/jazzcash/*` 使用。
- `reader.py`：API 派单、app/my、UPI controller 读取 JazzCash runtime。

Admin 侧新增 `application/jazzcash_runtime`：

- `reader.py`：列表展示、筛选和计数读取 runtime。
- `service.py`：admin 手动开关、重置写 runtime，并同步清理派生 legacy。
- `keyspace.py`、`flags.py`：与 API 保持 key 语义一致。

## 数据流

上号成功：

```text
JazzCash verify_fingerprint/loginStep2 成功
-> runtime_service.mark_active_successful(payment_id)
-> 写 jazzcash_runtime:snapshot:{payment_id}
-> 写 jazzcash_runtime:index:online / dispatch_ds / dispatch_df
-> legacy bridge 投影到 payment_online_ds / payment_online_df / payment_active_{channel}
```

代收派单：

```text
orders_ds 下单
-> payment_active_{channel} 提供旧派单候选
-> JazzCashRuntimeReader 校验 dispatch_ds
-> runtime 为 false 或 snapshot 缺失时拒绝派单
```

代付：

```text
orders_df 下单或自动代付 job
-> JazzCashRuntimeReader / SyncJazzCashRuntimeService 判断 dispatch_df
-> legacy payment_online_df/payment_active_df 只作为兼容队列
```

Admin 操作：

```text
列表展示/筛选 -> JazzCashAdminRuntimeReader
手动下线/禁用接单/重置 -> JazzCashAdminRuntimeService
```

## 验收标准

- API：JazzCash snapshot `dispatch_ds=false` 时，即使 `payment_online_ds` 和 `payment_active_{channel}` 残留，也不能代收派单。
- API：JazzCash snapshot `dispatch_df=false` 时，即使 `payment_online_df` 残留，`place_order_status` 和 app 展示也必须为离线。
- API：JazzCash 上号成功只通过 runtime service 写主状态，legacy 队列由 service 投影。
- Admin：JazzCash 列表在线态、代收态、代付态来自 `jazzcash_runtime:snapshot:*`。
- Admin：JazzCash 重置会清 `jazzcash_runtime:session:*`、runtime index、legacy 队列、`login_on_jazzcash_*`、`hash_jazzcash`、`set_jazzcash`。
- 文档：`api/build.md`、`api/err.md`、`admin/build.md`、`admin/err.md` 记录 JazzCash runtime 验证和排错入口。
