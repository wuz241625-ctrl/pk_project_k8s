# Admin 构建文档

## 推荐方式

从根目录启动：

```bash
cd /Users/tear/pk_project
docker compose up -d admin
```

## 单独运行

`admin/requirements.txt` 与 `api/requirements.txt` 保持一致，K8s Dockerfile 会直接读取 `admin/requirements.txt`。

```bash
cd /Users/tear/pk_project
python3 -m venv .venv
source .venv/bin/activate
pip install -r admin/requirements.txt
cd admin
export RUN_ENV=DEV
export REDIS_HOST=127.0.0.1
export MYSQL_HOST=127.0.0.1
export MYSQL_DATABASE=ospay
export MYSQL_USER=ospay
export MYSQL_PASSWORD=ospay123456
export ADMIN_API_URL=http://127.0.0.1:9000
python main.py --port=6000 --logfile=admin_6000.log
```

## 关键入口

- [main.py](/Users/tear/pk_project/admin/main.py)
- [router.py](/Users/tear/pk_project/admin/router.py)
- [config.py](/Users/tear/pk_project/admin/config.py)

## 线上 K8s

生产环境 Deployment 必须显式设置 `RUN_ENV=PROD`，否则 `config.get_config()` 会按默认值回落到 `DEV`。

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/admin-deploy -- printenv RUN_ENV
```

## 相关测试

真实客户端 IP 与登录日志脱敏测试：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest admin.tests.test_client_ip -v
python3 -m py_compile admin/application/client_ip.py admin/application/base.py
```

后端标签序列化测试：

```bash
cd /Users/tear/pk_project
python3 -m unittest discover -s admin/tests -p 'test_otherpay_option_label.py' -v
```

管理端前端下拉标签测试：

```bash
cd /Users/tear/pk_project/frontend_src/admin
VUE_APP_SYSTEM=OSPay VUE_APP_BASE_API=/prod-api npm run test:unit -- --runInBand tests/unit/utils/otherpay.spec.js
```

本轮 EasyPaisa admin runtime 验证命令：

```bash
cd /Users/tear/pk_project/admin
python3.12 -m py_compile application/easypaisa_runtime/*.py application/partner/partner.py application/order/auto_payout.py
python3.12 -m unittest discover -s tests -v
```

本轮 EasyPaisa admin 锁键语义拆分验证命令：

```bash
cd /Users/tear/pk_project
python3 -m py_compile \
  admin/application/easypaisa_runtime/keyspace.py \
  admin/application/easypaisa_runtime/service.py \
  admin/application/easypaisa_runtime/reader.py

PYTHONPATH=admin python3 -m unittest admin.tests.test_easypaisa_runtime_reader
```

验收重点：

- `admin` 不会把 `easypaisa_runtime:lock:*` 误读成在线状态
- `resettingPayment` / runtime `force_reset()` 会清新锁
- legacy `login_on_easypaisa_*` 仍只作为在线镜像兜底

本轮 `api/admin` EasyPaisa 远端收口里，`admin` 不需要再次同步 `config.py`。fresh 验收重点是：

- 远端这两个目标文件哈希与本地一致：
  - `admin/application/partner/partner.py`
  - `admin/application/order/auto_payout.py`
- `admin` 进程数正常
- `partner.py` 展示的 EasyPaisa 在线态与 `api` runtime 收敛结果一致

注意：

- `payment_active_df` 在当前系统里是 list，不是 set
- `admin/application/order/auto_payout.py` 读取活跃账号数量时必须用 `LLEN` 语义，不能再用 `SCARD`
- `admin/application/order/order.py` 的回队链仍然写 `payment_active_df`，这是有意保留给 `order_push.py` / `jobs/easypaisa/auto_payout.py` 消费的 legacy bridge

本轮实际远端 `ops admin restart` 执行策略：

- 不覆盖 `admin/config.py`
- 不覆盖远端其他未知脏改动
- 只在确认以下文件哈希已与本地一致后执行重启：
  - `admin/application/partner/partner.py`
  - `admin/application/order/auto_payout.py`
  - `admin/application/base.py`
  - `admin/router.py`
  - `admin/application/easypaisa_runtime/__init__.py`
  - `admin/application/easypaisa_runtime/reader.py`

fresh 验收命令：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'ops admin restart'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'ps -ef | grep "/www/python/admin/main.py" | grep -v grep | wc -l'

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'curl -sS -m 10 -o /tmp/admin.out -w "%{http_code}\n" http://127.0.0.1:6000/ && tail -n 20 /www/python/admin/logs/admin_6000.log'
```

本轮实际结果：

- `admin` 进程数：`15`
- `http://127.0.0.1:6000/`：`404`
- `logs` 路径是 `/www/python/admin/logs/admin_6000.log`
- 最新日志尾部是正常业务请求，没有启动级 traceback

## 本轮 `admin` EasyPaisa runtime helper 二次发布

远端发布顺序：

```bash
ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'mkdir -p /www/python/_codex_backup_admin_api_<timestamp> && cp /www/python/admin/application/easypaisa_runtime/service.py /www/python/_codex_backup_admin_api_<timestamp>/service.py && cp /www/python/admin/application/easypaisa_runtime/keyspace.py /www/python/_codex_backup_admin_api_<timestamp>/keyspace.py'

scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  /Users/tear/pk_project/admin/application/easypaisa_runtime/service.py \
  root@34.96.148.205:/www/python/admin/application/easypaisa_runtime/service.py

scp -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no \
  /Users/tear/pk_project/admin/application/easypaisa_runtime/keyspace.py \
  root@34.96.148.205:/www/python/admin/application/easypaisa_runtime/keyspace.py

ssh -i /Users/tear/pk_project/open_ssh_private.txt -o StrictHostKeyChecking=no root@34.96.148.205 \
  'cd /www/python/admin && python -m py_compile application/easypaisa_runtime/keyspace.py application/easypaisa_runtime/service.py application/easypaisa_runtime/reader.py && ops admin restart'
```

远端 fresh 验收重点：

- 只同步：
  - `admin/application/easypaisa_runtime/service.py`
  - `admin/application/easypaisa_runtime/keyspace.py`
- 不同步 `admin/config.py`
- 远端这两个文件 `sha256` 要与本地一致
- `admin` 进程数 `15`
- `http://127.0.0.1:6000/` 返回 `404`
## 2026-04-26 JazzCashBusiness admin 唯一真相源收口

admin 对 JazzCashBusiness `bank_type/bank_type_id=98` 统一读写 `jazzcash_runtime`：

- 列表在线态：`jazzcash_runtime:snapshot:{payment_id}.online`
- 代收态：`ds_order_enabled/dispatch_ds`
- 代付态：`df_order_enabled/dispatch_df`
- 手动监控开关：通过 `JazzCashAdminRuntimeService` 更新 snapshot/index
- 重置下线：清 runtime session/index、legacy 队列、`hash_jazzcash`、`set_jazzcash`

验证命令：

```bash
cd /Users/tear/pk_project_k8s
PYTHONPATH=admin python3.12 -m unittest admin.tests.test_jazzcash_runtime_reader -v

python3.12 -m py_compile \
  admin/application/jazzcash_runtime/*.py \
  admin/application/partner/partner.py
```

验收重点：

- `payment_online_ds/payment_online_df` 残留时，JazzCashBusiness admin 列表不能误显示在线。
- 收款资料筛选 `collect/pay` 合并 runtime index，排除 JazzCashBusiness legacy 脏成员。
- `resettingPayment` 对 JazzCashBusiness 必须调用 `JazzCashAdminRuntimeService.force_reset()`。
