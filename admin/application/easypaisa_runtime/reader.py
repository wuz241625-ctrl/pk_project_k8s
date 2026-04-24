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

    async def is_payment_online_df(self, payment_id, *, bank_type):
        if self._is_easypaisa(bank_type):
            snapshot = await self.read_snapshot(payment_id)
            if snapshot is not None:
                return bool(snapshot.get("online") and snapshot.get("dispatch_df"))
        return await self.redis.sismember(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)

    async def is_payment_online_status(self, payment_id, *, bank_type, bank_name=None):
        if self._is_easypaisa(bank_type):
            snapshot = await self.read_snapshot(payment_id)
            if snapshot is not None:
                return bool(snapshot.get("online"))
            legacy_key = keyspace.legacy_login_on_payment_key(payment_id)
            return await self.redis.get(legacy_key) is not None

        if bank_name:
            return await self.redis.get(f"login_on_{bank_name}_{payment_id}") is not None
        return False

    async def online_df_count(self):
        if self.enabled:
            return await self.redis.scard(keyspace.INDEX_ONLINE)
        return await self.redis.scard(keyspace.LEGACY_PAYMENT_ONLINE_DF)

    async def active_df_count(self):
        return await self.redis.llen(keyspace.LEGACY_PAYMENT_ACTIVE_DF)
