# Admin H5 排错文档

## Admin 白名单看到 Pod 内网 IP

现象：

- `admin-h5` access log 里来源是 `10.244.x.x`
- `admin` 后端白名单拒绝也显示 `10.244.x.x`

根因：

- 宿主机 Nginx 没有传真实客户端 IP
- `admin-h5` ConfigMap 中的 Nginx 把 `X-Real-IP` 覆盖成 `$remote_addr`

处理：

1. 宿主机 Nginx server 中设置：

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header CF-Connecting-IP "";
```

2. `admin-h5` ConfigMap 中设置：

```nginx
proxy_set_header X-Real-IP $http_x_real_ip;
proxy_set_header X-Forwarded-For $http_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
proxy_set_header CF-Connecting-IP "";
```

3. 应用 ConfigMap 并重启 Pod：

```bash
kubectl apply -f /opt/cicd/k8s/admin-h5/k8s/admin-h5-cm.yaml
kubectl rollout restart deployment/admin-h5-deploy -n pk
```
