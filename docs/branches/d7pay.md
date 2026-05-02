# D7pay 分支说明

## 定位

`d7pay` 分支是 D7pay 托管租户专用分支。它保留 D7pay 品牌、D7pay APK 下载页、D7pay K8s/Jenkins 发布合同和 `pk-d7pay` 运维脚本。

`d7pay` 不能作为当前服务器原 `pk` 测试环境的发布源。原 `pk` 测试环境使用 `test` 分支。

## 包含内容

- `ops/tenants/d7pay/`：D7pay 租户合同、K8s 资源、Secret 模板、运维 SOP、验收清单和一键脚本。
- `admin-h5`、`merchant-h5`：D7pay 构建模式、D7pay logo 和 favicon。
- `apkdownload`：D7pay 下载页配置和 D7pay APK 元信息。
- `docs/rental/d7pay-hosted.md`：D7pay 托管交付边界。
- 根目录 `Makefile`：D7pay `preflight/render/deploy/healthcheck/rollback` 运维入口。

## 验收标准

- 当前分支名为 `d7pay`。
- `python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- `make d7pay-preflight` 通过。
- `ops/tenants/d7pay/tenant.yaml` 存在，且 namespace 为 `pk-d7pay`。
- `ops/tenants/d7pay/README_OPERATIONS.md` 存在，运维可按一页 SOP 执行。
- D7pay 发布前必须使用真实客户域名和真实 Secret，不能使用 `example.com`、`awekay.com` 或 `replace-in-jenkins`。

## 发布命令

```bash
KUBECONFIG=/etc/kubernetes/admin.conf make d7pay-preflight D7PAY_ENV=/opt/cicd/secrets/d7pay.env
KUBECONFIG=/etc/kubernetes/admin.conf make d7pay-render-config D7PAY_ENV=/opt/cicd/secrets/d7pay.env
KUBECONFIG=/etc/kubernetes/admin.conf make d7pay-deploy D7PAY_ENV=/opt/cicd/secrets/d7pay.env
KUBECONFIG=/etc/kubernetes/admin.conf make d7pay-healthcheck D7PAY_ENV=/opt/cicd/secrets/d7pay.env
```
