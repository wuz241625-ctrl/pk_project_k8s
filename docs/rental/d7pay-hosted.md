# D7pay 托管交付说明

## 定位

D7pay 按托管专属实例交付。我们负责代码、部署、运维、备份、升级和故障处理；客户只拿 admin、merchant、App、API 域名和使用账号，不拿源码、服务器、数据库、Redis 或 K8s 权限。

## 已落地配置

- 运维一页 SOP：`ops/tenants/d7pay/README_OPERATIONS.md`
- 运维细节 runbook：`ops/tenants/d7pay/current-deployment-ops-runbook.md`
- 运维一键命令：`make d7pay-preflight`、`make d7pay-render-config`、`make d7pay-deploy`、`make d7pay-healthcheck`、`make d7pay-rollback`
- 租户配置：`ops/tenants/d7pay/tenant.yaml`
- 密钥模板：`ops/tenants/d7pay/secrets.env.example`
- 验收标准：`ops/tenants/d7pay/acceptance.md`
- admin 构建脚本：`npm run d7pay:prod`
- merchant 构建脚本：`npm run d7pay:prod`
- apkdownload 构建脚本：`npm run build:d7pay`
- D7pay 合并 APK：`apkdownload/public/files/android/d7pay/d7pay_merchant_universal_v0.1.8_202605031855.apk`
- Jenkins 发布合同：`ops/tenants/d7pay/jenkins.env.example`
- K8s 配置合同：`ops/tenants/d7pay/k8s/`
- Flutter 展示名构建参数：`APP_DISPLAY_NAME='D7pay Merchant'`、`APP_SHORT_NAME=D7pay`
- D7pay 品牌资产：`ops/tenants/d7pay/assets/`

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

D7pay logo 使用 per-size image_gen 源图集合，Android `192/144/96/72/48`、后台 `128`、下载页 `192`、favicon `256/64/48/32/16` 均有独立源图；生成脚本只做精确导出和 ICO 封装，不从单一主图裁切。D7pay launcher icon 使用独立资源 `@mipmap/ic_launcher_d7pay`，不覆盖默认 Ashrafi `ic_launcher`。admin、merchant、apkdownload 在 D7pay 构建模式下使用 D7pay logo 和 favicon，默认 Ashrafi 构建不受影响。

本地没有 `android/key.properties` 时，带 `ORG_GRADLE_PROJECT_requireReleaseSigning=true` 的构建会主动失败，这是正确保护；只有 Jenkins 挂载共享 release 签名后才允许出正式包。

本轮要求合并包 `d7pay_merchant_universal_v0.1.8_202605031855.apk` 通过 `aapt dump badging` 与 `apksigner verify` 验证：

- `package`：`com.d7pay.merchant`
- `versionName`：`0.1.8`
- `versionCode`：`9`
- `application-label`：`D7pay Merchant`
- `native-code`：同时包含 `armeabi-v7a` 和 `arm64-v8a`
- 签名证书：共享正式 release keystore，不能是 Android Debug。

D7pay 不交付 `app.d7pay.net` H5 入口；客户使用 Android APK，APK 运行时请求 `https://api.d7pay.net`。如果线上曾把 `app.d7pay.net` 指到旧 `app-h5`，必须从 nginx 移除，避免展示 Ashrafi 页面。

## Jenkins / K8s 发布策略

`api/admin/merchant` 的真实 `config.py` 是运行配置，不提交 Git。D7pay 发布时使用 tracked 的 `config.example.py` 作为模板，实际值由 K8s `d7pay-runtime-config` 和 `d7pay-runtime-secret` 注入。这样 Jenkins 只负责构建镜像、生成 Secret、应用 K8s patch 和等待 rollout，业务运行数据由 `pk-d7pay` namespace 内的 MySQL、Redis、PVC 隔离承载。

2026-04-29 线上检查确认：当前服务器仍只运行原 `pk` 实例，仓库停在旧提交，未创建 `pk-d7pay`，未配置 D7pay 域名，线上 apkdownload 也没有 `d7pay_merchant`。首次上线前运维必须先按 `ops/tenants/d7pay/README_OPERATIONS.md` 执行一键命令，遇到细节问题再看 `ops/tenants/d7pay/current-deployment-ops-runbook.md`；不能把 D7pay 域名直接指向现有 `pk` NodePort。

D7pay 不能使用我们的 `awekay.com` 域名。文档和 `jenkins.env.example` 中的 `*.d7pay.example.com` 只是占位，Jenkins 正式发布前必须替换为客户自有域名；`deploy-d7pay.sh` 会拒绝 `example.com` 和 `awekay.com`。

现有 `pk` 部署继续作为当前业务环境保留。D7pay 首次上线是新增 `pk-d7pay` 隔离实例，不替换 `pk`，不复用 `pk` 的 `30080-30085` NodePort，不复用 `pakistan` 数据库，不覆盖现有 nginx server block。

首次全量发布顺序：

1. 运维准备私有 `D7PAY_ENV` 文件，并执行 `make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
2. 执行 `make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env`，生成 nginx 和 runtime ConfigMap 预览。
3. Jenkins 加载 `ops/tenants/d7pay/jenkins.env.example` 对应的真实凭据。
4. 调用 `make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env`，底层执行 `ops/tenants/d7pay/jenkins/deploy-d7pay.sh`。
5. 该脚本会按 D7pay mode 改写远端现有 Dockerfile 构建命令。
6. 构建 `api/admin/merchant/admin-h5/merchant-h5/apkdownload` 镜像。
7. 使用 `APP_APPLICATION_ID=com.d7pay.merchant`、`APP_ICON=@mipmap/ic_launcher_d7pay` 和共享 release 签名构建 D7pay APK。
8. 应用 `ops/tenants/d7pay/k8s/namespace.yaml`、`runtime-configmap.yaml`、真实 Secret、`data-volumes.yaml`。
9. 应用 `ops/tenants/d7pay/k8s/h5-configmaps.yaml` 和 `services.yaml`，创建 D7pay 专属 H5 nginx 配置和 NodePort。
10. 对 `api/admin/merchant/apkdownload` 应用 `*-deployment-env.patch.yaml`。
11. 等待所有 deployment rollout 成功，再执行 `make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。

维护期发布顺序：

1. 只改后端 API 时执行 `make d7pay-deploy-api D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
2. 只改 admin 后端时执行 `make d7pay-deploy-admin D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
3. 只改 merchant 后端时执行 `make d7pay-deploy-merchant D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
4. 只改 admin 前端时执行 `make d7pay-deploy-admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
5. 只改 merchant 前端时执行 `make d7pay-deploy-merchant-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
6. 只改下载页或 APK 元信息时执行 `make d7pay-deploy-apkdownload D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
7. Jenkins 参数化发布使用 `make d7pay-deploy-service SERVICE=api D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。

维护期单服务发布仍会同步代码、检查合同并 apply 公共租户资源，但只构建和 rollout 指定 deployment，避免无关服务被滚动。

## 上线前必须完成

1. 为 D7pay 客户自有的 admin、merchant、api、apkdownload 域名配置 DNS 和 nginx；`*.d7pay.example.com` 只是文档占位。
2. 创建 `pk-d7pay` namespace、独立 MySQL、独立 Redis、独立 fingerprint PVC。
3. 应用 D7pay 专属 Service/NodePort：`31080`、`31081`、`31082`、`31085`，不要复用现有 `pk` 的 `30080-30085`。
4. 使用干净数据初始化 D7pay，不复制真实业务数据。
5. 生成 D7pay admin、merchant、partner 账号和商户密钥。
6. D7pay Merchant APK 已构建并更新 `d7pay_merchant` 下载元信息；正式上线前仍需按目标域名重新确认 API 指向。
7. 按 `ops/tenants/d7pay/acceptance.md` 完成验收。
