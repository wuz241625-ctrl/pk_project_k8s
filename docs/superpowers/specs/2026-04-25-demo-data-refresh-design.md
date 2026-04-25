# 测试环境演示数据整理设计

## 目标

将测试环境从生产级历史数据整理成可演示、可登录、可讲业务流程的数据集，同时保留系统运行需要的基础配置。

## 头脑风暴结论

比较过三种方案：

1. 只删除旧日志和旧订单，保留所有账号。
   - 优点是风险小。
   - 缺点是旧商户、旧管理员、旧收款资料仍然暴露，不适合演示。
2. 全量清空后手写新数据。
   - 优点是最干净。
   - 缺点是容易脱离真实业务，订单、流水、费率、权限展示不自然。
3. 保留基础配置，从旧数据抽样改造成近期脱敏演示数据。
   - 优点是保留真实业务形状，同时去掉敏感账号和历史脏数据。
   - 本次采用该方案。

## 保留范围

- `permissions`：保留完整权限树，后台菜单和按钮权限需要它。
- `roles`：收敛为 5 个演示角色，覆盖超级管理员、商户运营、财务、客服、风控。
- `admin`：收敛为 5 个演示管理员账号，统一密码为 `123456`，统一 Google 密钥用于正常登录流程。
- `sys_info`、`channel`、`bank_type`、`vip`、系统设置类小表：保留，用于服务开关、渠道、费率和基础配置展示。
- `merchant` / `merchant_channel` / `merchant_tree`：从旧商户抽样生成 8 个演示商户，并保留层级和渠道费率关系。
- `partner` / `partner_tree`：生成 4 个演示码商，用于列表和订单归属展示。

## 清理范围

- 订单和流水大表清空后重建小样本：
  - `orders_ds`：320 条
  - `orders_df`：120 条
  - `balance_record`：按成功订单重建余额流水
- 日志、统计和派生表清理后按演示数据重建必要汇总。
- `payment`、`payment_d`、`bank_record`、`payment_upi_history`、`payment_weight` 清空。

## 收款资料边界

不创建、不迁移、不启用任何收款资料。

- `payment` 保持空。
- `payment_d` 保持空。
- `merchant.target_payment` 保持空。
- 订单里的 `payment_id` 保持空。
- Redis 里的在线收款资料、活跃队列、EasyPaisa runtime 状态在执行后清理。

这样演示人员可以看到入口，但收款资料必须由他们自己登录后新增、启用、上线。

## 验收标准

- 执行前存在压缩备份文件。
- `mysql` Service 只指向 `mysql-0`。
- `admin` 表仅保留 5 个演示管理员，`18088880000` 密码为 `123456`。
- `roles` 表仅保留 5 个演示角色，并且权限字段非空。
- `merchant` 表仅保留 8 个演示商户，全部启用，白名单包含 `103.135.100.192`。
- `partner` 表仅保留 4 个演示码商。
- `payment` 和 `payment_d` 均为 0 条。
- `orders_ds` 为 320 条，`orders_df` 为 120 条，且时间均落在最近 10 天。
- `balance_record` 与成功订单对应，商户余额非负。
- `merchant.target_payment` 没有任何非空值。
- admin 正确密码加当前 Google 码可以登录。
- merchant 正确密码加当前 Google 码可以登录。
- 后台/商户主要列表接口返回 `code=20000` 或 HTTP 200。

## 2026-04-25 执行记录

- 备份文件：`/opt/cicd/k8s/backups/pakistan-demo-before-20260425153732.sql.gz`
- `mysql` Service selector：`app=mysql`、`statefulset.kubernetes.io/pod-name=mysql-0`
- `mysql` endpoint：`10.244.1.49:3306`
- `admin` / `api` / `merchant` 均为 `RUN_ENV=PROD`
- admin 白名单：`103.135.100.192` 已写入 `sys_info.sys_ip_w`
- merchant 白名单：8 个演示商户 `ip/ip_df` 均包含 `103.135.100.192`
- api 访问控制：API 代码使用 `sys_info.api_ip_b` 黑名单，不是白名单；验收时 `103.135.100.192` 不在黑名单中

最终 SQL 验收：

```text
admin=5
roles=5
merchant=8
partner=4
payment=0
payment_d=0
orders_ds=320
orders_df=120
balance_record=177
merchant_target_payment_nonempty=0
merchant_negative_balance=0
admin_demo_accounts=5
merchant_demo_accounts=8
sys_info_demo_ip=1
merchant_demo_ip=8
```

真实接口验收：

```text
admin /login/singin -> HTTP 200, code=20000
admin /login/getuserinfo -> HTTP 200, code=20000
admin /merchant/getmerchant -> HTTP 200, code=20000, total=8
admin /order/getorderds -> HTTP 200, code=20000
merchant /login/singin -> HTTP 200, code=20000
merchant /login/getuserinfo -> HTTP 200, code=20000
merchant /merchant/getmerchant -> HTTP 200, code=20000
merchant /order/getorderds -> HTTP 200, code=20000
```
