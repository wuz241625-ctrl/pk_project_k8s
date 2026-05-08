# D7pay 同步 pk_project 代付幂等与终态报告

## 同步范围

- 同步来源：`/Users/tear/pk_project`，提交 `cdc3068 fix: align payout and callback idempotency`
- 同步目标：`/Users/tear/pk_project_k8s`，分支 `d7pay`
- 同步模块：
  - `api/jobs/Jazzcashpay_v2.py`
  - `api/jobs/pakistanpay_v2.py`
  - `api/jobs/jazzcash/payout/order_lifecycle.py`
  - `api/jobs/jazzcash/payout/settlement.py`
  - `api/jobs/jazzcash/payout/transfer_executor.py`
  - `api/tests/test_jazzcash_auto_payout_v16.py`
  - `api/tests/test_jazzcash_payout_state_machine.py`
  - `api/tests/test_statement_callback_mysql_idempotency.py`

## 保留边界

- 未同步 pk_project 未跟踪文件。
- 未同步 app-h5、lakshmi_uniapp、runtime、指纹、临时文件。
- 未改动 D7pay 租户配置、K8s YAML、Jenkins 发布入口、域名、证书、APK 下载配置。
- 保持数据库 UTC 存储策略，应用层展示巴基斯坦时间的既有约束不变。

## 业务结果

- JazzCashBusiness 代付只有 `402` 作为明确失败重试信号。
- `402` 前两次回到待处理池，第 3 次走驳回退款。
- 非明确失败不再回到待处理池，进入人工待确认，避免重复出款。
- 成功终态只允许由结算逻辑在状态保护条件下写入。
- 对账回调以 MySQL 订单状态作为幂等真相源，不再用 Redis marker 跳过必要回调。

## 验收记录

```bash
python3 -m pytest api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_statement_callback_mysql_idempotency.py -q
```

结果：`11 passed, 7 subtests passed`

```bash
python3 -m pytest api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_jazzcash_bill_worker_final_state.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_timezone_policy.py -q
```

结果：`28 passed, 7 subtests passed`

```bash
python3 -m py_compile api/jobs/Jazzcashpay_v2.py api/jobs/pakistanpay_v2.py api/jobs/jazzcash/payout/order_lifecycle.py api/jobs/jazzcash/payout/settlement.py api/jobs/jazzcash/payout/transfer_executor.py
```

结果：通过

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

结果：`D7pay release contract OK`

```bash
rg -n "Asia/Shanghai|datetime\.today\(\)\.date\(\)" api admin merchant -g '*.py'
```

结果：无匹配
