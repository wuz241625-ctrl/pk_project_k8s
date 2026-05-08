# D7pay 同步 pk_project 最新业务设计

## 目标

将 `/Users/tear/pk_project` 最近业务提交同步到 D7pay 分支，覆盖 Pakistan 钱包 UTR 语义、EasyPaisa 账单幂等、代付 MySQL 连接集中管理、MySQL 余额选号、Redis 业务态退役。

## 同步范围

- API 回调与订单语义：`api/application/pay/order.py`、`api/application/websocket/callback.py`
- EasyPaisa 账单采集：`api/jobs/pakistanpay_v2.py`
- 代付 worker 公共数据库连接：`api/jobs/common/db.py`、`api/jobs/easypaisa/common/db.py`
- EasyPaisa/JazzCash 代付选号、结算、监控和 worker 编排。
- Admin 自动代付开关和商户指定码缓存退役逻辑。
- 同步 pk_project 中对应测试，保留 D7pay 已有 IP、时区、Redis 业务态边界测试。

## 保留边界

- 不同步 D7pay 租户配置、域名、Jenkins、K8s、APK、H5 前端。
- 不改变 D7pay IP 识别和时区展示策略。
- Redis 只能作为锁、临时缓存、幂等、通知、上号会话、余额缓存等辅助设施，不能作为业务状态最终判断源。
- 历史 Redis 残留不在本次清理，后续由独立脚本处理。

## 验收标准

- pk_project 最近提交涉及的业务测试在 D7pay 通过。
- D7pay 的 `test_client_ip.py`、`test_timezone_policy.py` 继续通过。
- `verify_release_contract.py` 继续通过。
- GitNexus 变更检查显示影响面符合本次同步范围。
