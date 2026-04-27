# JCB 冷却期流程处理计划

## 目标

把 JazzCashBusiness `loginStep2` 的冷却期从“指纹拒绝/重新上传”修正为“指纹已验证并等待 120 分钟冷却”，并让 API、runtime snapshot、`payment_status_http` 对同一事实给出一致输出。

## 计划

1. 官方 App 反编译核对
   - 核对 cool-down 文案、时长、BVS cooldown 参数和接口。
   - 明确冷却期与扫描失败是两个分支。

2. 测试先行
   - 新增 `verify_fingerprint_http` 遇到冷却时保留 `fingerprintVerified` 的测试。
   - 新增冷却未结束时重复验证不打上游的测试。
   - 新增 `payment_status_http` 在冷却中返回 `wait_cooldown` 的测试。

3. 实现
   - 给 JCB 指纹验证增加结构化结果：`verified`、`cooldown`、`rejected`、`transient`。
   - `cooldown` 分支写入 `cd_until/cooldown_until/last_error`，状态保持 `fingerprintVerified`。
   - 冷却未结束时短路，不重复调用上游。
   - 冷却结束后直接 `secondLogin`，不重复 `loginStep2`。
   - `payment_status_http` 根据 `last_error.code=FP_COOLDOWN` 和 `cd_until` 返回 `wait_cooldown`。

4. 文档
   - 更新 `api/build.md` 的测试入口。
   - 更新 `api/err.md` 的排错口径。
   - 保留设计文档和本计划。

5. 验收与提交
   - 运行定向测试和 JCB runtime 相关测试。
   - 运行 `py_compile` 和 `git diff --check`。
   - `git commit` 后 `git push origin main`。

## 验收标准

- `loginStep2` 冷却响应不会把 session 退回 `fingerprintUploadRequired`。
- 冷却期间 Redis session 与 runtime snapshot 都保留 `fingerprintVerified`、`fingerprint_path`、`cd_until`、`last_error.code=FP_COOLDOWN`。
- 冷却期间重复调用 `verify_fingerprint_http` 不打上游，返回 `next_action=wait_cooldown`。
- 冷却结束后允许复用同一份指纹继续 `verify_fingerprint_http`，内部直接执行 `secondLogin`。
- 明确上游拒绝指纹时仍返回 `FP_UPSTREAM_REJECTED`，并要求重新上传。
- `payment_status_http` 冷却期间返回 `next_action=wait_cooldown`。
- 测试、编译、diff 检查通过。
