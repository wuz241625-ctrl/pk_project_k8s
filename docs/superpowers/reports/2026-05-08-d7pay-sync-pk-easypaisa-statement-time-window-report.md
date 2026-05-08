# D7pay 同步 PK EasyPaisa 账单时间窗口报告

## 背景

本次同步 `/Users/tear/pk_project` 最新提交 `07fe60b`。该提交修复 EasyPaisa 代收账单预匹配只按付款手机号和金额判断的问题，避免历史同手机号同金额流水误命中新订单。

## 同步内容

- `api/jobs/pakistanpay_v2.py`
  - `_credit_statement_matches_due_order()` 新增账单时间判断。
  - 只有当 `orders_ds.time_create <= statement.tradeTime <= orders_ds.time_create + 8 分钟` 时才允许预匹配成功。
  - 如果账单缺少可解析 `tradeTime` 或订单缺少可解析 `time_create`，不允许预匹配。
- `api/tests/easypaisa_runtime/test_statement_order_scheduler.py`
  - 新增历史流水不回调测试。
  - 保留订单窗口内同手机号同金额流水正常回调测试。

## 验收标准

- 历史同手机号同金额 EasyPaisa CREDIT 流水不会触发 `/order/Success`。
- 订单创建后 8 分钟内的同手机号同金额 CREDIT 流水仍能正常回调。
- 不改变 D7pay 已同步的 `status IN (1,2)` 与官方 `extOrderNo` 口径。

## 验收结果

- `api/jobs/pakistanpay_v2.py` 与 `/Users/tear/pk_project` 当前提交对应文件一致。
- `api/tests/easypaisa_runtime/test_statement_order_scheduler.py` 与 `/Users/tear/pk_project` 当前提交对应文件一致。
- `PYTHONPATH=api python3 -m unittest api.tests.easypaisa_runtime.test_statement_order_scheduler -v` 通过：19 tests OK。
- `python3 -m py_compile api/jobs/pakistanpay_v2.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py` 通过。
- 受影响测试合并执行通过：129 passed，5 subtests passed。
- `git diff --check` 通过。
- GitNexus detect changes 风险为 low。
