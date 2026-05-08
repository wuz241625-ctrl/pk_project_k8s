# 2026-05-08 代收派单 NOWAIT 事务抢占设计

## 背景

代收派单已经改为手写 MySQL 候选 SQL：先从 `payment`、`partner`、`vip` 查出最多 20 个候选码，再由 `push_order()` 做冷却、风控、限额、费率和最终接单。

当前最终接单事务只做两件事：

1. 调用 `change_balance()` 扣减 `partner.balance`。
2. `UPDATE orders_ds ... WHERE code=%s AND status=0` 把订单从待派单改成已接单。

这可以避免同一个订单重复更新，但多 worker 同时命中同一码商或同一码时，会进入普通 InnoDB 行锁等待。热点钱包会拖慢连接，不能快速换下一个候选。

## 目标

- 候选 SQL 继续保持只读、手写、`LIMIT 20`。
- 最终抢占阶段使用 MySQL 事务管理资源占用。
- 在同一个事务内用 `FOR UPDATE NOWAIT` 锁住 `partner` 和 `payment`。
- 锁不到立即回滚并换下一个候选，不等待热点锁。
- 锁成功后必须重新校验余额、状态、人工锁、日限额和订单状态。
- 不新增表，不引入 Redis Stream，不改变订单创建时机。

## 设计

候选阶段不加锁：

```sql
SELECT ...
FROM payment pay
JOIN partner p ON pay.partner_id = p.id
JOIN vip v ON v.vip = p.vip
WHERE ...
ORDER BY COALESCE(pay.weight, 1) DESC, p.balance DESC, pay.id ASC
LIMIT 20;
```

最终抢占阶段对每个候选单独开启事务：

```sql
SELECT id, balance, status, certified, vip, type, ds_min, ds_max
FROM partner
WHERE id = %s
FOR UPDATE NOWAIT;

SELECT id, partner_id, amount_top, manual_status, collection_status, status, certified
FROM payment
WHERE id = %s
FOR UPDATE NOWAIT;
```

锁顺序固定为 `partner -> payment`，避免不同代码路径以不同顺序拿锁导致死锁。

锁成功后在事务内重新判断：

1. `partner.status = 1`。
2. `partner.certified = 1`。
3. `partner.balance` 扣除保证金后仍大于等于订单金额。
4. `payment.partner_id` 仍等于当前 `partner_id`。
5. `payment.collection_status = 1`。
6. `payment.manual_status != 1`。
7. `payment.amount_top` 今日额度仍然足够。
8. 外部码商的未回调扣款流水仍不超过可接额度。
9. `orders_ds.code` 当前仍是 `status=0`。

任一判断失败都回滚并继续尝试候选池里的下一个码。

## 错误处理

MySQL 8 `NOWAIT` 获取不到锁时通常返回 `3572`。老版本或不同驱动可能表现为锁等待类 `1205`。代码统一识别这两类错误：

- `3572`：NOWAIT 无法立即获取锁。
- `1205`：锁等待超时，作为兼容兜底处理。

识别为锁冲突时只记录 warning，回滚后换候选，不把整个订单直接判为派单失败。

## 不做的事

- 不在候选 SQL 上加 `FOR UPDATE NOWAIT`，避免一次锁住 20 个候选。
- 不新增 pending 聚合表，因为当前 `partner.balance` 已经在接单成功时扣减占用。
- 不改 `orders_ds` 创建逻辑。
- 不改采集加速和超时退款逻辑。
- 不把 Redis 重新作为业务最终态。

## 验收标准

- `build_ds_candidate_sql()` 不包含 `FOR UPDATE` 或 `NOWAIT`。
- 事务抢占代码包含 `partner FOR UPDATE NOWAIT` 和 `payment FOR UPDATE NOWAIT`。
- 锁顺序固定为 `partner -> payment`。
- 能识别 MySQL `3572` 和 `1205` 为锁冲突。
- 锁冲突时会回滚并继续尝试下一个候选。
- 锁成功后会在事务内重新校验余额、状态、人工锁和 `amount_top`。
- `change_balance()` 只在锁成功和复核通过后调用。
- `orders_ds` 仍通过 `WHERE code=%s AND status=0` 做订单幂等推进。
- 相关 pytest、py_compile、git diff check 通过。
