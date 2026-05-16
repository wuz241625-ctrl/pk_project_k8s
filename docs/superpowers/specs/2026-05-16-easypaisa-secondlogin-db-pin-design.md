# EasyPaisa secondLogin 使用数据库 PIN 设计

## 背景

当前 v1.9 EasyPaisa 已支持 `_call_second_login(..., with_pwd=True)`，`_build_verify_account_request()` 会在 `with_pwd=True` 时给云机 `secondLogin` 请求追加 `phone/pwd`。历史设计里只有 URM90040 fallback 和 `change_pin_http` 内部续推带 `pwd`，独立 `second_login_http` 仍不带 `pwd`。

本轮要求调整为：EasyPaisa `secondLogin` 也带 `pwd`，但不能让 App 在普通 secondLogin 场景传钱包 PIN。除修改 PIN 以外，钱包 PIN 必须以后端数据库 `Payment.pin` 为准。

## 方案比较

### 方案 A：App 在 second_login 请求里传 pin

实现最少，但会让普通 secondLogin 信任客户端 PIN，和当前 App “已绑定钱包不展示官方 PIN”的安全边界冲突。

### 方案 B：后端在 secondLogin 前从 MySQL `payment.pin` 注入 session

`second_login_http`、二次上号链路、URM90040 fallback 链路在调用 `_call_second_login(..., with_pwd=True)` 前，统一把 `Payment.pin` 写入当前 `session_data['pinCode']`。App 请求里的 `pin/pwd` 不参与普通 secondLogin。

优点：符合“只有修改 PIN 是用户输入，其它读数据库”；改动集中；保留 `_build_verify_account_request` 的既有接口。缺点：需要给几个 secondLogin 调用点补同一段 PIN 注入。

### 方案 C：`_build_verify_account_request` 内部直接查 DB

所有 with_pwd 调用都自动查 DB。缺点是请求构建函数会混入异步 DB 访问，不符合当前同步构建器模式，也会扩大测试和调用面。

## 采用方案

采用方案 B。

新增后端 helper：

- 从传入的 payment 字典或 `_query_payment(payment_id)` 读取 `pin`。
- 只在读取到数据库 PIN 时覆盖 `session_data['pinCode']`。
- 读取不到 PIN 时返回失败，由调用链路终止为可诊断错误，避免用客户端传入的旧 PIN/假 PIN 顶上。

调用点：

- `_pre_login_second_time_chain`：二次上号 secondLogin 改为 `with_pwd=True`，pwd 来自绑定钱包 `Payment.pin`。
- `_verify_otp_fallback_chain`：fallback secondLogin 继续 `with_pwd=True`，但先用 `_query_payment()` 返回的 `pin` 覆盖 session。
- `second_login_http`：独立 second_login 从 DB 取 PIN 后 `with_pwd=True`。
- `change_pin_http`：保持例外。用户输入的新 `pin` 先走 `_change_pin()`，成功后 `_save_payment(..., pin=pin)` 写 DB，再用这个新 PIN `with_pwd=True` 续推。

## 验收标准

- 普通 `second_login_http` 即使请求里带假 `pin/pwd`，实际 `_call_second_login` 使用的 `session_data['pinCode']` 必须来自 `_query_payment(...).pin`。
- 二次上号 `_pre_login_second_time_chain` 必须用绑定钱包的 DB PIN 并 `with_pwd=True` 调 secondLogin。
- URM90040 fallback `_verify_otp_fallback_chain` 必须用 DB PIN 并 `with_pwd=True` 调 secondLogin。
- `change_pin_http` 仍只使用用户本次传入的新 PIN，且 `_save_payment(..., pin=新PIN)` 后续推 secondLogin。
- 目标测试通过：`api/tests/test_easypaisa_v19_acceptance.py`、`api/tests/test_easypaisa_v19_change_pin.py`、`api/tests/test_easypaisa_v19_urm90040.py`。
- `python3 -m py_compile api/application/app/login/banks/easypaisa.py` 通过。
- 提交前 `npx gitnexus detect-changes --repo pk_project_k8s --scope staged` 范围符合本任务。
