# EasyPaisa 旧指纹优先复用设计

日期：2026-05-17
分支：`d7pay`

## 1. 背景

已绑定 EasyPaisa 账号重新上号时，MySQL `payment.fingerprint_path` 代表该账号历史上已经完成过 `verifyFingerprint`，并且本地 ZIP 已经落盘。修复前代码在 `pre_login_http` 中会识别本地 ZIP，并写入 `reuse_local_fingerprint_after_otp` / `local_fingerprint_path`，但 `verify_otp_http` 不消费这两个字段；另外 `loginStep1 direct_success + local_zip_path` 分支会调用不存在的 `_fallback_chain_after_verify_otp`。

这会导致两个问题：

- MySQL 有可用旧指纹时，OTP 成功后仍要求 App 重新 `upload_fingerprint`。
- 极端直登分支会抛 `AttributeError`。

> 落地记录（2026-05-17）：当前 d7pay 已新增 `_reuse_local_fingerprint_after_otp`，并由 `pre_login_http` 的 direct success 分支和 `verify_otp_http` 共同调用；当前代码不包含 `_fallback_chain_after_verify_otp`，该名字只作为历史缺陷背景保留。

## 2. 头脑风暴结论

目标业务口径：

- 已绑定账号：`secondLogin` 快路径失败后，如果 MySQL 有本地旧指纹，OTP 或 `loginStep1 direct_success` 后必须先复用旧指纹。
- 旧指纹复用链路：`upload_data(旧 ZIP)` → `verifyFingerprint` → `secondLogin(with_pwd=True)` → `queryAccountList`。
- 只有旧指纹缺失、文件不存在、推送失败、上游拒绝、DB PIN 缺失或后续 secondLogin 失败时，才引导 App 进入 `upload_fingerprint` 或原有错误分支。

候选方案：

- 在 `verify_otp_http` 内直接内联旧指纹链路：实现快，但会复制 fallback 逻辑。
- 恢复旧计划里的 `_fallback_chain_after_verify_otp`：能修直登缺方法，但旧计划依赖过时的 `_perform_second_login` / `_post_secondlogin_query_accts`，当前 d7pay 已明确不采用。
- 新增当前代码口径的 `_reuse_local_fingerprint_after_otp` helper，并让直登和 OTP 成功都调用它。

选定第三种：新增小 helper，复用当前已有 `_call_upload_data`、`_call_verify_fingerprint`、`_hydrate_second_login_pin_from_db`、`_call_second_login`、`_fallback_finish_with_query_accts`。

## 3. 设计

- `pre_login_http` 保留对 `payment.fingerprint_path` 的检测，把可用路径写入 session。
- `loginStep1 direct_success + local_zip_path` 调用新的 `_reuse_local_fingerprint_after_otp(redis_key, session_data, local_zip_path)`，不再调用缺失方法。
- `verify_otp_http` 在 OTP 成功、session 状态推进到 `OTP_VERIFIED` 后：
  - 如果 `reuse_local_fingerprint_after_otp=True` 且 `local_fingerprint_path` 存在，先调用 `_reuse_local_fingerprint_after_otp`。
  - 如果复用成功，直接返回 `ACCOUNT_SELECTION_REQUIRED/select_accts`。
  - 如果复用失败且属于指纹不可用，返回 `FP_UPSTREAM_REJECTED` / `upload_fingerprint`。
  - 如果没有旧指纹标记，保持首次上号原行为：返回 `fingerprintUploadRequired`。

## 4. 验收标准

- AC1：已绑定账号 `secondLogin` 快路径失败、`loginStep1` 发 OTP、本地旧指纹存在时，`verify_otp_http` 不返回 `fingerprintUploadRequired`，而是复用旧指纹并进入 `ACCOUNT_SELECTION_REQUIRED`。
- AC2：已绑定账号 `loginStep1 direct_success` 且本地旧指纹存在时，不再抛 `AttributeError`，而是复用旧指纹并进入 `ACCOUNT_SELECTION_REQUIRED`。
- AC3：旧指纹推送或验证失败时，返回 `next_step=upload_fingerprint`，让 App 重新采集。
- AC4：新号或没有旧指纹时，仍按原流程返回 `fingerprintUploadRequired`。
- AC5：EasyPaisa 回归测试通过：`cd api && python3 -m pytest tests/ -q -k easypaisa`。
- AC6：提交前 GitNexus `detect_changes(scope=staged)` 风险符合预期。
