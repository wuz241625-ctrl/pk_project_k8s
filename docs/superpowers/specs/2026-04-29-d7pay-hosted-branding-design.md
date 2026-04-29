# D7pay 托管品牌与租户配置设计

## 背景

客户平台名称确定为 D7pay，交付方式为托管使用。目标是先把 D7pay 作为专属实例的品牌和租户配置落地，避免通过长期 Git 分支复制一套“他们系统”，也避免把核心业务逻辑改成客户专属代码。

## 方案比较

方案一是长期客户分支。优点是短期看起来隔离清楚，缺点是 JCB、EasyPaisa、余额流水、白名单等修复需要重复 cherry-pick，长期一定分叉。

方案二是共享 SaaS 加全库 `tenant_id`。优点是资源省，缺点是当前订单、余额、Runtime、指纹、Redis key、采集脚本、代付脚本都要改，风险过高。

方案三是同一主干加托管专属实例配置。优点是代码统一、数据隔离、部署独立、可快速交付；缺点是每个客户占用独立资源。当前选择方案三。

## 设计

D7pay 以 `ops/tenants/d7pay/tenant.yaml` 作为租户配置入口，记录品牌名、域名、namespace、数据库、Redis、fingerprint、apkdownload 和 App 构建参数。admin-h5 和 merchant-h5 增加 `d7pay:prod` 构建脚本，继续复用现有构建机制。apkdownload 增加 Vite mode `d7pay`，通过 `VITE_APP_KEY=d7pay_merchant` 读取 D7pay App 元信息。Flutter App 通过 `APP_DISPLAY_NAME` 和 `APP_SHORT_NAME` 切换展示名，不改 package name。

## 数据与安全边界

D7pay 不复制我们的真实订单、真实商户、真实码商、真实指纹、真实密钥。D7pay 上线时必须使用独立 MySQL database、独立 Redis、独立 `/fingerprint/d7pay` 和独立 apkdownload 目录。客户没有源码、服务器、K8s、MySQL、Redis 权限。

## 验收标准

admin、merchant、apkdownload 均可按 D7pay mode 构建。Flutter 可用 D7pay 展示名构建。D7pay 租户配置和交付文档存在。上线前按 `ops/tenants/d7pay/acceptance.md` 验证品牌、隔离、数据、业务和运维。
