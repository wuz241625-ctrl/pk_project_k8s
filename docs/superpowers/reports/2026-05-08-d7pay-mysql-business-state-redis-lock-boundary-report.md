# D7pay MySQL 业务态与 Redis 锁边界验收报告

## 处理内容

- `EWalletHandler.place_order_status()` 在 MySQL final status 模式下只读 MySQL 业务态，不再降级读取 `payment_online_df`。
- `BaseHandler.clear_active()` 退役旧 `payment_active_channel_*` 扫描清理，不再让历史 Redis 投影进入业务路径。
- `admin.application.order.requeue_df_if_online()` 退役旧 `payment_active_df` 清理，代付是否可继续由 MySQL `payout_status` 决定。
- 新增测试锁住边界：Redis 不能作为业务资格判断源，历史残留后续由独立脚本清理。

## 保留内容

- Redis 作为锁、临时缓存、幂等、通知、上号会话、余额缓存的辅助用途不在本次清理范围。
- IP 识别和时区展示保持原样。
- D7pay env、Jenkins、K8s、域名、APK、前端配置保持原样。

## 验收记录

```bash
python3 -m py_compile api/application/lakshmi_api/services/payments/e_wallet_handler.py api/application/base.py admin/application/order/order.py
```

结果：通过。

```bash
python3 -m pytest api/tests/test_easypaisa_redis_compat_retirement.py::EasyPaisaRedisCompatRetirementTests::test_lakshmi_place_order_status_does_not_use_legacy_payment_online_df api/tests/test_easypaisa_redis_compat_retirement.py::EasyPaisaRedisCompatRetirementTests::test_base_clear_active_does_not_clean_legacy_active_channel_projection -q
```

结果：`2 passed`

```bash
python3 -m pytest admin/tests/test_redis_business_state_retirement.py -q
```

结果：`1 passed`

```bash
python3 -m pytest api/tests/test_easypaisa_redis_compat_retirement.py api/tests/test_jazzcash_auto_payout_v16.py api/tests/test_jazzcash_monitor_final_state.py api/tests/test_websocket_monitor_ep_dispatch.py api/tests/test_client_ip.py api/tests/test_timezone_policy.py -q
```

结果：`34 passed, 5 subtests passed`

```bash
python3 -m pytest admin/tests/test_redis_business_state_retirement.py admin/tests/test_client_ip.py admin/tests/test_timezone_policy.py -q
```

结果：`7 passed`

```bash
python3 -m pytest merchant/tests/test_client_ip.py merchant/tests/test_timezone_policy.py -q
```

结果：`5 passed`

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
```

结果：`D7pay release contract OK`

```bash
rg -n "payment_online_df|payment_active_df|payment_active_channel_" api/application/lakshmi_api/services/payments/e_wallet_handler.py api/application/base.py admin/application/order/order.py api/tests/test_easypaisa_redis_compat_retirement.py admin/tests/test_redis_business_state_retirement.py
```

结果：业务文件无匹配，仅测试函数名包含这些旧 key 名称。

```bash
git diff --check
```

结果：通过。

```bash
npx gitnexus analyze
```

结果：通过，索引刷新为 `15,584 nodes | 29,736 edges | 522 clusters | 292 flows`。

```bash
gitnexus detect_changes(scope="all")
```

结果：`risk_level: low`，5 个已跟踪文件变更，未发现受影响流程。

## 回归调整

`api/tests/test_websocket_monitor_ep_dispatch.py` 原有 `test_non_ep_online_ds_preserves_legacy_write` 仍期待非 EasyPaisa 钱包写入 `payment_online_ds/payment_active_*` 旧业务投影。根据本次边界，Redis 不再作为任何钱包业务在线状态裁判，因此已调整为 `test_non_ep_online_ds_does_not_write_legacy_business_projection`，断言不再写旧投影。
