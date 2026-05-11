# D7pay 运维一页 SOP

这份是运维唯一入口。长 runbook 只在排障或核对细节时查看：`ops/tenants/d7pay/current-deployment-ops-runbook.md`。

## 不能做的事

- 不能把 D7pay 指到 `awekay.com`。
- 不能复用现有 `pk` namespace、`30080-30085` NodePort、`pakistan` 数据库、真实商户、真实码商、真实订单或真实指纹。
- 不能把真实密钥写进 Git、文档、截图或群聊。

## 准备一次

在服务器准备私有环境变量文件，路径示例：

```bash
cp /opt/cicd/k8s_d7pay/pk_project_k8s/ops/tenants/d7pay/jenkins.env.example /opt/cicd/secrets/d7pay.env
chmod 600 /opt/cicd/secrets/d7pay.env
```

把 `/opt/cicd/secrets/d7pay.env` 里的 `*.d7pay.example.com` 改成客户自有域名，并确认：

- `KUBE_NAMESPACE=pk-d7pay`
- `RUN_ENV=PROD`
- `PROJECT_DIR=/opt/cicd/k8s_d7pay/pk_project_k8s`
- `BUSINESS_TIMEZONE=UTC`
- `APP_DISPLAY_TIMEZONE=Asia/Karachi`
- `D7PAY_GIT_BRANCH=d7pay`
- `API_DOMAIN`、`ADMIN_DOMAIN`、`MERCHANT_DOMAIN`、`APKDOWNLOAD_DOMAIN` 都是客户域名
- `D7PAY_SECRET_YAML` 指向真实 Secret YAML

`D7PAY_ENV` 不执行 shell 变量展开，不能写 `${API_DOMAIN}`；所有 URL 都要写完整值。

当前线上发布只走 Jenkins 触发的宿主机脚本，脚本目录是：

```text
/opt/cicd/k8s_d7pay/sh/
```

线上真实脚本包括：

- `/opt/cicd/k8s_d7pay/sh/deploy-api.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-admin.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-merchant.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-admin-h5.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-merchant-h5.sh`
- `/opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh`
- `/opt/cicd/k8s_d7pay/sh/check_conf.sh`

这些脚本会进入 `/opt/cicd/k8s_d7pay/pk_project_k8s`，执行 `git reset --hard origin/d7pay` 和 `git clean -fd`，再复制对应目录到 `/opt/cicd/k8s_d7pay/<service>/pk_dockerfile/`，构建 `10.170.0.18:30086/lib/<service>-d7pay:<timestamp>`，推送镜像，改写对应 deployment yaml 的 image，然后 `kubectl apply` 并等待 rollout。

Makefile 目标只作为本地合同检查、配置渲染、配置修复和旧兼容入口，不作为线上业务发布入口；不要用 Makefile 代替 Jenkins 发布 `api/admin/merchant/admin-h5/merchant-h5/apkdownload`。

## 当前 API 后台任务

当前线上 API 镜像由 `/opt/cicd/k8s_d7pay/api/pk_dockerfile/start.sh` 启动，仍然是 API Web 服务加 Python jobs，不是 Go worker：

- `nginx`
- `python main.py --port=9000 --logfile=api.log`
- `jobs/easypaisa/auto_payout.py`
- `jobs/jazzcash/jazzcash_auto_payout.py`
- `jobs/jazzcash/jazzcash_monitor.py`
- `jobs/Jazzcashpay_v2.py`
- `jobs/notify_df.py`
- `jobs/notify.py`
- `jobs/time_out.py`
- `jobs/pakistanpay_v2.py`

Go worker 不属于当前线上发布入口。后续如果切 Go worker，必须先单独更新 Jenkins、API start 脚本、worker deployment、数据库 schema 和回滚文档；不能只改本地 D7pay 文档或 Makefile 就认为线上已经切流。

时区规则保持不变：MySQL、Redis、Pod 系统时间和业务判断都按 UTC；EasyPaisa/JazzCash 上游返回的无时区 `tradeTime/TRX_DTTM` 按巴基斯坦时间解析，应用层转换后与订单窗口匹配。

## Go Worker 切流发布

切流目标是：Go worker 在 `pk-d7pay` namespace 单独部署，API 容器只跑 Web 服务，Python jobs 退役。

切流必须同时满足：

- `pk-go-worker` 使用 `d7pay` 分支构建镜像，镜像推送为 `10.170.0.18:30086/lib/pk-go-worker-d7pay:<tag>`。
- D7pay MySQL 先执行 `api/sql/20260510_go_worker_phase0_schema.sql`，已跑过 Phase 0 的环境再执行 `api/sql/20260510_go_worker_balance_changed_scan.sql`。
- Jenkins API 发布前，线上启动路径仍是 `/opt/cicd/k8s_d7pay/api/pk_dockerfile/start.sh`；只用仓库模板 `ops/tenants/d7pay/runtime/api-start-web-only.sh` 覆盖这个现有文件的内容，删除 jobs 启动段。
- Jenkins 单独发布 `ops/tenants/d7pay/k8s/go-worker-deployments.yaml`，并把镜像占位 `replace-by-jenkins` 替换为本次 Go worker 镜像 tag。
- 四个 Deployment 必须都在 `pk-d7pay`：`d7pay-go-worker`、`d7pay-go-worker-relay`、`d7pay-go-worker-scheduler`、`d7pay-go-worker-ops`。
- 切流后 `api` Pod 内不得再出现 `pakistanpay_v2.py`、`Jazzcashpay_v2.py`、`auto_payout.py`、`jazzcash_auto_payout.py`、`jazzcash_monitor.py`、`notify.py`、`notify_df.py`、`time_out.py`。

Go worker 的 `tradeTime/TRX_DTTM` 规则固定为：上游无时区字符串按 `Asia/Karachi` 解析，再转 UTC 与 MySQL UTC 时间比较；RFC3339 带时区字符串按原时区解析后转 UTC。不能把 Pod、MySQL 或 Redis 系统时区改成巴基斯坦时间。

## 发布前检查配置

```bash
cd /opt/cicd/k8s/pk_project_k8s
git status --short
git checkout d7pay
git pull --ff-only origin d7pay
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

D7pay 侧只负责配置检查、配置渲染、配置应用和健康检查。应用打包、镜像构建、推送和 rollout 继续走线上 Jenkins 脚本，不走 D7pay Makefile。

`make d7pay-render-config` 会生成：

- `/tmp/d7pay-rendered/app-configmap.yaml`
- `/tmp/d7pay-rendered/nginx-d7pay.conf`
- `/tmp/d7pay-rendered/env-summary.txt`

## 配置不对时自动改回来

如果 D7pay 的 K8s 公共配置被改乱，先检查 `/opt/cicd/secrets/d7pay.env`，确认 `PROJECT_DIR` 指向 `/opt/cicd/k8s_d7pay/pk_project_k8s`。线上应由 Jenkins 配置发布步骤应用 D7pay 公共配置；手工排障时只能渲染并应用 `pk-d7pay` 的公共配置，不能触发业务镜像发布。

```bash
cd /opt/cicd/k8s_d7pay/pk_project_k8s
bash ops/tenants/d7pay/scripts/apply-config.sh
```

它只会应用 namespace、应用 ConfigMap、H5 nginx ConfigMap、Service、真实 Secret 和 PVC，不会构建镜像、不会推送镜像、不会改写打包文件、不会滚动业务 deployment。

旧的 `make d7pay-deploy` 现在只是兼容入口，也只会应用配置。服务发布请继续走现有发布脚本。

## Flutter App 发布

App 发布不走 `d7pay-deploy` 全量入口。App 是 `apkdownload` 的静态制品，流程是先构建 APK，再只发布 `apkdownload`：

```bash
make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env \
  FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter
git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/
git commit -m "chore: publish d7pay merchant apk"
git push origin d7pay
# 后续由 Jenkins 执行 /opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

正式发布前必须确认 Flutter 工程存在 `android/key.properties`，并且 `D7PAY_ENV` 里 `REQUIRE_RELEASE_SIGNING=true`、`APP_API_BASE_URL=https://api.d7pay.net`。不能用 debug 签名包交付客户。

nginx 配置上线前先执行：

```bash
nginx -t
systemctl reload nginx
```

D7pay 的 `api` 域名必须把 `/static/` 交给 API 静态资源。当前 API 支付页使用 Tornado `static_url()`，浏览器会请求 `https://api.d7pay.net/static/...`；如果 nginx 只代理 `/api/`，扫码页会出现 `reset.css`、`qrcode.min.js`、`jquery-2.1.4.min.js`、`layer3.js` 404，随后报 `$ is not defined`。

推荐规则与 tc160 一致，K8s/NodePort 场景使用代理到 API NodePort：

```nginx
location ^~ /static/ {
    proxy_pass http://127.0.0.1:31085/static/;
    expires 3650d;
    add_header Cache-Control "public, immutable";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
}
```

上线后验收：

```bash
curl -k -I https://api.d7pay.net/static/css/reset.css
curl -k -I https://api.d7pay.net/static/v2/plugins/jquery/jquery-2.1.4.min.js
```

两条都应返回 `200`。

## 验收

- `pk` namespace 仍在运行，`awekay.com` 仍指向原业务。
- `pk-d7pay` namespace 存在，`api/admin/merchant/admin-h5/merchant-h5/apkdownload` rollout 成功。
- admin、merchant、apkdownload、api 四个客户域名都能访问。
- `https://api.d7pay.net/static/css/reset.css` 和 `https://api.d7pay.net/static/v2/plugins/jquery/jquery-2.1.4.min.js` 返回 `200`，扫码页控制台不再出现静态资源 404。
- admin、merchant、App 展示 D7pay 品牌。
- API、数据库、Redis、指纹目录和 APK 目录都只属于 D7pay。
- D7pay 业务时间保持 UTC：不修改 MySQL、Redis、Pod 系统时区；`d7pay-config` 必须包含 `BUSINESS_TIMEZONE=UTC` 和 `APP_DISPLAY_TIMEZONE=Asia/Karachi`。
- 面向客户展示、报表边界和上游接口参数由应用层转换为巴基斯坦时间。
- Go worker 切流后，四个 `d7pay-go-worker*` Deployment Running，API Pod 只剩 `main.py` Web 进程，Python jobs 全部退役。

时区验收命令：

```bash
kubectl -n pk-d7pay get cm d7pay-config -o yaml | grep -E 'BUSINESS_TIMEZONE|APP_DISPLAY_TIMEZONE|TZ|MYSQL_DEFAULT_TIME_ZONE'
kubectl -n pk-d7pay exec statefulset/mysql -- mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -NBe 'select @@global.time_zone,@@session.time_zone,@@system_time_zone,now(),utc_timestamp();'
kubectl -n pk-d7pay exec deploy/api-deploy -- python - <<'PY'
from application.timezone import get_business_timezone_name, get_display_timezone_name, format_for_display
print(get_business_timezone_name(), get_display_timezone_name(), format_for_display())
PY
```

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
