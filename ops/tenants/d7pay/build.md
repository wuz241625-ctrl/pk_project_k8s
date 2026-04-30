# D7pay 运维构建与发布

## 本地合同检查

```bash
make d7pay-preflight
```

## 使用真实环境变量发布

```bash
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## 生成配置但不发布

```bash
make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env D7PAY_RENDER_DIR=/tmp/d7pay-rendered
```

## 回滚

```bash
make d7pay-rollback D7PAY_ENV=/opt/cicd/secrets/d7pay.env CONFIRM_D7PAY_ROLLBACK=1
```
