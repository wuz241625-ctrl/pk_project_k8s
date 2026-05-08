# D7pay 同步 pk_project 钱包手机号与代付并发验收报告

## 同步内容

本次同步 `/Users/tear/pk_project` 最新业务提交：

- `022ac24 fix: require wallet payer phone before statement scan`
- `dcb3252 fix: harden easypaisa payout concurrency`
- `ed262c7 fix: split easypaisa accno and qr channels`
- `b94d3e0 fix: show wallet phone for easypaisa account channel`

覆盖范围：

- EasyPaisa `1001` 账号/钱包展示与 `1010` QR 通道拆分。
- 代收候选 SQL 支持 EasyPaisa 钱包手机号与银行账号两类资料。
- 收银台 Pakistan 钱包手机号归一化，短时间同账号同金额重复提交会拦截。
- EasyPaisa/JazzCash 账单扫描要求代收订单已有付款手机号。
- EasyPaisa 代付锁改为原子 `set nx ex` 和 Lua compare-delete。
- EasyPaisa 代付并发限制、执行中超时转人工确认、`code=200` 非 `S` 不结算。

## 保留边界

- 未同步 pk_project 的环境配置、README、根级 `build.md`/`err.md`。
- 未修改 D7pay K8s/Jenkins/tenant ops/APK/H5。
- D7pay IP 识别、时区展示、release contract 保持原样。

## 验收记录

同步测试后、实现同步前：

```bash
python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py api/tests/test_order_10100_template.py api/tests/test_easypaisa_mysql_eligibility.py api/tests/test_jazzcash_mysql_statement_scheduler.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

结果：`25 failed, 105 passed`，红灯符合预期。

实现同步后：

```bash
python3 -m pytest api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py api/tests/test_order_10100_template.py api/tests/test_easypaisa_mysql_eligibility.py api/tests/test_jazzcash_mysql_statement_scheduler.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

结果：`130 passed`

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa_runtime/test_worker_wallet_status_integration.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa/test_common_db.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/jobs/easypaisa/tests/test_settlement.py api/jobs/easypaisa/tests/test_transaction_log.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_websocket_monitor_ep_dispatch.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

结果：`168 passed, 10 subtests passed`

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

结果：`15,995 nodes | 30,296 edges | 532 clusters | 300 flows`

```text
gitnexus detect_changes(scope="all")
```

结果：暂存 21 个文件变更，影响 7 条执行流程，风险等级为 `high`。高风险来自本次同步代收派单、收银台确认、账单扫描、EasyPaisa 代付流程，属于预期业务同步范围。
