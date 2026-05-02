# Test Branch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建原 `pk` 测试环境专用 `test` 分支，并保证它不包含客户租户交付内容。

**Architecture:** `test` 分支基于 `68a657d`，只增加分支说明、根目录构建索引和排错索引；租户相关内容保留在客户租户分支。

**Tech Stack:** Git branch、Markdown。

---

### Task 1: 创建 test 分支说明

**Files:**
- Create: `/Users/tear/pk_project_k8s/docs/branches/test.md`
- Create: `/Users/tear/pk_project_k8s/build.md`
- Create: `/Users/tear/pk_project_k8s/err.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-05-02-test-branch-design.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/plans/2026-05-02-test-branch.md`

- [x] **Step 1: 写入分支说明**

说明 `test` 是当前服务器原 `pk` 测试环境发布源。

- [x] **Step 2: 写入构建和排错索引**

根目录 `build.md`、`err.md` 只指向原测试环境构建和排错入口。

### Task 2: 验证分支隔离

**Files:**
- Verify only.

- [x] **Step 1: 确认租户目录不存在**

Run:

```bash
test ! -e ops/tenants/d7pay
```

- [x] **Step 2: 确认客户 APK 目录不存在**

Run:

```bash
test ! -e apkdownload/public/files/android/d7pay
```

- [x] **Step 3: 确认核心工程没有客户专属标识**

Run:

```bash
! rg -n "d7pay:prod|ic_launcher_d7pay|pk-d7pay" admin-h5 merchant-h5 apkdownload api admin merchant
```
