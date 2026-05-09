# D7pay PK File Diff Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 D7pay 与 pk_project 文件对比中确认无用的旧代码残留，同时保留 D7pay 租户差异。

**Architecture:** 只清理孤立残留，不做业务同步覆盖。通过旧印度钱包退役测试、关键词扫描、编译和 GitNexus 变更审计确认范围。

**Tech Stack:** Python、Tornado、unittest、GitNexus。

---

### Task 1: 锁定可清理残留

**Files:**
- Modify: `api/tests/test_legacy_india_bank_code_retirement.py`

- [x] **Step 1: 增加失败用例**

新增 `test_websocket_bank_analysis_no_longer_keeps_retired_bank_parsers`，断言 `api/application/websocket/bank_analysis.py` 不包含旧函数名。

- [x] **Step 2: 运行单测确认失败**

Run:

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_legacy_india_bank_code_retirement.LegacyIndiaBankCodeRetirementTest.test_websocket_bank_analysis_no_longer_keeps_retired_bank_parsers -v
```

Expected: FAIL，提示仍包含 `async def indusind`。

### Task 2: 清理残留代码

**Files:**
- Modify: `api/application/websocket/bank_analysis.py`
- Modify: `admin/application/count/collect_partner.py`
- Modify: `api/application/lakshmi_api/controllers/http_login_controller.py`

- [x] **Step 1: 删除旧银行解析函数**

删除 `indusind`、`freecharge`、`mobikwik`、`maharastra`，保留其它已有解析函数。

- [x] **Step 2: 删除旧 Redis 在线集合注释**

删除 `getOnlinePayment` 注释块，避免 `payment_online_ds` / `payment_online_df` 旧业务态再次回流。

- [x] **Step 3: 修正登录控制器注释**

将不存在的 `JioBank` 注释改为“当前仍在使用的登录模块”。

### Task 3: 文档和验收

**Files:**
- Create: `docs/superpowers/specs/2026-05-09-d7pay-pk-file-diff-cleanup-design.md`
- Create: `docs/superpowers/plans/2026-05-09-d7pay-pk-file-diff-cleanup-plan.md`
- Create: `docs/superpowers/reports/2026-05-09-d7pay-pk-file-diff-cleanup-report.md`
- Modify: `api/build.md`
- Modify: `api/err.md`

- [x] **Step 1: 写明差异保留与清理边界**

记录 D7pay 必须保留 IP、时区、env 和 K8s/Jenkins 差异。

- [x] **Step 2: 记录验证命令**

记录旧印度钱包退役测试、编译检查和关键词扫描。
