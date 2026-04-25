from typing import Dict, Iterable, List, Sequence, Set

from application.easypaisa_runtime import keyspace


KEY_PATTERNS: Sequence[str] = (
    "pre_login_easypaisa_*",
    "login_on_easypaisa_*",
    "easypaisa_runtime:session:*",
    "easypaisa_runtime:snapshot:*",
    "easypaisa_runtime:health_pause:order:*",
)


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def normalize_payment_ids(values: Iterable[object]) -> List[str]:
    payment_ids = set()
    for value in values:
        text = _text(value).strip()
        if text.isdigit():
            payment_ids.add(text)
    return sorted(payment_ids, key=int)


def _extract_numeric_suffixes(keys: Iterable[str]) -> Set[str]:
    extracted = set()
    for key in keys:
        suffix = str(key).rsplit("_", 1)[-1]
        if suffix.isdigit():
            extracted.add(suffix)
    return extracted


def collect_matching_keys(redis_client, patterns: Sequence[str] = KEY_PATTERNS) -> List[str]:
    matched = set()
    for pattern in patterns:
        for key in redis_client.scan_iter(pattern):
            matched.add(_text(key))
    return sorted(matched)


def collect_cleanup_plan(redis_client, easypaisa_payment_ids: Iterable[object]) -> Dict[str, List[str]]:
    matched_keys = collect_matching_keys(redis_client)
    easypaisa_ids = set(normalize_payment_ids(easypaisa_payment_ids))
    easypaisa_ids.update(_extract_numeric_suffixes(matched_keys))
    easypaisa_ids.update(normalize_payment_ids(redis_client.hkeys(keyspace.JOB_HASH)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.zrange(keyspace.JOB_SET, 0, -1)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_ONLINE)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_COLLECT_ENABLED)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DF_ORDER_ENABLED)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DS_ORDER_ENABLED)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DF)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DS)))
    easypaisa_ids.update(normalize_payment_ids(redis_client.zrange(keyspace.SCHEDULE_COLLECTION, 0, -1)))
    legacy_online_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.LEGACY_PAYMENT_ONLINE_DF))),
        key=int,
    )
    legacy_collection_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.LEGACY_PAYMENT_ONLINE_DS))),
        key=int,
    )
    legacy_active_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.lrange(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, -1))),
        key=int,
    )
    runtime_online_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_ONLINE))),
        key=int,
    )
    runtime_collect_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_COLLECT_ENABLED))),
        key=int,
    )
    runtime_df_order_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DF_ORDER_ENABLED))),
        key=int,
    )
    runtime_ds_order_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DS_ORDER_ENABLED))),
        key=int,
    )
    runtime_dispatch_df_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DF))),
        key=int,
    )
    runtime_dispatch_ds_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.smembers(keyspace.INDEX_DISPATCH_DS))),
        key=int,
    )
    job_hash_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.hkeys(keyspace.JOB_HASH))),
        key=int,
    )
    job_set_ids = sorted(
        easypaisa_ids.intersection(normalize_payment_ids(redis_client.zrange(keyspace.JOB_SET, 0, -1))),
        key=int,
    )

    runtime_updated_ids = []
    runtime_schedule_collection_ids = []
    for payment_id in sorted(easypaisa_ids, key=int):
        if redis_client.zscore(keyspace.SCHEDULE_COLLECTION, payment_id) is not None:
            runtime_schedule_collection_ids.append(payment_id)
        if redis_client.zscore(keyspace.INDEX_UPDATED_AT, payment_id) is not None:
            runtime_updated_ids.append(payment_id)

    return {
        "matched_keys": matched_keys,
        "legacy_online_payment_ids": legacy_online_ids,
        "legacy_collection_payment_ids": legacy_collection_ids,
        "legacy_active_payment_ids": legacy_active_ids,
        "runtime_online_payment_ids": runtime_online_ids,
        "runtime_collect_payment_ids": runtime_collect_ids,
        "runtime_df_order_payment_ids": runtime_df_order_ids,
        "runtime_ds_order_payment_ids": runtime_ds_order_ids,
        "runtime_dispatch_df_payment_ids": runtime_dispatch_df_ids,
        "runtime_dispatch_ds_payment_ids": runtime_dispatch_ds_ids,
        "runtime_schedule_collection_payment_ids": runtime_schedule_collection_ids,
        "job_hash_payment_ids": job_hash_ids,
        "job_set_payment_ids": job_set_ids,
        "runtime_updated_payment_ids": runtime_updated_ids,
    }


def execute_cleanup(redis_client, plan: Dict[str, List[str]]) -> Dict[str, int]:
    matched_keys = plan.get("matched_keys", [])
    legacy_online_ids = plan.get("legacy_online_payment_ids", [])
    legacy_collection_ids = plan.get("legacy_collection_payment_ids", [])
    legacy_active_ids = plan.get("legacy_active_payment_ids", [])
    runtime_online_ids = plan.get("runtime_online_payment_ids", [])
    runtime_collect_ids = plan.get("runtime_collect_payment_ids", [])
    runtime_df_order_ids = plan.get("runtime_df_order_payment_ids", [])
    runtime_ds_order_ids = plan.get("runtime_ds_order_payment_ids", [])
    runtime_dispatch_df_ids = plan.get("runtime_dispatch_df_payment_ids", [])
    runtime_dispatch_ds_ids = plan.get("runtime_dispatch_ds_payment_ids", [])
    runtime_schedule_collection_ids = plan.get("runtime_schedule_collection_payment_ids", [])
    job_hash_ids = plan.get("job_hash_payment_ids", [])
    job_set_ids = plan.get("job_set_payment_ids", [])
    runtime_updated_ids = plan.get("runtime_updated_payment_ids", [])

    deleted_keys = redis_client.delete(*matched_keys) if matched_keys else 0
    removed_online_df = (
        redis_client.srem(keyspace.LEGACY_PAYMENT_ONLINE_DF, *legacy_online_ids)
        if legacy_online_ids
        else 0
    )
    removed_online_ds = (
        redis_client.srem(keyspace.LEGACY_PAYMENT_ONLINE_DS, *legacy_collection_ids)
        if legacy_collection_ids
        else 0
    )

    removed_active_df = 0
    for payment_id in legacy_active_ids:
        removed_active_df += redis_client.lrem(keyspace.LEGACY_PAYMENT_ACTIVE_DF, 0, payment_id)

    removed_runtime_online = (
        redis_client.srem(keyspace.INDEX_ONLINE, *runtime_online_ids) if runtime_online_ids else 0
    )
    removed_runtime_collect = (
        redis_client.srem(keyspace.INDEX_COLLECT_ENABLED, *runtime_collect_ids)
        if runtime_collect_ids
        else 0
    )
    removed_runtime_df_order = (
        redis_client.srem(keyspace.INDEX_DF_ORDER_ENABLED, *runtime_df_order_ids)
        if runtime_df_order_ids
        else 0
    )
    removed_runtime_ds_order = (
        redis_client.srem(keyspace.INDEX_DS_ORDER_ENABLED, *runtime_ds_order_ids)
        if runtime_ds_order_ids
        else 0
    )
    removed_runtime_dispatch_df = (
        redis_client.srem(keyspace.INDEX_DISPATCH_DF, *runtime_dispatch_df_ids)
        if runtime_dispatch_df_ids
        else 0
    )
    removed_runtime_dispatch_ds = (
        redis_client.srem(keyspace.INDEX_DISPATCH_DS, *runtime_dispatch_ds_ids)
        if runtime_dispatch_ds_ids
        else 0
    )
    removed_job_hash = (
        redis_client.hdel(keyspace.JOB_HASH, *job_hash_ids) if job_hash_ids else 0
    )
    removed_job_set = (
        redis_client.zrem(keyspace.JOB_SET, *job_set_ids) if job_set_ids else 0
    )
    removed_runtime_updated = (
        redis_client.zrem(keyspace.INDEX_UPDATED_AT, *runtime_updated_ids) if runtime_updated_ids else 0
    )
    removed_runtime_schedule_collection = (
        redis_client.zrem(keyspace.SCHEDULE_COLLECTION, *runtime_schedule_collection_ids)
        if runtime_schedule_collection_ids
        else 0
    )

    return {
        "deleted_keys": deleted_keys,
        "removed_online_df": removed_online_df,
        "removed_online_ds": removed_online_ds,
        "removed_active_df": removed_active_df,
        "removed_runtime_online": removed_runtime_online,
        "removed_runtime_collect": removed_runtime_collect,
        "removed_runtime_df_order": removed_runtime_df_order,
        "removed_runtime_ds_order": removed_runtime_ds_order,
        "removed_runtime_dispatch_df": removed_runtime_dispatch_df,
        "removed_runtime_dispatch_ds": removed_runtime_dispatch_ds,
        "removed_runtime_schedule_collection": removed_runtime_schedule_collection,
        "removed_job_hash": removed_job_hash,
        "removed_job_set": removed_job_set,
        "removed_runtime_updated": removed_runtime_updated,
    }


def summarize_plan(plan: Dict[str, List[str]]) -> Dict[str, int]:
    return {
        "matched_keys": len(plan.get("matched_keys", [])),
        "legacy_online_payment_ids": len(plan.get("legacy_online_payment_ids", [])),
        "legacy_collection_payment_ids": len(plan.get("legacy_collection_payment_ids", [])),
        "legacy_active_payment_ids": len(plan.get("legacy_active_payment_ids", [])),
        "runtime_online_payment_ids": len(plan.get("runtime_online_payment_ids", [])),
        "runtime_collect_payment_ids": len(plan.get("runtime_collect_payment_ids", [])),
        "runtime_df_order_payment_ids": len(plan.get("runtime_df_order_payment_ids", [])),
        "runtime_ds_order_payment_ids": len(plan.get("runtime_ds_order_payment_ids", [])),
        "runtime_dispatch_df_payment_ids": len(plan.get("runtime_dispatch_df_payment_ids", [])),
        "runtime_dispatch_ds_payment_ids": len(plan.get("runtime_dispatch_ds_payment_ids", [])),
        "runtime_schedule_collection_payment_ids": len(plan.get("runtime_schedule_collection_payment_ids", [])),
        "job_hash_payment_ids": len(plan.get("job_hash_payment_ids", [])),
        "job_set_payment_ids": len(plan.get("job_set_payment_ids", [])),
        "runtime_updated_payment_ids": len(plan.get("runtime_updated_payment_ids", [])),
    }
