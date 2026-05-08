# API 构建说明

## 当前口径

- API 不再保留 `easypaisa_运行时` / `jazzcash_运行时` 模块。
- EasyPaisa 派单读取 MySQL `collection_status` / `payout_status`。
- JazzCashBusiness 业务逻辑参考 `/Users/tear/pk_project`：使用 `application/jazzcash_gateway.py` 的 v1.6 FormBody 封装、MySQL `wallet_status` / `collection_status` / `payout_status` 作为资格源，不再写 Redis 运行时 session/snapshot/index。
- PayFast 代收、查询和收银台跳转逻辑参考 `/Users/tear/pk_project`。
- D7pay 配置由 `config.example.py` 读取环境变量，K8s 通过 `d7pay-config` 与 `d7pay-secret` 注入。
- API 仓库不再保留 `api/docker-compose.yml`、`api/docker/`、`api/static/v2`、`api/jobs/freecharge-monitor/php/` 和 `*.bak` 备份文件；D7pay 发布以 Jenkins/K8s 为准。
- D7pay 分支不再保留 `api/application/app/login/banks/gcash_bank.py`、`api/application/app/login/banks/indus_bank.py`、`api/jobs/induspay/`、`api/jobs/jio/`、`api/jobs/maha/` 和 tracked Vim swap 文件。
- D7pay 分支不再保留旧印度钱包 service、`api/application/phonepe/`、旧 Redis 维护脚本、Indus/Jio/Maha/ULCASH 旧 SQL 和 PhonePe 静态图标；服务注册表只保留 `EASYPAISA` 与 `JAZZCASH`。
- `api/application/lakshmi_api` 当前仍承载 App `/v1` 登录、上号、订单和 websocket 相关接口，不属于本轮垃圾清理范围。

## 构建检查

```bash
PYTHONPATH=api python3 -m py_compile main.py router.py router_lakshmi.py application/jazzcash_gateway.py application/pay/pay.py application/pay/order.py application/pay/thirdPart.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py jobs/pakistanpay_v2.py jobs/easypaisa/auto_payout.py jobs/easypaisa/easypaisa_monitor.py jobs/jazzcash/jazzcash_auto_payout.py jobs/jazzcash/jazzcash_monitor.py jobs/Jazzcashpay_v2.py
```

## 垃圾残留检查

```bash
test -z "$(git ls-files api/application/phonepe api/jobs/check_proxy.py api/jobs/clear_redis_dsdf.py api/jobs/clear_redis_inactive_payment.py api/jobs/collect_partner_status.py api/jobs/order_push.py api/jobs/weight.py api/static/images/india_transaction/PhonePe.svg)"
test -z "$(git ls-files api/application/lakshmi_api/services/payments/airtel_service.py api/application/lakshmi_api/services/payments/amazon_pay_service.py api/application/lakshmi_api/services/payments/freecharge_service.py api/application/lakshmi_api/services/payments/indus_pay_service.py api/application/lakshmi_api/services/payments/jio_service.py api/application/lakshmi_api/services/payments/maha_service.py api/application/lakshmi_api/services/payments/mobikwik_service.py api/application/lakshmi_api/services/payments/phonepe_service.py api/application/lakshmi_api/services/payments/ulcash_service.py)"
```

## 验收测试

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_easypaisa_mysql_eligibility api.tests.test_easypaisa_wallet_status_dispatch api.tests.test_ep_scan_channel api.tests.test_order_10100_template api.tests.test_jazzcash_gateway_v16 api.tests.test_jazzcash_auto_payout_v16 api.tests.test_jazzcash_request_to_pay_v16
```
