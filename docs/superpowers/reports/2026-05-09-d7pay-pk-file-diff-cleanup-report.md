# D7pay 与 pk_project 文件差异清理报告

## 文件对比结论

本次按文件对比 `api`、`admin`、`merchant` 后端目录，排除 `__pycache__`、`.pytest_cache`、日志、`*.pyc`、`.DS_Store` 等噪声后：

- 共同文件内容不同：42 个。
- 共同文件仅空白或换行不同：39 个。
- pk_project 独有文件：80 个，主要是本地 docker、旧静态资源、runtime SQL 和旧测试。
- D7pay 独有文件：23 个，主要是真实 IP、时区、env 注入和 D7pay 测试。

## 保留差异

- API/Admin/Merchant 的 `application/client_ip.py` 和 `BaseHandler.get_ip()`。
- API/Admin/Merchant 的 `application/timezone.py` 和默认查询日界转换。
- EasyPaisa 账单 `tradeTime` 巴基斯坦时间转 UTC 后匹配 MySQL UTC 订单时间。
- D7pay `config.example.py`、`build.md`、`err.md`、K8s/Jenkins 发布说明和相关测试。

## 15 个指定文件的具体差异

| 文件 | 差异结论 |
| --- | --- |
| `api/jobs/pakistanpay_v2.py` | D7pay 增加 `display_timezone()`，将 EasyPaisa 上游 `tradeTime` 从巴基斯坦时间转 UTC；数据库 `time_create` / `time_accept` 继续按 UTC naive datetime 比较。 |
| `api/application/base.py` | D7pay 改用 `resolve_client_ip()` 解析真实客户端 IP；缓存读取时如果 Redis 缺少请求字段，会刷新 MySQL 数据，避免旧缓存字段不全。 |
| `api/application/app/agent/agent.py` | D7pay 将“今天/本月”等默认时间边界改为 `display_today_between()` / `display_now()`，查询仍落 UTC。 |
| `api/application/app/home/home.py` | D7pay 首页统计默认日界使用 `display_today_between()`。 |
| `api/application/pay/thirdCallback.py` | D7pay 将第三方回调签名时间从硬编码 `Asia/Shanghai` 改为 `display_now()`。 |
| `api/application/third/third_df.py` | D7pay 将代付查询/回调签名时间从硬编码 `Asia/Shanghai` 改为 `display_now()`。 |
| `api/application/websocket/bank_analysis.py` | D7pay 曾残留旧印度钱包解析函数，本次已清理。 |
| `admin/application/base.py` | D7pay 改用真实客户端 IP 解析和请求体脱敏摘要；缓存字段缺失时刷新 MySQL。 |
| `admin/application/count/count.py` | D7pay 今日统计按巴基斯坦展示日界转换为 UTC；余额统计增加空值归零。 |
| `admin/application/merchant/merchant.py` | D7pay 码商统计默认日界使用 `display_today_between()`。 |
| `admin/application/order/order.py` | D7pay 代收/代付/提现默认查询日界使用 `display_today_between()`。 |
| `admin/application/partner/partner.py` | D7pay 代理统计、订单、转账、银行类型统计默认日界使用 `display_today_between()`。 |
| `merchant/application/base.py` | D7pay 改用真实客户端 IP 解析，并记录入口 host、remote_ip、client_ip。 |
| `merchant/application/count/count.py` | D7pay 商户余额流水默认日界使用 `display_today_between()`。 |
| `merchant/application/order/order.py` | D7pay 商户代收/代付/提现默认查询日界使用 `display_today_between()`。 |

## 清理内容

- 删除 `api/application/websocket/bank_analysis.py` 中孤立的旧印度钱包解析函数：`indusind`、`freecharge`、`mobikwik`、`maharastra`。
- 删除 `admin/application/count/collect_partner.py` 中已无路由使用的旧 `getPartner` / `getOnlinePayment` 注释块。
- 修正 `api/application/lakshmi_api/controllers/http_login_controller.py` 的旧 `JioBank` 注释。
- 增加旧印度钱包退役测试，防止这些残留再次回流。

## 验收命令

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_legacy_india_bank_code_retirement -v
python3 -m py_compile api/application/websocket/bank_analysis.py api/application/lakshmi_api/controllers/http_login_controller.py admin/application/count/collect_partner.py
rg -n "async def (indusind|freecharge|mobikwik|maharastra)|导入所有银行模块|jio_bank|payment_online_ds|payment_online_df" api/application admin/application merchant/application --glob '!**/__pycache__/**' --glob '!*.md'
```

结果：

- 旧印度钱包退役测试：`8 tests OK`。
- 编译检查：通过。
- 运行源码关键词扫描：无命中。
- 相关回归分组执行通过：API 17 个、Admin 5 个、Merchant 3 个测试通过。`admin/tests/test_client_ip.py` 与 `merchant/tests/test_client_ip.py` 文件同名，不能放在同一次 pytest collection 里混跑。
