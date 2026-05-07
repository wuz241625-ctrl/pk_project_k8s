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
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get deploy apkdownload-deploy -n pk-d7pay -o wide
curl -I https://apkdownload.d7pay.net/files/android/d7pay/d7pay_merchant_universal_v0.1.8_202605031855.apk
```

## 2026-05-07 D7pay 下载页混入旧客户 APK

### 现象

D7pay 分支中出现：

```text
apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk
apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk
apkdownload/src/components/Appdownload/index.vue 中 fallback 指向旧客户 key
```

### 根因

历史下载站同时服务多个 App，D7pay 租户分支继承了旧 APK 制品和旧兜底配置，存在误交付给客户或暴露旧客户品牌的风险。

### 处理

删除旧 Ashrafi/Lakshmi APK。D7pay 下载站只允许保留 `d7pay_merchant` 元信息和 D7pay APK 路径；默认 app key 与 fallback app key 都必须指向 `d7pay_merchant`。

### 验收

```bash
test -z "$(git ls-files apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk)"
test "$(python3 - <<'PY'
import json
data = json.load(open("apkdownload/public/files/android/appInfo.json", encoding="utf-8"))
print(",".join(data.keys()))
PY
)" = "d7pay_merchant"
rg -n '"lakshmi"|ashrafi_merchant|lakshmi_v1.0.0|ashrafi_v0.1.6' apkdownload/public/files/android/appInfo.json apkdownload/src
```
