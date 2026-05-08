# 项目构建入口

本仓库包含后端、后台前端、商户前端、下载页和租户运维配置。各子项目仍按自己的构建命令执行；D7pay 托管租户的运维入口统一走根目录 Makefile。

## D7pay 配置检查与配置修复

D7pay 侧不再负责应用镜像构建、推送或滚动发布；这些工作走现有发布脚本。每次发布前可先执行配置检查和配置应用，防止域名、namespace、ConfigMap、Secret、PVC 漂移：

```bash
make d7pay-preflight
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-apply-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

应用构建和滚动发布由现有脚本处理，D7pay 不改写打包文件。各应用应该使用的 D7pay 构建模式是：

```bash
admin-h5: pnpm run d7pay:prod
merchant-h5: pnpm run d7pay:prod
apkdownload: pnpm run build:d7pay
Flutter: 使用 com.d7pay.merchant、D7pay Merchant、@mipmap/ic_launcher_d7pay、APP_API_BASE_URL=https://api.d7pay.net
```

Flutter App 发布不是单独的 K8s deployment，而是先生成 apkdownload 静态制品，再发布 `apkdownload`：

```bash
make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env \
  FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter
git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/
git commit -m "chore: publish d7pay merchant apk"
git push origin d7pay
# 后续由现有发布脚本发布 apkdownload
```

D7pay 详细说明见 `ops/tenants/d7pay/build.md` 和 `ops/tenants/d7pay/README_OPERATIONS.md`。

## 常用子项目命令

```bash
cd admin-h5 && NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod
cd merchant-h5 && NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod
cd apkdownload && npm run build:d7pay
python3 ops/tenants/d7pay/verify_release_contract.py
```

## D7pay 时区验收

业务存储保持 UTC，展示和默认查询日界使用巴基斯坦时间转换。发布前可执行：

```bash
PYTHONPATH=api python3 -m unittest api.tests.test_timezone_policy
PYTHONPATH=admin python3 -m unittest admin.tests.test_timezone_policy admin.tests.test_order_ds_default_filter
PYTHONPATH=merchant python3 -m unittest merchant.tests.test_timezone_policy
rg -n "Asia/Shanghai|datetime\\.today\\(\\)\\.date\\(\\)" api admin merchant -g '*.py'
```
