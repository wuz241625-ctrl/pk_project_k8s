# Merchant 排错文档

## 常见问题

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
