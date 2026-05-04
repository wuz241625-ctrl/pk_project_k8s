# D7pay 运维构建与发布

## 本地合同检查

```bash
make d7pay-preflight
```

## 首次全量发布

首次上线或租户整体版本发布使用全量入口，会构建并滚动 `api/admin/merchant/admin-h5/merchant-h5/apkdownload`：

```bash
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## 维护期单服务发布

上线后只改哪个服务就发布哪个服务；脚本仍会同步代码、检查合同并 apply 公共租户资源，但只构建和 rollout 指定 deployment：

```bash
make d7pay-deploy-api D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-admin D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-merchant D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-merchant-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-apkdownload D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

Jenkins 参数化维护入口：

```bash
make d7pay-deploy-service SERVICE=admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

底层也支持一次发布多个明确目标：

```bash
D7PAY_DEPLOY_TARGETS=api,admin-h5 bash ops/tenants/d7pay/jenkins/deploy-d7pay.sh
```

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
make d7pay-deploy-apkdownload D7PAY_ENV=/opt/cicd/secrets/d7pay.env
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
