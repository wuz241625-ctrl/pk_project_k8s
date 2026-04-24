from typing import Any, Mapping


def _normalize_channel_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def is_jazzcash_payout_request(data: Mapping[str, Any]) -> bool:
    bank = _normalize_channel_value(data.get("bank"))
    if bank == "jazzcash":
        return True

    bank_code = _normalize_channel_value(data.get("bank_code"))
    if bank_code:
        return bank_code == "jazzcash"

    legacy_bankcode = _normalize_channel_value(data.get("bankcode"))
    return legacy_bankcode == "jazzcash"
