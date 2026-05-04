# D7pay Config Only Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D7pay 运维入口从构建发布收缩为配置检查与配置修复，避免和用户现有 Dockerfile 发布脚本冲突。

**Architecture:** 新增 `apply-config.sh` 专门应用 K8s 公共配置；旧 `deploy-d7pay.sh` 变成 config-only 兼容包装器；测试和合同检查禁止 D7pay 脚本再出现 Dockerfile 改写或 Docker 构建逻辑。

**Tech Stack:** Bash、Python unittest、Kubernetes YAML、Makefile。

---

### Task 1: Config-only 边界测试

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tests/test_config_only_release.py`
- Delete: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tests/test_deploy_targets.py`

- [x] **Step 1: 写测试**

测试 `deploy-d7pay.sh`、`apply-config.sh` 不包含 `docker build`、`docker push`、`Dockerfile`、`RUN pnpm`、`pnpm build`、`kubectl patch deployment`。

- [x] **Step 2: 运行测试确认当前失败**

```bash
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release
```

预期：当前失败，因为旧 `deploy-d7pay.sh` 仍含构建和 Dockerfile 改写逻辑。

### Task 2: 新增配置应用入口

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/apply-config.sh`

- [x] **Step 1: 读取环境与防呆**

读取 `D7PAY_ENV`，校验客户域名、namespace、Secret YAML、`kubectl` 和 `python3`。

- [x] **Step 2: 应用公共配置**

应用 namespace、runtime ConfigMap、H5 ConfigMap、Service、真实 Secret 和 data volumes。

- [x] **Step 3: 不构建不滚动**

脚本内不出现 Docker、Dockerfile、镜像 patch 或 rollout。

### Task 3: 降级旧发布脚本

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins/deploy-d7pay.sh`

- [x] **Step 1: 改成包装器**

旧脚本只打印提示并执行 `scripts/apply-config.sh`。

- [x] **Step 2: 移除构建逻辑**

删除目标选择器、Docker build/push、Dockerfile 改写、deployment image patch。

### Task 4: Makefile 和文档

**Files:**
- Modify: `/Users/tear/pk_project_k8s/Makefile`
- Modify: `/Users/tear/pk_project_k8s/build.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/README_OPERATIONS.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/build.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/err.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: Makefile 增加 config 入口**

新增 `d7pay-apply-config`，保留旧 deploy 目标但说明为兼容配置包装器。

- [x] **Step 2: 文档改职责边界**

说明用户脚本负责构建/发布，D7pay 只负责 preflight/render/apply-config/healthcheck。

- [x] **Step 3: 合同检查同步**

合同检查强制禁止 D7pay 脚本重新引入 Dockerfile 改写或 Docker 构建。

### Task 5: 验证和交付

**Files:**
- Verify only

- [x] **Step 1: 运行边界测试**

```bash
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release
```

- [x] **Step 2: 运行语法检查**

```bash
bash -n ops/tenants/d7pay/scripts/apply-config.sh
bash -n ops/tenants/d7pay/jenkins/deploy-d7pay.sh
```

- [x] **Step 3: 运行合同检查和 preflight**

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
make d7pay-preflight
```

- [x] **Step 4: 提交推送**

```bash
git add Makefile build.md docs/rental/d7pay-hosted.md docs/superpowers/specs/2026-05-04-d7pay-config-only-release-design.md docs/superpowers/plans/2026-05-04-d7pay-config-only-release.md ops/tenants/d7pay
git commit -m "chore: make d7pay release config-only"
git push origin d7pay
```
