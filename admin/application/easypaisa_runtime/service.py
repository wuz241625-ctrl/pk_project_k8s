import json
from typing import Any, Dict, Optional

from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.flags import runtime_write_enabled


class EasyPaisaAdminRuntimeService:
    def __init__(self, redis, now_provider=None):
        self.redis = redis
        self.now_provider = now_provider or __import__("time").time
        self.enabled = runtime_write_enabled()

    def _now(self) -> int:
        return int(self.now_provider())

    @staticmethod
    def _decode(raw: Any) -> Optional[Dict[str, Any]]:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            return json.loads(raw)
        if isinstance(raw, dict):
            return raw
        raise TypeError(f"unsupported runtime payload: {type(raw)!r}")

    async def read_snapshot(self, payment_id):
        return self._decode(await self.redis.get(keyspace.snapshot_key(payment_id)))

    async def write_snapshot(self, payment_id, patch: Dict[str, Any], source: str):
        snapshot = await self.read_snapshot(payment_id) or {
            "schema_version": keyspace.SCHEMA_VERSION,
            "payment_id": payment_id,
        }
        snapshot.update(patch)
        snapshot["schema_version"] = keyspace.SCHEMA_VERSION
        snapshot["payment_id"] = payment_id
        snapshot["last_source"] = source
        snapshot["updated_at"] = self._now()

        if self.enabled:
            raw = json.dumps(snapshot, ensure_ascii=True)
            await self.redis.set(keyspace.snapshot_key(payment_id), raw)
            await self.redis.zadd(keyspace.INDEX_UPDATED_AT, {payment_id: snapshot["updated_at"]})
        return snapshot

    async def clear_session(self, payment_id):
        await self.redis.delete(keyspace.session_key(payment_id))

    async def force_offline(self, payment_id, *, phone=None, source: str, reason: str):
        current = await self.read_snapshot(payment_id) or {}
        resolved_phone = phone or current.get("phone")
        resolved_channels = keyspace.normalize_channels(current.get("channels"))
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": resolved_phone,
                "online": False,
                "dispatch_df": False,
                "dispatch_ds": False,
                "channels": resolved_channels,
                "session_phase": "offline",
                "last_transition": reason,
            },
            source=source,
        )
        if self.enabled:
            await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone:
            await self.redis.delete(keyspace.lock_phone_key(resolved_phone))
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        for channel in resolved_channels:
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        await self.redis.delete(keyspace.legacy_login_on_payment_key(payment_id))
        if resolved_phone:
            await self.redis.delete(keyspace.legacy_login_on_phone_key(resolved_phone))
        return snapshot

    async def force_reset(self, payment_id, source: str):
        snapshot = await self.read_snapshot(payment_id) or {}
        await self.clear_session(payment_id)
        return await self.force_offline(
            payment_id,
            phone=snapshot.get("phone"),
            source=source,
            reason=source,
        )
