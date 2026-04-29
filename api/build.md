# API 构建文档

## 推荐方式

优先使用根目录统一编排：

```bash
cd /Users/tear/pk_project
docker compose up -d api
```

## 单独运行

依赖来源统一使用 [requirements.txt](/Users/tear/pk_project/api/requirements.txt)。

```bash
cd /Users/tear/pk_project/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export RUN_ENV=DEV
export REDIS_HOST=127.0.0.1
export MYSQL_HOST=127.0.0.1
export MYSQL_DATABASE=ospay
export MYSQL_USER=ospay
export MYSQL_PASSWORD=ospay123456
python main.py --port=9000 --logfile=api_9000.log
```

## 本地验证

本项目测试与语法校验建议显式使用 Python 3.12，避免系统自带 Python 3.9 在收集阶段因 `match` 语法报错。

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile router.py application/pay/order.py application/pay/pay.py application/pay/thirdCallback.py application/pay/thirdPart.py application/pay/easypay_soap.py
python3.12 -m pytest tests/test_router_easypay_cleanup.py tests/test_easypay_soap.py -q
```

## 线上 K8s

生产环境 Deployment 必须显式设置 `RUN_ENV=PROD`，否则 `config.get_config()` 会按默认值回落到 `DEV`。

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/api-deploy -- printenv RUN_ENV
```

## D7pay Jenkins/K8s 发布配置

D7pay 不提交真实 `api/config.py`。Jenkins 应使用 `api/config.example.py` 作为模板，并通过 K8s `d7pay-runtime-config` 与 `d7pay-runtime-secret` 注入：

```bash
API_DOMAIN=<d7pay-api-domain> \
ADMIN_DOMAIN=<d7pay-admin-domain> \
MERCHANT_DOMAIN=<d7pay-merchant-domain> \
APKDOWNLOAD_DOMAIN=<d7pay-apkdownload-domain> \
bash ops/tenants/d7pay/jenkins/deploy-d7pay.sh
```

`runtime-configmap.yaml` 中的 `api.d7pay.example.com` 只是占位。正式发布必须由 Jenkins 注入 D7pay 客户自有域名，不能使用 `awekay.com`。

验收重点：

- `RUN_ENV=PROD`
- `TENANT_CODE=d7pay`
- `MYSQL_DATABASE=pakistan_d7pay`
- `API_OSPAY_API_HOST=http://<d7pay-api-domain>/api`
- `/fingerprint` 挂载到 `d7pay-fingerprint-pvc`

远端 API 发布脚本 `/opt/cicd/k8s/sh/deploy-api.sh` 需要固定 kubeconfig，否则在非交互 SSH 环境可能读到错误的默认上下文并返回登录页 HTML。脚本头部应保留：

```bash
export KUBECONFIG=${KUBECONFIG:-/etc/kubernetes/admin.conf}
```

如果镜像已经构建并推送，但 `kubectl apply` 失败，可以用同一个 YAML 手动补发布：

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f /opt/cicd/k8s/api/k8s/api-deployment.yaml
KUBECONFIG=/etc/kubernetes/admin.conf kubectl rollout status deployment/api-deploy -n pk --timeout=180s
```

真实客户端 IP 白名单/黑名单解析验证：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3 -m unittest api.tests.test_client_ip -v
python3 -m py_compile api/application/client_ip.py api/application/base.py api/application/lakshmi_api/base.py api/application/lakshmi_api/base_ws.py
```

线上 `api.awekay.com` 入口需要宿主机 Nginx 先清洗并重设真实 IP 请求头：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header CF-Connecting-IP "";
```

`api-h5` ConfigMap 的 `/api/` 反代需要继续透传宿主机 Nginx 已清洗的请求头：

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

本轮 EasyPaisa “手机号归属约束”补充验证命令：

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/app/login/banks/easypaisa.py application/easypaisa_runtime/*.py application/lakshmi_api/controllers/upi_controller.py application/lakshmi_api/services/payments/e_wallet_handler.py
python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py tests/easypaisa_runtime -q
```

本轮 EasyPaisa jobs runtime 闭环补充验证命令：

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/easypaisa_runtime/*.py jobs/easypaisa/easypaisa_monitor.py jobs/pakistanpay_v2.py jobs/clear_redis_inactive_payment.py
python3.12 -m pytest tests/easypaisa_runtime/test_sync_runtime_service.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_reader.py tests/test_easypaisa_business_flow_v2.py -q
```

本轮 EasyPaisa 锁键语义拆分补充验证命令：

```bash
cd /Users/tear/pk_project
python3 -m py_compile \
  api/application/app/login/banks/easypaisa.py \
  api/application/easypaisa_runtime/runtime_service.py \
  api/application/easypaisa_runtime/sync_runtime_service.py

PYTHONPATH=api python3 -m unittest \
  api.tests.test_easypaisa_business_flow_v2 \
  api.tests.easypaisa_runtime.test_runtime_service \
  api.tests.easypaisa_runtime.test_sync_runtime_service \
  api.tests.easypaisa_runtime.test_reader \
  api.tests.test_app_my_easypaisa_runtime
```

验收重点：

- 旧 `login_on_easypaisa_*` 不再拦 EasyPaisa 登录
- 新 `easypaisa_runtime:lock:*` 仍然拦重复登录
- `force_offline()` / `_force_logout()` 会把新锁和 legacy 在线镜像一起清掉

本轮 EasyPaisa rollout cleanup 收口补充验证命令：

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/easypaisa_runtime/*.py jobs/easypaisa/easypaisa_monitor.py scripts/easypaisa_runtime_rollout_cleanup.py
python3.12 -m pytest tests/test_easypaisa_runtime_rollout_cleanup.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_reader.py tests/test_easypaisa_business_flow_v2.py -q
```

远端 EasyPaisa 旧状态处理正确顺序：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile application/easypaisa_runtime/*.py jobs/easypaisa/easypaisa_monitor.py scripts/easypaisa_runtime_rollout_cleanup.py'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python scripts/easypaisa_runtime_rollout_cleanup.py'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python scripts/easypaisa_runtime_rollout_cleanup.py --execute'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  '/www/server/panel/pyenv/bin/supervisorctl restart easypaisa_monitor:* pakistanpay_v2:*'
```

这次 cleanup 不能只看 `login_on_easypaisa_*`，还要一起看：

- `hash_easypaisa`
- `set_easypaisa`
- `easypaisa_runtime:index:online`
- `payment_online_df`
- `payment_active_df`

本轮 EasyPaisa 单号保留补充验证命令：

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/easypaisa_runtime/*.py jobs/easypaisa/easypaisa_monitor.py scripts/easypaisa_runtime_retain_accounts.py
python3.12 -m pytest tests/test_easypaisa_account_retention.py tests/test_easypaisa_runtime_rollout_cleanup.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_reader.py tests/test_easypaisa_business_flow_v2.py -q
python3.12 -m unittest discover -s tests -p 'test_app_my_easypaisa_runtime.py' -v
```

远端 EasyPaisa 单号保留执行顺序：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile application/easypaisa_runtime/*.py scripts/easypaisa_runtime_retain_accounts.py'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python scripts/easypaisa_runtime_retain_accounts.py --keep-phone 03045536108'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python scripts/easypaisa_runtime_retain_accounts.py --keep-phone 03045536108 --execute'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  '/www/server/panel/pyenv/bin/supervisorctl restart easypaisa_monitor:* pakistanpay_v2:* auto_payout:*'
```

这次单号保留不能直接看全局：

- `payment_online_df`
- `payment_active_df`

必须只看其中 `bank_type=97` 的 EasyPaisa 子集是否只剩 `533280`。

本轮 EasyPaisa app runtime 闭环补充验证命令：

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/app/my/my.py application/easypaisa_runtime/*.py
python3.12 -m unittest discover -s tests -p 'test_app_my_easypaisa_runtime.py' -v
python3.12 -m unittest discover -s tests -v
```

补充说明：

- `application/app/my/my.py` 对 EasyPaisa `bank_type=97` 改读 runtime snapshot
- `my.getpayment` / `my.getOnlinePayment` 不再把 EasyPaisa 真相建立在 `payment_online_ds` / `payment_online_df` 上
- `my.changepayment(status=0)` 会同步清 `easypaisa_runtime:session:*` 并把 snapshot 强制改成 offline

本轮 EasyPaisa runtime 第 1 步上线前约束：

```bash
cd /Users/tear/pk_project/api
python3.12 scripts/easypaisa_session_flush.py --execute
```

- 旧 `pre_login_easypaisa_*` / `login_on_easypaisa_*` 会话不兼容
- 发布前必须先 flush，再允许新登录链写入 runtime snapshot
- `order_push.py` 与 `jobs/easypaisa/auto_payout.py` 仍通过 legacy bridge 消费 `payment_active_df` / `payment_online_df`
- `clear_redis_dsdf.py` 当前扫描的 `bank_type in (16,14,17,21,30)` 不包含 EasyPaisa `bank_type_id=97`，本轮只做审计，不作为 EasyPaisa cleanup 主入口

本轮 EasyPaisa 全量状态统一 fresh 验证命令：

```bash
cd /Users/tear/pk_project/api
python3.12 -m py_compile application/easypaisa_runtime/*.py application/pay/pay.py application/lakshmi_api/controllers/upi_controller.py application/app/my/my.py jobs/pakistanpay_v2.py jobs/easypaisa/easypaisa_monitor.py
python3.12 -m pytest tests/easypaisa_runtime/test_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py tests/easypaisa_runtime/test_reader.py tests/test_easypaisa_runtime_rollout_cleanup.py tests/test_easypaisa_account_retention.py tests/test_easypaisa_business_flow_v2.py -q
python3.12 -m unittest discover -s tests -p 'test_app_my_easypaisa_runtime.py' -v
```

本轮收口重点：

- `runtime snapshot + INDEX_*` 是 EasyPaisa 唯一真相源
- `dispatch_df` 表示代付/接单在线
- `dispatch_ds` 表示采集/代收在线
- `snapshot.channels` 保存 EasyPaisa 应投影到哪些 `payment_active_{channel}`
- `payment_online_df` / `payment_online_ds` / `payment_active_{channel}` / `login_on_easypaisa_*` / `hash_easypaisa` / `set_easypaisa` 全部是 runtime 派生投影

验收重点：

- `selling_order_status` / `my.getpayment.online_ds` 只跟 `dispatch_ds` 一致
- `place_order_status` / `online_df` 只跟 `dispatch_df` 一致
- `dispatch_ds=false` 时，EasyPaisa 不允许继续代收分单
- `dispatch_ds=true` 且 `snapshot.channels=["1001"]` 时，必须进入 `payment_active_1001`
- `force_offline()` / retention / rollout cleanup 会一起清：
  - `payment_online_ds`
  - `INDEX_DISPATCH_DS`
  - `payment_active_{channel}`
  - `hash_easypaisa`
  - `set_easypaisa`

本轮 EasyPaisa `payment_active_1001` 闭环补充验证命令：

```bash
cd /Users/tear/pk_project
python3.12 -m py_compile \
  api/application/easypaisa_runtime/runtime_service.py \
  api/application/lakshmi_api/services/payments/e_wallet_handler.py \
  api/jobs/pakistanpay_v2.py \
  admin/application/easypaisa_runtime/keyspace.py \
  admin/application/easypaisa_runtime/service.py

PYTHONPATH=api python3.12 -m unittest \
  api.tests.easypaisa_runtime.test_runtime_service \
  api.tests.easypaisa_runtime.test_sync_runtime_service \
  api.tests.test_easypaisa_collection_runtime_toggle \
  api.tests.test_app_my_easypaisa_runtime \
  api.tests.easypaisa_runtime.test_reader -v

python3.12 -m unittest discover -s admin/tests -p 'test_easypaisa_runtime_reader.py' -v

cd /Users/tear/pk_project/api
python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py -q
```

验收重点：

- `selling_active/selling_inactive` 会即时同步 EasyPaisa runtime `dispatch_ds`
- admin `force_reset` 会一起清 `payment_online_ds` 与 `payment_active_{channel}`
- `423 云机正忙查单` 不再误触发 `on_off(_on=0)`，不会把账号踢出 `payment_active_1001`
- `easypaisa_monitor` 对数据库仍允许接单的账号，在线恢复时会显式回写 `dispatch_ds=true`
- 不能再出现“账号已经恢复在线，但 snapshot 仍永久卡在 `dispatch_ds=false`”

本轮 EasyPaisa `dispatch_ds` 自动恢复补充验证命令：

```bash
cd /Users/tear/pk_project
PYTHONPATH=api python3.12 -m unittest \
  api.tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaMonitorRuntimeIntegrationTests -v

PYTHONPATH=api python3.12 -m unittest \
  api.tests.easypaisa_runtime.test_sync_runtime_service \
  api.tests.easypaisa_runtime.test_runtime_service \
  api.tests.test_easypaisa_collection_runtime_toggle -v

cd /Users/tear/pk_project/api
python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py -q
```

如果要对数据库结构做同样的约束落地，迁移文件是：

- [20260418190000_add_payment_bank_phone_unique/migration.sql](/Users/tear/pk_project/api/migrations/20260418190000_add_payment_bank_phone_unique/migration.sql)

线上 fresh 验证唯一键与重复组的命令：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 <<'SSH'
mysql -h10.108.32.29 -upakistan -p'HFCCoB$D7]{?NTNn' -Dpakistan -Nse "
SELECT COUNT(*) FROM (
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

线上执行 `ops api restart` 前，必须先在远端做一次编译检查，避免把语法错误版本直接重启上线：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile application/app/login/banks/easypaisa.py application/lakshmi_api/models/payment.py'
```

注意：

- 线上 `ops` 脚本调用的是 `python`，不是 `python3`
- 当前线上 `python=3.12.0`，`python3=3.10.12`
- 所以重启前验收必须用 `python -m py_compile`

本轮 EasyPaisa runtime 收口如果要真正让线上 `ops api restart` 用上最新代码，正确顺序是：

```bash
scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  api/application/easypaisa_runtime/account_retention.py \
  api/application/easypaisa_runtime/keyspace.py \
  api/application/easypaisa_runtime/legacy_bridge.py \
  api/application/easypaisa_runtime/reader.py \
  api/application/easypaisa_runtime/rollout_cleanup.py \
  api/application/easypaisa_runtime/runtime_service.py \
  api/application/easypaisa_runtime/sync_runtime_service.py \
  root@34.96.148.205:/www/python/api/application/easypaisa_runtime/

scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  api/application/pay/pay.py \
  root@34.96.148.205:/www/python/api/application/pay/pay.py

scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  api/application/lakshmi_api/controllers/upi_controller.py \
  root@34.96.148.205:/www/python/api/application/lakshmi_api/controllers/upi_controller.py

scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  api/jobs/pakistanpay_v2.py \
  root@34.96.148.205:/www/python/api/jobs/pakistanpay_v2.py

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile application/easypaisa_runtime/*.py application/pay/pay.py application/lakshmi_api/controllers/upi_controller.py jobs/pakistanpay_v2.py jobs/easypaisa/easypaisa_monitor.py'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'ops api restart'
```

本轮实际 fresh 结果：

- `api` 进程数：`30`
- `http://127.0.0.1:9000/`：`404`
- `logs` 路径是 `/www/python/api/logs/api_9000.log`
- 上述白名单文件哈希全部已与本地一致

## 2026-04-19 EasyPaisa 回调修复验证

本地验证：

```bash
cd /Users/tear/pk_project/api
python3 -m py_compile jobs/pakistanpay_v2.py application/easypaisa_runtime/sync_runtime_service.py tests/easypaisa_runtime/test_sync_runtime_service.py
python3 -m pytest tests/easypaisa_runtime/test_sync_runtime_service.py -q
```

验收点：

- `send()` 会优先走 `http://127.0.0.1:9000/order/Success`
- 只有内部地址缺失时，才会把 `http://host/api` 规整成 `http://host/order/Success`
- `transaction_callback()` 失败时不会写 `if_callback_easypaisa`
- `sync_collection_job_state()` 不会用瘦 `login_data` 覆盖已有完整 `hash_easypaisa`
- 公网域名的 `/api` 路由保持不变，不能为修 job 内部回调而全局删除

线上验证：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'source /www/server/panel/pyenv/bin/activate && cd /www/python/api && python -m py_compile jobs/pakistanpay_v2.py application/easypaisa_runtime/sync_runtime_service.py'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  '/www/server/panel/pyenv/bin/supervisorctl restart pakistanpay_v2:*'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  '/www/server/panel/pyenv/bin/supervisorctl status pakistanpay_v2:*'
```

若需要核对公网域名 `api.aweces.com` 是否已正确挂到 API：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  "python - <<'PY'
import requests
for url in [
    'https://api.aweces.com/api/order/Success',
    'https://api.aweces.com/order/Success',
]:
    r = requests.post(url, timeout=15, verify=False, allow_redirects=False)
    print(url, r.status_code)
PY"
```

验收点：

- `https://api.aweces.com/api/order/Success` 返回 `200`
- `https://api.aweces.com/order/Success` 返回 `404`
- `server_name` 中必须显式包含 `api.aweces.com`

超窗订单补单顺序：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  "curl -sS -X POST http://127.0.0.1:9000/order/Success \
    --data-urlencode 'type=New' \
    --data-urlencode 'bank_name=easypaisa' \
    --data-urlencode 'payment_id=<payment_id>' \
    --data-urlencode 'partner_id=<partner_id>' \
    --data-urlencode 'amount=<amount>' \
    --data-urlencode 'utr=<utr>' \
    --data-urlencode 'trade_type=CREDIT' \
    --data-urlencode 'status=SUCCESS' \
    --data-urlencode 'account=<account>' \
    --data-urlencode 'trans_id=<trans_id>'"

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  "curl -sS -X POST http://127.0.0.1:9000/pay/ds/utr \
    --data-urlencode 'mer_id=<merchant_id>' \
    --data-urlencode 'order_id=<merchant_code>' \
    --data-urlencode 'utr=<utr>' \
    --data-urlencode 'trans_id=<trans_id>' \
    --data-urlencode 'sign=<md5_sign>'"
```

说明：

- 第一步会先把流水写进 `bank_record(callback=0)`。
- 第二步走正式商户 UTR 补单链路，适用于 `/order/Success` 因 8 分钟窗口超时而无法直接关单的场景。

## 关键入口

- [main.py](/Users/tear/pk_project/api/main.py)
- [router.py](/Users/tear/pk_project/api/router.py)
- [router_lakshmi.py](/Users/tear/pk_project/api/router_lakshmi.py)
- [config.py](/Users/tear/pk_project/api/config.py)

## 线上 EasyPaisa `auto_payout` 定点发布

这个任务在线上不是走 `ops api restart`，而是走 supervisor。

发布顺序：

```bash
scp api/jobs/easypaisa/auto_payout.py root@<host>:/www/python/api/jobs/easypaisa/auto_payout.py
scp api/jobs/easypaisa/scheduling_state.py root@<host>:/www/python/api/jobs/easypaisa/scheduling_state.py
ssh root@<host> 'python3 -m py_compile /www/python/api/jobs/easypaisa/auto_payout.py /www/python/api/jobs/easypaisa/scheduling_state.py'
ssh root@<host> '/www/server/panel/pyenv/bin/supervisorctl restart auto_payout:*'
```

不要误用：

```bash
/usr/local/bin/ops api restart
```

上面这个只会重启 Web API 进程，不会重启 `auto_payout`。

## 2026-04-20 EasyPaisa `Fingerprint data corruption` API 热修发布

适用场景：

- 上游 `verifyFingerprint` 返回：

```json
{"code":403,"msg":"读取<phone>指纹数据失败，请检查指纹数据包(Fingerprint data corruption)","data":null}
```

- 目标是把这类坏包错误从 `FP_UPSTREAM_TRANSIENT` 改判为 `FP_UPSTREAM_REJECTED`
- 发布要求是 API 无中断，不允许整组 `kill + nohup`

本地验证：

```bash
cd /Users/tear/pk_project
python3 -m unittest api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_perform_verify_fingerprint_corruption_maps_to_rejected -v
python3 -m unittest api.tests.test_easypaisa_business_flow_v2 -v
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

同步线上文件后，先编译检查：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  "python -m py_compile /www/python/api/application/app/login/banks/easypaisa.py"
```

API 滚动重启：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 '
for port in $(seq 9000 9029); do
  pid=$(ps -ef | awk "/main.py --port=${port} / && !/awk/ {print \$2; exit}")
  [ -n "$pid" ] && kill -TERM "$pid"
  nohup python /www/python/api/main.py --port=${port} --logfile=api_${port}.log >/dev/null 2>&1 &
  sleep 1
  ss -lnt | grep -q ":${port} " || exit 1
done
'
```

线上验收：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  "ss -lnt | awk '\$4 ~ /:900[0-9]\$/ || \$4 ~ /:90[1-2][0-9]\$/ {print \$4}' | sort | uniq | wc -l"

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  "curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9000/"
```

验收点：

- `9000-9029` 共 `30` 个端口全部恢复监听
- 没有 API 整组同时消失的窗口
- 同类坏包场景会回到 `FP_UPSTREAM_REJECTED -> fingerprintUploadRequired`

## Easypay SOAP 代收配置

首次部署需在数据库执行 `mysql.sql` 末尾的 otherpay INSERT 语句，为 1002 通道添加 Easypay SOAP 配置。
当前商户后台名称为 `AbdulMoizE-Store`。
字段映射固定为：`merchant_id=Account ID`、`key=Merchant Name`、`key2=API Key`、`key3=Store ID`。
不要把商户后台登录密码误填到 `key2`。
无新增 pip 依赖（aiohttp/requests 已有）。

## 线上 `1002` 误命中 JazzCash 自有码商时的修复顺序

如果线上日志里仍出现：

- `按照权重随机选取码接单: 533182`
- `码 533182 在 Redis 队列 'payment_active_1002' 中`

不要只清一个 Redis 列表，正确顺序是：

1. 备份 `payment` 命中记录与 Redis 运行态
2. 批量把 `payment.channel` 从 `1002,1003` 改成 `1003`
3. 把 `hash_jazzcash.qr_channel` 从 `1002,1003` 改成 `1003`
4. 清空：
   - `payment_active_1002`
   - `payment_active_1002,1003`
5. 重启：

```bash
/www/server/panel/pyenv/bin/supervisorctl restart jazzcashv2:* pakistanpay_v2:*
```

6. fresh 复查：
   - `payment.id=533182.channel = '1003'`
   - `hash_jazzcash['533182'].qr_channel = '1003'`
   - `payment_active_1002 = []`
   - 如果前两项已对，但 `payment_active_1002` 还有成员，说明 Redis 留着历史脏数据，需要继续 `LREM`

7. 同步代码防回归：
   - [jazzcash.py](/Users/tear/pk_project/api/application/app/login/banks/jazzcash.py) 的默认 `qr_channel/channel` 改为 `1003`
   - 并 fresh 重启 `api`

8. 只用 `196` 测试商户 fresh 拉 `1002` 新单验收：
   - `payment_id` 必须为 `NULL`
   - `otherpay=25`
   - `third_party_name=easypay`

## 本轮 EasyPaisa `account_iban` 回填补充验证

本地验证命令：

```bash
cd /Users/tear/pk_project
PYTHONPATH=api python3.12 -m unittest \
  api.tests.easypaisa_runtime.test_sync_runtime_service.EasyPaisaMonitorRuntimeIntegrationTests -v

PYTHONPATH=api python3.12 -m unittest \
  api.tests.easypaisa_runtime.test_sync_runtime_service \
  api.tests.easypaisa_runtime.test_runtime_service \
  api.tests.test_easypaisa_collection_runtime_toggle -v

cd /Users/tear/pk_project/api
python3.12 -m pytest tests/test_easypaisa_business_flow_v2.py -q
```

远端发布顺序：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'mkdir -p /www/python/_codex_backup_admin_api_<timestamp> && cp /www/python/api/jobs/easypaisa/easypaisa_monitor.py /www/python/_codex_backup_admin_api_<timestamp>/easypaisa_monitor.py'

scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  /Users/tear/pk_project/api/jobs/easypaisa/easypaisa_monitor.py \
  root@34.96.148.205:/www/python/api/jobs/easypaisa/easypaisa_monitor.py

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/api && python -m py_compile jobs/easypaisa/easypaisa_monitor.py && ops api restart && /www/server/panel/pyenv/bin/supervisorctl restart easypaisa_monitor:* pakistanpay_v2:*'
```

远端 fresh 验收重点：

- `api` 进程数 `30`
- `http://127.0.0.1:9000/` 返回 `404`
- `easypaisa_monitor:*` / `pakistanpay_v2:*` 全部 `RUNNING`
- `easypaisa_runtime:snapshot:533280.selected_iban` 已不再是 `null`
- `hash_easypaisa[533280].account_iban` 已不再是空串

## 2026-04-26 JazzCash OTP 后指纹验证链路

本轮目标：

- JazzCash 上号固定为：`pre_login -> get_otp -> verify_otp -> upload_fingerprint/verify_fingerprint -> activeSuccessful`
- JazzCash 上游没有独立“验证 OTP”能力：`verify_otp` 只做本地 OTP 提交检查和 session 推进，不调用上游 `loginStep2`
- `/api/v1/login/verify_fingerprint` 支持 `bankname=jazzcash`，内部使用上游 `loginStep2` 验证指纹，成功后完成 secondLogin、更新 `payment`、写 Redis 在线队列
- 旧 `/api/v1/login/active_account` 暂保留兼容，但新 App 不再调用

本地验证命令：

```bash
cd /Users/tear/pk_project_k8s
python3.12 -m unittest api.tests.test_jazzcash_business_flow_v2 -v
python3.12 -m unittest api.tests.test_easypaisa_business_flow_v2 api.tests.test_jazzcash_business_flow_v2 api.tests.test_jazzcash_auto_payout -v
python3.12 -m py_compile \
  api/application/app/login/banks/jazzcash.py \
  api/application/lakshmi_api/controllers/http_login_controller.py \
  api/jobs/jazzcash/jazzcash_auto_payout.py
```

验收重点：

- JazzCash `JAZZCASH_API_VERSION` 必须是 `v1.5`
- JazzCash 不配置上游 `verify_fingerprint` action；指纹验证请求必须使用 `action=loginStep2`
- `loginStep2` 是指纹校验入口，当前业务不在这里校验 OTP；payload 必须显式传：

```json
{
  "account_id": "03xxxxxxxxx",
  "otpcode": "123456",
  "should_verify_otpcode": false,
  "should_verify_fingerprint": true
}
```

- `verify_otp_http()` 返回 `data.next_phase`，不能返回 `next_step=active_account`
- `verify_otp_http()` 不能调用 JazzCash 上游，也不能调用 `_verify_account()`
- OTP 后上传指纹时 Redis session 从 `fingerprintUploadRequired` 进入 `fingerprintUploaded`
- OTP 提交后 Redis session 必须保留 `otpcode`，供后续 `loginStep2` 透传；但 `should_verify_otpcode=false` 仍表示上游不在该步骤校验 OTP
- `verify_fingerprint_http()` 成功后 Redis session 为 `activeSuccessful`
- 代付 `transferToAcc/transferToCard` 返回 `code=500` 时不能直接按失败或驳回处理，必须进入 `pending_reconciliation`/待核查，订单置 `status=2`，`sys_remark` 写入待核查原因，但不设置 `payment_id` 失败冷却

## 2026-04-26 API 回调域名缓存

本轮目标：

- PROD `ospay_api_host` 固定为当前服务器入口：`http://api.awekay.com/api`
- PROD `pay_url` 固定为当前服务器收银台入口：`http://api.awekay.com/api/order/`
- PROD `websocket_api_allow_host` 只保留当前 API 域名：`api.awekay.com`
- API 启动时若 Redis `notice_domain_api_list` 为空，自动写入 `ospay_api_host`
- JazzCash/EasyPaisa job 统一通过 `conf.get('ospay_api_host')` 读取 dict 配置，避免误回退到 localhost
- 若后台已经维护了 `notice_domain_api_list`，启动初始化不覆盖已有值

本地验证命令：

```bash
cd /Users/tear/pk_project_k8s
python3.12 -m py_compile \
  api/main.py \
  api/config.example.py \
  api/jobs/Jazzcashpay_v2.py \
  api/jobs/jazzcash/jazzcash_monitor.py \
  api/jobs/easypaisa/easypaisa_monitor.py
```

线上验收命令：

```bash
REDIS_POD=$(kubectl get pods -n pk -l app=redis -o jsonpath='{.items[0].metadata.name}')
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

期望结果：

- Redis `notice_domain_api_list` 为 `http://api.awekay.com/api`
- 容器内 `get_config()['ospay_api_host']` 为 `http://api.awekay.com/api`
- 容器内 `get_config()['pay_url']` 为 `http://api.awekay.com/api/order/`
- 容器内 `get_config()['websocket_api_allow_host']` 为 `['api.awekay.com']`

## 2026-04-26 API 指纹持久化挂载

背景：

- EasyPaisa/JazzCash 指纹 zip 统一保存到 `/fingerprint`
- 当前测试集群没有 RWX StorageClass，只有手工 RWO PV
- 为避免两个 API Pod 跨节点读不到同一份本地文件，API 固定调度到 `pk-1`

持久化清单：

```bash
cd /Users/tear/pk_project_k8s
kubectl apply -f ops/k8s/api-fingerprint-persistence.yaml
```

线上 Deployment 需要包含：

```yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/hostname: pk-1
      containers:
      - name: api
        volumeMounts:
        - name: fingerprint-storage
          mountPath: /fingerprint
      volumes:
      - name: fingerprint-storage
        persistentVolumeClaim:
          claimName: api-fingerprint-pvc
```

验收命令：

```bash
kubectl get pv api-fingerprint-pv
kubectl get pvc api-fingerprint-pvc -n pk
kubectl get pods -n pk -l app=api -o wide
kubectl exec -n pk deploy/api-deploy -- sh -lc 'mount | grep " /fingerprint "'
```

指纹保存路径回归测试：

```bash
python3 -m unittest api.tests.test_jazzcash_business_flow_v2.JazzCashBusinessFlowV2Tests.test_save_fingerprint_uses_root_fingerprint_mount_dir -v
python3 -m unittest api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_save_fingerprint_uses_root_fingerprint_mount_dir -v
```

期望：

- `api-fingerprint-pvc` 为 `Bound`
- API Pod 均调度在 `pk-1`
- 指纹目录挂载点存在，发布重建 Pod 后测试文件仍保留
## 2026-04-26 JazzCashBusiness 唯一真相源收口

本轮 JazzCashBusiness 运行态统一改为：

- 主真相源：`jazzcash_runtime:snapshot:{payment_id}`
- 索引：`jazzcash_runtime:index:online`、`jazzcash_runtime:index:ds_order_enabled`、`jazzcash_runtime:index:df_order_enabled`
- 派生投影：`payment_online_ds`、`payment_online_df`、`payment_active_df`、`payment_active_{channel}`、`login_on_jazzcash_*`

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.test_order_push_easypaisa_runtime_guard -v

python3.12 -m py_compile \
  api/application/app/login/banks/jazzcash.py \
  api/application/app/my/my.py \
  api/application/lakshmi_api/controllers/upi_controller.py \
  api/application/lakshmi_api/services/payments/e_wallet_handler.py \
  api/application/pay/pay.py \
  api/jobs/order_push.py \
  api/jobs/Jazzcashpay_v2.py \
  api/jobs/jazzcash/jazzcash_monitor.py \
  api/jobs/jazzcash/jazzcash_auto_payout.py
```

验收重点：

- JazzCashBusiness `bank_type/bank_type_id=98` 不能直接信任 legacy Redis 在线队列。
- `sendOtp -> verifyOtp -> uploadFingerprint -> verifyFingerprint -> activeSuccessful` 的会话会写入 `jazzcash_runtime:session:{payment_id}`。
- 激活成功必须通过 `JazzCashRuntimeService.mark_active_successful()` 写 snapshot/index，再由 legacy bridge 派生旧队列。
- 代收判断读 `dispatch_ds/ds_order_enabled`，代付判断读 `dispatch_df/df_order_enabled`。
- `order_push.py`、`jazzcash_auto_payout.py`、`jazzcash_monitor.py` 只能把旧 `payment_active_df/payment_online_df` 当兼容投影消费，主状态必须以 runtime 为准。

## 2026-04-26 JazzCashBusiness 唯一真相源补漏验收

本轮补齐 websocket monitor、订单超时回队和代收回队的剩余入口：

- `bank_type/bank_type_id=98` 的 websocket ds/df 上下线必须调用 `JazzCashRuntimeService`。
- `time_out.py` 对 JazzCashBusiness 回队必须检查 `jazzcash_runtime:index:dispatch_ds`。
- `pay.py` 代收回队对 JazzCashBusiness 只认 `jazzcash_runtime:kickoff:{payment_id}`，不再被 legacy `kick_off_{payment_id}` 脏 key 误拦。

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_jazzcash_business_flow_v2 \
  api.tests.test_websocket_monitor_ep_dispatch \
  api.tests.test_time_out_guard \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.test_order_push_easypaisa_runtime_guard -v

python3.12 -m py_compile \
  api/application/jazzcash_runtime/*.py \
  api/application/websocket/monitor.py \
  api/application/pay/pay.py \
  api/jobs/time_out.py
```

验收重点：

- snapshot 缺失时，JazzCashBusiness 默认不能因为 `payment_online_ds/payment_online_df` 残留而继续接单。
- `jazzcash_runtime:index:dispatch_ds` 是 JazzCashBusiness 超时回队的唯一准入索引。
- legacy `kick_off_*` 只影响非 runtime 银行；JazzCashBusiness 必须以 runtime kickoff key 为准。

## 2026-04-26 JazzCashBusiness 采集端唯一真相源验收

本轮收口 `api/jobs/Jazzcashpay_v2.py`：

- `hash_jazzcash` / `set_jazzcash` 只作为采集 job 投影，不再作为主真相源。
- `pre_login_jazzcash_*` 的 `activeSuccessful` 推进必须调用 `SyncJazzCashRuntimeService.sync_collection_job_state()`。
- worker 采集前必须确认 `jazzcash_runtime:snapshot:{payment_id}` 仍为 `online=true` 且 `collect_enabled=true`。
- JazzCashBusiness 代付必须依赖采集能力；`collect_enabled=false` 时 DS/DF 必须同时关闭，避免上游代付异常时无法采集账单对账。

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.jazzcash_runtime.test_sync_collection_worker \
  api.tests.test_jazzcash_business_flow_v2 -v

python3.12 -m py_compile \
  api/application/jazzcash_runtime/sync_runtime_service.py \
  api/jobs/Jazzcashpay_v2.py
```

验收重点：

- runtime 禁采时，旧 `hash_jazzcash` / `set_jazzcash` 残留不会触发上游账单接口。
- `payment.status/certified` 不满足接单时仍保留采集，但关闭代收/代付派单。
- 旧 `login_off_jazzcash_*` 只作为清理标记，不再覆盖 runtime 主状态。

## 2026-04-27 EasyPaisa activeSuccessful 同步验收

本轮修复 EasyPaisa 账户选择完成后，Redis session 已进入 `activeSuccessful` 但 DB/runtime 业务开关没有同步恢复的问题。

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest \
  api.tests.test_easypaisa_business_flow_v2.EasyPaisaBusinessFlowV2Tests.test_select_accts_http_activates_payment_and_runtime_dispatch -v

PYTHONPATH=api python3.12 -m unittest api.tests.test_easypaisa_business_flow_v2 -v
PYTHONPATH=api python3.12 -m unittest api.tests.easypaisa_runtime.test_runtime_service -v
```

验收重点：

- `select_accts_http()` 更新 payment 时必须携带 `status=activeSuccessful`，从而写回 `payment.status=1`。
- `login_flow` 写入 `activeSuccessful` runtime snapshot 时必须显式恢复 `collect_enabled/ds_order_enabled/df_order_enabled`。
- 如果后台或 App 后续手动禁用、人工锁定、健康暂停，仍由对应开关入口关闭派单，不改变本轮默认激活语义。

## 2026-04-28 JazzCashBusiness 冷却期流程验收

本轮修复 JCB `loginStep2` 设备冷却期被误判为指纹拒绝的问题。`loginStep2` 返回冷却表示指纹/BVS 已通过，冷却期应保持 `fingerprintVerified`，保留 `/fingerprint` 中已上传的指纹文件，等待 `cd_until` 后直接执行 `secondLogin`。

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest api.tests.test_jazzcash_business_flow_v2 -v

PYTHONPATH=api python3.12 -m unittest \
  api.tests.jazzcash_runtime.test_runtime_service \
  api.tests.jazzcash_runtime.test_reader \
  api.tests.jazzcash_runtime.test_sync_collection_worker -v

python3.12 -m py_compile \
  api/application/app/login/banks/jazzcash.py \
  api/application/jazzcash_runtime/runtime_service.py \
  api/application/jazzcash_runtime/reader.py \
  api/application/jazzcash_runtime/sync_runtime_service.py

git diff --check
```

验收重点：

- `loginStep2` 返回冷却期时，session/runtime snapshot 都保持 `fingerprintVerified`。
- `last_error.code=FP_COOLDOWN` 且 `cd_until` 未到时，`payment_status_http.next_action=wait_cooldown`。
- 冷却期间重复调用 `verify_fingerprint_http` 不再打上游。
- 冷却结束后继续复用同一份 `fingerprint_path`，直接调用 `secondLogin`，不再重复 `loginStep2`。
- 不兼容旧的 `fingerprintUploaded + FP_COOLDOWN` 冷却会话；这种状态到期后仍按普通 `fingerprintUploaded` 流程重新走 `loginStep2`。
- 明确指纹被上游拒绝时仍按 `FP_UPSTREAM_REJECTED` 要求重新上传。

## 2026-04-28 JazzCashBusiness loginStep2 冷却表示指纹已验证

补充语义：

- 上游没有独立 `verifyFingerprint` action，我方 `/api/v1/login/verify_fingerprint` 只是 App 入口名。
- `loginStep2` 返回 `JC-CPS-COOL-T01` 代表指纹/BVS 已通过，只是设备注册进入 120 分钟冷却。
- 冷却期唯一真相源为 `fingerprintVerified + FP_COOLDOWN + cd_until`。
- `cd_until` 之前不请求上游；`cd_until` 之后直接 `secondLogin`。

## 2026-04-28 JazzCashBusiness activeSuccessful 清理旧错误验收

本轮处理 `03409297123 / payment_id=533298` 时确认：旧代码曾把 `loginStep2` 冷却期折叠成 `FP_UPSTREAM_REJECTED`，但当前 `secondLogin` 已能成功返回账户信息。账号补推进到 `activeSuccessful` 后，runtime snapshot 不能继续继承旧 `last_error/cd_until/cooldown_until`。

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=api python3.12 -m unittest api.tests.jazzcash_runtime.test_runtime_service -v

python3.12 -m py_compile api/application/jazzcash_runtime/runtime_service.py
git diff --check
```

验收重点：

- `JazzCashRuntimeService.mark_active_successful()` 写入 `activeSuccessful` 时必须清空 `last_error`。
- `cd_until/cooldown_until` 必须归零，避免 App 状态轮询把已上线账号误展示成冷却或错误。
- `session_expires_at` 必须刷新为当前时间加 `online_ttl`，避免 snapshot 保留过期会话时间。
