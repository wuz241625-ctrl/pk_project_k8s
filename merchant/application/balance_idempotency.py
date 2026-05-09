import hashlib
from decimal import Decimal, InvalidOperation


INSERT_IDEMPOTENCY_SQL = """
INSERT IGNORE INTO `balance_record_idempotency`
(`idempotency_key`, `code`, `user_type`, `user_id`, `amount`, `record_type`)
VALUES (%s, %s, %s, %s, %s, %s)
"""


def _normalize_amount(amount):
    try:
        return str(Decimal(str(amount)).quantize(Decimal("0.0000")))
    except (InvalidOperation, TypeError, ValueError):
        return str(amount)


def build_balance_idempotency_key(code, user_type, user_id, amount, record_type):
    normalized_code = str(code or "").strip()
    if not normalized_code or normalized_code == "0":
        return None
    payload = "|".join([
        normalized_code,
        str(user_type),
        str(user_id),
        _normalize_amount(amount),
        str(record_type),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_missing_idempotency_table(exc):
    if getattr(exc, "args", None) and exc.args and exc.args[0] == 1146:
        return True
    return "balance_record_idempotency" in str(exc) and "exist" in str(exc).lower()


async def reserve_balance_idempotency(cur, idempotency_key, code, user_type, user_id, amount, record_type, logger=None):
    if not idempotency_key:
        return True
    try:
        affected = await cur.execute(
            INSERT_IDEMPOTENCY_SQL,
            (idempotency_key, code, user_type, user_id, amount, record_type),
        )
    except Exception as exc:
        if _is_missing_idempotency_table(exc):
            if logger:
                logger.warning("balance_record_idempotency 表不存在，暂时跳过余额幂等保护")
            return True
        raise
    return affected == 1


def reserve_balance_idempotency_sync(cur, idempotency_key, code, user_type, user_id, amount, record_type, logger=None):
    if not idempotency_key:
        return True
    try:
        affected = cur.execute(
            INSERT_IDEMPOTENCY_SQL,
            (idempotency_key, code, user_type, user_id, amount, record_type),
        )
    except Exception as exc:
        if _is_missing_idempotency_table(exc):
            if logger:
                logger.warning("balance_record_idempotency 表不存在，暂时跳过余额幂等保护")
            return True
        raise
    return affected == 1
