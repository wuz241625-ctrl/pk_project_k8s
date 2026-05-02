# Test 分支排错入口

`test` 分支是当前服务器原 `pk` 测试环境发布源。排错优先查看对应子项目：

- `api/err.md`
- `admin/err.md`
- `merchant/err.md`
- `admin-h5/err.md`
- `merchant-h5/err.md`
- `apkdownload/err.md`

## 分支混用排错

如果原 `pk` 测试环境出现客户品牌、客户 APK、客户 namespace 或客户 NodePort 配置，先确认服务器仓库分支：

```bash
git status --short --branch
git rev-parse --abbrev-ref HEAD
```

预期分支是：

```text
test
```

如果分支不是 `test`，先停止发布，确认是否误用了客户租户分支。
