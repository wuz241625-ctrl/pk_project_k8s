# D7pay 托管实例验收标准

## 品牌验收

- admin 构建使用 `npm run d7pay:prod`，浏览器标题包含 `D7pay管理系统`。
- merchant 构建使用 `npm run d7pay:prod`，登录页展示 `D7pay`。
- apkdownload 构建使用 `npm run build:d7pay`，页面读取 `d7pay_merchant` 元信息并指向 `d7pay_merchant_arm64_v0.1.6_202604292006.apk`。
- Flutter 构建使用 `APP_DISPLAY_NAME='D7pay Merchant'` 和 `APP_SHORT_NAME=D7pay`，Android 桌面名称为 `D7pay Merchant`。
- Android package 必须为 `com.d7pay.merchant`。
- D7pay 与 Ashrafi 共用同一份 release 签名配置入口，Jenkins 必须挂载 `android/key.properties` 并设置 `REQUIRE_RELEASE_SIGNING=true`。

## 本轮验证记录

- `admin-h5` 使用 `NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod` 构建通过，产物标题包含 `D7pay管理系统`。
- `merchant-h5` 使用 `NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod` 构建通过，产物标题包含 `D7payMerchant`。
- `apkdownload` 使用 `npm run build:d7pay` 构建通过，产物包含 `/files/android/d7pay/d7pay_merchant_arm64_v0.1.6_202604292006.apk`。
- Flutter 使用 D7pay 构建参数构建 arm64 release APK 通过，`aapt dump badging` 验证 `application-label` 为 `D7pay Merchant`，`package` 为 `com.d7pay.merchant`。
- Flutter `flutter test test/login_page_test.dart test/payments_controller_test.dart` 通过。
- Flutter `flutter analyze lib/app/brand.dart lib/app/app.dart lib/features/login/presentation/login_page.dart lib/features/payments/presentation/home_page.dart` 通过。
- 本地无 `android/key.properties` 时，带 `ORG_GRADLE_PROJECT_requireReleaseSigning=true` 的 release 构建必须失败并提示缺少签名文件，证明 Jenkins 正式包不会静默回退 debug 签名。

## 隔离验收

- K8s namespace 使用 `pk-d7pay`。
- MySQL database 使用 `pakistan_d7pay`。
- Redis 使用独立实例 `redis-d7pay`。
- API 容器内指纹目录使用唯一真相源 `/fingerprint`，宿主机目录使用 `/data/pk-d7pay/fingerprint`。
- APK 下载目录宿主机使用 `/data/pk-d7pay/apkdownload/d7pay`，容器挂载到 `/usr/share/nginx/html/files/android/d7pay`。
- 客户不拿 SSH、K8s、MySQL、Redis、源码仓库权限。

## Jenkins / K8s 验收

- Jenkins 使用 `ops/tenants/d7pay/jenkins.env.example` 中的变量合同发布。
- Jenkins 调用 `ops/tenants/d7pay/jenkins/deploy-d7pay.sh`，不能直接复用硬编码 `pk` namespace 和默认 `build:prod` 的旧脚本。
- Jenkins 必须设置 `RUN_ENV=PROD`，不能让 api/admin/merchant 回落到 DEV。
- Jenkins 构建 D7pay App 时必须设置 `ORG_GRADLE_PROJECT_appApplicationId=com.d7pay.merchant`。
- Jenkins 构建 release App 时必须设置 `ORG_GRADLE_PROJECT_requireReleaseSigning=true`。
- K8s 应先应用 `namespace.yaml`、`runtime-configmap.yaml`、真实 Secret、`data-volumes.yaml`。
- K8s 应应用 `h5-configmaps.yaml`，确保 `admin-h5-nginx-conf`、`merchant-h5-nginx-conf`、`download-nginx-conf` 存在于 `pk-d7pay`。
- K8s 应应用 `services.yaml`，确保 `api/admin/merchant` 内部服务和 D7pay 专属 NodePort 存在。
- D7pay NodePort 必须为 `apkdownload:31080`、`admin-h5:31081`、`merchant-h5:31082`、`api-public:31085`，不能复用 `pk` 的 `30080-30085`。
- K8s 应对 `api/admin/merchant/apkdownload` 应用对应 patch，并完成 rollout。
- `python3 ops/tenants/d7pay/verify_release_contract.py` 必须通过。
- 首次部署前必须按 `ops/tenants/d7pay/current-deployment-ops-runbook.md` 检查当前线上状态、备份、配置 DNS/nginx 和验证 rollout。

## 数据验收

- 不复制我们的真实商户、真实码商、真实订单、真实指纹。
- 商户 `mc_key` 重新生成。
- admin、merchant、partner 初始密码重新生成。
- 所有余额调整通过后台接口或服务方法产生 `balance_record`。
- 当前余额等于初始余额加流水汇总。

## 业务验收

- admin 可登录并只看到 D7pay 数据。
- merchant 可登录并只看到 D7pay 数据。
- App 可登录并请求 D7pay API。
- 1001 EasyPaisa 测试拉单成功。
- 1003 JazzCashBusiness 测试拉单成功。
- 订单能绑定正确商户、码商、收款资料，并产生正确余额流水。

## 运维验收

- 可一键备份 MySQL。
- 可一键恢复 MySQL 到验收前备份。
- 可一键重启 api/admin/merchant/apkdownload。
- 可一键停用 D7pay 实例。
- nginx 白名单对 admin 和 merchant 生效。
- D7pay 客户自有的 admin、merchant、api、apkdownload 域名均解析并代理到 D7pay 专属 NodePort；`*.d7pay.example.com` 只能作为占位，不能作为正式发布域名。
