# D7pay Online Release Doc Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让本地 D7pay 运维文档与当前线上 Jenkins 发布事实保持一致，避免误用 Makefile 或未上线 Go worker 草稿改乱线上。

**Architecture:** 以线上 `/opt/cicd/k8s_d7pay/sh/deploy-*.sh` 为发布事实源，文档只描述当前可执行链路；未来 Go worker 切流不写成当前发布入口。用单测固定文档合同。

**Tech Stack:** Markdown 文档、Python `unittest`、现有 D7pay release contract 验证脚本。

---

### Task 1: 收口本次修改范围

**Files:**
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/README_OPERATIONS.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/build.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/current-deployment-ops-runbook.md`
- Modify: `/Users/tear/pk_project_k8s/docs/rental/d7pay-hosted.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/err.md`
- Modify: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tests/test_config_only_release.py`

- [x] **Step 1: 清理未上线草稿**

保留文档同步范围，移除本次不应提交的 Go worker 草稿代码和生成缓存。

- [x] **Step 2: 更新一页 SOP**

写清 Jenkins 发布脚本路径、Makefile 职责边界、当前 API Python jobs、Go worker 非当前入口。

- [x] **Step 3: 更新构建文档**

写清线上脚本的固定发布步骤，以及 admin-h5、merchant-h5、apkdownload、api 当前构建/启动模式。

- [x] **Step 4: 更新 runbook 和托管文档**

新增 2026-05-11 当前线上发布事实源，移除或覆盖过期“未部署”结论。

- [x] **Step 5: 增加排错条目**

记录误用 Makefile 当线上发布入口的现象、原因、处理和验收。

- [x] **Step 6: 增加合同测试**

验证文档必须包含 Jenkins 脚本、线上工作目录、`git reset --hard origin/d7pay`、Python jobs 和 Go worker 非当前入口说明。

### Task 2: 验证和提交

**Files:**
- Test: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/tests/test_config_only_release.py`
- Test: `/Users/tear/pk_project_k8s/ops/tenants/d7pay/verify_release_contract.py`

- [x] **Step 1: 运行 D7pay release contract**

Run: `python3 ops/tenants/d7pay/verify_release_contract.py`

Expected: exit 0。实际结果：`D7pay release contract OK`。

- [x] **Step 2: 运行 D7pay 配置发布测试**

Run: `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v`

Expected: exit 0，所有测试通过。实际结果：9 个测试通过。

- [x] **Step 3: 运行 GitNexus 变更检查**

Run: `npx gitnexus detect-changes --repo pk_project_k8s`

Expected: 只出现文档和测试合同相关变化。实际结果：6 个已跟踪文件、24 个符号、0 个受影响流程、低风险。

- [ ] **Step 4: 提交并推送**

Run:

```bash
git add docs/rental/d7pay-hosted.md docs/superpowers/specs/2026-05-11-d7pay-online-release-doc-sync-design.md docs/superpowers/plans/2026-05-11-d7pay-online-release-doc-sync-plan.md ops/tenants/d7pay/README_OPERATIONS.md ops/tenants/d7pay/build.md ops/tenants/d7pay/current-deployment-ops-runbook.md ops/tenants/d7pay/err.md ops/tenants/d7pay/tests/test_config_only_release.py
git commit -m "docs: align d7pay release docs with jenkins"
git push origin d7pay
```
