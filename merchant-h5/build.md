# Merchant H5 构建文档

## 本地构建

```bash
cd /Users/tear/pk_project_k8s/merchant-h5
npm install
npm run build:prod
```

## K8s 发布

线上发布脚本位于服务器：

```bash
/opt/cicd/k8s/sh/deploy-merchant-h5.sh
```

`merchant-h5` 的 Nginx 配置来自 K8s ConfigMap：

```bash
/opt/cicd/k8s/merchant-h5/k8s/merchant-h5-cm.yaml
kubectl apply -f /opt/cicd/k8s/merchant-h5/k8s/merchant-h5-cm.yaml
kubectl rollout restart deployment/merchant-h5-deploy -n pk
kubectl rollout status deployment/merchant-h5-deploy -n pk --timeout=180s
```

## 真实客户端 IP 代理要求

`/prod-api/` 反代必须剥离 `/prod-api/` 并透传宿主机 Nginx 已清洗的真实 IP 请求头：

```nginx
location /prod-api/ {
    proxy_pass http://merchant:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $http_x_real_ip;
    proxy_set_header X-Forwarded-For $http_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    proxy_set_header CF-Connecting-IP "";
}
```
