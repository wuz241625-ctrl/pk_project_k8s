# D7pay Jenkins 与 K8s 发布收口设计

## 背景

上一次 D7pay 改动只完成了品牌 mode、下载页和 App 展示名，不能算完整托管发布。缺口在于 Jenkins 没有明确发布合同，K8s 没有 D7pay namespace/ConfigMap/Secret/PVC/patch 约束，`api/admin/merchant` 的运行配置仍容易被误解为直接提交真实 `config.py`，Flutter APK package 也还没有真正切到 D7pay。

## 方案比较

方案一是继续直接改 `config.py` 并提交。优点是直观，缺点是 `config.py` 已被 `.gitignore` 作为真实环境文件排除，提交真实配置会泄漏密钥，也不符合 K8s Secret 管理。

方案二是为 D7pay 复制一套长期分支和独立代码。优点是看起来独立，缺点是后续 JCB/EasyPaisa、账务、白名单、回调等修复会分叉。

方案三是同一主干加 Jenkins/K8s 租户合同。优点是发布入口统一、真实密钥不入库、数据通过 namespace/database/Redis/PVC 隔离、App 包名和签名由构建参数控制。当前选择方案三。

## 设计

D7pay 的唯一发布入口是 `ops/tenants/d7pay/tenant.yaml`。Jenkins 读取 `jenkins.env.example` 对应的真实凭据，并调用 `ops/tenants/d7pay/jenkins/deploy-d7pay.sh`。该脚本在服务器现有 `/opt/cicd/k8s` 发布结构上工作：Python 服务继续使用 Dockerfile 里的 `config.example.py -> config.py` 复制逻辑，admin-h5/merchant-h5/apkdownload 会在构建前把默认构建命令改为 D7pay mode。构建 Flutter APK 时传入 `ORG_GRADLE_PROJECT_appApplicationId=com.d7pay.merchant` 和 `ORG_GRADLE_PROJECT_requireReleaseSigning=true`。K8s 使用 `pk-d7pay` namespace，运行配置进入 `d7pay-runtime-config`，密钥进入 `d7pay-runtime-secret`，指纹和 APK 目录由 PVC 管理。

`api/admin/merchant` 只提交 `config.example.py`，真实 `config.py` 继续忽略。配置模板必须从环境变量读取 MySQL、Redis、API URL、Cookie Key、上游密钥等值，确保 Jenkins/K8s 注入能覆盖，而不是把某个租户的真实配置写死在代码里。

## 数据与发布边界

D7pay 使用 `pakistan_d7pay` 数据库、独立 Redis 实例、`/data/pk-d7pay/fingerprint` 指纹宿主机目录和 `/data/pk-d7pay/apkdownload/d7pay` APK 宿主机目录。客户不获得 SSH、K8s、数据库、Redis、源码或 Docker registry 权限。签名共用同一份 release keystore，但 `android/key.properties` 和 keystore 只能来自 Jenkins Credential 或 K8s Secret，不能提交 Git。

## 验收标准

`python3 ops/tenants/d7pay/verify_release_contract.py` 必须通过。D7pay APK 的 `aapt dump badging` 必须显示 `package: name='com.d7pay.merchant'` 和 `application-label:'D7pay Merchant'`。apkdownload 的 D7pay mode 必须指向新 APK。`api/admin/merchant` 的 `config.example.py` 必须包含 `TENANT_CODE`、`MYSQL_DATABASE` 等环境变量读取。K8s patch 必须覆盖 api/admin/merchant 的 ConfigMap/Secret 注入，api 必须挂载 `/fingerprint`。
