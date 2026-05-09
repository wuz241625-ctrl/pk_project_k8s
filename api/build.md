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

## PK 模块化业务同步检查

D7pay 已同步 `/Users/tear/pk_project` 的 API pay 模块拆分、EasyPaisa/JazzCash 代付 worker 拆分和旧 HTTP 兼容层清理。同步后必须保留 D7pay 租户配置，不允许覆盖 `ops/tenants/d7pay`、K8s、Jenkins、APK 下载站和 `config.example.py`。

```bash
python3 -m py_compile api/application/pay/pay.py api/application/pay/collection.py api/application/pay/dispatch.py api/application/pay/payout.py api/application/pay/utr_callback.py api/application/pay/decimal_amount.py api/application/pay/raast_qr.py api/jobs/common/logging_setup.py api/jobs/easypaisa/common/*.py api/jobs/easypaisa/payout/*.py api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/easypaisa_monitor.py api/jobs/jazzcash/payout/*.py api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_monitor.py api/jobs/pakistanpay_v2.py api/jobs/Jazzcashpay_v2.py api/jobs/update_payment_balance.py
python3 -m pytest api/tests/test_decimal_amount.py api/tests/test_raast_qr.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_jazzcash_bill_worker_final_state.py api/tests/test_easypaisa_redis_compat_retirement.py -q
git diff --name-status | egrep 'ops/tenants/d7pay|config.example.py|apkdownload|admin-h5|merchant-h5|k8s|jenkins' || true
```

## EasyPaisa 账单时间口径检查

MySQL 与系统时间保持 UTC。EasyPaisa 上游账单 `tradeTime` 按巴基斯坦时间解释，进入代收/代付账单窗口比较前转为 UTC。

```bash
PYTHONPATH=api python3 -m unittest api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_payout_statement_match_is_observation_only_without_callback api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_collection_credit_matches_when_statement_time_is_inside_order_window api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_collection_credit_rejects_statement_time_after_converted_window -v
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
