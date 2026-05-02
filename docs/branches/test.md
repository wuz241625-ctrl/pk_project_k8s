# Test 分支说明

## 定位

`test` 分支是当前服务器原 `pk` 测试环境的发布源。它基于最后一个非租户交付提交 `68a657d fix: clear jazzcash active stale cooldown errors` 创建。

这个分支只维护原测试环境，不承载客户托管租户、客户品牌资源、客户 APK 下载页或客户 K8s/Jenkins 发布合同。

## 包含内容

- `api`、`admin`、`merchant` 后端服务。
- `admin-h5`、`merchant-h5`、`apkdownload` 原测试环境前端。
- 当前 `pk` 测试环境使用的业务修复、脚本、测试和排错文档。

## 不包含内容

- 客户租户目录。
- 客户品牌 logo、favicon、下载页和 APK 元信息。
- 客户独立 namespace、NodePort、Secret、PVC、Jenkins 发布合同。

## 验收标准

- 当前分支名为 `test`。
- `ops/tenants/d7pay` 不存在。
- `apkdownload/public/files/android/d7pay` 不存在。
- `admin-h5/package.json` 和 `merchant-h5/package.json` 不包含客户专属构建脚本。
- `api`、`admin`、`merchant`、`admin-h5`、`merchant-h5`、`apkdownload` 的既有 `build.md` 与 `err.md` 保留。
- 当前服务器原 `pk` 测试环境如果要切分支，只切到 `test`，不要切到客户租户分支。

## 发布边界

当前服务器原 `pk` 测试环境的 namespace、Service、NodePort、数据库、Redis 和 nginx 域名保持现状。切到 `test` 分支只改变代码来源，不改变运行环境归属。
