# D7pay 同步 pk_project 流水回调幂等报告

## 同步范围

- 同步来源：`/Users/tear/pk_project` 当前工作区未提交业务改动
- 同步目标：`/Users/tear/pk_project_k8s`，分支 `d7pay`
- 同步文件：
  - `api/application/pay/order.py`
  - `api/tests/test_statement_callback_mysql_idempotency.py`

## 业务结果

- EasyPaisa 和 JazzCash 的 `New` 流水回调共用 `_handle_pakistan_statement_callback`。
- 回调入口先获取 `success_busy_{trans_id}` 分布式锁，再查询 `bank_record`，再进入 `success_ds` 或 `success_df`。
- 重复流水不再返回 `10019`，而是返回 `Duplicate statement accepted`，避免上游反复重试导致噪声。
- 当历史 `bank_record.callback=0` 时，采集入口不重复推进业务回调，保留补单链路处理权。
- D7pay 租户配置、K8s、Jenkins、域名、APK、运行时配置未参与本次同步。

## 验收记录

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py -q
```

结果：`4 passed, 2 subtests passed`

```bash
python3 -m py_compile api/application/pay/order.py
```

结果：通过

```bash
python3 -m pytest api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_jazzcash_bill_worker_final_state.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_timezone_policy.py -q
```

结果：`30 passed, 7 subtests passed`

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

结果：`D7pay release contract OK`

```bash
rg -n "Asia/Shanghai|datetime\.today\(\)\.date\(\)" api admin merchant -g '*.py'
```

结果：无匹配
