import json
import time
from typing import Any, Dict, Optional

from application.jazzcash_runtime import keyspace
from application.jazzcash_runtime.flags import runtime_write_enabled


class JazzCashAdminRuntimeService:
    def __init__(self, redis, now_provider=None):
        self.redis = redis
        self.now_provider = now_provider or time.time
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

    @staticmethod
    def _flag_from_snapshot(current: Dict[str, Any], key: str, legacy_key: str, default: bool) -> bool:
        if key in current:
            return bool(current.get(key))
        if legacy_key in current:
            return bool(current.get(legacy_key))
        return default

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
            await self.redis.set(keyspace.snapshot_key(payment_id), json.dumps(snapshot, ensure_ascii=True))
            await self.redis.zadd(keyspace.INDEX_UPDATED_AT, {str(payment_id): snapshot["updated_at"]})
        return snapshot

    async def _sync_indexes(self, payment_id, snapshot: Dict[str, Any]):
        if not self.enabled:
            return
        if snapshot.get("online"):
            await self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)

        if snapshot.get("collect_enabled"):
            await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
        else:
            await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)

        if snapshot.get("ds_order_enabled"):
            await self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)

        if snapshot.get("df_order_enabled"):
            await self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            await self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)

    async def _mirror_active(self, payment_id, *, phone=None, dispatch_df=True, dispatch_ds=True, channels=None, previous_channels=None):
        if dispatch_df:
            await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            await self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)

        resolved_channels = keyspace.normalize_channels(channels)
        all_channels = []
        for channel in keyspace.normalize_channels(previous_channels) + resolved_channels:
            if channel not in all_channels:
                all_channels.append(channel)

        if dispatch_ds:
            await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in all_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            for channel in resolved_channels:
                await self.redis.rpush(keyspace.legacy_payment_active_channel_key(channel), payment_id)
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in all_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)

        await self.redis.setex(keyspace.legacy_login_on_payment_key(payment_id), 660, "1")
        if phone:
            await self.redis.setex(keyspace.legacy_login_on_phone_key(phone), 660, "1")

    async def _mirror_offline(self, payment_id, *, phone=None, channels=None):
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        for channel in keyspace.normalize_channels(channels):
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        await self.redis.delete(keyspace.legacy_login_on_payment_key(payment_id))
        if phone:
            await self.redis.delete(keyspace.legacy_login_on_phone_key(phone))

    async def pause_order_dispatch(self, payment_id, *, phone: Optional[str] = None, channels=None, source: str):
        current = await self.read_snapshot(payment_id) or {}
        is_online = bool(current.get("online"))
        resolved_channels = keyspace.normalize_channels(current.get("channels") if channels is None else channels)
        collect_enabled = bool(is_online and (current.get("collect_enabled") if "collect_enabled" in current else True))
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "online": is_online,
                "collect_enabled": collect_enabled,
                "ds_order_enabled": False,
                "df_order_enabled": False,
                "dispatch_ds": False,
                "dispatch_df": False,
                "channels": resolved_channels,
                "session_phase": current.get("session_phase"),
                "last_transition": source,
            },
            source=source,
        )
        await self._sync_indexes(payment_id, snapshot)
        await self._mirror_active(
            payment_id,
            phone=snapshot.get("phone"),
            dispatch_df=False,
            dispatch_ds=False,
            channels=resolved_channels,
            previous_channels=current.get("channels"),
        )
        return snapshot

    async def resume_order_dispatch(
        self,
        payment_id,
        *,
        ds_enabled: bool,
        df_enabled: bool = True,
        phone: Optional[str] = None,
        channels=None,
        source: str,
    ):
        current = await self.read_snapshot(payment_id) or {}
        is_online = bool(current.get("online"))
        resolved_channels = keyspace.normalize_channels(current.get("channels") if channels is None else channels)
        collect_enabled = bool(is_online and (current.get("collect_enabled") if "collect_enabled" in current else True))
        resolved_ds_order_enabled = bool(collect_enabled and ds_enabled)
        resolved_df_order_enabled = bool(collect_enabled and df_enabled)
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "online": is_online,
                "collect_enabled": collect_enabled,
                "ds_order_enabled": resolved_ds_order_enabled,
                "df_order_enabled": resolved_df_order_enabled,
                "dispatch_ds": resolved_ds_order_enabled,
                "dispatch_df": resolved_df_order_enabled,
                "channels": resolved_channels,
                "session_phase": current.get("session_phase"),
                "last_transition": source,
            },
            source=source,
        )
        await self._sync_indexes(payment_id, snapshot)
        await self._mirror_active(
            payment_id,
            phone=snapshot.get("phone"),
            dispatch_df=resolved_df_order_enabled,
            dispatch_ds=resolved_ds_order_enabled,
            channels=resolved_channels,
            previous_channels=current.get("channels"),
        )
        return snapshot

    async def set_ds_order_dispatch(self, payment_id, *, enabled: bool, phone=None, channels=None, source: str):
        current = await self.read_snapshot(payment_id) or {}
        if current.get("online"):
            return await self.resume_order_dispatch(
                payment_id,
                ds_enabled=enabled,
                df_enabled=self._flag_from_snapshot(current, "df_order_enabled", "dispatch_df", False),
                phone=phone or current.get("phone"),
                channels=channels if channels is not None else current.get("channels"),
                source=source,
            )
        return await self.pause_order_dispatch(
            payment_id,
            phone=phone or current.get("phone"),
            channels=channels if channels is not None else current.get("channels"),
            source=source,
        )

    async def force_offline(self, payment_id, *, phone=None, source: str, reason: str, channels=None):
        current = await self.read_snapshot(payment_id) or {}
        resolved_phone = phone or current.get("phone")
        resolved_channels = keyspace.normalize_channels(current.get("channels") if channels is None else channels)
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": resolved_phone,
                "online": False,
                "collect_enabled": False,
                "ds_order_enabled": False,
                "df_order_enabled": False,
                "dispatch_ds": False,
                "dispatch_df": False,
                "channels": resolved_channels,
                "session_phase": "offline",
                "last_transition": reason,
            },
            source=source,
        )
        await self._sync_indexes(payment_id, snapshot)
        await self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone:
            await self.redis.delete(keyspace.lock_phone_key(resolved_phone))
        await self._mirror_offline(payment_id, phone=resolved_phone, channels=resolved_channels)
        return snapshot

    async def force_reset(self, payment_id, *, source: str):
        current = await self.read_snapshot(payment_id) or {}
        snapshot = await self.force_offline(
            payment_id,
            phone=current.get("phone"),
            channels=current.get("channels"),
            source=source,
            reason=source,
        )
        await self.redis.delete(keyspace.session_key(payment_id))
        await self.redis.delete(keyspace.pre_login_key(payment_id))
        await self.redis.delete(keyspace.kickoff_key(payment_id))
        await self.redis.delete(keyspace.legacy_kickoff_key(payment_id))
        await self.redis.hdel(keyspace.JOB_HASH, payment_id)
        await self.redis.zrem(keyspace.JOB_SET, payment_id)
        await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        return snapshot
