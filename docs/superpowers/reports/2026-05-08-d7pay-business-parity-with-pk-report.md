# D7pay 后端业务同步 pk_project 验收报告

## 同步范围

本次将 D7pay 后端业务同步到 `/Users/tear/pk_project` 当前实现，覆盖：

- 钱包状态和上号状态：EasyPaisa/JazzCash app 登录处理、钱包 monitor、`update_payment_balance.py` 退役。
- 代收下单和派单：`pay.py`、`dispatch.py`、Lakshmi deposit 入口和 `/pay/df` 路由恢复。
- 采集和回调：`order.py`、`websocket/callback.py`、`Jazzcashpay_v2.py`、`jazzcash_monitor.py`。
- 代付：EasyPaisa 自动代付调度与已同步的 payout 状态机继续保持。

## 保留边界

- 保留 D7pay 的 `resolve_client_ip` IP 识别实现。
- 保留 D7pay 的 `display_today_between` 时区展示实现。
- 未改动 D7pay env 化 `config.example.py`、K8s、Jenkins、H5、APK、域名和租户运维配置。

## 本地兼容补丁

`/Users/tear/pk_project` 当前有未跟踪测试要求 EasyPaisa 自动代付旧 `members=` 参数安全退役。同步后在 `api/jobs/easypaisa/auto_payout.py` 保留了这个兼容入口：旧消息只记录并返回 `(0, 0)`，新业务仍走 `account_order_batches` 预分配。

## 验收记录

```bash
npx gitnexus analyze
```

结果：通过，索引刷新为 `15,569 nodes | 29,467 edges | 524 clusters | 300 flows`。

```bash
gitnexus detect_changes(scope="all")
```

结果：本次覆盖 15 个业务文件，GitNexus 标记整体风险为 `critical`。原因是变更横跨下单、派单、采集、代付主流程，符合本次“完全同步”的预期范围；随后对核心入口单独做影响确认：

- `push_order`：上游直接影响 `Pay._dispatch_and_respond`，风险 `LOW`。
- `Pay`：上游 import 影响 `callback.py`、`third_df.py`，风险 `LOW`。
- `Jazzcashpay_v2.BankLogin`：未发现上游调用方，风险 `LOW`。
- `jazzcash_monitor.AutoPayoutMonitor`：未发现上游调用方，风险 `LOW`。

```bash
python3 -m py_compile api/application/pay/pay.py api/application/pay/dispatch.py api/application/pay/order.py api/application/websocket/callback.py api/application/websocket/monitor.py api/application/app/login/banks/easypaisa.py api/application/app/login/banks/jazzcash.py api/application/lakshmi_api/controllers/deposit_orders_controller.py api/jobs/easypaisa/auto_payout.py api/jobs/Jazzcashpay_v2.py api/jobs/update_payment_balance.py api/jobs/jazzcash/jazzcash_monitor.py api/router.py
```

结果：通过，只有 `api/router.py` 历史正则 `\S` 的 `SyntaxWarning`。

```bash
python3 -m pytest api/tests/test_crawl_frequently_retirement.py api/tests/test_update_payment_balance_retirement.py api/tests/test_jazzcash_mysql_statement_scheduler.py api/tests/test_ds_dispatch_candidate_sql.py api/tests/test_easypaisa_qr_payload.py api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_jazzcash_bill_worker_final_state.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_client_ip.py api/tests/test_timezone_policy.py -q
```

结果：`56 passed, 3 warnings, 7 subtests passed`

```bash
python3 -m pytest admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py -q
```

结果：`6 passed`

```bash
python3 -m pytest merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
```

结果：`5 passed`

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

结果：`D7pay release contract OK`

```bash
python3 api/jobs/update_payment_balance.py
```

结果：成功退出并输出 `update_payment_balance 已退役`。

```bash
rg -n "crawl_frequently_" api/application api/jobs -g '*.py'
```

结果：无匹配。

```bash
rg -n "datetime\.today\(\)\.date\(\)|Asia/Shanghai" api admin merchant -g '*.py'
```

结果：无匹配。
