import argparse
import sys
from pathlib import Path

import pymysql
import redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.easypaisa_runtime.rollout_cleanup import (
    collect_cleanup_plan,
    execute_cleanup,
    normalize_payment_ids,
    summarize_plan,
)
from config import get_config


def fetch_easypaisa_payment_ids(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM payment WHERE bank_type_id = 97")
        rows = cursor.fetchall()
    return normalize_payment_ids(row[0] for row in rows)


def print_section(title, values):
    print(f"{title}={len(values)}")
    for value in values:
        print(value)


def main(execute: bool):
    conf = get_config()
    connection = pymysql.connect(
        host=conf["mysql_host"],
        user=conf["mysql_user"],
        password=conf["mysql_password"],
        db=conf["mysql_database"],
        charset="utf8mb4",
    )
    redis_client = redis.Redis(host=conf["redis_host"], port=6379, db=0, decode_responses=True)
    try:
        easypaisa_payment_ids = fetch_easypaisa_payment_ids(connection)
        print(f"easypaisa_payment_ids={len(easypaisa_payment_ids)}")

        plan = collect_cleanup_plan(redis_client, easypaisa_payment_ids)
        summary = summarize_plan(plan)
        for key, value in summary.items():
            print(f"{key}={value}")

        print_section("matched_keys_list", plan["matched_keys"])
        print_section("legacy_online_payment_ids_list", plan["legacy_online_payment_ids"])
        print_section("legacy_active_payment_ids_list", plan["legacy_active_payment_ids"])
        print_section("runtime_online_payment_ids_list", plan["runtime_online_payment_ids"])

        if not execute:
            print("dry_run=true")
            return

        result = execute_cleanup(redis_client, plan)
        for key, value in result.items():
            print(f"{key}={value}")
    finally:
        connection.close()
        redis_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup EasyPaisa rollout legacy/runtime Redis state.")
    parser.add_argument("--execute", action="store_true", help="Actually delete matched keys and stale members.")
    args = parser.parse_args()
    main(execute=args.execute)
