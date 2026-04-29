# D7pay Logo 品牌适配设计

## 背景

用户提供了 D7pay logo，要求把当前系统的 logo 适配处理好。前一轮只处理了 D7pay 名称、包名、下载页元信息和发布合同，logo 侧还不完整：admin-h5 侧边栏仍使用旧外链图，merchant-h5 默认不显示 logo，apkdownload 只使用默认 logo，Flutter App 只有默认 `ic_launcher`。

## 方案

采用“D7pay 构建模式独立启用，默认 Ashrafi 不受影响”的方案：

- 使用 image_gen 源图 `ops/tenants/d7pay/assets/d7pay-logo-source-imagegen.png` 生成 D7pay 品牌资产到 `ops/tenants/d7pay/assets/`，作为可复用源。
- admin-h5/merchant-h5 在 `VUE_APP_SYSTEM=d7pay` 时显示 D7pay 侧边栏 logo，并切换 favicon。
- apkdownload 在 `.env.d7pay` 的 `VITE_APP_KEY=d7pay_merchant` 下使用 D7pay logo，默认 Ashrafi 下载页继续使用原 logo。
- Flutter App 增加 `ic_launcher_d7pay` 多 density 资源，通过 `ORG_GRADLE_PROJECT_appIcon='@mipmap/ic_launcher_d7pay'` 启用，不覆盖默认 `ic_launcher`。

## 边界

当前使用 image_gen 输出的高质感 D7 图标作为唯一源图。后续如果用户提供原始 PNG/AI/SVG 文件，可以用同一生成流程替换源图并重新导出。

## 验收标准

- admin-h5 `npm run d7pay:prod` 构建产物引用 `d7pay-favicon.ico`，bundle 中包含 D7pay logo 资源。
- merchant-h5 `npm run d7pay:prod` 构建产物引用 `d7pay-favicon.ico`，bundle 中包含 D7pay logo 资源。
- apkdownload `npm run build:d7pay` 构建产物包含 D7pay logo 资源，默认 Ashrafi logo 不被覆盖。
- Flutter D7pay build contract 包含 `ORG_GRADLE_PROJECT_appIcon='@mipmap/ic_launcher_d7pay'`。
- Android `mipmap-*dpi/ic_launcher_d7pay.png` 多尺寸资源存在。
- `python3 ops/tenants/d7pay/verify_release_contract.py`、H5 构建、apkdownload 构建和 Flutter 关键测试通过。
