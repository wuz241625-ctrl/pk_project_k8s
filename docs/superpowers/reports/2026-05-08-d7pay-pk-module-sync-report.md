# D7pay PK Module Sync Report

## 同步内容

- 同步 `api/application/pay` 模块化拆分：代收派单、代付、UTR 回调、Raast QR、金额小数处理。
- 同步 `api/jobs/easypaisa` 的公共模块、代付拆分模块、编排器和 monitor。
- 同步 `api/jobs/jazzcash` 的代付拆分模块、编排器和 monitor。
- 同步 `pakistanpay_v2.py`、`Jazzcashpay_v2.py`、`update_payment_balance.py` 中去旧 HTTP 兼容层后的实现。
- 同步并调整相关测试，删除已不适配新架构的旧 JazzCash 单体测试。

## 未同步内容

- 未覆盖 D7pay 租户配置、K8s、Jenkins、APK 下载站、前端构建配置和 `config.example.py`。
- 未复制 `pk_project` 的本地未跟踪目录、日志、缓存、指纹和临时文件。

## 验收记录

```bash
python3 -m py_compile api/application/pay/pay.py api/application/pay/collection.py api/application/pay/dispatch.py api/application/pay/payout.py api/application/pay/utr_callback.py api/application/pay/decimal_amount.py api/application/pay/raast_qr.py api/jobs/common/logging_setup.py api/jobs/easypaisa/common/*.py api/jobs/easypaisa/payout/*.py api/jobs/easypaisa/auto_payout.py api/jobs/easypaisa/easypaisa_monitor.py api/jobs/jazzcash/payout/*.py api/jobs/jazzcash/jazzcash_auto_payout.py api/jobs/jazzcash/jazzcash_monitor.py api/jobs/pakistanpay_v2.py api/jobs/Jazzcashpay_v2.py api/jobs/update_payment_balance.py
```

结果：exit 0。

```bash
python3 -m pytest api/tests/test_decimal_amount.py api/tests/test_raast_qr.py api/tests/easypaisa_runtime/test_easypaisa_monitor_idempotency.py api/tests/easypaisa_runtime/test_statement_order_scheduler.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_jazzcash_bill_worker_final_state.py api/tests/test_easypaisa_redis_compat_retirement.py -q
```

结果：`44 passed, 5 subtests passed`。

```bash
git diff --name-status | egrep 'ops/tenants/d7pay|config.example.py|apkdownload|admin-h5|merchant-h5|k8s|jenkins' || true
```

结果：无输出，未覆盖 D7pay 租户和发布配置。

## GitNexus 审计

变更审计结果为 `critical`，原因是本次按文件同步覆盖了 API pay 派单、账单采集、EasyPaisa/JazzCash 代付 worker 主流程，属于大面积结构重构。`staged` 范围审计显示 45 个变更文件、23 个受影响流程，主要集中在 `Push_order`、账单采集、EasyPaisa monitor 和代付 worker。已用重点编译和 44 个相关测试覆盖本次同步范围。
