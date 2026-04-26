# Admin 排错文档

## 常见问题

### 0.7 Admin 登录间歇性提示账号密码错误，或 `sys_info` 缓存变成 `{}`

现象：

- 同一个账号、同一个密码，有时返回 `账号密码错误`
- 正确密码配错误 Google 码时，本应稳定返回 `谷歌验证码错误`，但会间歇性返回 `账号密码错误`
- Redis 里的 `cache_info_sys_info_1` 曾被写成 `{}`

根因：

- 线上 `mysql` Service selector 只按 `app=mysql` 选择后端
- `mysql` StatefulSet 被配置为 `replicas: 2`
- 两个 MySQL Pod 没有主从复制：
  - `mysql-0` 有生产数据
  - `mysql-1` 是空库
- admin 连接池通过 `mysql` Service 建连接时会随机连到 `mysql-0` 或 `mysql-1`
- 连到 `mysql-1` 时，管理员账号查不到，所以登录被返回为 `账号密码错误`
- 连到 `mysql-1` 时查询 `sys_info where id=1` 也查不到，旧缓存逻辑会把 `{}` 写入 Redis，后续触发 `KeyError: 'sys_ip_w'`

处理：

1. 将线上 `/opt/cicd/k8s/db-yaml/mysql-svc.yaml` 收敛到唯一有数据的 `mysql-0`：

```yaml
selector:
  app: mysql
  statefulset.kubernetes.io/pod-name: mysql-0
```

2. 将线上 `/opt/cicd/k8s/db-yaml/mysql.yaml` 收敛为单副本：

```yaml
replicas: 1
```

3. 应用并重启依赖 MySQL 的连接池：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/db-yaml/mysql-svc.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/db-yaml/mysql.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout restart deployment/admin-deploy deployment/api-deploy deployment/merchant-deploy -n pk
```

验证：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get endpoints mysql -n pk -o wide
```

期望只有：

```text
10.244.1.49:3306
```

并用 admin Pod 连续读 `mysql` Service，必须全部返回 `mysql-0` 且 `admin` 表有数据。

### 0.6 Admin 登录 500，日志 `KeyError: 'sys_ip_w'`

现象：

- `POST /prod-api/login/singin` 返回 500
- admin 后端日志出现：
  - `KeyError: 'sys_ip_w'`
  - 请求 IP 已经是真实公网 IP，例如 `103.135.100.192`

根因：

- Redis 共享缓存 `cache_info_sys_info_1` 被写成 `{}` 这类缺字段脏数据
- `get_cache_result('sys_info', ['sys_ip_w'], {'id': 1})` 旧逻辑只要缓存 key 存在就直接使用，没有校验请求字段是否齐全

处理：

1. 先清理坏缓存，让线上立即恢复：

```bash
REDIS_POD=$(KUBECONFIG=/etc/kubernetes/admin.conf kubectl get pods -n pk -l app=redis -o jsonpath='{.items[0].metadata.name}')
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk "$REDIS_POD" -- redis-cli DEL cache_info_sys_info_1
```

2. 代码层修复 `get_cache_result()`：
   - 缓存存在但缺少本次请求字段时，丢弃缓存并回源数据库刷新
   - 避免 `{}` 再次导致登录前置白名单检查 500

验证：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest admin.tests.test_cache_result -v
```

### 0.5 Admin 线上意外按 DEV 配置启动

现象：

- Deployment 里没有 `RUN_ENV`
- `config.get_config()` 默认读取 `DEV`
- 线上服务可能使用 DEV 配置里的 `api_url`、cookie key、token key 等

处理：

1. `/opt/cicd/k8s/admin/k8s/admin-deployment.yaml` 的容器环境变量显式增加：

```yaml
- name: RUN_ENV
  value: "PROD"
```

2. 应用并等待滚动：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/admin/k8s/admin-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/admin-deploy -n pk --timeout=180s
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/admin-deploy -- printenv RUN_ENV
```

### 0.4 Admin 登录白名单看到 `10.244.x.x`

现象：

- 用户从 `admin.awekay.com` 登录后台
- 宿主机 Nginx access log 里是真实公网 IP
- `admin` 后端 403 日志里显示 `ip:10.244.x.x 禁止登录`

根因：

- 宿主机 Nginx 只做 `proxy_pass`，没有重设真实客户端 IP 请求头
- `admin-h5` Pod 内 Nginx 把 `X-Real-IP` 覆盖成自己的 `$remote_addr`
- 后端旧逻辑优先信任 `CF-Connecting-IP`，否则回落 `request.remote_ip`，最终白名单拿到 Pod/CNI 内网地址

处理：

1. `admin/application/client_ip.py` 统一解析真实客户端 IP：
   - 只在直接来源是内网/本机可信代理时读取代理头
   - 从 `X-Forwarded-For` / `X-Real-IP` 里优先取公网地址
   - 不再把客户端传入的 `CF-Connecting-IP` 作为白名单依据
2. `admin/application/base.py` 改用统一解析函数
3. 登录请求日志通过 `sanitize_request_body()` 脱敏 `password` / `googlecode`
4. 入口 Nginx 需要清洗并重设请求头：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header CF-Connecting-IP "";
```

5. `admin-h5` ConfigMap 中 `/prod-api/` 反代继续透传入口 Nginx 传来的头，不再覆盖成 Pod 地址：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $http_x_real_ip;
proxy_set_header X-Forwarded-For $http_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
proxy_set_header CF-Connecting-IP "";
```

验证：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest admin.tests.test_client_ip -v

curl -s -o /tmp/admin_ip.out -w '%{http_code}\n' \
  -H 'Host: admin.awekay.com' \
  -H 'CF-Connecting-IP: 8.8.8.8' \
  -H 'Content-Type: application/json' \
  --data '{"username":"debug","password":"debug","googlecode":"debug"}' \
  http://127.0.0.1/prod-api/login/singin

kubectl logs -n pk deploy/admin-deploy --since=2m --tail=80
```

验收：

- 后端 403 日志里的 IP 是真实公网 IP 或入口 Nginx 的 `$remote_addr`
- 日志不再出现明文 `password` / `googlecode`
- 伪造 `CF-Connecting-IP` 不会影响白名单判断

### 0.3 admin 已有 EasyPaisa runtime 代码，但线上还是旧 helper

现象：

- 本地 `admin` 的 EasyPaisa runtime 读写已经收口
- 但线上页面仍可能表现得像旧版本
- reset、在线态展示、`payment_active_1001` 对齐结果会和本地预期不一致

这轮线上实测结论：

- 真正不同步的不是 `partner.py` / `auto_payout.py`
- 而是：
  - `admin/application/easypaisa_runtime/service.py`
  - `admin/application/easypaisa_runtime/keyspace.py`

处理：

1. 只白名单同步这两个文件
2. 不覆盖 `admin/config.py`
3. 远端先跑：
   - `python -m py_compile application/easypaisa_runtime/keyspace.py application/easypaisa_runtime/service.py application/easypaisa_runtime/reader.py`
4. 再执行：
   - `ops admin restart`

fresh 验证：

- 远端 `sha256`
  - `service.py = fce561d7382d338c60b30c53f526ead9dd2cdda5de067d4704016935d13fcc25`
  - `keyspace.py = a17722d014fd72d31510d454906d37d165cd232eabff609d035139ff3286a661`
- `admin` 进程数：`15`
- `http://127.0.0.1:6000/`：`404`

结论：

- 以后遇到 admin EasyPaisa 展示口径不对，先查线上这两个 runtime helper 文件哈希
- 不要先把问题归因到前端或 `partner.py`

### 0.2 Admin 点了 EasyPaisa reset，但 `payment_active_1001` 还残留

现象：

- admin 已执行 `resettingPayment`
- runtime snapshot 已变成 offline
- 但 Redis 里仍残留：
  - `payment_online_ds`
  - `payment_active_1001`

根因：

- `admin/application/easypaisa_runtime/service.py`
  之前只清：
  - `payment_online_df`
  - `payment_active_df`
  - `login_on_easypaisa_*`
- 没有按 EasyPaisa runtime snapshot 的 `channels` 清：
  - `payment_online_ds`
  - `payment_active_{channel}`

处理：

1. `admin/application/easypaisa_runtime/keyspace.py`
   - 补齐：
     - `LEGACY_PAYMENT_ONLINE_DS`
     - `normalize_channels(...)`
     - `legacy_payment_active_channel_key(...)`
2. `EasyPaisaAdminRuntimeService.force_offline()`
   - 读取 snapshot `channels`
   - reset/offline 时一并清理 DS/channel 投影

验证：

```bash
cd /Users/tear/pk_project
python3.12 -m unittest discover -s admin/tests -p 'test_easypaisa_runtime_reader.py' -v
```

结果：

- `Ran 7 tests`
- `OK`

结论：

- admin reset 现在不仅会清 EasyPaisa 代付 legacy 状态
- 也会同步清掉 `payment_online_ds` 与 `payment_active_{channel}`

### 0.1 Admin 看到的 EasyPaisa 在线态，不能从新锁键反推

现象：

- Redis 里可能只剩：
  - `easypaisa_runtime:lock:payment:<payment_id>`
- 但 admin 页面不应该因此把账号展示成在线

根因：

- `easypaisa_runtime:lock:*` 是重复登录锁，不是在线投影
- admin 的 EasyPaisa 在线态只应来自：
  - runtime snapshot
  - 或 legacy `login_on_easypaisa_*` 兜底

处理：

- `admin/application/easypaisa_runtime/reader.py`
  不读取 `easypaisa_runtime:lock:*`
- `admin/application/easypaisa_runtime/service.py`
  在 `force_reset()` / `force_offline()` 时同步清新锁
- `admin/application/easypaisa_runtime/keyspace.py`
  补齐新锁 helper，避免 admin/api 漂移

结论：

- admin 上“在线”与否，不再允许通过新锁键猜测
- 新锁只服务于登录防重，不服务于展示口径

### 0. EasyPaisa 管理端看起来“不一致”，但根因在 API jobs 旧状态

现象：

- `admin` 页面看到的 EasyPaisa 在线态与预期不一致
- 容易误以为是 `partner.py` / `auto_payout.py` 没有更新

这次线上实测结论：

- `admin` 目标文件同步后，远端哈希已与本地一致
- 真正导致状态漂移的是 `api` 侧 Redis 旧状态回流：
  - `hash_easypaisa`
  - `set_easypaisa`
  - `easypaisa_runtime:index:*`

排查顺序：

1. 先看 `api` runtime 是否已收敛
2. 再看 `admin` 是否还是旧代码

不要反过来先怀疑 `admin` 展示逻辑。

### 1. Admin 能启动，但请求失败

优先检查：

- `ADMIN_API_URL` 是否指向可达的 API 服务
- MySQL / Redis 是否可用

### 2. 登录和权限相关异常

`admin` 强依赖数据库中的管理员、角色和权限数据。若本地没有导入种子数据，很多接口虽然能启动，但不会有可用账号。

### 3. 管理端 `otherpay` 下拉只能看到名字

现象：

- 多个 Easypay 账号都叫 `easypay`
- 运营在商户配置和通道一键全切里无法判断自己选中了哪一个

处理后行为：

- 下拉改为显示 `name | merchant_id | key3 | #id`
- 保存时仍提交 `id`

若要回归验证，运行：

```bash
cd /Users/tear/pk_project/frontend_src/admin
VUE_APP_SYSTEM=OSPay VUE_APP_BASE_API=/prod-api npm run test:unit -- --runInBand tests/unit/utils/otherpay.spec.js
```

注意：

- 这个前端测试依赖 `VUE_APP_SYSTEM`
- 若未设置，会在 `vue.config.js` 阶段报 `toLocaleLowerCase` 空指针

## 2026-04-19 EasyPaisa admin runtime 读取与重置闭环

### 现象

- `partner.py` 里 EasyPaisa 仍直接读取：
  - `login_on_easypaisa_*`
  - `payment_online_df`
- `resettingPayment` 只清 legacy 集合，不清 EasyPaisa runtime session / snapshot
- `admin/application/order/auto_payout.py` 用 `scard("payment_active_df")` 统计活跃账号，但这个 key 实际上是 list

### 根因

- `admin` 还没有自己的 EasyPaisa runtime helper
- API / jobs 已经把 EasyPaisa 主状态切到 runtime snapshot，但 admin 展示和重置入口还停在旧 Redis 语义

### 处理

1. 新增：
   - [reader.py](/Users/tear/pk_project/admin/application/easypaisa_runtime/reader.py)
   - [service.py](/Users/tear/pk_project/admin/application/easypaisa_runtime/service.py)
2. `partner.py`：
   - EasyPaisa `online_status` / `online_df` 改读 runtime snapshot
   - 非 EasyPaisa 继续保持 legacy 逻辑
3. `resettingPayment`：
   - 保留原来的 `login_off_realtime_*` 和 legacy 集合清理
   - EasyPaisa 额外补 `force_reset(...)`，同步清 session 和 snapshot 在线态
4. `auto_payout.py`：
   - `online_accounts` 改读 `easypaisa_runtime:index:online`
   - `active_accounts` 改为 list 语义读取

### 验证

```bash
cd /Users/tear/pk_project/admin
python3.12 -m py_compile application/easypaisa_runtime/*.py application/partner/partner.py application/order/auto_payout.py
python3.12 -m unittest discover -s tests -v
```

结果：

- `py_compile`：通过
- `unittest`：`38 tests` 全部通过

### 结论

- EasyPaisa 在 `admin` 里的展示面已经与 runtime snapshot 对齐
- 管理端重置下线不再留下 EasyPaisa runtime 脏会话
- 自动代付监控页不再错误把 `payment_active_df` 当 set 统计
## 2026-04-26 JazzCashBusiness admin 被 legacy Redis 脏数据误导

### 现象

JazzCashBusiness 旧链路会残留：

- `payment_online_ds`
- `payment_online_df`
- `payment_active_df`
- `payment_active_{channel}`
- `login_on_jazzcash_*`

admin 收款资料列表、在线筛选、手动监控开关和重置下线如果直接读写这些 key，就会和 API 派单状态不一致。

### 根因

admin 侧只有 EasyPaisa runtime reader/service，JazzCashBusiness 仍走 legacy Redis 判断，没有唯一真相源。

### 处理

- 新增 `admin/application/jazzcash_runtime`：
  - `reader.py`
  - `service.py`
  - `keyspace.py`
  - `flags.py`
- `application/partner/partner.py` 新增：
  - `is_jazzcash_payment()`
  - `apply_jazzcash_runtime_fields()`
- 收款资料列表和筛选对 JazzCashBusiness 改读 runtime snapshot/index。
- 手动监控开关和重置下线改走 `JazzCashAdminRuntimeService`。

### 排错口径

- snapshot 缺失时，JazzCashBusiness 在 admin 读面默认离线，不能信任 legacy。
- 需要看真实状态时先查：
  - `jazzcash_runtime:snapshot:{payment_id}`
  - `jazzcash_runtime:index:online`
  - `jazzcash_runtime:index:ds_order_enabled`
  - `jazzcash_runtime:index:df_order_enabled`
- legacy `payment_online_*` 只能用于判断 bridge 投影是否同步，不能作为业务结论。

### 本轮验证

```bash
PYTHONPATH=admin python3.12 -m unittest admin.tests.test_jazzcash_runtime_reader -v
python3.12 -m py_compile admin/application/jazzcash_runtime/*.py admin/application/partner/partner.py
```
