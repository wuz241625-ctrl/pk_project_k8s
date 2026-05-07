"""JazzCash Merchant v1.6 协议薄封装。"""

import base64
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional


SENSITIVE_KEYS = {"pin", "pincode", "mpin", "password", "pwd", "token", "authorization"}


CODE_SEMANTICS = {
    100: {"category": "success", "action": "accept", "retryable": False},
    200: {"category": "success", "action": "accept", "retryable": False},
    401: {"category": "auth", "action": "relogin", "retryable": False},
    402: {"category": "business_failed", "action": "reroute", "retryable": True},
    403: {"category": "rejected", "action": "reject", "retryable": False},
    423: {"category": "busy", "action": "retry", "retryable": True},
    500: {"category": "unknown", "action": "manual_confirm", "retryable": False},
    501: {"category": "account_invalid", "action": "offline_account", "retryable": False},
    503: {"category": "network", "action": "retry", "retryable": True},
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _normalize_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


def build_envelope(action: str, payload: Any, request_id: Optional[str] = None) -> Dict[str, Any]:
    if not action:
        raise ValueError("action is required")
    return {
        "id": request_id or str(uuid.uuid4()),
        "action": action,
        "payload": _normalize_payload(payload),
    }


def build_form_body(
    action: str,
    payload: Any,
    user_id: str,
    secret: str,
    request_id: Optional[str] = None,
) -> Dict[str, str]:
    if not user_id:
        raise ValueError("user_id is required")
    if not secret:
        raise ValueError("secret is required")

    envelope = build_envelope(action, payload, request_id=request_id)
    envelope_json = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"), default=_json_default)
    data = base64.b64encode(envelope_json.encode("utf-8")).decode("utf-8")
    sign = hashlib.md5((data + secret).encode("utf-8")).hexdigest()
    return {"user_id": user_id, "data": data, "sign": sign}


def decode_response(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        if "resp" in raw and isinstance(raw["resp"], str):
            decoded = _decode_possible_base64_json(raw["resp"])
            return decoded if isinstance(decoded, dict) else raw
        return raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            decoded = _decode_possible_base64_json(raw)
            return decoded if isinstance(decoded, dict) else {}
    return {}


def _decode_possible_base64_json(value: str) -> Any:
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return None


def classify_code(code: Any) -> Dict[str, Any]:
    try:
        normalized = int(code)
    except (TypeError, ValueError):
        normalized = None
    semantic = CODE_SEMANTICS.get(normalized)
    if semantic:
        result = dict(semantic)
        result["code"] = normalized
        return result
    return {"code": normalized, "category": "unknown", "action": "manual_confirm", "retryable": False}


def _to_enabled(value: Any) -> bool:
    try:
        return int(value or 0) == 1
    except (TypeError, ValueError):
        return False


def calculate_final_status(
    status: Any,
    certified: Any,
    manual_status: Any,
    wallet_status: Any = 1,
) -> Dict[str, int]:
    wallet_enabled = _to_enabled(wallet_status)
    legacy_enabled = _to_enabled(status)
    certified_enabled = _to_enabled(certified)
    manual_locked = _to_enabled(manual_status)

    if not wallet_enabled:
        return {"wallet_status": 0, "collection_status": 0, "payout_status": 0}

    payout_enabled = legacy_enabled and certified_enabled
    collection_enabled = payout_enabled and not manual_locked
    return {
        "wallet_status": 1,
        "collection_status": 1 if collection_enabled else 0,
        "payout_status": 1 if payout_enabled else 0,
    }


def mask_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                masked[key] = "******"
            else:
                masked[key] = mask_sensitive_payload(item)
        return masked
    if isinstance(value, list):
        return [mask_sensitive_payload(item) for item in value]
    return value
