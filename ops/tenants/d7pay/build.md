# D7pay 运维构建与发布

## 本地合同检查

```bash
make d7pay-preflight
```

## 首次全量发布

首次上线或租户整体版本发布使用全量入口，会构建并滚动 `api/admin/merchant/admin-h5/merchant-h5/apkdownload`：

```bash
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## 维护期单服务发布

上线后只改哪个服务就发布哪个服务；脚本仍会同步代码、检查合同并 apply 公共租户资源，但只构建和 rollout 指定 deployment：

```bash
make d7pay-deploy-api D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-admin D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-merchant D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-merchant-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy-apkdownload D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

Jenkins 参数化维护入口：

```bash
make d7pay-deploy-service SERVICE=admin-h5 D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

底层也支持一次发布多个明确目标：

```bash
D7PAY_DEPLOY_TARGETS=api,admin-h5 bash ops/tenants/d7pay/jenkins/deploy-d7pay.sh
```

## 生成配置但不发布

```bash
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env D7PAY_RENDER_DIR=/tmp/d7pay-rendered
```

## 回滚

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1
```
