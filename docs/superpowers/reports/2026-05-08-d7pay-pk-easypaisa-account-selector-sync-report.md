# D7pay 同步 pk_project EasyPaisa 派单清理报告

## 同步范围

- 同步来源：`/Users/tear/pk_project`
- 来源提交：
  - `5851bbe fix: make statement callbacks idempotent`
  - `6f37e95 chore: remove dead code from easypaisa account_selector`
  - `3dcae39 docs: update auto-payout split spec after dead code removal`
- 同步目标：`/Users/tear/pk_project_k8s`，分支 `d7pay`
- 同步文件：
  - `api/jobs/easypaisa/payout/account_selector.py`
  - `docs/superpowers/plans/2026-05-08-payout-idempotency-final-state-plan.md`
  - `docs/superpowers/reports/2026-05-08-payout-idempotency-final-state-report.md`
  - `docs/superpowers/specs/2026-05-08-payout-idempotency-final-state-design.md`
  - `docs/superpowers/specs/2026-05-08-auto-payout-split-design.md`

## 业务结果

- 移除 EasyPaisa `account_selector.py` 内旧的单订单选卡入口 `get_available_accounts` 和 `prepare_account_and_locks`。
- 保留当前批量预分配调度链路，账号筛选入口继续以 `get_real_available_accounts` 为主。
- 避免旧入口和当前派单入口同时存在，降低后续误用和维护成本。
- 同步 pk_project 对代付幂等和自动代付拆分设计文档的最新描述。
- 未改动 D7pay 租户配置、K8s、Jenkins、域名、APK 和运行时密钥配置。

## 验收记录

```bash
python3 -m pytest api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_payout_state_machine.py api/tests/test_timezone_policy.py -q
```

结果：`26 passed, 7 subtests passed`

```bash
python3 -m py_compile api/jobs/easypaisa/payout/account_selector.py api/application/pay/order.py
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
