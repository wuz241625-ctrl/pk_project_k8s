# SuccessBot 恢复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复仍需使用的 `/order/successBot` 机器人银行账单回调入口。

**Architecture:** 最小恢复公开路由和 `SuccessBot` 处理类，保持旧机器人回调继续复用 `callback.success_df()` 完成代付确认。不恢复已退役的 EasyPaisa/JazzCash UPI 写入 helper，避免把旧钱包写码逻辑重新带回主链路。

**Tech Stack:** Tornado route、`BaseHandler`、`callback.success_df()`、`bank_record` 幂等记录。

---

## 执行步骤

- [x] 从上一版提交读取被删除的 `SuccessBot` 实现。
- [x] 恢复 `/order/successBot` 路由。
- [x] 恢复 `SuccessBot` 类和 AU C / NAGERCOIL ENBL 账单解析逻辑。
- [x] 保留 `bank_record` 重复流水检查和 `callback.success_df()` 调用。
- [x] 不恢复 `check_upi()` / `save_upi_to_history()`。
- [x] 更新死代码清理报告，标记 `SuccessBot` 已恢复且不能作为死代码删除。
- [x] 执行编译、引用和 GitNexus 验收。
- [ ] 提交并推送 `main`。

## 验收标准

- `api/router.py` 重新包含 `/order/successBot`。
- `api/application/pay/order.py` 重新包含 `class SuccessBot`。
- `api/application/pay/order.py` 不包含 `def check_upi` 和 `def save_upi_to_history`。
- `python3 -m py_compile api/router.py api/application/pay/order.py` 通过。
- `git diff --check` 通过。
- GitNexus 索引通过。
