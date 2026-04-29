# D7pay 托管品牌实施计划

> **执行要求：** 按任务逐项实施并回写复选框状态。

**目标：** 将 D7pay 作为托管专属实例品牌落地到构建配置、租户配置、下载页配置和交付文档。

**架构：** 保持主干代码统一，通过 `ops/tenants/d7pay` 和前端构建 mode 承载客户差异。Flutter 只用构建参数切换展示名，保留现有 package name 以保护 Veridium/4F 授权。

**技术栈：** Vue CLI、Vite、Flutter、Kubernetes、MySQL、Redis。

---

### 任务 1：Web 构建配置

**文件：**
- Modify: `/Users/tear/pk_project_k8s/admin-h5/scripts/build.config.js`
- Modify: `/Users/tear/pk_project_k8s/admin-h5/package.json`
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/scripts/build.config.js`
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/package.json`

- [x] **Step 1: 增加 d7pay 构建配置**

`VUE_APP_SYSTEM=d7pay`，`VUE_APP_TITLE=D7pay`。

- [x] **Step 2: 增加构建命令**

admin 和 merchant 都支持：

```bash
npm run d7pay:prod
```

### 任务 2：apkdownload 租户元信息

**文件：**
- Modify: `/Users/tear/pk_project_k8s/apkdownload/package.json`
- Modify: `/Users/tear/pk_project_k8s/apkdownload/index.html`
- Modify: `/Users/tear/pk_project_k8s/apkdownload/src/components/Appdownload/index.vue`
- Modify: `/Users/tear/pk_project_k8s/apkdownload/public/files/android/appInfo.json`
- Create: `/Users/tear/pk_project_k8s/apkdownload/.env`
- Create: `/Users/tear/pk_project_k8s/apkdownload/.env.d7pay`

- [x] **Step 1: 支持 Vite mode**

`npm run build:d7pay` 使用 `VITE_APP_KEY=d7pay_merchant`。

- [x] **Step 2: 下载页按 app key 读取 JSON**

默认仍读取 `ashrafi_merchant`，D7pay mode 读取 `d7pay_merchant`，没有 APK 时显示 `APK Pending`。

### 任务 3：D7pay 租户配置与文档

**文件：**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tenant.yaml`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/secrets.env.example`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`
- Create: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-04-29-d7pay-hosted-branding-design.md`

- [x] **Step 1: 写入租户配置**

配置 namespace、数据库、Redis、fingerprint、apkdownload、域名和 App 构建参数。

- [x] **Step 2: 写入验收文档**

覆盖品牌、隔离、数据、业务、运维验收。

### 任务 4：Flutter 展示名参数化

**文件：**
- Create: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/app/brand.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/app/app.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/payments/presentation/home_page.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/lib/features/login/presentation/login_page.dart`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/build.gradle.kts`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/src/main/AndroidManifest.xml`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/build.md`

- [x] **Step 1: 添加品牌常量**

`APP_DISPLAY_NAME` 默认 `Ashrafi Merchant`，D7pay 构建传 `D7pay Merchant`。

- [x] **Step 2: Android label 支持 Gradle 属性**

`ORG_GRADLE_PROJECT_appLabel='D7pay Merchant'` 控制桌面名称。

### 任务 5：验证与发布

**文件：**
- 验证所有变更文件。

- [x] **Step 1: Web 构建**

```bash
cd /Users/tear/pk_project_k8s/admin-h5 && npm run d7pay:prod
cd /Users/tear/pk_project_k8s/merchant-h5 && npm run d7pay:prod
cd /Users/tear/pk_project_k8s/apkdownload && npm run build:d7pay
```

验收结果：三个构建均通过；admin 产物标题为 `D7pay管理系统`，merchant 产物标题为 `D7payMerchant`，apkdownload 产物读取 `d7pay_merchant` 并包含 D7pay APK。

- [x] **Step 2: Flutter 静态验证**

```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
export PATH=/Users/tear/sdk/flutter/bin:$PATH
flutter test test/login_page_test.dart test/payments_controller_test.dart
flutter analyze lib/app/brand.dart lib/app/app.dart lib/features/login/presentation/login_page.dart lib/features/payments/presentation/home_page.dart
```

验收结果：测试与分析均通过；D7pay release APK 构建通过，`aapt dump badging` 确认 package 为 `com.ashrafi.pay`，应用展示名为 `D7pay Merchant`。

- [x] **Step 3: Git 提交推送**

```bash
git add .
git commit -m "feat: add d7pay hosted branding config"
git push origin main
```
