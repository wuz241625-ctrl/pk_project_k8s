# Go-Worker Health Check 501 不重试 + 消除无效日志

## 问题描述

go-worker 的 health check 和 collect handler 在云机返回 501（AccountCompromised）时，虽然已经调用 `DisableCompromisedAccount` 禁用了账号，但 `Handle` 方法仍然 return error，触发 asynq 默认 25 次指数退避重试。

**线上表现**（2026-05-13 日志）：
- payment_id=533296 从 16:50 到次日 00:13 持续打 `CRITICAL: 501 账号已下线`（间隔从 1 分钟递增到 2 小时 — 指数退避特征）
- `STATUS_CLOSURE: collection+payout closed payment_id=533296 affected=0` 刷屏数百条（账号已关闭，每次 UPDATE 命中 0 行）

## 根因

1. asynq 默认 `MaxRetry=25`，项目未显式设置
2. 501 是确定性失败（被抢登），重试无意义
3. `CloseCollectionAndPayout` 不检查 affected 就打日志

## 修复方案

### 1. Health Handler 前置检查

`fetchAccount` 新增返回 `wallet_status` 字段。Handle 开头检查：
- `wallet_status == 0` → return nil（跳过已禁用账号）

### 2. 501 后 return nil

health handler 和 collect handler 中，501 错误处理完（DisableCompromisedAccount 已执行）后 return nil，告诉 asynq 任务完成不重试。

### 3. 日志静默

`CloseCollectionAndPayout` / `CloseCollectionOnly` 仅在 `affected > 0` 时打日志。

## 影响文件

| 文件 | 仓库 | 变更 |
|------|------|------|
| `internal/health/handler.go` | pk-go-worker | 前置检查 + 501 nil |
| `internal/health/handler_test.go` | pk-go-worker | 新增 2 个测试 |
| `internal/collect/handler.go` | pk-go-worker | 501 后 return nil |
| `internal/gateway/disable.go` | pk-go-worker | affected=0 不打日志 |
| `internal/gateway/disable_test.go` | pk-go-worker | 新增静默测试 |

## 验收标准

1. 501 后 asynq 不再重试该 task
2. wallet_status=0 的 payment 执行 health task 时直接跳过
3. `STATUS_CLOSURE affected=0` 不再出现在日志中
4. 非 501 错误（423/503/网络）仍正常重试
5. collect handler 501 审计记录仍写入，但不重试
6. 所有测试通过

## 部署

commit: `0d7c87e` on `d7pay` branch (pk-go-worker)
需要重新构建 go-worker 镜像并部署到 k8s。
