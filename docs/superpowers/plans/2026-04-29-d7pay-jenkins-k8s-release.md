# D7pay Jenkins K8s Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D7pay 从品牌构建补齐为 Jenkins/K8s 可发布的托管实例合同。

**Architecture:** `config.py` 继续作为真实运行文件不入库，tracked 的 `config.example.py` 负责环境变量模板。Jenkins 通过 `ops/tenants/d7pay/jenkins.env.example` 的变量合同构建镜像和 D7pay APK，K8s 通过 `ops/tenants/d7pay/k8s` 下的 namespace、ConfigMap、Secret 示例、PVC 和 deployment patch 管理运行数据与配置。

**Tech Stack:** Python、Tornado、Vue CLI、Vite、Flutter、Gradle、Kubernetes、Jenkins。

---

### Task 1: 运行配置模板

**Files:**
- Modify: `/Users/tear/pk_project_k8s/api/config.example.py`
- Modify: `/Users/tear/pk_project_k8s/admin/config.example.py`
- Create: `/Users/tear/pk_project_k8s/merchant/config.example.py`

- [x] **Step 1: api 配置改为环境变量模板**

`api/config.example.py` 支持 `TENANT_CODE`、MySQL、Redis、`API_PAY_URL`、`API_OSPAY_API_HOST`、WebSocket allow host、上下游密钥等环境变量。

- [x] **Step 2: admin 配置改为环境变量模板**

`admin/config.example.py` 支持 `TENANT_CODE`、MySQL、Redis、`ADMIN_API_URL`、Cookie Key、Token Key、通知配置等环境变量。

- [x] **Step 3: merchant 补 tracked 配置模板**

`merchant/config.example.py` 支持 `TENANT_CODE`、MySQL、Redis、`MERCHANT_API_URL` 和 Cookie Key。

### Task 2: Jenkins 与 K8s 合同

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tenant.yaml`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/secrets.env.example`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins.env.example`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins/deploy-d7pay.sh`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/k8s/*.yaml`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: tenant.yaml 补 Jenkins/K8s 字段**

记录 `pk-d7pay`、`pakistan_d7pay`、D7pay 域名、`com.d7pay.merchant`、共享签名策略、ConfigMap/Secret 名称和发布步骤。

- [x] **Step 2: 增加 Jenkins env 示例**

`jenkins.env.example` 明确 `RUN_ENV=PROD`、构建脚本、镜像变量、D7pay API 域名、App package、共享签名和 PVC 宿主机路径。

- [x] **Step 3: 增加 Jenkins 发布脚本**

`jenkins/deploy-d7pay.sh` 基于服务器现有 `/opt/cicd/k8s` 结构发布，构建前把 admin-h5、merchant-h5、apkdownload 的默认构建命令切到 D7pay mode，并把 deployment 发布到 `pk-d7pay`。

- [x] **Step 4: 增加 K8s 资源与 patch**

包含 namespace、runtime ConfigMap、Secret 示例、fingerprint/apkdownload PVC，以及 api/admin/merchant/apkdownload deployment patch。

- [x] **Step 5: 增加合同校验脚本**

`verify_release_contract.py` 检查 package、RUN_ENV、ConfigMap/Secret、PVC、`/fingerprint` 挂载和配置模板环境变量。

### Task 3: Flutter 包名与签名

**Files:**
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/build.gradle.kts`
- Create: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/key.properties.example`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/build.md`
- Modify: `/Users/tear/pk_project_k8s/apkdownload/public/files/android/appInfo.json`

- [x] **Step 1: Gradle 支持 package 参数**

新增 `ORG_GRADLE_PROJECT_appApplicationId=com.d7pay.merchant`，默认仍为 `com.ashrafi.pay`。

- [x] **Step 2: Gradle 支持正式签名强制检查**

新增 `ORG_GRADLE_PROJECT_requireReleaseSigning=true`，Jenkins 正式 release 缺少 `android/key.properties` 时直接失败。

- [x] **Step 3: 重新构建 D7pay APK**

使用 D7pay package 构建 arm64 release APK，并复制到 `apkdownload/public/files/android/d7pay/`。

### Task 4: 文档与验收

**Files:**
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Modify: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-04-29-d7pay-hosted-branding-design.md`
- Modify: `/Users/tear/pk_project_k8s/docs/superpowers/plans/2026-04-29-d7pay-hosted-branding.md`

- [x] **Step 1: 文档写明旧改动缺口**

说明之前只是品牌构建，不是完整 Jenkins/K8s 发布。

- [x] **Step 2: 文档写明包名与签名策略**

D7pay package 为 `com.d7pay.merchant`，签名共用同一份 release keystore。

- [x] **Step 3: 验收命令**

运行 Python 语法检查、D7pay release contract 校验、Flutter 测试/分析/APK 构建、apkdownload D7pay 构建。
