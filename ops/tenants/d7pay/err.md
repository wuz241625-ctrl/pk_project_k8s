# D7pay 运维排错

## RUN_ENV 是 PROD 但仍读到旧库或旧域名

现象：

```text
printenv RUN_ENV
PROD
```

但容器内 `get_config()` 仍显示 `mysql_database=pakistan` 或 `ospay_api_host` 是旧域名。

原因：`RUN_ENV=PROD` 只决定使用 `product` 配置分支；如果镜像里的 `config.py` 是硬编码版本，K8s 注入 `MYSQL_DATABASE`、`API_OSPAY_API_HOST` 也不会生效。

处理：

```bash
cd /opt/cicd/k8s/pk_project_k8s
git checkout d7pay
git pull --ff-only origin d7pay
make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

D7pay 发布脚本必须在构建 `api/admin/merchant` 时把 `config.example.py` 复制为镜像内 `config.py`，并通过 `d7pay-runtime-config`、`d7pay-runtime-secret` 注入真实配置。

验收：

```bash
kubectl -n pk-d7pay exec deploy/api-deploy -- printenv RUN_ENV MYSQL_DATABASE TENANT_CODE
kubectl -n pk-d7pay exec deploy/api-deploy -- python -c 'from config import get_config; c=get_config(); print(c.get("tenant_code"), c.get("mysql_database"), c.get("ospay_api_host"))'
```

期望看到：

```text
PROD
pakistan_d7pay
d7pay
d7pay pakistan_d7pay https://api.d7pay.net/api
```

## 同实例迁库时报 `GTID_PURGED` 冲突

现象：

```text
ERROR 3546 (HY000): @@GLOBAL.GTID_PURGED cannot be changed
mysqldump: Got errno 11 on write
```

原因：从同一个 MySQL 实例的 `pakistan` 导入到 `pakistan_d7pay` 时，普通 `mysqldump` 会带 `GTID_PURGED`，和目标实例已有 `GTID_EXECUTED` 重叠。

处理：同实例内复制库必须关闭 GTID purge。

```bash
kubectl -n pk-d7pay exec mysql-0 -- sh -lc \
  'MYSQL_PWD=Pass_1234 mysqldump --set-gtid-purged=OFF --default-character-set=utf8mb4 --single-transaction --quick -uroot pakistan | MYSQL_PWD=Pass_1234 mysql --default-character-set=utf8mb4 -uroot pakistan_d7pay'
```

## D7pay admin/merchant 前端返回 500

现象：

```text
https://admin.d7pay.net 500 Internal Server Error
https://merchant.d7pay.net 500 Internal Server Error
```

原因：D7pay 前端构建产物在 `/usr/share/nginx/html/d7pay/`，但 H5 nginx ConfigMap 如果仍指向 `/usr/share/nginx/html/prod/`，`try_files` 会内部跳转到不存在的 `/index.html`，最终返回 500。

处理：

```bash
kubectl apply -f ops/tenants/d7pay/k8s/h5-configmaps.yaml
kubectl -n pk-d7pay rollout restart deployment/admin-h5-deploy deployment/merchant-h5-deploy
```

ConfigMap 中 admin/merchant 的 `root` 必须是：

```nginx
root /usr/share/nginx/html/d7pay/;
```

## apkdownload 启动报 `Resource busy`

现象：

```text
rm: can't remove '/usr/share/nginx/html/files/android/d7pay': Resource busy
CrashLoopBackOff
```

原因：D7pay APK 目录通过 PVC 挂载到 `/usr/share/nginx/html/files/android/d7pay`，启动脚本不能再执行 `rm -rf /usr/share/nginx/html/*` 删除挂载点。

处理：D7pay 发布脚本会把清理命令替换成保留 `files` 目录，只删除非挂载的静态产物；发布后只保留 `d7pay_merchant` 元信息和 `/files/android/d7pay` APK 目录。

验收：

```bash
curl -k https://apkdownload.d7pay.net/files/android/appInfo.json
curl -k -I https://apkdownload.d7pay.net/files/android/d7pay/d7pay_merchant_arm64_v0.1.7_202605031803.apk
curl -k -I https://apkdownload.d7pay.net/files/android/d7pay/d7pay_merchant_arm_v0.1.7_202605031803.apk
```

D7pay 线上 `appInfo.json` 不能出现 `ashrafi_merchant` 或 `lakshmi`。

## apkdownload 公网还下载到旧 APK

现象：宿主机 `/data/pk-d7pay/apkdownload/d7pay/` 和容器挂载目录里的 APK 已经更新，但 `https://apkdownload.d7pay.net/files/android/d7pay/<旧文件名>.apk` 仍返回旧哈希。

原因：`apkdownload.d7pay.net` 经过 Cloudflare，旧文件名可能被缓存。不要继续复用同一个 APK 文件名覆盖发布。

处理：生成新的 APK 文件名，更新 `apkdownload/public/files/android/appInfo.d7pay.json` 的 `filename` 和 `path`，把新文件同步到 PVC，再验证新 URL。旧文件可以从 origin 删除，避免绕过 `appInfo.json` 下载到旧包。

## app.d7pay.net 显示 Ashrafi

现象：访问 `app.d7pay.net` 看到 Ashrafi 的 H5 title 或 manifest。

原因：该域名不是 D7pay Android App 的交付入口，曾被手工代理到旧 `app-h5` NodePort。

处理：从宿主机 nginx 的 D7pay server block 中移除 `app.d7pay.net`，并删除或禁用对应 443 server；D7pay App 只通过 `apkdownload.d7pay.net` 下载 APK，运行时请求 `https://api.d7pay.net`。

## nginx 备份文件放在 `sites-enabled` 触发重复域名

现象：

```text
nginx: [warn] conflicting server name "admin.d7pay.net" on 0.0.0.0:443, ignored
```

原因：把备份文件放在 `/etc/nginx/sites-enabled/` 下会被 nginx 一起 include，导致重复 server block。

处理：备份必须放到非启用目录，例如：

```bash
mkdir -p /root/backup/nginx
mv /etc/nginx/sites-enabled/d7pay.before-* /root/backup/nginx/
nginx -t
systemctl reload nginx
```

## 域名被拒绝

现象：

```text
API_DOMAIN 必须替换为 D7pay 客户自有域名
```

原因：环境变量仍使用 `example.com` 或 `awekay.com`。D7pay 不能使用我们的域名，也不能使用占位域名。

处理：

```bash
vi /opt/cicd/secrets/d7pay.env
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## Secret 文件不存在

现象：

```text
D7PAY_RUNTIME_SECRET_YAML 指向的文件不存在
```

原因：Jenkins 或服务器上的真实 Secret YAML 没准备好，或仍包含 `replace-in-jenkins`、`CHANGE_ME` 这类占位值。

处理：

```bash
cp ops/tenants/d7pay/k8s/runtime-secret.example.yaml /opt/cicd/secrets/d7pay-runtime-secret.yaml
chmod 600 /opt/cicd/secrets/d7pay-runtime-secret.yaml
vi /opt/cicd/secrets/d7pay-runtime-secret.yaml
```

替换所有真实密钥后再执行 preflight。

## KUBE_NAMESPACE 被拒绝

现象：

```text
KUBE_NAMESPACE=pk 不允许用于 D7pay 运维命令
```

原因：D7pay 必须使用 `pk-d7pay`，不能发布到现有 `pk`。

处理：

```bash
grep KUBE_NAMESPACE /opt/cicd/secrets/d7pay.env
```

确认值为 `pk-d7pay`。

## 环境变量没有展开

现象：

```text
APP_API_BASE_URL 存在未展开的变量引用
```

原因：`D7PAY_ENV` 是逐行读取的 key/value 文件，不执行 shell 展开；不要写 `${API_DOMAIN}` 这种引用。

处理：把值写成完整客户域名，例如：

```text
API_WEBSOCKET_ALLOW_HOST=api.customer-domain.com
APP_API_BASE_URL=http://api.customer-domain.com
```

## healthcheck 返回 000 或 5xx

原因通常是 DNS 未解析、nginx 未 reload、NodePort 未通或 deployment 未完成 rollout。

处理顺序：

```bash
kubectl get deploy,pod,svc -n pk-d7pay -o wide
kubectl rollout status deployment/api-deploy -n pk-d7pay --timeout=180s
nginx -t
systemctl reload nginx
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## 回滚命令被拒绝

现象：

```text
确认执行请追加 CONFIRM_D7PAY_ROLLBACK=1
```

原因：回滚会影响 D7pay 线上实例，脚本要求显式确认。

处理：

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1
```
