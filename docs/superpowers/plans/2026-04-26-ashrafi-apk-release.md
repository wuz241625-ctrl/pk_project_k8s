# Ashrafi APK 发布执行计划

> **给自动化执行者:** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐步执行本计划。步骤使用 checkbox（`- [ ]`）记录状态。

**目标:** 发布 Ashrafi Flutter release APK 到线上 apkdownload，并完成 API 指纹持久化挂载和账号交付验收。

**架构:** APK 作为静态制品纳入 `apkdownload` 工程，由线上部署脚本构建镜像并滚动更新。API 指纹目录通过已有 Kubernetes PV/PVC 挂载验证，不改变业务代码。

**技术栈:** Flutter 3.32.4、Vue 3/Vite、Kubernetes、Docker、MySQL。

---

### Task 1: 本地 APK 制品和 apkdownload 配置

**文件:**
- 修改: `/Users/tear/pk_project_k8s/apkdownload/public/files/android/appInfo.json`
- 新增: `/Users/tear/pk_project_k8s/apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk`
- 新增: `/Users/tear/pk_project_k8s/apkdownload/build.md`
- 新增: `/Users/tear/pk_project_k8s/apkdownload/err.md`

- [x] **Step 1: 用当前系统域名构建 Flutter APK**

执行:

```bash
cd /Users/tear/pk_project/ashrafi_merchant_flutter
export PATH=/Users/tear/sdk/flutter/bin:$PATH
flutter pub get
flutter build apk --release \
  --target-platform android-arm,android-arm64 \
  -PtargetAbis=armeabi-v7a,arm64-v8a \
  --obfuscate \
  --split-debug-info=build/symbols \
  --dart-define=API_BASE_URL=http://api.awekay.com
```

预期: `Built build/app/outputs/flutter-apk/app-release.apk`。

- [x] **Step 2: 复制 APK 到 apkdownload 静态目录**

执行:

```bash
mkdir -p /Users/tear/pk_project_k8s/apkdownload/public/files/android/ashrafi
cp /Users/tear/pk_project/ashrafi_merchant_flutter/build/app/outputs/flutter-apk/app-release.apk \
  /Users/tear/pk_project_k8s/apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk
```

预期: 目标 APK 存在，SHA256 为 `90f3edb5bbb30984856059df9f7b031d3c1dc652a58dfa43b080e4ea99a59532`。

- [x] **Step 3: 更新下载元信息和构建/排错文档**

预期: `appInfo.json` 指向 `/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk`，`build.md` 写清构建和部署命令，`err.md` 记录 kubectl kubeconfig 问题。

- [x] **Step 4: 验证 apkdownload 本地构建**

执行:

```bash
cd /Users/tear/pk_project_k8s/apkdownload
npm install
npm run build
```

预期: Vite 构建退出码为 0。

### Task 2: 提交并推送发布制品

**文件:**
- 修改: `/Users/tear/pk_project_k8s/apkdownload/public/files/android/appInfo.json`
- 新增: `/Users/tear/pk_project_k8s/apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk`
- 新增: `/Users/tear/pk_project_k8s/apkdownload/build.md`
- 新增: `/Users/tear/pk_project_k8s/apkdownload/err.md`
- 新增: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-04-26-ashrafi-apk-release-design.md`
- 新增: `/Users/tear/pk_project_k8s/docs/superpowers/plans/2026-04-26-ashrafi-apk-release.md`

- [ ] **Step 1: 检查差异格式**

执行:

```bash
cd /Users/tear/pk_project_k8s
git diff --check
```

预期: 无输出，退出码为 0。

- [ ] **Step 2: 暂存发布文件**

执行:

```bash
git add \
  apkdownload/public/files/android/appInfo.json \
  apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk \
  apkdownload/build.md \
  apkdownload/err.md \
  docs/superpowers/specs/2026-04-26-ashrafi-apk-release-design.md \
  docs/superpowers/plans/2026-04-26-ashrafi-apk-release.md
```

预期: `git diff --cached --check` 退出码为 0。

- [ ] **Step 3: 提交并推送**

执行:

```bash
git commit -m "chore: 发布 Ashrafi APK 下载包"
git push origin main
```

预期: 远端 `main` 包含本次 APK 制品和文档。

### Task 3: 线上部署和验收

**文件:**
- 远端: `/opt/cicd/k8s/sh/deploy-apkdownload.sh`
- 远端: `/opt/cicd/k8s/apkdownload/k8s/apkdownload-deployment.yaml`

- [ ] **Step 1: 运行线上部署脚本**

执行:

```bash
ssh root@34.92.65.29 '/opt/cicd/k8s/sh/deploy-apkdownload.sh'
```

预期: 镜像构建并推送；如果 `kubectl apply` 因 kubeconfig 失败，使用 `/etc/kubernetes/admin.conf` 补 apply。

- [ ] **Step 2: 验证 rollout**

执行:

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/apkdownload-deploy -n pk --timeout=240s
```

预期: `deployment "apkdownload-deploy" successfully rolled out`。

- [ ] **Step 3: 验证下载链接**

执行:

```bash
curl -I http://apkdownload.awekay.com/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk
```

预期: HTTP 200，`Content-Length` 大于 68 MB。

### Task 4: 指纹挂载和账号验收

**文件:**
- 远端 Kubernetes deployment: `api-deploy`
- 远端 MySQL database: `pakistan`

- [ ] **Step 1: 验证指纹持久化卷**

执行:

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get pv api-fingerprint-pv
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get pvc api-fingerprint-pvc -n pk
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/api-deploy -- mount | grep /app/api/application/app/login/banks/fingerprint
```

预期: PV/PVC 为 `Bound`，容器内指纹路径有挂载记录。

- [ ] **Step 2: 查询演示账号**

执行:

```sql
SELECT id, account, name, role, status FROM admin WHERE id IN (1,9001,9002,9003,9004);
SELECT id, cellphone, name, status FROM merchant WHERE id BETWEEN 9101 AND 9108;
SELECT id, cellphone, name, status FROM partner WHERE id BETWEEN 9201 AND 9204;
```

预期: 账号存在且 `status=1`。
