# Second Login Idempotency Hotfix (v1.9.1) 设计文档

- **日期**: 2026-05-14
- **目标版本**: v1.9.1（hotfix-1，建立在 v1.9 之上）
- **关联 spec**: `docs/superpowers/specs/2026-05-14-easypaisa-login-redesign-design.md`
- **关联 plan**: `docs/superpowers/plans/2026-05-14-easypaisa-login-redesign.md`
- **范围**: 仅 backend `api/application/app/login/banks/easypaisa.py` + 测试。APP 端零改动。

## 1. 背景

v1.9 在 2026-05-14 13:10 部署后做了生产 e2e 验证（533294 → ready ✅、533296 → URM90040 fallback ✅）。之后做代码 review 发现 5 个待修问题：

| 编号 | 问题 | 严重度 |
|---|---|---|
| C1 | `second_login_http` 入态校验只接 `FINGERPRINT_VERIFIED`，二次上号续推 / URM90040 fallback chain 全成功后状态已是 `ACCOUNT_SELECTION_REQUIRED`，APP 按 `next_step='second_login'` 调进来 → `INVALID_TRANSITION` → APP 卡死 | **Critical** |
| C2 | `verify_fingerprint_http` 落盘失败时 `_update_payment_fingerprint_path` 内部 try/except 吃掉异常 → 本地新 ZIP 已覆盖老 ZIP 但 MySQL 还是老 path → 本地文件与 MySQL 不一致 | **Critical** |
| M1 | `_urm90040_fallback` 用 `GET + SETEX`（非原子），并发场景下限频会失效 | Major |
| M2 | `_check_payment` SQL filter 没 `partner_id`，盗号防护仅靠应用层 `existing.user_id == user_id` 判断（无防御纵深） | Major |
| M3 | session 持久化前没清除 `password` 字段（partner 交易密码明文进 Redis） | Major |

C1 在生产实际经常发生（任何 wallet_status=0 但云机健康的账户重新上号都撞）。spec §3.3 ⑪ 设计意图原本就要求 `second_login_http` 幂等（"由于服务端已经把 queryAccountList 完成、状态已是 ACCOUNT_SELECTION_REQUIRED，APP 的 secondLogin 调用会拿到 success → query_accts → 选账号"），但代码漏实现了幂等分支。

## 2. 五个 Fix 总览

| Fix | 文件 | 位置 | 改动量 | 测试位置 |
|---|---|---|---|---|
| #1 second_login_http 入态幂等（C1）| `easypaisa.py` | line 1583-1588 之前插入 | +10 行 | `test_easypaisa_v19_acceptance.py` 加 2 条 |
| #2 _check_payment SQL filter（M2）| `easypaisa.py` | line 2813-2825 内 | +1 / -1 行 | 新文件 `test_easypaisa_v19_check_payment.py` 加 2 条 |
| #3 URM90040 原子 INCR（M1）| `easypaisa.py` | line 1172-1187 替换 | +6 / -8 行 | `test_easypaisa_v19_urm90040.py` 加 2 条 |
| #4 fingerprint atomic rename（C2）| `easypaisa.py` | line 1530-1543 + `_update_payment_fingerprint_path` | +20 / -10 行 | `test_easypaisa_v19_fingerprint.py` 加 1 条 |
| #5 session scrub password（M3）| `easypaisa.py` | line 926 删除 + `_fallback_to_first_login` 检查 | -1 行 | `test_easypaisa_v19_force_terminal.py` 加 1 条 |
| docs | spec + plan 更新 | 本文件 + plan 追加段 | — | — |

策略 B：每个 fix 独立 commit + 1 个文档 commit，共 6 commit。

## 3. 详细修复

### 3.1 Fix #1：`second_login_http` 入态幂等

**当前行为**（`easypaisa.py:1583-1588`）：
```python
cur = session_data.get('status')
if cur != LoginStatus.FINGERPRINT_VERIFIED:
    raise NewApiError('INVALID_TRANSITION',
                      f'second_login expected FINGERPRINT_VERIFIED, got {cur}')
```

**问题**：spec §3.3 ⑩ 让 `pre_login_http` 内部一气呵成跑 upload_data + verifyFingerprint + secondLogin + queryAccountList，状态直接跨步到 `ACCOUNT_SELECTION_REQUIRED`。spec §3.3 ⑪ 让 APP 按 `next_step='second_login'` 调进来 → 入态校验拦下。

**修复**：模仿 `verify_fingerprint_http` 的 spec §3.6.1 幂等模式，在入态校验之前加短路。

```python
cur = session_data.get('status')
# spec §3.6.1 风格幂等：二次上号续推 / fallback chain 已完成
if cur in (LoginStatus.ACCOUNT_SELECTION_REQUIRED,
           LoginStatus.ACTIVE_SUCCESSFUL):
    self.logger.info(
        f'{self._log_key(funcName)} 幂等返回: 状态已 {cur}，'
        f'second_login 续推已由 pre_login/verify_otp 完成'
    )
    return {
        'status': 'success',
        'message': '二次登录已就绪（幂等）',
        'data': {
            'ok': True,
            'next_step': 'query_accts',
            'phase': cur,
        },
    }
# 原有入态校验
if cur != LoginStatus.FINGERPRINT_VERIFIED:
    raise NewApiError('INVALID_TRANSITION',
                      f'second_login expected FINGERPRINT_VERIFIED, got {cur}')
```

**影响路径**：
- Path B（二次上号 secondLogin 直接成功）→ 现在 APP 调 `second_login_http` 拿到 `ok:true, next_step:'query_accts'` 继续走
- Path C（URM90040 fallback chain 续推成功）→ 同上
- 首次上号路径（入态 FINGERPRINT_VERIFIED）→ 不受影响（不进入新分支）

### 3.2 Fix #2：`_check_payment` SQL filter by partner_id

**当前行为**（`easypaisa.py:2813-2825`）：
```python
existing_payment = session.query(Payment).filter(
    Payment.bank_type == bank_type_id,      # 历史 dead filter（bank_type 与 bank_type_id 重复）
    Payment.bank_type_id == bank_type_id,
    Payment.phone == phone,
).first()
```

**问题**：SQL 没用 partner_id 过滤。盗号防护靠应用层 `if existing.get('user_id') == user_id: ... else: raise 10402`。如果以后重构丢了 application 层判断，攻击者用 B 的 phone 就能查到 B 的记录。

**修复**：SQL 层直接 `AND partner_id = ?`（用 ORM 属性 `Payment.user_id`，SQLAlchemy 会翻译成 SQL 列 `partner_id`）。

```python
existing_payment = session.query(Payment).filter(
    Payment.bank_type_id == bank_type_id,
    Payment.phone == phone,
    # NEW: 防御纵深。Payment.user_id 是 ORM 属性，对应 SQL 列 partner_id
    Payment.user_id == partner_id,
).first()
```

同时删除 `Payment.bank_type == bank_type_id` 这条历史 dead filter（与 `bank_type_id` 重复）。

**ORM/SQL 映射说明**：
- Python ORM 属性：`Payment.user_id`
- SQL 实际列：`partner_id`
- 定义：`payment.py:34` `user_id: Mapped[int] = Column("partner_id", Integer, ...)`

**影响**：
- 攻击者 A 用 B 的 phone 调 pre_login → `_check_payment` SQL 查不到（filter 含 `partner_id = A`）→ `existing = None` → 进入 `else` 走"is_new_user=True"分支 → 后续 _save_payment 在 verify_otp_http 创建新行（this is OK; race window 已在 spec discussion 中讨论）
- B 自己调 → 正常查到 → 走 owner 分支

### 3.3 Fix #3：URM90040 fallback 原子 INCR

**当前行为**（`easypaisa.py:1172-1187`）：
```python
count_key = self.URM90040_COUNT_KEY.format(payment_id=payment_id)
cur = await self.redis.get(count_key)         # 读
try:
    cur_count = int(cur) if cur else 0
except (TypeError, ValueError):
    cur_count = 0
if cur_count >= self.URM90040_LIMIT:           # 判断
    return await self._force_terminal_needs_relogin(...)
new_count = cur_count + 1                       # 自增
await self.redis.setex(count_key, ..., new_count)  # 写
```

**问题**：GET → 判断 → SETEX 之间有时间窗口。两个并发请求都看到 `cur_count = 2` → 都写 3 → 实际允许 4 次而不是 3 次。攻击场景：恶意 APP 并发发起 N 次 pre_login。

**修复**：用 Redis `INCR`（原子）+ 首次设 EXPIRE TTL。

```python
count_key = self.URM90040_COUNT_KEY.format(payment_id=payment_id)
# 原子 INCR：返回自增后的值
new_count = await self.redis.incr(count_key)
# 首次自增后才设 TTL（避免覆盖已有 TTL）
if new_count == 1:
    await self.redis.expire(count_key, self.URM90040_WINDOW_SECONDS)
if new_count > self.URM90040_LIMIT:
    return await self._force_terminal_needs_relogin(
        redis_key=redis_key, session_data=session_data,
        reason=f'URM90040 count {new_count} exceeded {self.URM90040_LIMIT}/hour',
        error_code='SL_NEEDS_RELOGIN',
        message='账号疑似被频繁占用，请联系运维介入',
    )
```

**注意行为变化**：
- 老逻辑：`cur_count >= LIMIT`（cur_count 是 INCR 之前的值），意思是"达到 LIMIT 就拒下一次"
- 新逻辑：`new_count > LIMIT`（new_count 是 INCR 之后的值），意思是"超过 LIMIT 才拒"
- 数值等价：老的拒第 4 次，新的也拒第 4 次

**保留行为**：计数器在失败也会 +1（spec §3.5 没明示否定，保守保留）。

### 3.4 Fix #4：指纹 MySQL 写失败时 atomic rename

**当前行为**（`easypaisa.py:1530-1543`）：
```python
full_path = os.path.join(self.FINGERPRINT_PATH, filename)
try:
    os.makedirs(self.FINGERPRINT_PATH, exist_ok=True)
    with open(full_path, 'wb') as fp_file:
        fp_file.write(zip_body)           # 1. 老 ZIP 已被覆盖
except Exception as e:
    return {'status': 'error', ...}        # file 失败：return（pending 没删，OK）
await self._update_payment_fingerprint_path(resolved_payment_id, full_path)
# 2. _update_payment_fingerprint_path 内部 try/except 吃掉 MySQL 异常 → 静默
await self.redis.delete(pending_key)       # 3. 不管 MySQL 是否成功都删 pending
```

**问题**：MySQL 写失败时 file 已覆盖、pending 被删、状态仍推进到 FINGERPRINT_VERIFIED。但 MySQL `fingerprint_path` 还是老路径。下次二次上号读 MySQL 拿到老路径，文件内容已被覆盖 → 上传给云机的是新 ZIP，但行为对 _check_payment / _update_payment 来说像是用旧 ZIP。

**修复策略**：先写 `.new` 临时文件 → MySQL 写成功才 `os.rename` 原子替换 → 失败时 rollback 删 `.new`。

```python
full_path = os.path.join(self.FINGERPRINT_PATH, filename)
tmp_path = full_path + '.new'
try:
    os.makedirs(self.FINGERPRINT_PATH, exist_ok=True)
    with open(tmp_path, 'wb') as fp_file:
        fp_file.write(zip_body)
except Exception as e:
    self.logger.error(f'{self._log_key(funcName)} 落盘失败: {e}', exc_info=True)
    return {
        'status': 'error', 'message': '本地保存失败',
        'data': {'code': 'SL_UPSTREAM_ERROR', 'phase': LoginStatus.OTP_VERIFIED},
    }
# MySQL 写成功才 atomic rename，失败 rollback
try:
    await self._update_payment_fingerprint_path(resolved_payment_id, full_path)
except Exception as e:
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    self.logger.error(
        f'{self._log_key(funcName)} MySQL 写入失败，回滚 .new: {e}',
        exc_info=True,
    )
    return {
        'status': 'error', 'message': 'MySQL 写入失败',
        'data': {'code': 'SL_UPSTREAM_ERROR', 'phase': LoginStatus.OTP_VERIFIED},
    }
os.rename(tmp_path, full_path)  # atomic 替换老 ZIP
await self.redis.delete(pending_key)
```

**同时改 `_update_payment_fingerprint_path`**（`easypaisa.py:1216-1224`）让它 re-raise 异常而不是吃掉：

```python
async def _update_payment_fingerprint_path(self, payment_id, full_path):
    funcName = '_update_payment_fingerprint_path'
    # 上层依赖此函数的异常做回滚，必须 re-raise（不要 try/except 吃异常）
    with self.handler.db_orm.sessionmaker() as session:
        session.execute(
            update(Payment).where(Payment.id == payment_id).values(fingerprint_path=full_path)
        )
        session.commit()
    self.logger.info(f'{self._log_key(funcName)} payment_id={payment_id} path={full_path}')
```

### 3.5 Fix #5：session scrub password

**当前行为**（`easypaisa.py:926` 在 `pre_login_http` 内）：
```python
session_data = {
    # ...
    'pinCode': pin,
    'bankname': bankname,
    'password': password,        # ← 明文 partner 交易密码
    'account': data.get('account', ''),
    # ...
}
```

**问题**：partner 交易密码 bcrypt 校验通过后被直接放进 session，跟着整个 session 序列化到 Redis（TTL 300s）。Redis 数据泄露 = 所有 active 上号用户的交易密码明文泄露。

**修复**：直接从 session_data dict 删除该字段。

```python
session_data = {
    # ...
    'pinCode': pin,
    'bankname': bankname,
    # 'password' 字段移除：bcrypt 校验完不再需要存 session
    'account': data.get('account', ''),
    # ...
}
```

**安全验证**（pre-spec sanity check 已完成）：
```bash
grep -nE "session\['password'\]|session_data\['password'\]|session_data\.get\('password'\)|session\.get\('password'\)" \
  api/application/app/login/banks/easypaisa.py
# 输出：空
```

`session.password` **在整个 easypaisa.py 0 引用**。`_fallback_to_first_login` 重建 session 时也不读 password。删除 100% 安全。

## 4. 状态机变更

**无变化**。仍是 spec §3.1 的 8 状态 + §3.1.1 邻接表。Fix #1 只是给 `second_login_http` 加幂等返回，不改状态转换边。

## 5. APP 端契约

**零影响**。

- 返回字段：Fix #1 在 ACCOUNT_SELECTION_REQUIRED / ACTIVE_SUCCESSFUL 状态下返回 `next_step: 'query_accts'` 字段，APP 端 spec §13 已识别（与 second_login_http 正常成功路径返回同款 `next_step: 'query_accts'`）
- 错误码：Fix #1 之前会返回 `INVALID_TRANSITION` 这是错误行为；修复后返回 `success`，更友好
- 字段名：无新增字段

## 6. 测试清单

| Fix | 测试文件 | 用例名 | 验证 |
|---|---|---|---|
| #1 | `test_easypaisa_v19_acceptance.py` | `test_second_login_idempotent_after_pre_login_chain` | ACCOUNT_SELECTION_REQUIRED 入态返回 ok |
| #1 | `test_easypaisa_v19_acceptance.py` | `test_second_login_idempotent_after_active` | ACTIVE_SUCCESSFUL 入态返回 ok |
| #2 | `test_easypaisa_v19_check_payment.py` (NEW) | `test_check_payment_returns_only_owner_record` | 跨 partner 查询返回 None |
| #2 | `test_easypaisa_v19_check_payment.py` (NEW) | `test_check_payment_returns_own_record` | 同 partner 查询返回记录 |
| #3 | `test_easypaisa_v19_urm90040.py` | `test_urm90040_atomic_concurrent_calls` | 模拟 5 个并发 INCR：前 3 通过，后 2 拒 |
| #3 | `test_easypaisa_v19_urm90040.py` | `test_urm90040_first_call_sets_expire` | INCR 返回 1 时调 EXPIRE 设 TTL 3600 |
| #4 | `test_easypaisa_v19_fingerprint.py` | `test_verify_fingerprint_rollback_on_mysql_fail` | MySQL 抛异常时 .new 删、老 ZIP md5 不变 |
| #5 | `test_easypaisa_v19_force_terminal.py` | `test_session_data_does_not_contain_password` | pre_login 后 session 无 password 字段 |

**累计预期**：27（v1.9 基线）+ 8（hotfix-1 新增）= **35 passed**。Regression 必须全过。

## 7. 验收用例（H1-H6）

H1 - H5 是单元/集成测试覆盖（Fix #1-#5 各自的新测试）。H6 是生产 e2e。

| 编号 | 用例 | 步骤 | 预期 |
|---|---|---|---|
| **H1** | Fix #1 单元测试 | 跑 `test_second_login_idempotent_after_*` | 2 个全过 |
| **H2** | Fix #2 单元测试 | 跑 `test_check_payment_returns_*` | 2 个全过 |
| **H3** | Fix #3 单元测试 | 跑 `test_urm90040_*` | 4 个全过（2 老 + 2 新）|
| **H4** | Fix #4 单元测试 | 跑 `test_verify_fingerprint_rollback_*` | 1 个通过 |
| **H5** | Fix #5 单元测试 | 跑 `test_session_data_does_not_contain_password` | 1 个通过 |
| **H6** | 生产 e2e（Fix #1 Path B 实测）| 临时把 533294 wallet_status 改 0 → pre_login → second_login | second_login 返回 success / ok / next_step=query_accts（不再 INVALID_TRANSITION）|
| **H6b** | 生产 e2e（Fix #2 防御纵深）| partner 33057 token 调 pre_login，phone 用别的 partner 的 | 返回 10402；后端 SQL 日志显示 `WHERE partner_id=33057` |
| **H6c** | 生产 e2e（Fix #3 INCR）| kubectl exec 触发一次 533296 pre_login | Redis `easypaisa:urm90040_count:533296` 通过 INCR 增加，TTL 接近 3600 |
| **H6d** | 生产 e2e（Fix #5）| 触发任何 pre_login → kubectl get session JSON | 不含 "password" 字段 |
| **H6e** | Smoke test | 部署完跑 5 分钟 → 看 api.log 末 200 行 | 无新增 ERROR；payment_status_http 正常返回 |

**通过条件**：
- H1-H5（必备）单元测试全过
- H6 至少 H6 / H6b / H6e 通过（H6c / H6d 视环境配合度可降为单元测试代替）

## 8. 部署 + 回滚

### 8.1 部署流程

```
T0:    合并 6 commit 到 d7pay → git push
T+5m:  打镜像 → kubectl set image deployment/api-deploy api=<new_tag>
T+10m: kubectl rollout status 等 2 个 pod Ready
T+12m: 跑 H6 系列生产 e2e
T+25m: 通过 → 完成；不通过 → 8.2 回滚
```

### 8.2 回滚

```bash
kubectl rollout undo deployment/api-deploy -n pk-d7pay
kubectl rollout status deployment/api-deploy -n pk-d7pay
```

**回滚后 Redis 数据兼容性**：
- Fix #3 用 INCR 写入的 count 值是 string 形式的整数（如 `b'3'`），老代码 GET 后能正确 int 解析 ✅
- Fix #5 session 不含 password 字段，老代码读 `session.get('password')` 返回 None；老代码也不读这个字段 → 无影响 ✅
- Fix #4 留下的 `.new` 临时文件如果有遗留，老代码不会处理；需要发版前后扫一遍 `/fingerprint/*.new` 清理（可选）

回滚是 forward-compatible 的。

## 9. 已知 Trade-offs

1. **Fix #3 失败也算计数**：spec §3.5 没明示 fallback 失败时计数器是否递增。当前实现"失败也算"——保守选择，防止恶意 spam。未来如需"只算成功的 fallback"，需要在 `_send_otp` 成功后才 INCR。

2. **Fix #4 .new 临时文件清理**：`os.rename` 失败的概率极低（同一目录下原子操作），但理论上仍可能留下 `.new` 文件。未来可加一个 housekeeping cron 定期扫除（不在本 hotfix 范围）。

3. **Fix #5 删 password 后 race window 仍存在**：同 phone 跨 partner 并发 race 不在本 hotfix 范围。需要 MySQL 加 `(bank_type_id, phone) UNIQUE` 约束才能根除。当前依赖 OTP SMS 单向通道天然限流。

4. **Fix #1 幂等返回的 `next_step` 是固定 `'query_accts'`**：spec §13 APP 端识别 `query_accts` 走 `_runQueryAndSelect`。OK ✅。

## 10. 不在本次范围内

- 业务接口（queryBalance、queryBill、transfer）不动
- APP 端任何改动（PreLoginResult / submitForm 等都不动）
- spec 主文档 `2026-05-14-easypaisa-login-redesign-design.md` 不动
- Plan 主文档：仅末尾追加 hotfix-1 记录段
- `_check_payment` race condition 防护（DB UNIQUE 约束）
- 路径 D/E/F（指纹失败、PIN 错误、已 active 重复 pre_login）已 OK 不动
- `_log_response` 30 行日志精简（独立优化项）
- 文件 3056 行 → 1500 行的瘦身（独立优化项）
