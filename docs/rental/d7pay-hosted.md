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
- D7pay APK：`apkdownload/public/files/android/d7pay/d7pay_merchant_arm64_v0.1.6_202604292006.apk`
- Jenkins 发布合同：`ops/tenants/d7pay/jenkins.env.example`
- K8s 配置合同：`ops/tenants/d7pay/k8s/`
- 当前部署运维 Runbook：`ops/tenants/d7pay/current-deployment-ops-runbook.md`
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

## App 包名与签名策略

D7pay 必须使用独立 Android package name：`com.d7pay.merchant`。签名不单独生成，继续复用同一份 release keystore；Jenkins 通过 `android/key.properties` 挂载签名配置，Flutter 构建时设置 `ORG_GRADLE_PROJECT_requireReleaseSigning=true`，避免正式包意外回退 debug 签名。

本地没有 `android/key.properties` 时，带 `ORG_GRADLE_PROJECT_requireReleaseSigning=true` 的构建会主动失败，这是正确保护；只有 Jenkins 挂载共享 release 签名后才允许出正式包。

本轮要求 arm64 瘦身包 `d7pay_merchant_arm64_v0.1.6_202604292006.apk` 通过 `aapt dump badging` 验证：

- `package`：`com.d7pay.merchant`
- `versionName`：`0.1.6`
- `versionCode`：`7`
- `application-label`：`D7pay Merchant`

## Jenkins / K8s 发布策略

`api/admin/merchant` 的真实 `config.py` 是运行配置，不提交 Git。D7pay 发布时使用 tracked 的 `config.example.py` 作为模板，实际值由 K8s `d7pay-runtime-config` 和 `d7pay-runtime-secret` 注入。这样 Jenkins 只负责构建镜像、生成 Secret、应用 K8s patch 和等待 rollout，业务运行数据由 `pk-d7pay` namespace 内的 MySQL、Redis、PVC 隔离承载。

2026-04-29 线上检查确认：当前服务器仍只运行原 `pk` 实例，仓库停在旧提交，未创建 `pk-d7pay`，未配置 D7pay 域名，线上 apkdownload 也没有 `d7pay_merchant`。首次上线前运维必须按 `ops/tenants/d7pay/current-deployment-ops-runbook.md` 执行，不能把 D7pay 域名直接指向现有 `pk` NodePort。

发布顺序：

1. Jenkins 加载 `ops/tenants/d7pay/jenkins.env.example` 对应的真实凭据。
2. 调用 `ops/tenants/d7pay/jenkins/deploy-d7pay.sh`，该脚本会按 D7pay mode 改写远端现有 Dockerfile 构建命令。
3. 构建 `api/admin/merchant/admin-h5/merchant-h5/apkdownload` 镜像。
4. 使用 `APP_APPLICATION_ID=com.d7pay.merchant` 和共享 release 签名构建 D7pay APK。
5. 应用 `ops/tenants/d7pay/k8s/namespace.yaml`、`runtime-configmap.yaml`、真实 Secret、`data-volumes.yaml`。
6. 应用 `ops/tenants/d7pay/k8s/h5-configmaps.yaml` 和 `services.yaml`，创建 D7pay 专属 H5 nginx 配置和 NodePort。
7. 对 `api/admin/merchant/apkdownload` 应用 `*-deployment-env.patch.yaml`。
8. 等待所有 deployment rollout 成功，再执行验收。

## 上线前必须完成

1. 为 `admin-d7pay.awekay.com`、`merchant-d7pay.awekay.com`、`api-d7pay.awekay.com`、`apkdownload-d7pay.awekay.com` 配置 DNS 和 nginx。
2. 创建 `pk-d7pay` namespace、独立 MySQL、独立 Redis、独立 fingerprint PVC。
3. 应用 D7pay 专属 Service/NodePort：`31080`、`31081`、`31082`、`31085`，不要复用现有 `pk` 的 `30080-30085`。
4. 使用干净数据初始化 D7pay，不复制真实业务数据。
5. 生成 D7pay admin、merchant、partner 账号和商户密钥。
6. D7pay Merchant APK 已构建并更新 `d7pay_merchant` 下载元信息；正式上线前仍需按目标域名重新确认 API 指向。
7. 按 `ops/tenants/d7pay/acceptance.md` 完成验收。
