# D7pay 线上发布文档同步设计

## 背景

D7pay 当前线上发布由 Jenkins 调用 `/opt/cicd/k8s_d7pay/sh/deploy-*.sh` 完成。线上脚本会拉取 `origin/d7pay`，重置工作区，构建并推送镜像，更新 K8s deployment yaml，然后等待 rollout。本地 D7pay Makefile 只负责配置检查、配置渲染、配置应用、健康检查和旧入口兼容。

此前文档混入了未上线的 Go worker 切流说明，容易让运维误以为当前 API 已经 Web-only，或者误用 Makefile 发布业务服务。当前事实是：API 容器仍由线上 `start.sh` 启动 Web 服务和 Python jobs。

## 方案

采用“线上事实源优先”的文档策略：

1. 一页 SOP 明确：业务发布只走 Jenkins 脚本，Makefile 不发布业务镜像。
2. `build.md` 明确当前线上发布步骤和构建模式。
3. 长 runbook 增加 2026-05-11 当前线上发布事实源，记录脚本路径、工作目录、镜像仓库、API jobs。
4. 托管交付文档同步当前线上状态，避免继续保留“尚未部署”的旧结论。
5. 排错文档增加“误用 Makefile 当线上发布入口”的处理流程。
6. 单测增加文档合同检查，防止后续再次把未上线方案写成当前发布入口。

## 验收标准

- 文档中能直接看到 `/opt/cicd/k8s_d7pay/sh/deploy-api.sh` 等 Jenkins 发布脚本。
- 文档中能直接看到 `/opt/cicd/k8s_d7pay/pk_project_k8s`、`git reset --hard origin/d7pay`、`pk-d7pay`。
- 文档中明确 Go worker 不属于当前线上发布入口。
- 文档中明确当前 API 仍运行 Python jobs。
- `ops/tenants/d7pay/tests/test_config_only_release.py` 覆盖上述合同。
- `python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v` 通过。
