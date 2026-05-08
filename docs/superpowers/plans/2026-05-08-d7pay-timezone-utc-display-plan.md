# D7pay UTC Display Timezone Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 D7pay 业务存储继续保持 UTC，同时把用户默认查询日界和上游展示时间统一到巴基斯坦时间。

**Architecture:** 在三个后端入口复用同名 `application.timezone` 工具函数，默认“今天”先按 `Asia/Karachi` 计算自然日，再转回 UTC naive datetime 进入 SQL 查询。硬编码上海时区的上游签名参数统一改为 `display_now()`。

**Tech Stack:** Python 3.12、Tornado、pytz、unittest、GitNexus。

---

### Task 1: 增加展示日界转换测试

**Files:**
- Modify: `api/tests/test_timezone_policy.py`
- Modify: `admin/tests/test_timezone_policy.py`
- Modify: `merchant/tests/test_timezone_policy.py`
- Modify: `admin/tests/test_order_ds_default_filter.py`

- [x] **Step 1: 写失败测试**

覆盖 `display_today_between()` 和无 `Asia/Shanghai` 残留。

- [x] **Step 2: 运行测试确认失败**

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_timezone_policy
PYTHONPATH=admin python3 -m unittest admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter
PYTHONPATH=merchant python3 -m unittest merchant.tests.test_timezone_policy
```

初始结果：`display_today_between` 不存在，且扫描到 `Asia/Shanghai`。

### Task 2: 实现应用层时区工具

**Files:**
- Modify: `api/application/timezone.py`
- Modify: `admin/application/timezone.py`
- Modify: `merchant/application/timezone.py`

- [x] **Step 1: 增加 `display_today_between()`**

按展示时区自然日计算开始/结束，再转 UTC naive datetime。

- [x] **Step 2: 将 `business_now_utc()` 改为显式 UTC**

使用 `datetime.now(timezone.utc).replace(tzinfo=None)`，避免依赖宿主时区。

### Task 3: 替换用户可见默认查询日界

**Files:**
- Modify: `admin/application/order/order.py`
- Modify: `admin/application/merchant/merchant.py`
- Modify: `admin/application/partner/partner.py`
- Modify: `admin/application/record/record.py`
- Modify: `admin/application/recharge/recharge.py`
- Modify: `admin/application/usdtRecharge/usdtRecharge.py`
- Modify: `admin/application/order/pub_acc_withdrawal.py`
- Modify: `merchant/application/count/count.py`
- Modify: `merchant/application/order/order.py`
- Modify: `api/application/app/home/home.py`
- Modify: `api/application/app/agent/agent.py`

- [x] **Step 1: 默认“今天”改为 `display_today_between()`**

这些查询由用户界面触发，默认日界按巴基斯坦自然日展示语义处理。

### Task 4: 清理硬编码上海时区

**Files:**
- Modify: `api/application/pay/thirdCallback.py`
- Modify: `api/application/third/third_df.py`
- Modify: `admin/application/order/query_third_order_status.py`

- [x] **Step 1: 上游签名时间改为 `display_now()`**

这些参数是发给上游/三方的展示时间，不应使用 `Asia/Shanghai`。

### Task 5: 验收

- [x] **Step 1: 编译改动文件**
- [x] **Step 2: 运行时区与订单默认筛选测试**
- [x] **Step 3: 扫描 `Asia/Shanghai` 和 `datetime.today().date()`**
- [x] **Step 4: 更新文档并提交推送**

