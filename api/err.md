# API 排错记录

## 0.1 不允许恢复 运行时 模块

现象：

- `api/application/easypaisa_运行时` 或 `api/application/jazzcash_运行时` 再次出现。
- 登录、派单、监控脚本重新 import 运行时 reader/service。
- D7pay K8s 配置重新使用 `旧运行配置` 命名。

处理：

- 删除 运行时 模块、脚本、SQL、测试和旧设计文档。
- EasyPaisa 代收派单读取 MySQL `collection_status`。
- EasyPaisa 代付派单读取 MySQL `payout_status`。
- JazzCashBusiness 使用当前业务主线，不写 运行时 session/snapshot/index。
- D7pay K8s 环境注入统一命名为 `d7pay-config` / `d7pay-secret`。

验证：

```bash
rg "旧服务类|旧读取类" api --glob '!*.md'
PYTHONPATH=api python3 -m py_compile main.py router_lakshmi.py application/pay/pay.py application/app/login/banks/easypaisa.py application/app/login/banks/jazzcash.py
```

## 0.2 业务同步时不能把运行层带回

现象：

- 从 `/Users/tear/pk_project` 同步业务后，重新出现旧英文运行层 key、旧读取类或旧服务类。
- JCB v1.6 代码缺少 `application/jazzcash_gateway.py`，导致 `from application.jazzcash_gateway import ...` 失败。
- PayFast 代收跳转已合入，但 `thirdPart.py` 没有 `payfast_payment`。

处理：

- JCB/PayFast/Lakshmi API 业务可以参考 `/Users/tear/pk_project`。
- EasyPaisa 与 Admin 收款资料列表只保留 MySQL 最终状态和旧 Redis 投影清理，不恢复运行层 key。
- D7pay API 配置必须保留 `JAZZCASH_API_VERSION=v1.6`，默认值在 `api/config.example.py`。

验证：

```bash
rg "旧服务类|旧读取类" api --glob '!*.md'
PYTHONPATH=api python3 -m py_compile application/jazzcash_gateway.py application/app/login/banks/jazzcash.py application/pay/order.py application/pay/thirdPart.py jobs/jazzcash/jazzcash_auto_payout.py
```

## 0.3 明确垃圾制品不能回流

现象：

- 仓库重新出现 `api/jobs/freecharge-monitor/php`、`api/jobs/easypaisa/auto_payout.py.bak`、`api/docker-compose.yml`、`api/docker` 或 `api/static/v2`。
- 仓库重新出现 D7pay 已清理的旧银行实现：`gcash_bank.py`、`indus_bank.py`、`api/jobs/induspay`、`api/jobs/jio`、`api/jobs/maha`。
- D7pay 下载站重新提交 `apkdownload/public/files/android/lakshmi/*.apk` 或 `apkdownload/public/files/android/ashrafi/*.apk`。

处理：

- PHP 依赖应由对应旧项目自行安装，不提交 vendor 目录到 D7pay 分支。
- Freecharge PHP、GCash、Indus、Jio、Maha 旧入口不属于 D7pay 当前运行链路，不重新提交。
- 备份文件不进入 Git，需要保留历史时使用 Git commit。
- D7pay APK 下载页只保留 D7pay 发布项，不携带 Ashrafi/Lakshmi 旧客户 APK。
- 当前线上发布只走 Jenkins/K8s，不恢复 API 本地 compose。

验证：

```bash
test "$(git ls-files api/jobs/freecharge-monitor/php | wc -l | tr -d ' ')" = "0"
test "$(git ls-files api/static/v2 | wc -l | tr -d ' ')" = "0"
test -z "$(git ls-files api/jobs/easypaisa/auto_payout.py.bak api/docker-compose.yml api/docker api/application/app/login/banks/gcash_bank.py api/application/app/login/banks/indus_bank.py api/jobs/induspay api/jobs/jio api/jobs/maha merchant/.config.py.swp apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk)"
```

## 0.4 旧印度钱包和 PhonePe 残留不能回流

现象：

- `api/application/lakshmi_api/services/payment_services.py` 再次注册 `FREECHARGE`、`PHONEPE`、`MOBIKWIK`、`AIRTEL`、`AMAZON`、`INDUS`、`ULCASH`、`JIO` 或 `MAHA`。
- `api/main.py` 再次启动 `application.phonepe.redissub` 后台线程。
- `api/router.py` 再次暴露 `/phonepe/ws` 或 `/phonepe/api/*`。
- `api/router_lakshmi.py` 再次暴露 Indus/Amazon 专用的 `pin_pre_sign_in`、`cookie` 或 `grabOTP` 路由。
- 仓库重新出现旧 Redis 维护脚本：`check_proxy.py`、`clear_redis_dsdf.py`、`clear_redis_inactive_payment.py`、`collect_partner_status.py`、`order_push.py`、`weight.py`。

处理：

- 参考 `/Users/tear/pk_project` 当前文件，Lakshmi API 只注册 `EASYPAISA` 与 `JAZZCASH`。
- API 启动不再创建 PhonePe 订阅线程。
- 删除旧 PhonePe websocket/http 路由和旧印度钱包专用 App 路由。
- 代收派单以 MySQL `collection_status` 为候选真相源，不回退到旧 `payment_active_*`。

验证：

```bash
rg "application\\.phonepe|PhonepeService|FreechargeService|IndusPayService|MahaService|MobikwikService|AirtelService|AmazonService|UlCashPayService|JioService|/phonepe|PaymentPINPreSignIn|StoreCookie|GrabOTP" api --glob '!*.md'
test -z "$(git ls-files api/application/phonepe api/jobs/check_proxy.py api/jobs/clear_redis_dsdf.py api/jobs/clear_redis_inactive_payment.py api/jobs/collect_partner_status.py api/jobs/order_push.py api/jobs/weight.py api/static/images/india_transaction/PhonePe.svg)"
```
