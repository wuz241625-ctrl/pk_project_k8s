# D7pay 运维交接与现有部署处理设计

## 背景

用户需要明确两件事：运维应该看哪一份文档，以及现有已部署的 `pk` 环境应该怎么处理。2026-04-29 20:59 Asia/Shanghai 再次检查服务器，当前状态仍是：

- 服务器仓库 `/opt/cicd/k8s/pk_project_k8s` 停在 `68a657d`。
- K8s 只有 `pk` namespace，不存在 `pk-d7pay`。
- 当前 `pk` 继续运行 admin、merchant、api、apkdownload、MySQL、Redis 等服务。
- nginx 只有 `awekay.com` 相关域名，没有 D7pay 客户自有域名。

这说明 D7pay 不是“改现有部署”，而是“在现有集群旁路新增隔离租户”。

## 头脑风暴方案

方案一：让运维看 `acceptance.md`。优点是验收清晰，缺点是没有当前线上状态、备份、域名、回滚和部署顺序，不适合作为执行入口。

方案二：让运维看 `jenkins.env.example` 和 `k8s/`。优点是接近实际配置，缺点是容易误把单个 YAML 当成完整流程，也容易漏掉现有 `pk` 保护。

方案三：让运维只从 `ops/tenants/d7pay/current-deployment-ops-runbook.md` 开始。该文档包含当前部署事实、现有部署处理原则、上线步骤、域名要求、回滚和验收。采用方案三。

## 设计

`current-deployment-ops-runbook.md` 顶部增加“运维只看哪一份”，明确它是唯一执行入口，其他文件只是引用。这样运维不会从 `tenant.yaml`、`runtime-configmap.yaml` 或 patch 文件直接开始操作。

Runbook 增加“现有部署怎么处理”：现有 `pk` namespace 保留，不删除、不缩容、不改 Service、不改 NodePort；现有 `awekay.com` 域名继续指向当前业务；D7pay 新增 `pk-d7pay` namespace、独立 database、独立 Redis、独立 PVC、专属 NodePort 和客户自有域名。

Runbook 的上线步骤前增加第 0 步：确认不是替换现有部署。运维必须先检查 `pk`、`pk-d7pay` 和 `pk` Service，确认 D7pay 不复用 `pk` 的 `30080-30085`。

`docs/rental/d7pay-hosted.md` 同步写明运维唯一入口和现有部署处理原则；`acceptance.md` 同步加入现有 `pk` 不被破坏、D7pay 不指向 `awekay.com`、运维必须从 runbook 执行的验收项。

## 验收标准

- Runbook 顶部明确：运维唯一入口是 `ops/tenants/d7pay/current-deployment-ops-runbook.md`。
- Runbook 明确现有 `pk` 部署保留，不替换、不缩容、不复用 NodePort。
- Runbook 明确 D7pay 使用 `pk-d7pay`、客户自有域名和 `31080/31081/31082/31085`。
- 托管说明和验收标准同步引用 runbook 和现有部署保护要求。
- `python3 ops/tenants/d7pay/verify_release_contract.py`、`bash -n ops/tenants/d7pay/jenkins/deploy-d7pay.sh`、YAML 解析和 `git diff --check` 通过。
