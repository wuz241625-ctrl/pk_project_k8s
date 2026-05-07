# D7pay Indus/Jio/Maha 死代码清理设计

## 背景

GitNexus 已为当前 `d7pay` 分支建立最新索引，当前提交为 `641ff6d`。图谱显示下列文件或入口没有外部 `IMPORTS` incoming，并且 D7pay 当前 HTTP 上号控制器只支持 `easypaisa` 与 `jazzcash`。

## 方案

本轮只清理已经明确不属于 D7pay 运行链路的旧实现和制品，不触碰仍被路由挂载的 `/v1` App 接口、代收代付主入口、JazzCash/EasyPaisa worker、三方回调和数据库业务配置。

删除范围：

- `api/jobs/freecharge-monitor/php/`：旧 Freecharge PHP 交互式脚本，GitNexus 显示无外部引用，且 vendor 已经在上一轮清理。
- `api/application/app/login/banks/gcash_bank.py`：GCash 独立登录实现，HTTP 登录控制器没有导入或分发到该类。
- `api/application/app/login/banks/indus_bank.py`：Indus 独立登录实现，HTTP 登录控制器没有导入或分发到该类。
- `api/docker/`：旧 API 本地 Docker 配套文件；D7pay 发布以 Jenkins/K8s 为准，不通过该目录构建。
- `api/jobs/induspay/`、`api/jobs/jio/`、`api/jobs/maha/`：旧印度钱包 worker 目录，主入口在 GitNexus 中无外部 incoming，D7pay 运维脚本和文档不引用这些 worker。
- `merchant/.config.py.swp`：被 Git 跟踪的 Vim swap 文件，属于编辑器临时文件且可能携带旧线上配置痕迹。

## 保留边界

- 保留 `api/application/lakshmi_api/`，因为它仍承载 Flutter App `/v1` 接口。
- 保留 `api/jobs/pakistanpay_v2.py`、`api/jobs/easypaisa/*`、`api/jobs/jazzcash/*`、`api/jobs/Jazzcashpay_v2.py`，这些仍属于当前或测试覆盖的 EasyPaisa/JazzCash 运行链路。
- 保留 `api/application/pay/order.py`、`api/application/phonepe/*`、`api/application/third/*` 中旧分支。它们仍被路由或业务回调引用，后续要清理必须先同步数据库配置、菜单权限和线上流量。

## 验收标准

- `git ls-files` 不再列出本轮删除路径。
- `rg` 不再发现业务代码引用已删除的文件路径或模块名。
- API/admin/merchant 关键 Python 文件可编译。
- D7pay 发布合同检查通过，并能拦截这些路径回流。
- 文档记录本轮清理范围和保留边界。
