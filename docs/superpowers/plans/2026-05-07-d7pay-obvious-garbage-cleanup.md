# D7pay Obvious Garbage Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 D7pay 分支中明确无用且低风险的历史制品。

**Architecture:** 保持业务代码和路由不变，只移除不会被当前 D7pay 运行入口引用的仓库垃圾。同步更新文档，说明哪些旧代码暂时不能清理。

**Tech Stack:** Git、Tornado Python 服务、Vite 下载页、D7pay Jenkins/K8s 发布合同。

---

### Task 1: 删除明确垃圾文件

**Files:**
- Delete: `api/jobs/freecharge-monitor/php/vendor/`
- Delete: `api/jobs/easypaisa/auto_payout.py.bak`
- Delete: `apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk`
- Delete: `apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk`
- Delete: `api/docker-compose.yml`
- Delete: `api/static/v2/`
- Modify: `apkdownload/.env`
- Modify: `apkdownload/.env.d7pay`
- Modify: `apkdownload/src/components/Appdownload/index.vue`
- Modify: `apkdownload/package.json`
- Modify: `apkdownload/package-lock.json`
- Modify: `apkdownload/public/files/android/appInfo.json`

- [x] **Step 1: 验证删除候选是否仍被外部引用**

Run:

```bash
rg -n "static/v2|/static/v2|v2/dist|AdminLTE|adminlte" api admin merchant -g '*.*' -g '!api/static/v2/**'
rg -n "docker-compose|api/docker-compose|freecharge-monitor/php/vendor|auto_payout.py.bak|lakshmi_v1.0.0.202406232042.apk|ashrafi_v0.1.6_202604280158.apk" .
```

Expected: 没有业务代码直接依赖这些删除候选；历史文档中的引用需要同步更新。

- [x] **Step 2: 用 Git 删除候选文件**

Run:

```bash
git rm -r api/jobs/freecharge-monitor/php/vendor api/static/v2
git rm api/jobs/easypaisa/auto_payout.py.bak api/docker-compose.yml apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk
```

Expected: Git 暂存删除记录。

- [x] **Step 3: 清理下载页旧品牌兜底**

将 `apkdownload` 默认 app key、兜底 app key、下载元信息和 package 名称改为 D7pay 或中性名称。

### Task 2: 更新文档

**Files:**
- Modify: `docs/branches/d7pay.md`
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `apkdownload/build.md`
- Modify: `apkdownload/err.md`
- Modify: `ops/tenants/d7pay/current-deployment-ops-runbook.md`

- [x] **Step 1: 写入清理边界**

更新文档，明确 D7pay 分支不再保留 PHP vendor、旧客户 APK、旧 compose 和 AdminLTE v2 静态包。

- [x] **Step 2: 保留不可误删说明**

写明 `api/application/lakshmi_api` 当前仍承载 App `/v1` 接口；`application/phonepe` 和旧银行代码已在 2026-05-08 后续清理中参考 `/Users/tear/pk_project` 当前文件移除。本文件保留为当时阶段记录。

### Task 3: 验证与提交

**Files:**
- Test: repository checks

- [x] **Step 1: 验证垃圾路径不存在**

Run:

```bash
test "$(git ls-files api/jobs/freecharge-monitor/php/vendor | wc -l | tr -d ' ')" = "0"
test "$(git ls-files api/static/v2 | wc -l | tr -d ' ')" = "0"
test -z "$(git ls-files api/jobs/easypaisa/auto_payout.py.bak api/docker-compose.yml apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk)"
```

Expected: 所有命令退出码为 0。

- [x] **Step 2: 编译关键服务文件**

Run:

```bash
PYTHONPATH=api python3 -m py_compile api/main.py api/router.py api/router_lakshmi.py api/application/jazzcash_gateway.py api/application/pay/pay.py api/application/pay/order.py api/application/app/login/banks/easypaisa.py api/application/app/login/banks/jazzcash.py api/jobs/pakistanpay_v2.py api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/easypaisa_monitor.py api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_monitor.py
PYTHONPATH=admin python3 -m py_compile admin/main.py admin/router.py admin/application/partner/partner.py admin/application/order/order.py
PYTHONPATH=merchant python3 -m py_compile merchant/main.py merchant/router.py merchant/application/order/order.py
```

Expected: 三条命令退出码为 0。

- [x] **Step 3: 运行 D7pay 合同检查**

Run:

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

Expected: 输出 `D7pay release contract OK`。

- [x] **Step 4: 构建 D7pay 下载页**

Run:

```bash
cd apkdownload
npm run build:d7pay
```

Expected: Vite 构建成功，输出 D7pay logo 资源。

- [ ] **Step 5: 提交并推送**

Run:

```bash
git add docs/superpowers/specs/2026-05-07-d7pay-obvious-garbage-cleanup-design.md docs/superpowers/plans/2026-05-07-d7pay-obvious-garbage-cleanup.md docs/branches/d7pay.md api/build.md api/err.md apkdownload/build.md apkdownload/err.md ops/tenants/d7pay/current-deployment-ops-runbook.md
git commit -m "cleanup: remove obvious d7pay garbage artifacts"
git push origin d7pay
```

Expected: 推送成功。
