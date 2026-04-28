import json
import time
from typing import Any, Dict, Optional

from application.jazzcash_runtime import keyspace
from application.jazzcash_runtime.flags import runtime_write_enabled
from application.jazzcash_runtime.legacy_bridge import JazzCashLegacyBridge


class JazzCashRuntimeService:
    def __init__(self, redis, now_provider=None):
        self.redis = redis
        self.now_provider = now_provider or time.time
        self.enabled = runtime_write_enabled()
        self.legacy_bridge = JazzCashLegacyBridge(redis)

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

    async def read_session(self, payment_id):
        return self._decode(await self.redis.get(keyspace.session_key(payment_id)))

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

    async def write_session(self, payment_id, session_data: Dict[str, Any], ttl: int):
        if self.enabled:
            await self.redis.setex(keyspace.session_key(payment_id), ttl, json.dumps(session_data, ensure_ascii=True))

    async def clear_session(self, payment_id):
        await self.redis.delete(keyspace.session_key(payment_id))

    async def clear_snapshot(self, payment_id):
        await self.redis.delete(keyspace.snapshot_key(payment_id))
        await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
        await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
        await self.redis.zrem(keyspace.INDEX_UPDATED_AT, payment_id)
        await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)

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

    async def mark_active_successful(
        self,
        payment_id,
        *,
        phone: Optional[str] = None,
        selected_accno: Optional[str],
        selected_iban: Optional[str],
        source: str,
        online_ttl: int = 660,
        dispatch_df: bool = True,
        dispatch_ds: Optional[bool] = None,
        collect_enabled: Optional[bool] = None,
        ds_order_enabled: Optional[bool] = None,
        df_order_enabled: Optional[bool] = None,
        channels=None,
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}

        if collect_enabled is None:
            resolved_collect_enabled = bool(current.get("collect_enabled")) if "collect_enabled" in current else True
            if dispatch_ds is True:
                resolved_collect_enabled = True
        else:
            resolved_collect_enabled = bool(collect_enabled)

        if ds_order_enabled is None:
            if dispatch_ds is None:
                resolved_ds_order_enabled = self._flag_from_snapshot(
                    current,
                    "ds_order_enabled",
                    "dispatch_ds",
                    True,
                )
            else:
                resolved_ds_order_enabled = bool(dispatch_ds)
        else:
            resolved_ds_order_enabled = bool(ds_order_enabled)

        if df_order_enabled is None:
            resolved_df_order_enabled = bool(dispatch_df)
        else:
            resolved_df_order_enabled = bool(df_order_enabled)

        if not resolved_collect_enabled:
            resolved_ds_order_enabled = False
            resolved_df_order_enabled = False

        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "online": True,
                "collect_enabled": resolved_collect_enabled,
                "ds_order_enabled": resolved_ds_order_enabled,
                "df_order_enabled": resolved_df_order_enabled,
                "dispatch_ds": resolved_ds_order_enabled,
                "dispatch_df": resolved_df_order_enabled,
                "selected_accno": selected_accno if selected_accno is not None else current.get("selected_accno"),
                "selected_iban": selected_iban if selected_iban is not None else current.get("selected_iban"),
                "channels": resolved_channels,
                "session_phase": "activeSuccessful",
                "last_transition": "activeSuccessful",
                "session_expires_at": self._now() + int(online_ttl or 0),
                "cd_until": 0,
                "cooldown_until": 0,
                "last_error": None,
            },
            source=source,
        )
        await self._sync_indexes(payment_id, snapshot)
        await self.redis.delete(keyspace.kickoff_key(payment_id))
        await self.legacy_bridge.clear_kickoff(payment_id)
        await self.legacy_bridge.mirror_active(
            payment_id,
            phone=snapshot.get("phone"),
            online_ttl=online_ttl,
            dispatch_df=snapshot.get("df_order_enabled", False),
            dispatch_ds=snapshot.get("ds_order_enabled", False),
            channels=snapshot.get("channels"),
            previous_channels=current.get("channels"),
        )
        return snapshot

    async def set_ds_order_dispatch(
        self,
        payment_id,
        *,
        enabled: bool,
        phone: Optional[str] = None,
        channels=None,
        source: str,
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        if current.get("online"):
            return await self.mark_active_successful(
                payment_id,
                phone=phone or current.get("phone"),
                selected_accno=current.get("selected_accno"),
                selected_iban=current.get("selected_iban"),
                source=source,
                online_ttl=online_ttl,
                collect_enabled=bool(current.get("collect_enabled")) if "collect_enabled" in current else True,
                ds_order_enabled=bool(enabled),
                df_order_enabled=self._flag_from_snapshot(current, "df_order_enabled", "dispatch_df", False),
                channels=resolved_channels,
            )

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
        await self._sync_indexes(payment_id, snapshot)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        return snapshot

    async def set_collection_dispatch(self, payment_id, **kwargs) -> Dict[str, Any]:
        return await self.set_ds_order_dispatch(payment_id, **kwargs)

    async def set_df_order_dispatch(
        self,
        payment_id,
        *,
        enabled: bool,
        phone: Optional[str] = None,
        channels=None,
        source: str,
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        """只控制 JazzCashBusiness 代付 DF 派单资格，不改变代收派单资格。"""
        current = await self.read_snapshot(payment_id) or {}
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )

        if current.get("online"):
            return await self.mark_active_successful(
                payment_id,
                phone=phone or current.get("phone"),
                selected_accno=current.get("selected_accno"),
                selected_iban=current.get("selected_iban"),
                source=source,
                online_ttl=online_ttl,
                collect_enabled=bool(current.get("collect_enabled")) if "collect_enabled" in current else True,
                ds_order_enabled=self._flag_from_snapshot(current, "ds_order_enabled", "dispatch_ds", False),
                df_order_enabled=bool(enabled),
                channels=resolved_channels,
            )

        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "df_order_enabled": False,
                "dispatch_df": False,
                "channels": resolved_channels,
                "last_transition": source,
            },
            source=source,
        )
        await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
        await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        return snapshot

    async def pause_order_dispatch(self, payment_id, *, phone=None, channels=None, source: str) -> Dict[str, Any]:
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
        await self.legacy_bridge.mirror_active(
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
        ds_enabled: bool = True,
        df_enabled: bool = True,
        phone: Optional[str] = None,
        channels=None,
        source: str,
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        return await self.mark_active_successful(
            payment_id,
            phone=phone or current.get("phone"),
            selected_accno=current.get("selected_accno"),
            selected_iban=current.get("selected_iban"),
            source=source,
            online_ttl=online_ttl,
            collect_enabled=True,
            ds_order_enabled=bool(ds_enabled),
            df_order_enabled=bool(df_enabled),
            channels=channels if channels is not None else current.get("channels"),
        )

    async def set_kickoff(self, payment_id, *, phone=None, ttl: int, source: str, reason: str):
        current = await self.read_snapshot(payment_id) or {}
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "last_transition": reason,
                "kickoff": True,
                "kickoff_until": self._now() + int(ttl),
            },
            source=source,
        )
        if self.enabled:
            await self.redis.setex(keyspace.kickoff_key(payment_id), ttl, reason)
        await self.legacy_bridge.mirror_kickoff(payment_id, ttl)
        return snapshot

    async def force_offline(self, payment_id, *, phone=None, source: str, reason: str, channels=None) -> Dict[str, Any]:
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
        await self.legacy_bridge.mirror_offline(payment_id, phone=resolved_phone, channels=resolved_channels)
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
        await self.legacy_bridge.clear_kickoff(payment_id)
        await self.redis.hdel(keyspace.JOB_HASH, payment_id)
        await self.redis.zrem(keyspace.JOB_SET, payment_id)
        await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        return snapshot
