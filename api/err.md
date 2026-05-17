# API 排错记录

## 0.16 EasyPaisa 状态响应 envelope 不闭环

现象：

- `ACCOUNT_SELECTION_REQUIRED` 有些接口返回 `next_step=select_accts`，有些返回 `second_login` 或 `query_accts`。
- `verify_fingerprint_http` 幂等短路在真实状态已经是 `ACCOUNT_SELECTION_REQUIRED` / `ACTIVE_SUCCESSFUL` 时，仍返回 `phase=fingerprintVerified`。
- `_force_terminal_needs_relogin()` 直返没有 `next_step=needs_relogin`。

根因：

- 状态机邻接表已经收敛，但多个入口各自手写 response envelope。
- 历史上 `query_accts` 和 `second_login` 曾作为中间下一步返回，后续自动续推到 `ACCOUNT_SELECTION_REQUIRED` 后没有同步改响应。

处理：

- 扩展 `NEXT_STEP_MAP`，补齐 `activeSuccessful -> ready` 与 `needsRelogin -> needs_relogin`。
- 所有 `ACCOUNT_SELECTION_REQUIRED` 成功响应统一返回 `next_step=select_accts`。
- `verify_fingerprint_http` 幂等短路返回真实 phase 和对应 next_step。
- `_force_terminal_needs_relogin()` 返回 `next_step=needs_relogin`。

验证：

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m pytest tests/test_easypaisa_v19_force_terminal.py tests/test_easypaisa_v19_fingerprint.py tests/test_easypaisa_v19_acceptance.py tests/test_easypaisa_v19_pre_login_branching.py tests/test_easypaisa_v19_urm90040.py -q
python3 -m pytest tests/ -q -k easypaisa
python3 -m py_compile application/app/login/banks/easypaisa.py
```

## 0.15 EasyPaisa 已绑定账号旧指纹没有被复用

现象：

- 已绑定账号 `secondLogin` 快路径失败后回退到 OTP 流程。
- MySQL `payment.fingerprint_path` 存在且本地 ZIP 可读，但 `verify_otp_http` 仍返回 `fingerprintUploadRequired`，要求 App 重新上传指纹。
- `loginStep1 direct_success` 且本地旧指纹存在时，会调用不存在的 `_fallback_chain_after_verify_otp`，触发 `AttributeError`。

根因：

- `pre_login_http` 只写入 `reuse_local_fingerprint_after_otp` / `local_fingerprint_path`，但 `verify_otp_http` 没有消费这些字段。
- 旧计划中的 `_fallback_chain_after_verify_otp` 没有落到当前代码，当前文件只保留了 `_verify_otp_fallback_chain`。

处理：

- 新增 `_reuse_local_fingerprint_after_otp()`，统一执行旧指纹复用链路：
  - `upload_data` 推本地旧 ZIP。
  - `verifyFingerprint` 验证旧指纹。
  - `secondLogin(with_pwd=True)`。
  - `queryAccountList` 后进入 `ACCOUNT_SELECTION_REQUIRED`。
- `pre_login_http` 的 `direct_success + local_zip_path` 改用新 helper。
- `verify_otp_http` 在 OTP 成功后，如果 session 有旧指纹标记，先调用新 helper；旧指纹推送或验证失败时返回 `upload_fingerprint` 让 App 重新采集。

验证：

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m pytest tests/test_easypaisa_v19_pre_login_branching.py -q
python3 -m pytest tests/ -q -k easypaisa
python3 -m py_compile application/app/login/banks/easypaisa.py
```

## 0.14 TimeOutGuard 不应恢复到 Python timeout job

现象：

- API EasyPaisa 回归曾依赖 `api/jobs/time_out.py::TimeOutGuard`。
- 业务 jobs 已迁到 `/Users/tear/pk-go-worker` 后，继续保留该兼容类会误导后续同步把旧 Redis 回压逻辑带回。

根因：

- Python `time_out.py` 已不再是在线 timeout job owner。
- 当前 timeout 任务类型由 Go worker 负责：`timeout:collect_order` 与 `timeout:payout_claim`。

处理：

- 删除 `api/jobs/time_out.py::TimeOutGuard` 兼容类。
- 将 `api/tests/test_easypaisa_timeout_guard.py` 改为退役守护，断言 Python 旧脚本不再定义该类，并校验 Go worker timeout handler 注册。

验证：

```bash
cd /Users/tear/pk_project_k8s/api
python3 -m pytest tests/test_easypaisa_timeout_guard.py -q

cd /Users/tear/pk-go-worker
go test ./internal/timeout ./tasks
```

## 0.13 EasyPaisa isAccountRegistered 403/false 被误判为上游异常

现象：

- 03009208353 上号停在 `pre_login`。
- 日志显示上游 `isAccountRegistered` 返回：

```json
{"code":403,"msg":"isAccountRegistered查询: pk_easypaisa_03009208353","data":false}
```

- 旧代码把所有非 `code=200` 都抛为 `SL_UPSTREAM_ERROR`，导致 App 没有拿到 `next_step=send_otp`。

根因：

- EasyPaisa v2.2 文档定义 `code=403/data=false` 是“云机不存在或账户未完成云机绑定流程”，属于正常未注册分支。
- D7pay 的 `_is_account_registered()` 把它误判成接口异常。

处理：

- `_is_account_registered()` 改为：
  - `code=200/data=true` 返回 `True`。
  - `code=403/data=false` 返回 `False`。
  - 其他响应继续抛 `SL_UPSTREAM_ERROR`。
- `pre_login_http` 收到 `False` 后继续首次上号，返回 `next_step=send_otp`。

验证：

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_is_account_registered_403_false_means_not_registered api/tests/test_easypaisa_v19_acceptance.py::test_is_account_registered_rejects_unexpected_codes api/tests/test_easypaisa_v19_acceptance.py::test_pre_login_treats_unregistered_cloud_account_as_send_otp -q
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

## 0.12 EasyPaisa loginStep1 code=200 不能当作 OTP 已发送

现象：

- 上游 `doc_EasyPaisa v2.2.txt` 新增/明确 `loginStep1` 可直接返回 `code=200`。
- 旧代码把 `code=100` 和 `code=200` 都当作 `OTP发送成功`，导致 App 继续等待 OTP。
- 实际 `code=200` 表示设备复用直接登录成功，无需再提交 `loginStep2`。

处理：

- `_send_otp()` 返回 `direct_login` 标志：`code=100` 为 `False`，`code=200` 为 `True`。
- `send_otp_http` 收到 `direct_login=True` 后保存/更新 `Payment`，推进 session 到 `OTP_VERIFIED`，返回 `fingerprintUploadRequired`。
- URM90040 fallback 收到 `direct_login=True` 后不返回 `SL_NEEDS_OTP`，直接继续 `_verify_otp_fallback_chain()`。
- D7pay 不使用上游 `should_verify_fingerprint`，指纹上传与验证仍走本地 `upload_fingerprint` / `verify_fingerprint` 链路。

验证：

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py::test_send_otp_http_direct_login_routes_to_fingerprint_upload api/tests/test_easypaisa_v19_urm90040.py::test_urm90040_login_step1_direct_success_continues_fallback_chain api/tests/test_easypaisa_v19_acceptance.py::test_build_send_otp_request_does_not_use_upstream_fingerprint_flag -q
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

## 0.11 EasyPaisa 普通 secondLogin 不能使用客户端 PIN

现象：

- EasyPaisa 已绑定钱包走 `second_login` 时，上游要求 `secondLogin` 请求带 `pwd`。
- App 普通二次登录链路不展示钱包官方 PIN，如果后端信任请求里的 `pin/pwd`，会出现错 PIN、假 PIN 或旧 PIN 被带给上游的问题。
- 只有 `change_pin` 场景里的 `pin` 是用户本次输入的新 PIN。

处理：

- 普通 `second_login_http`、二次上号 `_pre_login_second_time_chain`、URM90040 fallback `_verify_otp_fallback_chain` 都先读取数据库 `Payment.pin`。
- 读取到 DB PIN 后覆盖当前 session 的 `pinCode`，再调用 `_call_second_login(..., with_pwd=True)`。
- 如果 DB PIN 缺失，不使用 App 请求里的 PIN 兜底，直接终止为 `SL_UPSTREAM_ERROR`/needsRelogin，避免把不可信 PIN 送给上游。
- `change_pin_http` 保持例外：用户传入新 PIN，先 `_change_pin()`，再 `_save_payment(..., pin=新PIN)`，最后用新 PIN 续推 secondLogin。

验证：

```bash
python3 -m pytest api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_change_pin.py api/tests/test_easypaisa_v19_urm90040.py -q
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

## 0.0 EasyPaisa verify_fingerprint 读取 pending ZIP 触发 UTF-8 解码失败

现象：

- EasyPaisa `upload_fingerprint_http` 把指纹 ZIP 暂存到 `easypaisa:pending_fp:{payment_id}`。
- `verify_fingerprint_http` 再读取该 key，准备上传云机并执行 `verifyFingerprint`。
- API 主 Redis 客户端使用 `decode_responses=True`，读取 ZIP bytes 时可能触发 `UnicodeDecodeError`，典型错误形态为：`'utf-8' codec can't decode byte ... invalid start byte`。
- 失败发生在读取 Redis pending 阶段，尚未进入云机上传、指纹验证、落盘或 `payment.fingerprint_path` 更新。

根因：

- `api/main.py` 的 `application.redis` 是字符串 Redis 客户端，适合 session、锁、JSON 等文本数据。
- 指纹 ZIP 是二进制 payload，不能用 decoded Redis 客户端读取。
- 当前流程把二进制 ZIP 和文本业务数据混用同一个 Redis 客户端。

处理：

- API 启动时新增 `redis_binary = aioredis.from_url(..., decode_responses=False)`。
- `Application` 挂载 `redis_binary`，保留原 `redis` 的 decoded 行为不变。
- `EasyPaisa` 新增 pending ZIP 专用 helper：
  - `_set_pending_fingerprint_zip()` 写 ZIP bytes。
  - `_get_pending_fingerprint_zip()` 读 ZIP bytes。
- `upload_fingerprint_http` 和 `verify_fingerprint_http` 的 pending ZIP 读写改走 binary helper。

验收：

```bash
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py::test_verify_fingerprint_reads_pending_zip_from_binary_redis -q
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py -q
python3 -m py_compile api/main.py api/application/app/login/banks/easypaisa.py
npx gitnexus detect-changes
```

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
- D7pay K8s 环境注入统一使用线上实际对象 `d7pay-runtime-config` / `d7pay-runtime-secret`；旧 `d7pay-config` / `d7pay-secret` 命名只允许出现在历史备份或未应用的模板说明中。

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

## 0.9 JazzCashBusiness 账单或代付状态机回退到旧逻辑

现象：

- `Jazzcashpay_v2.grabstatement` 不接收 `statement_context`。
- JCB 抓到 PAY 账单后进入 `transaction_callback`，把代付账单当代收回调处理。
- CREDIT 账单没有按本轮 MySQL 待确认代收订单的金额、付款手机号和时间窗口匹配就回调。
- JCB 代付成功后在拆散链路里另起连接处理结算，或官方成功但 `payment.balance` 未在同一事务链路扣减。
- 抢单失败仍调用官方转账，或未知/超时订单回到待处理池导致重复出款风险。

原因：

- 从旧 JazzCashBusiness worker 同步代码时，只同步了表面 worker 文件，没有同步 `/Users/tear/pk_project` 最新的账单匹配和 EasyPaisa 对齐状态机。
- JCB 账单里的 PAY 是代付观测来源，不是代收成功依据；代收成功只能由 CREDIT 与待确认代收订单匹配触发。

处理：

- 以 `/Users/tear/pk_project/api/jobs/Jazzcashpay_v2.py`、`api/jobs/jazzcash/payout/account_selector.py`、`api/jobs/jazzcash/payout/order_lifecycle.py`、`api/jobs/jazzcash/payout/transfer_executor.py` 当前业务逻辑为准同步。
- 保留 D7pay 租户配置、IP 识别、时区展示和资金幂等代码，不做全仓覆盖。

验证：

```bash
PYTHONPATH=api python3 -m pytest api/tests/test_jazzcash_mysql_statement_scheduler.py api/tests/test_jazzcash_payout_state_machine.py -q
PYTHONPATH=api python3 -m pytest api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_jazzcash_bill_worker_final_state.py -q
```

## 0.10 本地环境没有 `python` 命令

现象：

- 执行 `python -c "import ast; ast.parse(...)"` 时返回 `zsh:1: command not found: python`。
- 项目既有构建与排错命令统一使用 `python3`。

处理：

- 本地语法、AST、unittest 和 py_compile 验证改用 `python3`。
- 不在仓库内新增 Python 软链或修改系统解释器。

验证：

```bash
python3 -c "import ast; ast.parse(open('api/application/app/login/banks/easypaisa.py').read())"
python3 -m py_compile api/application/app/login/banks/easypaisa.py
```

## 0.11 EasyPaisa URM90040 被误当成真实掉线

现象：

- 首次上号中指纹未确认成功，后续 `secondLogin` 返回 `501 / URM90040`。
- 代码把所有 `URM90040` 都当作掉线/抢登，重置到 `preLoginCreated` 并调用 `loginStep1`。
- 已上号或指纹未完成状态下 `loginStep1` 无法成功，用户可能反复失败直到 URM90040 限频打满。

原因：

- `URM90040` 有两层含义：指纹没有验证成功、真实掉线/抢登。
- 本项目只有 `verifyFingerprint` 确认成功后才写 MySQL `payment.fingerprint_path`。
- 因此没有可用 `fingerprint_path` 时，不应进入 `_urm90040_fallback` 的 `loginStep1` 恢复链路。

处理：

- `_urm90040_fallback` 增加指纹前置条件：只有 MySQL 有 `fingerprint_path` 且本地 ZIP 存在时，才允许 `loginStep1` / OTP fallback。
- 无指纹或本地 ZIP 缺失时，返回 `code=FP_REQUIRED_OR_UNVERIFIED`、`phase=otpVerified`、`next_step=upload_fingerprint`，让 APP 继续录指纹。
- `_pre_login_second_time_chain` 缺指纹不再直接 `needsRelogin`。

验证：

```bash
pytest api/tests/test_easypaisa_v19_urm90040.py api/tests/test_easypaisa_v19_acceptance.py api/tests/test_easypaisa_v19_change_pin.py api/tests/test_easypaisa_v19_state_machine.py -v
```

## 0.12 Go 代付重派覆盖历史导致无法核对出款钱包

现象：

- 同一 `orders_df.code` 经历 402 重派或本地结算失败恢复。
- 只看 `worker_transfer_intent` 时只能看到最后一次状态，无法判断哪些钱包曾调用官方 transfer。
- 线上枚举不包含旧方案中的 `402_redispatch`，写入会失败。

处理：

- 执行 `api/sql/20260516_go_worker_transfer_attempts.sql`。
- `worker_transfer_attempt` 作为追加事实表，每次钱包出款尝试写一行。
- `worker_transfer_intent` 作为当前状态表，只保存 `latest_attempt_id` 和 `success_attempt_id`。
- 402 重派写 `failed_retryable`，不再写 `402_redispatch`。
- 本地结算失败恢复时，从 `success_attempt_id` 关联的 attempt 取 `payment_id`、`partner_id`、`channel` 和 `official_transaction_id`，不再次调用官方 transfer。

验证：

```sql
SHOW CREATE TABLE worker_transfer_attempt;
SHOW COLUMNS FROM worker_transfer_intent LIKE 'latest_attempt_id';
SHOW COLUMNS FROM worker_transfer_intent LIKE 'success_attempt_id';

SELECT order_code, status, latest_attempt_id, success_attempt_id,
       payment_id, channel, official_transaction_id, updated_at
FROM worker_transfer_intent
WHERE order_code='<orders_df.code>';

SELECT id, attempt_no, request_id, payment_id, partner_id, channel,
       official_code, official_message, official_transaction_id, result,
       error_message, submitted_at, settled_at
FROM worker_transfer_attempt
WHERE order_code='<orders_df.code>'
ORDER BY attempt_no ASC;
```

## 0.13 EasyPaisa pre_login 继续依赖 isAccountRegistered 导致分流抖动

现象：

- 已绑定 EasyPaisa 账号重新上号时，`pre_login_http` 仍调用云机 `isAccountRegistered` 做新号/二次号分流。
- 云机池化回收或绑定实例漂移时，同一账号可能短时间内返回 true/false 抖动。
- 抖动会让已绑定号误入首次上号路径，或让新号路径依赖一个实时探针。

原因：

- `isAccountRegistered` 表示“当前云机实例是否正在绑定该号”，不是“该号是否曾经在本系统绑定过”的持久事实。
- 旧流程先 check 再 act，`isAccountRegistered` 与后续 `loginStep1` / `secondLogin` 之间有竞态窗口。

处理：

- `pre_login_http` 改为按本地账号类别分流：命中 `bound_payment` 先走 `_try_secondlogin_fastpath`，fastpath 返回 `None` 时回退 `_perform_loginstep1`；新号直接走 `_perform_loginstep1`。
- `_perform_loginstep1` 对 `loginStep1` 做非 raise 分类：`200 direct_success`、`100 otp_sent`、`501 offline_501`、`423 server_busy`、`503 network_error`、其余 `rejected`。
- `_try_secondlogin_fastpath` 对 `success/needs_pin_change/cooldown` 直接返回契约信封，其余结果统一回退 `loginStep1`，不在 pre_login fastpath 内杀 session。
- 新增 `test_easypaisa_v19_branching_invariants.py` 守护：`pre_login_http` 不得调用 `_is_account_registered`，且仓库源码不应出现旧 `_second_login_chain_from_pre_login`。

验证：

```bash
cd api && python3 -m pytest tests/test_easypaisa_v19_loginstep1_classifier.py tests/test_easypaisa_v19_fastpath.py tests/test_easypaisa_v19_pre_login_branching.py tests/test_easypaisa_v19_branching_invariants.py -q
cd api && python3 -m pytest tests/ -q -k easypaisa
```
