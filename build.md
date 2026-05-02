# Test 分支构建入口

`test` 分支用于当前服务器原 `pk` 测试环境。根目录只做构建索引，具体构建命令以各子项目的 `build.md` 为准。

## 后端服务

```bash
cd api
python3 -m pytest tests

cd admin
python3 -m pytest tests

cd merchant
python3 -m pytest tests
```

## 前端服务

```bash
cd admin-h5
npm run build:prod

cd merchant-h5
npm run build:prod

cd apkdownload
npm run build
```

## 分支验收

```bash
test ! -e ops/tenants/d7pay
test ! -e apkdownload/public/files/android/d7pay
```
