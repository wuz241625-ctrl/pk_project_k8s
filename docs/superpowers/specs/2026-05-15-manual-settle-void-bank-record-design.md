# 废除流水直接补单核销设计

## 背景

银行流水“废除”用于把一条未回调流水从自动候选里移开，但废除不能释放官方交易号幂等键。误废除后，如果先恢复再补单，会多出一条运营动作和一个后台权限入口；更直接的闭环是补单接口自己支持废除流水。

## 设计

- 废除接口 `/partner/delbank_recoed` 只更新 `invalid=1` 和备注，保留原始 `utr/trans_id`。
- 不提供 `/partner/restorebank_recoed` 恢复接口，也不在后台页面展示恢复按钮。
- 代收普通补单 `/order/handleorder` 前端只提交 `code + trans_id`，后端用 `trans_id + 订单金额` 查询银行流水，并允许 `invalid IN (0,1)`：
  - 未废除流水：按现有方式核销。
  - 已废除流水：仍可被人工补单选中，补单成功后直接扣钱/核销。
- 三方补单 `/order/handleOrderFromThird` 暂不调整，继续使用现有 `utr`/付款手机号口径做三方查询。
- 补单消费流水时写回 `callback=1, invalid=0, order_code=订单号`，避免废除状态继续干扰后续排查。
- 补单成功写订单时，`orders_ds.utr` 和 `orders_ds.trans_id` 均来自选中的 `bank_record`，不再信任前端传入的 UTR。
- 资金事务沿用现有补单逻辑：需要扣码商时扣码商余额，商户加款，订单置成功，写日志并通知商户。
- 历史环境若已经写入恢复权限，发布前执行 `api/sql/20260515_disable_bank_record_restore_permission.sql` 禁用残留权限。

## 验收标准

1. 废除流水保留原始 `utr/trans_id`，不释放采集幂等键。
2. 人工补单 SQL 明确使用 `trans_id=%s AND amount=%s` 匹配流水，允许 `invalid IN (0,1)`，且只选 `callback=0`、`trade_type=1` 的流水。
3. 人工补单消费流水时写 `callback=1, invalid=0, order_code`。
4. Admin H5 普通补单只传 `code + trans_id`；三方补单仍只传 `code + utr`，不做行为变更。
5. `/partner/restorebank_recoed` 路由、前端 API、页面按钮、语言包文案全部移除。
6. 文档明确“误废除确认付款后直接到代收补单核销，不新增流水，不恢复流水”。
7. Admin 单测、语法检查、Admin H5 D7pay 构建通过。
