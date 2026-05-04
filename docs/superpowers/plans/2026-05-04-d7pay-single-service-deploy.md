# D7pay Single Service Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D7pay 发布入口拆成首次全量发布和维护期单服务发布，同时保持 Jenkins/K8s 发布合同可审计。

**Architecture:** 保留 `deploy-d7pay.sh` 作为唯一发布脚本，在脚本内增加目标选择器和分发函数。Makefile 只做薄入口，把单服务目标映射到 `D7PAY_DEPLOY_TARGETS`。

**Tech Stack:** GNU make、bash、Kubernetes `kubectl`、Docker、Python `unittest`。

---

### Task 1: 目标选择测试

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tests/test_deploy_targets.py`

- [x] **Step 1: 写失败测试**

测试 source `deploy-d7pay.sh` 后调用 `set_deploy_targets` 和 `deploy_selected_targets`，覆盖默认全量、逗号分隔、去重、非法目标和单服务分发。

- [x] **Step 2: 运行测试确认失败**

```bash
python3 -m unittest ops.tenants.d7pay.tests.test_deploy_targets
```

预期：失败，因为 `set_deploy_targets` 尚未实现。

### Task 2: 部署脚本目标选择器

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins/deploy-d7pay.sh`

- [x] **Step 1: 增加支持目标**

定义 `ALL_D7PAY_DEPLOY_TARGETS=(api admin merchant admin-h5 merchant-h5 apkdownload)`。

- [x] **Step 2: 增加解析函数**

实现 `set_deploy_targets`，支持 `all`、`full`、逗号、空格和去重；非法目标返回非零。

- [x] **Step 3: 增加分发函数**

实现 `deploy_target` 和 `deploy_selected_targets`，将目标映射到已有构建函数。

- [x] **Step 4: 保持脚本可 source**

使用 `if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi`，让测试可以 source 函数，直接执行脚本时行为不变。

### Task 3: Makefile 单服务入口

**Files:**
- Modify: `/Users/tear/pk_project_k8s/Makefile`

- [x] **Step 1: 扩展 phony 目标**

新增 `d7pay-deploy-api`、`d7pay-deploy-admin`、`d7pay-deploy-merchant`、`d7pay-deploy-admin-h5`、`d7pay-deploy-merchant-h5`、`d7pay-deploy-apkdownload`、`d7pay-deploy-service`。

- [x] **Step 2: 目标映射**

单服务目标设置 `D7PAY_DEPLOY_TARGETS` 后调用同一个 `deploy-d7pay.sh`。

- [x] **Step 3: 参数化入口**

`d7pay-deploy-service` 要求 `SERVICE` 非空，并传给 `D7PAY_DEPLOY_TARGETS`。

### Task 4: 文档和合同检查

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/README_OPERATIONS.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/build.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: 区分首次发布和维护发布**

文档明确 `make d7pay-deploy` 是全量入口，维护期优先使用单服务入口。

- [x] **Step 2: 更新验收标准**

验收标准加入单服务发布不会滚动其他服务、非法目标失败、参数化 Jenkins 入口可用。

- [x] **Step 3: 更新合同检查**

`verify_release_contract.py` 检查 Makefile、运维 SOP 和部署脚本包含单服务发布合同。

### Task 5: 验证与交付

**Files:**
- Verify only

- [x] **Step 1: 运行脚本测试**

```bash
python3 -m unittest ops.tenants.d7pay.tests.test_deploy_targets
```

- [x] **Step 2: 运行语法检查**

```bash
bash -n ops/tenants/d7pay/jenkins/deploy-d7pay.sh
bash -n ops/tenants/d7pay/scripts/preflight.sh
```

- [x] **Step 3: 运行合同检查**

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

- [x] **Step 4: 运行 Makefile dry-run**

```bash
make -n d7pay-deploy-api D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make -n d7pay-deploy-service SERVICE=admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

- [x] **Step 5: 提交并推送**

```bash
git add Makefile ops/tenants/d7pay docs/superpowers/specs/2026-05-04-d7pay-single-service-deploy-design.md docs/superpowers/plans/2026-05-04-d7pay-single-service-deploy.md docs/rental/d7pay-hosted.md
git commit -m "feat: support d7pay single service deploy"
git push origin d7pay
```
