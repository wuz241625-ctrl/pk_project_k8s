# D7pay Runtime Env Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 D7pay 运行配置对象名统一到线上实际 `d7pay-runtime-config` / `d7pay-runtime-secret`。

**Architecture:** 只调整 K8s 配置模板、发布合同检查、测试和文档，不修改应用业务逻辑。运行时仍由 ConfigMap 提供非敏感配置、Secret 提供敏感凭据，API/Admin/Merchant/Go worker 使用同一组对象。

**Tech Stack:** Kubernetes YAML、Python unittest、发布合同脚本、Markdown 文档。

---

### Task 1: 统一 K8s 对象名

**Files:**
- Modify: `ops/tenants/d7pay/k8s/app-configmap.yaml`
- Modify: `ops/tenants/d7pay/k8s/app-secret.example.yaml`
- Modify: `ops/tenants/d7pay/k8s/api-deployment-env.patch.yaml`
- Modify: `ops/tenants/d7pay/k8s/admin-deployment-env.patch.yaml`
- Modify: `ops/tenants/d7pay/k8s/merchant-deployment-env.patch.yaml`
- Modify: `ops/tenants/d7pay/tenant.yaml`

- [ ] **Step 1: Replace object names**

Change ConfigMap object references from `d7pay-config` to `d7pay-runtime-config`, and Secret object references from `d7pay-secret` to `d7pay-runtime-secret`.

- [ ] **Step 2: Verify no runtime template still points at old objects**

Run:

```bash
rg -n "name: d7pay-config|name: d7pay-secret|config_map: d7pay-config|secret: d7pay-secret" ops/tenants/d7pay/k8s ops/tenants/d7pay/tenant.yaml
```

Expected: no output.

### Task 2: Update Contract And Tests

**Files:**
- Modify: `ops/tenants/d7pay/verify_release_contract.py`
- Modify: `ops/tenants/d7pay/tests/test_config_only_release.py`

- [ ] **Step 1: Update object-name assertions**

Require `d7pay-runtime-config` and `d7pay-runtime-secret` in app patches and Go worker manifest.

- [ ] **Step 2: Update Go worker mode assertions**

The current Go worker manifest starts each component through shell commands, so assert the command contains `-mode=worker`, `-mode=relay`, `-mode=scheduler`, and `-mode=ops-scheduler` instead of old `args: ["-mode=..."]` array syntax.

- [ ] **Step 3: Run tests**

Run:

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v
```

Expected: both pass.

### Task 3: Update Docs

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `ops/tenants/d7pay/build.md`
- Modify: `ops/tenants/d7pay/README_OPERATIONS.md`
- Modify: `ops/tenants/d7pay/current-deployment-ops-runbook.md`
- Modify: `ops/tenants/d7pay/err.md`
- Modify: `ops/tenants/d7pay/jenkins.env.example`

- [ ] **Step 1: Document source files**

Record `/opt/cicd/secrets/d7pay.env` as the non-sensitive runtime env source, and `/opt/cicd/secrets/d7pay-runtime-secret.yaml` as the Secret manifest source.

- [ ] **Step 2: Remove old object names from operational instructions**

Operational commands should use `d7pay-runtime-config` / `d7pay-runtime-secret`. Any remaining old names must be explicitly marked as historical examples or local file names.

- [ ] **Step 3: Run grep acceptance**

Run:

```bash
rg -n "d7pay-config|d7pay-secret" ops/tenants/d7pay api/build.md api/err.md
```

Expected: no active runtime object assertions use old names.

### Task 4: Final Verification And Git

**Files:**
- All files changed above.

- [ ] **Step 1: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 2: Run GitNexus staged detect**

Expected: risk low and no affected execution flows.

- [ ] **Step 3: Commit and push**

Run:

```bash
git add <changed-files>
git commit -m "chore: align d7pay runtime config naming"
git push origin d7pay
```
