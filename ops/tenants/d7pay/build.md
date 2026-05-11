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

## 线上 Jenkins 发布入口

当前线上发布以宿主机 `/opt/cicd/k8s_d7pay/sh/` 下的 Jenkins 脚本为准，不以本仓库 Makefile 为准：

- `/opt/cicd/k8s_d7pay/sh/deploy-api.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-admin.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-merchant.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-admin-h5.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-merchant-h5.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh`
- `/opt/cicd/k8s_d7pay/sh/check_conf.sh`

业务发布脚本的固定流程是：

1. 进入 `/opt/cicd/k8s_d7pay/pk_project_k8s`。
2. `git fetch --all`。
3. `git reset --hard origin/d7pay`。
4. `git clean -fd`。
5. 复制对应服务目录到 `/opt/cicd/k8s_d7pay/<service>/pk_dockerfile/`。
6. `docker build` 为 `10.170.0.18:30086/lib/<service>-d7pay:<timestamp>`。
7. `docker push`。
8. `sed -i` 更新对应 K8s deployment yaml 的 image。
9. `kubectl apply -f <deployment.yaml>`。
10. `kubectl rollout status deployment/<deployment> -n pk-d7pay --timeout=180s`。

D7pay Makefile 只能用于检查配置、渲染配置、应用公共配置、构建 Flutter APK 本地制品、健康检查和回滚辅助；不要把 `make d7pay-deploy` 当成线上发布。

## 线上构建模式

现有 Dockerfile/Jenkins 脚本继续负责应用打包、镜像构建、推送和 rollout。D7pay 只规定这些构建模式：

- `api/admin/merchant`：镜像内运行配置必须来自 `config.example.py` + K8s 运行时配置；当前线上对象名是 `d7pay-runtime-config` / `d7pay-runtime-secret`
- `api`：当前线上 start 脚本启动 API Web 服务和 Python jobs；Go worker 不属于当前线上发布入口。
- `api`：Go worker 切流版本仍使用线上 `/opt/cicd/k8s_d7pay/api/pk_dockerfile/start.sh` 作为启动文件；Jenkins 用 `ops/tenants/d7pay/runtime/api-start-web-only.sh` 覆盖其内容后，只启动 `main.py` Web 服务，不再启动 Python jobs。
- `pk-go-worker`：从 `/Users/tear/pk-go-worker` 的 `d7pay` 分支构建镜像，发布到 `pk-d7pay` namespace 的四个独立 Deployment。
- `api`：JCB 业务默认 `JAZZCASH_API_VERSION=v1.6`，由 D7pay 运行时 ConfigMap 注入；不要改回代码内硬编码旧版本。
- `admin-h5`：线上 Dockerfile 当前使用 `pnpm d7pay:prod`
- `merchant-h5`：使用 `pnpm run d7pay:prod`
- `apkdownload`：使用 `pnpm run build:d7pay`，并发布 D7pay 专属 `appInfo.d7pay.json`
- Flutter：正式包使用 `com.d7pay.merchant`、`D7pay Merchant`、`@mipmap/ic_launcher_d7pay`、`APP_API_BASE_URL=https://api.d7pay.net`

当前 API 后台任务由 `/opt/cicd/k8s_d7pay/api/pk_dockerfile/start.sh` 拉起，验收命令：

当前脚本应能看到：

- `jobs/easypaisa/auto_payout.py`
- `jobs/jazzcash/jazzcash_auto_payout.py`
- `jobs/jazzcash/jazzcash_monitor.py`
- `jobs/Jazzcashpay_v2.py`
- `jobs/notify_df.py`
- `jobs/notify.py`
- `jobs/time_out.py`
- `jobs/pakistanpay_v2.py`

```bash
kubectl -n pk-d7pay exec deploy/api-deploy -- pgrep -af 'main.py|pakistanpay_v2|Jazzcashpay_v2|auto_payout|jazzcash_auto_payout|notify_df|notify.py|time_out' || true
```

预期：能看到 `main.py` 和上述 Python jobs。不要用“没有 Python jobs”作为当前线上验收标准。

## Go Worker 切流构建

Go worker 是独立服务，不塞进 API 容器。切流时发布顺序：

1. 在 D7pay 数据库执行 `api/sql/20260510_go_worker_phase0_schema.sql`。
2. 已跑过 Phase 0 的环境执行 `api/sql/20260510_go_worker_balance_changed_scan.sql`。
3. 在 `/Users/tear/pk-go-worker` 的 `d7pay` 分支执行 `go test ./...`、`go vet ./...`、`go build ./cmd/worker`。
4. 构建并推送 `10.170.0.18:30086/lib/pk-go-worker-d7pay:<tag>`。
5. 发布 API 前不要改变线上启动路径；只把 `ops/tenants/d7pay/runtime/api-start-web-only.sh` 的内容复制到 `/opt/cicd/k8s_d7pay/api/pk_dockerfile/start.sh`，删除 jobs 启动段。
6. 把 `ops/tenants/d7pay/k8s/go-worker-deployments.yaml` 的 `replace-by-jenkins` 替换为 `<tag>` 并 `kubectl apply`。
7. 等待 `d7pay-go-worker`、`d7pay-go-worker-relay`、`d7pay-go-worker-scheduler`、`d7pay-go-worker-ops` rollout 成功。

切流后验收：

```bash
kubectl -n pk-d7pay exec deploy/api-deploy -- pgrep -af 'pakistanpay_v2|Jazzcashpay_v2|auto_payout|jazzcash_auto_payout|jazzcash_monitor|notify_df|notify.py|time_out' && exit 1 || true
kubectl -n pk-d7pay rollout status deploy/d7pay-go-worker --timeout=180s
kubectl -n pk-d7pay rollout status deploy/d7pay-go-worker-relay --timeout=180s
kubectl -n pk-d7pay rollout status deploy/d7pay-go-worker-scheduler --timeout=180s
kubectl -n pk-d7pay rollout status deploy/d7pay-go-worker-ops --timeout=180s
```

Go worker 时间规则：MySQL 与系统时间保持 UTC；EasyPaisa/JazzCash 上游无时区 `tradeTime/TRX_DTTM` 按 `Asia/Karachi` 解析后转 UTC，RFC3339 带时区值按原时区转 UTC。

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
# 由 Jenkins 执行 /opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh
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
