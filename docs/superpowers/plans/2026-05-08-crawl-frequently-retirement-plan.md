# crawl_frequently Redis 信号退役实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 全面退役 `crawl_frequently_{payment_id}` Redis 临时调度信号，避免账单采集重新依赖旧 Redis 运行态。

**Architecture:** 代收派单和 Lakshmi 抢单不再写 `crawl_frequently_*`；JazzCash worker 不再读取该 key 来决定短/长爬取间隔。EasyPaisa 账单调度继续以 MySQL 订单窗口为准，JazzCash 保留自身失败重试和既有时间间隔逻辑。Redis 仍只保留锁、通知、缓存和必要临时会话职责。

**Tech Stack:** Tornado/Aio handlers、Python workers、Redis、MySQL 订单窗口、unittest。

---

## 执行步骤

- [x] 搜索活跃后端代码中的 `crawl_frequently_*` 写入和读取点。
- [x] 删除 `api/application/pay/dispatch.py` 代收派单成功后的 `crawl_frequently_*` 写入。
- [x] 删除 `api/application/lakshmi_api/controllers/deposit_orders_controller.py` 抢单后的 `crawl_frequently_*` 写入。
- [x] 删除 `api/jobs/Jazzcashpay_v2.py` 对 `crawl_frequently_*` 的读取和调度判断。
- [x] 添加回归测试，断言活跃后端代码不再包含 `crawl_frequently_*`。
- [x] 同步 README、build、err 和相关 superpowers 文档。
- [x] 执行残留搜索、Python 编译、专项测试、空白检查和 GitNexus 验收。
- [ ] 提交并推送 `main`。

## 验收标准

- `rg -n "crawl_frequently_" api/application api/jobs admin merchant -S` 无匹配。
- `PYTHONPATH=api python3 -m unittest api.tests.test_crawl_frequently_retirement -v` 通过。
- 修改过的 Python 文件 `py_compile` 通过。
- `git diff --check` 通过。
- GitNexus 索引通过。
