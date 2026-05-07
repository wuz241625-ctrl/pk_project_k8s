# apkdownload 构建文档

## 本地构建

```bash
cd /Users/tear/pk_project_k8s/apkdownload
npm install
npm run build
```

## APK 文件发布

APK 文件放在：

```text
public/files/android/<app-name>/<filename>.apk
```

下载页读取：

```text
public/files/android/appInfo.json
```

当前 D7pay App 使用 `d7pay_merchant` 配置键，实际文件指向：

```text
public/files/android/d7pay/d7pay_merchant_universal_v0.1.8_202605031855.apk
```

下载页展示名与 Flutter Android 包保持一致：

```text
D7pay Merchant
```

## D7pay 下载页构建

D7pay 托管实例使用 Vite mode 读取 `d7pay_merchant` 元信息：

```bash
cd /Users/tear/pk_project_k8s/apkdownload
npm install
npm run build:d7pay
```

构建完成后页面标题为：

```text
D7pay Merchant
```

当前 D7pay APK 文件指向 arm64 瘦身包，避免超过 GitHub 普通单文件限制：

```text
public/files/android/d7pay/d7pay_merchant_universal_v0.1.8_202605031855.apk
```

该 APK 必须满足：

```text
package: name='com.d7pay.merchant'
application-label:'D7pay Merchant'
```

如果后续 `appInfo.json` 中 `d7pay_merchant.path` 为空，页面会显示 `APK Pending`，避免把旧 APK 误交付成 D7pay APK。

下载页 D7pay 模式使用独立 logo：

```text
src/assets/logo/d7pay-logo-192x192.png
public/d7pay-logo-192x192.png
```

D7pay 分支不再保留旧 Ashrafi/Lakshmi APK 文件。`apkdownload/public/files/android/appInfo.json` 不允许出现 `ashrafi_merchant` 或 `lakshmi` 下载项，`public/files/android/ashrafi/`、`public/files/android/lakshmi/` 不应重新提交 APK。

## 线上发布

服务器脚本：

```bash
ssh root@34.92.65.29
/opt/cicd/k8s/sh/deploy-apkdownload.sh
```

如果脚本里的 `kubectl` 因未带 kubeconfig 被拦截，继续执行：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/apkdownload/k8s/apkdownload-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/apkdownload-deploy -n pk --timeout=180s
```

## 访问验收

```bash
curl -I https://apkdownload.d7pay.net/files/android/d7pay/d7pay_merchant_universal_v0.1.8_202605031855.apk
curl -s https://apkdownload.d7pay.net/files/android/appInfo.json
```
