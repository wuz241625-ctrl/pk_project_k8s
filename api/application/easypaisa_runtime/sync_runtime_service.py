import json
from typing import Any, Dict, Optional

from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.flags import runtime_jobs_enabled
from application.easypaisa_runtime.legacy_bridge import SyncEasyPaisaLegacyBridge


class SyncEasyPaisaRuntimeService:
    def __init__(self, redis, now_provider=None):
        self.redis = redis
        self.now_provider = now_provider or __import__("time").time
        self.legacy_bridge = SyncEasyPaisaLegacyBridge(redis)

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

    def _clear_pre_login_aliases(self, payment_id):
        if not hasattr(self.redis, "scan_iter"):
            return

        for key in [self._text(raw_key) for raw_key in self.redis.scan_iter("pre_login_easypaisa_*")]:
            entry = self._decode(self.redis.get(key))
            if self._is_payment_id_alias_entry(entry, payment_id):
                self.redis.delete(key)

    def read_snapshot(self, payment_id) -> Optional[Dict[str, Any]]:
        return self._decode(self.redis.get(keyspace.snapshot_key(payment_id)))

    def is_manual_off(self, payment_id) -> bool:
        snapshot = self.read_snapshot(payment_id)
        return bool(snapshot and snapshot.get("manual_ds_paused"))

    def is_order_health_paused(self, payment_id) -> bool:
        snapshot = self.read_snapshot(payment_id)
        return self._is_health_paused_snapshot(snapshot)

    def is_df_order_online(self, payment_id) -> bool:
        """EasyPaisa DF 派单资格只能来自 runtime snapshot。"""
        snapshot = self.read_snapshot(payment_id)
        if snapshot is None:
            return False
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        df_order_enabled = self._flag_from_snapshot(snapshot, "df_order_enabled", "dispatch_df", False)
        return bool(snapshot.get("online") and collect_enabled and df_order_enabled)

    def requeue_df_if_online(self, payment_id) -> bool:
        if not self.is_df_order_online(payment_id):
            self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            return False
        self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        return True

    def pop_df_order_candidate(self, *, max_attempts: int = 50) -> Optional[str]:
        for _ in range(max_attempts):
            raw_payment_id = self.redis.lpop(keyspace.LEGACY_PAYMENT_ACTIVE_DF)
            if raw_payment_id is None:
                return None
            payment_id = self._text(raw_payment_id)
            if self.is_df_order_online(payment_id):
                return payment_id
            self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        return None

    def write_snapshot(self, payment_id, patch: Dict[str, Any], source: str) -> Dict[str, Any]:
        snapshot = self.read_snapshot(payment_id) or {
            "schema_version": keyspace.SCHEMA_VERSION,
            "payment_id": payment_id,
        }
        snapshot.update(patch)
        snapshot["schema_version"] = keyspace.SCHEMA_VERSION
        snapshot["payment_id"] = payment_id
        snapshot["last_source"] = source
        snapshot["updated_at"] = self._now()

        if runtime_jobs_enabled():
            raw = json.dumps(snapshot, ensure_ascii=True)
            self.redis.set(keyspace.snapshot_key(payment_id), raw)
            self.redis.zadd(keyspace.INDEX_UPDATED_AT, {payment_id: snapshot["updated_at"]})
        return snapshot

    def mark_active_successful(
        self,
        payment_id,
        *,
        phone: Optional[str],
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
        current = self.read_snapshot(payment_id) or {}
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
        snapshot = self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "online": True,
                "collect_enabled": resolved_collect_enabled,
                "ds_order_enabled": resolved_ds_order_enabled,
                "df_order_enabled": resolved_df_order_enabled,
                "dispatch_df": resolved_df_order_enabled,
                "dispatch_ds": resolved_ds_order_enabled,
                "selected_accno": selected_accno or current.get("selected_accno"),
                "selected_iban": selected_iban or current.get("selected_iban"),
                "channels": resolved_channels,
                "session_phase": "activeSuccessful",
                "last_transition": "activeSuccessful",
            },
            source=source,
        )
        if runtime_jobs_enabled():
            self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
            if snapshot.get("collect_enabled"):
                self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
            else:
                self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
            if snapshot.get("df_order_enabled"):
                self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
                self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
            else:
                self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
                self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            if snapshot.get("ds_order_enabled"):
                self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
                self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
            else:
                self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
                self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            self.redis.delete(keyspace.kickoff_key(payment_id))
        self.legacy_bridge.clear_kickoff(payment_id)
        self.legacy_bridge.mirror_active(
            payment_id,
            phone=snapshot.get("phone"),
            online_ttl=online_ttl,
            dispatch_df=snapshot.get("df_order_enabled", False),
            dispatch_ds=snapshot.get("ds_order_enabled", False),
            channels=snapshot.get("channels"),
            previous_channels=current.get("channels"),
        )
        # Stage 0.7: rebuild JOB_HASH/JOB_SET from session when missing.
        # sync_collection_job_state owns the full login_data path; when monitor
        # calls mark_active_successful directly (no login_data), JOB_HASH may be
        # empty after a prior login_off. Self-heal from session_key so worker
        # can resume polling this pid.
        if runtime_jobs_enabled() and snapshot.get("collect_enabled"):
            self._maybe_rebuild_job_hash_from_session(payment_id, snapshot)
        return snapshot

    def _maybe_rebuild_job_hash_from_session(self, payment_id, snapshot):
        """Self-heal JOB_HASH when it's missing but session still holds credentials.

        Only triggered from mark_active_successful where caller doesn't own the
        full login_data. Preserves worker runtime state (count/try_count/flags)
        by skipping when JOB_HASH already exists. Skips when session is missing
        to avoid writing incomplete data (worker will bypass the pid safely).
        """
        if self.redis.hget(keyspace.JOB_HASH, payment_id) is not None:
            return  # worker runtime state exists; don't overwrite

        session_raw = self.redis.get(keyspace.session_key(payment_id))
        if not session_raw:
            return  # no credentials available; skip rather than write garbage

        try:
            session_data = json.loads(
                session_raw.decode() if isinstance(session_raw, (bytes, bytearray)) else session_raw
            )
        except (ValueError, TypeError):
            return

        # Schema hygiene: strip runtime-versioning fields from session, force
        # worker-expected status, ensure id/count/if_first_time scaffolding.
        session_data.pop("schema_version", None)
        session_data.pop("fg_times", None)
        session_data["id"] = int(payment_id) if str(payment_id).isdigit() else payment_id
        session_data["status"] = "grabstatement"
        session_data.setdefault("count", 0)
        session_data.setdefault("if_first_time", False)

        # Enrich with snapshot fields that may be fresher than session (e.g. channels rotation).
        if snapshot.get("phone"):
            session_data.setdefault("phone", snapshot["phone"])
            session_data.setdefault("original_phone", snapshot["phone"])
        if snapshot.get("selected_accno"):
            session_data.setdefault("account_accno", snapshot["selected_accno"])
        if snapshot.get("selected_iban"):
            session_data.setdefault("account_iban", snapshot["selected_iban"])
        snap_channels = snapshot.get("channels") or []
        if snap_channels:
            session_data.setdefault("qr_channel", snap_channels[0])

        payload = json.dumps(session_data, ensure_ascii=True)
        self.redis.hset(keyspace.JOB_HASH, payment_id, payload)
        self.redis.zadd(keyspace.JOB_SET, {str(payment_id): self._now()})

    def set_ds_order_dispatch(
        self,
        payment_id,
        *,
        enabled: bool,
        phone: Optional[str] = None,
        channels=None,
        source: str,
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        current = self.read_snapshot(payment_id) or {}
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )

        if current.get("online"):
            return self.mark_active_successful(
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

        snapshot = self.write_snapshot(
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
        self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
        self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
        self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
        self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
            self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        return snapshot

    def set_collection_dispatch(
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
        return self.set_ds_order_dispatch(
            payment_id,
            enabled=enabled,
            phone=phone,
            channels=channels,
            source=source,
            online_ttl=online_ttl,
        )

    def pause_order_dispatch(
        self,
        payment_id,
        *,
        phone: Optional[str] = None,
        channels=None,
        source: str,
        online_ttl: int = 660,
    ) -> Dict[str, Any]:
        """业务禁用只暂停派单，保留可继续采集的会话和 jobs 队列。"""
        current = self.read_snapshot(payment_id) or {}
        is_online = bool(current.get("online"))
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        collect_enabled = (
            bool(current.get("collect_enabled")) if "collect_enabled" in current else is_online
        )
        collect_enabled = bool(is_online and collect_enabled)
        snapshot = self.write_snapshot(
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
        if runtime_jobs_enabled():
            if is_online:
                self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
            else:
                self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
            if collect_enabled:
                self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
            else:
                self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
                self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
            self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            self.redis.delete(keyspace.kickoff_key(payment_id))
            self.legacy_bridge.clear_kickoff(payment_id)
        if is_online:
            self.legacy_bridge.mirror_active(
                payment_id,
                phone=snapshot.get("phone"),
                online_ttl=online_ttl,
                dispatch_df=False,
                dispatch_ds=False,
                channels=resolved_channels,
                previous_channels=current.get("channels"),
            )
        else:
            self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            for channel in keyspace.normalize_channels(current.get("channels")) + resolved_channels:
                self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        return snapshot

    def resume_order_dispatch(
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
        current = self.read_snapshot(payment_id) or {}
        if not current.get("online"):
            return self.pause_order_dispatch(
                payment_id,
                phone=phone or current.get("phone"),
                channels=channels if channels is not None else current.get("channels"),
                source=source,
            )
        if self.is_order_health_paused(payment_id):
            return self.pause_order_dispatch(
                payment_id,
                phone=phone or current.get("phone"),
                channels=channels if channels is not None else current.get("channels"),
                source=source,
            )
        return self.mark_active_successful(
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

    def set_manual_off(self, payment_id, *, reason: str, ttl: Optional[int] = None) -> None:
        self.write_snapshot(
            payment_id,
            {
                "manual_ds_paused": True,
                "manual_ds_pause_reason": reason,
                "last_transition": f"manual_off:{reason}",
            },
            source=f"manual_off:{reason}",
        )
        if ttl is None:
            self.redis.set(keyspace.manual_off_collection_key(payment_id), reason)
        else:
            self.redis.setex(keyspace.manual_off_collection_key(payment_id), ttl, reason)
        self.set_ds_order_dispatch(payment_id, enabled=False, source=f"manual_off:{reason}")

    def clear_manual_off(self, payment_id) -> None:
        self.redis.delete(keyspace.manual_off_collection_key(payment_id))
        self.write_snapshot(
            payment_id,
            {
                "manual_ds_paused": False,
                "manual_ds_pause_reason": None,
                "last_transition": "manual_off_cleared",
            },
            source="manual_off_cleared",
        )

    def set_order_health_pause(
        self,
        payment_id,
        *,
        reason: str,
        ttl: int,
        source: str,
        phone: Optional[str] = None,
        channels=None,
    ) -> Dict[str, Any]:
        self.write_snapshot(
            payment_id,
            {
                "order_health_paused": True,
                "order_health_pause_reason": reason,
                "order_health_paused_until": self._now() + int(ttl),
                "last_transition": source,
            },
            source=source,
        )
        self.redis.setex(keyspace.health_pause_order_key(payment_id), ttl, reason)
        return self.pause_order_dispatch(
            payment_id,
            phone=phone,
            channels=channels,
            source=source,
        )

    def clear_order_health_pause(self, payment_id, *, source: str) -> Dict[str, Any]:
        self.redis.delete(keyspace.health_pause_order_key(payment_id))
        return self.write_snapshot(
            payment_id,
            {
                "order_health_paused": False,
                "order_health_pause_reason": None,
                "order_health_paused_until": 0,
                "last_transition": source,
            },
            source=source,
        )

    def schedule_collection(self, payment_id, *, next_at: int) -> None:
        self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): next_at})

    def requeue_ds_if_online(self, payment_id, *, channels=None, source: str) -> bool:
        current = self.read_snapshot(payment_id)
        resolved_channels = keyspace.normalize_channels(
            (current or {}).get("channels") if channels is None else channels
        )
        collect_enabled = bool((current or {}).get("collect_enabled")) if current and "collect_enabled" in current else True
        ds_order_enabled = self._flag_from_snapshot(current or {}, "ds_order_enabled", "dispatch_ds", False)
        if not current or not (current.get("online") and collect_enabled and ds_order_enabled):
            for channel in resolved_channels:
                self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            return False

        self.set_ds_order_dispatch(
            payment_id,
            enabled=True,
            phone=current.get("phone"),
            channels=resolved_channels,
            source=source,
        )
        return True

    def force_offline(self, payment_id, *, phone: Optional[str], source: str, reason: str, channels=None) -> Dict[str, Any]:
        current = self.read_snapshot(payment_id) or {}
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        snapshot = self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
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
        if runtime_jobs_enabled():
            self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
            self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
            self.redis.delete(keyspace.kickoff_key(payment_id))
        self.redis.delete(keyspace.health_pause_order_key(payment_id))
        self.redis.delete(keyspace.manual_off_collection_key(payment_id))
        resolved_phone = phone or current.get("phone") or snapshot.get("phone")
        self.redis.hdel(keyspace.JOB_HASH, payment_id)
        self.redis.zrem(keyspace.JOB_SET, payment_id)
        self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone:
            self.redis.delete(keyspace.lock_phone_key(resolved_phone))
        self._clear_pre_login_aliases(payment_id)
        self.legacy_bridge.mirror_offline(payment_id, phone=resolved_phone, channels=resolved_channels)
        return snapshot

    def set_kickoff(self, payment_id, *, phone: Optional[str], ttl: int, source: str, reason: str) -> Dict[str, Any]:
        snapshot = self.force_offline(payment_id, phone=phone, source=source, reason=reason)
        if runtime_jobs_enabled():
            self.redis.setex(keyspace.kickoff_key(payment_id), ttl, "1")
        self.legacy_bridge.mirror_kickoff(payment_id, ttl)
        return snapshot

    def sync_collection_job_state(
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
        existing_job = self._decode(self.redis.hget(keyspace.JOB_HASH, payment_id)) or {}
        resolved_collect_enabled = True if collect_enabled is None else bool(collect_enabled)
        resolved_ds_order_enabled = bool(dispatch_ds) if ds_order_enabled is None else bool(ds_order_enabled)
        resolved_df_order_enabled = True if df_order_enabled is None else bool(df_order_enabled)
        if not resolved_collect_enabled:
            resolved_ds_order_enabled = False
            resolved_df_order_enabled = False
        snapshot = self.mark_active_successful(
            payment_id,
            phone=login_data.get("phone"),
            selected_accno=login_data.get("account_accno"),
            selected_iban=login_data.get("account_iban") or login_data.get("IBAN"),
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
            self.redis.hdel(keyspace.JOB_HASH, payment_id)
            self.redis.zrem(keyspace.JOB_SET, payment_id)
            return snapshot
        merged_job = dict(existing_job)
        merged_job.update(login_data)
        merged_job["id"] = payment_id
        if login_data.get("real_payment_id") or existing_job.get("real_payment_id"):
            merged_job["real_payment_id"] = login_data.get("real_payment_id") or existing_job.get("real_payment_id")
        self.redis.hset(keyspace.JOB_HASH, payment_id, json.dumps(merged_job, ensure_ascii=True))
        self.redis.zadd(keyspace.JOB_SET, {payment_id: score})
        return snapshot
