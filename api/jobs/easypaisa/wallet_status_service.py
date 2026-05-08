import uuid


class WorkerWalletStatusService:
    """EasyPaisa worker 唯一钱包状态写入口。"""

    def __init__(self, connection, logger=None, redis_client=None, lock_ttl=10, invalid_guard_ttl=1800):
        self.connection = connection
        self.logger = logger
        self.redis = redis_client
        self.lock_ttl = lock_ttl
        self.invalid_guard_ttl = invalid_guard_ttl

    @staticmethod
    def _has_selected_account(row):
        account_accno = row.get("account_accno") if isinstance(row, dict) else None
        return bool(str(account_accno or "").strip())

    @staticmethod
    def _wallet_status(row):
        value = row.get("wallet_status") if isinstance(row, dict) else 0
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def reconcile_wallet_status_row(cls, row):
        has_account = cls._has_selected_account(row)
        wallet_status = cls._wallet_status(row)

        if has_account and wallet_status == 0:
            return "confirm"
        if not has_account and wallet_status == 1:
            return "offline"
        return "noop"

    def mark_available(self, payment_id, reason=""):
        token = self._acquire_lock(payment_id)
        if token is None:
            return 0
        try:
            if self._has_invalid_guard(payment_id):
                if self.logger:
                    self.logger.warning(
                        "EasyPaisa wallet_status available skipped by invalid guard: payment_id=%s reason=%s",
                        payment_id,
                        reason,
                    )
                return 0
            return self._mark_available_unlocked(payment_id, reason)
        finally:
            self._release_lock(payment_id, token)

    def _mark_available_unlocked(self, payment_id, reason=""):
        sql = """
            UPDATE payment
            SET wallet_status = 1,
                collection_status = CASE
                    WHEN status = 1 AND certified = 1 AND manual_status = 0 THEN 1
                    ELSE 0
                END,
                payout_status = CASE
                    WHEN status = 1 AND certified = 1 THEN 1
                    ELSE 0
                END
            WHERE id = %s
              AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
              AND account_accno IS NOT NULL
              AND account_accno <> ''
              AND (
                    wallet_status <> 1
                 OR collection_status <> CASE
                    WHEN status = 1 AND certified = 1 AND manual_status = 0 THEN 1
                    ELSE 0
                 END
                 OR payout_status <> CASE
                    WHEN status = 1 AND certified = 1 THEN 1
                    ELSE 0
                 END
              )
        """
        return self._execute_update(sql, (payment_id,), "available", reason)

    def mark_offline(self, payment_id, reason=""):
        token = self._acquire_lock(payment_id)
        if token is None:
            return 0
        try:
            if self._is_account_invalid_reason(reason):
                self._set_invalid_guard(payment_id, reason)
                return self._mark_account_invalid_unlocked(payment_id, reason)
            return self._mark_offline_unlocked(payment_id, reason)
        finally:
            self._release_lock(payment_id, token)

    def mark_account_invalid(self, payment_id, reason="account_invalid"):
        token = self._acquire_lock(payment_id)
        if token is None:
            return 0
        try:
            self._set_invalid_guard(payment_id, reason)
            return self._mark_account_invalid_unlocked(payment_id, reason)
        finally:
            self._release_lock(payment_id, token)

    def _mark_offline_unlocked(self, payment_id, reason=""):
        sql = """
            UPDATE payment
            SET wallet_status = 0,
                collection_status = 0,
                payout_status = 0
            WHERE id = %s
              AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
              AND (
                    wallet_status <> 0
                 OR collection_status <> 0
                 OR payout_status <> 0
              )
        """
        return self._execute_update(sql, (payment_id,), "offline", reason)

    def _mark_account_invalid_unlocked(self, payment_id, reason=""):
        sql = """
            UPDATE payment
            SET status = 0,
                wallet_status = 0,
                collection_status = 0,
                payout_status = 0,
                time_update = NOW()
            WHERE id = %s
              AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
              AND (
                    status <> 0
                 OR wallet_status <> 0
                 OR collection_status <> 0
                 OR payout_status <> 0
              )
        """
        return self._execute_update(sql, (payment_id,), "account_invalid", reason)

    def _execute_update(self, sql, params, action, reason):
        with self.connection.cursor() as cursor:
            affected_rows = cursor.execute(sql, params)
        self.connection.commit()
        if self.logger:
            self.logger.info(
                "EasyPaisa wallet_status %s: payment_id=%s affected=%s reason=%s",
                action,
                params[0],
                affected_rows,
                reason,
            )
        return affected_rows

    def _lock_key(self, payment_id):
        return f"easypaisa_wallet_status_lock:{payment_id}"

    def _invalid_guard_key(self, payment_id):
        return f"easypaisa_wallet_status_invalid:{payment_id}"

    def _acquire_lock(self, payment_id):
        if not self.redis:
            return ""
        token = uuid.uuid4().hex
        acquired = self.redis.set(self._lock_key(payment_id), token, nx=True, ex=self.lock_ttl)
        if acquired:
            return token
        if self.logger:
            self.logger.warning("EasyPaisa wallet_status lock busy: payment_id=%s", payment_id)
        return None

    def _release_lock(self, payment_id, token):
        if not self.redis:
            return
        lock_key = self._lock_key(payment_id)
        current = self.redis.get(lock_key)
        if self._to_text(current) == self._to_text(token):
            self.redis.delete(lock_key)

    def _set_invalid_guard(self, payment_id, reason):
        if self.redis:
            self.redis.setex(self._invalid_guard_key(payment_id), self.invalid_guard_ttl, str(reason or "account_invalid"))

    def _has_invalid_guard(self, payment_id):
        return bool(self.redis and self.redis.get(self._invalid_guard_key(payment_id)))

    @staticmethod
    def _is_account_invalid_reason(reason):
        text = str(reason or "").lower()
        return "501" in text or "account_invalid" in text or "账号无效" in text

    @staticmethod
    def _to_text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        return str(value or "")
