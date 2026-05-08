# 2026-05-08 tc160 EasyPaisa 下单失败排障报告

## 现象

- tc160 `/pay` 收到 EasyPaisa `1010` 下单请求后，参数校验、商户校验、渠道校验、签名校验均通过。
- 手写候选 SQL 正常返回 `payment_id=533295`，并完成 `orders_ds.status=1`、`payment_id=533295` 和商户余额扣减。当时仍会写入 `crawl_frequently_533295`；该 Redis 加速信号已在后续清理中退役。
- 接口最终异常返回下单失败，日志堆栈为：`AttributeError: 'Pay' object has no attribute 'generate_qr_code'`。

## 根因

`pay.py` 模块拆分后，`dispatch.py` 仍在 EasyPaisa 分支调用 `handler.generate_qr_code(...)` 生成 `order_ds_third_qr_<code>`，但 `Pay.generate_qr_code(...)` 方法在重构中丢失。异常发生在派单成功之后、返回收银台 URL 之前，因此用户侧看到失败，但订单与余额状态已经进入已派单链路。

## 修复

- 在 `api/application/pay/pay.py` 恢复 `Pay.generate_qr_code(...)`。
- 方法只读取 `payment.account_iban`，继续使用 `build_payload_amount(...)` 生成带金额和 7 分钟过期时间的 Raast 动态 QR。
- 不改变候选 SQL、订单状态机、余额扣减和 Redis QR key 语义。采集加速信号 `crawl_frequently_*` 已在后续清理中退役。

## 验收

本地回归：

```bash
cd api
python3 -m unittest tests.test_easypaisa_qr_payload.EasyPaisaQrPayloadTests.test_generate_qr_code_uses_amount_and_seven_minute_expiry
python3 -m unittest tests.test_easypaisa_qr_payload tests.test_ds_dispatch_candidate_sql
```

tc160 复核：

```bash
ssh tc160 'cd /opt/pk_project && docker compose -f docker-compose.tc160.yml logs --tail=250 api'
```

验收重点：

- 新下单不再出现 `Pay object has no attribute generate_qr_code`。
- EasyPaisa 1010 派单成功后写入 `order_ds_third_qr_<code>`。
- 返回商户的下单响应进入正常收银台链路。
