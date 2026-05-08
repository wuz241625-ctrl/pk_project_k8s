# D7pay 同步 pk_project EasyPaisa Worker 扩容加固验收报告

## 同步内容

本次同步 `/Users/tear/pk_project` 最新业务提交：

- `1ed2b2a fix: harden easypaisa payout worker scaling`

覆盖范围：

- EasyPaisa 代付候选账号带出今日已代付金额和 `daily_remaining`。
- 派单按剩余日限额判断，而不是只看完整 `amount_top`。
- payment_id 锁后复查释放期、近期使用、金额限制和 MySQL 当前余额。
- 官方成功后，`payment.balance` 扣减与订单结算在同一事务内完成。
- 官方返回 `orderStatus=S` 但没有官方交易号时，不生成本地假 UTR，不按成功结算。

## 保留边界

- 未同步 pk_project 的 README、根级 `build.md`、`err.md` 和环境配置。
- 未修改 D7pay tenant ops、Jenkins/K8s、APK、H5。
- IP 识别、时区展示和 Redis 业务态边界保持原样。

## 验收记录

同步测试后、实现同步前：

```bash
python3 -m pytest api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py -q
```

结果：`15 failed, 71 passed`，红灯符合预期。

实现同步后：

```bash
python3 -m pytest api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py -q
```

结果：`86 passed`

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/easypaisa_runtime/test_worker_wallet_status_integration.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa/test_common_db.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py api/jobs/easypaisa/tests/test_settlement.py api/jobs/easypaisa/tests/test_transaction_log.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_websocket_monitor_ep_dispatch.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

结果：`178 passed, 10 subtests passed`

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

结果：`16,057 nodes | 30,366 edges | 557 clusters | 300 flows`

```text
gitnexus detect_changes(scope="all")
```

结果：暂存 9 个文件变更，影响 3 条执行流程，风险等级为 `medium`，影响范围集中在 EasyPaisa 代付候选账号与订单处理流程。
