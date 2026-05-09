# D7pay Fund Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 D7pay 订单、银行流水和余额流水补上数据库层资金幂等保护。

**Architecture:** 用 SQL 迁移提供订单/流水唯一约束和余额幂等表；用轻量 helper 在核心余额变更入口抢幂等键，重复业务事件直接跳过余额变更。迁移发现重复数据时跳过对应唯一约束，避免上线时直接中断。

**Tech Stack:** MySQL 8.0、Python、Tornado、pytest/unittest、GitNexus。

---

### Task 1: 资金约束合同测试

**Files:**
- Create: `api/tests/test_fund_integrity_contract.py`

- [x] **Step 1: 写失败测试**

覆盖迁移 SQL、幂等 key 生成、同步/异步抢幂等键、核心余额写入口接入。

- [x] **Step 2: 验证失败**

Run: `PYTHONPATH=api python3 -m pytest api/tests/test_fund_integrity_contract.py -q`

Expected: 缺少 helper、迁移和接入点，测试失败。

### Task 2: 迁移和幂等 helper

**Files:**
- Create: `api/sql/20260509_add_fund_integrity_constraints.sql`
- Create: `api/application/balance_idempotency.py`
- Create: `admin/application/balance_idempotency.py`
- Create: `merchant/application/balance_idempotency.py`

- [x] **Step 1: 新增 SQL 迁移**

增加 `uk_orders_df_merchant_code`、`uk_orders_ds_trans_id_unique`、`uk_bank_record_payment_trade_trans` 和 `balance_record_idempotency`。

- [x] **Step 2: 新增 helper**

提供 `build_balance_idempotency_key`、`reserve_balance_idempotency`、`reserve_balance_idempotency_sync`。

### Task 3: 核心余额入口接入

**Files:**
- Modify: `api/application/base.py`
- Modify: `admin/application/base.py`
- Modify: `merchant/application/base.py`
- Modify: `api/jobs/easypaisa/payout/settlement.py`
- Modify: `api/jobs/jazzcash/payout/settlement.py`

- [x] **Step 1: 变更前抢幂等键**

在读余额和改余额前计算业务幂等键并 `INSERT IGNORE`。

- [x] **Step 2: 重复业务事件直接返回成功**

避免调用方重试造成二次加减余额。

### Task 4: 验收和文档

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Create: `docs/superpowers/reports/2026-05-09-d7pay-fund-integrity-report.md`

- [x] **Step 1: 运行验证**

运行合同测试、相关回调/代付测试、py_compile。

- [x] **Step 2: 更新文档**

记录迁移前只读查重、上线顺序和回滚注意事项。
