# D7pay 明确垃圾清理设计

## 背景

`d7pay` 分支已经保留 D7pay 租户、EP/JCB 业务、admin/merchant/API/H5/apkdownload 发布链路，但仓库里仍有与当前运行入口无关的历史制品。它们会增加镜像上下文、代码审查噪音和误交付风险。

## 方案

采用保守清理方案：只删除引用证据明确、不会改变运行路由和业务行为的文件。旧银行代码、phonepe 路由、Lakshmi API 命名目录、三方回调等仍被路由或业务引用，暂不纳入本轮清理。

本轮删除范围：

- `api/jobs/freecharge-monitor/php/vendor/`：第三方 PHP vendor 被提交进仓库，D7pay 不依赖该 vendor 运行。
- `api/jobs/easypaisa/auto_payout.py.bak`：历史备份文件，正式实现为同目录 `auto_payout.py`。
- `apkdownload/public/files/android/lakshmi/lakshmi_v1.0.0.202406232042.apk`：D7pay 下载站不能保留 Lakshmi APK。
- `apkdownload/public/files/android/ashrafi/ashrafi_v0.1.6_202604280158.apk`：D7pay 下载站不能保留旧 Ashrafi 客户 APK。
- `apkdownload/.env`、`apkdownload/.env.d7pay`、`apkdownload/src/components/Appdownload/index.vue` 中旧客户兜底配置：D7pay 分支默认和兜底都必须落到 `d7pay_merchant`。
- `apkdownload/package.json`、`apkdownload/package-lock.json` 中旧 Lakshmi 包名：改为中性下载站包名，避免构建元信息泄漏旧项目名。
- `api/docker-compose.yml`：当前 D7pay 发布由 Jenkins/K8s 管理，不使用 API 本地 compose 作为运行入口。
- `api/static/v2/`：AdminLTE v2 静态包没有外部路由引用；当前 API 仍保留订单页静态资源，不删除 `api/static/images`、`api/static/order_page`。

## 验收标准

- `git ls-files` 不再列出上述明确垃圾路径。
- `rg` 检查不再出现 Lakshmi/Ashrafi APK 发布路径、PHP vendor 路径和 `.bak` 备份引用。
- API/admin/merchant 关键 Python 文件可编译。
- D7pay 发布合同检查通过。
- 构建与排错文档记录本轮清理边界，避免后续误删仍在路由中的旧业务代码。
