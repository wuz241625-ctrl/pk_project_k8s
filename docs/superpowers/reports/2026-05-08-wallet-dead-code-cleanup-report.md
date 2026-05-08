# 钱包链路死代码清理验收报告

## 本次清理内容

- `/order/successBot` 路由和 `SuccessBot` 旧机器人银行回调类后来确认仍需使用，已在 `2026-05-08-successbot-restore-report.md` 中按最小范围恢复。
- 删除 `Success.check_upi()` 与 `Success.save_upi_to_history()`，这两个方法只服务已经退役的旧 UPI 写入路径。
- 删除 `websocket/callback.py` 中已退役的 `_requeue_df_if_online()` 空壳和调用点。
- 删除 `success_ds()` 中由 `pakistan_flag = True` 导致永远不可达的旧整数匹配分支，保留实际运行的 Pakistan `payment_id + utr` 严格匹配链路。
- 修正 JazzCash 代收加速日志中的旧 `push_order_new` 名称。
- 删除 EasyPaisa 代付 `process_members_concurrent()` 中已退役的 `members` 参数兼容分支。

## 明确未清理内容

- Redis 锁、通知 PubSub、上号会话信号仍保留，它们是运行期职责，不是死代码。
- `/pay/ds/utr` 和 `bank_record.callback = 0` 仍保留，它们是补单边界。
- JazzCash 代付 `active_list` 命名兼容壳仍保留，因为当前选号流程仍有调用，需要单独做重命名重构。
- EasyPaisa 代付 Redis balance/cooldown fallback 仍保留，因为它属于架构风险改造，不是简单删除项。

## 验收命令

```bash
rg -n "class SuccessBot|/order/successBot|def check_upi|def save_upi_to_history|_requeue_df_if_online|pakistan_flag|push_order_new|legacy members|members=None" api/application api/jobs/easypaisa api/router.py -S
python3 -m py_compile api/router.py api/application/pay/order.py api/application/websocket/callback.py api/application/pay/dispatch.py api/jobs/easypaisa/auto_payout.py
git diff --check
npx gitnexus analyze --skip-agents-md --worker-timeout 120 --max-file-size 32768
```

## 验收结论

本次清理只移除已经确认无主链路入口或不可达的旧代码，不改变 EasyPaisa / JazzCash 的派单、采集、代付、通知最终态职责。

- 残留搜索：无命中。
- Python 编译：通过；`api/router.py` 仍有历史正则转义 `SyntaxWarning`，不是本次新增。
- 空白检查：通过。
- GitNexus 索引：通过。
