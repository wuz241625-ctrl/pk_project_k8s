from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set

from application.easypaisa_runtime import keyspace
from application.easypaisa_runtime.rollout_cleanup import normalize_payment_ids
from application.easypaisa_runtime.sync_runtime_service import SyncEasyPaisaRuntimeService


LOGIN_ON_PREFIX = "login_on_easypaisa_"
PRE_LOGIN_PREFIX = "pre_login_easypaisa_"
PAYMENT_KEY_PATTERNS: Sequence[tuple[str, str]] = (
    ("pre_login_easypaisa_*", PRE_LOGIN_PREFIX),
    ("easypaisa_runtime:session:*", "easypaisa_runtime:session:"),
    ("easypaisa_runtime:kickoff:*", "easypaisa_runtime:kickoff:"),
    ("kick_off_*", "kick_off_"),
    ("easypaisa_runtime:lock:payment:*", "easypaisa_runtime:lock:payment:"),
    ("easypaisa_runtime:snapshot:*", "easypaisa_runtime:snapshot:"),
)
PHONE_KEY_PATTERNS: Sequence[tuple[str, str]] = (
    ("easypaisa_runtime:lock:phone:*", "easypaisa_runtime:lock:phone:"),
)


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def normalize_phone(value) -> str:
    return _text(value).strip() if value is not None else ""


def _normalize_status(value) -> int:
    text = _text(value).strip() if value is not None else ""
    if text.lstrip("-").isdigit():
        return int(text)
    return 0


def _normalize_account(account: Mapping[str, object]) -> Dict[str, str]:
    payment_id = _text(account.get("id") or account.get("payment_id")).strip()
    if not payment_id.isdigit():
        raise ValueError(f"invalid easypaisa payment id: {payment_id!r}")
    return {
        "payment_id": payment_id,
        "phone": normalize_phone(account.get("phone")),
        "status": _normalize_status(account.get("status")),
    }


def _scan_keys(redis_client, pattern: str) -> List[str]:
    matched = set()
    for key in redis_client.scan_iter(pattern):
        matched.add(_text(key))
    return sorted(matched)


def _extract_suffixes(keys: Iterable[str], prefix: str) -> Set[str]:
    values = set()
    for key in keys:
        if key.startswith(prefix):
            values.add(key[len(prefix) :])
    return values


def _sorted(values: Iterable[object]) -> List[str]:
    return sorted({_text(value).strip() for value in values if _text(value).strip()}, key=lambda item: (len(item), item))


def _sorted_payment_ids(values: Iterable[object]) -> List[str]:
    return sorted({_text(value).strip() for value in values if _text(value).strip()}, key=int)


def _tracked_payment_ids(redis_client) -> Set[str]:
    payment_ids = set()
    payment_ids.update(normalize_payment_ids(redis_client.hkeys(keyspace.JOB_HASH)))
    payment_ids.update(normalize_payment_ids(redis_client.zrange(keyspace.JOB_SET, 0, -1)))
    payment_ids.update(normalize_payment_ids(redis_client.hkeys(keyspace.MONITOR_HASH)))
    payment_ids.update(normalize_payment_ids(redis_client.zrange(keyspace.MONITOR_SET, 0, -1)))
    payment_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_ONLINE)))
    payment_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DF)))
    payment_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DS)))
    payment_ids.update(normalize_payment_ids(redis_client.zrange(keyspace.INDEX_UPDATED_AT, 0, -1)))
    return payment_ids


def _force_offline_candidates(redis_client) -> Set[str]:
    payment_ids = set()
    payment_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_ONLINE)))
    payment_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DF)))
    payment_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DS)))
    payment_ids.update(normalize_payment_ids(redis_client.zrange(keyspace.INDEX_UPDATED_AT, 0, -1)))
    return payment_ids


def _scan_payment_and_phone_ids(redis_client) -> tuple[Set[str], Set[str], List[str], List[str]]:
    payment_ids = set()
    phone_values = set()

    for pattern, prefix in PAYMENT_KEY_PATTERNS:
        payment_ids.update(
            value
            for value in _extract_suffixes(_scan_keys(redis_client, pattern), prefix)
            if value.isdigit()
        )

    phone_lock_keys = _scan_keys(redis_client, "easypaisa_runtime:lock:phone:*")
    phone_values.update(_extract_suffixes(phone_lock_keys, "easypaisa_runtime:lock:phone:"))

    login_keys = _scan_keys(redis_client, "login_on_easypaisa_*")
    for suffix in _extract_suffixes(login_keys, LOGIN_ON_PREFIX):
        if suffix.isdigit() and len(suffix) < 10:
            payment_ids.add(suffix)
        else:
            phone_values.add(suffix)

    return payment_ids, phone_values, login_keys, phone_lock_keys


def _build_delete_keys(disable_payment_ids: Iterable[str], disable_phones: Iterable[str]) -> List[str]:
    matched = set()
    for payment_id in disable_payment_ids:
        matched.add(keyspace.pre_login_key(payment_id))
        matched.add(keyspace.legacy_login_on_payment_key(payment_id))
        matched.add(keyspace.session_key(payment_id))
        matched.add(keyspace.kickoff_key(payment_id))
        matched.add(keyspace.legacy_kickoff_key(payment_id))
        matched.add(keyspace.lock_payment_key(payment_id))

    for phone in disable_phones:
        matched.add(keyspace.legacy_login_on_phone_key(phone))
        matched.add(keyspace.lock_phone_key(phone))

    return sorted(matched)


def build_retention_plan(
    redis_client,
    easypaisa_accounts: Iterable[Mapping[str, object]],
    keep_phones: Iterable[object],
) -> Dict[str, object]:
    normalized_accounts = [_normalize_account(account) for account in easypaisa_accounts]
    known_payment_ids = {account["payment_id"] for account in normalized_accounts}
    phone_by_payment_id = {
        account["payment_id"]: account["phone"]
        for account in normalized_accounts
        if account["phone"]
    }
    status_by_payment_id = {
        account["payment_id"]: account["status"]
        for account in normalized_accounts
    }
    keep_phone_set = {normalize_phone(phone) for phone in keep_phones if normalize_phone(phone)}
    keep_payment_ids = {
        account["payment_id"]
        for account in normalized_accounts
        if account["phone"] in keep_phone_set
    }

    tracked_payment_ids = _tracked_payment_ids(redis_client)
    runtime_state_payment_ids = _force_offline_candidates(redis_client)
    scanned_payment_ids, scanned_phone_values, login_keys, phone_lock_keys = _scan_payment_and_phone_ids(redis_client)

    tracked_payment_ids = known_payment_ids | tracked_payment_ids | scanned_payment_ids
    disable_payment_ids = tracked_payment_ids - keep_payment_ids
    disable_db_payment_ids = known_payment_ids - keep_payment_ids
    orphan_payment_ids = tracked_payment_ids - known_payment_ids
    disable_phones = {
        phone_by_payment_id[payment_id]
        for payment_id in disable_db_payment_ids
        if payment_id in phone_by_payment_id
    }

    scanned_disable_phones = {
        suffix
        for suffix in _extract_suffixes(login_keys, LOGIN_ON_PREFIX)
        if suffix not in keep_phone_set and (not suffix.isdigit() or len(suffix) >= 10)
    }
    scanned_disable_phones.update(
        suffix
        for suffix in _extract_suffixes(phone_lock_keys, "easypaisa_runtime:lock:phone:")
        if suffix not in keep_phone_set
    )
    disable_phones.update(scanned_disable_phones)

    active_db_payment_ids = {
        payment_id
        for payment_id, status in status_by_payment_id.items()
        if status == 1
    }

    force_offline_payment_ids = (
        active_db_payment_ids
        | runtime_state_payment_ids
        | scanned_payment_ids
    ) - keep_payment_ids

    runtime_online_ids = disable_payment_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_ONLINE)))
    runtime_dispatch_df_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DF))
    )
    runtime_dispatch_ds_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DS))
    )
    legacy_online_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.smembers(keyspace.LEGACY_PAYMENT_ONLINE_DF))
    )
    legacy_active_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.lrange(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, -1))
    )
    runtime_updated_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.zrange(keyspace.INDEX_UPDATED_AT, 0, -1))
    )
    job_hash_ids = disable_payment_ids.intersection(normalize_payment_ids(redis_client.hkeys(keyspace.JOB_HASH)))
    job_set_ids = disable_payment_ids.intersection(normalize_payment_ids(redis_client.zrange(keyspace.JOB_SET, 0, -1)))
    monitor_hash_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.hkeys(keyspace.MONITOR_HASH))
    )
    monitor_set_ids = disable_payment_ids.intersection(
        normalize_payment_ids(redis_client.zrange(keyspace.MONITOR_SET, 0, -1))
    )

    matched_keys = _build_delete_keys(disable_payment_ids, disable_phones)

    return {
        "keep_phones": _sorted(keep_phone_set),
        "keep_payment_ids": _sorted_payment_ids(keep_payment_ids),
        "known_payment_ids": _sorted_payment_ids(known_payment_ids),
        "tracked_payment_ids": _sorted_payment_ids(tracked_payment_ids),
        "disable_payment_ids": _sorted_payment_ids(disable_payment_ids),
        "disable_db_payment_ids": _sorted_payment_ids(disable_db_payment_ids),
        "disable_phones": _sorted(disable_phones),
        "orphan_payment_ids": _sorted_payment_ids(orphan_payment_ids),
        "active_db_payment_ids": _sorted_payment_ids(active_db_payment_ids),
        "phone_by_payment_id": dict(sorted(phone_by_payment_id.items())),
        "force_offline_payment_ids": _sorted_payment_ids(force_offline_payment_ids),
        "matched_keys": matched_keys,
        "runtime_online_payment_ids": _sorted_payment_ids(runtime_online_ids),
        "runtime_dispatch_df_payment_ids": _sorted_payment_ids(runtime_dispatch_df_ids),
        "runtime_dispatch_ds_payment_ids": _sorted_payment_ids(runtime_dispatch_ds_ids),
        "runtime_updated_payment_ids": _sorted_payment_ids(runtime_updated_ids),
        "legacy_online_payment_ids": _sorted_payment_ids(legacy_online_ids),
        "legacy_active_payment_ids": _sorted_payment_ids(legacy_active_ids),
        "job_hash_payment_ids": _sorted_payment_ids(job_hash_ids),
        "job_set_payment_ids": _sorted_payment_ids(job_set_ids),
        "monitor_hash_payment_ids": _sorted_payment_ids(monitor_hash_ids),
        "monitor_set_payment_ids": _sorted_payment_ids(monitor_set_ids),
    }


def execute_retention_plan(
    redis_client,
    plan: Mapping[str, object],
    runtime_service: SyncEasyPaisaRuntimeService | None = None,
) -> Dict[str, int]:
    runtime_service = runtime_service or SyncEasyPaisaRuntimeService(redis_client)
    phone_by_payment_id = plan.get("phone_by_payment_id", {})

    forced_offline_payment_ids = plan.get("force_offline_payment_ids", [])
    forced_offline_job_hash_ids = set(forced_offline_payment_ids).intersection(
        set(plan.get("job_hash_payment_ids", []))
    )
    forced_offline_job_set_ids = set(forced_offline_payment_ids).intersection(
        set(plan.get("job_set_payment_ids", []))
    )
    for payment_id in forced_offline_payment_ids:
        payment_value = int(payment_id)
        runtime_service.force_offline(
            payment_value,
            phone=phone_by_payment_id.get(payment_id),
            source="account_retention",
            reason="retain_only_whitelist",
        )

    matched_keys = plan.get("matched_keys", [])
    deleted_keys = redis_client.delete(*matched_keys) if matched_keys else 0

    removed_runtime_updated = (
        redis_client.zrem(keyspace.INDEX_UPDATED_AT, *plan.get("runtime_updated_payment_ids", []))
        if plan.get("runtime_updated_payment_ids")
        else 0
    )
    removed_job_hash = (
        redis_client.hdel(keyspace.JOB_HASH, *plan.get("job_hash_payment_ids", []))
        if plan.get("job_hash_payment_ids")
        else 0
    )
    removed_job_set = (
        redis_client.zrem(keyspace.JOB_SET, *plan.get("job_set_payment_ids", []))
        if plan.get("job_set_payment_ids")
        else 0
    )
    removed_monitor_hash = (
        redis_client.hdel(keyspace.MONITOR_HASH, *plan.get("monitor_hash_payment_ids", []))
        if plan.get("monitor_hash_payment_ids")
        else 0
    )
    removed_monitor_set = (
        redis_client.zrem(keyspace.MONITOR_SET, *plan.get("monitor_set_payment_ids", []))
        if plan.get("monitor_set_payment_ids")
        else 0
    )

    return {
        "forced_offline_payment_ids": len(forced_offline_payment_ids),
        "deleted_keys": deleted_keys,
        "removed_runtime_updated": removed_runtime_updated,
        "removed_job_hash": removed_job_hash + len(forced_offline_job_hash_ids),
        "removed_job_set": removed_job_set + len(forced_offline_job_set_ids),
        "removed_monitor_hash": removed_monitor_hash,
        "removed_monitor_set": removed_monitor_set,
    }


def summarize_retention_plan(plan: Mapping[str, object]) -> Dict[str, int]:
    return {
        "keep_payment_ids": len(plan.get("keep_payment_ids", [])),
        "disable_payment_ids": len(plan.get("disable_payment_ids", [])),
        "disable_db_payment_ids": len(plan.get("disable_db_payment_ids", [])),
        "disable_phones": len(plan.get("disable_phones", [])),
        "orphan_payment_ids": len(plan.get("orphan_payment_ids", [])),
        "active_db_payment_ids": len(plan.get("active_db_payment_ids", [])),
        "force_offline_payment_ids": len(plan.get("force_offline_payment_ids", [])),
        "matched_keys": len(plan.get("matched_keys", [])),
        "runtime_online_payment_ids": len(plan.get("runtime_online_payment_ids", [])),
        "runtime_dispatch_df_payment_ids": len(plan.get("runtime_dispatch_df_payment_ids", [])),
        "runtime_dispatch_ds_payment_ids": len(plan.get("runtime_dispatch_ds_payment_ids", [])),
        "runtime_updated_payment_ids": len(plan.get("runtime_updated_payment_ids", [])),
        "legacy_online_payment_ids": len(plan.get("legacy_online_payment_ids", [])),
        "legacy_active_payment_ids": len(plan.get("legacy_active_payment_ids", [])),
        "job_hash_payment_ids": len(plan.get("job_hash_payment_ids", [])),
        "job_set_payment_ids": len(plan.get("job_set_payment_ids", [])),
        "monitor_hash_payment_ids": len(plan.get("monitor_hash_payment_ids", [])),
        "monitor_set_payment_ids": len(plan.get("monitor_set_payment_ids", [])),
    }
