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

    @staticmethod
    def _flag_from_snapshot(current: Dict[str, Any], key: str, legacy_key: str, default: bool) -> bool:
        if key in current:
            return bool(current.get(key))
        if legacy_key in current:
            return bool(current.get(legacy_key))
        return default

    def _is_health_paused_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> bool:
        if not snapshot or not snapshot.get("order_health_paused"):
            return False
        try:
            return int(snapshot.get("order_health_paused_until") or 0) > self._now()
        except Exception:
            return False

    async def read_snapshot(self, payment_id):
        return self._decode(await self.redis.get(keyspace.snapshot_key(payment_id)))

    async def is_manual_off(self, payment_id) -> bool:
        snapshot = await self.read_snapshot(payment_id)
        return bool(snapshot and snapshot.get("manual_ds_paused"))

    async def is_order_health_paused(self, payment_id) -> bool:
        snapshot = await self.read_snapshot(payment_id)
        return self._is_health_paused_snapshot(snapshot)

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
                "collect_enabled": False,
                "ds_order_enabled": False,
                "df_order_enabled": False,
                "dispatch_df": False,
                "dispatch_ds": False,
                "manual_ds_paused": False,
                "manual_ds_pause_reason": None,
                "order_health_paused": False,
                "order_health_pause_reason": None,
                "order_health_paused_until": 0,
                "channels": resolved_channels,
                "session_phase": "offline",
                "last_transition": reason,
            },
            source=source,
        )
        if self.enabled:
            await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
            await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        await self.redis.delete(keyspace.health_pause_order_key(payment_id))
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

    async def set_ds_order_dispatch(
        self,
        payment_id,
        *,
        enabled: bool,
        phone: Optional[str] = None,
        channels=None,
        source: str,
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )

        if current.get("online"):
            resolved_collect_enabled = bool(current.get("collect_enabled")) if "collect_enabled" in current else True
            resolved_ds_order_enabled = bool(enabled) and resolved_collect_enabled
            resolved_df_order_enabled = self._flag_from_snapshot(
                current,
                "df_order_enabled",
                "dispatch_df",
                False,
            )
            snapshot = await self.write_snapshot(
                payment_id,
                {
                    "phone": phone or current.get("phone"),
                    "collect_enabled": resolved_collect_enabled,
                    "ds_order_enabled": resolved_ds_order_enabled,
                    "df_order_enabled": resolved_df_order_enabled,
                    "dispatch_ds": resolved_ds_order_enabled,
                    "dispatch_df": resolved_df_order_enabled,
                    "channels": resolved_channels,
                    "last_transition": source,
                },
                source=source,
            )
            if self.enabled:
                if resolved_collect_enabled:
                    await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                    await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
                else:
                    await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                    await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
                if resolved_df_order_enabled:
                    await self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
                    await self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
                else:
                    await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
                    await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            if resolved_ds_order_enabled:
                if self.enabled:
                    await self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
                    await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
                await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
                for channel in resolved_channels:
                    await self.redis.rpush(keyspace.legacy_payment_active_channel_key(channel), payment_id)
            else:
                if self.enabled:
                    await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
                    await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
                await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
                for channel in resolved_channels:
                    await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            return snapshot

        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "collect_enabled": False,
                "ds_order_enabled": False,
                "dispatch_ds": False,
                "channels": resolved_channels,
                "last_transition": source,
            },
            source=source,
        )
        if self.enabled:
            await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        all_channels = keyspace.normalize_channels(current.get("channels")) + resolved_channels
        for channel in all_channels:
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        return snapshot

    async def set_collection_dispatch(
        self,
        payment_id,
        *,
        enabled: bool,
        phone: Optional[str] = None,
        channels=None,
        source: str,
    ) -> Dict[str, Any]:
        """兼容旧调用名：这里只控制代收 DS 派单，不控制采集。"""
        return await self.set_ds_order_dispatch(
            payment_id,
            enabled=enabled,
            phone=phone,
            channels=channels,
            source=source,
        )

    async def pause_order_dispatch(
        self,
        payment_id,
        *,
        phone: Optional[str] = None,
        channels=None,
        source: str,
    ) -> Dict[str, Any]:
        """后台禁用只暂停派单，不清登录态、不清 jobs 队列。"""
        current = await self.read_snapshot(payment_id) or {}
        is_online = bool(current.get("online"))
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        collect_enabled = (
            bool(current.get("collect_enabled")) if "collect_enabled" in current else is_online
        )
        collect_enabled = bool(is_online and collect_enabled)
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
        if self.enabled:
            if is_online:
                await self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
            else:
                await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
            if collect_enabled:
                await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
            else:
                await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
            await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            await self.redis.delete(f"easypaisa_runtime:kickoff:{payment_id}")
            await self.redis.delete(f"kick_off_{payment_id}")
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        if is_online:
            await self.redis.setex(keyspace.legacy_login_on_payment_key(payment_id), 660, "1")
            if snapshot.get("phone"):
                await self.redis.setex(keyspace.legacy_login_on_phone_key(snapshot["phone"]), 660, "1")
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
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        is_online = bool(current.get("online"))
        if await self.is_order_health_paused(payment_id):
            return await self.pause_order_dispatch(
                payment_id,
                phone=phone or current.get("phone"),
                channels=channels if channels is not None else current.get("channels"),
                source=source,
            )
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        collect_enabled = bool(is_online and (current.get("collect_enabled", True)))
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
        if self.enabled:
            if is_online:
                await self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
            if collect_enabled:
                await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
            if resolved_df_order_enabled:
                await self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
                await self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
            else:
                await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
                await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            if resolved_ds_order_enabled:
                await self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
                await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
            else:
                await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
                await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        if resolved_df_order_enabled:
            await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            await self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        if resolved_ds_order_enabled:
            await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            for channel in resolved_channels:
                await self.redis.rpush(keyspace.legacy_payment_active_channel_key(channel), payment_id)
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        if is_online:
            await self.redis.setex(keyspace.legacy_login_on_payment_key(payment_id), 660, "1")
            if snapshot.get("phone"):
                await self.redis.setex(keyspace.legacy_login_on_phone_key(snapshot["phone"]), 660, "1")
        return snapshot

    async def set_manual_off(self, payment_id, *, reason: str, ttl: Optional[int] = None) -> None:
        await self.write_snapshot(
            payment_id,
            {
                "manual_ds_paused": True,
                "manual_ds_pause_reason": reason,
                "last_transition": f"manual_off:{reason}",
            },
            source=f"manual_off:{reason}",
        )
        if ttl is None:
            await self.redis.set(keyspace.manual_off_collection_key(payment_id), reason)
        else:
            await self.redis.setex(keyspace.manual_off_collection_key(payment_id), ttl, reason)
        await self.set_ds_order_dispatch(payment_id, enabled=False, source=f"manual_off:{reason}")

    async def clear_manual_off(self, payment_id) -> None:
        await self.redis.delete(keyspace.manual_off_collection_key(payment_id))
        await self.write_snapshot(
            payment_id,
            {
                "manual_ds_paused": False,
                "manual_ds_pause_reason": None,
                "last_transition": "manual_off_cleared",
            },
            source="manual_off_cleared",
        )

    async def set_order_health_pause(
        self,
        payment_id,
        *,
        reason: str,
        ttl: int,
        source: str,
        phone: Optional[str] = None,
        channels=None,
    ) -> Dict[str, Any]:
        await self.write_snapshot(
            payment_id,
            {
                "order_health_paused": True,
                "order_health_pause_reason": reason,
                "order_health_paused_until": self._now() + int(ttl),
                "last_transition": source,
            },
            source=source,
        )
        await self.redis.setex(keyspace.health_pause_order_key(payment_id), ttl, reason)
        return await self.pause_order_dispatch(
            payment_id,
            phone=phone,
            channels=channels,
            source=source,
        )

    async def clear_order_health_pause(self, payment_id, *, source: str) -> Dict[str, Any]:
        await self.redis.delete(keyspace.health_pause_order_key(payment_id))
        return await self.write_snapshot(
            payment_id,
            {
                "order_health_paused": False,
                "order_health_pause_reason": None,
                "order_health_paused_until": 0,
                "last_transition": source,
            },
            source=source,
        )

    async def force_reset(self, payment_id, source: str, *, phone: Optional[str] = None):
        snapshot = await self.read_snapshot(payment_id) or {}
        await self.clear_session(payment_id)
        # clear pre_login / kickoff / job hash+set / manual_off / schedule_collection
        await self.redis.delete(f"pre_login_easypaisa_{payment_id}")
        await self.redis.delete(f"easypaisa_runtime:kickoff:{payment_id}")
        await self.redis.hdel(keyspace.JOB_HASH, str(payment_id))
        await self.redis.zrem(keyspace.JOB_SET, payment_id)
        await self.redis.delete(keyspace.manual_off_collection_key(payment_id))
        await self.redis.delete(keyspace.health_pause_order_key(payment_id))
        await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        return await self.force_offline(
            payment_id,
            phone=phone or snapshot.get("phone"),
            source=source,
            reason=source,
        )
