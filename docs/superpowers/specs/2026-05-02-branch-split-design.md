# Test 与 D7pay 分支隔离设计

## 背景

当前 `main` 已经包含 D7pay 托管租户相关提交。用户要求 D7pay 单独开分支，同时当前服务器原 `pk` 测试环境也单独开 `test` 分支，并且 `test` 不包含 D7pay 相关内容。

Git 历史显示最后一个非 D7pay 提交是 `68a657d fix: clear jazzcash active stale cooldown errors`。从 `4664b34 feat: add d7pay hosted branding config` 开始，后续提交都围绕 D7pay 品牌、K8s、Jenkins、运维 SOP 和验收文档。

## 头脑风暴方案

方案一：在当前 `main` 上删除 D7pay 文件再作为 `test`。这个方案会留下 D7pay 提交历史，后续容易误合并。

方案二：让 `main` 继续混合承载 test 和 D7pay，只用 Jenkins 参数区分。这个方案短期方便，但当前用户明确要求分支隔离，不适合继续混用。

方案三：`d7pay` 从当前最新提交切出，`test` 从最后一个非 D7pay 提交 `68a657d` 切出。这个方案能让 `test` 天然没有 D7pay 文件、品牌、APK 和租户资源，`d7pay` 则保留完整租户交付内容。本次采用方案三。

## 分支设计

`d7pay` 分支：

- 基于当前最新提交。
- 保留 `ops/tenants/d7pay/`、D7pay H5 构建、D7pay APK 下载页、D7pay logo 和运维脚本。
- 用于后续 D7pay 客户托管实例开发、发布和运维。

`test` 分支：

- 基于 `68a657d`。
- 不包含 D7pay 租户目录、D7pay 品牌、D7pay APK、D7pay K8s/Jenkins 发布合同。
- 用于当前服务器原 `pk` 测试环境。

## 验收标准

- `origin/d7pay` 存在，且包含 `ops/tenants/d7pay/tenant.yaml`。
- `origin/d7pay` 的 `python3 ops/tenants/d7pay/verify_release_contract.py` 通过。
- `origin/test` 存在，且 `ops/tenants/d7pay` 不存在。
- `origin/test` 中不包含 `apkdownload/public/files/android/d7pay`。
- `origin/test` 中 `admin-h5/package.json`、`merchant-h5/package.json` 不包含 `d7pay:prod`。
- 两个分支都有分支说明文档，说明各自用途和发布边界。
