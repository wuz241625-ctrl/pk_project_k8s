# D7pay Runtime Env Naming Design

## 背景

线上 `pk-d7pay` namespace 实际运行对象是 `d7pay-runtime-config` 和 `d7pay-runtime-secret`。API、Admin、Merchant 与四个 Go worker Deployment 都通过这两个对象注入运行时环境变量。仓库内仍有 `d7pay-config` / `d7pay-secret` 旧命名，容易让发布、排障和验收误查不存在的对象。

## 方案

采用线上对象名作为唯一运行口径：

- ConfigMap manifest 的 `metadata.name` 改为 `d7pay-runtime-config`。
- Secret example 的 `metadata.name` 改为 `d7pay-runtime-secret`。
- `tenant.yaml`、API/Admin/Merchant env patch、Go worker manifest 验收、单元测试和发布合同检查统一断言 runtime 对象名。
- 保留文件名 `app-configmap.yaml` / `app-secret.example.yaml`，因为它们描述文件用途，不代表 K8s 对象名。
- 文档明确服务器源文件：`/opt/cicd/secrets/d7pay.env` 生成非敏感 ConfigMap，`/opt/cicd/secrets/d7pay-runtime-secret.yaml` 提供 Secret manifest。

## 不做

- 不在文档或仓库写入 Secret 明文。
- 不修改线上 Secret 值。
- 不改 H5 静态服务的配置方式。
- 不把历史备份文件重命名。

## 验收标准

- `rg "d7pay-config|d7pay-secret" ops/tenants/d7pay api/build.md api/err.md` 只剩历史说明或本地文件路径场景，不再作为线上对象断言。
- `python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v` 通过。
- `git diff --check` 通过。
- GitNexus staged detect 风险为 low，且无受影响流程。
