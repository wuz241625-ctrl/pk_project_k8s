# JazzCashBusiness 唯一真相源补漏设计

## 背景

上一轮已经把 JazzCashBusiness 主链路接入 `jazzcash_runtime:snapshot:{payment_id}` 和 `jazzcash_runtime:index:*`。复查后仍发现 4 个绕过点：websocket monitor 仍把 `bank_type=98` 当普通非 EP 写 legacy，`time_out.py` 只检查 EasyPaisa runtime，admin 代付确认/驳回回队只接了 EasyPaisa reader，`pay.py` 回队时仍会被 legacy `kick_off_{payment_id}` 脏 key 二次拦截。

## 目标

JazzCashBusiness 的在线、代收派单、代付派单、回队、手动上下线都只能以 `jazzcash_runtime` 为主真相源。legacy Redis key 只保留为派生投影或非 runtime 银行的旧兼容路径。

## 方案选择

采用“在现有入口按银行分流”的小步收口方案：

- `bank_type/bank_type_id=97` 继续走 EasyPaisa runtime。
- `bank_type/bank_type_id=98` 走 JazzCash runtime。
- 其他银行保持 legacy。

不做大重构，不把所有银行一次性迁入 runtime，避免影响 PhonePe/Jio/Maha 等旧链路。

## 改动范围

- `api/application/websocket/monitor.py`：新增 JazzCash 判断，ds/df 上下线改走 `JazzCashRuntimeService`。
- `api/application/jazzcash_runtime/runtime_service.py`：补 `set_df_order_dispatch()`，供 websocket df 控制使用。
- `api/jobs/time_out.py`：`TimeOutGuard` 对 `bank_type=98` 检查 `jazzcash_runtime:index:dispatch_ds`。
- `admin/application/order/order.py`：admin 代付确认/驳回后的回队对 JazzCash 改读 `JazzCashAdminRuntimeReader`。
- `api/application/pay/pay.py`：代收回队判断 runtime 银行时只看 runtime kickoff key，不再受 legacy `kick_off_*` 脏 key 影响。
- 测试补齐上述行为，并修复旧 JazzCash v2 测试 FakeRedis 缺少 runtime index 方法的问题。

## 验收标准

- websocket monitor 对 JazzCash ds/df 上下线不会直接写 `payment_online_*` 作为主动作，而是调用 `JazzCashRuntimeService`。
- `time_out.py` 中 JazzCash 缺少 `jazzcash_runtime:index:dispatch_ds` 时不会回队。
- admin 代付确认/驳回对 JazzCash snapshot 缺失时不会信任 `payment_online_df`，snapshot df 可用时会回队。
- `pay.py` 中 JazzCash runtime 在线但只有 legacy `kick_off_*` 脏 key 时仍可按 runtime 继续回队；有 `jazzcash_runtime:kickoff:*` 时才跳过。
- 相关 API/admin 单测、语法编译、`git diff --check` 全部通过。
