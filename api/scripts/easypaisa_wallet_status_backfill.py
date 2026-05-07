import argparse
import sys
from pathlib import Path

import pymysql
import redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_config


JOB_HASH = "hash_easypaisa"
JOB_SET = "set_easypaisa"
RUNTIME_INDEX_KEYS = (
    "easypaisa_runtime:index:online",
    "easypaisa_runtime:index:collect_enabled",
    "easypaisa_runtime:index:dispatch_df",
    "easypaisa_runtime:index:dispatch_ds",
)
LEGACY_SET_KEYS = (
    "payment_online_ds",
    "payment_online_df",
)
LEGACY_LIST_KEYS = (
    "payment_active_df",
)
LEGACY_ACTIVE_SCAN_PATTERN = "payment_active_*"


def normalize_payment_id(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    value = str(value).strip()
    if not value.isdigit():
        return None
    return int(value)


def add_normalized(target, values):
    for value in values or []:
        payment_id = normalize_payment_id(value)
        if payment_id is not None:
            target.add(payment_id)


def collect_redis_candidate_ids(redis_client):
    candidate_ids = set()

    add_normalized(candidate_ids, redis_client.hkeys(JOB_HASH))
    add_normalized(candidate_ids, redis_client.zrange(JOB_SET, 0, -1))

    for key in RUNTIME_INDEX_KEYS:
        add_normalized(candidate_ids, redis_client.smembers(key))

    for key in LEGACY_SET_KEYS:
        add_normalized(candidate_ids, redis_client.smembers(key))

    for key in LEGACY_LIST_KEYS:
        add_normalized(candidate_ids, redis_client.lrange(key, 0, -1))

    for key in redis_client.scan_iter(match=LEGACY_ACTIVE_SCAN_PATTERN, count=200):
        key_name = key.decode("utf-8", errors="ignore") if isinstance(key, bytes) else str(key)
        if key_name in LEGACY_LIST_KEYS:
            continue
        add_normalized(candidate_ids, redis_client.lrange(key_name, 0, -1))

    return sorted(candidate_ids)


def fetch_valid_payment_ids(connection, candidate_ids):
    if not candidate_ids:
        return []

    placeholders = ",".join(["%s"] * len(candidate_ids))
    sql = f"""
        SELECT id
        FROM payment
        WHERE id IN ({placeholders})
          AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
          AND account_accno IS NOT NULL
          AND account_accno <> ''
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, candidate_ids)
        rows = cursor.fetchall()

    valid_ids = []
    for row in rows:
        if isinstance(row, dict):
            payment_id = row.get("id")
        else:
            payment_id = row[0]
        normalized = normalize_payment_id(payment_id)
        if normalized is not None:
            valid_ids.append(normalized)
    return sorted(set(valid_ids))


def update_wallet_status(connection, valid_ids):
    if not valid_ids:
        return 0

    placeholders = ",".join(["%s"] * len(valid_ids))
    sql = f"""
        UPDATE payment
        SET wallet_status = 1
        WHERE id IN ({placeholders})
          AND (bank_type = 97 OR bank_type = '97' OR bank_type_id = 97)
          AND account_accno IS NOT NULL
          AND account_accno <> ''
          AND wallet_status <> 1
    """
    with connection.cursor() as cursor:
        updated = cursor.execute(sql, valid_ids)
    connection.commit()
    return updated


def print_id_list(title, values):
    print(f"{title}={','.join(str(value) for value in values)}")


def build_plan(connection, redis_client):
    candidate_ids = collect_redis_candidate_ids(redis_client)
    valid_ids = fetch_valid_payment_ids(connection, candidate_ids)
    return {
        "candidate_ids": candidate_ids,
        "valid_ids": valid_ids,
    }


def main(execute=False):
    conf = get_config()
    connection = pymysql.connect(
        host=conf["mysql_host"],
        user=conf["mysql_user"],
        password=conf["mysql_password"],
        db=conf["mysql_database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    redis_client = redis.Redis(host=conf["redis_host"], port=6379, db=0, decode_responses=True)

    try:
        plan = build_plan(connection, redis_client)
        candidate_ids = plan["candidate_ids"]
        valid_ids = plan["valid_ids"]
        updated = 0
        if execute:
            updated = update_wallet_status(connection, valid_ids)

        print(f"candidate_count={len(candidate_ids)}")
        print(f"valid_count={len(valid_ids)}")
        print(f"updated={updated}")
        print_id_list("candidate_ids", candidate_ids)
        print_id_list("valid_ids", valid_ids)
        print(f"dry_run={str(not execute).lower()}")
    finally:
        connection.close()
        redis_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill EasyPaisa payment.wallet_status from old online Redis state.")
    parser.add_argument("--execute", action="store_true", help="真正执行 wallet_status=1 回填；默认只 dry-run。")
    args = parser.parse_args()
    main(execute=args.execute)
