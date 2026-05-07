class WorkerWalletStatusService:
    """EasyPaisa worker 唯一钱包状态写入口。"""

    def __init__(self, connection, logger=None):
        self.connection = connection
        self.logger = logger

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
