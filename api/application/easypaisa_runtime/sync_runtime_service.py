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

    def read_snapshot(self, payment_id) -> Optional[Dict[str, Any]]:
        return self._decode(self.redis.get(keyspace.snapshot_key(payment_id)))

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
        channels=None,
    ) -> Dict[str, Any]:
        current = self.read_snapshot(payment_id) or {}
        resolved_dispatch_ds = current.get("dispatch_ds", False) if dispatch_ds is None else bool(dispatch_ds)
        resolved_channels = keyspace.normalize_channels(
            current.get("channels") if channels is None else channels
        )
        snapshot = self.write_snapshot(
            payment_id,
            {
                "phone": phone or current.get("phone"),
                "online": True,
                "dispatch_df": bool(dispatch_df),
                "dispatch_ds": resolved_dispatch_ds,
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
            if snapshot.get("dispatch_df"):
                self.redis.sadd(keyspace.INDEX_DISPATCH_DF, payment_id)
            else:
                self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            if snapshot.get("dispatch_ds"):
                self.redis.sadd(keyspace.INDEX_DISPATCH_DS, payment_id)
            else:
                self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            self.redis.delete(keyspace.kickoff_key(payment_id))
        self.legacy_bridge.clear_kickoff(payment_id)
        self.legacy_bridge.mirror_active(
            payment_id,
            phone=snapshot.get("phone"),
            online_ttl=online_ttl,
            dispatch_df=snapshot.get("dispatch_df", False),
            dispatch_ds=snapshot.get("dispatch_ds", False),
            channels=snapshot.get("channels"),
            previous_channels=current.get("channels"),
        )
        return snapshot

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
                "dispatch_df": False,
                "dispatch_ds": False,
                "channels": resolved_channels,
                "session_phase": "offline",
                "last_transition": reason,
            },
            source=source,
        )
        if runtime_jobs_enabled():
            self.redis.srem(keyspace.INDEX_ONLINE, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DF, payment_id)
            self.redis.srem(keyspace.INDEX_DISPATCH_DS, payment_id)
            self.redis.delete(keyspace.kickoff_key(payment_id))
        resolved_phone = phone or current.get("phone") or snapshot.get("phone")
        self.redis.hdel(keyspace.JOB_HASH, payment_id)
        self.redis.zrem(keyspace.JOB_SET, payment_id)
        self.redis.delete(keyspace.lock_payment_key(payment_id))
        if resolved_phone:
            self.redis.delete(keyspace.lock_phone_key(resolved_phone))
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
    ) -> Dict[str, Any]:
        payment_id = login_data.get("real_payment_id") or login_data.get("id")
        if payment_id in [None, ""]:
            raise ValueError("sync_collection_job_state requires payment id")
        score = self._now() if schedule_score is None else int(schedule_score)
        existing_job = self._decode(self.redis.hget(keyspace.JOB_HASH, payment_id)) or {}
        snapshot = self.mark_active_successful(
            payment_id,
            phone=login_data.get("phone"),
            selected_accno=login_data.get("account_accno"),
            selected_iban=login_data.get("account_iban") or login_data.get("IBAN"),
            source=source,
            online_ttl=online_ttl,
            dispatch_df=True,
            dispatch_ds=True,
            channels=(
                login_data.get("channels")
                or login_data.get("qr_channel")
                or login_data.get("channel")
                or existing_job.get("channels")
                or existing_job.get("qr_channel")
                or existing_job.get("channel")
            ),
        )
        merged_job = dict(existing_job)
        merged_job.update(login_data)
        merged_job["id"] = payment_id
        if login_data.get("real_payment_id") or existing_job.get("real_payment_id"):
            merged_job["real_payment_id"] = login_data.get("real_payment_id") or existing_job.get("real_payment_id")
        self.redis.hset(keyspace.JOB_HASH, payment_id, json.dumps(merged_job, ensure_ascii=True))
        self.redis.zadd(keyspace.JOB_SET, {payment_id: score})
        return snapshot
