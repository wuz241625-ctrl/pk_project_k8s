# D7pay Logo Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将用户提供的 D7pay logo 适配到 admin、merchant、apkdownload 和 Flutter App，同时不影响默认 Ashrafi 构建。

**Architecture:** 通过生成脚本统一产出 D7pay 品牌资产。Web 端根据 D7pay 构建变量切换 logo/favicon；Flutter 端通过 Gradle `appIcon` 参数切换 launcher icon。

**Tech Stack:** Python Pillow、Vue CLI、Vite、Flutter/Gradle、Android mipmap 资源。

---

### Task 1: 品牌资产生成

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/assets/generate_logo_assets.py`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/assets/d7pay-logo-mark-1024.png`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/assets/d7pay-logo-full-1600x1200.png`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/assets/d7pay-logo-wordmark-900x260.png`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/assets/d7pay-favicon.ico`

- [x] **Step 1: 编写生成脚本**

使用 Pillow 生成 D7pay mark、full logo、wordmark 和 favicon。

- [x] **Step 2: 导出 Web 资产**

输出 admin、merchant、apkdownload 所需 PNG/ICO。

- [x] **Step 3: 导出 Flutter launcher icon**

输出 `ic_launcher_d7pay.png` 到 mdpi/hdpi/xhdpi/xxhdpi/xxxhdpi。

### Task 2: admin-h5 适配

**Files:**
- Modify: `/Users/tear/pk_project_k8s/admin-h5/scripts/build.config.js`
- Modify: `/Users/tear/pk_project_k8s/admin-h5/public/index.html`
- Modify: `/Users/tear/pk_project_k8s/admin-h5/src/settings.js`
- Modify: `/Users/tear/pk_project_k8s/admin-h5/src/layout/components/Sidebar/Logo.vue`
- Modify: `/Users/tear/pk_project_k8s/admin-h5/build.md`

- [x] **Step 1: D7pay 构建注入 favicon**

`VUE_APP_FAVICON=d7pay-favicon.ico`。

- [x] **Step 2: D7pay 构建启用侧边栏 logo**

`sidebarLogo` 在 `VUE_APP_SYSTEM=d7pay` 时为 true。

- [x] **Step 3: D7pay 构建使用 D7pay logo**

`Logo.vue` 在 D7pay 模式使用 `src/assets/brand/d7pay-logo-mark.png`。

### Task 3: merchant-h5 适配

**Files:**
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/scripts/build.config.js`
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/public/index.html`
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/src/settings.js`
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/src/layout/components/Sidebar/Logo.vue`
- Modify: `/Users/tear/pk_project_k8s/merchant-h5/build.md`

- [x] **Step 1: D7pay 构建注入 favicon**

`VUE_APP_FAVICON=d7pay-favicon.ico`。

- [x] **Step 2: D7pay 构建启用侧边栏 logo**

`sidebarLogo` 在 `VUE_APP_SYSTEM=d7pay` 时为 true。

- [x] **Step 3: D7pay 构建使用 D7pay logo**

`Logo.vue` 在 D7pay 模式使用 `src/assets/brand/d7pay-logo-mark.png`。

### Task 4: apkdownload 适配

**Files:**
- Modify: `/Users/tear/pk_project_k8s/apkdownload/src/views/apkm.vue`
- Modify: `/Users/tear/pk_project_k8s/apkdownload/build.md`

- [x] **Step 1: D7pay mode 使用 D7pay logo**

当 `VITE_APP_KEY=d7pay_merchant` 时使用 `d7pay-logo-192x192.png`。

- [x] **Step 2: 默认 logo 不变**

非 D7pay mode 继续使用原 `logo-192x192.png`。

### Task 5: Flutter App 适配

**Files:**
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/build.gradle.kts`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/src/main/AndroidManifest.xml`
- Modify: `/Users/tear/pk_project/ashrafi_merchant_flutter/build.md`
- Create: `/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/src/main/res/mipmap-*/ic_launcher_d7pay.png`

- [x] **Step 1: Gradle 支持 appIcon 参数**

新增 `ORG_GRADLE_PROJECT_appIcon`，默认 `@mipmap/ic_launcher`。

- [x] **Step 2: Manifest 使用占位符**

`android:icon="${appIcon}"`。

- [x] **Step 3: D7pay 文档加入 appIcon 参数**

D7pay 构建命令使用 `ORG_GRADLE_PROJECT_appIcon='@mipmap/ic_launcher_d7pay'`。

### Task 6: 校验

- [x] **Step 1: 运行构建与合同校验**

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod
npm run build:d7pay
export PATH=/Users/tear/sdk/flutter/bin:$PATH
flutter test --no-test-assets test/login_page_test.dart test/payments_controller_test.dart
cd android
./gradlew :app:packageDebug -PappApplicationId=com.d7pay.merchant -PappLabel='D7pay Merchant' -PappIcon='@mipmap/ic_launcher_d7pay'
```

预期全部退出码为 0。
