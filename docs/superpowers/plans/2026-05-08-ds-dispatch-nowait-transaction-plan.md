# DS Dispatch NOWAIT Transaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让代收派单最终抢占使用手写 MySQL 事务和 `FOR UPDATE NOWAIT`，锁不到立即换下一个候选。

**Architecture:** 候选 SQL 保持只读和 `LIMIT 20`；最终接单事务先锁 `partner` 再锁 `payment`，锁后重新校验余额、状态、限额和订单状态，再扣余额并推进 `orders_ds.status=1`。

**Tech Stack:** Python async、aiomysql、MySQL InnoDB、pytest、现有 `application.pay.dispatch`。

---

### Task 1: 锁冲突识别和锁 SQL 测试

**Files:**
- Modify: `api/tests/test_ds_dispatch_candidate_sql.py`
- Modify: `api/application/pay/dispatch.py`

- [x] **Step 1: 写失败测试**

新增测试断言候选 SQL 不加锁、最终锁 SQL 使用 `FOR UPDATE NOWAIT`，并识别 `3572` / `1205`。

- [x] **Step 2: 运行测试确认失败**

Run:

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py -q
```

Expected: 新增测试因 helper 尚不存在而失败。

- [x] **Step 3: 实现最小 helper**

在 `dispatch.py` 中增加：

- `_is_nowait_lock_error(exc)`
- `_lock_ds_dispatch_candidate(cur, partner_id, payment_id)`
- `_fetch_payment_amount_today_in_tx(cur, payment_id)`

- [x] **Step 4: 运行测试确认通过**

Run:

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py -q
```

Expected: PASS。

### Task 2: 接入最终抢占事务

**Files:**
- Modify: `api/application/pay/dispatch.py`

- [x] **Step 1: 在 `push_order()` 最终事务中先锁行**

锁顺序：

```sql
SELECT ... FROM partner WHERE id=%s FOR UPDATE NOWAIT;
SELECT ... FROM payment WHERE id=%s FOR UPDATE NOWAIT;
```

- [x] **Step 2: 锁后重新校验**

事务内重新校验：

- partner 状态、认证、余额。
- payment 归属、代收状态、人工锁。
- `amount_top` 今日额度。
- 外部码商未回调扣款流水。

- [x] **Step 3: 锁冲突回滚换候选**

`3572` / `1205` 只记录 warning，回滚后 `continue`。

- [x] **Step 4: 保持订单幂等推进**

继续使用：

```sql
UPDATE orders_ds SET ... WHERE code=%s AND status=0
```

### Task 3: 文档和验收

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Create: `docs/superpowers/reports/2026-05-08-ds-dispatch-nowait-transaction-report.md`

- [x] **Step 1: 更新构建文档**

记录代收派单 NOWAIT 事务验收命令。

- [x] **Step 2: 更新排错文档**

记录锁等待、NOWAIT 锁冲突和候选 SQL 不应加锁的排查口径。

- [x] **Step 3: 运行验收**

Run:

```bash
PYTHONPATH=api python3 -m pytest \
  api/tests/test_ds_dispatch_candidate_sql.py \
  api/tests/test_easypaisa_mysql_eligibility.py \
  api/tests/test_easypaisa_wallet_status_dispatch.py \
  api/tests/test_ds_dispatch_push_order_new_retirement.py -q

python3 -m py_compile api/application/pay/dispatch.py api/application/pay/pay.py
git diff --check
```

Expected: 全部 exit 0。

- [x] **Step 4: 提交并推送**

Run:

```bash
git add api/application/pay/dispatch.py api/tests/test_ds_dispatch_candidate_sql.py api/build.md api/err.md docs/superpowers/specs/2026-05-08-ds-dispatch-nowait-transaction-design.md docs/superpowers/plans/2026-05-08-ds-dispatch-nowait-transaction-plan.md docs/superpowers/reports/2026-05-08-ds-dispatch-nowait-transaction-report.md
git commit -m "feat: add nowait transaction lock for ds dispatch"
git push origin main
```
