import argparse
import os
import sys

import pymysql


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calculate_business_status(row):
    wallet_status = _to_int(row.get("wallet_status"))
    status = _to_int(row.get("status"))
    certified = _to_int(row.get("certified"))
    manual_status = _to_int(row.get("manual_status"))
    business_enabled = wallet_status == 1 and status == 1 and certified == 1
    collection_status = 1 if business_enabled and manual_status == 0 else 0
    payout_status = 1 if business_enabled else 0
    return collection_status, payout_status


def mysql_config_from_env():
    return {
        "host": os.getenv("APP_MYSQL_HOST", os.getenv("MYSQL_HOST", "127.0.0.1")),
        "port": int(os.getenv("APP_MYSQL_PORT", os.getenv("MYSQL_PORT", "3306"))),
        "user": os.getenv("APP_MYSQL_USER", os.getenv("MYSQL_USER", "root")),
        "password": os.getenv("APP_MYSQL_PASSWORD", os.getenv("MYSQL_PASSWORD", "")),
        "database": os.getenv("APP_MYSQL_DATABASE", os.getenv("MYSQL_DATABASE", "pakistan")),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }


def fetch_easypaisa_rows(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, wallet_status, status, certified, manual_status, collection_status, payout_status
            FROM payment
            WHERE bank_type = 97 OR bank_type = '97' OR bank_type_id = 97
            """
        )
        return cursor.fetchall() or []


def apply_backfill(connection, rows, execute=False):
    changed = []
    effective_collection = 0
    effective_payout = 0
    for row in rows:
        collection_status, payout_status = calculate_business_status(row)
        effective_collection += collection_status
        effective_payout += payout_status
        if (
            _to_int(row.get("collection_status")) != collection_status
            or _to_int(row.get("payout_status")) != payout_status
        ):
            changed.append((collection_status, payout_status, row["id"]))

    if execute and changed:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE payment
                SET collection_status = %s,
                    payout_status = %s
                WHERE id = %s
                """,
                changed,
            )
        connection.commit()

    return {
        "total": len(rows),
        "effective_collection": effective_collection,
        "effective_payout": effective_payout,
        "changed_rows": len(changed),
        "changed_ids": [payment_id for _, _, payment_id in changed],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Backfill EasyPaisa payment collection/payout business status.")
    parser.add_argument("--execute", action="store_true", help="真正执行回填；默认只 dry-run。")
    args = parser.parse_args(argv)

    connection = pymysql.connect(**mysql_config_from_env())
    try:
        stats = apply_backfill(connection, fetch_easypaisa_rows(connection), execute=args.execute)
        print(stats)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
