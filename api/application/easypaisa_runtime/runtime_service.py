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

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _is_payment_id_alias_entry(entry: Optional[Dict[str, Any]], payment_id) -> bool:
        if not isinstance(entry, dict):
            return False
        if entry.get("kind") != "payment_id_alias":
            return False
        return str(entry.get("target_payment_id") or "").strip() == str(payment_id)

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

    async def _clear_pre_login_aliases(self, payment_id):
        if not hasattr(self.redis, "scan_iter"):
            return

        iterator = self.redis.scan_iter("pre_login_easypaisa_*")
        if hasattr(iterator, "__aiter__"):
            keys = []
            async for raw_key in iterator:
                keys.append(self._text(raw_key))
            for key in keys:
                entry = self._decode(await self.redis.get(key))
                if self._is_payment_id_alias_entry(entry, payment_id):
                    await self.redis.delete(key)
            return

        for key in [self._text(raw_key) for raw_key in iterator]:
            entry = self._decode(await self.redis.get(key))
            if self._is_payment_id_alias_entry(entry, payment_id):
                await self.redis.delete(key)

    async def read_snapshot(self, payment_id) -> Optional[Dict[str, Any]]:
        return self._decode(await self.redis.get(keyspace.snapshot_key(payment_id)))

    async def read_session(self, payment_id) -> Optional[Dict[str, Any]]:
        return self._decode(await self.redis.get(keyspace.session_key(payment_id)))

    async def is_manual_off(self, payment_id) -> bool:
        snapshot = await self.read_snapshot(payment_id)
        return bool(snapshot and snapshot.get("manual_ds_paused"))

    async def is_order_health_paused(self, payment_id) -> bool:
        snapshot = await self.read_snapshot(payment_id)
        return self._is_health_paused_snapshot(snapshot)

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
                    False,
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
                "dispatch_df": resolved_df_order_enabled,
                "dispatch_ds": resolved_ds_order_enabled,
                "selected_accno": selected_accno if selected_accno is not None else current.get("selected_accno"),
                "selected_iban": selected_iban if selected_iban is not None else current.get("selected_iban"),
                "channels": resolved_channels,
                "session_phase": "activeSuccessful",
                "last_transition": "activeSuccessful",
            },
            source=source,
        )
        await self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
        if snapshot.get("collect_enabled"):
            await self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
        else:
            await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        if snapshot.get("df_order_enabled"):
            await self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            await self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
        if snapshot.get("ds_order_enabled"):
            await self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
        else:
            await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
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
                df_order_enabled=self._flag_from_snapshot(current, "df_order_enabled", "dispatch_df", False),
                ds_order_enabled=bool(enabled),
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
        await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
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
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        """兼容旧调用名：这里只控制代收 DS 派单，不控制采集。"""
        return await self.set_ds_order_dispatch(
            payment_id,
            enabled=enabled,
            phone=phone,
            channels=channels,
            source=source,
            online_ttl=online_ttl,
        )

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
        """只控制代付 DF 派单资格，不改变代收派单资格。"""
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

    async def pause_order_dispatch(
        self,
        payment_id,
        *,
        phone: Optional[str] = None,
        channels=None,
        source: str,
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        """后台禁用只暂停派单，不销毁仍可用于采集的登录态。"""
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
        await self.redis.delete(keyspace.kickoff_key(payment_id))
        await self.legacy_bridge.clear_kickoff(payment_id)
        if is_online:
            await self.legacy_bridge.mirror_active(
                payment_id,
                phone=snapshot.get("phone"),
                online_ttl=online_ttl,
                dispatch_df=False,
                dispatch_ds=False,
                channels=resolved_channels,
                previous_channels=current.get("channels"),
            )
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
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
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        current = await self.read_snapshot(payment_id) or {}
        if not current.get("online"):
            return await self.pause_order_dispatch(
                payment_id,
                phone=phone or current.get("phone"),
                channels=channels if channels is not None else current.get("channels"),
                source=source,
            )
        if await self.is_order_health_paused(payment_id):
            return await self.pause_order_dispatch(
                payment_id,
                phone=phone or current.get("phone"),
                channels=channels if channels is not None else current.get("channels"),
                source=source,
            )
        return await self.mark_active_successful(
            payment_id,
            phone=phone or current.get("phone"),
            selected_accno=current.get("selected_accno"),
            selected_iban=current.get("selected_iban"),
            source=source,
            online_ttl=online_ttl,
            collect_enabled=bool(current.get("collect_enabled")) if "collect_enabled" in current else True,
            ds_order_enabled=bool(ds_enabled),
            df_order_enabled=bool(df_enabled),
            channels=channels if channels is not None else current.get("channels"),
        )

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

    async def schedule_collection(self, payment_id, *, next_at: int) -> None:
        await self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): next_at})

    async def requeue_ds_if_online(self, payment_id, *, channels=None, source: str) -> bool:
        current = await self.read_snapshot(payment_id)
        resolved_channels = keyspace.normalize_channels(
            (current or {}).get("channels") if channels is None else channels
        )
        collect_enabled = bool((current or {}).get("collect_enabled")) if current and "collect_enabled" in current else True
        ds_order_enabled = self._flag_from_snapshot(current or {}, "ds_order_enabled", "dispatch_ds", False)
        if not current or not (current.get("online") and collect_enabled and ds_order_enabled):
            for channel in resolved_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            return False

        await self.set_ds_order_dispatch(
            payment_id,
            enabled=True,
            phone=current.get("phone"),
            channels=resolved_channels,
            source=source,
        )
        return True

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
        await self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
        await self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
        await self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        await self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        await self.redis.delete(keyspace.kickoff_key(payment_id))
        await self.redis.delete(keyspace.health_pause_order_key(payment_id))
        await self.redis.delete(keyspace.manual_off_collection_key(payment_id))
        await self.legacy_bridge.clear_kickoff(payment_id)
        await self.redis.hdel(keyspace.JOB_HASH, payment_id)
        await self.redis.zrem(keyspace.JOB_SET, payment_id)
        await self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone or snapshot.get("phone"):
            await self.redis.delete(keyspace.lock_phone_key(resolved_phone or snapshot.get("phone")))
        await self._clear_pre_login_aliases(payment_id)
        await self.legacy_bridge.mirror_offline(
            payment_id,
            phone=resolved_phone or snapshot.get("phone"),
            channels=resolved_channels,
        )
        return snapshot

    async def force_reset(self, payment_id, *, phone=None, source: str) -> Dict[str, Any]:
        snapshot = await self.read_snapshot(payment_id) or {}
        await self.clear_session(payment_id)
        await self.redis.delete(keyspace.pre_login_key(payment_id))
        await self.redis.delete(keyspace.health_pause_order_key(payment_id))
        await self.redis.delete(keyspace.manual_off_collection_key(payment_id))
        return await self.force_offline(
            payment_id,
            phone=phone or snapshot.get("phone"),
            source=source,
            reason=source,
        )

    async def sync_collection_job_state(
        self,
        login_data: Dict[str, Any],
        *,
        source: str,
        schedule_score: Optional[int] = None,
        online_ttl: int = 660,
        dispatch_ds: bool = True,
        collect_enabled: Optional[bool] = None,
        ds_order_enabled: Optional[bool] = None,
        df_order_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        payment_id = login_data.get("real_payment_id") or login_data.get("id")
        if payment_id in [None, ""]:
            raise ValueError("sync_collection_job_state requires payment id")
        score = self._now() if schedule_score is None else int(schedule_score)
        existing_job = self._decode(await self.redis.hget(keyspace.JOB_HASH, payment_id)) or {}
        resolved_collect_enabled = True if collect_enabled is None else bool(collect_enabled)
        resolved_ds_order_enabled = bool(dispatch_ds) if ds_order_enabled is None else bool(ds_order_enabled)
        resolved_df_order_enabled = True if df_order_enabled is None else bool(df_order_enabled)
        if not resolved_collect_enabled:
            resolved_ds_order_enabled = False
            resolved_df_order_enabled = False

        snapshot = await self.mark_active_successful(
            payment_id,
            phone=login_data.get("phone"),
            selected_accno=(
                login_data.get("account_accno")
                or login_data.get("selected_accno")
            ),
            selected_iban=(
                login_data.get("account_iban")
                or login_data.get("IBAN")
                or login_data.get("selected_iban")
            ),
            source=source,
            online_ttl=online_ttl,
            collect_enabled=resolved_collect_enabled,
            ds_order_enabled=resolved_ds_order_enabled,
            df_order_enabled=resolved_df_order_enabled,
            channels=(
                login_data.get("channels")
                or login_data.get("qr_channel")
                or login_data.get("channel")
                or existing_job.get("channels")
                or existing_job.get("qr_channel")
                or existing_job.get("channel")
            ),
        )
        if not resolved_collect_enabled:
            await self.redis.hdel(keyspace.JOB_HASH, payment_id)
            await self.redis.zrem(keyspace.JOB_SET, payment_id)
            return snapshot

        merged_job = dict(existing_job)
        merged_job.update(login_data)
        merged_job["id"] = payment_id
        if login_data.get("real_payment_id") or existing_job.get("real_payment_id"):
            merged_job["real_payment_id"] = login_data.get("real_payment_id") or existing_job.get("real_payment_id")
        await self.redis.hset(keyspace.JOB_HASH, payment_id, json.dumps(merged_job, ensure_ascii=True))
        await self.redis.zadd(keyspace.JOB_SET, {payment_id: score})
        return snapshot

    async def set_kickoff(self, payment_id, *, phone=None, ttl: int, source: str, reason: str, channels=None) -> Dict[str, Any]:
        snapshot = await self.force_offline(
            payment_id,
            phone=phone,
            source=source,
            reason=reason,
            channels=channels,
        )
        await self.redis.setex(keyspace.kickoff_key(payment_id), ttl, "1")
        await self.legacy_bridge.mirror_kickoff(payment_id, ttl)
        return snapshot
