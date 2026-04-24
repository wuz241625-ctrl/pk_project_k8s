from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.flags import runtime_read_enabled
from application.easypaisa_runtime.runtime_service import EasyPaisaRuntimeService


class EasyPaisaRuntimeReader:
    def __init__(self, redis):
        self.redis = redis
        self.enabled = runtime_read_enabled()
        self.runtime_service = EasyPaisaRuntimeService(redis)

    @staticmethod
    def _normalize_values(values):
        normalized = set()
        for value in values:
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            normalized.add(str(value))
        return normalized

    async def read_snapshot(self, payment_id):
        if not self.enabled:
            return None
        return await self.runtime_service.read_snapshot(payment_id)

    async def is_place_order_online(self, payment_id):
        snapshot = await self.read_snapshot(payment_id)
        if snapshot is not None:
            return bool(snapshot.get("online") and snapshot.get("dispatch_df"))
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)

    async def is_collection_order_online(self, payment_id):
        snapshot = await self.read_snapshot(payment_id)
        if snapshot is not None:
            return bool(snapshot.get("online") and snapshot.get("dispatch_ds"))
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)

    async def is_selling_order_online(self, payment_id):
        return await self.is_collection_order_online(payment_id)

    async def collection_online_payment_ids(self):
        if self.enabled:
            return self._normalize_values(await self.redis.smembers(keyspace.INDEX_DISPATCH_DS))
        return self._normalize_values(await self.redis.smembers(keyspace.LEGACY_PAYMENT_ONLINE_DS))
