# Merchant 构建文档

## 推荐方式

从根目录启动：

```bash
cd /Users/tear/pk_project
docker compose up -d merchant
```

如果要从本机浏览器直接验证商户后台，还要确认运行库里的 `merchant.ip` 白名单放行本地入口 IP，常见值包括：

- `172.17.0.1`
- `172.18.0.1`
- `127.0.0.1`

否则登录和订单查询会直接返回 `403 ip 禁止登录`。

真实客户端 IP 白名单测试：

```bash
cd /Users/tear/pk_project_k8s
python3 -m unittest merchant.tests.test_client_ip -v
python3 -m py_compile merchant/application/client_ip.py merchant/application/base.py
```

## 单独运行

`merchant/requirements.txt` 与 `api/requirements.txt` 保持一致，K8s Dockerfile 会直接读取 `merchant/requirements.txt`。

```bash
cd /Users/tear/pk_project
python3 -m venv .venv
source .venv/bin/activate
pip install -r merchant/requirements.txt
cd merchant
export RUN_ENV=DEV
export REDIS_HOST=127.0.0.1
export MYSQL_HOST=127.0.0.1
export MYSQL_DATABASE=ospay
export MYSQL_USER=ospay
export MYSQL_PASSWORD=ospay123456
export MERCHANT_API_URL=http://127.0.0.1:9000
python main.py --port=8000 --logfile=merchant_8000.log
```

## 关键入口

- [main.py](/Users/tear/pk_project/merchant/main.py)
- [router.py](/Users/tear/pk_project/merchant/router.py)
- [config.py](/Users/tear/pk_project/merchant/config.py)

## 线上 K8s

生产环境 Deployment 必须显式设置 `RUN_ENV=PROD`，否则 `config.get_config()` 会按默认值回落到 `DEV`。

```bash
KUBECONFIG=/etc/kubernetes/admin.conf kubectl exec -n pk deploy/merchant-deploy -- printenv RUN_ENV
```

## D7pay Jenkins/K8s 发布配置

D7pay 不提交真实 `merchant/config.py`。Jenkins 应使用 `merchant/config.example.py` 作为模板，并通过 K8s `d7pay-runtime-config` 与 `d7pay-runtime-secret` 注入：

```bash
kubectl patch deployment merchant-deploy -n pk-d7pay --type=strategic --patch-file ops/tenants/d7pay/k8s/merchant-deployment-env.patch.yaml
```

验收重点：

- `RUN_ENV=PROD`
- `TENANT_CODE=d7pay`
- `MYSQL_DATABASE=pakistan_d7pay`
- `MERCHANT_API_URL=http://api:9000`
