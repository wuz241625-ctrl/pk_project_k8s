import json
from typing import Any, Dict, Optional

from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.legacy_bridge import EasyPaisaLegacyBridge


class EasyPaisaRuntimeService:
    def __init__(self, redis, now_provider=None):
        self.redis = redis
        self.now_provider = now_provider or __import__("time").time
        self.legacy_bridge = EasyPaisaLegacyBridge(redis)

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

    async def read_snapshot(self, payment_id) -> Optional[Dict[str, Any]]:
        return self._decode(await self.redis.get(keyspace.snapshot_key(payment_id)))

    async def read_session(self, payment_id) -> Optional[Dict[str, Any]]:
        return self._decode(await self.redis.get(keyspace.session_key(payment_id)))

    async def write_snapshot(self, payment_id, patch: Dict[str, Any], source: str) -> Dict[str, Any]:
        snapshot = await self.read_snapshot(payment_id) or {
            "schema_version": keyspace.SCHEMA_VERSION,
            "payment_id": payment_id,
        }
        snapshot.update(patch)
        snapshot["schema_version"] = keyspace.SCHEMA_VERSION
        snapshot["payment_id"] = payment_id
        snapshot["last_source"] = source
        snapshot["updated_at"] = self._now()

        raw = json.dumps(snapshot, ensure_ascii=True)
        await self.redis.set(keyspace.snapshot_key(payment_id), raw)
        await self.redis.zadd(keyspace.INDEX_UPDATED_AT, {payment_id: snapshot["updated_at"]})
        return snapshot

    async def write_session(self, payment_id, session_data: Dict[str, Any], ttl: Optional[int] = None) -> Dict[str, Any]:
        payload = dict(session_data)
        payload["schema_version"] = keyspace.SCHEMA_VERSION
        raw = json.dumps(payload, ensure_ascii=True)
        if ttl is not None:
            await self.redis.setex(keyspace.session_key(payment_id), ttl, raw)
        else:
            await self.redis.set(keyspace.session_key(payment_id), raw)
        return payload

    async def clear_session(self, payment_id):
        await self.redis.delete(keyspace.session_key(payment_id))

    async def store_account_selection(
        self,
        payment_id,
        *,
        account_options,
        selected_accno: Optional[str],
        selected_iban: Optional[str],
        source: str,
    ) -> Dict[str, Any]:
        return await self.write_snapshot(
            payment_id,
            {
                "account_options": account_options,
                "selected_accno": selected_accno,
                "selected_iban": selected_iban,
                "session_phase": "accountSelectionRequired",
            },
            source=source,
        )

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
        channels=None,
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        resolved_dispatch_ds = current.get("dispatch_ds", False) if dispatch_ds is None else bool(dispatch_ds)
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "online": True,
                "dispatch_df": bool(dispatch_df),
                "dispatch_ds": resolved_dispatch_ds,
                "selected_accno": selected_accno if selected_accno is not None else current.get("selected_accno"),
                "selected_iban": selected_iban if selected_iban is not None else current.get("selected_iban"),
                "channels": resolved_channels,
                "session_phase": "activeSuccessful",
                "last_transition": "activeSuccessful",
            },
            source=source,
        )
        await self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
        if snapshot.get("dispatch_df"):
            await self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
        if snapshot.get("dispatch_ds"):
            await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.legacy_bridge.mirror_active(
            payment_id,
            phone=snapshot.get("phone"),
            online_ttl=online_ttl,
            dispatch_df=snapshot.get("dispatch_df", False),
            dispatch_ds=snapshot.get("dispatch_ds", False),
            channels=snapshot.get("channels"),
            previous_channels=current.get("channels"),
        )
        return snapshot

    async def set_collection_dispatch(
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
                dispatch_df=current.get("dispatch_df", False),
                dispatch_ds=bool(enabled),
                channels=resolved_channels,
            )

        snapshot = await self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "dispatch_ds": False,
                "channels": resolved_channels,
                "last_transition": source,
            },
            source=source,
        )
        await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        return snapshot

    async def force_offline(self, payment_id, *, phone=None, source: str, reason: str, channels=None) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        resolved_phone = phone or current.get("phone")
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
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
        await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone or snapshot.get("phone"):
            await self.redis.delete(keyspace.lock_phone_key(resolved_phone or snapshot.get("phone")))
        await self.legacy_bridge.mirror_offline(
            payment_id,
            phone=resolved_phone or snapshot.get("phone"),
            channels=resolved_channels,
        )
        return snapshot

    async def force_reset(self, payment_id, *, phone=None, source: str) -> Dict[str, Any]:
        snapshot = await self.read_snapshot(payment_id) or {}
        await self.clear_session(payment_id)
        return await self.force_offline(
            payment_id,
            phone=phone or snapshot.get("phone"),
            source=source,
            reason=source,
        )
