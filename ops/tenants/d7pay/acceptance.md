# D7pay 托管实例验收标准

## 品牌验收

- admin 构建使用 `npm run d7pay:prod`，浏览器标题包含 `D7pay管理系统`。
- merchant 构建使用 `npm run d7pay:prod`，登录页展示 `D7pay`。
- apkdownload 构建使用 `npm run build:d7pay`，页面读取 `d7pay_merchant` 元信息并指向 `d7pay_merchant_arm64_v0.1.6_202604291945.apk`。
- Flutter 构建使用 `APP_DISPLAY_NAME='D7pay Merchant'` 和 `APP_SHORT_NAME=D7pay`，Android 桌面名称为 `D7pay Merchant`。
- Android package 暂时保持 `com.ashrafi.pay`，原因是 Veridium/4F 授权与包名绑定。

## 本轮验证记录

- `admin-h5` 使用 `NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod` 构建通过，产物标题包含 `D7pay管理系统`。
- `merchant-h5` 使用 `NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod` 构建通过，产物标题包含 `D7payMerchant`。
- `apkdownload` 使用 `npm run build:d7pay` 构建通过，产物包含 `/files/android/d7pay/d7pay_merchant_arm64_v0.1.6_202604291945.apk`。
- Flutter 使用 D7pay 构建参数构建 arm64 release APK 通过，`aapt dump badging` 验证 `application-label` 为 `D7pay Merchant`，`package` 为 `com.ashrafi.pay`。
- Flutter `flutter test test/login_page_test.dart test/payments_controller_test.dart` 通过。
- Flutter `flutter analyze lib/app/brand.dart lib/app/app.dart lib/features/login/presentation/login_page.dart lib/features/payments/presentation/home_page.dart` 通过。

## 隔离验收

- K8s namespace 使用 `pk-d7pay`。
- MySQL database 使用 `pakistan_d7pay`。
- Redis 使用独立实例 `redis-d7pay`。
- 指纹目录使用 `/fingerprint/d7pay`。
- APK 下载目录使用 `/apkdownload/d7pay`。
- 客户不拿 SSH、K8s、MySQL、Redis、源码仓库权限。

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
