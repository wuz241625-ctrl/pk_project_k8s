# D7pay 同步 pk_project EasyPaisa Worker 扩容加固设计

## 目标

同步 `/Users/tear/pk_project` 最新 EasyPaisa 代付 worker 扩容安全改动到 D7pay，提升多 worker 并发时的余额、日限额和官方交易号一致性。

## 同步范围

- `AccountSelector` 从 MySQL 读取候选账号时带出今日已代付金额，并计算 `daily_remaining`。
- 代付派单按 `daily_remaining` 判断日限额，不再只看完整 `amount_top`。
- 在账号锁内复查 `payment.balance`，避免多个 worker 使用预选时的旧余额。
- 成功结算时把 `payment.balance` 扣减放进订单结算同一事务，余额不足或扣减失败时转人工确认。
- EasyPaisa 官方返回成功状态 `S` 但缺少官方交易号时，不再生成本地假 UTR，而是转失败/人工确认路径。

## 保留边界

- 不同步 pk_project 的 README、根级 `build.md`、`err.md` 和环境配置。
- 不修改 D7pay tenant ops、Jenkins、K8s、APK、H5。
- Redis 继续只作为锁/缓存/session/通知，不作为业务状态判断源。

## 验收标准

- 新测试在旧实现上失败，证明覆盖真实缺口。
- 同步实现后 EasyPaisa 代付测试全部通过。
- 业务回归、D7pay IP/时区边界、release contract 全部通过。
- GitNexus 完成索引和 staged 变更检测。
