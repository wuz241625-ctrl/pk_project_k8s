# Merchant H5 排错文档

## `/prod-api/login/singin` 返回 404

现象：

- 浏览器请求 `merchant.awekay.com/prod-api/login/singin`
- `merchant` 后端日志记录的是 `/prod-api/login/singin`
- 返回 404

根因：

- `merchant-h5` ConfigMap 里 `proxy_pass http://merchant:8000;` 缺少尾部 `/`
- Nginx 不会剥离 `/prod-api/` 前缀

处理：

```nginx
location /prod-api/ {
    proxy_pass http://merchant:8000/;
}
```

## Merchant 白名单看到 Pod 内网 IP

现象：

- `merchant-h5` access log 里来源是 `10.244.x.x`
- `merchant` 后端白名单拒绝也显示 `10.244.x.x`

根因：

- 宿主机 Nginx 没有传真实客户端 IP
- `merchant-h5` ConfigMap 中的 Nginx 把 `X-Real-IP` 覆盖成 `$remote_addr`

处理：

1. 宿主机 Nginx server 中设置：

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header CF-Connecting-IP "";
```

2. `merchant-h5` ConfigMap 中设置：

```nginx
proxy_set_header X-Real-IP $http_x_real_ip;
proxy_set_header X-Forwarded-For $http_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
proxy_set_header CF-Connecting-IP "";
```

3. 应用 ConfigMap 并重启 Pod：

```bash
kubectl apply -f /opt/cicd/k8s/merchant-h5/k8s/merchant-h5-cm.yaml
kubectl rollout restart deployment/merchant-h5-deploy -n pk
```
