# EasyPaisa isAccountRegistered 未注册响应兼容设计

## 背景

03009208353 上号日志显示，`pre_login` 调用上游 `isAccountRegistered` 返回：

```json
{"code":403,"msg":"isAccountRegistered查询: pk_easypaisa_03009208353","data":false}
```

EasyPaisa v2.2 文档定义这个响应表示“云机不存在或账户未完成云机绑定流程”，不是接口失败。旧代码把所有非 `code=200` 都当作 `SL_UPSTREAM_ERROR`，导致 `pre_login` 在首次上号前就中断，App 无法继续 `send_otp/loginStep1`。

## 方案

只调整 `_is_account_registered()` 的协议解释：

- `code=200 && data=true`：返回 `True`，进入二次上号链路。
- `code=403 && data=false`：返回 `False`，进入首次上号链路，`pre_login` 返回 `next_step=send_otp`。
- 其他响应：继续抛 `SL_UPSTREAM_ERROR`，避免把真实上游异常误判成可继续登录。

## 不做范围

- 不改变 `pre_login_http` 的状态机。
- 不改变 `loginStep1 code=200` 直登处理。
- 不改变 secondLogin 使用 DB PIN 的规则。
- 不清理 Redis 或修改线上 payment 数据。

## 验收标准

- `_is_account_registered()` 对 `403/data=false` 返回 `False`。
- `_is_account_registered()` 对未知错误码仍抛 `NewApiError`。
- `pre_login_http` 在云机未注册时返回 `next_step=send_otp`。
- EasyPaisa v19 登录相关测试通过。
- `easypaisa.py` 编译通过。
