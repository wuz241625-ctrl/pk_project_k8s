# EasyPaisa Pending Fingerprint Binary Redis Design

- **日期**: 2026-05-16
- **范围**: 修复 EasyPaisa 指纹 ZIP 暂存在 Redis 后，`verify_fingerprint` 读取二进制 ZIP 时被 UTF-8 解码的问题。
- **不在范围**: 不改变当前 k8s 分支的 `file/files` 内部适配协议；当前 Controller 仍从 multipart `files` 读取，再以内部 `file` 传给 EasyPaisa。

## 背景

当前 API 主 Redis 客户端在 `api/main.py` 中以 `decode_responses=True` 创建，适合 session、锁、JSON 字符串等业务数据。EasyPaisa 指纹上传会把 ZIP bytes 写入 `easypaisa:pending_fp:{payment_id}`，随后 `verify_fingerprint_http` 再读取该 key 并推送云机。

ZIP 是二进制格式，内容通常包含非 UTF-8 字节。使用 decoded Redis 客户端读取时，Redis 客户端会尝试 UTF-8 解码，可能在读取阶段抛出 `UnicodeDecodeError`，导致请求尚未进入云机上传和指纹验证逻辑就失败。

## 设计

保留现有 `application.redis` 的字符串行为不变，新增专用二进制 Redis 客户端：

- `application.redis`: `decode_responses=True`，继续供 session、锁、JSON 字符串使用。
- `application.redis_binary`: `decode_responses=False`，只供指纹 ZIP 这类二进制 payload 使用。

EasyPaisa 增加两个窄口 helper：

- `_set_pending_fingerprint_zip(key, ttl, body)`: 写入 ZIP bytes。
- `_get_pending_fingerprint_zip(key)`: 读取 ZIP bytes。

helper 优先使用 `handler.application.redis_binary`；测试或旧运行环境没有该属性时回退到 `self.redis`，避免破坏现有单元测试替身。

## 数据流

```text
upload_fingerprint_http
  -> 校验 ZIP 类型、大小和会话状态
  -> _set_pending_fingerprint_zip("easypaisa:pending_fp:{payment_id}", ttl, file["body"])

verify_fingerprint_http
  -> _get_pending_fingerprint_zip("easypaisa:pending_fp:{payment_id}")
  -> _call_upload_data_bytes(session_data, zip_body)
  -> _call_verify_fingerprint(session_data)
  -> 成功后落盘并写 payment.fingerprint_path
```

## 错误处理

- pending key 不存在时继续返回当前业务错误，提示先调用 `upload_fingerprint`。
- 二进制 Redis 读取异常时沿用 `verify_fingerprint_http` 的外层异常处理，返回 `ErrorCode.VerifyFingerPrint`。
- 不改变云机拒绝、冷却、session 过期、MySQL 写入失败等既有分支。

## 验收标准

1. `verify_fingerprint_http` 读取 pending ZIP 时必须走 `redis_binary`，即使普通 `redis.get()` 会触发 UTF-8 解码异常，也不能影响验证流程。
2. `upload_fingerprint_http` 写 pending ZIP 时必须写入 `redis_binary`，值保持 bytes。
3. `application.redis` 仍保持 `decode_responses=True`，不影响现有字符串 Redis 逻辑。
4. `api/main.py` 创建并挂载 `redis_binary`。
5. 新增回归测试覆盖二进制 Redis 读取路径，并先红后绿。
6. EasyPaisa 指纹相关测试通过，`api/main.py` 与 `easypaisa.py` 语法检查通过。
7. `err.md` 同步记录根因、处理和验证命令。
