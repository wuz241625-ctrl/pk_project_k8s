# Ashrafi APK 发布与部署验收设计

## 目标

将 Ashrafi Flutter 商户端按当前系统域名构建为生产 release APK，发布到 `apkdownload` 服务，并确认 API 指纹目录已经使用 Kubernetes 持久化卷挂载。

## 范围

- 后端 API 使用线上 `main` 最新提交部署，运行环境必须是 `PROD`。
- 指纹存储以 `api-fingerprint-pvc` 作为唯一持久化入口，容器路径为 `/app/api/application/app/login/banks/fingerprint`。
- APK 使用 `API_BASE_URL=http://api.awekay.com` 构建，发布路径为 `/files/android/ashrafi/ashrafi_v0.1.6_202604261714.apk`。
- `apkdownload` 页面配置继续兼容现有 `lakshmi` 配置键，但实际指向 Ashrafi 文件和元信息。
- 交付账号以线上数据库当前演示数据为准，密码统一为 `123456`，管理员和商户使用同一演示 TOTP secret。

## 方案

采用“制品入库 + 镜像发布”的方式发布 APK：本地 Flutter 构建产物复制到 `apkdownload/public/files/android/ashrafi/`，更新 `appInfo.json` 后提交推送；服务器部署脚本从 `origin/main` 拉取制品并构建 `apkdownload` 镜像。这样线上镜像内容、Git 记录、下载链接三者一致。

## 验收标准

- `api-deploy` rollout 成功，镜像为本次部署镜像，容器环境变量 `RUN_ENV=PROD`。
- `api-fingerprint-pvc` 和 `api-fingerprint-pv` 为 `Bound`，`api-deploy` 挂载了 `fingerprint-storage`。
- API 容器内 `/app/api/application/app/login/banks/fingerprint` 可访问，并对应宿主机 `/data/pk/api/fingerprint`。
- Flutter APK 构建命令退出码为 0，APK 包含 `arm64-v8a` 和 `armeabi-v7a` 两个 ABI。
- `apkdownload-deploy` rollout 成功，下载链接 HTTP 200，`Content-Length` 与发布 APK 大小一致。
- 线上库可查到 admin、merchant、partner/app 演示账号，状态为启用。

## 回滚

回滚 APK 时恢复 `apkdownload/public/files/android/appInfo.json` 的上一版路径并重新部署 `apkdownload`。回滚 API 时使用 Kubernetes deployment 的上一版 ReplicaSet 或重新应用上一版镜像 YAML。
