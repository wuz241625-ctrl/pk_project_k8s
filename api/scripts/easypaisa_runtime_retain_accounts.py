import argparse
import sys
from pathlib import Path

import pymysql
import redis

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.easypaisa_runtime.account_retention import (
    build_retention_plan,
    execute_retention_plan,
    summarize_retention_plan,
)
from config import get_config


def fetch_easypaisa_accounts(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, phone, name, partner_id, bank_type, status, certified, account_accno
            FROM payment
            WHERE bank_type = 97
            ORDER BY status DESC, id
            """
        )
        return cursor.fetchall()


def update_payment_statuses(connection, keep_payment_ids, disable_payment_ids):
    keep_updated = 0
    disable_updated = 0

    with connection.cursor() as cursor:
        if keep_payment_ids:
            placeholders = ",".join(["%s"] * len(keep_payment_ids))
            keep_updated = cursor.execute(
                f"UPDATE payment SET status = 1 WHERE id IN ({placeholders})",
                keep_payment_ids,
            )

        if disable_payment_ids:
            placeholders = ",".join(["%s"] * len(disable_payment_ids))
            disable_updated = cursor.execute(
                f"UPDATE payment SET status = 0 WHERE bank_type = 97 AND id IN ({placeholders})",
                disable_payment_ids,
            )

    connection.commit()
    return {
        "keep_status_updated": keep_updated,
        "disable_status_updated": disable_updated,
    }


def print_accounts(title, accounts):
    print(f"{title}={len(accounts)}")
    for account in accounts:
        print(
            "payment_id={id} phone={phone} status={status} certified={certified} partner_id={partner_id} name={name}".format(
                id=account.get("id"),
                phone=account.get("phone") or "",
                status=account.get("status"),
                certified=account.get("certified"),
                partner_id=account.get("partner_id"),
                name=account.get("name") or "",
            )
        )


def print_section(title, values):
    print(f"{title}={len(values)}")
    for value in values:
        print(value)


def main(keep_phone: str, execute: bool):
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
        accounts = fetch_easypaisa_accounts(connection)
        plan = build_retention_plan(redis_client, accounts, {keep_phone})
        summary = summarize_retention_plan(plan)

        if not plan["keep_payment_ids"]:
            raise SystemExit(f"未找到保留手机号对应的 EasyPaisa 账号: keep_phone={keep_phone}")

        print_accounts("easypaisa_accounts", accounts)
        print(f"keep_phone={keep_phone}")
        print_section("keep_payment_ids_list", plan["keep_payment_ids"])
        print_section("disable_db_payment_ids_list", plan["disable_db_payment_ids"])
        print_section("disable_payment_ids_list", plan["disable_payment_ids"])
        print_section("disable_phones_list", plan["disable_phones"])
        print_section("orphan_payment_ids_list", plan["orphan_payment_ids"])

        for key, value in summary.items():
            print(f"{key}={value}")

        if not execute:
            print("dry_run=true")
            return

        db_result = update_payment_statuses(
            connection,
            keep_payment_ids=[int(payment_id) for payment_id in plan["keep_payment_ids"]],
            disable_payment_ids=[int(payment_id) for payment_id in plan["disable_db_payment_ids"]],
        )
        for key, value in db_result.items():
            print(f"{key}={value}")

        redis_result = execute_retention_plan(redis_client, plan)
        for key, value in redis_result.items():
            print(f"{key}={value}")
    finally:
        connection.close()
        redis_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="只保留白名单 EasyPaisa 账号在线，其余账号统一下线。")
    parser.add_argument("--keep-phone", required=True, help="需要保留的 EasyPaisa 手机号，例如 03045536108")
    parser.add_argument("--execute", action="store_true", help="真正执行 DB 和 Redis 清理")
    args = parser.parse_args()
    main(keep_phone=args.keep_phone, execute=args.execute)
