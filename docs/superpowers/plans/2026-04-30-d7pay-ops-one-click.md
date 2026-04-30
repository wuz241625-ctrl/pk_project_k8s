# D7pay Ops One Click Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 D7pay 运维交付从长文档改成一页 SOP 加一键命令。

**Architecture:** 根目录 `Makefile` 暴露固定命令；`ops/tenants/d7pay/scripts/` 放置可执行检查、渲染、健康检查和回滚脚本；`README_OPERATIONS.md` 作为运维唯一入口；长 runbook 保留为排障和细节说明。

**Tech Stack:** Make、Bash、Python、Kubernetes、nginx、Jenkins。

---

### Task 1: 运维命令入口

**Files:**
- Create: `/Users/tear/pk_project_k8s/Makefile`
- Create: `/Users/tear/pk_project_k8s/build.md`
- Create: `/Users/tear/pk_project_k8s/err.md`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/common.sh`

- [x] **Step 1: 增加 Makefile 目标**

提供 `d7pay-preflight`、`d7pay-render-config`、`d7pay-deploy`、`d7pay-healthcheck`、`d7pay-rollback`。

- [x] **Step 2: 增加根目录构建与排错入口**

`build.md` 和 `err.md` 指向 D7pay Makefile 命令与子目录排错说明。

- [x] **Step 3: 增加共享运维函数**

`common.sh` 负责读取 `D7PAY_ENV`、校验客户域名、保护 namespace、查命令和输出分段。

### Task 2: 运维脚本

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/preflight.sh`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/render_runtime_config.py`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/render-config.sh`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/healthcheck.sh`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/rollback.sh`

- [x] **Step 1: preflight 检查合同、语法、YAML、域名、Secret 和集群可读性**
- [x] **Step 2: render-config 输出 runtime ConfigMap、nginx 片段和非敏感摘要**
- [x] **Step 3: healthcheck 检查 rollout 与客户域名连通性**
- [x] **Step 4: rollback 默认 rollout undo，并支持 scale-zero 停用**

### Task 3: 运维短文档与排错

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/README_OPERATIONS.md`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/build.md`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/err.md`

- [x] **Step 1: 一页 SOP 写明禁止事项、准备、发布、验收、回滚**
- [x] **Step 2: build.md 写明 D7pay 命令**
- [x] **Step 3: err.md 收录本轮脚本的常见错误**

### Task 4: 同步长文档和发布合同

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins/deploy-d7pay.sh`

- [x] **Step 1: runbook 指向 README_OPERATIONS.md**
- [x] **Step 2: 托管说明和验收标准同步运维入口**
- [x] **Step 3: 发布合同校验 Makefile、SOP 和脚本**
- [x] **Step 4: deploy 脚本支持 D7PAY_ENV，并拒绝覆盖脏工作区**

### Task 5: 验收

**Files:**
- Verify only.

- [x] **Step 1: 运行 Python 编译检查**
- [x] **Step 2: 运行 shell 语法检查**
- [x] **Step 3: 运行 D7pay release contract**
- [x] **Step 4: 运行 preflight**
- [x] **Step 5: 运行 git diff --check**
