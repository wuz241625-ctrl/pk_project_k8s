# D7pay MySQL Business State Redis Lock Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 D7pay 钱包业务资格只由 MySQL 业务态判断，Redis 只保留锁和辅助缓存职责。

**Architecture:** 保持现有模块边界，不新增服务层。对还在读取或清理旧 Redis 业务投影的入口做 no-op 或 MySQL-only 返回，并用源代码断言测试锁住边界。

**Tech Stack:** Python、Tornado、pytest、GitNexus。

---

### Task 1: 锁住 Redis 不能作为业务判断源

**Files:**
- Modify: `api/tests/test_easypaisa_redis_compat_retirement.py`
- Create: `admin/tests/test_redis_business_state_retirement.py`

- [x] **Step 1: 添加 Lakshmi 代付状态测试**

在 `api/tests/test_easypaisa_redis_compat_retirement.py` 中添加：

```python
def test_lakshmi_place_order_status_does_not_use_legacy_payment_online_df(self):
    source = (
        API_ROOT
        / "application"
        / "lakshmi_api"
        / "services"
        / "payments"
        / "e_wallet_handler.py"
    ).read_text(encoding="utf-8")

    self.assertNotIn("payment_" + "online_df", source)
    self.assertIn("mysql_business_status", source)
```

- [x] **Step 2: 添加 API active channel 退役测试**

在同一文件中添加：

```python
def test_base_clear_active_does_not_clean_legacy_active_channel_projection(self):
    source = (API_ROOT / "application" / "base.py").read_text(encoding="utf-8")

    self.assertNotIn("payment_" + "active_channel_", source)
```

- [x] **Step 3: 添加 Admin 代付回队退役测试**

创建 `admin/tests/test_redis_business_state_retirement.py`：

```python
from pathlib import Path


ADMIN_ROOT = Path(__file__).resolve().parents[1]


def test_admin_order_requeue_does_not_clean_legacy_payment_active_df():
    source = (ADMIN_ROOT / "application" / "order" / "order.py").read_text(encoding="utf-8")

    assert "payment_" + "active_df" not in source
    assert "async def requeue_df_if_online" in source
```

- [x] **Step 4: 运行测试验证失败**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_redis_compat_retirement.py::EasyPaisaRedisCompatRetirementTests::test_lakshmi_place_order_status_does_not_use_legacy_payment_online_df api/tests/test_easypaisa_redis_compat_retirement.py::EasyPaisaRedisCompatRetirementTests::test_base_clear_active_does_not_clean_legacy_active_channel_projection -q
python3 -m pytest admin/tests/test_redis_business_state_retirement.py -q
```

Expected: 旧实现失败，分别命中 `payment_online_df`、`payment_active_channel_`、`payment_active_df`。

### Task 2: 修改业务判断入口

**Files:**
- Modify: `api/application/lakshmi_api/services/payments/e_wallet_handler.py`
- Modify: `api/application/base.py`
- Modify: `admin/application/order/order.py`

- [x] **Step 1: Lakshmi place_order_status 不读 Redis**

把 fallback 改为不可用：

```python
async def place_order_status(self, payment_id):
    if self._use_mysql_final_status():
        status = self._read_mysql_business_status(payment_id)
        return bool(status and status["payout"])
    return False
```

- [x] **Step 2: API clear_active 退役**

把旧 active channel 清理改为 no-op：

```python
async def clear_active(self, partner_id):
    return None
```

- [x] **Step 3: Admin requeue_df_if_online 退役**

不再清理 `payment_active_df`：

```python
async def requeue_df_if_online(handler, payment_id):
    """代付回队已退役，MySQL payout_status 是唯一资格源。"""
    return False
```

- [x] **Step 4: 运行针对性测试验证通过**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_redis_compat_retirement.py::EasyPaisaRedisCompatRetirementTests::test_lakshmi_place_order_status_does_not_use_legacy_payment_online_df api/tests/test_easypaisa_redis_compat_retirement.py::EasyPaisaRedisCompatRetirementTests::test_base_clear_active_does_not_clean_legacy_active_channel_projection -q
python3 -m pytest admin/tests/test_redis_business_state_retirement.py -q
```

Expected: 全部通过。

### Task 3: 回归验收与提交

**Files:**
- Modify: `docs/superpowers/reports/2026-05-08-d7pay-mysql-business-state-redis-lock-boundary-report.md`

- [ ] **Step 1: 运行完整相关测试**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_websocket_monitor_ep_dispatch.py api/tests/test_client_ip.py api/tests/test_timezone_policy.py -q
python3 -m pytest admin/tests/test_redis_business_state_retirement.py admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py -q
python3 -m pytest merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
python3 ops/tenants/d7pay/verify_release_contract.py
```

Expected: 全部通过。

- [ ] **Step 2: GitNexus 变更检查**

Run:

```bash
npx gitnexus analyze
gitnexus detect_changes(scope="all")
```

Expected: 变更只覆盖本次 Redis/MySQL 边界相关文件和文档。

- [ ] **Step 3: 提交并推送**

Run:

```bash
git add api/application/lakshmi_api/services/payments/e_wallet_handler.py api/application/base.py admin/application/order/order.py api/tests/test_easypaisa_redis_compat_retirement.py admin/tests/test_redis_business_state_retirement.py docs/superpowers/specs/2026-05-08-d7pay-mysql-business-state-redis-lock-boundary-design.md docs/superpowers/plans/2026-05-08-d7pay-mysql-business-state-redis-lock-boundary-plan.md docs/superpowers/reports/2026-05-08-d7pay-mysql-business-state-redis-lock-boundary-report.md
git commit -m "fix: keep redis out of d7pay business state"
git push origin d7pay
```
