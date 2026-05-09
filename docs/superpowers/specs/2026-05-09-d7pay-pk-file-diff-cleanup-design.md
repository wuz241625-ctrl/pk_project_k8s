# D7pay 与 pk_project 文件差异清理设计

## 背景

本次按文件对比 `/Users/tear/pk_project` 与 `/Users/tear/pk_project_k8s` 的 `api`、`admin`、`merchant` 后端目录。D7pay 不是 pk_project 的字节级镜像，必须保留租户化、K8s/Jenkins、真实 IP 识别和 UTC 存储/巴基斯坦展示时区差异。

## 设计结论

保留以下 D7pay 差异：

- `application/client_ip.py` 与 `BaseHandler.get_ip()` 的真实客户端 IP 解析。
- `application/timezone.py` 与 `display_today_between()` 默认查询日界。
- `api/jobs/pakistanpay_v2.py` 中 EasyPaisa `tradeTime` 按巴基斯坦时间转 UTC 后匹配数据库 UTC 时间。
- `config.example.py`、`build.md`、`err.md`、D7pay 专属测试和 K8s/Jenkins 说明。

清理以下残留：

- `api/application/websocket/bank_analysis.py` 中 pk_project 已删除、D7pay 当前业务不用的旧印度钱包解析函数：`indusind`、`freecharge`、`mobikwik`、`maharastra`。
- `admin/application/count/collect_partner.py` 中已无路由使用的旧 `getPartner` / `getOnlinePayment` 注释块，其中包含旧 Redis 在线集合 `payment_online_ds` / `payment_online_df`。
- `api/application/lakshmi_api/controllers/http_login_controller.py` 中不存在的 `JioBank` 注释。

## 验收标准

- `api/application/websocket/bank_analysis.py` 不再包含 `async def indusind`、`async def freecharge`、`async def mobikwik`、`async def maharastra`。
- 运行时源码不再出现旧注释中的 `payment_online_ds` / `payment_online_df`。
- `http_login_controller.py` 不再出现不存在的 `JioBank` 注释。
- 旧印度钱包退役测试通过。
- API/Admin/Merchant 编译检查通过。
