# 测试环境演示数据整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将测试环境整理成安全、脱敏、可演示的数据集。

**Architecture:** 使用一个可审计 Python 脚本连接 MySQL，先读取旧商户和订单作为样本，再清理敏感/大体量表并重建小规模演示数据。执行前做压缩备份，执行后清理 Redis 运行态缓存并用 SQL/API 验收。

**Tech Stack:** Python 3、PyMySQL、bcrypt、MySQL 8、Kubernetes、Redis。

---

### Task 1: 编写脚本测试

**Files:**
- Create: `ops/demo_data/test_prepare_demo_data.py`

- [x] **Step 1: 写 helper 测试**

覆盖权限祖先补全、订单时间推导、金额规整、稳定 SQL 生成。

- [x] **Step 2: 确认测试先失败**

Run: `python3 -m unittest ops/demo_data/test_prepare_demo_data.py -v`

Expected: `ModuleNotFoundError: No module named 'prepare_demo_data'`

### Task 2: 实现演示数据脚本

**Files:**
- Create: `ops/demo_data/prepare_demo_data.py`

- [x] **Step 1: 实现只读 dry-run**

脚本默认只读取当前数据规模，不写库。

- [x] **Step 2: 实现 apply 模式**

必须同时传：

```bash
--apply --i-understand-this-rewrites-test-data
```

才会执行写入。

- [x] **Step 3: 验证 helper 测试通过**

Run:

```bash
python3 -m unittest ops/demo_data/test_prepare_demo_data.py -v
python3 -m py_compile ops/demo_data/prepare_demo_data.py
```

Expected: `OK`

### Task 3: 线上 dry-run

- [x] **Step 1: 复制脚本到 admin Pod**

通过 `kubectl exec -i` 写入 `/tmp/prepare_demo_data.py`。

- [x] **Step 2: 执行 dry-run**

Run:

```bash
python /tmp/prepare_demo_data.py
```

Expected: 输出当前 `admin_count`、`merchant_count`、`payment_count`、`orders_ds_count` 等，不写库。

### Task 4: 备份并执行

- [x] **Step 1: 备份测试库**

Run:

```bash
mysqldump --single-transaction --quick pakistan | gzip > /opt/cicd/k8s/backups/pakistan-demo-before-<timestamp>.sql.gz
```

实际备份文件：

```text
/opt/cicd/k8s/backups/pakistan-demo-before-20260425153732.sql.gz
```

- [x] **Step 2: 执行脚本**

Run:

```bash
python /tmp/prepare_demo_data.py --apply --i-understand-this-rewrites-test-data
```

执行结果：

```text
after={'admin_count': 5, 'demo_role_count': 5, 'merchant_count': 8, 'partner_count': 4, 'payment_count': 0, 'payment_d_count': 0, 'orders_ds_count': 320, 'orders_df_count': 120, 'balance_record_count': 177, 'merchant_with_target_payment': 0, 'merchant_negative_balance': 0, 'sys_info_demo_ip_count': 1, 'merchant_demo_ip_count': 8}
```

- [x] **Step 3: 清理 Redis 运行态**

清理 `payment_*`、`easypaisa_runtime:*`、`cache_info_*`、`target_payment_key` 等缓存。

### Task 5: 验收

- [x] **Step 1: SQL 验收**

确认管理员、角色、商户、码商、订单、流水、收款资料数量符合设计。

验收结果：

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

- [x] **Step 2: 登录验收**

用当前 TOTP 验证 admin 和 merchant 登录成功。

验收账号：

```text
admin: 18088880000 / 123456
merchant: 1888801001 / 123456
```

- [x] **Step 3: 接口验收**

验证后台/商户核心列表接口可返回 HTTP 200 或业务 `code=20000`。

HTTP 验收：

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

### Task 6: 文档与提交

- [x] **Step 1: 更新文档**

同步 `ops/demo_data/build.md`、`ops/demo_data/err.md`。

- [x] **Step 2: 提交并推送**

Run:

```bash
git add docs/superpowers/specs/2026-04-25-demo-data-refresh-design.md docs/superpowers/plans/2026-04-25-demo-data-refresh.md ops/demo_data
git commit -m "chore: 添加测试环境演示数据整理脚本"
git push
```
