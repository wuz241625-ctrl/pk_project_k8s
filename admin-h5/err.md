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

## 全量 `npm run lint` 存量格式错误

现象：

- 在 `admin-h5` 执行 `VUE_APP_SYSTEM=d7pay npm run lint`
- ESLint 扫描整个 `src` 后失败，输出约 `16052 problems`
- 主要是历史文件缩进、分号、空行、属性换行等格式问题，例如 `src/App.vue`、`src/api/count.js`、`src/api/partner.js`、`src/views/system/operationLog/index.vue`

处理：

- 不在业务小改动中批量格式化整个 `src`，避免混入大规模无关 diff
- 针对本次新增或修改文件单独跑 ESLint
- 生产构建仍以 `npm run d7pay:prod` 验证

本次命令：

```bash
cd /Users/tear/pk_project_k8s/admin-h5
VUE_APP_SYSTEM=d7pay ./node_modules/.bin/eslint src/utils/partnerPassword.js
VUE_APP_SYSTEM=d7pay npm run test:unit -- tests/unit/utils/partnerPassword.spec.js --runInBand
npm run d7pay:prod
```
