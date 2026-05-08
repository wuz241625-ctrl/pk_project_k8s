# D7pay 同步 PK EasyPaisa 官方流水号和 Status IN(1,2) 报告

## 背景

本次继续同步 `/Users/tear/pk_project` 最新提交到 D7pay。PK 最新业务口径包含两个关键变化：

- EasyPaisa 账单回调 `trans_id` 只认官方 `historyDetailRspDTO.extOrderNo`。
- EasyPaisa 代收账单调度允许已提交付款手机号的 `orders_ds.status IN (1,2)` 订单进入采集确认闭环。

## 同步内容

- `api/jobs/pakistanpay_v2.py`
  - `_extract_statement_ref()` 只读取 `historyDetailRspDTO.extOrderNo`。
  - 缺少 `extOrderNo` 的 CREDIT/PAY 映射直接跳过并记录告警。
  - 代收 due SQL 从 `status = 2` 改为 `status IN (1, 2)`。
  - 未匹配日志改为 `status IN (1,2) 已提交手机号订单`。
- `api/application/websocket/callback.py`
  - Pakistan CREDIT 匹配 SQL 与最终更新 SQL 允许 `status IN (1,2)`。
  - 保留 `FOR UPDATE` 和严格的订单匹配条件。
- 测试同步：
  - `api/tests/easypaisa_runtime/test_statement_order_scheduler.py`
  - `api/tests/test_easypaisa_multi_worker_guards.py`

## D7pay 保留差异

- 不恢复 `api/sql/runtime_init_from_remote_config.sql`。
- `api/tests/test_easypaisa_multi_worker_guards.py` 不检查 runtime 初始化脚本。

## 验收标准

- EasyPaisa 账单官方流水号只使用 `historyDetailRspDTO.extOrderNo`。
- 缺少 `extOrderNo` 时不生成 mapped transaction。
- EasyPaisa 代收 due SQL 包含 `status IN (1, 2)`。
- Pakistan CREDIT 成功确认 SQL 保留 `FOR UPDATE` 并允许 `status IN (1, 2)`。
- D7pay runtime 清理方向不回退。

## 验收结果

- `api/jobs/pakistanpay_v2.py`、`api/application/websocket/callback.py`、`api/tests/easypaisa_runtime/test_statement_order_scheduler.py` 与 `/Users/tear/pk_project` 当前提交对应文件一致。
- `api/tests/test_easypaisa_multi_worker_guards.py` 仅保留 D7pay 不检查 runtime 初始化脚本的差异。
- `PYTHONPATH=api python3 -m unittest api.tests.easypaisa_runtime.test_statement_order_scheduler -v` 通过：18 tests OK。
- `python3 -m pytest api/tests/test_easypaisa_multi_worker_guards.py api/tests/test_statement_callback_mysql_idempotency.py -q` 通过：12 passed，5 subtests passed。
- 受影响测试合并执行通过：128 passed，5 subtests passed。
- `python3 -m py_compile api/jobs/pakistanpay_v2.py api/application/websocket/callback.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/test_easypaisa_multi_worker_guards.py` 通过。
- `git diff --check` 通过。
- GitNexus detect changes 风险为 medium，影响集中在 EasyPaisa `grabstatement` 账单扫描流程，符合本次同步范围。
