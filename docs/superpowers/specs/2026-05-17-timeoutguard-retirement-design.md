# TimeOutGuard 退役设计

日期：2026-05-17
分支：`d7pay`

## 1. 背景

D7pay timeout jobs 已迁到 `/Users/tear/pk-go-worker`：

- Go worker `tasks.TypeCollectOrderTimeout` 处理代收订单超时。
- Go worker `tasks.TypePayoutClaimTimeout` 处理代付抢单超时。
- API Pod 不再启动 Python `api/jobs/time_out.py` 作为在线 timeout job。

本仓库此前为通过 EasyPaisa 回归测试，在 `api/jobs/time_out.py` 临时恢复了 `TimeOutGuard` 兼容类。当前在线 job 入口已经统一到 Go worker，该类不再承担运行时职责，继续保留会误导后续同步把旧 Redis 回压逻辑带回。

## 2. 头脑风暴结论

候选方案：

- 保留 `TimeOutGuard`：回归最少，但会让 Python 旧 job 看起来仍是 timeout owner。
- 删除整个 `time_out.py`：清理最彻底，但会扩大回滚脚本风险，本次没有必要。
- 只退役 `TimeOutGuard`：保留旧脚本表面，删除已无 owner 的兼容类，并用测试守护 Go worker 归属。

选定第三种：只删除 `TimeOutGuard` 兼容类，保留 `time_out.py` 其他逻辑不动。

## 3. 设计

- `api/jobs/time_out.py` 删除 `TimeOutGuard` 类和 `INDEX_DISPATCH_DS` 常量。
- `api/tests/test_easypaisa_timeout_guard.py` 改为退役守护：
  - 断言 Python 旧脚本不再定义 `TimeOutGuard`。
  - 断言 `/Users/tear/pk-go-worker` 中 collect/payout timeout handler 已注册并有任务类型。
- 文档明确 timeout job owner 为 Go worker，避免后续业务同步重新恢复旧兼容类。

## 4. 验收标准

- AC1：`api/jobs/time_out.py` 不再包含 `class TimeOutGuard`。
- AC2：`api/jobs/time_out.py` 不再包含 `INDEX_DISPATCH_DS` 兼容常量。
- AC3：退役守护测试通过：`cd api && python3 -m pytest tests/test_easypaisa_timeout_guard.py -q`。
- AC4：EasyPaisa 回归通过：`cd api && python3 -m pytest tests/ -q -k easypaisa`。
- AC5：Go worker timeout 单测通过：`cd /Users/tear/pk-go-worker && go test ./internal/timeout ./tasks`。
- AC6：提交前运行 GitNexus `detect_changes(scope=staged)`，确认影响面符合预期。

## 5. 风险

影响面为 LOW。GitNexus 对 `api/jobs/time_out.py` 的文件级 upstream 影响只命中 `api/tests/test_easypaisa_timeout_guard.py`，未命中执行流程。
