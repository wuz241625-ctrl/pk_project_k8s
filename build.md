# 项目构建入口

本仓库包含后端、后台前端、商户前端、下载页和租户运维配置。各子项目仍按自己的构建命令执行；D7pay 托管租户的运维入口统一走根目录 Makefile。

## D7pay 运维构建与发布

首次上线或租户整体版本发布使用全量入口：

```bash
make d7pay-preflight
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

上线后的日常维护使用单服务入口，避免无关服务滚动：

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
make d7pay-deploy-service SERVICE=api D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

Flutter App 发布不是单独的 K8s deployment，而是先生成 apkdownload 静态制品，再发布 `apkdownload`：

```bash
make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env \
  FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter
git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/
git commit -m "chore: publish d7pay merchant apk"
git push origin d7pay
make d7pay-deploy-apkdownload D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

D7pay 详细说明见 `ops/tenants/d7pay/build.md` 和 `ops/tenants/d7pay/README_OPERATIONS.md`。

## 常用子项目命令

```bash
cd admin-h5 && NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod
cd merchant-h5 && NODE_OPTIONS=--openssl-legacy-provider npm run d7pay:prod
cd apkdownload && npm run build:d7pay
python3 ops/tenants/d7pay/verify_release_contract.py
```
