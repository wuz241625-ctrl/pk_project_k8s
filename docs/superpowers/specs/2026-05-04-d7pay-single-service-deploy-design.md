# D7pay 单服务发布设计

## 背景

D7pay 首次上线需要全量部署 `api/admin/merchant/admin-h5/merchant-h5/apkdownload`，因为 namespace、ConfigMap、Secret、Service、PVC 和所有镜像都要一次性建好。上线后的日常维护不应该每次全量构建和滚动所有服务，否则一次只改后台页面也会重发 API、merchant 和 apkdownload，增加发布时间和误操作范围。

## 头脑风暴方案

方案 A：在现有 `deploy-d7pay.sh` 增加目标选择器，并由 Makefile 暴露单服务入口。优点是复用现有构建函数、域名防混用、namespace 防呆和 D7pay Dockerfile 改写逻辑；全量发布保持默认行为。缺点是部署脚本需要做一次小型重构。

方案 B：为每个服务新建独立脚本，例如 `deploy-api.sh`、`deploy-admin-h5.sh`。优点是入口直观；缺点是重复 Jenkins 合同、代码同步、资源 apply、镜像构建逻辑，后续容易漂移。

方案 C：只在 Jenkins Job 参数里控制 shell 片段。优点是代码改动少；缺点是发布真相源进入 Jenkins UI，Git 里无法验收和审计，不适合出租托管场景。

推荐方案 A。D7pay 发布能力继续以 Git 内脚本为唯一真相源，Jenkins 只传 `D7PAY_ENV` 和目标参数。

## 设计

`make d7pay-deploy` 保持全量发布，用于首次上线或租户整体版本发布。底层 `deploy-d7pay.sh` 默认 `D7PAY_DEPLOY_TARGETS=all`，执行顺序仍是 `api -> admin -> merchant -> admin-h5 -> merchant-h5 -> apkdownload`。

新增单服务入口：

```bash
make d7pay-deploy-api D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-admin D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-merchant D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-merchant-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-apkdownload D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

也支持 Jenkins 参数化入口：

```bash
make d7pay-deploy-service SERVICE=api D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-service SERVICE=admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

单服务发布仍会执行代码同步、合同检查和租户公共资源 apply，保证 ConfigMap、Secret、Service、PVC 是最新状态；但只构建、推送、应用并 rollout 被选中的 deployment。公共资源 apply 不会滚动其他 deployment。

`D7PAY_DEPLOY_TARGETS` 接受逗号或空格分隔，例如 `api,admin-h5`，也接受 `all` 或 `full` 表示全量。未知目标直接失败，避免 Jenkins 拼错参数后静默跳过。

## 验收标准

- `make d7pay-deploy` 仍是全量发布入口，默认目标等于六个服务。
- 每个 `make d7pay-deploy-*` 单服务目标只触发对应服务构建与 rollout。
- `make d7pay-deploy-service SERVICE=<目标>` 可用于 Jenkins 参数化发布。
- `D7PAY_DEPLOY_TARGETS=api,admin-h5` 可一次发布多个明确目标。
- 非法目标必须失败并打印支持的目标列表。
- `preflight`、合同检查和文档必须包含单服务发布入口，运维能区分首次全量发布和后续维护发布。
- 验证命令至少覆盖 shell 语法、目标选择测试、合同检查和 Makefile 入口检查。
