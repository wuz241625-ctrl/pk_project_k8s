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

## 4. 收款资料页面为空

这是预期行为。

本次整理明确不造、不启用、不挂任何收款资料：

- `payment` 为 0 条
- `payment_d` 为 0 条
- Redis 在线收款资料状态会被清理

需要演示收款资料时，由演示人员自己登录账号后新增和上线。

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
