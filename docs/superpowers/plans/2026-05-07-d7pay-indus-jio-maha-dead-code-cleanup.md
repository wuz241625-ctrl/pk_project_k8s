# D7pay Indus/Jio/Maha Dead Code Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 D7pay 分支中已确认不进当前运行链路的 Indus/Jio/Maha/GCash/Freecharge 旧代码和旧 Docker 制品。

**Architecture:** 保持 EasyPaisa、JazzCash、API `/v1`、代收代付、三方回调主链路不变。删除只覆盖 GitNexus 无外部 incoming 且 D7pay 发布脚本不引用的目录，并用发布合同阻止回流。

**Tech Stack:** GitNexus、Git、Tornado Python 服务、D7pay Jenkins/K8s 发布合同。

---

### Task 1: 删除死代码和旧制品

**Files:**
- Delete: `api/jobs/freecharge-monitor/php/`
- Delete: `api/application/app/login/banks/gcash_bank.py`
- Delete: `api/application/app/login/banks/indus_bank.py`
- Delete: `api/docker/`
- Delete: `api/jobs/induspay/`
- Delete: `api/jobs/jio/`
- Delete: `api/jobs/maha/`
- Delete: `merchant/.config.py.swp`

- [x] **Step 1: 用 GitNexus 验证候选入口无外部 imports**

Run:

```bash
gitnexus cypher -r pk_project_k8s "MATCH (f:File) WHERE f.filePath IN ['api/application/app/login/banks/gcash_bank.py','api/application/app/login/banks/indus_bank.py','api/docker/app/Dockerfile','api/jobs/freecharge-monitor/php/index.php','api/jobs/induspay/induspay.py','api/jobs/jio/jio.py','api/jobs/maha/maha.py'] OPTIONAL MATCH (x)-[r]->(f) WHERE r.type='IMPORTS' WITH f, count(r) AS importsIn RETURN f.filePath AS filePath, importsIn ORDER BY filePath"
```

Expected: 每个候选入口 `importsIn` 为 0。

- [x] **Step 2: 删除候选路径**

Run:

```bash
git rm -r api/jobs/freecharge-monitor/php api/docker api/jobs/induspay api/jobs/jio api/jobs/maha
git rm api/application/app/login/banks/gcash_bank.py api/application/app/login/banks/indus_bank.py merchant/.config.py.swp
```

Expected: Git 暂存删除记录。

### Task 2: 更新文档和发布合同

**Files:**
- Modify: `docs/branches/d7pay.md`
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: 更新清理边界文档**

写明 D7pay 分支不再保留旧 Freecharge PHP、GCash/Indus 独立登录实现、旧 API Docker、Indus/Jio/Maha worker 和 tracked swap 文件。

- [x] **Step 2: 更新发布合同**

在 `ops/tenants/d7pay/verify_release_contract.py` 中增加路径存在性拦截，避免旧目录和旧文件重新提交。

### Task 3: 验收

**Files:**
- Test: repository checks

- [x] **Step 1: 验证删除路径不再被 Git 跟踪**

Run:

```bash
test -z "$(git ls-files api/jobs/freecharge-monitor/php api/docker api/jobs/induspay api/jobs/jio api/jobs/maha api/application/app/login/banks/gcash_bank.py api/application/app/login/banks/indus_bank.py merchant/.config.py.swp)"
```

Expected: 命令退出码为 0。

- [x] **Step 2: 验证没有业务引用删除路径**

Run:

```bash
rg -n "gcash_bank|indus_bank|api/docker|freecharge-monitor/php|jobs/induspay|jobs/jio|jobs/maha|api/jobs/induspay|api/jobs/jio|api/jobs/maha" . -g '!docs/superpowers/plans/2026-05-07-d7pay-indus-jio-maha-dead-code-cleanup.md' -g '!docs/superpowers/specs/2026-05-07-d7pay-indus-jio-maha-dead-code-cleanup-design.md'
```

Expected: 只允许文档和发布合同中的清理说明命中。

- [x] **Step 3: 编译关键服务文件**

Run:

```bash
PYTHONPATH=api python3 -m py_compile api/main.py api/router.py api/router_lakshmi.py api/application/jazzcash_gateway.py api/application/pay/pay.py api/application/pay/order.py api/application/app/login/banks/easypaisa.py api/application/app/login/banks/jazzcash.py api/jobs/pakistanpay_v2.py api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/easypaisa_monitor.py api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_monitor.py api/jobs/Jazzcashpay_v2.py
PYTHONPATH=admin python3 -m py_compile admin/main.py admin/router.py admin/application/partner/partner.py admin/application/order/order.py
PYTHONPATH=merchant python3 -m py_compile merchant/main.py merchant/router.py merchant/application/order/order.py
```

Expected: 三条命令退出码为 0。

- [x] **Step 4: 运行 D7pay 合同和配置测试**

Run:

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release
git diff --check
```

Expected: 合同输出 `D7pay release contract OK`，单测 OK，diff check 无输出。

- [ ] **Step 5: 提交并推送**

Run:

```bash
git add -A
git commit -m "cleanup: remove d7pay unused bank artifacts"
git push origin d7pay
```

Expected: 推送成功。
