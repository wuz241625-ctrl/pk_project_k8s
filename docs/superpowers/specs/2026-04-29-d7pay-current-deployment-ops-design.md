# D7pay 当前部署运维收口设计

## 背景

用户要求先看当前已部署环境，再给运维一份明确处理文档。线上检查确认服务器仓库停在 `68a657d`，K8s 只有 `pk` namespace，不存在 `pk-d7pay`；nginx 也只有 `admin.awekay.com`、`merchant.awekay.com`、`api.awekay.com`、`apkdownload.awekay.com` 等原域名；线上 APK 下载目录没有 `d7pay_merchant`。

这说明 D7pay 目前只是本地代码和发布合同已准备，线上尚未部署。运维如果直接改域名或复用现有 NodePort，会把 D7pay 客户接到 Ashrafi 的数据、密钥、指纹和下载页上。

## 方案比较

方案一：直接把 D7pay 域名指向当前 `pk` 服务。优点是最快，缺点是数据和品牌混用，存在真实信息泄露风险，不采用。

方案二：新开长期分支并复制部署目录。优点是看起来隔离，缺点是主干修复无法自然同步，后续 JCB/EasyPaisa、账务、回调、白名单都会分叉，不采用。

方案三：同一主干加租户发布合同。`ops/tenants/d7pay` 作为唯一交付入口，Jenkins 创建 `pk-d7pay` namespace，K8s 用独立 ConfigMap、Secret、Service、PVC，数据库和 Redis 独立。采用方案三。

## 设计

新增 D7pay 运维 runbook：`ops/tenants/d7pay/current-deployment-ops-runbook.md`。文档必须记录线上检查证据、当前缺失项、上线步骤、nginx 配置、验收命令和回滚方式，避免运维凭经验复用 `pk`。

补齐 D7pay K8s 对外服务合同：`ops/tenants/d7pay/k8s/services.yaml`。D7pay 使用独立 NodePort：`31080` 给 apkdownload，`31081` 给 admin-h5，`31082` 给 merchant-h5，`31085` 给 api-public。`api/admin/merchant` 仍使用 ClusterIP 供内部 H5 代理。

补齐 H5 nginx ConfigMap：`ops/tenants/d7pay/k8s/h5-configmaps.yaml`。因为服务器原始 deployment 会引用 `admin-h5-nginx-conf`、`merchant-h5-nginx-conf` 和 `download-nginx-conf`，如果不在 `pk-d7pay` 里创建这些 ConfigMap，D7pay H5 deployment 会因为缺少挂载对象无法启动。

更新 Jenkins 脚本：`ops/tenants/d7pay/jenkins/deploy-d7pay.sh` 在应用 namespace 和 runtime config 后，先应用 H5 ConfigMap 和 Service，再构建并发布 deployment。

更新合同校验：`ops/tenants/d7pay/verify_release_contract.py` 检查新 Service、NodePort、H5 ConfigMap、发布脚本 apply 顺序，防止后续误删。

## 数据边界

D7pay 不能复用 `pk` 的 `pakistan` 数据库。运维必须创建 `pakistan_d7pay` database 和独立账号，或者提供明确的独立 MySQL endpoint 并同步修改 `runtime-configmap.yaml`。Redis 必须是 `pk-d7pay` 内可解析的独立 `redis:6379` 或独立外部 endpoint。

指纹唯一真相源保持容器内 `/fingerprint`，D7pay 宿主机目录是 `/data/pk-d7pay/fingerprint`。APK 宿主机目录是 `/data/pk-d7pay/apkdownload/d7pay`。真实 Secret 只能由 Jenkins/运维注入，不能进入 Git。

## 验收标准

- `python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- `bash -n ops/tenants/d7pay/jenkins/deploy-d7pay.sh` 通过。
- `ops/tenants/d7pay/current-deployment-ops-runbook.md` 记录线上当前状态、处理步骤、nginx 示例、验收命令和回滚。
- `services.yaml` 包含 `api-public/admin-h5/merchant-h5/apkdownload` 的 D7pay NodePort。
- `h5-configmaps.yaml` 包含 admin、merchant、apkdownload 所需 ConfigMap。
- `docs/rental/d7pay-hosted.md` 和 `ops/tenants/d7pay/acceptance.md` 同步引用本次运维要求。
