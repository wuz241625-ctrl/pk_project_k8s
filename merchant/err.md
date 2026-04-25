# Merchant 排错文档

## 常见问题

### 0.3 MySQL Service 误挂空库导致登录或业务查询间歇异常

现象：

- 同一套线上配置下，admin/api/merchant 偶发查不到数据库数据
- admin 登录可能间歇性提示 `账号密码错误`
- Redis 共享缓存可能被写入空对象

根因：

- `mysql` Service 原 selector 为 `app=mysql`
- `mysql` StatefulSet 原配置为 `replicas: 2`
- `mysql-0` 有生产数据，`mysql-1` 是空库，且没有主从复制
- 服务连接池随机连到 `mysql-1` 时，会读到空数据

处理：

```yaml
# /opt/cicd/k8s/db-yaml/mysql-svc.yaml
selector:
  app: mysql
  statefulset.kubernetes.io/pod-name: mysql-0

# /opt/cicd/k8s/db-yaml/mysql.yaml
replicas: 1
```

应用并重启依赖 MySQL 的服务：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/db-yaml/mysql-svc.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/db-yaml/mysql.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout restart deployment/admin-deploy deployment/api-deploy deployment/merchant-deploy -n pk
```

验证：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get endpoints mysql -n pk -o wide
```

`mysql` endpoint 必须只剩 `mysql-0`。

### 0.2 Merchant 线上意外按 DEV 配置启动

现象：

- Deployment 里没有 `RUN_ENV`
- `config.get_config()` 默认读取 `DEV`
- 线上商户后台可能使用 DEV 配置里的 `api_url`、cookie key、token key 等

处理：

1. `/opt/cicd/k8s/merchant/k8s/merchant-deployment.yaml` 的容器环境变量显式增加：

```yaml
- name: RUN_ENV
  value: "PROD"
```

2. 应用并等待滚动：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/merchant/k8s/merchant-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/merchant-deploy -n pk --timeout=180s
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/merchant-deploy -- printenv RUN_ENV
```

### 0.1 Merchant 登录白名单看到 `10.244.x.x` 或 `/prod-api/login/singin` 返回 404

现象：

- 用户从 `merchant.awekay.com` 登录商户后台
- 后端日志中的客户端 IP 是 `10.244.x.x`
- 某些请求进入后端时 URI 仍是 `/prod-api/login/singin`，导致 404

根因：

- 宿主机 Nginx 没有重设 `X-Real-IP` / `X-Forwarded-For`
- `merchant-h5` Pod 内 Nginx 把 `X-Real-IP` 覆盖成 Pod 侧 `$remote_addr`
- `merchant-h5` ConfigMap 里 `proxy_pass http://merchant:8000;` 缺少尾部 `/`，不会剥离 `/prod-api/`

处理：

1. `merchant/application/client_ip.py` 统一解析真实客户端 IP：
   - 只在直接来源是内网/本机可信代理时读取代理头
   - 从 `X-Forwarded-For` / `X-Real-IP` 里优先取公网地址
   - 不再把客户端传入的 `CF-Connecting-IP` 作为白名单依据
2. `merchant/application/base.py` 改用统一解析函数
3. 宿主机 Nginx 入口重设并清洗请求头：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header CF-Connecting-IP "";
```

4. `merchant-h5` ConfigMap 的 `/prod-api/` 反代改为：

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

验证：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest merchant.tests.test_client_ip -v

curl -s -o /tmp/merchant_ip.out -w '%{http_code}\n' \
  -H 'Host: merchant.awekay.com' \
  -H 'CF-Connecting-IP: 8.8.8.8' \
  -H 'Content-Type: application/json' \
  --data '{"username":"debug","password":"debug","googlecode":"debug"}' \
  http://127.0.0.1/prod-api/login/singin

kubectl logs -n pk deploy/merchant-deploy --since=2m --tail=80
```

验收：

- `/prod-api/login/singin` 不再以原路径透传到 merchant 后端
- 白名单拒绝时显示真实公网 IP，不再显示 `10.244.x.x`
- 伪造 `CF-Connecting-IP` 不会影响白名单判断

### 1. Merchant 启动成功但接口返回空数据

最常见原因是本地数据库没有导入种子数据，导致商户、订单和通道配置为空。

### 2. API 依赖不通

`merchant` 的很多流程要透传到 API，先验证：

```bash
curl -I http://127.0.0.1:9000
```

## 2026-03-17 商户后台按商户单号查代收订单返回 500

现象：

- 商户后台登录后，请求 `/order/getorderds`
- 当筛选条件只传 `merchant_code`，不传平台订单号 `code`
- 页面返回 `500 Internal Server Error`

日志：

```text
KeyError: 'code'
File "/workspace/merchant/application/order/order.py", line 38, in post
if not condition or not condition['code'] and not between:
```

原因：

- [order.py](/Users/tear/pk_project/merchant/application/order/order.py) 默认假设筛选条件里一定有 `code`
- 实际前端支持按 `merchant_code` 查询
- 只传 `merchant_code` 时，后端直接读取 `condition['code']` 会抛 `KeyError`

处理：

- 在 [order.py](/Users/tear/pk_project/merchant/application/order/order.py) 抽出 `should_use_default_order_range()`
- 代收与代付订单查询改成安全判断：
  - 有 `code` 或 `merchant_code` 任一标识时，不再错误套默认时间范围
  - 不再直接访问 `condition['code']`
- 在 [count.py](/Users/tear/pk_project/merchant/application/count/count.py) 和提现查询里也同步改成 `condition.get('code')`
- 新增回归测试：
  - [test_order_query_helpers.py](/Users/tear/pk_project/merchant/tests/test_order_query_helpers.py)

验证：

```bash
python3 -m unittest merchant.tests.test_order_query_helpers -v
python3 - <<'PY'
import pyotp, requests
base = 'http://localhost:8082/prod-api'
s = requests.Session()
code = pyotp.TOTP('NVRCYNS6E7LMH7BWXK3YFRJL4UYWZLTN').now()
print(s.post(base + '/login/singin', json={
    'username': '1234567889',
    'password': '123456',
    'googlecode': code,
}).text)
print(s.post(base + '/order/getorderds', json={
    'serchData': {'merchant_code': 'M177372338517417200'},
    'size': 10,
    'page': 1,
}).text)
PY
```

结果：

- 单测通过
- 商户后台可按 `merchant_code` 正常查到订单
- 不再出现 `KeyError: 'code'`
