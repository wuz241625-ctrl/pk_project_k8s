# D7pay EasyPaisa tradeTime UTC 匹配报告

## 背景

D7pay 运行口径是 MySQL 与系统时间保持 UTC，后台和商户展示按巴基斯坦时间转换。EasyPaisa 上游账单返回的 `tradeTime` 是巴基斯坦本地时间；此前账单 worker 直接把该值当作无时区时间与数据库 UTC 字段比较，会导致真实流水被误判为不在订单窗口内。

## 处理

- `api/jobs/pakistanpay_v2.py` 新增数据库时间和上游账单时间的独立解析边界。
- 上游 `tradeTime` 按 `APP_DISPLAY_TIMEZONE` 解析，默认 `Asia/Karachi`，转换为 UTC naive datetime 后比较。
- 数据库 `orders_ds.time_create`、`orders_df.time_accept` 继续按 UTC naive datetime 处理。
- 代收账单确认和代付账单观察共同使用该口径。

## 验收

```bash
PYTHONPATH=api python3 -m unittest api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_payout_statement_match_is_observation_only_without_callback api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_collection_credit_matches_when_statement_time_is_inside_order_window api.tests.easypaisa_runtime.test_statement_order_scheduler.EasyPaisaStatementOrderSchedulerTests.test_collection_credit_rejects_statement_time_after_converted_window -v
```

结果：通过。该用例覆盖巴基斯坦 `tradeTime` 转 UTC 后的代收命中、代收超窗拒绝和代付观察命中。

```bash
python3 -m pytest api/tests/test_easypaisa_multi_worker_guards.py api/tests/test_statement_callback_mysql_idempotency.py api/tests/test_ds_dispatch_candidate_sql.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/jobs/easypaisa/tests/test_account_selector.py api/jobs/easypaisa/tests/test_order_lifecycle.py api/jobs/easypaisa/tests/test_transfer_executor.py -q
```

结果：`130 passed, 3 warnings, 5 subtests passed`。警告来自 `razorpay/pkg_resources` 弃用提示，与本次时间处理无关。
