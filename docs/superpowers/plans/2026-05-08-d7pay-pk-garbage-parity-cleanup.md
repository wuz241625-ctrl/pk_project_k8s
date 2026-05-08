# D7pay pk_project 垃圾清理对齐实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 参考 `/Users/tear/pk_project` 当前文件清理 D7pay 分支的旧印度钱包、PhonePe 和旧 Redis 残留。

**Architecture:** 以 pk_project 当前业务文件为参考源，同步删除 D7pay 独有旧文件，并收口服务注册、路由、worker 和 Admin 重置逻辑。D7pay 租户配置、Jenkins/K8s 发布合同和品牌资源不参与覆盖。

**Tech Stack:** Python/Tornado、aiomysql、Redis、MySQL、K8s/Jenkins。

---

### Task 1: 删除旧文件

**Files:**
- Delete: `api/application/lakshmi_api/services/payments/*_service.py` 中旧印度钱包 service
- Delete: `api/application/phonepe/`
- Delete: `api/jobs/check_proxy.py`
- Delete: `api/jobs/clear_redis_dsdf.py`
- Delete: `api/jobs/clear_redis_inactive_payment.py`
- Delete: `api/jobs/collect_partner_status.py`
- Delete: `api/jobs/order_push.py`
- Delete: `api/jobs/weight.py`
- Delete: `api/sql/20241125-添加indus银行.sql`
- Delete: `api/sql/20241216-add-bank-ulcash.sql`
- Delete: `api/sql/20241223-添加银行jio.sql`
- Delete: `api/sql/20250206-添加银行maha.sql`
- Delete: `api/static/images/india_transaction/PhonePe.svg`

- [x] **Step 1:** 用 `git rm` 删除旧文件。
- [x] **Step 2:** 运行 `git status --short` 确认删除进入暂存状态。

### Task 2: 同步引用文件

**Files:**
- Modify: `api/main.py`
- Modify: `api/router.py`
- Modify: `api/router_lakshmi.py`
- Modify: `api/application/app/my/my.py`
- Modify: `api/application/lakshmi_api/controllers/payment_controller.py`
- Modify: `api/application/lakshmi_api/controllers/upi_controller.py`
- Modify: `api/application/lakshmi_api/controllers/deposit_orders_controller.py`
- Modify: `api/application/lakshmi_api/schema/bank_schema.py`
- Modify: `api/application/lakshmi_api/services/payment_services.py`
- Modify: `api/application/lakshmi_api/services/websockets/payment_service.py`
- Modify: `api/application/pay/pay.py`
- Modify: `api/application/pay/order.py`
- Modify: `api/jobs/Jazzcashpay_v2.py`
- Modify: `api/jobs/pakistanpay_v2.py`
- Modify: EasyPaisa/JazzCash worker 文件
- Modify: `admin/application/partner/partner.py`

- [x] **Step 1:** 参考 `/Users/tear/pk_project` 当前文件同步业务清理后的实现。
- [x] **Step 2:** 保留 D7pay 专属 `config.example.py`、`client_ip.py`、`timezone.py` 和 Jenkins/K8s 文件。
- [x] **Step 3:** 手工移除 D7pay 路由里的 PhonePe、Indus/Amazon 专用入口。

### Task 3: 更新文档

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `docs/branches/d7pay.md`
- Create: `docs/superpowers/specs/2026-05-08-d7pay-pk-garbage-parity-cleanup-design.md`
- Create: `docs/superpowers/reports/2026-05-08-d7pay-pk-garbage-parity-cleanup-report.md`

- [x] **Step 1:** 写明旧模块不能回流。
- [x] **Step 2:** 修正旧文档里“PhonePe 暂不能清理”的历史口径。

### Task 4: 验收

- [x] **Step 1:** 运行旧引用残留扫描。
- [x] **Step 2:** 运行 API 核心 `py_compile`。
- [x] **Step 3:** 运行 EasyPaisa/JazzCash 定向测试。
- [ ] **Step 4:** 提交并推送 `d7pay` 分支。
