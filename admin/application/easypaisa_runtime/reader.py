import json
from typing import Any, Dict, Optional

from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.flags import runtime_read_enabled


class EasyPaisaAdminRuntimeReader:
    def __init__(self, redis):
        self.redis = redis
        self.enabled = runtime_read_enabled()

    @staticmethod
    def _is_easypaisa(bank_type) -> bool:
        return str(bank_type) == "97"

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
        if not self.enabled:
            return None
        return self._decode(await self.redis.get(keyspace.snapshot_key(payment_id)))

    @staticmethod
    def _flag(snapshot, key, legacy_key, default=False):
        if key in snapshot:
            return bool(snapshot.get(key))
        if legacy_key in snapshot:
            return bool(snapshot.get(legacy_key))
        return default

    def _can_collect(self, snapshot):
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        return bool(snapshot.get("online") and collect_enabled)

    async def is_payment_online_df(self, payment_id, *, bank_type):
        if self._is_easypaisa(bank_type):
            snapshot = await self.read_snapshot(payment_id)
            if snapshot is not None:
                return bool(
                    self._can_collect(snapshot)
                    and self._flag(snapshot, "df_order_enabled", "dispatch_df", False)
                )
            if self.enabled:
                return False
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)

    async def is_payment_online_ds(self, payment_id, *, bank_type):
        if self._is_easypaisa(bank_type):
            snapshot = await self.read_snapshot(payment_id)
            if snapshot is not None:
                return bool(
                    self._can_collect(snapshot)
                    and self._flag(snapshot, "ds_order_enabled", "dispatch_ds", False)
                )
            if self.enabled:
                return False
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)

    async def is_payment_online_status(self, payment_id, *, bank_type, bank_name=None):
        if self._is_easypaisa(bank_type):
            snapshot = await self.read_snapshot(payment_id)
            if snapshot is not None:
                return bool(snapshot.get("online"))
            if self.enabled:
                return False
            legacy_key = keyspace.legacy_login_on_payment_key(payment_id)
            return await self.redis.get(legacy_key) is not None

        if bank_name:
            return await self.redis.get(f"login_on_{bank_name}_{payment_id}") is not None
        return False

    async def online_df_count(self):
        if self.enabled:
            return await self.redis.scard(keyspace.INDEX_ONLINE)
        return await self.redis.scard(keyspace.LEGACY_PAYMENT_ONLINE_DF)

    async def df_order_count(self):
        if self.enabled:
            count = await self.redis.scard(keyspace.INDEX_DF_ORDER_ENABLED)
            if count:
                return count
            return await self.redis.scard(keyspace.INDEX_DISPATCH_DF)
        return await self.redis.scard(keyspace.LEGACY_PAYMENT_ONLINE_DF)

    async def df_order_members(self) -> set:
        raw = await self.redis.smembers(keyspace.INDEX_DF_ORDER_ENABLED)
        if not raw:
            raw = await self.redis.smembers(keyspace.INDEX_DISPATCH_DF)
        return {r.decode() if isinstance(r, bytes) else str(r) for r in raw}

    async def active_df_count(self):
        if self.enabled:
            active_ids = await self.redis.lrange(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, -1)
            df_members = await self.df_order_members()
            return sum(
                1
                for payment_id in active_ids
                if (payment_id.decode() if isinstance(payment_id, bytes) else str(payment_id)) in df_members
            )
        return await self.redis.llen(keyspace.LEGACY_PAYMENT_ACTIVE_DF)

    async def dispatch_ds_count(self) -> int:
        count = await self.redis.scard(keyspace.INDEX_DS_ORDER_ENABLED)
        if count:
            return count
        return await self.redis.scard(keyspace.INDEX_DISPATCH_DS)

    async def dispatch_ds_members(self) -> set:
        raw = await self.redis.smembers(keyspace.INDEX_DS_ORDER_ENABLED)
        if not raw:
            raw = await self.redis.smembers(keyspace.INDEX_DISPATCH_DS)
        return {r.decode() if isinstance(r, bytes) else str(r) for r in raw}
