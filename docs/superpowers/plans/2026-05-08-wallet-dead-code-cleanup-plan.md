# 钱包链路死代码清理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理 EasyPaisa / JazzCash 主链路中已经确认无引用的旧 UPI、机器人回调、空壳回队和旧日志代码，降低后续维护误判。

**Architecture:** 本次只处理“引用关系确认后无业务入口”的死代码。仍承担幂等锁、补单、上号会话、通知重试、余额缓存职责的 Redis/fallback 逻辑不在本次强删范围内，后续按单独架构改造处理。

**Tech Stack:** Tornado Handler、aiomysql、Redis 锁/通知、Python worker、GitNexus 索引。

---

## 清理边界

- `/order/successBot` 旧机器人银行回调入口已确认仍需使用，后续恢复，不能作为死代码清理。
- 删除 `Success.check_upi()` / `Success.save_upi_to_history()`，它们只服务已退役的旧 UPI 写入路径。
- 删除 `websocket/callback.py` 中已经退役且只返回 `False` 的代付回队空壳。
- 删除 `success_ds()` 中由 `pakistan_flag = True` 导致永远不可达的旧整数订单匹配分支。
- 修正 `dispatch.py` 中残留的 `push_order_new` 日志文字。
- 收敛 `auto_payout.py` 中已退役的 `members` 参数兼容分支。

## 暂不处理

- Redis 锁、通知 PubSub、`pre_login_*`、`login_on_*`、`login_off_*`：仍是运行期锁/会话/通知信号。
- `bank_record.callback = 0` 和 `/pay/ds/utr`：仍是补单职责边界。
- JazzCash payout `active_list` 命名兼容壳：仍被当前选号流程调用，需单独重命名重构。
- EasyPaisa payout Redis balance/cooldown fallback：属于架构风险，不作为死代码直接删除。

## 验收标准

- `rg "SuccessBot|successBot|check_upi|save_upi_to_history|_requeue_df_if_online|push_order_new|legacy members" api/application api/jobs api/router.py` 不再命中本次清理目标。
- `python3 -m py_compile` 覆盖修改过的 Python 文件并全部通过。
- `git diff --check` 无空白错误。
- GitNexus pre/post commit 索引通过。
- 只提交本次相关文件，不纳入工作区已有未跟踪目录。
