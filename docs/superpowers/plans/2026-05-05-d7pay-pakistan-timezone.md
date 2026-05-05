# D7pay UTC Storage And Pakistan Display Timezone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 D7pay 生产实例的业务存储保持 UTC，并在应用层统一转换为巴基斯坦展示时间。

**Architecture:** D7pay runtime ConfigMap 只声明 `BUSINESS_TIMEZONE=UTC` 和 `APP_DISPLAY_TIMEZONE=Asia/Karachi`，不修改 MySQL/Redis/Pod 系统时区。API/admin/merchant 提供应用层时区工具，写库和运行计算保持 UTC，展示、报表和上游接口参数转换为巴基斯坦时间。

**Tech Stack:** Kubernetes YAML、Bash 运维脚本、Python Tornado 服务、unittest 合同测试。

---

### Task 1: 合同测试

**Files:**
- Modify: `ops/tenants/d7pay/tests/test_config_only_release.py`
- Modify: `ops/tenants/d7pay/verify_release_contract.py`
- Create: `api/tests/test_timezone_policy.py`
- Create: `admin/tests/test_timezone_policy.py`
- Create: `merchant/tests/test_timezone_policy.py`

- [x] 增加 D7pay runtime ConfigMap 静态合同断言：业务 UTC、展示 `Asia/Karachi`。
- [x] 增加断言：不得存在 MySQL/Redis/Pod 系统时区 patch。
- [x] 增加应用层时区转换测试，并先运行确认缺少模块时失败。

### Task 2: K8s 与配置合同

**Files:**
- Modify: `ops/tenants/d7pay/k8s/runtime-configmap.yaml`
- Modify: `ops/tenants/d7pay/tenant.yaml`
- Modify: `api/docker/db/create_database.sql`
- Modify: `api/docker/app/Dockerfile`
- Modify: `api/docker-compose.yml`

- [x] runtime ConfigMap 增加 `BUSINESS_TIMEZONE=UTC` 和 `APP_DISPLAY_TIMEZONE=Asia/Karachi`。
- [x] tenant 合同声明业务 UTC、展示巴基斯坦时区。
- [x] 本地 Docker 示例改成 UTC。
- [x] 撤回 MySQL/Redis/H5/apkdownload 时区 patch。

### Task 3: 业务代码时间来源

**Files:**
- Modify: `api/config.example.py`
- Modify: `admin/config.example.py`
- Modify: `merchant/config.example.py`
- Create: `api/application/timezone.py`
- Create: `admin/application/timezone.py`
- Create: `merchant/application/timezone.py`
- Modify: `api/application/pay/thirdCallback.py`
- Modify: `api/application/third/third_df.py`
- Modify: `admin/application/order/query_third_order_status.py`

- [x] 配置样例增加 `business_timezone` 和 `display_timezone`。
- [x] 第三方查询时间使用 `format_for_display()`。
- [x] 移除 D7pay 相关业务代码里的 `Asia/Shanghai` 硬编码。

### Task 4: 文档与验收

**Files:**
- Modify: `ops/tenants/d7pay/README_OPERATIONS.md`
- Modify: `ops/tenants/d7pay/acceptance.md`
- Modify: `ops/tenants/d7pay/err.md`
- Modify: `err.md`

- [x] 文档写清 D7pay 时区标准、`d7pay.env` 入口和线上验证命令。
- [x] 运行 preflight、合同测试、应用层时区测试、静态搜索和 git diff 检查。
- [ ] 验收通过后提交并推送 `d7pay` 分支。
