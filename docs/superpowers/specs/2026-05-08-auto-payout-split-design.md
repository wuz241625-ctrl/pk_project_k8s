# auto_payout.py 模块拆分设计

## 背景

`auto_payout.py` 经过公共层提取后仍有 5206 行，是典型的 God Class 反模式。70+ 方法混合了选号、转账、结算、日志、冷却期等不同关注点。需要拆分为纯编排器 + 5 个聚焦模块。

## 设计目标

1. `auto_payout.py` 变为纯编排器（~200-300 行）：只含 main loop、init、dispatch
2. 业务逻辑拆入 5 个模块，每个模块单一职责、不超过 700 行
3. 删除 `_create_response_wrapper` 及相关 HTTP 兼容层（已有 common.easypaisa_api）
4. 消除重复代码（如两份 `_is_pakistan_mobile_number`）
5. 零行为变更：错误处理语义不变（500≠驳回，501=下线）

## 目标结构

```
jobs/easypaisa/
├── auto_payout.py              ← 纯编排器 (~250行)
├── payout/
│   ├── __init__.py
│   ├── account_selector.py     ← 选号 + 限额 + 余额查询 (~550行)
│   ├── transfer_executor.py    ← 转账API调用 + 结果解析 (~550行)
│   ├── order_lifecycle.py      ← 订单编排 + 冷却期 (~450行)
│   ├── settlement.py           ← 财务结算 (~350行)
│   └── transaction_log.py      ← 交易日志 + 操作日志 (~420行)
```

## 模块职责

### auto_payout.py — 纯编排器

| 方法 | 职责 |
|------|------|
| `main()` | 主循环：获取待处理订单 → 分发处理 → sleep |
| `init_function()` / `init_function_v2()` | 初始化 DB、Redis、API、Logger，构造各模块实例 |
| emergency stop check | 读 `easypaisa_emergency_stop` 决定是否暂停 |
| process sharding | 基于 PID 的一致性哈希分片 |

不含任何业务逻辑。所有订单处理委托给 `OrderLifecycle`。

### payout/account_selector.py — 选号

| 方法 | 职责 |
|------|------|
| `get_real_available_accounts()` | 批量预筛可用账号（含全部防护检查） |
| `dispatch_orders_to_accounts()` | 按余额降序虚拟扣减分配订单到账号 |
| `check_account_amount_limits()` | 单笔/日限额检查 |
| `fetch_balance_from_api()` | 实时余额查询 |
| `acquire_account_lock()` / `release_account_lock()` | 账号锁管理 |
| `_is_pakistan_mobile_number()` | 手机号格式校验（唯一副本） |
| `filter_accounts_by_balance()` | 最低余额过滤 |

接口：
```python
class AccountSelector:
    def __init__(self, db, redis_client, api, logger): ...
    async def select_and_lock_account(self, order) -> tuple[dict, str] | None
    async def release_account(self, account_id, lock_value): ...
    def check_limits(self, account, amount) -> bool
```

### payout/transfer_executor.py — 转账执行

| 方法 | 职责 |
|------|------|
| `execute_transfer()` | 完整转账流程：前余额 → API调用 → 后余额 → 状态码路由 |
| `_extract_transaction_id()` | 从多种响应格式解析 transaction_id |
| `check_duplicate_failure()` | 重复失败检测 |
| `handle_501()` | 账号无效 → wallet_status=0 |

接口：
```python
@dataclass
class TransferResult:
    status: str  # success / rejected / unknown / error
    transaction_id: str | None
    balance_before: Decimal | None
    balance_after: Decimal | None
    error_code: int | None
    raw_response: dict | None

class TransferExecutor:
    def __init__(self, db, redis_client, api, logger): ...
    async def execute_transfer(self, order, account) -> TransferResult
    async def handle_501(self, account): ...
```

错误码语义（不变）：
- 200 → status=success
- 402 → status=rejected（安全驳回）
- 500 → status=unknown（**不能自动驳回，钱可能已扣**）
- 501 → status=error + 立即调 handle_501

### payout/order_lifecycle.py — 订单编排

| 方法 | 职责 |
|------|------|
| `process_single_order_async()` | 完整订单生命周期：校验 → 选号 → 锁 → 风控 → 转账 → 结算 |
| `process_payout_order()` | 订单处理入口 |
| `is_order_in_cooldown()` | 冷却期检查 |
| `set_order_cooldown()` | 设置冷却期（指数退避） |
| `calculate_cooldown_minutes()` | 计算冷却时长 |
| `mark_order_cooldown_success()` | 成功后清除冷却 |
| `filter_cooldown_orders()` | 过滤冷却中的订单 |
| order lock | `payment_id_lock` 管理 |

接口：
```python
class OrderLifecycle:
    def __init__(self, db, redis_client, account_selector, transfer_executor,
                 settlement, tx_logger, logger): ...
    async def process_order(self, order) -> None
    def filter_cooldown_orders(self, orders) -> list
```

### payout/settlement.py — 财务结算

| 方法 | 职责 |
|------|------|
| `handle_payout_success()` | 更新订单状态 + 扣减余额 + 记录流水 |
| `handle_payout_rejection()` | 驳回订单 + 退回商户余额 |
| `change_balance()` | 余额变动 + 账本记录（带幂等保护） |

接口：
```python
class Settlement:
    def __init__(self, db, redis_client, logger): ...
    async def settle_success(self, order, account, transfer_result: TransferResult): ...
    async def settle_rejection(self, order, account, reason: str): ...
    async def adjust_balance(self, account_id, amount, direction, order_code): ...
```

### payout/transaction_log.py — 交易日志

| 方法 | 职责 |
|------|------|
| `log_complete_transaction()` | 详细 JSON 交易日志（前后状态、耗时、API响应） |
| `log_operation()` | 操作级日志（审计用） |
| formatting helpers | 日志条目格式化 |

接口：
```python
class TransactionLogger:
    def __init__(self, logger, db): ...
    def log_transaction(self, order, account, result: TransferResult, timing: dict): ...
    def log_operation(self, op_type: str, details: dict): ...
```

## 依赖图

```
auto_payout.py (编排器)
    │
    └── OrderLifecycle
            ├── AccountSelector
            ├── TransferExecutor
            ├── Settlement
            └── TransactionLogger
            
所有模块共享: easypaisa.common (DB, Redis, API, Logger)
```

单向依赖，无循环。

## 删除清单

| 代码 | 原因 |
|------|------|
| `_create_response_wrapper()` | common.easypaisa_api 已封装 HTTP |
| `make_request()` / `retry_make_request()` | 同上 |
| `async_session_context()` | 同上 |
| 重复的 `_is_pakistan_mobile_number()` | 保留 account_selector 中的唯一副本 |
| `hash_key` / `set_key` / `list_key` 残留引用 | 旧投影已退役 |

## 验收标准

### 结构验收

- [ ] `auto_payout.py` ≤ 300 行，只含编排逻辑
- [ ] `payout/` 目录包含 5 个模块 + `__init__.py`
- [ ] 每个模块 ≤ 700 行
- [ ] 无跨模块重复函数
- [ ] `_create_response_wrapper` 及相关 HTTP 兼容代码已删除
- [ ] 依赖图单向，无循环 import

### 行为验收

- [ ] Worker 正常启动（import 无报错）
- [ ] 订单处理流程不变：选号 → 锁 → 转账 → 结算
- [ ] 错误码处理语义不变：200=成功, 402=驳回, 500=不驳回, 501=下线
- [ ] 501 → `wallet_status=0`（强约束）
- [ ] 冷却期逻辑不变（指数退避）
- [ ] 紧急停机 `easypaisa_emergency_stop` 正常工作
- [ ] 分布式锁行为不变（账号锁 + 订单锁）
- [ ] 现有单元测试全部通过

### 清理验收

- [ ] 无 `_create_response_wrapper` 残留
- [ ] 无重复 `_is_pakistan_mobile_number`
- [ ] 无 `hash_key` / `set_key` / `list_key` 残留
- [ ] 无 `local_mock` 残留
