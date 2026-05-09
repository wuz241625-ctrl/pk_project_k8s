# API 排错记录

## 0.1 不允许恢复 运行时 模块

现象：

- `api/application/easypaisa_运行时` 或 `api/application/jazzcash_运行时` 再次出现。
- 登录、派单、监控脚本重新 import 运行时 reader/service。
- D7pay K8s 配置重新使用 `旧运行配置` 命名。

处理：

- 删除 运行时 模块、脚本、SQL、测试和旧设计文档。
- EasyPaisa 代收派单读取 MySQL `collection_status`。
- EasyPaisa 代付派单读取 MySQL `payout_status`。
- JazzCashBusiness 使用当前业务主线，不写 运行时 session/snapshot/index。
- D7pay K8s 环境注入统一命名为 `d7pay-config` / `d7pay-secret`。

验证：

```bash
rg "旧服务类|旧读取类" api --glob '!*.md'
PYTHONPATH=api python3 -m py_compile main.py router_lakshmi.py application/pay/pay.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py
```

## 0.2 业务同步时不能把运行层带回

现象：

- 从 `/Users/tear/pk_project` 同步业务后，重新出现旧英文运行层 key、旧读取类或旧服务类。
- JCB v1.6 代码缺少 `application/jazzcash_gateway.py`，导致 `from application.jazzcash_gateway import ...` 失败。
- PayFast 代收跳转已合入，但 `thirdPart.py` 没有 `payfast_payment`。

处理：

- JCB/PayFast/Lakshmi API 业务可以参考 `/Users/tear/pk_project`。
- EasyPaisa 与 Admin 收款资料列表只保留 MySQL 最终状态和旧 Redis 投影清理，不恢复运行层 key。
- D7pay API 配置必须保留 `JAZZCASH_API_VERSION=v1.6`，默认值在 `api/config.example.py`。

验证：

```bash
rg "旧服务类|旧读取类" api --glob '!*.md'
PYTHONPATH=api python3 -m py_compile application/jazzcash_gateway.py application/app/login/banks/jazzcash.py application/pay/order.py application/pay/thirdPart.py jobs/jazzcash/jazzcash_auto_payout.py
```

## 0.3 明确垃圾制品不能回流

现象：

- 仓库重新出现 `api/jobs/freecharge-monitor/php`、`api/jobs/easypaisa/auto_payout.py.bak`、`api/docker-compose.yml`、`api/docker` 或 `api/static/v2`。
- 仓库重新出现 D7pay 已清理的旧银行实现：`gcash_bank.py`、`indus_bank.py`、`api/jobs/induspay`、`api/jobs/jio`、`api/jobs/maha`。
- D7pay 下载站重新提交 `apkdownload/public/files/android/lakshmi/*.apk` 或 `apkdownload/public/files/android/ashrafi/*.apk`。

处理：

- PHP 依赖应由对应旧项目自行安装，不提交 vendor 目录到 D7pay 分支。
- Freecharge PHP、GCash、Indus、Jio、Maha 旧入口不属于 D7pay 当前运行链路，不重新提交。
- 备份文件不进入 Git，需要保留历史时使用 Git commit。
- D7pay APK 下载页只保留 D7pay 发布项，不携带 Ashrafi/Lakshmi 旧客户 APK。
- 当前线上发布只走 Jenkins/K8s，不恢复 API 本地 compose。

验证：

```bash
test "$(git ls-files api/jobs/freecharge-monitor/php | wc -l | tr -d ' ')" = "0"
test "$(git ls-files api/static/v2 | wc -l | tr -d ' ')" = "0"
test -z "$(git ls-files api/jobs/easypaisa/auto_payout.py.bak api/docker-compose.yml api/docker api/application/app/login/banks/gcash_bank.py api/application/app/login/banks/indus_bank.py api/jobs/induspay api/jobs/jio api/jobs/maha merchant/.config.py.swp apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk)"
```

## 0.4 旧印度钱包和 PhonePe 残留不能回流

现象：

- `api/application/lakshmi_api/services/payment_services.py` 再次注册 `FREECHARGE`、`PHONEPE`、`MOBIKWIK`、`AIRTEL`、`AMAZON`、`INDUS`、`ULCASH`、`JIO` 或 `MAHA`。
- `api/main.py` 再次启动 `application.phonepe.redissub` 后台线程。
- `api/router.py` 再次暴露 `/phonepe/ws` 或 `/phonepe/api/*`。
- `api/router_lakshmi.py` 再次暴露 Indus/Amazon 专用的 `pin_pre_sign_in`、`cookie` 或 `grabOTP` 路由。
- 仓库重新出现旧 Redis 维护脚本：`check_proxy.py`、`clear_redis_dsdf.py`、`clear_redis_inactive_payment.py`、`collect_partner_status.py`、`order_push.py`、`weight.py`。

处理：

- 参考 `/Users/tear/pk_project` 当前文件，Lakshmi API 只注册 `EASYPAISA` 与 `JAZZCASH`。
- API 启动不再创建 PhonePe 订阅线程。
- 删除旧 PhonePe websocket/http 路由和旧印度钱包专用 App 路由。
- 代收派单以 MySQL `collection_status` 为候选真相源，不回退到旧 `payment_active_*`。

验证：

```bash
rg "application\\.phonepe|PhonepeService|FreechargeService|IndusPayService|MahaService|MobikwikService|AirtelService|AmazonService|UlCashPayService|JioService|/phonepe|PaymentPINPreSignIn|StoreCookie|GrabOTP" api --glob '!*.md'
test -z "$(git ls-files api/application/phonepe api/jobs/check_proxy.py api/jobs/clear_redis_dsdf.py api/jobs/clear_redis_inactive_payment.py api/jobs/collect_partner_status.py api/jobs/order_push.py api/jobs/weight.py api/static/images/india_transaction/PhonePe.svg)"
```

## 0.5 同步 pk_project 模块化代码后旧单体测试失败

现象：

- 同步 `pk_project` 后，`api/jobs/jazzcash/jazzcash_auto_payout.py` 变成编排器，旧测试仍直接断言 `JazzCashAutoPayout.process_payout_order`、`process_single_order_async` 或 `_execute_jazzcash_transfer`。
- 同步 `EasyPaisaAutoPayout` 后，旧测试仍断言在线检查在编排器类上，实际已移动到 `jobs/easypaisa/payout/account_selector.py`。

原因：

- 这是模块拆分后的职责迁移，不是业务方法丢失。JazzCash 代付执行在 `TransferExecutor`，订单生命周期在 `OrderLifecycle`，账号选择在 `AccountSelector`；EasyPaisa 同理。

处理：

- 删除 D7pay 已过时的 `api/tests/test_jazzcash_auto_payout.py`，改用 `api/tests/test_jazzcash_auto_payout_v16.py` 覆盖编排器和拆分模块。
- EasyPaisa 测试改为断言 `AccountSelector.check_account_online_status` 和 `OrderLifecycle.process_payout_order`。
- 保留 `pay.py` re-export，这是 import 路径兼容层，不影响唯一真相源。

验证：

```bash
python3 -m pytest api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

## 0.6 EasyPaisa 账单 tradeTime 与 UTC 订单时间错位

现象：

- MySQL 和系统时间为 UTC。
- EasyPaisa 上游账单 `tradeTime` 为巴基斯坦时间。
- 代收订单或代付订单实际在窗口内，但 worker 直接用无时区 datetime 比较，导致 `tradeTime` 被当成 UTC，出现误判不匹配。

处理：

- 数据库字段 `orders_ds.time_create`、`orders_df.time_accept` 继续按 UTC naive datetime 处理。
- 上游 `tradeTime` 先按 `APP_DISPLAY_TIMEZONE` 解析，默认 `Asia/Karachi`，再转换为 UTC naive datetime。
- 代收账单确认和代付账单观察共用该边界，不改 MySQL、Pod、Redis 或宿主机时区。

验证：

```bash
PYTHONPATH=api python3 -m unittest api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_payout_statement_match_is_observation_only_without_callback api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_collection_credit_matches_when_statement_time_is_inside_order_window api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_collection_credit_rejects_statement_time_after_converted_window -v
```

## 0.7 与 pk_project 文件对比时旧印度钱包残留回流

现象：

- D7pay 与 `/Users/tear/pk_project` 文件对比时，D7pay 仍保留 pk_project 已删除的旧印度钱包解析函数。
- `api/application/websocket/bank_analysis.py` 中出现 `indusind`、`freecharge`、`mobikwik`、`maharastra`。
- 注释里出现旧 Redis 在线集合 `payment_online_ds` / `payment_online_df`，或不存在的 `JioBank` 引用。

处理：

- 删除孤立旧解析函数，不恢复旧银行登录、旧 worker 或 runtime SQL。
- 删除旧 Redis 在线集合注释，避免把 Redis 当业务态判断源。
- 登录控制器注释只保留当前实际使用的 EasyPaisa/JazzCash。

验证：

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_legacy_india_bank_code_retirement -v
rg -n "async def (indusind|freecharge|mobikwik|maharastra)|导入所有银行模块|jio_bank|payment_online_ds|payment_online_df" api/application admin/application merchant/application --glob '!**/__pycache__/**' --glob '!*.md'
```

## 0.8 资金约束迁移被重复数据拦截

现象：

- 执行 `api/sql/20260509_add_fund_integrity_constraints.sql` 时，`orders_df`、`orders_ds` 或 `bank_record` 的唯一索引没有新增。
- 迁移输出提示存在重复业务键。
- 余额流水重复执行，导致同一业务单号多次加减余额。

原因：

- `orders_df` 需要以 `merchant_id + merchant_code` 保证商户代付单唯一。
- `orders_ds` 需要以非空 `trans_id` 保证上游/系统交易号唯一。
- `bank_record` 的 `utr` 可能是手机号或付款方引用，不适合作为唯一真相源；巴基斯坦账单流水应优先使用 `payment_id + trade_type + trans_id`。
- `balance_record` 历史上只有流水展示意义，没有独立幂等键，所以需要新增 `balance_record_idempotency` 表拦截重复资金变更。

处理：

- 上线前先只读检查重复数据，确认是否需要业务清理。
- 有重复时先按业务订单、账单源和回调来源确认保留哪一条，不允许直接删除资金流水。
- 清理后重新执行迁移，确认唯一索引已存在。
- 应用代码已在 API、Admin、Merchant 和代付 worker 的余额变更入口预占幂等键；如果 SQL 表未创建，会降级放行并记录日志，因此正式上线必须先跑迁移。

验证：

```sql
SELECT merchant_id, merchant_code, COUNT(*) c FROM orders_df WHERE merchant_code IS NOT NULL AND merchant_code <> '' GROUP BY merchant_id, merchant_code HAVING c > 1;
SELECT trans_id, COUNT(*) c FROM orders_ds WHERE trans_id IS NOT NULL AND trans_id <> '' GROUP BY trans_id HAVING c > 1;
SELECT payment_id, trade_type, trans_id, COUNT(*) c FROM bank_record WHERE trans_id IS NOT NULL AND trans_id <> '' GROUP BY payment_id, trade_type, trans_id HAVING c > 1;
SHOW INDEX FROM orders_df WHERE Key_name = 'uk_orders_df_merchant_code';
SHOW INDEX FROM orders_ds WHERE Key_name = 'uk_orders_ds_trans_id_unique';
SHOW INDEX FROM bank_record WHERE Key_name = 'uk_bank_record_payment_trade_trans';
SHOW CREATE TABLE balance_record_idempotency;
```
