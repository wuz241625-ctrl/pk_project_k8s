# D7pay 后端业务同步 pk_project 设计

## 目标

将 D7pay 后端的钱包状态实现、代收下单、派单、采集、代付业务逻辑同步到 `/Users/tear/pk_project` 当前实现，同时明确保留 D7pay 自己的 IP 识别、时区展示、env 租户配置和 K8s/Jenkins 发布配置。

## 同步范围

本次只同步后端业务文件：

- 钱包状态和上号状态：
  - `api/application/app/login/banks/easypaisa.py`
  - `api/application/app/login/banks/jazzcash.py`
  - `api/application/websocket/monitor.py`
  - `api/jobs/update_payment_balance.py`
- 代收下单和派单：
  - `api/application/pay/pay.py`
  - `api/application/pay/dispatch.py`
  - `api/application/lakshmi_api/controllers/deposit_orders_controller.py`
  - `api/router.py`
- 采集和回调：
  - `api/application/pay/order.py`
  - `api/application/websocket/callback.py`
  - `api/jobs/Jazzcashpay_v2.py`
- 代付：
  - `api/jobs/easypaisa/auto_payout.py`
  - 已经同步且继续验收的 `api/jobs/easypaisa/payout/*.py`
  - 已经同步且继续验收的 `api/jobs/jazzcash/payout/*.py`
  - 已经同步且继续验收的 `api/jobs/pakistanpay_v2.py`

同步测试和文档：

- `api/tests/test_crawl_frequently_retirement.py`
- `api/tests/test_update_payment_balance_retirement.py`
- `api/tests/test_jazzcash_mysql_statement_scheduler.py`
- pk_project 最近相关 `docs/superpowers/{plans,reports,specs}` 文档。

## 保留边界

以下 D7pay 差异不得被 pk_project 覆盖：

- IP 识别：`api/admin/merchant/application/client_ip.py` 和各后端 `BaseHandler.get_ip()` 中的 `resolve_client_ip` 调用。
- 时区展示：`api/admin/merchant/application/timezone.py` 和 `display_today_between` 调用。
- 配置：`config.example.py` env 化配置、D7pay 域名、数据库、密钥读取约定。
- 部署：`ops/tenants/d7pay/**`、`Makefile`、K8s YAML、Jenkins 脚本、H5、APK 下载资源。

## 业务规则

- 钱包最终资格源继续是 MySQL `payment.wallet_status / collection_status / payout_status`。
- `update_payment_balance.py` 退役，余额/限额由各钱包 monitor 维护。
- 代收自有派单成功后才写 `orders_ds`；三方强制通道才先落单给三方回写。
- 派单在事务内完成扣款和 `orders_ds` 插入，不再依赖先创建再更新的旧流程。
- `crawl_frequently_*` Redis 加速采集信号退役，不再由派单和 Lakshmi 入口写入，不再由 JazzCash 采集读取。
- 采集回调保持 MySQL 幂等，重复流水返回成功接受，不重复推进业务回调。
- 代付状态机继续以已同步的 pk_project 版本为准：明确失败只处理 `402`，未知结果进入人工待确认。

## 验收标准

- 同步范围内业务文件与 `/Users/tear/pk_project` 内容一致。
- IP 和时区文件仍保留 D7pay 实现，`resolve_client_ip` 和 `display_today_between` 测试通过。
- `rg` 检查业务同步后没有 `crawl_frequently_` 残留。
- `update_payment_balance.py` 运行后成功退出并输出退役提示。
- 代收同步测试、派单测试、采集测试、钱包状态测试、代付状态机测试全部通过。
- `python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- GitNexus 变更检测完成，影响面与本次业务同步范围一致。
