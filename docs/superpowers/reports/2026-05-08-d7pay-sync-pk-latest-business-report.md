# D7pay 同步 pk_project 最新业务验收报告

## 同步内容

本次将 `/Users/tear/pk_project` 最新业务改动同步到 D7pay，覆盖：

- Pakistan UTR 语义澄清：代收回调里 `utr` 表示付款手机号，`trans_id` 表示官方流水；代付成功写官方交易号。
- EasyPaisa 账单幂等增强：账单采集、订单匹配、回调锁和重复账单处理同步 pk_project。
- 代付 MySQL 连接集中管理：新增 `api/jobs/common/db.py`，EasyPaisa/JazzCash worker 复用统一连接管理。
- 代付选号余额源改为 MySQL：EasyPaisa/JazzCash selector、monitor、settlement 同步。
- Redis 业务态退役：自动代付开关、专卡专户、旧 active/online 投影不再作为业务判断源。
- 同步新增 SQL：`api/sql/20260508_add_easypaisa_statement_health_indexes.sql`。

## D7pay 保留差异

- `admin/application/merchant/merchant.py`、`admin/application/partner/partner.py` 与 pk_project 只保留 D7pay 展示时区差异，继续使用 `display_today_between()`。
- 未覆盖 D7pay 配置、域名、K8s、Jenkins、APK、H5。
- IP 识别与时区展示保持原样。

## 验收记录

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa_runtime/test_worker_wallet_status_integration.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa/test_common_db.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/jobs/easypaisa/tests/test_settlement.py api/jobs/easypaisa/tests/test_transaction_log.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_websocket_monitor_ep_dispatch.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

结果：`162 passed, 10 subtests passed`

```bash
python3 -m pytest api/tests/test_client_ip.py api/tests/test_timezone_policy.py -q
```

结果：`8 passed`

```bash
python3 -m pytest admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py admin/tests/test_redis_business_state_retirement.py -q
```

结果：`7 passed`

```bash
python3 -m pytest merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
```

结果：`5 passed`

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

结果：`D7pay release contract OK`

```bash
python3 -m py_compile api/jobs/pakistanpay_v2.py api/jobs/common/db.py api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/easypaisa_monitor.py api/jobs/easypaisa/payout/account_selector.py api/jobs/easypaisa/payout/order_lifecycle.py api/jobs/easypaisa/payout/settlement.py api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_monitor.py api/jobs/jazzcash/payout/account_selector.py api/jobs/jazzcash/payout/order_lifecycle.py api/jobs/jazzcash/payout/settlement.py api/application/websocket/callback.py api/application/pay/payout.py admin/application/order/auto_payout.py admin/application/merchant/merchant.py admin/application/partner/partner.py
```

结果：通过。

```bash
rg -n "datetime\.today\(\)\.date\(\)|Asia/Shanghai|target_payment_key|easypaisa_emergency_stop|payment_active_channel_" api/application api/jobs admin/application -g '*.py'
```

结果：无匹配。

```bash
git diff --check
```

结果：通过。

```bash
npx gitnexus analyze
```

结果：`15,928 nodes | 30,173 edges | 546 clusters | 300 flows`

```text
gitnexus detect_changes(scope="all")
```

结果：暂存变更 40 个文件、影响 14 条执行流程，风险等级为 `high`。高风险来自本次按要求同步代收账单、代付选号、采集、回调等核心业务流程，属于预期范围；未发现 D7pay 配置、域名、Jenkins/K8s/APK/H5 被覆盖。
