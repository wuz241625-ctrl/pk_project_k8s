SCHEMA_VERSION = 1

SNAPSHOT_KEY = "easypaisa_runtime:snapshot:{payment_id}"
SESSION_KEY = "easypaisa_runtime:session:{payment_id}"
LOCK_PAYMENT_KEY = "easypaisa_runtime:lock:payment:{payment_id}"
LOCK_PHONE_KEY = "easypaisa_runtime:lock:phone:{phone}"

INDEX_ONLINE = "easypaisa_runtime:index:online"
INDEX_DISPATCH_DF = "easypaisa_runtime:index:dispatch_df"
INDEX_DISPATCH_DS = "easypaisa_runtime:index:dispatch_ds"
INDEX_UPDATED_AT = "easypaisa_runtime:index:updated_at"

LEGACY_PAYMENT_ONLINE_DF = "payment_online_df"
LEGACY_PAYMENT_ONLINE_DS = "payment_online_ds"
LEGACY_PAYMENT_ACTIVE_DF = "payment_active_df"
LEGACY_LOGIN_ON_PAYMENT = "login_on_easypaisa_{payment_id}"
LEGACY_LOGIN_ON_PHONE = "login_on_easypaisa_{phone}"


def normalize_channels(channels) -> list[str]:
    if channels in (None, "", []):
        return []

    if isinstance(channels, (list, tuple, set)):
        raw_items = list(channels)
    else:
        raw_items = [channels]

    normalized = []
    seen = set()
    for item in raw_items:
        if isinstance(item, bytes):
            item = item.decode("utf-8")
        parts = str(item).split(",")
        for part in parts:
            text = part.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
    return normalized


def snapshot_key(payment_id) -> str:
    return SNAPSHOT_KEY.format(payment_id=payment_id)


def session_key(payment_id) -> str:
    return SESSION_KEY.format(payment_id=payment_id)


def lock_payment_key(payment_id) -> str:
    return LOCK_PAYMENT_KEY.format(payment_id=payment_id)


def lock_phone_key(phone: str) -> str:
    return LOCK_PHONE_KEY.format(phone=phone)


def legacy_login_on_payment_key(payment_id) -> str:
    return LEGACY_LOGIN_ON_PAYMENT.format(payment_id=payment_id)


def legacy_login_on_phone_key(phone: str) -> str:
    return LEGACY_LOGIN_ON_PHONE.format(phone=phone)


def legacy_payment_active_channel_key(channel) -> str:
    return f"payment_active_{str(channel).strip()}"
