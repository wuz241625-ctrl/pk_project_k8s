# D7pay Ops Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 明确运维唯一入口文档，并把现有 `pk` 部署的处理策略写入 D7pay 运维文档和验收标准。

**Architecture:** `ops/tenants/d7pay/current-deployment-ops-runbook.md` 作为唯一执行入口；`docs/rental/d7pay-hosted.md` 作为交付边界说明；`ops/tenants/d7pay/acceptance.md` 作为验收清单；`docs/superpowers` 记录设计与执行计划。

**Tech Stack:** Markdown、Kubernetes、nginx、Jenkins、D7pay 租户发布合同。

---

### Task 1: 明确运维唯一入口

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`

- [x] **Step 1: 在 runbook 顶部写明入口**

写入运维只从 `ops/tenants/d7pay/current-deployment-ops-runbook.md` 开始，`acceptance.md`、`jenkins.env.example`、`k8s/` 和 `docs/rental/d7pay-hosted.md` 只是引用。

- [x] **Step 2: 写明不能从单个 YAML 开始**

说明 `tenant.yaml`、`runtime-configmap.yaml`、patch 文件缺少当前线上状态、备份、域名、回滚和验收顺序。

### Task 2: 写清现有部署处理策略

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`

- [x] **Step 1: 增加现有部署处理原则**

现有 `pk` 保留，不删除、不缩容、不改 Service、不改现有 NodePort；现有 `awekay.com` 域名继续指向当前业务。

- [x] **Step 2: 增加 D7pay 新增隔离实例原则**

D7pay 新增 `pk-d7pay`、独立 database、独立 Redis、独立 PVC、专属 NodePort 和客户自有域名。

- [x] **Step 3: 增加上线第 0 步**

上线前先检查 `pk`、`pk-d7pay` 和 `pk` Service，确认 D7pay 不是替换现有部署。

### Task 3: 同步交付与验收文档

**Files:**
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/acceptance.md`

- [x] **Step 1: 托管说明写入运维唯一入口**

`docs/rental/d7pay-hosted.md` 的已落地配置中把 runbook 标成运维唯一入口。

- [x] **Step 2: 托管说明写入现有部署保护**

说明 D7pay 首次上线新增 `pk-d7pay`，不替换 `pk`，不复用 `pk` 的 `30080-30085`。

- [x] **Step 3: 验收标准加入现有部署保护**

验收项要求 `pk` 保持运行，`awekay.com` 保持原业务入口，运维必须从 runbook 执行。

### Task 4: 保存设计与校验

**Files:**
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/specs/2026-04-29-d7pay-ops-handoff-design.md`
- Create: `/Users/tear/pk_project_k8s/docs/superpowers/plans/2026-04-29-d7pay-ops-handoff.md`

- [x] **Step 1: 保存设计文档**

记录头脑风暴方案、选型和验收标准。

- [x] **Step 2: 运行校验命令**

```bash
python3 -m py_compile ops/tenants/d7pay/verify_release_contract.py
python3 ops/tenants/d7pay/verify_release_contract.py
bash -n ops/tenants/d7pay/jenkins/deploy-d7pay.sh
python3 - <<'PY'
import pathlib, yaml
for path in sorted(pathlib.Path('ops/tenants/d7pay/k8s').glob('*.yaml')):
    with path.open(encoding='utf-8') as fh:
        list(yaml.safe_load_all(fh))
print('D7pay k8s yaml parse OK')
PY
git diff --check
```

预期全部退出码为 0。
