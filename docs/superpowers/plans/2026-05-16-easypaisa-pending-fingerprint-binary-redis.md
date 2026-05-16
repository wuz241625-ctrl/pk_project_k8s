# EasyPaisa Pending Fingerprint Binary Redis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 EasyPaisa pending 指纹 ZIP 使用二进制 Redis 客户端读写，避免 `verify_fingerprint` 在读取 ZIP 时触发 UTF-8 解码失败。

**Architecture:** 保留现有 decoded Redis 作为默认业务客户端，新增 `redis_binary` 专门处理 ZIP bytes。EasyPaisa 通过两个 helper 读写 `easypaisa:pending_fp:{payment_id}`，避免二进制存取散落在流程里。

**Tech Stack:** Python 3、Tornado、redis.asyncio、pytest、unittest.mock。

---

## File Structure

| 文件 | 责任 | 改动 |
|---|---|---|
| `api/main.py` | API 应用启动与全局资源挂载 | 新增 `redis_binary` 客户端并传入 `Application` |
| `api/application/app/login/banks/easypaisa.py` | EasyPaisa 登录与指纹流程 | 增加 pending ZIP 二进制 Redis helper，替换 pending ZIP 读写点 |
| `api/tests/test_easypaisa_v19_fingerprint.py` | EasyPaisa 指纹流程回归测试 | 新增 `verify_fingerprint` 使用 binary Redis 读取 ZIP 的测试 |
| `err.md` | 项目排错索引 | 记录本次二进制 Redis 根因与验证命令 |

## Task 1: 写失败测试

- [x] **Step 1: 新增测试 `test_verify_fingerprint_reads_pending_zip_from_binary_redis`**

测试构造两个 Redis 替身：

```python
decoded_redis.get = AsyncMock(side_effect=UnicodeDecodeError('utf-8', b'\xaf', 0, 1, 'invalid start byte'))
binary_redis.get = AsyncMock(return_value=b'PK\x03\x04\xafzip')
handler.application = MagicMock(redis_binary=binary_redis)
```

期望 `verify_fingerprint_http()` 能成功调用 `_call_upload_data_bytes(session, b'PK\x03\x04\xafzip')`，并不调用 decoded redis 的 pending 读取路径。

- [x] **Step 2: 运行单测确认失败**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py::test_verify_fingerprint_reads_pending_zip_from_binary_redis -q
```

Expected:

```text
FAILED
```

失败原因应表明当前代码还没有 `_get_pending_fingerprint_zip`/`redis_binary` 路径，或仍调用 decoded Redis 读取 pending ZIP。

## Task 2: 实现 binary Redis helper

- [x] **Step 1: 修改 `EasyPaisa.__init__`**

从 handler application 上读取可选的 `redis_binary`：

```python
app = vars(request_handler).get('application')
self.redis_binary = vars(app).get('redis_binary') if app is not None else None
```

- [x] **Step 2: 增加 helper**

```python
def _get_binary_redis(self):
    return self.redis_binary or self.redis

async def _set_pending_fingerprint_zip(self, key, ttl, body):
    return await self._get_binary_redis().setex(key, ttl, body)

async def _get_pending_fingerprint_zip(self, key):
    return await self._get_binary_redis().get(key)
```

- [x] **Step 3: 替换 pending ZIP 读写**

`upload_fingerprint_http`:

```python
await self._set_pending_fingerprint_zip(pending_key, 600, file["body"])
```

`verify_fingerprint_http`:

```python
zip_body = await self._get_pending_fingerprint_zip(pending_key)
```

## Task 3: 挂载 API binary Redis 客户端

- [x] **Step 1: 修改 `Application.__init__` 签名**

```python
def __init__(self, db, db_orm, redispool, redis_binary, redis_pub, redis_sub, logger):
    self.redis = redispool
    self.redis_binary = redis_binary
```

- [x] **Step 2: 启动时创建 binary Redis**

```python
redis = aioredis.from_url('redis://%s' % conf['redis_host'], encoding="utf-8", decode_responses=True)
redis_binary = aioredis.from_url('redis://%s' % conf['redis_host'], decode_responses=False)
```

- [x] **Step 3: 传入 Application**

```python
app = Application(db, db_orm, redis, redis_binary, redis_pub, redis_sub, logger)
```

## Task 4: 文档和验收

- [x] **Step 1: 更新 `err.md`**

新增条目记录：

- 现象：`verify_fingerprint` 读取 pending ZIP 可能触发 UTF-8 解码失败。
- 根因：主 Redis 客户端 `decode_responses=True` 不适合 ZIP bytes。
- 处理：新增并使用 `redis_binary`。
- 验证命令。

- [x] **Step 2: 跑验收命令**

Run:

```bash
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py::test_verify_fingerprint_reads_pending_zip_from_binary_redis -q
python3 -m pytest api/tests/test_easypaisa_v19_fingerprint.py -q
python3 -m py_compile api/main.py api/application/app/login/banks/easypaisa.py
npx gitnexus detect-changes
```

Expected:

```text
全部测试和语法检查通过，GitNexus 变更范围只覆盖 EasyPaisa 指纹 pending ZIP 与 API 启动 Redis 客户端。
```
