import json
import time
from typing import Any, Dict, Optional

from application.jazzcash_runtime import keyspace
from application.jazzcash_runtime.flags import runtime_write_enabled
from application.jazzcash_runtime.legacy_bridge import SyncJazzCashLegacyBridge


class SyncJazzCashRuntimeService:
    def __init__(self, redis, now_provider=None):
        self.redis = redis
        self.now_provider = now_provider or time.time
        self.enabled = runtime_write_enabled()
        self.legacy_bridge = SyncJazzCashLegacyBridge(redis)

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

    def read_snapshot(self, payment_id):
        return self._decode(self.redis.get(keyspace.snapshot_key(payment_id)))

    def write_snapshot(self, payment_id, patch: Dict[str, Any], source: str):
        snapshot = self.read_snapshot(payment_id) or {
            "schema_version": keyspace.SCHEMA_VERSION,
            "payment_id": payment_id,
        }
        snapshot.update(patch)
        snapshot["schema_version"] = keyspace.SCHEMA_VERSION
        snapshot["payment_id"] = payment_id
        snapshot["last_source"] = source
        snapshot["updated_at"] = self._now()
        if self.enabled:
            self.redis.set(keyspace.snapshot_key(payment_id), json.dumps(snapshot, ensure_ascii=True))
            self.redis.zadd(keyspace.INDEX_UPDATED_AT, {str(payment_id): snapshot["updated_at"]})
        return snapshot

    def _sync_indexes(self, payment_id, snapshot):
        if not self.enabled:
            return
        if snapshot.get("online"):
            self.redis.sadd(keyspace.INDEX_ONLINE, payment_id)
        else:
            self.redis.srem(keyspace.INDEX_ONLINE, payment_id)

        if snapshot.get("collect_enabled"):
            self.redis.sadd(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            self.redis.zadd(keyspace.SCHEDULE_COLLECTION, {str(payment_id): self._now()})
        else:
            self.redis.srem(keyspace.INDEX_COLLECT_ENABLED, payment_id)
            self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)

        if snapshot.get("ds_order_enabled"):
            self.redis.sadd(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
        else:
            self.redis.srem(keyspace.INDEX_DS_ORDER_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)

        if snapshot.get("df_order_enabled"):
            self.redis.sadd(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
        else:
            self.redis.srem(keyspace.INDEX_DF_ORDER_ENABLED, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)

    def mark_active_successful(
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
    ):
        current = self.read_snapshot(payment_id) or {}
        if collect_enabled is None:
            resolved_collect_enabled = bool(current.get("collect_enabled")) if "collect_enabled" in current else True
            if dispatch_ds is True:
                resolved_collect_enabled = True
        else:
            resolved_collect_enabled = bool(collect_enabled)

        if ds_order_enabled is None:
            if dispatch_ds is None:
                resolved_ds_order_enabled = self._flag_from_snapshot(current, "ds_order_enabled", "dispatch_ds", True)
            else:
                resolved_ds_order_enabled = bool(dispatch_ds)
        else:
            resolved_ds_order_enabled = bool(ds_order_enabled)

        resolved_df_order_enabled = bool(dispatch_df) if df_order_enabled is None else bool(df_order_enabled)
        if not resolved_collect_enabled:
            resolved_ds_order_enabled = False
            resolved_df_order_enabled = False

        resolved_channels = keyspace.normalize_channels(current.get("channels") if channels is None else channels)
        snapshot = self.write_snapshot(
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
            },
            source=source,
        )
        self._sync_indexes(payment_id, snapshot)
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
        return snapshot

    def is_df_order_online(self, payment_id) -> bool:
        snapshot = self.read_snapshot(payment_id)
        if snapshot is None:
            return False
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        df_order_enabled = self._flag_from_snapshot(snapshot, "df_order_enabled", "dispatch_df", False)
        return bool(snapshot.get("online") and collect_enabled and df_order_enabled)

    def is_ds_order_online(self, payment_id) -> bool:
        snapshot = self.read_snapshot(payment_id)
        if snapshot is None:
            return False
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        ds_order_enabled = self._flag_from_snapshot(snapshot, "ds_order_enabled", "dispatch_ds", False)
        return bool(snapshot.get("online") and collect_enabled and ds_order_enabled)

    def requeue_df_if_online(self, payment_id) -> bool:
        self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        if not self.is_df_order_online(payment_id):
            return False
        self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        return True

    def is_collection_online(self, payment_id) -> bool:
        snapshot = self.read_snapshot(payment_id)
        if snapshot is None:
            return False
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        return bool(snapshot.get("online") and collect_enabled)

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
            phone=login_data.get("phone") or existing_job.get("phone"),
            selected_accno=(
                login_data.get("account_accno")
                or login_data.get("account")
                or existing_job.get("account_accno")
                or existing_job.get("account")
                or login_data.get("phone")
                or existing_job.get("phone")
            ),
            selected_iban=(
                login_data.get("account_iban")
                or login_data.get("iban")
                or login_data.get("IBAN")
                or existing_job.get("account_iban")
                or existing_job.get("iban")
                or existing_job.get("IBAN")
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

    def set_kickoff(self, payment_id, *, phone=None, ttl: int, source: str, reason: str):
        current = self.read_snapshot(payment_id) or {}
        snapshot = self.write_snapshot(
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
            self.redis.setex(keyspace.kickoff_key(payment_id), ttl, reason)
        self.legacy_bridge.mirror_kickoff(payment_id, ttl)
        return snapshot

    def force_offline(self, payment_id, *, phone=None, source: str, reason: str, channels=None):
        current = self.read_snapshot(payment_id) or {}
        resolved_phone = phone or current.get("phone")
        resolved_channels = keyspace.normalize_channels(current.get("channels") if channels is None else channels)
        snapshot = self.write_snapshot(
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
        self._sync_indexes(payment_id, snapshot)
        self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone:
            self.redis.delete(keyspace.lock_phone_key(resolved_phone))
        self.legacy_bridge.mirror_offline(payment_id, phone=resolved_phone, channels=resolved_channels)
        return snapshot

    def force_reset(self, payment_id, *, source: str):
        current = self.read_snapshot(payment_id) or {}
        snapshot = self.force_offline(
            payment_id,
            phone=current.get("phone"),
            channels=current.get("channels"),
            source=source,
            reason=source,
        )
        self.redis.delete(keyspace.session_key(payment_id))
        self.redis.delete(keyspace.pre_login_key(payment_id))
        self.redis.delete(keyspace.kickoff_key(payment_id))
        self.legacy_bridge.clear_kickoff(payment_id)
        self.redis.hdel(keyspace.JOB_HASH, payment_id)
        self.redis.zrem(keyspace.JOB_SET, payment_id)
        self.redis.zrem(keyspace.SCHEDULE_COLLECTION, payment_id)
        return snapshot
