# 废除流水直接补单核销实施计划

## 目标

废除流水不再走恢复流程。人工补单接口直接支持 `invalid=1` 的未回调代收流水：废除的直接扣钱/核销，未废除的按原逻辑核销。

## 计划

1. 补充单测锁定人工补单 SQL：
   - 查询条件必须允许 `invalid IN (0,1)`。
   - 消费流水时必须写 `callback=1, invalid=0, order_code`。

2. 调整 Admin 后端：
   - `/partner/delbank_recoed` 继续只废除，不修改 `utr/trans_id`。
   - `/order/handleorder` 人工补单使用统一 SQL helper 查询和消费银行流水。
   - 移除 `/partner/restorebank_recoed` handler 和路由。

3. 调整 Admin H5：
   - 移除恢复 API。
   - 银行流水页仅保留废除按钮；`invalid=1` 不显示恢复入口。
   - 移除恢复语言包文案。

4. 调整 SQL 和文档：
   - 删除新增恢复权限 SQL。
   - 新增禁用历史恢复权限 SQL。
   - 更新 `build.md`、`err.md`、设计文档和计划文档。

5. 验收：
   - Admin py_compile。
   - Admin 相关 unittest。
   - `git diff --check`。
   - Admin H5 `npm run d7pay:prod`。
   - GitNexus 变更范围检测。
   - 提交并推送 `d7pay` 分支。

## 验收标准

- 废除流水不会释放采集幂等键。
- 误废除确认付款后，不需要恢复接口，直接在代收补单核销。
- 补单完成后流水变为 `callback=1, invalid=0`，订单和资金按既有事务成功落库。
- 恢复接口、恢复按钮、恢复权限新增 SQL 不再存在。
