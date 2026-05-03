# EasyPaisa 分层真相源边界设计

## 背景

EasyPaisa 已有 runtime session、snapshot/index、worker job 投影和 legacy bridge，但仍存在一个边界风险：Pakistanpay worker 的调试读取会直接查看 `login_on_easypaisa_*`、`payment_online_*`、`payment_active_*`、`kick_off_*` 等 legacy 投影。即使只是日志，这也会让排障和后续改动继续把下游投影当成可读取事实。

本次目标是把现有口径固化为可验收规则：

- SQL 是配置唯一源：`payment.status`、`certified`、`manual_status`、`channel` 等配置只能从 SQL 读取。
- `easypaisa_runtime:session:{payment_id}` 是 EasyPaisa 登录真相源。
- `easypaisa_runtime:snapshot:{payment_id}` 与 `easypaisa_runtime:index:*` 是 EasyPaisa 运行调度真相源。
- `hash_easypaisa` / `set_easypaisa` 是 runtime 给 Pakistanpay worker 的采集任务投影。
- legacy key 只是 runtime bridge 生成的旧系统兼容投影，不能再作为 EasyPaisa 主事实或调试事实。

## 方案比较

### 方案 A：只补文档

成本最低，但代码仍允许 worker 读取 legacy 投影，后续排障会继续依赖旧 key，不满足“任何进程不得跨层读写下游状态”。

### 方案 B：小范围代码收口 + 静态/单元验收

保留现有 runtime service 和 worker 主流程，只移除 Pakistanpay `read_cache()` 对 EasyPaisa legacy 投影的读取；新增测试防止回退；把 admin raw `hash_easypaisa` / `set_easypaisa` 清理改为 keyspace 常量。该方案改动小，覆盖当前明确风险，推荐采用。

### 方案 C：彻底移除 worker 扫描 `pre_login_easypaisa_*`

边界更纯粹，但会牵涉登录链、activeSuccessful 推进、worker 启动路径和上线操作窗口，超出本次“跨层读写下游状态”收口范围。本次不做，后续可单独设计。

## 设计

采用方案 B。

1. Pakistanpay worker 仍可读取自己的任务投影：`self.hash_key` / `self.set_key`，以及 worker 私有锁和设备缓存。
2. Pakistanpay worker 的 `read_cache()` 不再读取或记录 EasyPaisa legacy bridge 投影：
   - `login_on_easypaisa_*`
   - `payment_online_ds`
   - `payment_online_df`
   - `payment_active_{channel}`
   - `kick_off_{payment_id}`
3. runtime service 仍是写入 snapshot/index、job 投影和 legacy bridge 的唯一入口；worker 需要调整运行态时调用 runtime service，不直接操作 legacy。
4. admin runtime reset 使用 `keyspace.JOB_HASH` / `keyspace.JOB_SET` 常量，不再在 service 内散落 raw job key。
5. 文档同步声明分层边界，并给出验收命令。

## 验收标准

- 新增测试证明 `BankLogin.read_cache()` 只读取 worker 投影和 worker 私有缓存；一旦重新读取 EasyPaisa legacy 投影，测试失败。
- 新增静态边界测试证明生产代码中的 `hash_easypaisa` / `set_easypaisa` raw 字符串只保留在 EasyPaisa runtime keyspace 常量定义中。
- 既有 EasyPaisa runtime service、reader、order_push guard、business flow 相关测试通过。
- `api/build.md`、`api/README.md`、根 `err.md` 或对应排错文档记录本次边界和验证方式。
- 验收通过后提交并推送当前分支。

## 自检

- 无 TBD/TODO。
- 本次只收口 EasyPaisa 已明确的下游投影读取风险，不改变 SQL 配置字段语义。
- 方案不触碰 UI，不需要 Gemini 协作。
