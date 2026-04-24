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

## 单独运行

`merchant` 同样复用 API 依赖集。

```bash
cd /Users/tear/pk_project
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
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
