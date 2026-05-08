# D7pay 同步 pk_project 钱包手机号与代付并发设计

## 目标

将 `/Users/tear/pk_project` 最新 4 个业务提交同步到 D7pay，保持 D7pay 租户配置、域名、Jenkins/K8s、IP 识别和时区展示不变。

## 同步范围

- EasyPaisa 代收通道拆分：`1001` 为账号/钱包展示通道，钱包户展示 `phone`，银行户展示 `account_accno`；`1010` 为二维码通道，使用二维码载荷。
- 代收派单候选 SQL：`1001` 允许 EasyPaisa 钱包手机号和银行账号，`1010` 继续要求 QR 所需字段；JazzCash 逻辑不改成 QR。
- 收银台付款标识：Pakistan 钱包手机号归一化后写入 `orders_ds.utr`，并在同账号、同金额、短时间窗口内阻止重复提交。
- 账单扫描：EasyPaisa/JazzCash 只扫描已有付款手机号的代收订单，避免未提交 payer phone 的订单进入账单核对。
- EasyPaisa 代付并发加固：Redis 锁使用原子 `set nx ex` 与 Lua compare-delete，代付按并发限制处理，超时执行中订单转人工确认。
- EasyPaisa 代付成功判定：官方 `code=200` 但 `orderStatus` 未明确为 `S` 时不按成功结算。

## 保留边界

- 不同步 pk_project 的真实环境配置、README 租户描述、根级 `build.md`/`err.md`。
- 不修改 D7pay 的 `config.example.py`、K8s、Jenkins、APK、H5 和 tenant ops 目录。
- Redis 继续只作为锁、缓存、session、通知；业务态判断以 MySQL 为准。

## 验收标准

- 新同步测试先在旧实现上失败，再在同步后通过。
- 业务测试、D7pay IP/时区边界测试、D7pay release contract 全部通过。
- 静态扫描不出现旧 Redis 业务态关键字和错误时区关键字。
- GitNexus 重新索引并完成 staged 变更检测。
