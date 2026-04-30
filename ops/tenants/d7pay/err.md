# D7pay 运维排错

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

原因：Jenkins 或服务器上的真实 Secret YAML 没准备好。

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
