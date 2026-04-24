# Admin 排错文档

## 常见问题

### 0.3 admin 已有 EasyPaisa runtime 代码，但线上还是旧 helper

现象：

- 本地 `admin` 的 EasyPaisa runtime 读写已经收口
- 但线上页面仍可能表现得像旧版本
- reset、在线态展示、`payment_active_1001` 对齐结果会和本地预期不一致

这轮线上实测结论：

- 真正不同步的不是 `partner.py` / `auto_payout.py`
- 而是：
  - `admin/application/easypaisa_runtime/service.py`
  - `admin/application/easypaisa_runtime/keyspace.py`

处理：

1. 只白名单同步这两个文件
2. 不覆盖 `admin/config.py`
3. 远端先跑：
   - `python -m py_compile application/easypaisa_runtime/keyspace.py application/easypaisa_runtime/service.py application/easypaisa_runtime/reader.py`
4. 再执行：
   - `ops admin restart`

fresh 验证：

- 远端 `sha256`
  - `service.py = fce561d7382d338c60b30c53f526ead9dd2cdda5de067d4704016935d13fcc25`
  - `keyspace.py = a17722d014fd72d31510d454906d37d165cd232eabff609d035139ff3286a661`
- `admin` 进程数：`15`
- `http://127.0.0.1:6000/`：`404`

结论：

- 以后遇到 admin EasyPaisa 展示口径不对，先查线上这两个 runtime helper 文件哈希
- 不要先把问题归因到前端或 `partner.py`

### 0.2 Admin 点了 EasyPaisa reset，但 `payment_active_1001` 还残留

现象：

- admin 已执行 `resettingPayment`
- runtime snapshot 已变成 offline
- 但 Redis 里仍残留：
  - `payment_online_ds`
  - `payment_active_1001`

根因：

- `admin/application/easypaisa_runtime/service.py`
  之前只清：
  - `payment_online_df`
  - `payment_active_df`
  - `login_on_easypaisa_*`
- 没有按 EasyPaisa runtime snapshot 的 `channels` 清：
  - `payment_online_ds`
  - `payment_active_{channel}`

处理：

1. `admin/application/easypaisa_runtime/keyspace.py`
   - 补齐：
     - `LEGACY_PAYMENT_ONLINE_DS`
     - `normalize_channels(...)`
     - `legacy_payment_active_channel_key(...)`
2. `EasyPaisaAdminRuntimeService.force_offline()`
   - 读取 snapshot `channels`
   - reset/offline 时一并清理 DS/channel 投影

验证：

```bash
cd /Users/tear/pk_project
python3.12 -m unittest discover -s admin/tests -p 'test_easypaisa_runtime_reader.py' -v
```

结果：

- `Ran 7 tests`
- `OK`

结论：

- admin reset 现在不仅会清 EasyPaisa 代付 legacy 状态
- 也会同步清掉 `payment_online_ds` 与 `payment_active_{channel}`

### 0.1 Admin 看到的 EasyPaisa 在线态，不能从新锁键反推

现象：

- Redis 里可能只剩：
  - `easypaisa_runtime:lock:payment:<payment_id>`
- 但 admin 页面不应该因此把账号展示成在线

根因：

- `easypaisa_runtime:lock:*` 是重复登录锁，不是在线投影
- admin 的 EasyPaisa 在线态只应来自：
  - runtime snapshot
  - 或 legacy `login_on_easypaisa_*` 兜底

处理：

- `admin/application/easypaisa_runtime/reader.py`
  不读取 `easypaisa_runtime:lock:*`
- `admin/application/easypaisa_runtime/service.py`
  在 `force_reset()` / `force_offline()` 时同步清新锁
- `admin/application/easypaisa_runtime/keyspace.py`
  补齐新锁 helper，避免 admin/api 漂移

结论：

- admin 上“在线”与否，不再允许通过新锁键猜测
- 新锁只服务于登录防重，不服务于展示口径

### 0. EasyPaisa 管理端看起来“不一致”，但根因在 API jobs 旧状态

现象：

- `admin` 页面看到的 EasyPaisa 在线态与预期不一致
- 容易误以为是 `partner.py` / `auto_payout.py` 没有更新

这次线上实测结论：

- `admin` 目标文件同步后，远端哈希已与本地一致
- 真正导致状态漂移的是 `api` 侧 Redis 旧状态回流：
  - `hash_easypaisa`
  - `set_easypaisa`
  - `easypaisa_runtime:index:*`

排查顺序：

1. 先看 `api` runtime 是否已收敛
2. 再看 `admin` 是否还是旧代码

不要反过来先怀疑 `admin` 展示逻辑。

### 1. Admin 能启动，但请求失败

优先检查：

- `ADMIN_API_URL` 是否指向可达的 API 服务
- MySQL / Redis 是否可用

### 2. 登录和权限相关异常

`admin` 强依赖数据库中的管理员、角色和权限数据。若本地没有导入种子数据，很多接口虽然能启动，但不会有可用账号。

### 3. 管理端 `otherpay` 下拉只能看到名字

现象：

- 多个 Easypay 账号都叫 `easypay`
- 运营在商户配置和通道一键全切里无法判断自己选中了哪一个

处理后行为：

- 下拉改为显示 `name | merchant_id | key3 | #id`
- 保存时仍提交 `id`

若要回归验证，运行：

```bash
cd /Users/tear/pk_project/frontend_src/admin
VUE_APP_SYSTEM=OSPay VUE_APP_BASE_API=/prod-api npm run test:unit -- --runInBand tests/unit/utils/otherpay.spec.js
```

注意：

- 这个前端测试依赖 `VUE_APP_SYSTEM`
- 若未设置，会在 `vue.config.js` 阶段报 `toLocaleLowerCase` 空指针

## 2026-04-19 EasyPaisa admin runtime 读取与重置闭环

### 现象

- `partner.py` 里 EasyPaisa 仍直接读取：
  - `login_on_easypaisa_*`
  - `payment_online_df`
- `resettingPayment` 只清 legacy 集合，不清 EasyPaisa runtime session / snapshot
- `admin/application/order/auto_payout.py` 用 `scard("payment_active_df")` 统计活跃账号，但这个 key 实际上是 list

### 根因

- `admin` 还没有自己的 EasyPaisa runtime helper
- API / jobs 已经把 EasyPaisa 主状态切到 runtime snapshot，但 admin 展示和重置入口还停在旧 Redis 语义

### 处理

1. 新增：
   - [reader.py](/Users/tear/pk_project/admin/application/easypaisa_runtime/reader.py)
   - [service.py](/Users/tear/pk_project/admin/application/easypaisa_runtime/service.py)
2. `partner.py`：
   - EasyPaisa `online_status` / `online_df` 改读 runtime snapshot
   - 非 EasyPaisa 继续保持 legacy 逻辑
3. `resettingPayment`：
   - 保留原来的 `login_off_realtime_*` 和 legacy 集合清理
   - EasyPaisa 额外补 `force_reset(...)`，同步清 session 和 snapshot 在线态
4. `auto_payout.py`：
   - `online_accounts` 改读 `easypaisa_runtime:index:online`
   - `active_accounts` 改为 list 语义读取

### 验证

```bash
cd /Users/tear/pk_project/admin
python3.12 -m py_compile application/easypaisa_runtime/*.py application/partner/partner.py application/order/auto_payout.py
python3.12 -m unittest discover -s tests -v
```

结果：

- `py_compile`：通过
- `unittest`：`38 tests` 全部通过

### 结论

- EasyPaisa 在 `admin` 里的展示面已经与 runtime snapshot 对齐
- 管理端重置下线不再留下 EasyPaisa runtime 脏会话
- 自动代付监控页不再错误把 `payment_active_df` 当 set 统计
