# API 排错文档

## 常见问题

### 0.18 JazzCashMerchant v1.6 `loginStep2` 和代付 `500` 语义误用

现象：

- JazzCashBusiness 指纹验证调用 `loginStep2` 时只传 `account_id`
- 代付 `transferToAcc` / `transferToCard` 返回 `code=500` 时被当成 `server_error`，外层继续给 `payment_id` 打失败冷却

根因：

1. v1.6 文档里的 `loginStep2` 同时支持 OTP 与指纹两个开关；当前业务需要“真实发送验证码，但 `verify_otp` 只推进到指纹流程”，所以 `loginStep2` 必须明确关闭 OTP 校验、开启指纹校验。
2. v1.6 文档对转账接口特别说明：`code=500` 是异常/未知结果，不能直接判定代付失败，必须后续查账或人工核查。

处理：

```json
{
  "account_id": "03xxxxxxxxx",
  "otpcode": "123456",
  "should_verify_otpcode": false,
  "should_verify_fingerprint": true
}
```

- [jazzcash.py](/Users/tear/pk_project_k8s/api/application/app/login/banks/jazzcash.py) 的 `verify_otp_http()` 保存用户提交的 `otpcode`
- [jazzcash.py](/Users/tear/pk_project_k8s/api/application/app/login/banks/jazzcash.py) 的 `_build_verify_fingerprint_request()` 使用上面 payload 调 `action=loginStep2`
- [jazzcash_auto_payout.py](/Users/tear/pk_project_k8s/api/jobs/jazzcash/jazzcash_auto_payout.py) 对代付 `code=500` 返回：
  - `pending_check=True`
  - 交易日志状态 `pending_reconciliation`
  - 外层订单置 `status=2` 待核查
  - `orders_df.sys_remark` 写入“待核查”原因，admin 代付列表备注列可见
  - 不调用 `set_payment_id_failed()`，不写失败冷却

验证：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest \
  api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_build_verify_fingerprint_request_uses_login_step2 \
  api.tests.test_jazzcash_auto_payout.JazzCashAutoPayoutV16Tests -v
```

### 0.17 MySQL Service 误挂空库导致共享缓存和业务查询异常

现象：

- API、admin、merchant 通过 `mysql` Service 访问数据库时，查询结果偶发为空
- Redis 共享缓存可能被空库查询结果污染，例如 `cache_info_sys_info_1` 被写成 `{}`
- admin 登录可能间歇性返回 `账号密码错误`

根因：

- `mysql` Service 原 selector 为 `app=mysql`
- `mysql` StatefulSet 原配置为 `replicas: 2`
- `mysql-0` 有生产数据，`mysql-1` 是空库，二者没有配置复制
- 业务服务连接池经 Service 建连时会随机落到空库 `mysql-1`

处理：

```yaml
# /opt/cicd/k8s/db-yaml/mysql-svc.yaml
selector:
  app: mysql
  statefulset.kubernetes.io/pod-name: mysql-0

# /opt/cicd/k8s/db-yaml/mysql.yaml
replicas: 1
```

应用后重启连接池：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/db-yaml/mysql-svc.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/db-yaml/mysql.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout restart deployment/admin-deploy deployment/api-deploy deployment/merchant-deploy -n pk
```

验证：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get endpoints mysql -n pk -o wide
```

`mysql` endpoint 必须只剩 `mysql-0` 的 Pod IP。

### 0.16 API 共享缓存缺字段导致 `get_cache_result()` 异常

现象：

- Redis 里的 `cache_info_sys_info_1` 变成 `{}` 或缺少调用方需要的字段
- API 读取 `sys_info` 的局部字段时可能抛 `KeyError`

根因：

- 旧 `get_cache_result()` 只判断缓存 key 是否存在
- 没有校验缓存里的字段是否覆盖本次 `keys`

处理：

- `api/application/base.py` 中 `get_cache_result()` 改为：
  - 缓存存在但缺字段时丢弃缓存
  - 回源数据库查询 `['*']`
  - 重新写入完整缓存

验证：

```bash
cd /Users/tear/pk_project_k8s
python3 -m py_compile api/application/base.py
```

### 0.15 API 线上意外按 DEV 配置启动

现象：

- Deployment 里没有 `RUN_ENV`
- `config.get_config()` 默认读取 `DEV`
- Lakshmi 路由、短信、WebSocket 推送等逻辑会出现 DEV/生产分支不一致

处理：

1. `/opt/cicd/k8s/api/k8s/api-deployment.yaml` 的容器环境变量显式增加：

```yaml
- name: RUN_ENV
  value: "PROD"
```

2. 应用并等待滚动：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/api/k8s/api-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/api-deploy -n pk --timeout=180s
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/api-deploy -- printenv RUN_ENV
```

### 0.14 API 白名单/黑名单看到内网 IP 或被伪造 `CF-Connecting-IP`

现象：

- `api` 的 `api_ip_b` 黑名单或三方回调白名单判断使用了 `10.244.x.x`、NodePort 内网地址等非真实客户端 IP
- 客户端手工带 `CF-Connecting-IP` 时，旧代码会直接把该值当成真实 IP
- `pay`、`thirdCallback`、`third_df`、Lakshmi 登录限频等所有调用 `get_ip()` 的链路都会受影响

根因：

1. 宿主机 Nginx 的 `api.awekay.com` 反代只做 `proxy_pass`，没有重设 `X-Real-IP` / `X-Forwarded-For`
2. `api-h5` Pod 内 Nginx 把 `X-Real-IP` 覆盖成 `$remote_addr`，容易变成上游内网地址
3. `api/application/base.py`、`application/lakshmi_api/base.py`、`application/lakshmi_api/base_ws.py` 旧逻辑优先信任 `CF-Connecting-IP`

处理：

1. 新增 `application/client_ip.py`
   - 只有直接来源是可信代理地址时才读取代理头
   - 从 `X-Forwarded-For` / `X-Real-IP` 优先取公网客户端 IP
   - 不再把客户端传入的 `CF-Connecting-IP` 作为白名单依据
2. `api` 三个 BaseHandler 的 `get_ip()` / `_get_ip()` 统一调用 `resolve_client_ip(...)`
3. 宿主机 Nginx 的 `api.awekay.com` 增加：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header CF-Connecting-IP "";
```

4. `api-h5` ConfigMap 的 `/api/` 反代改为：

```nginx
location /api/ {
  proxy_pass http://api:9000/;
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $http_x_real_ip;
  proxy_set_header X-Forwarded-For $http_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
  proxy_set_header CF-Connecting-IP "";
}
```

本地验证：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3 -m unittest api.tests.test_client_ip -v
python3 -m py_compile api/application/client_ip.py api/application/base.py api/application/lakshmi_api/base.py api/application/lakshmi_api/base_ws.py
```

验收点：

- 白名单/黑名单拒绝或通过时使用真实公网 IP，不再使用 `10.244.x.x`
- 伪造 `CF-Connecting-IP` 不会影响判断
- `/api/` 路径仍由 `api-h5` 正确剥离后转发到 `api:9000`

### 0.13 EasyPaisa 数据库里已经有 `account_iban`，但 runtime/hash 还是空

现象：

- 数据库里已经有：
  - `payment.id=533280`
  - `account_accno=93759505`
  - `account_iban=PK25TMFB0000000093759505`
- 但 Redis 里仍然看到：
  - `easypaisa_runtime:snapshot:533280.selected_iban = null`
  - `hash_easypaisa[533280].account_iban = ""`

根因：

1. `jobs/easypaisa/easypaisa_monitor.py`
   - `get_online_payments_from_db()` 旧 SQL 只查 `account_accno`
   - 没查 `account_iban`
2. monitor 循环里如果发现：
   - `hash_easypaisa` 已有
   - `set_easypaisa` 已有
   就会直接跳过
3. 所以旧的空 `account_iban` 会一直留在：
   - runtime snapshot
   - `hash_easypaisa`

处理：

1. `get_online_payments_from_db()` 补查 `account_iban`
2. 新增 `refresh_job_account_fields(payment_data)`
   - 对已存在 job 也会回填：
     - `account_accno`
     - `account_iban`
     - `qr_channel`
     - `channel`
3. monitor 在 `hash_exists && zset_exists` 分支不再裸跳过
   - 先刷新 job 字段，再继续保留调度状态

fresh 验证：

- `PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaMonitorRuntimeIntegrationTests -v`
  - `Ran 6 tests`
  - `OK`
- `PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_sync_runtime_service api.tests.easypaisa_runtime.test_runtime_service api.tests.test_easypaisa_collection_runtime_toggle -v`
  - `Ran 32 tests`
  - `OK`
- 线上 fresh：
  - `easypaisa_runtime:snapshot:533280.selected_iban = PK25TMFB0000000093759505`
  - `hash_easypaisa[533280].account_iban = PK25TMFB0000000093759505`
  - `payment_active_1001` 列表里包含 `533280`

结论：

- 这类问题不要先怀疑数据库
- 先看 monitor 的 DB 查询字段是否完整，以及已存在 job 的 hash 有没有刷新路径

### 0.12 EasyPaisa `dispatch_ds` 掉成 `false` 之后，账号恢复在线了也写不回来

现象：

- `payment.status=1`
- `payment.certified=1`
- runtime snapshot 里已经 `online=true`
- 但 `dispatch_ds=false` 一直保留
- 账号长期不在：
  - `easypaisa_runtime:index:dispatch_ds`
  - `payment_online_ds`
  - `payment_active_1001`

根因：

1. 旧链路里，`pakistanpay_v2.py` / `easypaisa_monitor.py` 都可能把账号打到 `set_kickoff()/force_offline()`
   - 这会把 `dispatch_ds` 真写成 `false`
2. 账号后续恢复在线时，`jobs/easypaisa/easypaisa_monitor.py` 会继续调用：
   - `mark_active_successful(...)`
3. 但 monitor 这条写面之前没有显式传 `dispatch_ds`
   - `mark_active_successful()` 会继承 snapshot 里的旧值
4. 结果就是：
   - 账号明明恢复健康了
   - monitor 仍把历史 `dispatch_ds=false` 一直保住

处理：

1. 在 `jobs/easypaisa/easypaisa_monitor.py` 增加统一 helper：
   - `should_enable_collection_dispatch(payment_id, payment_data=None)`
2. `update_redis_cache()` 在线分支
   - 显式传 `dispatch_ds=...`
3. `on_off(login_data, 1)`
   - 显式传 `dispatch_ds=...`
4. `sync_online_payment_runtime(payment_data)`
   - 显式传 `dispatch_ds=...`
5. 恢复条件只认数据库口径：
   - `payment.status=1 && payment.certified=1`
   - 这样不会把 app 主动 `selling_inactive` 的账号错误恢复

fresh 验证：

- `PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaMonitorRuntimeIntegrationTests -v`
  - `Ran 5 tests`
  - `OK`
- `PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_sync_runtime_service api.tests.easypaisa_runtime.test_runtime_service api.tests.test_easypaisa_collection_runtime_toggle -v`
  - `Ran 31 tests`
  - `OK`
- `python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py -q`
  - `31 passed, 1 warning`

结论：

- `423` 只是触发错误写成 `dispatch_ds=false` 的入口之一
- 真正的恢复缺口在 `easypaisa_monitor`
- 后续只要数据库仍允许接单，monitor 在线恢复就必须把 `dispatch_ds` 显式写回 `true`

### 0.11 EasyPaisa 明明还能登录成功，但突然从 `payment_active_1001` 被移除了

现象：

- `payment_status_http` 仍然显示 `activeSuccessful`
- 账号看起来在线
- 但 `payment_active_1001` 里突然没有这个账号了
- `selling_order_status` 也变成了 false

根因：

这不是单一 Redis 脏数据，而是三条写路径没有完全闭环：

1. `jobs/pakistanpay_v2.py`
   - `verify_and_handle_abnormal_payout()` 遇到 `423 云机正忙查单` 这类临时抓账异常时，之前会直接 `on_off(_on=0)`
   - 这会把账号从：
     - `payment_online_ds`
     - `payment_active_{channel}`
     一起清掉
2. `lakshmi_api/services/payments/e_wallet_handler.py`
   - `selling_active/selling_inactive` 之前只改 `payment.certified`
   - 不会同步 EasyPaisa runtime `dispatch_ds`
3. `admin/application/easypaisa_runtime/service.py`
   - `force_reset()` 之前只清代付 legacy 投影
   - 不会清 `payment_online_ds` / `payment_active_{channel}`

处理：

1. `EasyPaisaRuntimeService` 新增 `set_collection_dispatch(...)`
   - 专门负责同步 EasyPaisa `dispatch_ds`
   - 会一起维护：
     - `easypaisa_runtime:index:dispatch_ds`
     - `payment_online_ds`
     - `payment_active_{channel}`
2. app 端 `selling_active/selling_inactive`
   - 改为直接调用 `set_collection_dispatch(...)`
3. admin `force_reset()`
   - 改为按 snapshot `channels` 一起清理：
     - `payment_online_ds`
     - `payment_active_{channel}`
4. `pakistanpay_v2.py`
   - 对 `423 云机正忙查单` 改为临时失败，只保留失败标记和重试
   - 不再调用 `on_off(_on=0)`

fresh 验证：

- `PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_runtime_service api.tests.test_easypaisa_collection_runtime_toggle -v`
  - `Ran 10 tests`
  - `OK`
- `PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_sync_runtime_service -v`
  - `Ran 21 tests`
  - `OK`
- `python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py -q`
  - `31 passed, 1 warning`

结论：

- 以后排查 `payment_active_1001`，不能只看 list 结果
- 要同时看：
  - `easypaisa_runtime:snapshot:{payment_id}.dispatch_ds`
  - `easypaisa_runtime:index:dispatch_ds`
  - `payment_online_ds`
  - `payment_active_{channel}`
- 若日志里是 `423 云机正忙查单`，那属于临时异常，不应该再被解释成“账号被正常下线”

### 0.10 Admin 已点重置，但 EasyPaisa App 端仍提示已登录/不能重新登录

现象：

- Admin 对 EasyPaisa 账号点了 `resettingPayment`
- `pre_login_easypaisa_*`、`login_on_easypaisa_*`、`kick_off_*` 这类旧锁已经没了
- 但 App 端重新登录时仍然会报重复登录，或者表现为“怎么重置都登不上”

本轮实证：

- `533281 / 03489696378`
  - `2026-04-19 18:49:07` 已命中 `/partner/resettingPayment`
  - 但 `easypaisa_runtime:session:533281` 仍然存在，且 `status=activeSuccessful`
  - 该 session 的 `login_time=2026-04-19 18:49:47`
  - 说明它不是 reset 前遗留，而是 reset 后又被重新写回
- `533283 / 03218629016`
  - 当天只有 `updatePaymentEnable / updatePaymentDisenable / updatePaymentLock`
  - 没有命中 `resettingPayment`
  - `easypaisa_runtime:session:533283` 也仍然残留为 `activeSuccessful`

根因：

1. `api/application/app/login/banks/easypaisa.py`
   - `_get_session_data()` 在 `pre_login_easypaisa_{payment_id}` 不存在时，会继续 fallback 读取：
     - `easypaisa_runtime:session:{payment_id}`
2. `pre_login_http()`
   - 只要读到 `activeSuccessful`，就直接抛：
     - `ErrorCode.Logined2`
3. 同一个文件里的 `_check_payment()`
   - 通过 `bank_type + phone` 找历史 payment 时，不区分该 payment 当前是否已经 offline
4. 结果就是：
   - runtime snapshot 明明已经是 `session_phase=offline`
   - 但只要残留 `activeSuccessful` session 没清掉
   - App 重新登录仍会被当成重复登录拒绝

处理：

1. 在 `pre_login_http()` 增加 stale session 兜底
   - 当检测到：
     - `existing_session.status == activeSuccessful`
     - 且 runtime snapshot 已经 `offline`
   - 自动清理：
     - `easypaisa_runtime:session:{payment_id}`
     - `pre_login_easypaisa_{payment_id}`
     - `login_on_easypaisa_{payment_id}`
     - `login_on_easypaisa_{phone}`
   - 然后允许重新登录
2. 新增回归测试：
   - `test_pre_login_clears_stale_runtime_session_when_snapshot_offline`

fresh 验证：

- `python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py -k stale_runtime_session_when_snapshot_offline -q`
  - `1 passed`
- `python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py tests/test_app_my_easypaisa_runtime.py -q`
  - `34 passed`
- `python3.12 -m py_compile application/app/login/banks/easypaisa.py tests/test_easypaisa_business_flow_v2.py`

结论：

- EasyPaisa 重新登录不能只清旧 `pre_login_*` / `login_on_*`
- 还必须把 `runtime snapshot` 和 `runtime session` 视为一组状态一起判断
- 对已经 `offline` 的 runtime snapshot，残留的 `activeSuccessful` session 必须视为脏数据，而不是有效在线态

### 0.9 EasyPaisa `dispatch_ds` 已经是 `true`，但还是没进 `payment_active_1001`

现象：

- 类似 `533282` 这种账号，runtime snapshot 已经显示：
  - `online=true`
  - `dispatch_ds=true`
- `payment_online_ds` 里也有它
- 但 `payment_active_1001` 里没有它，所以代收分单仍然会跳过

同一类漂移的反向表现：

- 类似 `533283` 这种账号，runtime snapshot 已经是：
  - `dispatch_ds=false`
- 却仍然残留在 `payment_active_1001`

根因：

- 之前 EasyPaisa runtime service / legacy bridge 只维护了：
  - `payment_online_ds`
  - `payment_online_df`
  - `payment_active_df`
  - `login_on_easypaisa_*`
- 没把 `payment_active_{channel}` 当成 runtime 派生投影的一部分
- 于是系统出现了两套真相：
  - runtime `dispatch_ds`
  - 分单实际读取的 `payment_active_{channel}`

处理：

1. `easypaisa_runtime:snapshot:*` 新增/固定 `channels`
   - 统一保存 EasyPaisa 应投影的 channel 列表
2. `application/easypaisa_runtime/legacy_bridge.py`
   - `dispatch_ds=true` 时：
     - 同步写 `payment_online_ds`
     - 同步写 `payment_active_{channel}`
   - `dispatch_ds=false` / offline 时：
     - 一起清 `payment_online_ds`
     - 一起清 `payment_active_{channel}`
3. `runtime_service.py` / `sync_runtime_service.py`
   - `mark_active_successful()` 会保留已有 `channels`
   - `force_offline()` 会按 `channels` 清理 channel 队列
4. `easypaisa.py` / `pakistanpay_v2.py` / `easypaisa_monitor.py`
   - 调 runtime service 时同步带上 `channel` / `qr_channel`
5. `/user/upi`
   - 补上 `_collection_online_payment_ids()`，把 runtime `dispatch_ds` 也纳入 EasyPaisa 在线集合聚合

fresh 验证：

- `python3.12 -m pytest tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/easypaisa_runtime/test_reader.py tests/test_easypaisa_business_flow_v2.py -q`
- `62 passed`

结论：

- 以后判断 EasyPaisa 能不能参与代收分单，不能只看 `payment_online_ds`
- 必须保证这三层同时一致：
  - `snapshot.dispatch_ds`
  - `payment_online_ds`
  - `payment_active_{channel}`

### 0.8 `api.aweces.com` 看起来有 `/api/` 配置，但实际没挂到 API

现象：

- 线上文件名叫 `api.aweces.com.conf`
- 文件内部也有：
  - `location /api/ { proxy_pass http://api/; }`
- 但 `api.aweces.com/api/order/Success` 实际不能稳定命中 API

根因：

1. `server_name` 配错了
   - 原来是：
     - `app.aweces.com jgood.vip www.jgood.vip below_is_old5.com`
   - 少了：
     - `api.aweces.com`
2. 外网前面还有 Cloudflare
   - `http://api.aweces.com/api/order/Success` 会先 `301` 到 HTTPS
   - 真正需要通的是：
     - `https://api.aweces.com/api/order/Success`

处理：

1. 在线上 `/www/server/panel/vhost/nginx/api.aweces.com.conf`
   - 把 `api.aweces.com` 加回 `server_name`
2. 执行：
   - `nginx -t`
   - `nginx -s reload`

fresh 验证：

- `api.aweces.com /api/order/Success -> 200`
- `api.aweces.com /order/Success -> 404`
- `app.aweces.com /api/order/Success -> 200`
- `ospay.vip /api/order/Success -> 200`

结论：

- 这不是 upstream 没配，而是域名没绑到正确的 server block
- EasyPaisa job 现在已经优先走内网 `127.0.0.1:9000`
- 公网域名只作为兜底或排障入口

### 0.7 EasyPaisa 抓到流水但没回调，随后又被标成“已回调”

现象：

- `pakistanpay_v2` 日志已经抓到 EasyPaisa 流水：
  - 例如：
    - `orderNo = PWM20260419135152388940`
    - `trans_id = 48696661001`
- 但订单一直停在未完成态
- 随后日志又出现：
  - `交易 ... 已回调过，跳过`

本轮线上实证：

- `/order/Success` 被拼成了 `http://api.aweces.com/api/order/Success`
- 该地址返回 `404`
- `ospay.vip`、`www.ospay.vip`、`app.aweces.com` 这类域名仍依赖 nginx 的 `/api/ -> api upstream` 映射
- 如果把公网入口里的 `/api` 全局去掉，这些域名上的 `/order/Success` 会直接在 nginx 层 `404`
- 旧逻辑即使 `transaction_callback()` 失败，仍然会执行：
  - `mark_transaction_callback(utr, login_data)`
- 同时 `sync_collection_job_state()` 会直接用当前 `login_data` 覆盖 `hash_easypaisa`
- 一旦传入的是瘦运行态，就会把完整会话字段覆盖丢

根因：

1. `jobs/pakistanpay_v2.py`
   - 旧逻辑只依赖公网 `ospay_api_host`
   - `ospay_api_host` 带 `/api` 时，错误拼成 `/api/order/Success`
   - 即使去掉 `/api`，也会误伤仍依赖 nginx `/api/` 转发的其他域名
2. `jobs/pakistanpay_v2.py`
   - 回调失败仍标记 `if_callback_easypaisa`
3. `application/easypaisa_runtime/sync_runtime_service.py`
   - `sync_collection_job_state()` 回写 `hash_easypaisa` 时未合并旧值
   - 完整登录态会被瘦 `login_data` 覆盖

处理：

1. `jobs/pakistanpay_v2.py`
   - 新增 `get_order_success_url()`
   - `send()` 优先直连 `http://127.0.0.1:9000/order/Success`
   - 仅在内部地址缺失时才回退公网域名
   - 新增 `callback_transaction()`
   - 只在回调成功后标记 `if_callback_easypaisa`
2. `application/easypaisa_runtime/sync_runtime_service.py`
   - `sync_collection_job_state()` 改为先读旧 `hash_easypaisa`，再 merge 新字段后写回
3. 线上修复顺序：
   - 上传 `jobs/pakistanpay_v2.py`
   - 上传 `application/easypaisa_runtime/sync_runtime_service.py`
   - `python -m py_compile`
   - `supervisorctl restart pakistanpay_v2:*`
   - 删除错误 `if_callback_easypaisa` 成员
4. 如果订单已超出 `/order/Success` 的 8 分钟匹配窗口：
   - 先调用一次 `/order/Success` 写入 `bank_record(callback=0)`
   - 再调用 `/pay/ds/utr` 正式补单
   - 成功后补写 `if_callback_easypaisa`

本轮 fresh 验证：

- 本地：
  - `python3 -m pytest tests/easypaisa_runtime/test_sync_runtime_service.py -q`
  - `17 passed`
- 线上：
  - `supervisorctl status pakistanpay_v2:*` 两个进程均为 `RUNNING`
  - `orders_ds.code='S1776588686613477970'`
    - `status = 4`
    - `trans_id = 48696661001`
    - `time_success` 已写入
  - `bank_record.trans_id='48696661001'`
    - `callback = 1`
    - `order_code = S1776588686613477970`
  - `if_callback_easypaisa`
    - `533280_PWM20260419135152388940` 已重新存在

结论：

- EasyPaisa 这类问题不能只盯 `/order/Success`
- 必须同时检查：
  - 回调 URL 是否被 `/api` 污染
  - `if_callback_easypaisa` 是否被错误提前标记
  - `hash_easypaisa` 是否被 runtime 瘦状态覆盖
  - 订单是否已经超出 8 分钟回调匹配窗

补充样例：

- `trans_id = 48546006954`
  - 不是“没抓到”
  - 已经在 `2026-04-16 00:46:12` 写入：
    - `bank_record.id = 1035912`
    - `payment_id = 533275`
    - `utr = 3084579180`
    - `callback = 0`
    - `if_ew = 1`
    - `ew_code = EW17762823726057366151`
- 这说明当时 API 已收到回调，但返回的不是成功闭环
- `if_ew = 1` 说明已经走到了“回调未匹配成功，额外扣减余额”的分支，不是“jobs 完全没抓到账单”

### 0.6 EasyPaisa `selling_order_status` 和 `payment_online_ds` 漂移

现象：

- 钱包列表、App 或管理侧看起来在线
- 代收订单仍然会分到该账号
- 但 `hash_easypaisa / set_easypaisa` 没有这个账号，抓单任务不会采集

根因：

- 之前只把 EasyPaisa 登录链和部分读面收口到了 runtime
- 没把 `dispatch_ds`、`payment_online_ds`、`hash_easypaisa`、`set_easypaisa` 一起纳入同一真相源
- 导致“能分单”和“会抓单”来自不同状态源

处理：

1. `application/easypaisa_runtime/reader.py`
   - `selling_order_status` 改读 `online && dispatch_ds`
2. `application/pay/pay.py`
   - EasyPaisa 代收 eligibility 改读 runtime `dispatch_ds`
3. `application/easypaisa_runtime/sync_runtime_service.py`
   - jobs 通过 `sync_collection_job_state()` 同步：
     - snapshot
     - `INDEX_DISPATCH_DS`
     - `payment_online_ds`
     - `hash_easypaisa`
     - `set_easypaisa`
4. `rollout_cleanup` / `account_retention`
   - 一起清 `payment_online_ds`

结论：

- 以后 EasyPaisa：
  - `place_order_status` 看 `dispatch_df`
  - `selling_order_status` 看 `dispatch_ds`
- 不能再把 `payment_online_ds` 或 `hash_easypaisa` 单独当主真相源

### 0.5 `login_on_easypaisa_*` 不是重复登录锁的唯一真相

现象：

- 登录没成功，Redis 里却还能看到：
  - `login_on_easypaisa_<payment_id>`
  - `login_on_easypaisa_<phone>`
- 旧逻辑会直接把它当成 `Logined`

根因：

- 这批 key 历史上既被 EasyPaisa 登录流当锁用
- 又被 runtime legacy bridge 当在线镜像用

处理：

1. `application/app/login/banks/easypaisa.py`
   - 改成只查 `easypaisa_runtime:lock:*`
2. `application/easypaisa_runtime/runtime_service.py`
3. `application/easypaisa_runtime/sync_runtime_service.py`
4. `_force_logout()`
   - offline/reset 时同时清：
     - `easypaisa_runtime:lock:*`
     - `login_on_easypaisa_*`

结论：

- 判断“是否被重复登录锁挡住”，以后要看：
  - `easypaisa_runtime:lock:payment:<payment_id>`
  - `easypaisa_runtime:lock:phone:<phone>`
- `login_on_easypaisa_*` 只再表示 legacy 在线镜像

### 0.4 EasyPaisa 单号保留后，不要把全局 `payment_online_df` 误判成回流

现象：

- 已执行：
  - `python scripts/easypaisa_runtime_retain_accounts.py --keep-phone 03045536108 --execute`
- 且 fresh 验证已经看到：
  - `easypaisa_runtime:index:online = ['533280']`
  - `hash_ep_monitor = ['533280']`
  - `login_on_easypaisa_*` 只剩保留号
- 但 Redis 全局仍可能显示：
  - `payment_online_df_count > 1`
  - `payment_active_df_count > 1`

根因：

- `payment_online_df` / `payment_active_df` 是全渠道共享读面
- 这些集合里会同时存在 EasyPaisa、PakistanPay、JazzCash 等其他银行账号
- 所以“全量个数不为 1”不能推出 EasyPaisa 回流

处理：

1. 先查 DB：
   - `SELECT id FROM payment WHERE bank_type=97`
2. 再过滤 Redis：
   - `payment_online_df`
   - `payment_active_df`
3. 只对 EasyPaisa 子集验收

本轮 fresh 结果：

- `payment(bank_type=97, status=1)` 只剩：
  - `533280 / 03045536108`
- `easypaisa_runtime:index:online` / `dispatch_df` 只剩 `533280`
- `hash_ep_monitor` / `set_ep_monitor` 只剩 `533280`
- `login_on_easypaisa_*` 只剩：
  - `login_on_easypaisa_533280`
  - `login_on_easypaisa_03045536108`
- `payment_online_df` / `payment_active_df` 过滤到 EasyPaisa 子集后只剩 `533280`

### 0.3 EasyPaisa runtime rollout 后旧状态继续回流

现象：

- 明明已经执行过：
  - `python scripts/easypaisa_runtime_rollout_cleanup.py --execute`
- 但线上仍会重新出现：
  - `easypaisa_runtime:index:online` 里的孤儿 `payment_id`
  - `login_on_easypaisa_*`
  - `payment_online_df` / `payment_active_df` 中 EasyPaisa 旧成员

根因：

本轮最终确认，回流源有两层：

1. cleanup 早期版本没有清 EasyPaisa jobs 自己的队列态：
   - `hash_easypaisa`
   - `set_easypaisa`
2. `jobs/easypaisa/easypaisa_monitor.py`
   - DB 在线账号补队列时，没有强制同步 runtime snapshot/index
   - DB 已删账号清理时，没有补 `runtime_service.force_offline(...)`

处理：

- `application/easypaisa_runtime/rollout_cleanup.py`
  - 新增清理 `hash_easypaisa` / `set_easypaisa`
- `jobs/easypaisa/easypaisa_monitor.py`
  - 新增 `sync_online_payment_runtime(...)`
  - 新增 `cleanup_missing_db_payment(...)`
- 远端执行顺序：
  1. `python -m py_compile`
  2. `python scripts/easypaisa_runtime_rollout_cleanup.py --execute`
  3. `supervisorctl restart easypaisa_monitor:* pakistanpay_v2:*`

fresh 验收口径：

- `easypaisa_runtime:index:online` 与 DB 当前真实在线 EasyPaisa 账号完全一致
- `hash_easypaisa` / `set_easypaisa` 不再残留 DB 中不存在的 `payment_id`
- `payment_online_df` / `payment_active_df` 中属于当前在线 EasyPaisa 的成员与 runtime 一致
- `login_on_easypaisa_<payment_id>` / `login_on_easypaisa_<phone>` 只对应当前在线账号

### 0.2 列表页切账号发布后，`/user/upi` 报 `Upi has no attribute set_lock_status_from_redis`

现象：

- App 首页点击 `Retry` 后提示：
  - `Could not load wallets`
  - `'Upi' object has no attribute 'set_lock_status_from_redis'`
- 线上日志会在 `GET /v1/user/upi` 时抛 `AttributeError`

根因：

- 新增 `UpiAccounts` / `UpiAccountSelect` 时，`application/lakshmi_api/controllers/upi_controller.py` 的缩进被改坏
- `set_lock_status_from_redis()` 原本属于 `class Upi`
- 误缩进到了 `class UpiAccountSelect`
- 结果 `Upi.get()` 里执行：
  - `await self.set_lock_status_from_redis(raw_payments)`
  时直接找不到该方法

处理：

1. 把 `set_lock_status_from_redis()` 重新挂回 `class Upi`
2. 保持 `UpiAccounts` / `UpiAccountSelect` 作为独立类放在 `Upi` 之后
3. 本地先验：

```bash
cd /Users/tear/pk_project
python3.12 -m py_compile api/application/lakshmi_api/controllers/upi_controller.py
python3 - <<'PY'
import sys
sys.path.insert(0, '/Users/tear/pk_project/api')
from application.lakshmi_api.controllers.upi_controller import Upi, UpiAccounts, UpiAccountSelect
print(hasattr(Upi, 'set_lock_status_from_redis'))
print(hasattr(UpiAccounts, 'set_lock_status_from_redis'))
print(hasattr(UpiAccountSelect, 'set_lock_status_from_redis'))
PY
```

4. 热修上线：

```bash
scp api/application/lakshmi_api/controllers/upi_controller.py \
  root@34.96.148.205:/www/python/api/application/lakshmi_api/controllers/upi_controller.py

ssh root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile application/lakshmi_api/controllers/upi_controller.py && ops api restart'
```

5. fresh 验证：

```bash
ssh root@34.96.148.205 \
  'curl -sS -m 10 -H "Authorization: Bearer invalid" \
  "http://127.0.0.1:9000/v1/user/upi?per_page=1&current_page=1&is_formal=1" -o /tmp/upi.out -w "%{http_code}\n"'
```

结果：

- 返回 `401`
- 不再是 `500`
- 说明接口已经回到正常鉴权路径，`AttributeError` 消失

### 0. EasyPaisa 手机号归属要看 `bank_type_id + phone`，不是 `partner_id + phone`

现象：

- 同一个 EasyPaisa 手机号可能已经被另一个码商历史绑定过
- 应用层虽然返回 `10402`，但主表如果没有数据库唯一键，历史脏数据仍可能残留

本次线上 fresh 查询前发现：

- `global_dup_groups = 2`
- `same_partner_dup_groups = 0`

说明问题不在“同码商重复”，而在“跨码商同号脏数据”。

处理原则：

1. 业务唯一键应为 `payment(bank_type_id, phone)`，不是 `partner_id + bank_type_id + phone`
2. 有指纹的记录优先保留
3. 无指纹脏记录先归档到 `payment_d`，再从 `payment` 主表删除

这次实际清理了：

- `533207`
- `533206`
- `533223`

保留：

- `533026`，因为存在 `/fingerprint/easypaisa_533026_03401336531.zip`

约束：

- 已在线上 `payment` 主表增加唯一键 `uk_payment_bank_phone (bank_type_id, phone)`

fresh 验证：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 <<'SSH'
mysql -h10.108.32.29 -upakistan -p'HFCCoB$D7]{?NTNn' -Dpakistan -Nse "
SELECT 'global_dup_groups', COUNT(*) FROM (
  SELECT 1
  FROM payment
  WHERE phone IS NOT NULL AND phone <> ''
  GROUP BY bank_type_id, phone
  HAVING COUNT(*) > 1
) t;
SHOW INDEX FROM payment WHERE Key_name = 'uk_payment_bank_phone';
"
SSH
```

结果：

- `global_dup_groups = 0`
- `uk_payment_bank_phone` 存在

### 0.1 线上 `ops api restart` 前必须先跑 `py_compile`

现象：

- 这次线上 `/www/python/api` 工作区不是干净态
- 且 `application/app/login/banks/easypaisa.py` 曾存在 f-string 引号错误
- 直接执行 `ops api restart` 会把语法错误代码带着重启，风险很高

处理：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile application/app/login/banks/easypaisa.py application/lakshmi_api/models/payment.py'
```

只有 `py_compile` 通过后，才允许继续：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'ops api restart'
```

补充：

- 不要误用 `python3 -m py_compile` 作为最终上线判断
- 因为当前线上 `python3=3.10.12`，而 `ops` 实际调用的是 `python=3.12.0`

### 0. EasyPaisa business-flow v2 已移除 `payment_status` 自动补推进

现象：

- v2 上线后，`payment_status` 只读，不再把 EasyPaisa 会话从中间态自动推到成功态
- 如果前端还沿用旧链路去调 `/login/active_account`，EasyPaisa 会直接返回 `410 Gone`
- 旧会话若还停留在历史状态字符串（如 `loginSuccessful`），需要在发布前先 flush Redis

根因：

- business-flow v2 把链路拆成：
  - `preLoginCreated -> otpSent -> otpVerified`
  - `fingerprintUploadRequired / fingerprintUploaded -> fingerprintVerified`
  - `secondLoginPassed -> accountSelectionRequired -> activeSuccessful`
  - 异常分支：`awaitingPinChange`
- `/login/payment_status` 的旧式自动补推进逻辑已经删除，后端不会再偷偷调用 `_verify_account`
- `/login/active_account` 对 EasyPaisa 已废弃，必须改走：
  - `/login/verify_fingerprint`
  - `/login/second_login`

修复：

- 发布前执行新脚本清理 EasyPaisa 历史会话与旧登录锁：

```bash
cd /Users/tear/pk_project/api
python3 scripts/easypaisa_session_flush.py
python3 scripts/easypaisa_session_flush.py --execute
```

- Flutter / 调用方必须按新接口顺序串联，不允许再依赖 `payment_status` 自动推进
- 若 verify_fingerprint 返回 `FP_UPSTREAM_REJECTED`，服务端会同步清空 `payment.fingerprint_path` 并删除本地 zip，前端应回到重新扫指纹
- 本轮 runtime 改造不兼容旧 EasyPaisa 会话；发布前必须先执行 flush，不能指望历史 `pre_login_easypaisa_*` / `login_on_easypaisa_*` 自动迁移

验收：

```bash
cd /Users/tear/pk_project/api
python3 -m py_compile application/app/login/banks/easypaisa.py application/easypaisa_runtime/*.py application/lakshmi_api/controllers/upi_controller.py application/lakshmi_api/services/payments/e_wallet_handler.py
python3 -m pytest tests/test_easypaisa_business_flow_v2.py tests/easypaisa_runtime -v
python3 -m pytest tests -q
```

结论：

- v2 之后，`payment_status` 只负责回显 `status / error / cd_until / next_action`
- 旧的 `payment_status auto-promote` 已删除，不再作为排错方向
- 如果线上还有旧 phase/旧 session，先 flush，再按新链路重新登录

### 0.1 EasyPaisa `Fingerprint data corruption` 必须回退到重新扫指纹

现象：

- EasyPaisa 登录已经走到 `verify_fingerprint`
- 上游实际返回：

```json
{"code":403,"msg":"读取03431940911指纹数据失败，请检查指纹数据包(Fingerprint data corruption)","data":null}
```

- API 却把它回成了 `FP_UPSTREAM_TRANSIENT`
- session 继续停在 `fingerprintUploaded`
- App 不会回到重新上传指纹页

根因：

- `application/app/login/banks/easypaisa.py::_perform_verify_fingerprint()`
  旧逻辑只把以下情况归成 `rejected`：
  - `缺少指纹数据`
  - `不支持的action`
  - `code == 500`
- `Fingerprint data corruption` 属于“当前指纹包坏了”的明确拒绝，但它是 `403`，message 也不在旧关键字里，所以被误判成了 `transient`

修复：

- rejected 关键字扩展为：
  - `fingerprint data corruption`
  - `指纹数据失败`
  - `指纹数据包`
- 命中后统一返回 `FP_UPSTREAM_REJECTED`
- 继续复用现有 rejected 清理链：
  - phase 回退到 `fingerprintUploadRequired`
  - 清空 `payment.fingerprint_path`
  - best effort 删除本地 zip

验收：

```bash
cd /Users/tear/pk_project
python3 -m unittest api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_perform_verify_fingerprint_corruption_maps_to_rejected -v
python3 -m unittest api.tests.test_easypaisa_business_flow_v2 -v
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

结论：

- `Fingerprint data corruption` 不是普通临时错误，不能继续留在 `fingerprintUploaded`
- 若线上再看到这类 message，正确动作是重新采并重新上传指纹，而不是反复 verify

### 1. 启动即报数据库连接失败

先检查：

- `MYSQL_HOST`
- `MYSQL_DATABASE`
- `MYSQL_USER`
- `MYSQL_PASSWORD`

如果走 Docker，优先看：

```bash
docker compose logs -f mysql
docker compose logs -f api
```

### 2. 启动即报 Redis 连接失败

检查：

- `REDIS_HOST`
- Redis 容器是否已健康

### 3. WebSocket / 机器人 / 第三方支付接口不通

这是常见现象，因为本地默认是安全占位配置，不会自动接入真实外部环境。

### 4. EasyPaisa `auto_payout` 线上热更新后怎么判断要不要回滚

先看三层证据：

1. supervisor 状态

```bash
/www/server/panel/pyenv/bin/supervisorctl status auto_payout:*
```

2. 线上任务日志

```bash
tail -n 200 /www/server/panel/plugin/supervisor/log/auto_payout.out.log
tail -n 200 /www/server/panel/plugin/supervisor/log/auto_payout.err.log
```

3. ELK 索引

- 重点看 `online_pakistan_easypaisa-YYYY.MM.DD`
- 观察：
  - `ImportError`
  - `ModuleNotFoundError`
  - `SyntaxError`
  - `Traceback`
  - `服务器严重错误`
  - `Lock已不存在`
  - `代付成功处理完成`

经验判断：

- 如果是导入失败、语法错误、属性错误，直接回滚
- 如果只是 `网络请求超时`、`银行维护` 这类三方波动，不要立刻误判成代码回归
- `重复失败检查` 当前会写成 `ERROR`，看 ELK 时要把这类伪错误排除

### 5. JazzCash 单独代付开关关闭后，其他 `/pay/df` 请求也进不来

现象：

- 巴基斯坦 `online_pakistan_api-*` 索引里会集中出现 `HTTP 400: Bad Request (Missing argument bankcode)`
- 许多非 JazzCash 的代付请求也会一起失败

原因：

- `/pay/df` 的商户协议字段是 `bank_code`
- 但 JazzCash 单独开关关闭后的分支直接读取了 `bankcode`
- Tornado 在参数缺失时会直接抛 `MissingArgumentError`

排查：

```bash
curl -s -u 'elastic:***' \
  'http://<es-host>:9200/online_pakistan_api-*/_search' \
  -H 'Content-Type: application/json' \
  -d '{"query":{"match_phrase":{"message":"Missing argument bankcode"}}}'
```

修复：

- 关闭 JazzCash 单独通道时，优先按商户协议读取 `bank_code`
- 同时兼容旧字段 `bankcode`
- 禁止在判断分支里直接无默认值读取 `bankcode`

### 6. 本地直接跑 `pytest` 报 `SyntaxError`，指向 `match self.bank_type`

现象：

- 直接执行 `pytest ...` 时，收集阶段报错
- 栈里显示使用的是系统 Python 3.9
- 错误文件通常会落在 `application/phonepe/phmonitor.py`

原因：

- 当前仓库代码已使用 Python 3.10+ 的 `match/case`
- 终端里的 `pytest` 可能绑定到系统 Python 3.9，而不是项目实际使用的 Python 3.12

处理：

```bash
cd /Users/tear/pk_project/api
python3.12 -m pytest tests/test_router_easypay_cleanup.py -q
```

结论：

- 这不是本次代码修改引入的语法回归
- 优先用 `python3.12 -m pytest`，不要直接信任裸 `pytest`

### Easypay SOAP 代收错误码

| Code | 含义 | 排查方向 |
|------|------|---------|
| 0000 | 成功 | — |
| 0001 | 系统错误 | Easypay 侧问题，稍后重试 |
| 0002 | 缺少必填字段 | 检查 SOAP XML 是否完整（username/password/orderId/storeId/amount/msisdn） |
| 0003 | 无效订单号 | 检查 orderId 是否重复或格式不对 |
| 0004 | 商户账户不存在 | 检查 otherpay.merchant_id 是否正确 |
| 0005 | 商户账户未激活 | 联系 Easypay 确认 KYC 状态 |
| 0006 | 店铺不存在 | 检查 otherpay.key3 (store_id) |
| 0007 | 店铺未激活 | 在 Easypay 商户后台确认店铺状态 |

排查步骤：查看 `api_*.log` 中 `[easypay]` 前缀日志，或 `order_timeout.log` 中轮询日志。
当前商户后台名称：`AbdulMoizE-Store`。
配置核对：`otherpay.merchant_id=Account ID`、`otherpay.key=Merchant Name`、`otherpay.key2=API Key`、`otherpay.key3=Store ID`。

### JazzCash `1002` 误派到自有码商

现象：

- `1002` 订单日志先出现：
  - `按照权重随机选取码接单: 533182`
  - `码 533182 在 Redis 队列 'payment_active_1002' 中`
- 订单表里会同时留下：
  - `payment_id=533182`
  - `otherpay=25`
  - `third_party_name=easypay`

根因：

- 数据库 `payment.channel` 错配为 `1002,1003`
- Redis `payment_active_1002` 被污染
- 运行态 `hash_jazzcash.qr_channel` 仍是 `1002,1003`
- `jazzcashv2/pakistanpay_v2` 长驻任务不重启时，会继续把旧运行态写回 Redis
- 仓库里的 [jazzcash.py](/Users/tear/pk_project/api/application/app/login/banks/jazzcash.py) 也曾默认把新登录账号写成 `1002,1003`

修复顺序：

1. 备份数据库与 Redis 运行态
2. `payment.channel: 1002,1003 -> 1003`
3. `hash_jazzcash.qr_channel: 1002,1003 -> 1003`
4. 清空：
   - `payment_active_1002`
   - `payment_active_1002,1003`
5. 重启：

```bash
/www/server/panel/pyenv/bin/supervisorctl restart jazzcashv2:* pakistanpay_v2:*
```

6. 把 [jazzcash.py](/Users/tear/pk_project/api/application/app/login/banks/jazzcash.py) 默认通道改成 `1003`
7. 只用 `196` 测试商户 fresh 拉单验收

验收信号：

- `payment.id=533182.channel = 1003`
- `hash_jazzcash['533182'].qr_channel = 1003`
- `payment_active_1002 = []`
- 新测试单 `payment_id = NULL`

补充：

- 如果数据库和 `hash_jazzcash` 都已经改对，但 `payment_active_1002` 仍然还能看到 `533182`，这不是数据库回滚，而是 Redis 历史脏成员没清干净。
- 这种情况下 [pay.py](/Users/tear/pk_project/api/application/pay/pay.py) 仍会按在线池继续命中 `533182`。
- 处理动作是：
  1. `LREM payment_active_1002 0 533182`
  2. 同步线上 [jazzcash.py](/Users/tear/pk_project/api/application/app/login/banks/jazzcash.py) 为默认 `1003`
  3. fresh 重启 `api`

### 7. 码商 `03416683864` 的 UPI 列表突然为空

现象：

- 远端 Flutter 商户端查询 `GET /v1/user/upi?per_page=500&current_page=1&is_formal=1` 时，`user=33046` 返回：

```json
{"data":{"payments":[]},"pagination":{"total_pages":0,"current_page":1}}
```

- 账号信息存在：

```sql
select id,name,cellphone,status,certified,type
from partner
where cellphone='03416683864';
```

结果为 `partner.id=33046, name=Kawish Naseem`。

根因：

- 不是前端过滤，也不是接口参数问题。
- `/user/upi` 只查主表 `payment`，条件是 `payment.partner_id = current_user.id` 且 `payment.bank_type_id in (97,98)`。
- 该账号原本的 5 条 EasyPaisa 钱包记录曾经存在于 `payment`，至少在 `2026-04-17 14:00:31` 的线上日志里还能正常返回：
  - `533243 / 03416683864`
  - `533246 / 03059777652`
  - `533247 / 03084579180`
  - `533250 / 03489696378`
  - `533279 / 03321914388`
- 之后这些记录被整体转移到了归档表 `payment_d`，主表 `payment` 中已不存在，因此 `/user/upi` 返回空列表。

证据：

```sql
select id,partner_id,phone,upi,status,certified,name,time_create,time_update
from payment
where partner_id=33046;
```

返回 `0` 行。

```sql
select id,partner_id,phone,upi,status,certified,name,time_create,time_update
from payment_d
where partner_id=33046
order by id;
```

返回：

- `533243 03416683864 time_create=2026-04-17 14:48:46`
- `533246 03059777652 time_create=2026-04-17 14:48:44`
- `533247 03084579180 time_create=2026-04-17 14:48:42`
- `533250 03489696378 time_create=2026-04-17 14:48:38`
- `533279 03321914388 time_create=2026-04-17 14:48:40`

复核命令：

```bash
ssh -i open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205

mysql -h10.108.32.29 -upakistan -p'***' pakistan -e "
select id,name,cellphone,status,certified,type
from partner
where cellphone='03416683864';

select id,partner_id,phone,upi,status,certified,name,time_create,time_update
from payment
where partner_id=33046;

select id,partner_id,phone,upi,status,certified,name,time_create,time_update
from payment_d
where partner_id=33046
order by id;
"

curl -sS -H 'Authorization: Bearer <该账号 token>' \
  'http://127.0.0.1:9000/v1/user/upi?per_page=500&current_page=1&is_formal=1'
```

结论：

- `03416683864` “没有列表”的直接原因是：钱包记录已经不在 `payment`，而在 `payment_d`。
- 后续继续查 `admin` 日志后，已经确认这不是“猜测上的人工操作”，而是后台页面真实触发的删除接口：
  - `2026-04-17 14:48:38` `POST /partner/deletepayment` `{"id":533250,"is_del":false}`
  - `2026-04-17 14:48:40` `POST /partner/deletepayment` `{"id":533279,"is_del":false}`
  - `2026-04-17 14:48:42` `POST /partner/deletepayment` `{"id":533247,"is_del":false}`
  - `2026-04-17 14:48:44` `POST /partner/deletepayment` `{"id":533246,"is_del":false}`
  - `2026-04-17 14:48:46` `POST /partner/deletepayment` `{"id":533243,"is_del":false}`
- 这些请求都来自同一个后台操作者：`337@34.131.201.121`。
- 数据库 `admin` 表核对结果：`admin.id=337, account=188888866, name=小悔, status=1`。
- 因此这次 `33046` 账号下的 5 条钱包记录，是在 `2026-04-17 14:48:38~14:48:46` 被后台账号 `小悔(337)` 通过 `admin` 页面连续点击删除，导致从 `payment` 迁入 `payment_d`。
- 如果要恢复列表，需要把对应记录从 `payment_d` 恢复回 `payment`；如果要继续审计，可再结合 `admin.aweces.com` 的 Nginx 访问日志和该账号登录日志做交叉确认。

## 2026-04-18 EasyPaisa `pre_login` 漏掉跨码商手机号占用校验

### 现象

- Lakshmi `/user/upi` 新增接口已经能阻止“同银行同手机号被不同码商重复新增”
- 但 EasyPaisa `pre_login` 仍可能绕过这层约束，导致相同手机号被错误复用或继续初始化登录会话

### 根因

`api/application/app/login/banks/easypaisa.py` 的 `_check_payment(bankname, phone, partner_id)` 之前带了：

```python
(Payment.user_id == partner_id) if partner_id else True
```

这会让查询只能看到“当前码商自己的 payment”，从而看不到“该手机号已经属于其他码商”的记录。

### 处理

1. `_check_payment(...)` 改为只按 `bank_type + phone` 查现有记录
2. `pre_login_http(...)` 在 `payment_id` 为空的分支里增加归属判断：
   - 属于当前码商：继续复用现有 `payment_id`
   - 属于其他码商：直接返回 `10402`

### 验证

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/app/login/banks/easypaisa.py application/easypaisa_runtime/*.py application/lakshmi_api/controllers/upi_controller.py application/lakshmi_api/services/payments/e_wallet_handler.py
python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py tests/easypaisa_runtime -q
```

结果：

- `py_compile`：通过
- `pytest tests/test_easypaisa_business_flow_v2.py tests/easypaisa_runtime -q`：`36 passed`

## 2026-04-19 EasyPaisa jobs runtime 写面闭环

### 现象

- 登录链已经把 EasyPaisa 主状态切到 `easypaisa_runtime:snapshot:*`
- 但 `jobs/easypaisa/easypaisa_monitor.py`、`jobs/pakistanpay_v2.py` 仍会直接散写：
  - `payment_online_df`
  - `payment_active_df`
  - `login_on_easypaisa_*`
  - `kick_off_*`
- `clear_redis_inactive_payment.py` 仍把 `login_on_*` 当成 EasyPaisa 活跃态真相

这样会导致：

- monitor / statement worker 继续把旧运行态写回 Redis
- runtime snapshot 和 legacy bridge 可能重新分叉
- `order_push.py` / `jobs/easypaisa/auto_payout.py` 虽然还能消费旧队列，但其输入语义不再由 runtime 统一驱动

### 根因

- 之前只完成了 API 登录链与 reader 的 runtime 化
- 同步 Redis 作业缺少对应的 sync runtime service
- inactive cleanup 对 EasyPaisa 没有 runtime 在线索引入口

### 处理

1. 新增同步版 runtime service：
   - [sync_runtime_service.py](/Users/tear/pk_project/api/application/easypaisa_runtime/sync_runtime_service.py)
2. 为 sync runtime 补上：
   - runtime kickoff key
   - legacy kickoff bridge
3. `jobs/easypaisa/easypaisa_monitor.py` 改为：
   - `update_redis_cache()` 在线时走 `mark_active_successful(...)`
   - 下线时走 `force_offline(...)`
   - `on_off()` 改走 sync runtime service
4. `jobs/pakistanpay_v2.py` 的 `on_off()` 改走 sync runtime service
5. `clear_redis_inactive_payment.py` 对 EasyPaisa 先读 `easypaisa_runtime:index:online`
6. 保持：
   - `order_push.py`
   - `jobs/easypaisa/auto_payout.py`

继续消费 legacy bridge 输出，不额外做无意义兼容改造

### 边界说明

- `clear_redis_dsdf.py` 当前 SQL 只扫 `bank_type in (16,14,17,21,30)`，不包含 EasyPaisa `97`
- 所以它不是本轮 EasyPaisa cleanup 主入口，本轮只记录审计结论，不强行把 EasyPaisa 逻辑塞进去

### 验证

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/easypaisa_runtime/*.py jobs/easypaisa/easypaisa_monitor.py jobs/pakistanpay_v2.py jobs/clear_redis_inactive_payment.py
python3.12 -m pytest tests/easypaisa_runtime/test_sync_runtime_service.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_reader.py tests/test_easypaisa_business_flow_v2.py -q
```

结果：

- `py_compile`：通过
- `pytest ... -q`：`44 passed, 1 warning`

### 结论

- EasyPaisa `api + jobs` 现在已经统一由 runtime snapshot 驱动主状态
- legacy `payment_online_df` / `payment_active_df` / `login_on_easypaisa_*` 只保留 bridge 输出，不再作为 jobs 主写面
- `order_push.py` 和 `jobs/easypaisa/auto_payout.py` 的消费链不需要改代码，就能继续吃到 runtime 驱动后的 legacy 队列

## 2026-04-19 EasyPaisa legacy app runtime 读面与下线闭环

### 现象

`api/application/app/my/my.py` 里的 EasyPaisa 仍残留两类问题：

- `my.getpayment` / `my.getOnlinePayment` 直接读 `payment_online_ds` / `payment_online_df`
- `my.changepayment(status=0)` 只改数据库 `payment.status`，不会同步清 runtime session / snapshot

这会导致：

- runtime snapshot 已在线，但旧 `my` 接口仍可能把 EasyPaisa 展示成离线
- 用户在旧 app 里手动关闭 EasyPaisa 后，runtime 仍可能保持在线

### 根因

- 前两轮只完成了：
  - API 登录链 runtime 化
  - jobs 写面 runtime 化
  - admin 读面 runtime 化
- 旧 `application/app/my/my.py` 仍保留 legacy Redis 判断

### 处理

1. `my.py` 新增 EasyPaisa 最小 helper：
   - `bank_type == 97` 时，`online_ds` 读 runtime session 在线态
   - `online_df` 读 runtime 代付在线态
2. `my.getOnlinePayment` 对 EasyPaisa 改为按 runtime 在线字段筛选
3. `EasyPaisaRuntimeService` 增加 `force_reset(...)`
4. `my.changepayment(status=0)` 对 EasyPaisa 同步：
   - `clear_session`
   - `force_offline`
   - legacy bridge 清理
5. 非 EasyPaisa 银行保持现状，不扩散兼容面

### 验证

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/app/my/my.py application/easypaisa_runtime/*.py
python3.12 -m unittest discover -s tests -p 'test_app_my_easypaisa_runtime.py' -v
python3.12 -m unittest discover -s tests -v
```

结果：

- `py_compile`：通过
- `test_app_my_easypaisa_runtime.py`：`3 tests` 全绿
- `tests -v`：`47 tests` 全绿

### 结论

- EasyPaisa 在 legacy app 的列表展示和在线列表已经改读 runtime 语义
- 旧 app 手动下线 EasyPaisa 时，runtime session / snapshot 也会同步下线
- 非 EasyPaisa 银行不受本轮改动影响

## 2026-04-26 JazzCash verify_otp 实际在验指纹

### 现象

JazzCash 业务要求展示为：

```text
发送验证码 -> 验证验证码 -> 验证指纹 -> 激活成功
```

但旧后端在 OTP 页面对应的 `loginStep2` 请求中生成：

```python
should_verify_otpcode = False
should_verify_fingerprint = True
```

这会让 `/api/v1/login/verify_otp` 的页面语义和真实上游动作不一致：用户输入 OTP 时，服务端实际在调用 `loginStep2` 验指纹。进一步复核后确认，JazzCash 上游没有独立的 `verifyFingerprint` action，`loginStep2` 本身就是指纹验证动作。

### 根因

1. JazzCash 真实上游语义是：`loginStep1` 发 OTP，`loginStep2` 验指纹；不存在单独的上游 `verifyFingerprint`。
2. 旧代码把 `loginStep2` 挂在 `/login/verify_otp` 下，导致 OTP 页面实际在做指纹验证。
3. `VerifyFingerprint` controller 只支持 EasyPaisa，JazzCash 没有自己的公开 `/login/verify_fingerprint` 分支。
4. App 把 JazzCash OTP 后的 `next_step=active_account` 作为成功收尾，没有走“OTP 后验指纹”。

### 处理

1. JazzCash 切到 `v1.5` send-OTP-first 模式。
2. `verify_otp_http()` 不再调用 JazzCash 上游，只做 OTP 非空检查、本地状态推进、保存 payment/session，并返回：
   - `next_phase=fingerprintUploadRequired`
   - 或已有指纹时 `next_phase=fingerprintUploaded`
3. `upload_fingerprint_http()` 允许 OTP 后状态，并推进到 `fingerprintUploaded`。
4. 新增 `JazzCash.verify_fingerprint_http()`，内部调用上游 `loginStep2` 验指纹；成功后再 secondLogin、更新 payment、写 Redis 在线队列并返回 `activeSuccessful`。
5. Flutter 端移除 JazzCash `active_account` 收尾依赖，JazzCash 指纹验证成功即 `activeSuccess`。

### 验证

```bash
cd /Users/tear/pk_project_k8s
python3.12 -m unittest api.tests.test_jazzcash_business_flow_v2 -v
```

关键断言：

- JazzCash 不配置上游 `verify_fingerprint` action
- `_build_verify_fingerprint_request()` 使用 `action=loginStep2`
- `verify_otp_http()` 不调用 JazzCash 上游，也不调用 `_verify_account()`
- OTP 后上传指纹可进入 `fingerprintUploaded`
- `/login/verify_fingerprint` 支持 `bankname=jazzcash`
- 指纹验证成功后 session 为 `activeSuccessful`

## 2026-04-26 `ospay_api_host` 与回调缓存混用旧域名

### 现象

当前服务器入口是 `api.awekay.com`，但 PROD 配置里的 `ospay_api_host`、`pay_url`、`websocket_api_allow_host` 仍残留旧域名。Redis `notice_domain_api_list` 为空时，代收/代付三方回调地址会回退到旧域名；`merchant_pay_links` 为空时，平台收银台链接会回退到旧 `pay_url`，导致当前测试环境和旧环境混用。

### 根因

1. `ospay_api_host` 和 `pay_url` 都是代码兜底配置，未随当前服务器域名更新。
2. 多个三方通道优先读 Redis `notice_domain_api_list`，为空时才回退到 `ospay_api_host` 或历史硬编码域名。
3. 平台收银台链接优先读 Redis `merchant_pay_links`，为空时才回退到 `pay_url`。
4. JazzCash/EasyPaisa job 中个别位置使用 `getattr(conf, 'ospay_api_host', ...)` 读取 dict，实际读不到配置，会误回退到 localhost。
5. Redis 属于易失缓存，重建后如果 API 启动不主动写入当前服务器域名，就容易再次落回旧域名。

### 处理

1. PROD `ospay_api_host` 改为 `http://api.awekay.com/api`。
2. PROD `pay_url` 改为 `http://api.awekay.com/api/order/`。
3. PROD `websocket_api_allow_host` 改为 `['api.awekay.com']`。
4. JazzCash/EasyPaisa job 改为 `conf.get('ospay_api_host', ...)`。
5. API 启动初始化时，若 Redis `notice_domain_api_list` 为空，写入 `ospay_api_host`。
6. 若 Redis 已有 `notice_domain_api_list`，不覆盖，保留后台维护多回调域名的能力。

### 验证

```bash
cd /Users/tear/pk_project_k8s
python3.12 -m py_compile \
  api/main.py \
  api/config.example.py \
  api/jobs/Jazzcashpay_v2.py \
  api/jobs/jazzcash/jazzcash_monitor.py \
  api/jobs/easypaisa/easypaisa_monitor.py
```

线上检查：

```bash
kubectl exec -n pk "$REDIS_POD" -- redis-cli GET notice_domain_api_list
kubectl exec -n pk deploy/api-deploy -- python - <<'PY'
import sys, json
sys.path.insert(0, '/app/api')
from config import get_config
conf = get_config()
print(json.dumps({
    'ospay_api_host': conf['ospay_api_host'],
    'pay_url': conf['pay_url'],
    'websocket_api_allow_host': conf['websocket_api_allow_host'],
}, ensure_ascii=False))
PY
```

期望 `ospay_api_host` 为 `http://api.awekay.com/api`，`pay_url` 为 `http://api.awekay.com/api/order/`，`websocket_api_allow_host` 为 `['api.awekay.com']`。

## 2026-04-26 上传指纹后重部署文件丢失

### 现象

App 已调用 `/api/v1/login/upload_fingerprint`，Nginx access log 也能看到上传请求返回 200；但部署后服务器上查不到 `fingerprint/*.zip`，`payment.fingerprint_path` 也为空。

### 根因

1. EasyPaisa/JazzCash 的 `_save_fingerprint()` 统一以 `/fingerprint/` 作为指纹 zip 保存目录。
2. API Deployment 曾经把 PVC 挂载到 `/app/api/application/app/login/banks/fingerprint`，而代码实际写入 `/fingerprint/`；因此上传成功后文件没有进入持久化目录，Pod 重建后根目录临时文件消失。
3. `/fingerprint` 是业务约定的唯一指纹目录，Deployment 必须把 PVC 直接挂到该目录，避免模块目录和根目录两套路径并存。
4. 当前集群没有 RWX StorageClass，两个 API 副本跨节点时即使使用节点本地目录，也会出现 A Pod 上传、B Pod 验证找不到文件。

### 处理

1. 新增 `ops/k8s/api-fingerprint-persistence.yaml`：
   - `api-fingerprint-pv`
   - `api-fingerprint-pvc`
   - 本地路径 `/data/pk/api/fingerprint`
   - 节点亲和固定到 `pk-1`
2. API Deployment 固定调度到 `pk-1`。
3. API 容器挂载：

```text
/fingerprint -> api-fingerprint-pvc
```
4. 保持 EasyPaisa/JazzCash 的 `FINGERPRINT_PATH=/fingerprint/`，确保代码保存目录和 PVC 挂载目录完全一致。

### 验证

```bash
kubectl get pv api-fingerprint-pv
kubectl get pvc api-fingerprint-pvc -n pk
kubectl get pods -n pk -l app=api -o wide
kubectl exec -n pk deploy/api-deploy -- sh -lc 'mount | grep " /fingerprint "'
```

回归测试：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_save_fingerprint_uses_root_fingerprint_mount_dir -v
python3 -m unittest api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_save_fingerprint_uses_root_fingerprint_mount_dir -v
```

补充验证：

1. 在一个 API Pod 写入测试文件。
2. 在另一个 API Pod 读取同一文件。
3. 滚动重启 API Deployment。
4. 新 Pod 仍能读到该文件。

### 后续建议

当前方案适合测试环境。若需要跨节点高可用，应替换为 NFS/云文件存储等 RWX PVC，再取消 API 固定 `pk-1` 的调度约束。
## 2026-04-26 JazzCashBusiness legacy Redis 脏状态导致 API 派单误判

### 现象

JazzCashBusiness 激活和监控链路会直接写：

- `payment_online_ds`
- `payment_online_df`
- `payment_active_df`
- `payment_active_{channel}`
- `login_on_jazzcash_*`

如果这些 legacy key 残留，API 的代收、代付和 app 展示会把脏队列误判成真实在线。

### 根因

JazzCashBusiness 没有像 EasyPaisa 一样的 runtime snapshot/index，admin、API、jobs 分别读写不同 Redis key，缺少唯一真相源。

### 处理

- 新增 `application/jazzcash_runtime`：
  - `runtime_service.py`
  - `sync_runtime_service.py`
  - `reader.py`
  - `legacy_bridge.py`
  - `keyspace.py`
- 登录激活成功统一调用 `JazzCashRuntimeService.mark_active_successful()`。
- `pay.py`、`upi_controller.py`、`e_wallet_handler.py`、`app/my.py` 对 `bank_type/bank_type_id=98` 改读 `JazzCashRuntimeReader`。
- `order_push.py` 和 JazzCash jobs 对 JazzCash 代付在线、回队、上下线改走 `SyncJazzCashRuntimeService`。

### 排错口径

- snapshot 缺失时，`bank_type=98` 默认离线，不能回退信任 `payment_online_ds/payment_online_df`。
- `payment_online_*` 只能作为兼容旧 job 的派生投影，不是主状态。
- 如果发现 JazzCashBusiness 明明 admin 显示离线但仍接单，优先查：
  - `jazzcash_runtime:snapshot:{payment_id}`
  - `jazzcash_runtime:index:ds_order_enabled`
  - `jazzcash_runtime:index:df_order_enabled`
  - 再看 legacy 是否只是 bridge 派生残留。

### 本轮验证

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.test_order_push_easypaisa_runtime_guard -v

python3.12 -m py_compile \
  api/application/app/login/banks/jazzcash.py \
  api/jobs/Jazzcashpay_v2.py \
  api/jobs/jazzcash/jazzcash_monitor.py \
  api/jobs/jazzcash/jazzcash_auto_payout.py
```

## 2026-04-26 JazzCashBusiness websocket/time_out/pay 回队仍绕过 runtime

### 现象

上一轮 runtime 收口后复查仍发现：

- websocket monitor 对 `bank_type=98` 仍会走非 EP legacy 分支，直接写 `payment_online_ds/payment_online_df`。
- `time_out.py` 只校验 EasyPaisa 的 `easypaisa_runtime:index:dispatch_ds`，JazzCashBusiness 超时后可能被 legacy 队列回推。
- `pay.py` 代收回队会检查 legacy `kick_off_{payment_id}`，JazzCashBusiness runtime 在线时也可能被历史脏 key 拦住。

### 根因

这些入口早期只区分 EasyPaisa 和非 EasyPaisa。JazzCashBusiness 接入独立 runtime 后，如果不增加 `bank_type/bank_type_id=98` 分支，就会继续把 legacy Redis key 当成主状态。

### 处理

- `api/application/websocket/monitor.py` 增加 JazzCashBusiness 分流，ds/df 上下线调用 `JazzCashRuntimeService`。
- `api/application/jazzcash_runtime/runtime_service.py` 补 `set_df_order_dispatch()`。
- `api/jobs/time_out.py` 的 `TimeOutGuard` 增加 `jazzcash_runtime:index:dispatch_ds` 校验。
- `api/application/pay/pay.py` 新增 `_has_collection_kickoff()`，runtime 银行只读各自 runtime kickoff key。
- 删除被 git 跟踪的旧 `api/jobs/jazzcash/jazzcash_auto_payout.py.bak`，避免死代码继续保留直接读写 legacy 队列的 JazzCashBusiness 旧口径。

### 排错口径

- JazzCashBusiness 可否代收：先看 `jazzcash_runtime:snapshot:{payment_id}.ds_order_enabled/dispatch_ds` 和 `jazzcash_runtime:index:dispatch_ds`。
- JazzCashBusiness 是否被踢下线或暂停：先看 `jazzcash_runtime:kickoff:{payment_id}`。
- `kick_off_{payment_id}` 只作为非 runtime 银行 legacy 口径，不能作为 JazzCashBusiness 业务结论。

### 本轮验证

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_jazzcash_business_flow_v2 \
  api.tests.test_websocket_monitor_ep_dispatch \
  api.tests.test_time_out_guard \
  api.tests.jazzcash_runtime.test_reader -v

python3.12 -m py_compile \
  api/application/jazzcash_runtime/*.py \
  api/application/websocket/monitor.py \
  api/application/pay/pay.py \
  api/jobs/time_out.py
```

## 2026-04-26 JazzCashBusiness 采集端旧队列绕过 runtime

### 现象

- `jazzcash_runtime:snapshot:{payment_id}` 已经离线或 `collect_enabled=false`。
- 但旧 `hash_jazzcash` / `set_jazzcash` 里仍有 `grabstatement` job。
- 采集 worker 可能继续调用上游账单接口。

### 根因

旧采集端把 `hash_jazzcash` / `set_jazzcash` 当成主状态。JazzCashBusiness 接入 runtime 后，如果 worker 不先读取 `jazzcash_runtime`，旧队列残留就可能绕过 admin/api 的 runtime 判断。

### 处理

- `SyncJazzCashRuntimeService` 新增 `sync_collection_job_state()`，统一维护 runtime snapshot/index 与 `hash_jazzcash` / `set_jazzcash` 投影。
- `Jazzcashpay_v2.py` 的 `update_key()`、`pre_login` 推进、worker 采集前检查全部改走 runtime。
- `collect_enabled=false` 时强制关闭 DS/DF，并清理 `hash_jazzcash` / `set_jazzcash`。
- JCB 业务约束保持不变：代付必须能采集账单，方便上游代付结果异常时对账。

### 排错口径

先查 runtime：

```bash
redis-cli GET jazzcash_runtime:snapshot:{payment_id}
redis-cli SISMEMBER jazzcash_runtime:index:collect_enabled {payment_id}
redis-cli ZSCORE jazzcash_runtime:schedule:collection {payment_id}
```

再查旧 job 投影：

```bash
redis-cli HGET hash_jazzcash {payment_id}
redis-cli ZSCORE set_jazzcash {payment_id}
```

判断规则：

- runtime `online=false` 或 `collect_enabled=false` 时，旧 job 残留应被 worker 清理。
- `payment.status/certified` 不满足接单时，允许采集继续跑，但 `ds_order_enabled=false` 且 `df_order_enabled=false`。
- 旧 `login_off_jazzcash_*` 不再是主真相源，不能仅凭该 key 判断 JCB 必须下线。

### 本轮验证

```bash
PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.jazzcash_runtime.test_sync_collection_worker \
  api.tests.test_jazzcash_business_flow_v2 -v

python3.12 -m py_compile \
  api/application/jazzcash_runtime/sync_runtime_service.py \
  api/jobs/Jazzcashpay_v2.py
```

## 2026-04-26 JazzCashBusiness pre_login 写 runtime 快照时 `qr_channel` 未定义

### 现象

- 码商用 `03409297123` 做 JazzCashBusiness 上号，第一次交易密码验证成功。
- API 日志随后报错：

```text
NameError: name 'qr_channel' is not defined
```

- 第一次请求已经写入 `pre_login_jazzcash_03409297123`，但接口异常返回；后续重试被残留 `preLogin` 会话挡住，提示已经开始登录流程。
- 中间有一次请求把交易密码和 PIN 传反，导致一次 `Payment password verification failed`。

### 根因

`pre_login_http()` 的 `session_data` 中直接使用 `data.get('channel', '1003')`，但写 `jazzcash_runtime:snapshot:*` 时引用了未定义变量 `qr_channel`。异常发生在 Redis 会话写入之后、接口成功返回之前，因此会留下半截 `preLogin` 状态。

### 处理

- 在生成 `session_data` 前统一解析：

```python
qr_channel = data.get('channel', '1003')
```

- `session_data['qr_channel']` 和 runtime snapshot `channels` 都使用同一个 `qr_channel`。
- 加回归测试覆盖 `pre_login_http()` 写入 runtime snapshot 的通道字段。

### 本轮验证

```bash
python3 -m unittest api.tests.test_jazzcash_business_flow_v2 -v
python3 -m py_compile api/application/app/login/banks/jazzcash.py
```

## 2026-04-26 JazzCashBusiness 上号到派单整链路 payment_id/runtime 审计

### 现象

- 修复 `pre_login` 的 `qr_channel` 后继续复查全链路，发现 JCB 不是单点报错，而是临时 `payment_id`、真实 `payment.id`、pre_login Redis、runtime session/snapshot 之间没有完全收口。
- 新用户上号时 `pre_login` 会先用手机号作为临时 `payment_id`，`verify_otp` 保存 DB 后才得到真实 `payment.id`。
- 如果 App 或状态轮询仍携带旧临时 id，后续 `payment_status`、`upload_fingerprint`、`verify_fingerprint` 可能找不到真实会话。
- `pre_login` 只拦截了 `preLogin/sendOtp/verifyOtp/loginSuccessful` 等旧状态，漏掉 `fingerprintUploadRequired/fingerprintUploaded/fingerprintVerified/activeSuccessful`，重试时可能覆盖正在走的指纹流程。

### 根因

JCB 后端已经接入 `jazzcash_runtime`，但上号状态机仍有部分 EasyPaisa 已有的“真实会话解析”能力缺失：

- 缺少 `payment_id` alias：临时 id 晋升到真实 id 后，没有让旧 id 稳定解析到真实会话。
- `payment_status_http()` 只返回旧字段，没有 `status/next_action/error/resolved_payment_id`，App 状态机不能可靠判断下一步。
- pending session 没有完整同步到 runtime session/snapshot，导致 API、App 轮询、采集/派单查看到的状态可能不一致。
- 清理旧 snapshot 时只删主 key，未同步清理 runtime index，存在残留索引风险。

### 处理

- 新增 JCB 会话解析 helpers：`_resolve_session_context()`、pre_login alias、runtime session fallback。
- `verify_otp_http()` 保存真实 `payment.id` 后：
  - 删除临时 runtime session/snapshot。
  - 写入 `pre_login_jazzcash_{临时id}` alias 指向真实 id。
  - 后续 `payment_status/upload_fingerprint/verify_fingerprint/active_account` 都解析到真实会话。
- 对旧版本已产生的临时 id 残留增加兼容迁移：如果手机号临时 id 的 runtime session 仍在，但数据库和真实 `pre_login_jazzcash_{payment.id}` 已存在，则自动写 alias 并清理临时 runtime session/snapshot。
- `payment_status_http()` 改为优先读 `jazzcash_runtime:snapshot:{payment_id}`，返回：
  - `status`
  - `next_action`
  - `error`
  - `cd_until`
  - `resolved_payment_id`
- `pre_login_http()` 补齐所有指纹阶段和 `activeSuccessful` 的重复登录拦截；如果 runtime 已明确离线，则清理残留成功会话后允许重新上号。
- 登录锁统一写 `jazzcash_runtime:lock:*`，legacy `login_on_jazzcash_*` 继续由 runtime legacy bridge 作为投影维护。
- `JazzCashRuntimeService.clear_snapshot()` 同步清理所有 runtime index 与采集 schedule。

### 排错口径

上号链路先查真实会话解析：

```bash
redis-cli GET pre_login_jazzcash_{临时或真实payment_id}
redis-cli GET jazzcash_runtime:session:{真实payment_id}
redis-cli GET jazzcash_runtime:snapshot:{真实payment_id}
```

如果 `pre_login_jazzcash_{临时id}` 是：

```json
{"kind":"payment_id_alias","target_payment_id":"533280"}
```

则后续 `payment_status/upload_fingerprint/verify_fingerprint` 都应解析到 `533280`，不应再按手机号临时 id 找会话。

派单/采集继续只看 runtime 主状态：

```bash
redis-cli SISMEMBER jazzcash_runtime:index:dispatch_ds {payment_id}
redis-cli SISMEMBER jazzcash_runtime:index:dispatch_df {payment_id}
redis-cli SISMEMBER jazzcash_runtime:index:collect_enabled {payment_id}
```

legacy `payment_online_*`、`payment_active_*`、`hash_jazzcash`、`set_jazzcash` 只作为 runtime 投影，不作为 JCB 的唯一判断依据。

### 本轮验证

```bash
python3 -m unittest \
  api.tests.test_jazzcash_business_flow_v2 \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.jazzcash_runtime.test_sync_collection_worker -v

PYTHONPATH=api python3 -m unittest \
  api.tests.test_websocket_monitor_ep_dispatch \
  api.tests.test_order_push_easypaisa_runtime_guard -v

python3 -m py_compile \
  api/application/app/login/banks/jazzcash.py \
  api/application/jazzcash_runtime/runtime_service.py \
  api/application/jazzcash_runtime/reader.py \
  api/application/jazzcash_runtime/sync_runtime_service.py

git diff --check

cd /Users/tear/pk_project/ashrafi_merchant_flutter
export PATH=/Users/tear/sdk/flutter/bin:$PATH
flutter test --no-test-assets \
  test/exchange_api_response_parsing_test.dart \
  test/onboarding_controller_test.dart
```

## 2026-04-27 EasyPaisa 到了 `activeSuccessful` 但收款资料没有同步启用

### 现象

- 账号 `03009208353 / payment_id=533299` 的 Redis session 已经是 `activeSuccessful`。
- status history 已完整走完：
  `preLoginCreated -> otpSent -> otpVerified -> fingerprintUploadRequired -> fingerprintUploaded -> fingerprintVerified -> secondLoginPassed -> accountSelectionRequired -> activeSuccessful`。
- 但前端曾显示 `status=inactive`，runtime snapshot 里 `collect_enabled/ds_order_enabled/df_order_enabled` 仍为 `false`。

### 根因

EasyPaisa 账户选择路径 `select_accts_http()` 的写入顺序有问题：

1. 先调用 `_update_payment(payment_id, session_data, ...)`。
2. 此时 `session_data.status` 仍是 `accountSelectionRequired`，所以 `_update_payment()` 不会写 `payment.status=1`。
3. 后续才调用 `_update_session_status(..., activeSuccessful, ...)`，只把 Redis session/snapshot 推进到成功态。
4. runtime 在 `accountSelectionRequired` 阶段已经写过 `collect_enabled=false`，`activeSuccessful` 时未显式覆盖，导致继续继承 false。

### 修复

- `select_accts_http()` 在更新 payment 前构造 active 状态的 session 副本，确保 `_update_payment()` 能看到 `status=activeSuccessful` 并写回 `payment.status=1`。
- `_sync_runtime_state()` 在 `activeSuccessful` 分支显式传入：
  - `collect_enabled=True`
  - `ds_order_enabled=True`
  - `df_order_enabled=True`

### 验证

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_select_accts_http_activates_payment_and_runtime_dispatch -v

PYTHONPATH=api python3.12 -m unittest api.tests.test_easypaisa_business_flow_v2 -v
PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_runtime_service -v
```

### 排错口径

以后遇到 EasyPaisa “上号成功但 inactive/不能派单”，先查：

```bash
redis-cli GET easypaisa_runtime:session:{payment_id}
redis-cli GET easypaisa_runtime:snapshot:{payment_id}
mysql -e "SELECT id,status,certified,manual_status,phone,account_accno,account_iban FROM payment WHERE id={payment_id};"
```

如果 session 是 `activeSuccessful`，但 DB `status=0` 或 snapshot `collect_enabled=false`，优先检查账户选择完成后的 active 同步链路，而不是先按人工禁用处理。

## 2026-04-28 JazzCashBusiness loginStep2 冷却期被误判为指纹拒绝

### 现象

JCB 用户完成 OTP、上传指纹后调用 `verify_fingerprint_http`，上游实际进入设备变更冷却期，但本地返回：

```json
{
  "code": "FP_UPSTREAM_REJECTED",
  "phase": "fingerprintUploadRequired"
}
```

采集端随后反复要求用户重新上传指纹，Redis snapshot 里也会出现 `session_phase=fingerprintUploadRequired`。

### 根因

旧实现只把 `_verify_fingerprint()` 当成布尔值：

- `true`：继续 secondLogin 并激活。
- `false`：一律退回 `fingerprintUploadRequired`。

但官方 JazzCash Business App 里设备变更 BVS 流程有独立 cool-down 分支。这里的官方 APK 只作为业务语义证据，不代表我们要直接请求官方接口；我们实际请求的仍是自己的 JazzCashBusiness 上游包装服务：

- APK 字符串中存在 `cooldown_hours=120 Minutes`。
- App 会调用 `account/merchant/bvs/cooldown`。
- 参数包含 `transactionType=bvs-cooldown`、`deviceCoolEnabled=true`、`useCase=deviceChange`。

所以冷却期不是坏指纹，也不是重新采集；它表示指纹/BVS 已经通过，设备注册进入 120 分钟冷却。App 端只消费我们后端 `/api/v1/login/verify_fingerprint` 返回的 `FP_COOLDOWN/cd_until/next_action=wait_cooldown`。

### 修复

- `_verify_fingerprint()` 改为结构化结果：`verified`、`cooldown`、`rejected`、`transient`。
- `cooldown` 分支写入：
  - `status=fingerprintVerified`
  - `cd_until/cooldown_until`
  - `last_error.code=FP_COOLDOWN`
  - 保留 `fingerprint_path`
- 冷却未结束时，`verify_fingerprint_http` 短路返回 `next_action=wait_cooldown`，不打上游。
- 冷却结束后，`verify_fingerprint_http` 看到 `fingerprintVerified + FP_COOLDOWN + cd_until已过` 时直接调用 `secondLogin`，不再重复 `loginStep2`。
- 对旧版本已经写成 `fingerprintUploaded + FP_COOLDOWN + cd_until已过` 的会话，先迁移为 `fingerprintVerified`，再直接调用 `secondLogin`。
- `payment_status_http` 根据 `fingerprintVerified + FP_COOLDOWN + cd_until` 返回 `wait_cooldown`。

### 排查命令

```bash
redis-cli GET pre_login_jazzcash_{payment_id}
redis-cli GET jazzcash_runtime:session:{payment_id}
redis-cli GET jazzcash_runtime:snapshot:{payment_id}
```

正确状态应类似：

```json
{
  "status": "fingerprintVerified",
  "fingerprint_path": "/fingerprint/jazzcash_533280_03001234567.zip",
  "cd_until": 1777330000,
  "last_error": {
    "code": "FP_COOLDOWN"
  }
}
```

### 验证

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest api.tests.test_jazzcash_business_flow_v2 -v
```

## 2026-04-28 API 发布脚本 kubectl apply 返回 Authentication required

### 现象

执行远端 `/opt/cicd/k8s/sh/deploy-api.sh` 时，镜像已成功构建并推送到 Harbor，但发布阶段失败：

```text
Error from server (Forbidden): <html>...Authentication required...</html>
```

### 根因

脚本直接调用 `kubectl apply` 和 `kubectl rollout status`，没有固定 `KUBECONFIG`。在非交互 SSH 环境中，默认 kubeconfig 指到了错误上下文，返回了需要登录的 HTML 页面。

### 修复

远端脚本头部增加默认 kubeconfig：

```bash
export KUBECONFIG=${KUBECONFIG:-/etc/kubernetes/admin.conf}
```

本次镜像 `10.170.0.18:30086/lib/api:20260427165321` 已经推送成功，因此直接用正确 kubeconfig 补应用同一个 YAML：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/api/k8s/api-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/api-deploy -n pk --timeout=180s
KUBECONFIG=/etc/kubernetes/admin.conf kubectl get deploy api-deploy -n pk -o jsonpath='{.spec.template.spec.containers[*].image}'
```

### 验收

- `bash -n /opt/cicd/k8s/sh/deploy-api.sh` 通过。
- `api-deploy` rollout 成功。
- 当前线上镜像为 `10.170.0.18:30086/lib/api:20260427165321`。
