from application.jazzcash_runtime import keyspace


class JazzCashLegacyBridge:
    def __init__(self, redis):
        self.redis = redis

    @staticmethod
    def _channels(current_channels=None, previous_channels=None):
        resolved_current = keyspace.normalize_channels(current_channels)
        resolved_previous = keyspace.normalize_channels(previous_channels)
        all_channels = []
        for channel in resolved_previous + resolved_current:
            if channel not in all_channels:
                all_channels.append(channel)
        return resolved_current, all_channels

    async def mirror_active(
        self,
        payment_id,
        phone=None,
        online_ttl=660,
        dispatch_df=True,
        dispatch_ds=True,
        channels=None,
        previous_channels=None,
    ):
        await self.redis.setex(keyspace.legacy_login_on_payment_key(payment_id), online_ttl, "1")
        if phone:
            await self.redis.setex(keyspace.legacy_login_on_phone_key(phone), online_ttl, "1")

        if dispatch_df:
            await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            await self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)

        resolved_channels, all_channels = self._channels(channels, previous_channels)
        if dispatch_ds:
            await self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in all_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            for channel in resolved_channels:
                await self.redis.rpush(keyspace.legacy_payment_active_channel_key(channel), payment_id)
        else:
            await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in all_channels:
                await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)

    async def mirror_offline(self, payment_id, phone=None, channels=None):
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
        await self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        await self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        for channel in keyspace.normalize_channels(channels):
            await self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        await self.redis.delete(keyspace.legacy_login_on_payment_key(payment_id))
        if phone:
            await self.redis.delete(keyspace.legacy_login_on_phone_key(phone))

    async def mirror_kickoff(self, payment_id, ttl):
        await self.redis.setex(keyspace.legacy_kickoff_key(payment_id), ttl, "1")

    async def clear_kickoff(self, payment_id):
        await self.redis.delete(keyspace.legacy_kickoff_key(payment_id))


class SyncJazzCashLegacyBridge:
    def __init__(self, redis):
        self.redis = redis

    @staticmethod
    def _channels(current_channels=None, previous_channels=None):
        resolved_current = keyspace.normalize_channels(current_channels)
        resolved_previous = keyspace.normalize_channels(previous_channels)
        all_channels = []
        for channel in resolved_previous + resolved_current:
            if channel not in all_channels:
                all_channels.append(channel)
        return resolved_current, all_channels

    def mirror_active(
        self,
        payment_id,
        phone=None,
        online_ttl=660,
        dispatch_df=True,
        dispatch_ds=True,
        channels=None,
        previous_channels=None,
    ):
        self.redis.setex(keyspace.legacy_login_on_payment_key(payment_id), online_ttl, "1")
        if phone:
            self.redis.setex(keyspace.legacy_login_on_phone_key(phone), online_ttl, "1")

        if dispatch_df:
            self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
            self.redis.rpush(keyspace.LEGACY_PAYMENT_ACTIVE_DF, payment_id)
        else:
            self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
            self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)

        resolved_channels, all_channels = self._channels(channels, previous_channels)
        if dispatch_ds:
            self.redis.sadd(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in all_channels:
                self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
            for channel in resolved_channels:
                self.redis.rpush(keyspace.legacy_payment_active_channel_key(channel), payment_id)
        else:
            self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
            for channel in all_channels:
                self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)

    def mirror_offline(self, payment_id, phone=None, channels=None):
        self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, payment_id)
        self.redis.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, payment_id)
        self.redis.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)
        for channel in keyspace.normalize_channels(channels):
            self.redis.lrem(keyspace.legacy_payment_active_channel_key(channel), 0, payment_id)
        self.redis.delete(keyspace.legacy_login_on_payment_key(payment_id))
        if phone:
            self.redis.delete(keyspace.legacy_login_on_phone_key(phone))

    def mirror_kickoff(self, payment_id, ttl):
        self.redis.setex(keyspace.legacy_kickoff_key(payment_id), ttl, "1")

    def clear_kickoff(self, payment_id):
        self.redis.delete(keyspace.legacy_kickoff_key(payment_id))
