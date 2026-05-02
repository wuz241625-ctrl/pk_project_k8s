# Test 分支设计

## 背景

用户要求当前服务器原 `pk` 测试环境使用独立 `test` 分支，并且 `test` 分支不包含客户租户交付内容。

## 设计

`test` 分支基于 `68a657d fix: clear jazzcash active stale cooldown errors` 创建。该提交是当前历史中最后一个非客户租户交付提交。分支只补充根目录构建索引、排错索引和 `docs/branches/test.md`，不引入客户租户目录、品牌资源、APK 下载页或 K8s/Jenkins 合同。

## 验收标准

- `ops/tenants/d7pay` 不存在。
- `apkdownload/public/files/android/d7pay` 不存在。
- 业务目录中不包含客户专属构建脚本、客户图标资源或客户 namespace。
- 根目录 `build.md` 和 `err.md` 存在，指向原测试环境构建与排错入口。
