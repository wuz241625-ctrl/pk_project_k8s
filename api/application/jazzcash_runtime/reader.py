from application.jazzcash_runtime import keyspace
from application.jazzcash_runtime.flags import runtime_read_enabled
from application.jazzcash_runtime.runtime_service import JazzCashRuntimeService


class JazzCashRuntimeReader:
    def __init__(self, redis):
        self.redis = redis
        self.enabled = runtime_read_enabled()
        self.runtime_service = JazzCashRuntimeService(redis)

    @staticmethod
    def _normalize_values(values):
        normalized = set()
        for value in values:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            normalized.add(str(value))
        return normalized

    @staticmethod
    def _flag(snapshot, key, legacy_key, default=False):
        if key in snapshot:
            return bool(snapshot.get(key))
        if legacy_key in snapshot:
            return bool(snapshot.get(legacy_key))
        return default

    @staticmethod
    def _is_jazzcash(bank_type) -> bool:
        return str(bank_type) == "98"

    def _can_collect(self, snapshot):
        collect_enabled = bool(snapshot.get("collect_enabled")) if "collect_enabled" in snapshot else True
        return bool(snapshot.get("online") and collect_enabled)

    def _snapshot_df_online(self, snapshot):
        return bool(
            self._can_collect(snapshot)
            and self._flag(snapshot, "df_order_enabled", "dispatch_df", False)
        )

    def _snapshot_ds_online(self, snapshot):
        return bool(
            self._can_collect(snapshot)
            and self._flag(snapshot, "ds_order_enabled", "dispatch_ds", False)
        )

    async def read_snapshot(self, payment_id):
        if not self.enabled:
            return None
        return await self.runtime_service.read_snapshot(payment_id)

    async def is_place_order_online(self, payment_id):
        snapshot = await self.read_snapshot(payment_id)
        if snapshot is not None:
            return self._snapshot_df_online(snapshot)
        if self.enabled:
            return False
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)

    async def is_collection_order_online(self, payment_id):
        snapshot = await self.read_snapshot(payment_id)
        if snapshot is not None:
            return self._snapshot_ds_online(snapshot)
        if self.enabled:
            return False
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)

    async def is_payment_online_df(self, payment_id, *, bank_type):
        if self._is_jazzcash(bank_type):
            return await self.is_place_order_online(payment_id)
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)

    async def is_payment_online_ds(self, payment_id, *, bank_type):
        if self._is_jazzcash(bank_type):
            return await self.is_collection_order_online(payment_id)
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)

    async def requeue_df_if_online(self, payment_id, *, bank_type):
        if not await self.is_payment_online_df(payment_id, bank_type=bank_type):
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            return False
        await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        await self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        return True

    async def is_selling_order_online(self, payment_id):
        return await self.is_collection_order_online(payment_id)

    async def collection_online_payment_ids(self):
        if self.enabled:
            ids = await self.redis.smembers(keyspace.INDEX_DS_ORDER_ENABLED)
            if not ids:
                ids = await self.redis.smembers(keyspace.INDEX_DISPATCH_DS)
            return self._normalize_values(ids)
        return self._normalize_values(await self.redis.smembers(keyspace.LEGACY_PAYMENT_ONLINE_DS))
