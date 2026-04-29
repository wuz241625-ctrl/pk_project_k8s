# D7pay Current Deployment Ops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 D7pay 当前线上部署检查结果整理成运维可执行文档，并补齐首次部署会用到的 Service/ConfigMap 合同。

**Architecture:** 线上仍是原 `pk` 实例，D7pay 必须通过 `ops/tenants/d7pay` 在 `pk-d7pay` namespace 独立发布。文档负责告诉运维怎么处理，K8s 合同负责防止 D7pay H5 与外部域名缺 Service 或 ConfigMap。

**Tech Stack:** Kubernetes、nginx、Jenkins、Python、Bash、D7pay 租户配置。

---

### Task 1: 线上证据整理

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`

- [x] **Step 1: 记录服务器仓库提交**

写入服务器 `/opt/cicd/k8s/pk_project_k8s` 当前提交：

```text
68a657d fix: clear jazzcash active stale cooldown errors
```

- [x] **Step 2: 记录 K8s 现状**

写入当前只有 `pk` namespace，不存在 `pk-d7pay`，并列出当前 `pk` Service、Deployment 镜像、PV/PVC。

- [x] **Step 3: 记录 nginx 和 apkdownload 现状**

写入当前只有原域名，没有 D7pay 域名；线上 `appInfo.json` 只有 `ashrafi_merchant`，没有 `d7pay_merchant`。

### Task 2: D7pay K8s 对外服务合同

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/k8s/services.yaml`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tenant.yaml`

- [x] **Step 1: 创建内部服务**

创建 `api`、`admin`、`merchant` ClusterIP Service，分别转发到 `9000`、`6000`、`8000`。

- [x] **Step 2: 创建 D7pay NodePort**

创建 `api-public:31085`、`admin-h5:31081`、`merchant-h5:31082`、`apkdownload:31080`，避免复用现有 `pk` 的 `30080-30085`。

- [x] **Step 3: 在 tenant.yaml 记录端口合同**

写入 `public_api_service: api-public` 和 D7pay NodePort 映射，供运维和校验脚本读取。

### Task 3: H5 nginx ConfigMap 合同

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/k8s/h5-configmaps.yaml`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins/deploy-d7pay.sh`

- [x] **Step 1: 创建 admin-h5 ConfigMap**

`admin-h5-nginx-conf` 保持 `/prod-api/ -> http://admin:6000/`，namespace 为 `pk-d7pay`。

- [x] **Step 2: 创建 merchant-h5 ConfigMap**

`merchant-h5-nginx-conf` 保持 `/prod-api/ -> http://merchant:8000/`，namespace 为 `pk-d7pay`。

- [x] **Step 3: 创建 apkdownload ConfigMap**

`download-nginx-conf` 保持下载页静态服务配置，namespace 为 `pk-d7pay`。

- [x] **Step 4: 更新 Jenkins apply 顺序**

`deploy-d7pay.sh` 在发布 deployment 前应用 `h5-configmaps.yaml` 和 `services.yaml`。

### Task 4: 运维文档同步

**Files:**
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-04-29-d7pay-current-deployment-ops-design.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/plans/2026-04-29-d7pay-current-deployment-ops.md`

- [x] **Step 1: 托管文档引用 runbook**

说明当前线上尚未部署 D7pay，运维必须按 runbook 创建独立实例。

- [x] **Step 2: 验收标准补运维项**

补充 `pk-d7pay`、NodePort、H5 ConfigMap、nginx、apkdownload 和 `/fingerprint` 的验收要求。

- [x] **Step 3: 保存设计与计划**

把本次头脑风暴、设计、执行步骤和验收标准写入 `docs/superpowers`。

### Task 5: 校验

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: 更新合同校验脚本**

校验 `services.yaml`、`h5-configmaps.yaml`、NodePort、`api-public` 和发布脚本 apply 项。

- [x] **Step 2: 运行校验命令**

```bash
python3 -m py_compile ops/tenants/d7pay/verify_release_contract.py
python3 ops/tenants/d7pay/verify_release_contract.py
bash -n ops/tenants/d7pay/jenkins/deploy-d7pay.sh
git diff --check
```

预期全部退出码为 0。

### Task 6: D7pay 客户域名修正

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tenant.yaml`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins.env.example`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins/deploy-d7pay.sh`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/k8s/runtime-configmap.yaml`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Modify: `/Users/tear/pk_project_k8s/api/build.md`

- [x] **Step 1: 移除 D7pay 默认 awekay 域名**

D7pay 租户配置改用 `*.d7pay.example.com` 占位，并标记 `domain_policy: customer_owned_required`。

- [x] **Step 2: 发布脚本拒绝错误域名**

`deploy-d7pay.sh` 对 `API_DOMAIN`、`ADMIN_DOMAIN`、`MERCHANT_DOMAIN`、`APKDOWNLOAD_DOMAIN` 执行校验，遇到 `example.com` 或 `awekay.com` 直接退出。

- [x] **Step 3: 运行时 ConfigMap 由 Jenkins 域名渲染**

`deploy-d7pay.sh` 根据 `API_PUBLIC_SCHEME` 和 `API_DOMAIN` 渲染 `API_PAY_URL`、`API_OSPAY_API_HOST` 和 `API_WEBSOCKET_ALLOW_HOST`，避免静态占位误发布。

- [x] **Step 4: 文档同步客户自有域名要求**

Runbook、托管文档、验收标准和 API 构建文档都写明 D7pay 必须使用客户自有域名，不能使用我们的 `awekay.com`。
