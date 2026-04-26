# Admin H5 排错文档

## JCB 代付 `500` 待核查在后台如何展示

现象：

- JazzCashBusiness 代付上游 `transferToAcc` / `transferToCard` 返回 `code=500`
- 按 v1.6 文档这不是最终失败，需要人工或账单核查

展示口径：

- `orders_df.status=2` 在代付列表显示为“待确认”
- `orders_df.sys_remark` 在代付列表“备注”列显示待核查原因
- 自动代付详情里的操作日志状态为 `pending_reconciliation`

排查：

```bash
curl 'http://admin.awekay.com/prod-api/order/getorderds' \
  -H 'Content-Type: application/json;charset=UTF-8' \
  --data-raw '{"serchData":{"status":2},"size":10,"page":1}'
```

期望返回数据中 `status=2`，并且 `sys_remark` 包含“待核查”。

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
