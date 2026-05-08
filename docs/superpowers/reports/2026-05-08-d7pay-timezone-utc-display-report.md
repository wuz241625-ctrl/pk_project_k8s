# D7pay UTC 展示时区修复报告

## 处理内容

- 新增 `display_today_between()`，用于把巴基斯坦自然日转换为 UTC 查询范围。
- 将 `business_now_utc()` 改为显式 UTC naive datetime。
- admin、merchant、app 中用户可见的默认“今天”查询范围改为应用层时区转换。
- 上游查询签名参数移除 `Asia/Shanghai`，统一使用 `display_now()`。
- 保留订单超时、锁、TTL、数据库 `NOW()` 等内部相对时间逻辑，不做全局替换。

## 验收命令

```bash
python3 -m py_compile api/application/timezone.py admin/application/timezone.py merchant/application/timezone.py admin/application/order/order.py admin/application/merchant/merchant.py admin/application/partner/partner.py admin/application/record/record.py admin/application/recharge/recharge.py admin/application/usdtRecharge/usdtRecharge.py admin/application/order/pub_acc_withdrawal.py merchant/application/count/count.py merchant/application/order/order.py api/application/pay/thirdCallback.py api/application/third/third_df.py admin/application/order/query_third_order_status.py api/application/app/home/home.py api/application/app/agent/agent.py
```

结果：exit 0。

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_timezone_policy
PYTHONPATH=admin python3 -m unittest admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter
PYTHONPATH=merchant python3 -m unittest merchant.tests.test_timezone_policy
```

结果：全部通过。

```bash
rg -n "Asia/Shanghai|datetime\\.today\\(\\)\\.date\\(\\)" api admin merchant -g '*.py'
```

结果：无输出，exit 1。

