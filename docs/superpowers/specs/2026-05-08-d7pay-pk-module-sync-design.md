# D7pay PK Module Sync Design

## 背景

D7pay 当前已经同步了部分 `pk_project` 业务行为和垃圾代码清理，但核心 API 与 worker 结构仍保留大文件形态。`pk_project` 最新稳定代码已将代收派单、代付、UTR 回调、Raast QR、EasyPaisa 代付、JazzCash 代付拆成更清晰的模块，并移除一批旧 HTTP 兼容层。

## 目标

将 `pk_project` 中已纳管的业务拆分代码同步到 D7pay 分支，降低大文件维护成本，同时保持 D7pay 租户配置、域名、Jenkins、K8s、APK 下载站和 D7pay 文档不被覆盖。

## 同步范围

- 同步 `api/application/pay/` 下的业务拆分模块：`collection.py`、`dispatch.py`、`payout.py`、`utr_callback.py`、`decimal_amount.py`、`raast_qr.py` 和新的 `pay.py` 入口。
- 同步 worker 公共日志模块：`api/jobs/common/`。
- 同步 EasyPaisa 公共模块和代付拆分模块：`api/jobs/easypaisa/common/`、`api/jobs/easypaisa/payout/`、`auto_payout.py`、`easypaisa_monitor.py`。
- 同步 JazzCash 代付拆分模块：`api/jobs/jazzcash/payout/`、`jazzcash_auto_payout.py`、`jazzcash_monitor.py`。
- 同步账单/余额 worker 中已去掉旧 HTTP 兼容层的文件：`pakistanpay_v2.py`、`Jazzcashpay_v2.py`、`update_payment_balance.py`。
- 同步与本次代码直接相关的测试文件。

## 不同步范围

- 不覆盖 `api/config.example.py`、`admin/config.example.py`、`merchant/config.example.py`。
- 不覆盖 `ops/tenants/d7pay/`、K8s YAML、Jenkins 脚本、域名、证书、APK 下载站配置。
- 不复制 `pk_project` 未纳管目录、日志、缓存、指纹、前端构建产物或本地临时文件。
- 不同步 `pk_project` 当前未提交的 README/err 本地改动。

## 风险与控制

- API `pay.py` 入口拆分后保留 re-export，旧 import 路径继续可用。
- Worker 拆分后需要通过 Python 编译检查和重点测试验证导入路径。
- D7pay 运行配置由现有租户文件继续控制，本次只动业务代码和文档。
- GitNexus 代表性影响分析显示 `Pay`、`Pay_df`、`push_order`、EasyPaisa/JazzCash worker 类风险为 LOW。

## 验收标准

- `python3 -m py_compile` 覆盖本次同步的 API 与 worker 关键文件并返回 0。
- 重点测试通过：`test_decimal_amount.py`、`test_raast_qr.py`、`test_statement_order_scheduler.py`、`test_easypaisa_monitor_idempotency.py`。
- `git diff --name-status` 中不出现 D7pay 租户配置、K8s、Jenkins、APK 下载站配置被 pk_project 覆盖。
- `gitnexus detect_changes` 能列出预期影响范围，未出现非预期高风险改动。
