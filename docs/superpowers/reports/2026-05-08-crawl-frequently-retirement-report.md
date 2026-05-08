# crawl_frequently Redis 信号退役验收报告

## 背景

`crawl_frequently_{payment_id}` 曾用于派单成功后通知账单 worker 短时间加速采集。但 EasyPaisa 已切到 MySQL 订单窗口驱动，JazzCash 也不应再依赖这个旧 Redis 调度信号。该 key 不是业务最终态，也不应继续作为账单调度输入。

## 本次变更

- 删除代收派单成功后写入 `crawl_frequently_*`。
- 删除 Lakshmi 抢单成功后写入 `crawl_frequently_*`。
- 删除 JazzCash worker 读取 `crawl_frequently_*` 决定短间隔的逻辑。
- 新增回归测试，扫描活跃后端代码，防止重新引入该 key。
- 同步 README、build、err 和相关 superpowers 文档。

## 保留边界

- Redis 锁、通知 PubSub、短 TTL 幂等锁、上号会话和可重建缓存不属于本次清理对象。
- 历史迁移报告可能仍记录过去曾经写入 `crawl_frequently_*` 的事实，不代表当前运行链路仍使用。

## 验收命令

```bash
rg -n "crawl_frequently_" api/application api/jobs admin merchant -S
PYTHONPATH=api python3 -m unittest api.tests.test_crawl_frequently_retirement -v
python3 -m py_compile api/application/pay/dispatch.py api/application/lakshmi_api/controllers/deposit_orders_controller.py api/jobs/Jazzcashpay_v2.py
git diff --check
npx gitnexus analyze --skip-agents-md --worker-timeout 120 --max-file-size 32768
```

## 验收结果

- 活跃后端代码残留搜索：无匹配，退出码 `1` 符合预期。
- 专项回归测试：1 test，`OK`。
- 修改文件 Python 编译：通过。
- `git diff --check`：通过。
- GitNexus 索引：通过。
