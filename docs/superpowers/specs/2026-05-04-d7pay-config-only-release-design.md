# D7pay 配置-only 发布边界设计

## 背景

用户现有 Dockerfile 和发布脚本已经负责各应用的打包、镜像构建、推送和 deployment 滚动。此前 D7pay 的 `deploy-d7pay.sh` 也承担构建发布职责，并且会临时改写构建目录里的 Dockerfile 和 start.sh，将默认打包命令切到 D7pay mode。这会和用户自己的 Dockerfile 发布逻辑争夺构建控制权，尤其是 admin-h5、merchant-h5、apkdownload 已经在 Dockerfile 里写好打包命令时。

## 头脑风暴结论

方案 A：保留 D7pay 构建发布脚本，只要求用户每次发布前先跑 Makefile。优点是自动化完整；缺点是继续存在 Dockerfile 打包命令冲突，不符合用户现在的职责划分。

方案 B：删除 D7pay 所有运维入口，只留文档。优点是不会冲突；缺点是 D7pay 域名、namespace、ConfigMap、Secret、PVC 配置无人校验，容易把客户实例接回 `pk` 或 `awekay.com`。

方案 C：D7pay 侧只负责配置检查、配置渲染、K8s 公共配置应用和健康检查；构建、镜像、滚动发布全部交给用户现有脚本。推荐此方案。它既保留 D7pay 的防混用能力，也不再碰 Dockerfile 或打包命令。

## 设计

D7pay 运维脚本职责收缩为：

- `preflight.sh`：检查租户合同、域名、Secret、YAML、脚本语法和 config-only 边界。
- `render-config.sh`：渲染 runtime ConfigMap、nginx 配置和环境摘要，不发布。
- `apply-config.sh`：应用 namespace、runtime ConfigMap、H5 nginx ConfigMap、Service、真实 Secret 和 PVC，用于“配置不对自动改回来”。
- `healthcheck.sh`：检查当前 deployment rollout 和域名连通性。
- `rollback.sh`：仍只做 K8s 回滚/缩容，不参与构建。

`deploy-d7pay.sh` 改成兼容包装器，只调用 `apply-config.sh`，不再构建镜像、不再 patch deployment 镜像、不再改写 Dockerfile 或 start.sh。这样即使有人误用旧命令，也只会修复配置，不会抢发布脚本的构建控制权。

用户现有脚本负责：

- 后端 Dockerfile 构建 `api/admin/merchant` 镜像。
- 前端 Dockerfile 构建 `admin-h5/merchant-h5/apkdownload` 镜像。
- 按用户脚本自身逻辑推镜像、更新 deployment、等待 rollout。
- Flutter App 正式包构建和 APK 制品提交，D7pay 文档只记录参数和检查点。

## 验收标准

- D7pay 脚本不再包含 `docker build`、`docker push`、Dockerfile 改写、`RUN pnpm` 替换或 `pnpm build` 替换。
- `deploy-d7pay.sh` 只作为兼容包装器调用 `apply-config.sh`。
- `apply-config.sh` 可以读取 `/opt/cicd/secrets/d7pay.env` 和真实 Secret YAML，校验域名与 namespace 后应用 D7pay K8s 公共配置。
- Makefile 不再把 `d7pay-deploy-*` 描述为服务构建发布入口；构建发布交给用户脚本。
- 文档明确：每次发布前可以跑配置检查/应用配置，但应用构建不走 D7pay Makefile。
- `make d7pay-preflight`、合同检查、shell 语法检查和 config-only 测试通过。
