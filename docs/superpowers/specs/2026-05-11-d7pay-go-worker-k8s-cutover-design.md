# D7pay Go Worker K8s 切流设计

## 背景

D7pay 当前已经有独立 `pk-d7pay` namespace。后台任务不应继续和 API Web 服务混在同一个容器里运行；Go worker 应作为独立服务承接代收采集、代付执行、通知、超时和健康检查。切流后 API 只保留 HTTP 入口，Python jobs 退役。

同时，EasyPaisa/JazzCash 上游账单里的无时区 `tradeTime/TRX_DTTM` 是巴基斯坦时间，而系统、Pod、Redis、MySQL 都按 UTC 运行。Go worker 必须在上游时间进入订单窗口比较前转成 UTC。

## 方案

1. D7pay K8s 增加 `ops/tenants/d7pay/k8s/go-worker-deployments.yaml`，在 `pk-d7pay` 部署四个 Deployment：
   - `d7pay-go-worker`：消费 asynq，执行采集、代收结算、代付、通知、超时和健康任务。
   - `d7pay-go-worker-relay`：搬运 MySQL outbox 到 asynq。
   - `d7pay-go-worker-scheduler`：扫描订单窗口并写账单扫描 outbox。
   - `d7pay-go-worker-ops`：写代付、通知、超时和健康检查 outbox。
2. D7pay API 增加 Web-only start 模板 `ops/tenants/d7pay/runtime/api-start-web-only.sh`，切流后不再启动 Python jobs。
3. D7pay 分支携带 Go worker schema：`api/sql/20260510_go_worker_phase0_schema.sql` 和 `api/sql/20260510_go_worker_balance_changed_scan.sql`。
4. Jenkins 环境模板增加 `GO_WORKER_IMAGE`、`GO_WORKER_REPLICAS`、`APP_MYSQL_DATABASE`、`D7PAY_API_START_TEMPLATE`。
5. `pk-go-worker` 中 `parseStatementTime()` 对 RFC3339 带时区值转 UTC；对无时区值按 `Asia/Karachi` 解析后转 UTC。

## 验收标准

- D7pay release contract 通过。
- D7pay 配置发布测试通过，覆盖 Go worker manifest、Web-only start 模板、worker schema。
- D7pay K8s YAML 全部可解析。
- API Web-only 模板 `bash -n` 通过。
- `pk-go-worker` 执行 `go test ./...`、`go vet ./...`、`go build ./cmd/worker` 通过。
- `go test ./internal/collect -run TestParseStatementTimeTreatsNaiveTradeTimeAsPakistanAndReturnsUTC -v` 通过。
- GitNexus detect-changes 显示低风险或可解释的文档/运维变更。
