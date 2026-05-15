# Admin H5 构建文档

## 本地构建

```bash
cd /Users/tear/pk_project_k8s/admin-h5
npm install
npm run build:prod
```

## D7pay 构建

D7pay 托管实例使用独立构建变量，不需要单独长期分支：

```bash
cd /Users/tear/pk_project_k8s/admin-h5
npm install
npm run d7pay:prod
```

银行流水废除/恢复前端变更可用 D7pay 构建验收：

```bash
cd /Users/tear/pk_project_k8s/admin-h5
npm run d7pay:prod
```

页面口径：

- `invalid != 1` 显示“废除”。
- `invalid = 1 且 callback != 1` 显示“↩️ 恢复”。
- 已回调流水不提供恢复入口。

构建产物输出到：

```text
dist/d7pay
```

D7pay 模式会启用侧边栏 logo，并使用：

```text
src/assets/brand/d7pay-logo-mark.png
public/d7pay-favicon.ico
```

默认构建不受 D7pay logo 影响。

## K8s 发布

线上发布脚本位于服务器：

```bash
/opt/cicd/k8s/sh/deploy-admin-h5.sh
```

D7pay 由 Jenkins 使用 `ADMIN_H5_BUILD_SCRIPT=d7pay:prod` 构建，并发布到 `pk-d7pay` namespace。配置入口见：

```text
ops/tenants/d7pay/jenkins.env.example
ops/tenants/d7pay/k8s/
```

`admin-h5` 的 Nginx 配置来自 K8s ConfigMap：

```bash
/opt/cicd/k8s/admin-h5/k8s/admin-h5-cm.yaml
kubectl apply -f /opt/cicd/k8s/admin-h5/k8s/admin-h5-cm.yaml
kubectl rollout restart deployment/admin-h5-deploy -n pk
kubectl rollout status deployment/admin-h5-deploy -n pk --timeout=180s
```

## 真实客户端 IP 代理要求

`/prod-api/` 反代必须透传宿主机 Nginx 已清洗的真实 IP 请求头：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $http_x_real_ip;
proxy_set_header X-Forwarded-For $http_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
proxy_set_header CF-Connecting-IP "";
```
