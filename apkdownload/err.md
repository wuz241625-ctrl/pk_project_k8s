# apkdownload 排错文档

## 2026-04-26 发布脚本 kubectl 未带 kubeconfig

### 现象

`/opt/cicd/k8s/sh/deploy-apkdownload.sh` 在镜像构建、推送后执行 `kubectl apply`，返回登录页 HTML 和 `Authentication required`。

### 根因

服务器默认 `kubectl` 上下文不是 `/etc/kubernetes/admin.conf`。脚本未显式设置 `KUBECONFIG`。

### 处理

镜像和 YAML 已经生成时，不需要重建，直接补执行：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/apkdownload/k8s/apkdownload-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/apkdownload-deploy -n pk --timeout=180s
```

### 验收

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get deploy apkdownload-deploy -n pk -o wide
curl -I http://apkdownload.awekay.com/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk
```
