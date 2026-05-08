# Payout Idempotency Final State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 JazzCash 代付状态机和账单采集 Redis 去重残留，使核心链路符合 MySQL 唯一真相源原则。

**Architecture:** JazzCash 代付由 `orders_df` 状态机驱动，成功态只在 settlement 中从 `status=1` 推进到 `status=3`。账单 worker 每轮尝试回调，由内部 MySQL 订单/流水幂等判断重复。

**Tech Stack:** Python、PyMySQL、unittest、Redis 短锁/缓存、MySQL 业务最终态。

---

### Task 1: 固定 JazzCash 代付状态机测试

**Files:**
- Create: `api/tests/test_jazzcash_payout_state_machine.py`

- [x] **Step 1: 写失败测试**

测试断言：

```python
self.assertNotIn("WHERE code = %s AND status IN (0, 1)", lifecycle)
self.assertIn("WHERE code=%s AND status=1", settlement)
self.assertIn("error_code == 402", lifecycle)
self.assertIn("new_retry_count >= 3", lifecycle)
self.assertNotIn("reject_msg_codes", transfer_executor)
```

- [x] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_jazzcash_payout_state_machine -v
```

Expected: FAIL，命中 JazzCash 提前写成功态、402 特定 msgCd 分叉、8 次重试旧逻辑。

### Task 2: 固定采集 MySQL 幂等测试

**Files:**
- Create: `api/tests/test_statement_callback_mysql_idempotency.py`

- [x] **Step 1: 写失败测试**

测试断言：

```python
self.assertNotIn("zscore(self.if_callback_key", source)
self.assertNotIn("mark_transaction_callback(", source)
self.assertNotIn("clean_if_callback_key()", source)
self.assertIn("callback=0 and trade_type=1", utr_callback)
self.assertIn("success_busy_{trans_id}", order_callback)
```

- [x] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_statement_callback_mysql_idempotency -v
```

Expected: FAIL，命中 EasyPaisa/JazzCash worker 的 Redis 回调标记。

### Task 3: 修复 JazzCash 代付状态机

**Files:**
- Modify: `api/jobs/jazzcash/payout/order_lifecycle.py`
- Modify: `api/jobs/jazzcash/payout/settlement.py`
- Modify: `api/jobs/jazzcash/payout/transfer_executor.py`
- Modify: `api/tests/test_jazzcash_auto_payout_v16.py`

- [x] **Step 1: 抢单时绑定出款账号**

`orders_df` 只允许从 `status=0` 原子更新到 `status=1`，同时写入 `payment_id/partner_id`。

- [x] **Step 2: 移除提前成功态**

删除 `order_lifecycle.py` 中转账成功后直接 `status IN (0,1) -> 3` 的 SQL。

- [x] **Step 3: 成功结算加状态守卫**

`settlement.handle_payout_success()` 更新为：

```sql
UPDATE orders_df
SET earn_merchant=%s,
    status=3,
    time_payed=NOW(),
    time_success=NOW(),
    utr=CASE WHEN (utr IS NULL OR utr = '') THEN %s ELSE utr END
WHERE code=%s AND status=1
LIMIT 1
```

- [x] **Step 4: 收敛失败状态**

`402` 第 1、2 次回到 `status=0`，第 3 次驳回；其他失败/未知进入 `status=2`。

### Task 4: 移除账单 Redis 回调去重

**Files:**
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: `api/jobs/Jazzcashpay_v2.py`

- [x] **Step 1: 删除 Redis if_callback 判断**

worker 不再通过 Redis zset 判断流水是否已回调。

- [x] **Step 2: 删除成功后写 Redis 已回调标记**

回调成功不再写 `if_callback_*`，重复处理交给 MySQL 幂等。

- [x] **Step 3: 删除清理 if_callback 任务**

主循环不再维护过期 Redis 回调集合。

### Task 5: 验收和文档

**Files:**
- Modify: `README.md`
- Modify: `build.md`
- Modify: `err.md`
- Create: `docs/superpowers/reports/2026-05-08-payout-idempotency-final-state-report.md`

- [x] **Step 1: 运行单元测试**

```bash
PYTHONPATH=api python3 -m unittest \
  api.tests.test_jazzcash_payout_state_machine \
  api.tests.test_statement_callback_mysql_idempotency \
  api.tests.test_jazzcash_auto_payout_v16 -v
```

- [x] **Step 2: 编译关键文件**

```bash
python3 -m py_compile \
  api/jobs/jazzcash/payout/order_lifecycle.py \
  api/jobs/jazzcash/payout/settlement.py \
  api/jobs/jazzcash/payout/transfer_executor.py \
  api/jobs/pakistanpay_v2.py \
  api/jobs/Jazzcashpay_v2.py
```

- [x] **Step 3: 静态验收**

```bash
rg -n "if_callback|mark_transaction_callback|clean_if_callback_key|zscore\\(self\\.if_callback_key" api/jobs/pakistanpay_v2.py api/jobs/Jazzcashpay_v2.py
rg -n "status IN \\(0, 1\\)|new_retry_count > 8|reject_msg_codes|msg_cd in reject_msg_codes" api/jobs/jazzcash/payout/order_lifecycle.py api/jobs/jazzcash/payout/settlement.py api/jobs/jazzcash/payout/transfer_executor.py
git diff --check
```

Expected: 前两条 `rg` 无命中，`git diff --check` 无输出。
