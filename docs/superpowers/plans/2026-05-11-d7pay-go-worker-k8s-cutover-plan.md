# D7pay Go Worker K8s Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D7pay 后台任务切到 `pk-d7pay` namespace 的独立 Go worker，并让 API 退为 Web-only，同时保证上游 `tradeTime/TRX_DTTM` 巴基斯坦时间转 UTC。

**Architecture:** K8s 仓库负责 D7pay worker Deployment、API Web-only start 模板、schema、Jenkins 合同和文档；Go worker 仓库负责时间解析实现和 Go 验收。发布仍由 Jenkins 执行，Makefile 不接管业务镜像发布。

**Tech Stack:** K8s YAML、Bash、MySQL DDL、Python unittest、Go、asynq。

---

### Task 1: D7pay K8s 切流合同

**Files:**
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/k8s/go-worker-deployments.yaml`
- Create: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/runtime/api-start-web-only.sh`
- Create: `/Users/tear/pk_project_k8s/api/sql/20260510_go_worker_phase0_schema.sql`
- Create: `/Users/tear/pk_project_k8s/api/sql/20260510_go_worker_balance_changed_scan.sql`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/jenkins.env.example`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/scripts/preflight.sh`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tests/test_config_only_release.py`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: 新增 Go worker 四个 Deployment**

四个 Deployment 全部放在 `pk-d7pay`，引用 `d7pay-config` 和 `d7pay-secret`，默认副本 1。

- [x] **Step 2: 新增 API Web-only start 模板**

脚本只启动 nginx 和 `python main.py --port=9000`，不包含任何 Python jobs。

- [x] **Step 3: 带入 Go worker schema**

从当前业务源同步 outbox、scan audit、transfer intent、balance snapshot DDL。

- [x] **Step 4: 更新 Jenkins 合同**

增加 Go worker 镜像、API start 脚本、D7pay MySQL database 变量。

- [x] **Step 5: 增加合同测试**

测试检查 manifest namespace/mode/env、Web-only start 模板不包含 Python jobs、schema 表存在。

### Task 2: Go worker tradeTime UTC 边界

**Files:**
- Modify: `/Users/tear/pk-go-worker/internal/collect/provider.go`
- Modify: `/Users/tear/pk-go-worker/internal/collect/provider_test.go`
- Modify: `/Users/tear/pk-go-worker/README.md`
- Modify: `/Users/tear/pk-go-worker/build.md`
- Modify: `/Users/tear/pk-go-worker/err.md`

- [x] **Step 1: 修正无时区 tradeTime 解析**

无时区时间按 `Asia/Karachi` 解析后转 UTC；RFC3339 带时区值按原时区转 UTC。

- [x] **Step 2: 增加专项测试**

`2026-05-10 17:05:00` 应转为 `2026-05-10T12:05:00Z`。

- [x] **Step 3: 更新 Go worker 文档**

明确系统/MySQL/Redis UTC，上游无时区账单时间按巴基斯坦时间解释。

### Task 3: 验收与提交

- [x] **Step 1: 运行 D7pay 合同检查**

Run: `python3 ops/tenants/d7pay/verify_release_contract.py`

实际结果：通过，输出 `D7pay release contract OK`。

- [x] **Step 2: 运行 D7pay 单测**

Run: `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v`

实际结果：通过，10 个测试全部 `ok`。

- [x] **Step 3: 运行 YAML 与 Bash 检查**

Run: `python3 - <<'PY' ... yaml.safe_load_all ... PY && bash -n ops/tenants/d7pay/runtime/api-start-web-only.sh`

实际结果：通过，输出 `yaml ok`，脚本语法检查无错误。

- [x] **Step 4: 运行 Go 验收**

Run: `cd /Users/tear/pk-go-worker && go test ./... && go vet ./... && go build ./cmd/worker`

实际结果：通过；专项 `TestParseStatementTimeTreatsNaiveTradeTimeAsPakistanAndReturnsUTC` 通过。

- [x] **Step 5: 运行 GitNexus 变更检查**

Run: `npx gitnexus detect-changes --repo pk_project_k8s`

实际结果：17 个文件、20 个符号、0 个受影响流程、风险 low。

- [ ] **Step 6: 两个仓库提交并推送**

分别提交并推送 `/Users/tear/pk_project_k8s` 的 `d7pay` 分支和 `/Users/tear/pk-go-worker` 的 `d7pay` 分支。
