# Test 与 D7pay 分支隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 `d7pay` 与 `test` 两个远程分支，让 D7pay 托管内容和当前 `pk` 测试环境分离。

**Architecture:** `d7pay` 分支基于当前最新提交，保留 D7pay 租户资源；`test` 分支基于最后一个非 D7pay 提交 `68a657d`，只补测试环境分支说明和根级构建/排错索引，不引入 D7pay 文件。

**Tech Stack:** Git branch、Markdown、现有 D7pay release contract。

---

### Task 1: 创建 d7pay 分支

**Files:**
- Create: `/Users/tear/pk_project_k8s/docs/branches/d7pay.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-05-02-branch-split-design.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/plans/2026-05-02-branch-split.md`

- [x] **Step 1: 从当前最新提交创建 `d7pay` 分支**

Run:

```bash
git switch -c d7pay
```

- [x] **Step 2: 写入 d7pay 分支说明**

说明 `d7pay` 分支包含 D7pay 租户合同、K8s/Jenkins、品牌资源和运维命令。

### Task 2: 创建 test 分支

**Files:**
- Create on test branch: `/Users/tear/pk_project_k8s/docs/branches/test.md`
- Create on test branch: `/Users/tear/pk_project_k8s/build.md`
- Create on test branch: `/Users/tear/pk_project_k8s/err.md`

- [ ] **Step 1: 从最后一个非 D7pay 提交创建 `test` 分支**

Run:

```bash
git switch -c test 68a657d
```

- [ ] **Step 2: 写入 test 分支说明**

说明 `test` 是当前服务器原 `pk` 测试环境发布源，不包含 D7pay 租户资源。

### Task 3: 验证与推送

**Files:**
- Verify only.

- [ ] **Step 1: 验证 d7pay 分支**

Run:

```bash
git switch d7pay
python3 ops/tenants/d7pay/verify_release_contract.py
make d7pay-preflight
git diff --check
```

- [ ] **Step 2: 验证 test 分支**

Run:

```bash
git switch test
test ! -e ops/tenants/d7pay
test ! -e apkdownload/public/files/android/d7pay
! rg -n "d7pay:prod|ic_launcher_d7pay|pk-d7pay" admin-h5 merchant-h5 apkdownload api admin merchant
git diff --check
```

- [ ] **Step 3: 推送两个分支**

Run:

```bash
git push -u origin d7pay
git push -u origin test
```
