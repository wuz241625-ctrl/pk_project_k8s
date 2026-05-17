# EasyPaisa 状态流转闭环设计

日期：2026-05-17
分支：`d7pay`

## 1. 背景

EasyPaisa 当前主链路已经覆盖 `pre_login -> otp -> fingerprint -> secondLogin -> select_accts -> active`，但状态响应协议仍有几处不闭环：

- `ACCOUNT_SELECTION_REQUIRED` 有的返回 `next_step=select_accts`，有的返回 `second_login` 或 `query_accts`。
- `verify_fingerprint_http` 幂等短路在真实状态为 `ACCOUNT_SELECTION_REQUIRED` / `ACTIVE_SUCCESSFUL` 时仍返回 `phase=fingerprintVerified`。
- `_force_terminal_needs_relogin()` 直返没有 `next_step=needs_relogin`，App 需要猜。

## 2. 头脑风暴结论

候选方案：

- 只更新文档：风险最低，但 App 协议仍不一致。
- 在 App 端兼容多种 next_step：能绕过问题，但后端协议继续发散。
- 后端统一响应协议：所有状态都给出真实 `phase` 与可执行 `next_step`。

选第三种。状态机不改邻接表，只修响应 envelope。

## 3. 设计

- `ACCOUNT_SELECTION_REQUIRED` 的业务下一步统一为 `select_accts`。
- `second_login_http` 幂等短路：
  - 当前状态 `ACCOUNT_SELECTION_REQUIRED`：返回 `phase=accountSelectionRequired,next_step=select_accts`。
  - 当前状态 `ACTIVE_SUCCESSFUL`：返回 `phase=activeSuccessful,next_step=ready`。
- `verify_fingerprint_http` 幂等短路返回真实 `cur`，并按状态返回下一步。
- `_fallback_finish_with_query_accts()` 成功后返回 `next_step=select_accts`。
- `_force_terminal_needs_relogin()` 返回体补 `next_step=needs_relogin`。

## 4. 验收标准

- AC1：所有 `phase=accountSelectionRequired` 的成功 envelope 下一步统一为 `select_accts`。
- AC2：`verify_fingerprint_http` 幂等返回真实 phase，不把 `accountSelectionRequired/activeSuccessful` 降回 `fingerprintVerified`。
- AC3：`needsRelogin` 直返包含 `next_step=needs_relogin`。
- AC4：EasyPaisa 回归通过：`cd api && python3 -m pytest tests/ -q -k easypaisa`。
- AC5：提交前 GitNexus `detect_changes(scope=staged)` 风险已记录。
