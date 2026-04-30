# 项目排错入口

本文件只做排错索引，具体问题优先看对应子目录的 `err.md`。

## D7pay 运维问题

查看：

```text
ops/tenants/d7pay/err.md
```

常用检查：

```bash
make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```

## D7pay 常见失败方向

- 域名仍是 `example.com` 或 `awekay.com`。
- `KUBE_NAMESPACE` 错误指向 `pk`。
- `D7PAY_RUNTIME_SECRET_YAML` 不存在或仍有占位值。
- nginx 未 reload。
- `pk-d7pay` deployment 未 rollout 成功。
