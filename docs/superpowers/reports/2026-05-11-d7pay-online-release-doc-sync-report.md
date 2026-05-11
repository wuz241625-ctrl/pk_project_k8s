# D7pay 线上发布文档同步验收报告

## 处理范围

- 同步 D7pay 一页 SOP 为线上 Jenkins 发布事实源。
- 同步 D7pay 构建文档，明确 Makefile 不负责业务镜像发布。
- 同步当前部署 runbook，新增 2026-05-11 线上脚本、目录、API jobs 事实源。
- 同步托管交付文档，移除“尚未部署”的旧结论。
- 增加误用 Makefile 当线上发布入口的排错条目。
- 增加合同测试，固定当前线上发布文档必须包含的关键信息。

## 关键结论

当前线上业务发布入口是 Jenkins 执行：

```text
/opt/cicd/k8s_d7pay/sh/deploy-api.sh
/opt/cicd/k8s_d7pay/sh/deploy-admin.sh
/opt/cicd/k8s_d7pay/sh/deploy-merchant.sh
/opt/cicd/k8s_d7pay/sh/deploy-admin-h5.sh
/opt/cicd/k8s_d7pay/sh/deploy-merchant-h5.sh
/opt/cicd/k8s_d7pay/sh/deploy-apkdownload.sh
```

Makefile 只用于配置检查、配置渲染、配置应用、健康检查、回滚辅助和 Flutter APK 本地制品。当前 API 线上仍运行 Python jobs，Go worker 不属于当前线上发布入口。

## 验收命令

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v
npx gitnexus detect-changes
```

## 验收结果

- `python3 ops/tenants/d7pay/verify_release_contract.py`：通过，输出 `D7pay release contract OK`。
- `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v`：通过，9 个测试全部 `ok`。
- `npx gitnexus detect-changes --repo pk_project_k8s`：通过，6 个已跟踪文件、24 个符号、0 个受影响流程、风险等级 low。
