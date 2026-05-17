# TimeOutGuard 退役实施计划

日期：2026-05-17
分支：`d7pay`

## 1. 计划

- [x] 确认 `/Users/tear/pk-go-worker` 已接管 timeout jobs。
- [x] 运行 GitNexus impact，确认 `api/jobs/time_out.py` 修改影响面。
- [x] 用 TDD 改造 `test_easypaisa_timeout_guard.py`，先让测试因 `TimeOutGuard` 仍存在而失败。
- [x] 删除 `api/jobs/time_out.py::TimeOutGuard`，不改旧脚本其他业务逻辑。
- [x] 更新 spec、plan、build、err 文档，说明 Go worker 是 timeout job owner。
- [x] 运行 Python 与 Go worker 验收。
- [x] 运行 GitNexus staged detect_changes。
- [x] commit 并 push `d7pay`。

## 2. 验收标准

- `cd api && python3 -m pytest tests/test_easypaisa_timeout_guard.py -q`
- `cd api && python3 -m pytest tests/ -q -k easypaisa`
- `cd /Users/tear/pk-go-worker && go test ./internal/timeout ./tasks`
- `rg -n "class TimeOutGuard|INDEX_DISPATCH_DS" api/jobs`
- GitNexus `detect_changes(scope=staged)` 风险符合预期。

## 3. 执行记录

- GitNexus impact：`TimeOutGuard` 未在索引中；`api/jobs/time_out.py` 文件级 upstream 风险 LOW，直接影响仅 `api/tests/test_easypaisa_timeout_guard.py`，受影响流程 0。
- TDD 红灯：`test_python_timeout_guard_class_is_retired` 先失败，原因是 `api/jobs/time_out.py` 仍包含 `class TimeOutGuard`。
- 实现：删除 `TimeOutGuard` 兼容类；测试改为退役守护，并校验 Go worker 任务类型与 handler 注册。
- 验收：
  - `cd api && python3 -m pytest tests/test_easypaisa_timeout_guard.py -q`：`2 passed`。
  - `cd api && python3 -m pytest tests/ -q -k easypaisa`：`153 passed, 152 deselected`。
  - `cd /Users/tear/pk-go-worker && go test ./internal/timeout ./tasks`：通过。
  - `rg -n "class TimeOutGuard|INDEX_DISPATCH_DS" api/jobs`：无输出。
- GitNexus staged detect_changes：8 个 staged 文件，risk level `low`，affected processes 0。
- 提交并推送：`chore(easypaisa): retire legacy TimeOutGuard` 已推送到 `origin/d7pay`。
