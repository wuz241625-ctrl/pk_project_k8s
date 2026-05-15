# Bank Record 废除恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让银行流水“废除”保留幂等键，并新增“恢复”闭环，避免同一官方流水重复采集后再次核销。

**Architecture:** 后端在 `admin/application/partner/partner.py` 中新增可单测 helper 和恢复 handler；前端在银行流水页基于 `invalid/callback` 切换废除与恢复按钮；文档记录操作语义和部署验收。

**Tech Stack:** Tornado admin、aiomysql、Vue 2、Element UI、unittest、Vue CLI D7pay 构建。

---

### Task 1: 后端幂等语义测试

**Files:**
- Create: `admin/tests/test_bank_record_void_restore.py`
- Modify: `admin/application/partner/partner.py`

- [ ] **Step 1: Write the failing test**

```python
def test_void_update_keeps_original_keys(self):
    update_data = bank_record_void_update_data({"id": 7, "utr": "03001234567", "trans_id": "TXN7"}, "重复流水")
    self.assertEqual(update_data["invalid"], 1)
    self.assertNotIn("utr", update_data)
    self.assertNotIn("trans_id", update_data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore`
Expected: FAIL because helpers are not defined.

- [ ] **Step 3: Implement helper functions**

Add `bank_record_void_update_data()`, `strip_bank_record_void_suffix()`, `bank_record_restore_update_data()`, and `bank_record_active_duplicate_condition()` near existing partner helpers.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore`
Expected: PASS.

### Task 2: 后端恢复接口

**Files:**
- Modify: `admin/application/partner/partner.py`
- Modify: `admin/router.py`
- Create: `api/sql/20260515_add_bank_record_restore_permission.sql`

- [ ] **Step 1: Update delete handler**

Use `bank_record_void_update_data()` in `delBank_recoed.post()` and remove `utr/trans_id` mutation.

- [ ] **Step 2: Add restore handler**

Add `restoreBank_recoed.post()` that loads `bank_record`, checks `callback=0 AND invalid=1`, checks duplicate active `trans_id`, and updates `invalid=0`.

- [ ] **Step 3: Register route**

Add `url("/partner/restorebank_recoed", partner.restoreBank_recoed, name='restoreBank_recoed')`.

- [ ] **Step 4: Add permission migration**

Create an idempotent `INSERT INTO permissions ... WHERE NOT EXISTS` for `/partner/restorebank_recoed`.

- [ ] **Step 5: Compile and run targeted tests**

Run: `PYTHONPATH=admin python3 -m py_compile main.py router.py application/partner/partner.py`
Run: `PYTHONPATH=admin python3 -m unittest admin.tests.test_bank_record_void_restore admin.tests.test_partner_mysql_final_state`

### Task 3: 前端恢复入口

**Files:**
- Modify: `admin-h5/src/api/partner.js`
- Modify: `admin-h5/src/views/partner/bank-record.vue`
- Modify: `admin-h5/src/locales/zh.json`
- Modify: `admin-h5/src/locales/en.json`

- [ ] **Step 1: Add API wrapper**

Add `restoreBank_recoed(data)` posting to `/partner/restorebank_recoed`.

- [ ] **Step 2: Add restore button**

Render `↩️ 恢复` when `scope.row.invalid === 1 && scope.row.callback !== 1`; keep “废除” only when `invalid !== 1`.

- [ ] **Step 3: Add restore confirm handler**

Call `restoreBank_recoed({ id: row.id, memo: this.deleteMemo })`, show success message, and refresh list.

- [ ] **Step 4: Build D7pay frontend**

Run: `cd admin-h5 && npm run d7pay:prod`
Expected: build exits 0 and writes `dist/d7pay`.

### Task 4: 文档、检测、提交推送

**Files:**
- Modify: `admin/build.md`
- Modify: `admin/err.md`
- Modify: `admin-h5/build.md`
- Modify: `admin-h5/err.md`

- [ ] **Step 1: Document acceptance commands**

Add the new unittest and D7pay build command to build docs.

- [ ] **Step 2: Document the incident pattern**

Record “废除不要释放幂等键，误废除走恢复”的排错口径.

- [ ] **Step 3: Run GitNexus detect changes**

Run: `mcp__gitnexus__.detect_changes(scope="all", repo="pk_project_k8s")`
Expected: changed symbols are limited to bank record void/restore and docs.

- [ ] **Step 4: Commit and push**

Run: `git add ... && git commit -m "fix(admin): preserve bank record idempotency on void" && git push origin d7pay`.
