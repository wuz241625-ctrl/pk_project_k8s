# D7pay 托管交付说明

## 定位

D7pay 按托管专属实例交付。我们负责代码、部署、运维、备份、升级和故障处理；客户只拿 admin、merchant、App、API 域名和使用账号，不拿源码、服务器、数据库、Redis 或 K8s 权限。

## 已落地配置

- 租户配置：`ops/tenants/d7pay/tenant.yaml`
- 密钥模板：`ops/tenants/d7pay/secrets.env.example`
- 验收标准：`ops/tenants/d7pay/acceptance.md`
- admin 构建脚本：`npm run d7pay:prod`
- merchant 构建脚本：`npm run d7pay:prod`
- apkdownload 构建脚本：`npm run build:d7pay`
- D7pay APK：`apkdownload/public/files/android/d7pay/d7pay_merchant_arm64_v0.1.6_202604291945.apk`
- Flutter 展示名构建参数：`APP_DISPLAY_NAME='D7pay Merchant'`、`APP_SHORT_NAME=D7pay`

## 交付边界

客户可以使用：

- D7pay admin 后台
- D7pay merchant 后台
- D7pay Merchant App
- D7pay API 下单和回调
- 自己租户内的订单、码商、商户、收款资料和账务流水

客户不能获取：

- 源码仓库
- SSH
- K8s kubeconfig
- MySQL 直连
- Redis 直连
- Docker registry
- 我们的超管账号
- 我们的真实商户密钥、订单、指纹和码商数据

## App 包名策略

D7pay 当前只改展示名，不改 Android package name。包名继续是 `com.ashrafi.pay`，因为 Veridium/4F 授权链路与包名和签名强相关。只有拿到 D7pay 独立授权后，才允许改为独立 package。

本轮已构建 arm64 瘦身包 `d7pay_merchant_arm64_v0.1.6_202604291945.apk`，并通过 `aapt dump badging` 验证：

- `package`：`com.ashrafi.pay`
- `versionName`：`0.1.6`
- `versionCode`：`7`
- `application-label`：`D7pay Merchant`

## 上线前必须完成

1. 为 `admin-d7pay.awekay.com`、`merchant-d7pay.awekay.com`、`api-d7pay.awekay.com`、`apkdownload-d7pay.awekay.com` 配置 DNS 和 nginx。
2. 创建 `pk-d7pay` namespace、独立 MySQL、独立 Redis、独立 fingerprint PVC。
3. 使用干净数据初始化 D7pay，不复制真实业务数据。
4. 生成 D7pay admin、merchant、partner 账号和商户密钥。
5. D7pay Merchant APK 已构建并更新 `d7pay_merchant` 下载元信息；正式上线前仍需按目标域名重新确认 API 指向。
6. 按 `ops/tenants/d7pay/acceptance.md` 完成验收。
