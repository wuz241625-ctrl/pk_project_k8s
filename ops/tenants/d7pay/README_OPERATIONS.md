# D7pay 运维一页 SOP

这份是运维唯一入口。长 runbook 只在排障或核对细节时查看：`ops/tenants/d7pay/current-deployment-ops-runbook.md`。

## 不能做的事

- 不能把 D7pay 指到 `awekay.com`。
- 不能复用现有 `pk` namespace、`30080-30085` NodePort、`pakistan` 数据库、真实商户、真实码商、真实订单或真实指纹。
- 不能把真实密钥写进 Git、文档、截图或群聊。

## 准备一次

在服务器准备私有环境变量文件，路径示例：

```bash
cp /opt/cicd/k8s/pk_project_k8s/ops/tenants/d7pay/jenkins.env.example /opt/cicd/secrets/d7pay.env
chmod 600 /opt/cicd/secrets/d7pay.env
```

把 `/opt/cicd/secrets/d7pay.env` 里的 `*.d7pay.example.com` 改成客户自有域名，并确认：

- `KUBE_NAMESPACE=pk-d7pay`
- `RUN_ENV=PROD`
- `D7PAY_GIT_BRANCH=d7pay`
- `API_DOMAIN`、`ADMIN_DOMAIN`、`MERCHANT_DOMAIN`、`APKDOWNLOAD_DOMAIN` 都是客户域名
- `D7PAY_RUNTIME_SECRET_YAML` 指向真实 Secret YAML

`D7PAY_ENV` 不执行 shell 变量展开，不能写 `${API_DOMAIN}`；所有 URL 都要写完整值。

## 发布前检查配置

```bash
cd /opt/cicd/k8s/pk_project_k8s
git status --short
git checkout d7pay
git pull --ff-only origin d7pay
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

D7pay 侧只负责配置检查、配置渲染、配置应用和健康检查。应用打包、镜像构建、推送和 rollout 继续走现有发布脚本，不走 D7pay Makefile。

`make d7pay-render-config` 会生成：

- `/tmp/d7pay-rendered/runtime-configmap.yaml`
- `/tmp/d7pay-rendered/nginx-d7pay.conf`
- `/tmp/d7pay-rendered/env-summary.txt`

## 配置不对时自动改回来

如果 D7pay 的 K8s 公共配置被改乱，执行：

```bash
make d7pay-apply-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

它只会应用 namespace、runtime ConfigMap、H5 nginx ConfigMap、Service、真实 Secret 和 PVC，不会构建镜像、不会推送镜像、不会改写打包文件、不会滚动业务 deployment。

旧的 `make d7pay-deploy` 现在只是兼容入口，也只会应用配置。服务发布请继续走现有发布脚本。

## Flutter App 发布

App 发布不走 `d7pay-deploy` 全量入口。App 是 `apkdownload` 的静态制品，流程是先构建 APK，再只发布 `apkdownload`：

```bash
make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env \
  FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter
git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/
git commit -m "chore: publish d7pay merchant apk"
git push origin d7pay
# 后续由现有发布脚本发布 apkdownload
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

正式发布前必须确认 Flutter 工程存在 `android/key.properties`，并且 `D7PAY_ENV` 里 `REQUIRE_RELEASE_SIGNING=true`、`APP_API_BASE_URL=https://api.d7pay.net`。不能用 debug 签名包交付客户。

nginx 配置上线前先执行：

```bash
nginx -t
systemctl reload nginx
```

## 验收

- `pk` namespace 仍在运行，`awekay.com` 仍指向原业务。
- `pk-d7pay` namespace 存在，`api/admin/merchant/admin-h5/merchant-h5/apkdownload` rollout 成功。
- admin、merchant、apkdownload、api 四个客户域名都能访问。
- admin、merchant、App 展示 D7pay 品牌。
- API、数据库、Redis、指纹目录和 APK 目录都只属于 D7pay。

## 回滚

优先只回滚 D7pay，不动现有 `pk`：

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1
```

需要临时停用 D7pay：

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1 D7PAY_ROLLBACK_MODE=scale-zero
```

常见错误看 `ops/tenants/d7pay/err.md`。
