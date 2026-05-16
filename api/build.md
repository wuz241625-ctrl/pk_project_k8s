# API 构建说明

## 当前口径

- API 不再保留 `easypaisa_运行时` / `jazzcash_运行时` 模块。
- EasyPaisa 派单读取 MySQL `collection_status` / `payout_status`。
- JazzCashBusiness 业务逻辑参考 `/Users/tear/pk_project`：使用 `application/jazzcash_gateway.py` 的 v1.6 FormBody 封装、MySQL `wallet_status` / `collection_status` / `payout_status` 作为资格源，不再写 Redis 运行时 session/snapshot/index。
- PayFast 代收、查询和收银台跳转逻辑参考 `/Users/tear/pk_project`。
- D7pay 配置由 `config.example.py` 读取环境变量；当前线上 K8s 运行时对象为 `d7pay-runtime-config` 与 `d7pay-runtime-secret`，旧文档中的 `d7pay-config` / `d7pay-secret` 只作为历史命名参考。
- API 仓库不再保留 `api/docker-compose.yml`、`api/docker/`、`api/static/v2`、`api/jobs/freecharge-monitor/php/` 和 `*.bak` 备份文件；D7pay 发布以 Jenkins/K8s 为准。
- D7pay 分支不再保留 `api/application/app/login/banks/gcash_bank.py`、`api/application/app/login/banks/indus_bank.py`、`api/jobs/induspay/`、`api/jobs/jio/`、`api/jobs/maha/` 和 tracked Vim swap 文件。
- D7pay 分支不再保留旧印度钱包 service、`api/application/phonepe/`、旧 Redis 维护脚本、Indus/Jio/Maha/ULCASH 旧 SQL 和 PhonePe 静态图标；服务注册表只保留 `EASYPAISA` 与 `JAZZCASH`。
- `api/application/lakshmi_api` 当前仍承载 App `/v1` 登录、上号、订单和 websocket 相关接口，不属于本轮垃圾清理范围。

## 构建检查

```bash
PYTHONPATH=api python3 -m py_compile main.py router.py router_lakshmi.py application/jazzcash_gateway.py application/pay/pay.py application/pay/order.py application/pay/thirdPart.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py jobs/pakistanpay_v2.py jobs/easypaisa/auto_payout.py jobs/easypaisa/easypaisa_monitor.py jobs/jazzcash/jazzcash_auto_payout.py jobs/jazzcash/jazzcash_monitor.py jobs/Jazzcashpay_v2.py
```

## EasyPaisa secondLogin 数据库 PIN 验收

普通 `secondLogin` 需要带 `pwd`，但除 `change_pin` 外，`pwd` 必须从数据库 `payment.pin` 读取，不信任 App 请求里的 `pin/pwd`。

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_change_pin.py api/tests/test_easypaisa_v19_urm90040.py -q
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

验收重点：

- `second_login_http` 会先读取 `Payment.pin`，再调用 `_call_second_login(..., with_pwd=True)`。
- 二次上号 `_pre_login_second_time_chain` 使用绑定钱包 DB PIN 覆盖 session `pinCode`。
- URM90040 fallback 使用 DB PIN 覆盖 session `pinCode`。
- `change_pin_http` 是唯一用户输入 PIN 例外：先用新 PIN 修改上游和写 DB，再用新 PIN 续推 secondLogin。

## EasyPaisa loginStep1 直登成功验收

上游 `doc_EasyPaisa v2.2.txt` 允许 `loginStep1` 因设备复用直接返回 `code=200`。D7pay 不使用上游 `should_verify_fingerprint`，直登成功后仍进入本地 `OTP_VERIFIED -> upload_fingerprint` 链路。

```bash
cd /Users/tear/pk_project_k8s
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_send_otp_http_direct_login_routes_to_fingerprint_upload api/tests/test_easypaisa_v19_urm90040.py::test_urm90040_login_step1_direct_success_continues_fallback_chain api/tests/test_easypaisa_v19_acceptance.py::test_build_send_otp_request_does_not_use_upstream_fingerprint_flag -q
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

验收重点：

- `loginStep1 code=100` 仍返回 `OTP_SENT`，App 输入 OTP。
- `loginStep1 code=200` 保存/更新 `Payment` 后直接进入 `OTP_VERIFIED`。
- 首次直登成功返回 `fingerprintUploadRequired`，由 App 上传本地指纹 ZIP。
- URM90040 fallback 直登成功时不再要求 OTP，继续内部 fallback 链路。
- `loginStep1` 请求不包含 `should_verify_fingerprint`。

## 资金一致性约束检查

D7pay 资金链路必须先执行 SQL 约束迁移，再发布应用镜像。迁移文件：

```bash
api/sql/20260509_add_fund_integrity_constraints.sql
api/sql/20260510_go_worker_phase0_schema.sql
api/sql/20260516_go_worker_transfer_attempts.sql
```

`20260516_go_worker_transfer_attempts.sql` 为 Go 代付追加审计迁移：新增 `worker_transfer_attempt`，并给 `worker_transfer_intent` 增加 `latest_attempt_id` / `success_attempt_id` 指针。上线后查真实出款次数看 attempt 表，查订单当前状态看 intent 表。

上线前只读检查重复数据；如果重复数不为 0，先清理业务脏数据，再执行迁移：

```sql
SELECT merchant_id, merchant_code, COUNT(*) c FROM orders_df WHERE merchant_code IS NOT NULL AND merchant_code <> '' GROUP BY merchant_id, merchant_code HAVING c > 1;
SELECT trans_id, COUNT(*) c FROM orders_ds WHERE trans_id IS NOT NULL AND trans_id <> '' GROUP BY trans_id HAVING c > 1;
SELECT payment_id, trade_type, trans_id, COUNT(*) c FROM bank_record WHERE trans_id IS NOT NULL AND trans_id <> '' GROUP BY payment_id, trade_type, trans_id HAVING c > 1;
```

代码验收：

```bash
python3 -m py_compile api/application/balance_idempotency.py admin/application/balance_idempotency.py merchant/application/balance_idempotency.py api/application/base.py admin/application/base.py merchant/application/base.py api/jobs/easypaisa/payout/settlement.py api/jobs/jazzcash/payout/settlement.py
PYTHONPATH=api python3 -m pytest api/tests/test_fund_integrity_contract.py -q
```

## JazzCashBusiness 账单与代付状态机检查

D7pay 的 JazzCashBusiness 账单扫描和代付状态机需要跟随 `/Users/tear/pk_project` 当前业务口径：

- CREDIT 账单必须匹配本轮 MySQL 待确认代收订单后才回调。
- PAY 账单只做代付未知订单观测，不走代收回调。
- 代付订单先抢单并绑定账号，再调用官方转账，成功后在同一链路扣减 `payment.balance` 并结算。
- 抢单失败不能调用官方转账；未知、超时和异常进入人工待确认；首次 402 回待处理重试。

```bash
python3 -m py_compile api/jobs/Jazzcashpay_v2.py api/jobs/jazzcash/payout/account_selector.py api/jobs/jazzcash/payout/order_lifecycle.py api/jobs/jazzcash/payout/transfer_executor.py
PYTHONPATH=api python3 -m pytest api/tests/test_jazzcash_mysql_statement_scheduler.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_jazzcash_bill_worker_final_state.py -q
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
PYTHONPATH=api python3 -m unittest api.tests.test_legacy_india_bank_code_retirement -v
rg -n "async def (indusind|freecharge|mobikwik|maharastra)|导入所有银行模块|jio_bank|payment_online_ds|payment_online_df" api/application admin/application merchant/application --glob '!**/__pycache__/**' --glob '!*.md'
```

## 验收测试

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_easypaisa_mysql_eligibility api.tests.test_easypaisa_wallet_status_dispatch api.tests.test_ep_scan_channel api.tests.test_order_10100_template api.tests.test_jazzcash_gateway_v16 api.tests.test_jazzcash_auto_payout_v16 api.tests.test_jazzcash_request_to_pay_v16
```
