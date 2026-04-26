# 演示数据整理脚本排错

## 1. `ModuleNotFoundError: No module named 'pymysql'`

现象：

- 本地直接执行 `prepare_demo_data.py` 报缺少 `pymysql`

原因：

- 写库脚本依赖线上 admin 镜像中的 Python 依赖。
- 本地只要求跑 helper 单测和语法检查。

处理：

```bash
python3 -m unittest ops/demo_data/test_prepare_demo_data.py -v
python3 -m py_compile ops/demo_data/prepare_demo_data.py
```

真正 dry-run 或执行时，把脚本放到 admin Pod 里跑。

## 2. 执行脚本但没有写入数据

现象：

- 输出 `dry_run=1`

原因：

- 脚本默认只读。

处理：

写库必须显式传两个参数：

```bash
python /tmp/prepare_demo_data.py --apply --i-understand-this-rewrites-test-data
```

## 3. 演示登录返回 IP 禁止登录

原因：

- admin 依赖 `sys_info.sys_ip_w`
- merchant 依赖 `merchant.ip`

处理：

脚本会确保 `103.135.100.192` 在 admin 白名单和演示商户白名单中。若手工变更过 IP，重新执行脚本或手工补充白名单。

## 4. 收款资料不是在线卡池

这是预期行为。

演示订单需要 `payment_id` 才能符合真实代收/代付闭环，所以脚本会保留旧库抽样出来的历史收款资料；但这些资料必须全部禁用，不能进入在线派单卡池：

- `payment` 大于 0，用于历史订单展示和 payment 引用闭环
- `payment.status=0`
- `payment.manual_status=1`
- `payment_active_count=0`
- `payment_d` 为 0 条
- Redis 在线收款资料状态会被清理

需要演示“新增/上线收款资料”时，由演示人员自己登录码商账号后新增和上线。

## 5. 恢复备份卡在 `Waiting for table metadata lock`

现象：

- `mysql` 进程显示 `DROP TABLE ... Waiting for table metadata lock`
- 恢复管道长时间没有输出

原因：

- admin、api、merchant 的旧连接仍持有库表元数据锁。

处理：

1. 临时把 `admin-deploy`、`api-deploy`、`merchant-deploy` 缩到 0。
2. kill 掉 `information_schema.PROCESSLIST` 中旧的 `pakistan` 业务连接。
3. 等恢复完成后再恢复到原副本数。

## 6. `merchant.time_create` 唯一键冲突

现象：

```text
Duplicate entry '<datetime>' for key 'merchant.time_create'
```

原因：

- `merchant.time_create` 在线上表结构中有唯一约束。
- 批量造商户时如果使用同一个时间，会触发唯一键冲突。

处理：

- 每个演示商户的 `time_create` / `time_update` 使用同一个基准时间加不同秒数。

## 7. 演示商户余额为负

现象：

```sql
SELECT COUNT(*) FROM merchant WHERE balance < 0 OR balance_frozen < 0;
```

结果大于 0。

原因：

- 演示订单从旧订单抽样，部分商户成功代付金额大于代收入账。
- 固定开账余额不足时，按流水重放后会出现负余额。

处理：

- 脚本按每个商户的成功订单净额动态计算开账余额。
- `validate()` 增加 `merchant_negative_balance=0` 的硬校验，不满足就回滚并报错。

## 8. PyMySQL 报 `not enough arguments for format string`

现象：

```text
TypeError: not enough arguments for format string
```

原因：

- SQL 字符串中直接写 `LIKE '%103.135.100.192%'`，PyMySQL 会把 `%` 当成格式占位符。

处理：

- 在脚本内写成 `LIKE '%%103.135.100.192%%'`，或改为参数化查询。

## 9. 演示订单出现 `DSDEMO` / `DFDEMO` / `Demo Bank`

现象：

- 订单号、收款字段、付款人字段都是 `Demo...`
- `orders_ds.payment_id` 或 `orders_df.payment_id` 为空
- 管理后台看起来像随便造的数据

原因：

- 旧脚本虽然先抽旧库 seed，但随后硬覆盖为 Demo 模板字段。
- 验收只检查数量和余额非负，没有检查 `pay.py` 的真实订单闭环。

处理：

- 执行脚本时必须传 `--source-database=pakistan_backup_inspect_20260425`。
- 脚本从旧库抽真实 admin、role、merchant、partner、payment、orders_ds、orders_df。
- 历史 payment 禁用，订单保留 payment 引用。
- 验收必须确认以下结果为 0：

```sql
SELECT COUNT(*) FROM orders_ds WHERE code LIKE 'DSDEMO%' OR upi='demo@upi' OR realname='Demo Player';
SELECT COUNT(*) FROM orders_df WHERE code LIKE 'DFDEMO%' OR payment_bank='Demo Bank' OR payment_name LIKE 'Demo Receiver%';
SELECT COUNT(*) FROM orders_ds o LEFT JOIN payment p ON p.id=o.payment_id WHERE o.status IN (-1,3,4) AND (o.payment_id IS NULL OR p.id IS NULL);
SELECT COUNT(*) FROM orders_df o LEFT JOIN payment p ON p.id=o.payment_id WHERE o.status IN (-1,-2,3,4) AND (o.payment_id IS NULL OR p.id IS NULL);
```

## 10. 余额与最后一条流水不一致

现象：

```sql
merchant_balance_record_last_mismatch > 0
partner_balance_record_last_mismatch > 0
```

原因：

- 只抽了一段旧订单，没有导入旧库完整 `balance_record`。
- 如果只设置开账余额但不写开账流水，没有订单事件的账号会缺少最后一条流水。

处理：

- 脚本为每个演示商户、码商写入 `DEMOOPENM*` / `DEMOOPENP*` 开账流水。
- 然后按真实业务事件重放：
  - 代收接单：码商扣本金
  - 代收成功：商户入账、码商佣金、payment 系统余额增加
  - 代收失败：码商本金退回
  - 代付创建：商户扣款
  - 代付成功：码商入本金和佣金、payment 系统余额减少
  - 代付失败：商户退款

## 11. 后台看到旧商户密钥或多个商户共用同一密钥

现象：

- 后台商户管理打开商户编辑时能看到旧库带来的 `mc_key` / `gg_key`
- 多个演示商户显示同一 Google 密钥或固定商户密钥

原因：

- 商户管理接口会返回 `merchant.mc_key` 和 `merchant.gg_key`。
- 如果演示数据脚本保留旧库字段，或使用固定演示密钥，后台展示就会泄露旧商户数据或显得不真实。

处理：

- 演示脚本必须为每个商户重新生成随机 `mc_key` 和随机 `gg_key`。
- 当前测试库若已存在旧演示商户，直接批量更新 `merchant.mc_key` / `merchant.gg_key`，不要修改登录密码和订单数据。
- 验收必须确认以下结果都为 0：

```sql
SELECT COUNT(*) FROM merchant WHERE mc_key IS NULL OR CHAR_LENGTH(mc_key) != 32 OR mc_key REGEXP '[^0-9a-f]';
SELECT COUNT(*) FROM merchant WHERE gg_key IS NULL OR CHAR_LENGTH(gg_key) != 16 OR gg_key REGEXP '[^A-Z2-7]';
SELECT COUNT(*) - COUNT(DISTINCT mc_key) FROM merchant;
SELECT COUNT(*) - COUNT(DISTINCT gg_key) FROM merchant;
```
