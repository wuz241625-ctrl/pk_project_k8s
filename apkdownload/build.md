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

当前 Ashrafi App 使用 `ashrafi_merchant` 配置键，实际文件指向：

```text
public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk
```

下载页展示名与 Flutter Android 包保持一致：

```text
Ashrafi Merchant
```

下载页 favicon 与页面 logo 使用 Flutter Android launcher icon：

```text
/Users/tear/pk_project/ashrafi_merchant_flutter/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png
```

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
curl -I http://apkdownload.awekay.com/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk
curl -s http://apkdownload.awekay.com/files/android/appInfo.json
```
