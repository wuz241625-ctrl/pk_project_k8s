# D7pay 托管交付说明

## 定位

D7pay 按托管专属实例交付。我们负责代码、部署、运维、备份、升级和故障处理；客户只拿 admin、merchant、App、API 域名和使用账号，不拿源码、服务器、数据库、Redis 或 K8s 权限。

## 已落地配置

- 运维一页 SOP：`ops/tenants/d7pay/README_OPERATIONS.md`
- 运维细节 runbook：`ops/tenants/d7pay/current-deployment-ops-runbook.md`
- 运维一键命令：`make d7pay-preflight`、`make d7pay-render-config`、`make d7pay-apply-config`、`make d7pay-healthcheck`、`make d7pay-rollback`
- 租户配置：`ops/tenants/d7pay/tenant.yaml`
- 密钥模板：`ops/tenants/d7pay/secrets.env.example`
- 验收标准：`ops/tenants/d7pay/acceptance.md`
- admin 构建脚本：由现有发布脚本执行 `pnpm run d7pay:prod`
- merchant 构建脚本：由现有发布脚本执行 `pnpm run d7pay:prod`
- apkdownload 构建脚本：由现有发布脚本执行 `pnpm run build:d7pay`
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

D7pay 不交付 `app.d7pay.net` H5 入口；客户使用 Android APK，APK 运行时请求 `https://api.d7pay.net`。如果线上曾把 `app.d7pay.net` 指到旧 `旧移动 H5`，必须从 nginx 移除，避免展示 Ashrafi 页面。

## Jenkins / K8s 发布策略

`api/admin/merchant` 的真实 `config.py` 是运行配置，不提交 Git。D7pay 运行时使用 tracked 的 `config.example.py` 作为模板，实际值由 K8s `d7pay-config` 和 `d7pay-secret` 注入。现有发布脚本负责构建镜像、推送镜像和等待 rollout；D7pay 运维脚本只负责检查并应用公共配置。业务运行数据由 `pk-d7pay` namespace 内的 MySQL、Redis、PVC 隔离承载。

2026-05-11 线上检查确认：当前 D7pay 已按 `/opt/cicd/k8s_d7pay` 目录独立发布，Jenkins 入口脚本在 `/opt/cicd/k8s_d7pay/sh/`。本仓库 Makefile 只做配置检查、配置渲染、配置应用、Flutter APK 本地制品和健康检查，不直接替代 Jenkins 发布业务服务。API 当前仍由容器 start 脚本启动 Web 服务和 Python jobs；Go worker 不属于当前线上发布入口。

Go worker 切流后，D7pay 的后台任务不再跟随 API 容器启动，而是在 `pk-d7pay` namespace 单独部署四个 Deployment：`d7pay-go-worker`、`d7pay-go-worker-relay`、`d7pay-go-worker-scheduler`、`d7pay-go-worker-ops`。API 使用 Web-only start 模板，只保留商户下单、后台、状态查询等 HTTP 入口；Python jobs 退役。Go worker 的 `tradeTime/TRX_DTTM` 按巴基斯坦时间解释并转 UTC，系统、MySQL、Redis 仍保持 UTC。

线上业务发布脚本：

- `/opt/cicd/k8s_d7pay/sh/deploy-api.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-admin.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-merchant.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-admin-h5.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-merchant-h5.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh`

运维必须先按 `ops/tenants/d7pay/README_OPERATIONS.md` 检查并应用 D7pay 公共配置，遇到细节问题再看 `ops/tenants/d7pay/current-deployment-ops-runbook.md`；不能把 D7pay 域名直接指向现有 `pk` NodePort。

D7pay 不能使用我们的 `awekay.com` 域名。文档和 `jenkins.env.example` 中的 `*.d7pay.example.com` 只是占位，Jenkins 正式发布前必须替换为客户自有域名；D7pay 配置检查脚本会拒绝 `example.com` 和 `awekay.com`。

现有 `pk` 部署继续作为当前业务环境保留。D7pay 首次上线是新增 `pk-d7pay` 隔离实例，不替换 `pk`，不复用 `pk` 的 `30080-30085` NodePort，不复用 `pakistan` 数据库，不覆盖现有 nginx server block。

配置检查与发布职责边界：

1. 运维准备私有 `D7PAY_ENV` 文件，并执行 `make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。
2. 执行 `make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env`，生成 nginx 和 应用 ConfigMap 预览。
3. 执行 `make d7pay-apply-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env`，应用 namespace、应用 ConfigMap、真实 Secret、H5 nginx ConfigMap、Service 和 PVC。
4. Jenkins 执行 `/opt/cicd/k8s_d7pay/sh/deploy-*.sh`，负责构建 `api/admin/merchant/admin-h5/merchant-h5/apkdownload` 镜像、推送镜像并滚动 deployment。
5. D7pay 运维脚本不改写打包文件，不执行 Docker 构建，不更新 deployment 镜像。
6. 发布完成后执行 `make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env`。

Flutter App 发布顺序：

1. 在 Jenkins 或构建机准备 Flutter 工程 `/Users/tear/pk_project/ashrafi_merchant_flutter`，并挂载正式 `android/key.properties`。
2. 确认 `/opt/cicd/secrets/d7pay.env` 里 `APP_API_BASE_URL=https://api.d7pay.net`、`APP_APPLICATION_ID=com.d7pay.merchant`、`APP_ICON=@mipmap/ic_launcher_d7pay`、`REQUIRE_RELEASE_SIGNING=true`。
3. 执行 `make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter`。
4. 提交并推送生成的 `apkdownload/public/files/android/appInfo.d7pay.json` 和 `apkdownload/public/files/android/d7pay/<apk-name>.apk`。
5. 由现有发布脚本发布 `apkdownload`。
6. 用 `aapt dump badging`、`apksigner verify` 和 `curl` 验证包名、展示名、正式签名、ARM/ARM64 合并包和下载链接。

## 上线前必须完成

1. 为 D7pay 客户自有的 admin、merchant、api、apkdownload 域名配置 DNS 和 nginx；`*.d7pay.example.com` 只是文档占位。
2. 创建 `pk-d7pay` namespace、独立 MySQL、独立 Redis、独立 fingerprint PVC。
3. 应用 D7pay 专属 Service/NodePort：`31080`、`31081`、`31082`、`31085`，不要复用现有 `pk` 的 `30080-30085`。
4. 使用干净数据初始化 D7pay，不复制真实业务数据。
5. 生成 D7pay admin、merchant、partner 账号和商户密钥。
6. D7pay Merchant APK 已构建并更新 `d7pay_merchant` 下载元信息；正式上线前仍需按目标域名重新确认 API 指向。
7. 按 `ops/tenants/d7pay/acceptance.md` 完成验收。
