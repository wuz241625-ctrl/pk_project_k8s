# D7pay 配置检查与配置修复

## 本地合同检查

```bash
make d7pay-preflight
```

## 发布前配置检查

D7pay 侧不再负责构建镜像、推送镜像、改写打包文件或滚动 deployment。每次发布前建议先做配置检查：

```bash
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## 配置不对时自动改回来

如果 D7pay 的 namespace、ConfigMap、Secret、Service、PVC 被改乱，执行配置应用入口。它只应用配置，不构建、不推送、不滚动业务 deployment：

```bash
make d7pay-apply-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

兼容旧入口也只会应用配置：

```bash
make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## 你的发布脚本负责的构建模式

现有 Dockerfile/发布脚本继续负责应用打包、镜像构建、推送和 rollout。D7pay 只规定这些构建模式：

- `api/admin/merchant`：镜像内运行配置必须来自 `config.example.py` + K8s `d7pay-config` / `d7pay-secret`
- `admin-h5`：使用 `pnpm run d7pay:prod`
- `merchant-h5`：使用 `pnpm run d7pay:prod`
- `apkdownload`：使用 `pnpm run build:d7pay`，并发布 D7pay 专属 `appInfo.d7pay.json`
- Flutter：正式包使用 `com.d7pay.merchant`、`D7pay Merchant`、`@mipmap/ic_launcher_d7pay`、`APP_API_BASE_URL=https://api.d7pay.net`

## Flutter App 发布

Flutter App 不是 K8s deployment。发布 App 的正确链路是：构建正式签名 APK，更新 `apkdownload` 静态制品，提交推送，然后只发布 `apkdownload`。

本地或 Jenkins 需要有 Flutter 工程和正式签名文件：

- `FLUTTER_APP_DIR` 指向 `/Users/tear/pk_project/ashrafi_merchant_flutter` 或 Jenkins 上的 Flutter 工程路径
- `FLUTTER_BIN` 默认 `/Users/tear/sdk/flutter/bin/flutter`
- Flutter 工程内必须存在 `android/key.properties`
- `D7PAY_ENV` 里必须设置 `APP_API_BASE_URL=https://api.d7pay.net`
- `REQUIRE_RELEASE_SIGNING=true`

构建并更新下载页元信息：

```bash
make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env \
  FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter
```

该命令会生成一个同时包含 `armeabi-v7a` 和 `arm64-v8a` 的合并 release APK，并更新：

```text
apkdownload/public/files/android/d7pay/d7pay_merchant_universal_v<version>_<timestamp>.apk
apkdownload/public/files/android/appInfo.d7pay.json
```

确认后提交推送：

```bash
git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/
git commit -m "chore: publish d7pay merchant apk"
git push origin d7pay
```

最后只发布下载页：

```bash
# 由现有发布脚本发布 apkdownload
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

验收 APK：

```bash
aapt dump badging apkdownload/public/files/android/d7pay/<apk-name>.apk | grep -E "package:|application-label|native-code"
apksigner verify --verbose --print-certs apkdownload/public/files/android/d7pay/<apk-name>.apk
curl -k https://apkdownload.d7pay.net/files/android/appInfo.json
curl -k -I https://apkdownload.d7pay.net/files/android/d7pay/<apk-name>.apk
```

期望：

- package 是 `com.d7pay.merchant`
- application-label 是 `D7pay Merchant`
- native-code 同时包含 `armeabi-v7a` 和 `arm64-v8a`
- 签名不是 `CN=Android Debug`
- APK 内置 API 是 `https://api.d7pay.net`

## 生成配置但不发布

```bash
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env D7PAY_RENDER_DIR=/tmp/d7pay-rendered
```

## 回滚

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1
```
