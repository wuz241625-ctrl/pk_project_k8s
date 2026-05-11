# D7pay 当前部署检查与运维处理 Runbook

## 运维只看哪一份

运维日常执行不要啃这份长文档，先看一页 SOP：

```text
ops/tenants/d7pay/README_OPERATIONS.md
```

运维只需要按 SOP 跑下面几个命令做配置检查和配置修复：

```bash
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-apply-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

本 runbook 是排障和细节说明，其他文件只作为引用：

- `ops/tenants/d7pay/acceptance.md`：上线后验收清单。
- `ops/tenants/d7pay/jenkins.env.example`：Jenkins 变量模板。
- `ops/tenants/d7pay/k8s/`：K8s 资源与 patch。
- `docs/rental/d7pay-hosted.md`：托管交付边界说明。
- `ops/tenants/d7pay/err.md`：常见错误与处理。

运维不要从 `tenant.yaml`、`app-configmap.yaml` 或某个单独 patch 文件开始操作，因为这些文件只是发布合同的一部分，缺少当前线上状态、备份、域名、回滚和验收顺序。

## 2026-05-11 当前线上发布事实源

检查对象：`root@34.92.65.29:/opt/cicd/k8s_d7pay`。

当前线上发布由 Jenkins 执行宿主机脚本，不由本仓库 Makefile 直接发布业务服务。事实源如下：

```text
/opt/cicd/k8s_d7pay/sh/deploy-api.sh
/opt/cicd/k8s_d7pay/sh/deploy-admin.sh
/opt/cicd/k8s_d7pay/sh/deploy-merchant.sh
/opt/cicd/k8s_d7pay/sh/deploy-admin-h5.sh
/opt/cicd/k8s_d7pay/sh/deploy-merchant-h5.sh
/opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh
/opt/cicd/k8s_d7pay/sh/check_conf.sh
```

这些脚本统一使用：

```text
PROJECT_DIR=/opt/cicd/k8s_d7pay/pk_project_k8s
NAMESPACE=pk-d7pay
REGISTRY=10.170.0.18:30086/lib
BRANCH=origin/d7pay
```

发布时脚本会 `git reset --hard origin/d7pay` 和 `git clean -fd`，再复制对应源码到 `/opt/cicd/k8s_d7pay/<service>/pk_dockerfile/` 构建镜像，推送到 Harbor，改写对应 deployment yaml 的 image 并等待 rollout。

当前 API Dockerfile 会把 `api/config.example.py` 复制为镜像内 `api/config.py`。运行时配置由 K8s env/envFrom 覆盖，D7pay 不应手工维护镜像内 `config.py`。

当前 API start 脚本仍启动 Python jobs，不是 Go worker：

```text
main.py
jobs/easypaisa/auto_payout.py
jobs/jazzcash/jazzcash_auto_payout.py
jobs/jazzcash/jazzcash_monitor.py
jobs/Jazzcashpay_v2.py
jobs/notify_df.py
jobs/notify.py
jobs/time_out.py
jobs/pakistanpay_v2.py
```

因此当前验收标准是“API Web 服务和 Python jobs 正常运行”。Go worker 不属于当前线上发布入口。不要把 Go worker 文档、Makefile 或未来草稿当成当前线上发布依据；后续如果切 Go worker，必须另写切流步骤并同步 Jenkins。

## 2026-05-11 Go Worker 切流目标

本次切流目标不是在 API 容器里继续追加进程，而是在 `pk-d7pay` namespace 单独部署 Go worker，并退役 API 容器内的 Python jobs。

目标组件：

```text
d7pay-go-worker            -mode=worker
d7pay-go-worker-relay      -mode=relay
d7pay-go-worker-scheduler  -mode=scheduler
d7pay-go-worker-ops        -mode=ops-scheduler
```

发布边界：

1. `pk-go-worker` 单独构建镜像，镜像名为 `10.170.0.18:30086/lib/pk-go-worker-d7pay:<tag>`。
2. `api` 镜像发布前，线上启动路径仍是 Docker 构建目录里的 `start.sh`；Jenkins 只用 `ops/tenants/d7pay/runtime/api-start-web-only.sh` 覆盖现有 `start.sh` 内容，删除 jobs 启动段。
3. `ops/tenants/d7pay/k8s/go-worker-deployments.yaml` 必须只发布到 `pk-d7pay` namespace，并引用线上实际的 `d7pay-runtime-config`、`d7pay-runtime-secret`。
4. 切流后，`api` Pod 内不得再启动 `pakistanpay_v2.py`、`Jazzcashpay_v2.py`、`auto_payout.py`、`jazzcash_auto_payout.py`、`jazzcash_monitor.py`、`notify.py`、`notify_df.py`、`time_out.py`。

数据库前置：

```bash
kubectl -n pk-d7pay exec -i mysql-0 -- sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D pakistan_d7pay' \
  < api/sql/20260510_go_worker_phase0_schema.sql
kubectl -n pk-d7pay exec -i mysql-0 -- sh -lc 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D pakistan_d7pay' \
  < api/sql/20260510_go_worker_balance_changed_scan.sql
```

时间规则：

- MySQL、Redis、Pod 系统时间继续保持 UTC。
- Go worker 中上游无时区 `tradeTime/TRX_DTTM` 按 `Asia/Karachi` 解析后转 UTC。
- RFC3339 带时区的上游时间按原时区解析后转 UTC。
- 所有订单窗口匹配都用 UTC 和 MySQL 中的 UTC 字段比较。

## 2026-05-03 当前收口结果

检查时间：2026-05-03 09:48 UTC。

D7pay 已从临时混合部署收口到独立租户合同：

- 服务器仓库使用 `origin/d7pay`。
- `api/admin/merchant` 容器 `RUN_ENV=PROD`，`TENANT_CODE=d7pay`，`MYSQL_DATABASE=pakistan_d7pay`，`MYSQL_USER=d7pay_app`。
- `d7pay-runtime-config` 和 `d7pay-runtime-secret` 已存在于 `pk-d7pay`，Go worker 直接引用这两个运行时配置对象。
- `d7pay-fingerprint-pvc` 绑定 `/data/pk-d7pay/fingerprint`，容器内挂载 `/fingerprint`。
- `d7pay-apkdownload-pvc` 绑定 `/data/pk-d7pay/apkdownload/d7pay`。
- D7pay 早期规划 NodePort 使用 `admin-h5:31081`、`merchant-h5:31082`、`apkdownload:31080`、`api-public:31085`；当前线上已由 `/opt/cicd/k8s_d7pay/*/k8s/*.yaml` 管理，发布前以服务器 yaml 和 `kubectl -n pk-d7pay get svc -o wide` 为准，不按旧文档硬改 NodePort。
- 宿主机 nginx 的 `admin.d7pay.net`、`merchant.d7pay.net`、`apkdownload.d7pay.net`、`api.d7pay.net` 已指向 D7pay 专属 NodePort。
- `app.d7pay.net` 不作为 D7pay 交付入口，不应代理到旧 `旧移动 H5`。
- D7pay APK 当前文件名为 `d7pay_merchant_universal_v0.1.8_202605031855.apk`，内置 `API_BASE_URL=https://api.d7pay.net`，同时包含 `armeabi-v7a` 和 `arm64-v8a`，使用共享正式 release keystore 签名。
- `make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env` 已通过。
- D7pay 运维脚本当前只负责配置检查/应用和健康检查；应用构建、镜像推送和 rollout 由 `/opt/cicd/k8s_d7pay/sh/deploy-*.sh` 处理。

注意：D7pay 后端上游 EasyPaisa/JazzCash 凭据当前沿用现有可用上游配置；如果客户提供独立上游凭据，只替换 `/opt/cicd/secrets/d7pay-secret.yaml` 并 rollout `api/admin/merchant`，不要改代码或复制 pk 数据。

## 结论

检查时间：2026-04-29 12:59 UTC。

当前服务器只部署了原 `pk` 实例，尚未部署 D7pay 专属实例。运维不能直接把客户域名指到现有 `pk` 服务，否则会混用 Ashrafi 的运行环境、数据、下载页和域名配置。

D7pay 上线必须按本 runbook 先完成代码拉取、独立 namespace、独立数据库、独立 Redis、独立 PVC、D7pay Service/NodePort、nginx 域名和 Jenkins 发布。

## 现有部署怎么处理

现有 `pk` 部署按“保留、备份、旁路新增”的原则处理：

1. 保留现有 `pk` namespace，不删除、不缩容、不改 Service、不改现有 NodePort。
2. 保留现有域名：`admin.awekay.com`、`merchant.awekay.com`、`api.awekay.com`、`apkdownload.awekay.com` 继续指向当前 `pk`。
3. 保留现有数据库、Redis、指纹 PVC 和 apkdownload 文件，不把它们改名或迁到 D7pay。
4. D7pay 新建 `pk-d7pay` namespace，使用专属 Service/NodePort：`31080`、`31081`、`31082`、`31085`。
5. D7pay 使用客户自有域名，不能使用 `awekay.com`；`*.d7pay.example.com` 只是文档占位。
6. nginx 只追加 D7pay 客户域名的 server block，不覆盖现有 `awekay.com` server block。
7. 数据层只允许新建 `pakistan_d7pay` database 和独立 Redis；不能把 D7pay 指向现有 `pakistan` 数据库。
8. 服务器仓库可以更新到最新 `origin/d7pay`，但更新代码不等于发布应用；D7pay 配置应用入口是 `ops/tenants/d7pay/scripts/apply-config.sh`，应用发布走现有发布脚本。
9. 如果任一步失败，先回滚或停用 `pk-d7pay`，不要动 `pk`。

一句话：现有部署是当前业务环境，D7pay 是新增租户环境。运维的目标不是“替换现有部署”，而是在同一套集群上新增一套隔离的 D7pay 发布。

## 2026-04-29 部署前基线（历史记录）

SSH 目标：`root@34.92.65.29`

服务器仓库：

```bash
cd /opt/cicd/k8s/pk_project_k8s
git rev-parse --short HEAD
git log -1 --oneline
```

检查结果：

```text
68a657d
68a657d fix: clear jazzcash active stale cooldown errors
```

本地/远端 `d7pay` 分支已包含 D7pay Jenkins/K8s 发布合同，服务器仓库若停留在 `test` 或旧提交，运维上线前必须先切到并拉取最新 `origin/d7pay`。

K8s namespace：

```text
default
kube-flannel
kube-node-lease
kube-public
kube-system
pk
```

不存在 `pk-d7pay`。也就是说 D7pay 的 namespace、ConfigMap、Secret、PVC、Service、Deployment 都还没有创建。

当前 `pk` namespace 的服务：

```text
admin         ClusterIP   6000/TCP
admin-h5      NodePort    80:30081/TCP
api           ClusterIP   9000/TCP
api-h5        NodePort    80:30085/TCP
apkdownload   NodePort    80:30080/TCP
旧移动 H5        NodePort    80:30083/TCP
merchant      ClusterIP   8000/TCP
merchant-h5   NodePort    80:30082/TCP
mysql         ClusterIP   3306/TCP
mysql-slave   ClusterIP   3306/TCP
redis         ClusterIP   6379/TCP
```

当前 `pk` namespace 的镜像：

```text
admin-deploy         10.170.0.18:30086/lib/admin:20260425150525
admin-h5-deploy      10.170.0.18:30086/lib/admin-h5:20260425052526
api-deploy           10.170.0.18:30086/lib/api:20260428030411
api-h5-deploy        10.170.0.18:30086/lib/api-h5:20260425131427
apkdownload-deploy   10.170.0.18:30086/lib/apkdownload:20260427180808
旧移动 H5-deploy        10.170.0.18:30086/lib/旧移动 H5:20260425131430
merchant-deploy      10.170.0.18:30086/lib/merchant:20260425144145
merchant-h5-deploy   10.170.0.18:30086/lib/merchant-h5:20260425063649
redis                redis:7.2
```

当前 PV/PVC：

```text
api-fingerprint-pv   Bound pk/api-fingerprint-pvc
mysql-pv             Bound pk/mysql-pvc
mysql-slave-pv       Bound pk/mysql-slave-pvc
redis-pv             Bound pk/redis-pvc
```

不存在 `d7pay-fingerprint-pv`、`d7pay-apkdownload-pv` 或 `pk-d7pay` 下的 PVC。

当前 nginx 域名：

```text
admin.awekay.com       -> 127.0.0.1:30081
merchant.awekay.com    -> 127.0.0.1:30082
app.awekay.com         -> 127.0.0.1:30083
apkdownload.awekay.com -> 127.0.0.1:30080
api.awekay.com         -> 127.0.0.1:30085
harbor.awekay.com      -> 127.0.0.1:30086
jenkins.awekay.com     -> 127.0.0.1:8080
webssh.awekay.com      -> 127.0.0.1:8888
```

不存在 D7pay 客户自有域名配置。本文后续使用 `*.d7pay.example.com` 作为占位，正式发布前必须替换成客户自己的真实域名。

当前 APK 下载目录：

```text
appInfo.json
d7pay/d7pay_merchant_universal_v0.1.8_202605031855.apk
```

旧快照中曾存在 Ashrafi/Lakshmi APK，D7pay 分支已清理旧客户 APK。当前 D7pay 发布只允许 `d7pay_merchant` 元信息和 `/files/android/d7pay/` 下的 D7pay APK。

`appInfo.json` 必须只暴露 D7pay 下载项，不能混入 Ashrafi/Lakshmi 客户包。

## 头脑风暴结论

方案一：把 D7pay 域名直接指向现有 `pk` NodePort。这个方案最快，但会混用真实数据、真实商户、真实密钥、真实指纹和 Ashrafi APK，不能用于出租托管。

方案二：复制一套长期代码分支和单独脚本。表面隔离，但后续 JCB、EasyPaisa、账务、白名单、回调、风控修复会分叉，维护风险高。

方案三：单独 `d7pay` 分支加 D7pay 租户合同。D7pay Jenkins/K8s 按 `ops/tenants/d7pay` 创建 `pk-d7pay`，运行数据用独立 database、Redis、PVC、Secret 隔离。当前选择方案三。

## 运维上线步骤

### 0. 确认不是替换现有部署

执行前先确认：

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl get ns pk
kubectl get ns pk-d7pay 2>/dev/null || true
kubectl get svc -n pk
```

预期：

- `pk` 存在并继续承载当前业务。
- `pk-d7pay` 首次上线前不存在，或存在但只属于 D7pay。
- `pk` 里的 `30080-30085` 不给 D7pay 复用。

如果有人要求把 `admin.awekay.com`、`merchant.awekay.com`、`api.awekay.com`、`apkdownload.awekay.com` 改成 D7pay，必须停止操作并确认业务归属。

### 1. 上线前冻结与备份

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
BACKUP_DIR=/root/backup/d7pay-preflight-$(date +%Y%m%d%H%M%S)
mkdir -p "${BACKUP_DIR}"
kubectl get all -n pk -o wide > "${BACKUP_DIR}/pk-all.txt"
kubectl get pv,pvc -A > "${BACKUP_DIR}/pv-pvc.txt"
cp /etc/nginx/sites-enabled/pk "${BACKUP_DIR}/nginx-pk.conf"
```

如果要复用当前 MySQL 实例承载 `pakistan_d7pay` database，先做全量 dump。D7pay 不能复用 `pakistan` 数据库，不能复制真实商户、真实码商、真实订单、真实指纹。

### 2. 拉取最新代码

```bash
cd /opt/cicd/k8s/pk_project_k8s
git status --short
git fetch origin
git checkout d7pay
git pull --ff-only origin d7pay
git rev-parse --short HEAD
python3 ops/tenants/d7pay/verify_release_contract.py
```

如果 `git status --short` 不为空，先备份差异并停止发布，不要直接覆盖现场变更。

拉代码后再次确认本地合同：

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
grep -R "awekay.com" ops/tenants/d7pay/tenant.yaml ops/tenants/d7pay/k8s/app-configmap.yaml && exit 1 || true
```

`tenant.yaml` 和 D7pay 应用 ConfigMap 合同里不能出现 `awekay.com`。

### 3. 准备 D7pay 数据服务

必须满足下面两个名字在 `pk-d7pay` namespace 内可解析：

```text
mysql:3306
redis:6379
```

推荐方式：

- MySQL 使用独立 database：`pakistan_d7pay`。
- MySQL 使用独立账号：`d7pay_app`，只授权 `pakistan_d7pay`。
- Redis 使用独立实例或独立 database；如果使用 K8s 内 Redis，服务名必须是 `redis`，namespace 必须是 `pk-d7pay`。
- 不允许把 D7pay 指向 `pk` namespace 的 `pakistan` 数据库。

如果 MySQL/Redis 不在 `pk-d7pay` namespace 内，必须同步修改 `ops/tenants/d7pay/k8s/app-configmap.yaml` 中的 `MYSQL_HOST`、`REDIS_HOST`，并在发布前重新执行合同校验。

### 4. 准备宿主机目录

当前集群节点有 `pk-1`、`pk-2`，D7pay PVC 的 local PV 固定在 `pk-1`。运维需要在 `pk-1` 创建目录：

```bash
mkdir -p /data/pk-d7pay/fingerprint
mkdir -p /data/pk-d7pay/apkdownload/d7pay
chmod 755 /data/pk-d7pay/fingerprint
chmod 755 /data/pk-d7pay/apkdownload/d7pay
```

API 指纹唯一真相源是容器内 `/fingerprint`，宿主机持久化目录是 `/data/pk-d7pay/fingerprint`。

### 5. 准备 Secret

从示例复制真实 Secret 文件，文件必须放在 Jenkins 安全工作区或服务器私有目录，不能提交 Git：

```bash
cp ops/tenants/d7pay/k8s/app-secret.example.yaml /root/secrets/d7pay-secret.yaml
chmod 600 /root/secrets/d7pay-secret.yaml
```

需要替换：

- `MYSQL_PASSWORD`
- `API_KEY_ORDER`
- `API_SECRET_KEY`
- `ADMIN_COOKIE_KEY`
- `ADMIN_ID_TOKEN_KEY`
- `MERCHANT_COOKIE_KEY`
- EasyPaisa/JazzCash 上游地址、账号和密钥
- `d7pay-android-signing` 里的共享 release keystore 参数

禁止把真实密钥写入 `tenant.yaml`、`app-configmap.yaml`、文档或提交记录。

### 6. 运行 Jenkins 发布

Jenkins 环境变量按 `ops/tenants/d7pay/jenkins.env.example` 配置，核心值如下：

```bash
PROJECT_DIR=/opt/cicd/k8s/pk_project_k8s
K8S_ROOT=/opt/cicd/k8s
KUBE_NAMESPACE=pk-d7pay
RUN_ENV=PROD
API_DOMAIN=api.d7pay.example.com
ADMIN_DOMAIN=admin.d7pay.example.com
MERCHANT_DOMAIN=merchant.d7pay.example.com
APKDOWNLOAD_DOMAIN=apkdownload.d7pay.example.com
API_PUBLIC_SCHEME=http
D7PAY_SECRET_YAML=/root/secrets/d7pay-secret.yaml
APP_APPLICATION_ID=com.d7pay.merchant
APP_ICON=@mipmap/ic_launcher_d7pay
APP_SIGNING_MODE=shared_release_keystore
REQUIRE_RELEASE_SIGNING=true
```

上面的 `*.d7pay.example.com` 只是占位。运维必须替换为 D7pay 客户自有域名；D7pay 配置检查脚本会拒绝 `example.com` 和 `awekay.com`，防止把 D7pay 发布到我们的域名或占位域名。

发布前先应用 D7pay 公共配置：

```bash
cd /opt/cicd/k8s/pk_project_k8s
make d7pay-apply-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

D7pay 运维脚本只应用：

- namespace
- 应用 ConfigMap
- H5 nginx ConfigMap
- services
- 真实 Secret
- data volumes

应用构建、镜像推送、deployment image 更新和 rollout 都由现有发布脚本处理。D7pay 运维脚本不再改写打包文件，也不执行 Docker 构建。

### 6.1 发布 Flutter App

Flutter App 不属于 K8s deployment。它的发布路径是 `Flutter 工程 -> APK 制品 -> apkdownload 静态文件 -> apkdownload 单服务发布`。

正式构建前确认：

```bash
test -d /Users/tear/pk_project/ashrafi_merchant_flutter
test -f /Users/tear/pk_project/ashrafi_merchant_flutter/android/key.properties
grep '^APP_API_BASE_URL=' /opt/cicd/secrets/d7pay.env
grep '^REQUIRE_RELEASE_SIGNING=true' /opt/cicd/secrets/d7pay.env
```

构建并更新下载页元信息：

```bash
cd /opt/cicd/k8s/pk_project_k8s
make d7pay-build-app D7PAY_ENV=/opt/cicd/secrets/d7pay.env \
  FLUTTER_APP_DIR=/Users/tear/pk_project/ashrafi_merchant_flutter
```

该命令会读取 Flutter `pubspec.yaml` 的版本号，生成：

```text
apkdownload/public/files/android/d7pay/d7pay_merchant_universal_v<version>_<timestamp>.apk
apkdownload/public/files/android/appInfo.d7pay.json
```

提交推送：

```bash
git add apkdownload/public/files/android/appInfo.d7pay.json apkdownload/public/files/android/d7pay/
git commit -m "chore: publish d7pay merchant apk"
git push origin d7pay
```

线上发布 `apkdownload`：

```bash
# 由现有发布脚本发布 apkdownload
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

验收：

```bash
aapt dump badging apkdownload/public/files/android/d7pay/<apk-name>.apk | grep -E "package:|application-label|native-code"
apksigner verify --verbose --print-certs apkdownload/public/files/android/d7pay/<apk-name>.apk
curl -k https://apkdownload.d7pay.net/files/android/appInfo.json
curl -k -I https://apkdownload.d7pay.net/files/android/d7pay/<apk-name>.apk
```

必须看到：

- `package: name='com.d7pay.merchant'`
- `application-label:'D7pay Merchant'`
- `native-code` 包含 `armeabi-v7a` 和 `arm64-v8a`
- 证书不是 `CN=Android Debug`
- `appInfo.json` 只包含 D7pay 下载项

D7pay 对外 NodePort：

```text
apkdownload 31080
admin-h5    31081
merchant-h5 31082
api-public  31085
```

### 7. 配置 nginx 与 DNS

DNS 指向服务器公网 IP 后，在 `/etc/nginx/sites-enabled/pk` 增加 D7pay server block。以下 `*.d7pay.example.com` 只用于说明位置，必须替换为客户真实域名。

admin：

```nginx
server {
    listen 80;
    server_name admin.d7pay.example.com;

    location / {
        proxy_pass http://127.0.0.1:31081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

merchant：

```nginx
server {
    listen 80;
    server_name merchant.d7pay.example.com;

    location / {
        proxy_pass http://127.0.0.1:31082;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

api：

```nginx
server {
    listen 80;
    server_name api.d7pay.example.com;

    location = / {
        return 404;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:31085/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

apkdownload：

```nginx
server {
    listen 80;
    server_name apkdownload.d7pay.example.com;

    location / {
        proxy_pass http://127.0.0.1:31080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

如果 admin/merchant 开启 IP 白名单，D7pay 客户自有的 admin 和 merchant 域名要复制同一套白名单策略；不要把白名单加到 api 或 apkdownload，避免 App 和回调被误拦。

应用 nginx：

```bash
nginx -t
systemctl reload nginx
```

### 8. 验收命令

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl get ns pk-d7pay
kubectl get cm,secret,svc,pv,pvc -n pk-d7pay
kubectl get deploy,pod -n pk-d7pay -o wide
kubectl rollout status deployment/api-deploy -n pk-d7pay --timeout=180s
kubectl rollout status deployment/admin-deploy -n pk-d7pay --timeout=180s
kubectl rollout status deployment/merchant-deploy -n pk-d7pay --timeout=180s
kubectl rollout status deployment/admin-h5-deploy -n pk-d7pay --timeout=180s
kubectl rollout status deployment/merchant-h5-deploy -n pk-d7pay --timeout=180s
kubectl rollout status deployment/apkdownload-deploy -n pk-d7pay --timeout=180s
curl -I http://<d7pay-admin-domain>/
curl -I http://<d7pay-merchant-domain>/
curl -I http://<d7pay-apkdownload-domain>/
curl -I http://<d7pay-api-domain>/api/
kubectl -n pk-d7pay get cm d7pay-config -o yaml | grep -E 'BUSINESS_TIMEZONE|APP_DISPLAY_TIMEZONE|TZ|MYSQL_DEFAULT_TIME_ZONE'
kubectl -n pk-d7pay exec statefulset/mysql -- mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -NBe 'select @@global.time_zone,@@session.time_zone,@@system_time_zone,now(),utc_timestamp();'
```

业务验收按 `ops/tenants/d7pay/acceptance.md` 执行。

## 回滚

如果 D7pay 首次发布失败，优先只回滚 `pk-d7pay`，不要动现有 `pk`。运维优先使用：

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1
```

底层命令如下：

```bash
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl rollout undo deployment/api-deploy -n pk-d7pay
kubectl rollout undo deployment/admin-deploy -n pk-d7pay
kubectl rollout undo deployment/merchant-deploy -n pk-d7pay
kubectl rollout undo deployment/admin-h5-deploy -n pk-d7pay
kubectl rollout undo deployment/merchant-h5-deploy -n pk-d7pay
kubectl rollout undo deployment/apkdownload-deploy -n pk-d7pay
```

如果需要临时停用 D7pay：

```bash
kubectl scale deployment api-deploy admin-deploy merchant-deploy admin-h5-deploy merchant-h5-deploy apkdownload-deploy -n pk-d7pay --replicas=0
nginx -t
systemctl reload nginx
```

PVC 默认 `Retain`，不要删除 PV 目录，避免误删指纹和 APK 文件。

## 运维验收标准

- 服务器仓库已更新到最新 `origin/d7pay`，`python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- `pk-d7pay` namespace 存在。
- `d7pay-config`、真实 `d7pay-secret` 存在。
- `api/admin/merchant/admin-h5/merchant-h5/apkdownload` deployment 都在 `pk-d7pay` rollout 成功。
- `api/admin/merchant` 容器 `RUN_ENV=PROD`。
- `api` 容器挂载 `/fingerprint`，PVC 绑定 `d7pay-fingerprint-pvc`。
- `apkdownload` 容器挂载 D7pay APK 目录，下载页包含 `d7pay_merchant`。
- D7pay 客户自有的 admin、merchant、api、apkdownload nginx 生效。
- D7pay admin、merchant、App、API 只访问 D7pay 数据，不读取 `pk` 真实业务数据。
