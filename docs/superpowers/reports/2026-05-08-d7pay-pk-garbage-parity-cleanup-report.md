# D7pay pk_project 垃圾清理对齐报告

## 处理内容

- 删除 D7pay 独有旧印度钱包 service、PhonePe 目录、旧 Redis 维护脚本、旧银行 SQL 和 PhonePe 静态图标。
- 参考 `/Users/tear/pk_project` 当前文件，同步收口 Lakshmi API 注册表、App 控制器、代收派单、EasyPaisa/JazzCash worker 和 Admin 收款资料重置逻辑。
- 保留 D7pay 租户配置、品牌资源、Jenkins/K8s 运维合同。

## 业务口径

- 当前 D7pay 只保留 EasyPaisa / JazzCashBusiness 作为码商上号、采集、代收和代付链路。
- 旧 `payment_active_*` 只允许作为历史清理对象，不再作为代收候选真相源。
- 代收候选以 MySQL `collection_status` 为准，代付候选以 `payout_status` 为准，钱包健康以 `wallet_status` 为准。

## 验收记录

- `rg` 运行代码残留扫描：无旧 PhonePe/旧印度钱包 service/旧专用路由引用。
- `git ls-files` 旧文件残留检查：无旧文件被 Git 跟踪。
- `PYTHONPATH=api python3 -m py_compile ...`：通过，仅 `api/router.py` 存在历史 Tornado 路由正则转义 `SyntaxWarning`。
- `PYTHONPATH=api python3 -m unittest ...`：47 个定向测试通过。
- `python3 ops/tenants/d7pay/verify_release_contract.py`：通过。
