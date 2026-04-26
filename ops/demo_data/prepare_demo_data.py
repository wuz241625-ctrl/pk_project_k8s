#!/usr/bin/env python3
import argparse
import datetime as dt
import decimal
import fnmatch
import hashlib
import random
import re
import secrets
from typing import Dict, Iterable, List, Sequence, Tuple


DEMO_IP = "103.135.100.192"
DEMO_PASSWORD = "123456"
DEMO_TOTP_SECRET = "JBSWY3DPEHPK3PXP"
DEMO_TOTP_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

DEMO_ADMIN_IDS = [1, 9001, 9002, 9003, 9004]
DEMO_MERCHANT_IDS = [9101, 9102, 9103, 9104, 9105, 9106, 9107, 9108]
DEMO_PARTNER_IDS = [9201, 9202, 9203, 9204]
REALISTIC_ADMIN_IDS = [1, 24, 46, 51, 169, 297]
REALISTIC_MERCHANT_LIMIT = 8
REALISTIC_PARTNER_LIMIT = 8
REALISTIC_PAYMENT_LIMIT = 24
REALISTIC_DS_SUCCESS_LIMIT = 220
REALISTIC_DS_FAIL_LIMIT = 100
REALISTIC_DF_SUCCESS_LIMIT = 120
REALISTIC_DF_FAIL_LIMIT = 40
DEMO_WHITELIST_IPS = [
    "103.135.100.192",
    "1.54.194.2",
    "47.238.21.150",
    "169.150.222.78",
    "169.150.222.77",
    "169.150.222.76",
    "199.234.95.39",
]

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def generate_demo_totp_secret(length: int = 16) -> str:
    return "".join(secrets.choice(DEMO_TOTP_ALPHABET) for _ in range(length))


def generate_demo_api_key() -> str:
    return secrets.token_hex(16)

RESET_TABLES = [
    "orders_ds",
    "orders_df",
    "orders_df_cancel",
    "orders_cd",
    "balance_record",
    "bank_record",
    "easypaisa_operation_logs",
    "payment",
    "payment_d",
    "payment_upi_history",
    "payment_weight",
    "operate",
    "operation_logs",
    "sys_operation_log",
    "partner_login_log",
    "robot_message_log",
    "sms_record",
    "user_message",
    "daily",
    "balance_count_record",
    "statistics_daily_merchant_orders_ds",
    "statistics_daily_merchant_orders_df",
    "statistics_daily_partner_orders_ds",
    "statistics_daily_partner_orders_df",
    "partner_invitation_code",
    "partner_recharge",
    "partner_withdraw",
    "merchant_withdraw",
    "transfer",
    "usdt_deposit_orders",
    "order_pub_acct_payment",
]


def build_insert_sql(table: str, row: Dict[str, object]) -> Tuple[str, List[object]]:
    columns = sorted(row.keys())
    names = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    return f"INSERT INTO {table} ({names}) VALUES ({placeholders})", [row[column] for column in columns]


def normalize_amount(value: decimal.Decimal, index: int) -> decimal.Decimal:
    amount = decimal.Decimal(str(value or 0)).quantize(decimal.Decimal("0.01"))
    if amount < decimal.Decimal("10") or amount > decimal.Decimal("50000"):
        amount = decimal.Decimal(100 + index * 160).quantize(decimal.Decimal("0.01"))
    return amount


def ds_timestamps(created: dt.datetime, status: int):
    if status <= 0:
        return created, None, None, None
    accepted = created + dt.timedelta(minutes=5)
    if status >= 3:
        return created, accepted, created + dt.timedelta(minutes=10), created + dt.timedelta(minutes=12)
    return created, accepted, None, None


def demo_order_created_at(now: dt.datetime, index: int, merchant_count: int, minute_step: int) -> dt.datetime:
    days_ago = ((index - 1) // merchant_count) % 10
    target_date = now.date() - dt.timedelta(days=days_ago)
    minute_offset = (index * minute_step) % 600
    return dt.datetime.combine(target_date, dt.time(8, 0)) + dt.timedelta(minutes=minute_offset)


def build_permission_csv(permissions: Sequence[Dict[str, object]], patterns: Sequence[str]) -> str:
    by_id = {int(row["id"]): row for row in permissions}
    selected = set()
    for row in permissions:
        path = str(row.get("path") or "")
        if any(fnmatch.fnmatch(path, pattern.replace("%", "*")) for pattern in patterns):
            current_id = int(row["id"])
            while current_id and current_id in by_id and current_id not in selected:
                selected.add(current_id)
                current_id = int(by_id[current_id].get("pid") or 0)
    return ",".join(str(item) for item in sorted(selected))


def parse_args():
    parser = argparse.ArgumentParser(description="刷新测试环境演示数据")
    parser.add_argument("--host", default="mysql")
    parser.add_argument("--port", default=3306, type=int)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="Pass_1234")
    parser.add_argument("--database", default="pakistan")
    parser.add_argument("--source-database", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-understand-this-rewrites-test-data", action="store_true")
    return parser.parse_args()


def fetch_all(cur, sql: str, params: Iterable[object] = ()):
    cur.execute(sql, tuple(params))
    return list(cur.fetchall())


def fetch_one(cur, sql: str, params: Iterable[object] = ()):
    rows = fetch_all(cur, sql, params)
    return rows[0] if rows else None


def table_exists(cur, table: str) -> bool:
    row = fetch_one(
        cur,
        """
        SELECT COUNT(*) AS count
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        [table],
    )
    return bool(row and row["count"])


def execute_insert(cur, table: str, row: Dict[str, object]):
    sql, values = build_insert_sql(table, row)
    cur.execute(sql, values)


def quote_identifier(identifier: str) -> str:
    if not identifier or not IDENTIFIER_RE.match(identifier):
        raise ValueError(f"invalid mysql identifier: {identifier!r}")
    return f"`{identifier}`"


def qualified_table(database: str, table: str) -> str:
    return f"{quote_identifier(database)}.{quote_identifier(table)}"


def placeholders(values: Sequence[object]) -> str:
    if not values:
        raise ValueError("empty values are not allowed")
    return ",".join(["%s"] * len(values))


def merge_csv_values(*values: object) -> str:
    merged = []
    seen = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = str(value).split(",")
        for item in items:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                merged.append(text)
    return ",".join(merged)


def to_decimal(value: object, default: str = "0") -> decimal.Decimal:
    if value is None or value == "":
        value = default
    return decimal.Decimal(str(value))


def password_hash() -> str:
    import bcrypt

    return bcrypt.hashpw(DEMO_PASSWORD.encode("utf8"), bcrypt.gensalt()).decode("utf8")


def current_demo_date() -> dt.datetime:
    return dt.datetime.now().replace(second=0, microsecond=0)


def select_merchant_seeds(cur):
    rows = fetch_all(
        cur,
        """
        SELECT m.*
        FROM merchant m
        LEFT JOIN orders_ds o ON o.merchant_id = m.id
        WHERE m.status = 1
        GROUP BY m.id
        ORDER BY COUNT(o.id) DESC, m.balance DESC, m.id ASC
        LIMIT 8
        """,
    )
    if len(rows) < 8:
        rows = fetch_all(cur, "SELECT * FROM merchant ORDER BY balance DESC, id ASC LIMIT 8")
    if len(rows) < 4:
        raise RuntimeError("merchant seed rows are not enough")
    return rows


def select_order_seeds(cur, table: str, merchant_ids: Sequence[int], limit: int):
    ids = ",".join(["%s"] * len(merchant_ids))
    rows = fetch_all(
        cur,
        f"""
        SELECT *
        FROM {table}
        WHERE merchant_id IN ({ids})
        ORDER BY time_create DESC, id DESC
        LIMIT %s
        """,
        list(merchant_ids) + [limit],
    )
    if len(rows) < limit // 2:
        rows = fetch_all(cur, f"SELECT * FROM {table} ORDER BY time_create DESC, id DESC LIMIT %s", [limit])
    if not rows:
        raise RuntimeError(f"{table} seed rows are not enough")
    return rows


def all_active_permission_csv(cur) -> str:
    rows = fetch_all(cur, "SELECT id FROM permissions WHERE status = 1 ORDER BY id")
    return ",".join(str(row["id"]) for row in rows)


def prepare_roles(cur):
    permissions = fetch_all(cur, "SELECT id, pid, path FROM permissions WHERE status = 1")
    role_defs = [
        (1, "super_admin", "Demo Super Admin", all_active_permission_csv(cur), "Full access demo account"),
        (
            9001,
            "demo_merchant_ops",
            "Demo Merchant Ops",
            build_permission_csv(permissions, ["/merchant/%", "/order/%", "/count/%", "/login/%"]),
            "Merchant and order operation demo",
        ),
        (
            9002,
            "demo_finance",
            "Demo Finance",
            build_permission_csv(permissions, ["/record/%", "/recharge/%", "/count/%", "/order/get%", "/login/%"]),
            "Finance review demo",
        ),
        (
            9003,
            "demo_support",
            "Demo Support",
            build_permission_csv(permissions, ["/order/get%", "/merchant/get%", "/partner/get%", "/login/%"]),
            "Read mostly support demo",
        ),
        (
            9004,
            "demo_risk",
            "Demo Risk",
            build_permission_csv(permissions, ["/partner/%", "/event/%", "/order/get%", "/login/%"]),
            "Risk and code merchant demo",
        ),
    ]
    for role_id, key_name, name, permissions_csv, description in role_defs:
        cur.execute(
            """
            INSERT INTO roles (id, parent_id, key_name, name, permissions, description, encryption, level, admin_id)
            VALUES (%s, 1, %s, %s, %s, %s, 0, 1, 1)
            ON DUPLICATE KEY UPDATE
                parent_id=VALUES(parent_id),
                key_name=VALUES(key_name),
                name=VALUES(name),
                permissions=VALUES(permissions),
                description=VALUES(description),
                encryption=VALUES(encryption),
                level=VALUES(level),
                admin_id=VALUES(admin_id)
            """,
            (role_id, key_name, name, permissions_csv, description),
        )
    cur.execute(f"DELETE FROM roles WHERE id NOT IN ({','.join(['%s'] * len(role_defs))})", [r[0] for r in role_defs])


def prepare_admins(cur, hashed_password: str):
    admins = [
        (1, "18088880000", "Demo Super Admin", 1),
        (9001, "18088880101", "Demo Merchant Ops", 9001),
        (9002, "18088880102", "Demo Finance", 9002),
        (9003, "18088880103", "Demo Support", 9003),
        (9004, "18088880104", "Demo Risk", 9004),
    ]
    for admin_id, account, name, role_id in admins:
        cur.execute(
            """
            INSERT INTO admin (id, account, hash_login, name, role, ggkey, status, parent_id, admin_id)
            VALUES (%s, %s, %s, %s, %s, %s, 1, NULL, 1)
            ON DUPLICATE KEY UPDATE
                account=VALUES(account),
                hash_login=VALUES(hash_login),
                name=VALUES(name),
                role=VALUES(role),
                ggkey=VALUES(ggkey),
                status=VALUES(status),
                parent_id=VALUES(parent_id),
                admin_id=VALUES(admin_id)
            """,
            (admin_id, account, hashed_password, name, role_id, DEMO_TOTP_SECRET),
        )
    cur.execute(
        f"DELETE FROM admin WHERE id NOT IN ({','.join(['%s'] * len(admins))})",
        [row[0] for row in admins],
    )


def prepare_merchants(cur, hashed_password: str, seeds: Sequence[Dict[str, object]]):
    cur.execute("DELETE FROM merchant_channel")
    cur.execute("DELETE FROM merchant_tree")
    cur.execute("DELETE FROM merchant")
    demo_rows = []
    base_time = current_demo_date() - dt.timedelta(minutes=30)
    for index, merchant_id in enumerate(DEMO_MERCHANT_IDS, start=1):
        seed = seeds[(index - 1) % len(seeds)]
        parent_id = None if index <= 4 else DEMO_MERCHANT_IDS[(index % 4)]
        rate_df = decimal.Decimal(str(seed.get("rate_df") or "0.0200"))
        fee_df = decimal.Decimal(str(seed.get("fee_df") or "5.0000"))
        demo_rows.append(
            {
                "id": merchant_id,
                "name": f"Demo Merchant {index:02d}",
                "cellphone": f"18888010{index:02d}",
                "hash_login": hashed_password,
                "gg_key": generate_demo_totp_secret(),
                "balance": decimal.Decimal("0.0000"),
                "balance_frozen": decimal.Decimal("0.0000"),
                "fee_df": fee_df,
                "rate_df": rate_df if rate_df > 0 else decimal.Decimal("0.0200"),
                "mc_key": generate_demo_api_key(),
                "return_url": 1,
                "status": 1,
                "status_df": 1,
                "decimal_amt_flag": seed.get("decimal_amt_flag") or 0,
                "notify_callback_type": seed.get("notify_callback_type") or 0,
                "pid": parent_id,
                "target_payment": None,
                "ip": DEMO_IP,
                "ip_df": DEMO_IP,
                "amount_fixed": seed.get("amount_fixed") or decimal.Decimal("0.00"),
                "amount_fixed_max": seed.get("amount_fixed_max") or decimal.Decimal("0.00"),
                "ds_on": 1,
                "ds_black_ips": None,
                "ds_userid_on": 1,
                "ds_black_userids": None,
                "receive_point_amt_flag": seed.get("receive_point_amt_flag") or 0,
                "time_create": base_time + dt.timedelta(seconds=index),
                "time_update": base_time + dt.timedelta(seconds=index),
            }
        )
    for row in demo_rows:
        execute_insert(cur, "merchant", row)
    for row in demo_rows:
        cur.execute("INSERT INTO merchant_tree (parent, child, distance) VALUES (%s, %s, 0)", (row["id"], row["id"]))
        if row["pid"]:
            cur.execute("INSERT INTO merchant_tree (parent, child, distance) VALUES (%s, %s, 1)", (row["pid"], row["id"]))
    channels = fetch_all(cur, "SELECT code, rate FROM channel WHERE status = 1 ORDER BY code LIMIT 12")
    for row in demo_rows:
        for channel in channels:
            cur.execute(
                """
                INSERT INTO merchant_channel (merchant_id, code, rate, otherpay, is_force, target_channel, status)
                VALUES (%s, %s, %s, NULL, 0, NULL, 1)
                """,
                (row["id"], channel["code"], channel["rate"] or decimal.Decimal("0.0200")),
            )
    return demo_rows


def prepare_partners(cur, hashed_password: str):
    cur.execute("DELETE FROM partner_invitation_code")
    cur.execute("DELETE FROM partner_tree")
    cur.execute("DELETE FROM partner")
    partners = []
    for index, partner_id in enumerate(DEMO_PARTNER_IDS, start=1):
        parent_id = None if index <= 2 else DEMO_PARTNER_IDS[0]
        row = {
            "id": partner_id,
            "name": f"Demo Partner {index:02d}",
            "cellphone": f"19999020{index:02d}",
            "hash_login": hashed_password,
            "hash_trade": hashed_password,
            "balance": decimal.Decimal("0.0000"),
            "balance_frozen": decimal.Decimal("0.0000"),
            "balance_deposit": decimal.Decimal("0.0000"),
            "vip": 1,
            "pid": parent_id,
            "status": 1,
            "certified": 1,
            "ip": 0,
            "type": 1,
            "invitation_code": f"DMP{index:05d}"[-8:],
            "authentication_token": hashlib.md5(f"demo-partner-{index}".encode()).hexdigest(),
            "email": f"partner{index}@demo.test",
            "ds_min": decimal.Decimal("0.00"),
            "ds_max": decimal.Decimal("0.00"),
            "insufficient_balance": decimal.Decimal("500.0000"),
            "rates": None,
            "negative_limit": decimal.Decimal("0.00"),
            "banned": 0,
            "failed_login_attempts": 0,
            "last_failed_login": None,
            "is_danger": 0,
            "rate": decimal.Decimal("0.0060"),
            "invitation_code_rate_config": None,
        }
        partners.append(row)
        execute_insert(cur, "partner", row)
    for row in partners:
        cur.execute("INSERT INTO partner_tree (parent, child, distance) VALUES (%s, %s, 0)", (row["id"], row["id"]))
        if row["pid"]:
            cur.execute("INSERT INTO partner_tree (parent, child, distance) VALUES (%s, %s, 1)", (row["pid"], row["id"]))
    return partners


def collect_whitelist_ips(cur) -> str:
    ips = list(DEMO_WHITELIST_IPS)
    row = fetch_one(cur, "SELECT sys_ip_w FROM sys_info WHERE id=1")
    if row:
        ips.append(row.get("sys_ip_w"))
    for row in fetch_all(cur, "SELECT ip, ip_df FROM merchant"):
        ips.append(row.get("ip"))
        ips.append(row.get("ip_df"))
    return merge_csv_values(ips)


def select_realistic_admins(cur, source_db: str):
    table = qualified_table(source_db, "admin")
    rows = fetch_all(cur, f"SELECT * FROM {table} WHERE id IN ({placeholders(REALISTIC_ADMIN_IDS)})", REALISTIC_ADMIN_IDS)
    by_id = {int(row["id"]): row for row in rows}
    selected = [by_id[admin_id] for admin_id in REALISTIC_ADMIN_IDS if admin_id in by_id and by_id[admin_id]["status"] == 1]
    if len(selected) < 5:
        extra = fetch_all(
            cur,
            f"SELECT * FROM {table} WHERE status=1 ORDER BY id LIMIT %s",
            [8],
        )
        seen = {int(row["id"]) for row in selected}
        for row in extra:
            if int(row["id"]) not in seen:
                selected.append(row)
                seen.add(int(row["id"]))
            if len(selected) >= 6:
                break
    return selected[:6]


def select_realistic_roles(cur, source_db: str, role_ids: Sequence[int]):
    if not role_ids:
        return []
    roles_table = qualified_table(source_db, "roles")
    permissions_table = qualified_table(source_db, "permissions")
    role_ids = sorted(set(int(role_id) for role_id in role_ids))
    roles = fetch_all(cur, f"SELECT * FROM {roles_table} WHERE id IN ({placeholders(role_ids)})", role_ids)
    deny_rows = fetch_all(cur, f"SELECT id FROM {permissions_table} WHERE name LIKE %s", ["禁止查看%"])
    deny_ids = {str(row["id"]) for row in deny_rows}
    for row in roles:
        if int(row["id"]) == 1 and row.get("permissions"):
            permissions = [item for item in str(row["permissions"]).split(",") if item and item not in deny_ids]
            row["permissions"] = ",".join(permissions)
    return roles


def select_realistic_merchants(cur, source_db: str):
    merchant_table = qualified_table(source_db, "merchant")
    ds_table = qualified_table(source_db, "orders_ds")
    df_table = qualified_table(source_db, "orders_df")
    sql = f"""
        SELECT m.*
        FROM {merchant_table} m
        LEFT JOIN (SELECT merchant_id, COUNT(*) count_ds FROM {ds_table} GROUP BY merchant_id) ds ON ds.merchant_id=m.id
        LEFT JOIN (SELECT merchant_id, COUNT(*) count_df FROM {df_table} GROUP BY merchant_id) df ON df.merchant_id=m.id
        WHERE m.status=1
        ORDER BY (COALESCE(ds.count_ds,0)+COALESCE(df.count_df,0)) DESC, m.balance DESC, m.id ASC
        LIMIT %s
    """
    return fetch_all(cur, sql, [REALISTIC_MERCHANT_LIMIT])


def select_realistic_partners(cur, source_db: str):
    partner_table = qualified_table(source_db, "partner")
    payment_table = qualified_table(source_db, "payment")
    ds_table = qualified_table(source_db, "orders_ds")
    df_table = qualified_table(source_db, "orders_df")
    sql = f"""
        SELECT p.*
        FROM {partner_table} p
        JOIN (
            SELECT partner_id, COUNT(*) payment_count
            FROM {payment_table}
            WHERE certified=1 AND (bank_type_id IN (97,98) OR bank_type IN ('97','98'))
            GROUP BY partner_id
        ) pay ON pay.partner_id=p.id
        LEFT JOIN (SELECT partner_id, COUNT(*) count_ds FROM {ds_table} GROUP BY partner_id) ds ON ds.partner_id=p.id
        LEFT JOIN (SELECT partner_id, COUNT(*) count_df FROM {df_table} GROUP BY partner_id) df ON df.partner_id=p.id
        WHERE p.status=1 AND p.certified=1
        ORDER BY (COALESCE(ds.count_ds,0)+COALESCE(df.count_df,0)) DESC, p.balance DESC, p.id ASC
        LIMIT %s
    """
    return fetch_all(cur, sql, [REALISTIC_PARTNER_LIMIT])


def select_realistic_payments(cur, source_db: str, partner_ids: Sequence[int]):
    payment_table = qualified_table(source_db, "payment")
    sql = f"""
        SELECT *
        FROM {payment_table}
        WHERE partner_id IN ({placeholders(partner_ids)})
          AND certified=1
          AND (bank_type_id IN (97,98) OR bank_type IN ('97','98'))
          AND COALESCE(account_iban, '') != ''
        ORDER BY partner_id, status DESC, manual_status ASC, id DESC
    """
    rows = fetch_all(cur, sql, partner_ids)
    selected = []
    per_partner = {}
    for row in rows:
        partner_id = int(row["partner_id"])
        per_partner[partner_id] = per_partner.get(partner_id, 0) + 1
        if per_partner[partner_id] <= 3:
            selected.append(row)
        if len(selected) >= REALISTIC_PAYMENT_LIMIT:
            break
    return selected


def select_realistic_merchant_channels(cur, source_db: str, merchant_ids: Sequence[int]):
    merchant_channel_table = qualified_table(source_db, "merchant_channel")
    sql = f"""
        SELECT *
        FROM {merchant_channel_table}
        WHERE merchant_id IN ({placeholders(merchant_ids)})
          AND status=1
        ORDER BY merchant_id, code
    """
    return fetch_all(cur, sql, merchant_ids)


def select_order_subset(cur, source_db: str, table: str, merchant_ids: Sequence[int], partner_ids: Sequence[int],
                        payment_ids: Sequence[int], statuses: Sequence[int], limit: int):
    order_table = qualified_table(source_db, table)
    params = list(merchant_ids) + list(partner_ids) + list(payment_ids) + list(statuses) + [limit]
    sql = f"""
        SELECT *
        FROM {order_table}
        WHERE merchant_id IN ({placeholders(merchant_ids)})
          AND partner_id IN ({placeholders(partner_ids)})
          AND payment_id IN ({placeholders(payment_ids)})
          AND status IN ({placeholders(statuses)})
        ORDER BY time_create DESC, id DESC
        LIMIT %s
    """
    return fetch_all(cur, sql, params)


def select_realistic_orders(cur, source_db: str, merchant_ids: Sequence[int], partner_ids: Sequence[int],
                            payment_ids: Sequence[int]):
    ds_rows = []
    ds_rows.extend(select_order_subset(
        cur, source_db, "orders_ds", merchant_ids, partner_ids, payment_ids, [4, 3], REALISTIC_DS_SUCCESS_LIMIT
    ))
    ds_rows.extend(select_order_subset(
        cur, source_db, "orders_ds", merchant_ids, partner_ids, payment_ids, [-1], REALISTIC_DS_FAIL_LIMIT
    ))
    df_rows = []
    df_rows.extend(select_order_subset(
        cur, source_db, "orders_df", merchant_ids, partner_ids, payment_ids, [4, 3], REALISTIC_DF_SUCCESS_LIMIT
    ))
    df_rows.extend(select_order_subset(
        cur, source_db, "orders_df", merchant_ids, partner_ids, payment_ids, [-1, -2], REALISTIC_DF_FAIL_LIMIT
    ))
    return dedupe_rows(ds_rows), dedupe_rows(df_rows)


def dedupe_rows(rows: Sequence[Dict[str, object]]):
    seen = set()
    result = []
    for row in rows:
        code = row.get("code")
        if code in seen:
            continue
        seen.add(code)
        result.append(row)
    return result


def normalize_realistic_admins(admins: Sequence[Dict[str, object]], hashed_password: str):
    rows = []
    for row in admins:
        item = dict(row)
        item["hash_login"] = hashed_password
        item["ggkey"] = DEMO_TOTP_SECRET
        item["status"] = 1
        rows.append(item)
    return rows


def normalize_realistic_merchants(merchants: Sequence[Dict[str, object]], hashed_password: str, whitelist_ips: str):
    selected_ids = {int(row["id"]) for row in merchants}
    rows = []
    for row in merchants:
        item = dict(row)
        item["hash_login"] = hashed_password
        item["gg_key"] = generate_demo_totp_secret()
        item["mc_key"] = generate_demo_api_key()
        item["status"] = 1
        item["status_df"] = 1
        item["target_payment"] = None
        item["ip"] = whitelist_ips
        item["ip_df"] = whitelist_ips
        item["balance"] = decimal.Decimal("0.0000")
        item["balance_frozen"] = decimal.Decimal("0.0000")
        if item.get("pid") and int(item["pid"]) not in selected_ids:
            item["pid"] = None
        rows.append(item)
    return rows


def normalize_realistic_partners(partners: Sequence[Dict[str, object]], hashed_password: str):
    selected_ids = {int(row["id"]) for row in partners}
    rows = []
    for row in partners:
        item = dict(row)
        item["hash_login"] = hashed_password
        item["hash_trade"] = hashed_password
        item["status"] = 1
        item["certified"] = 1
        item["balance"] = decimal.Decimal("0.0000")
        item["balance_frozen"] = decimal.Decimal("0.0000")
        item["balance_deposit"] = decimal.Decimal("0.0000")
        item["banned"] = 0
        item["failed_login_attempts"] = 0
        item["last_failed_login"] = None
        if item.get("pid") and int(item["pid"]) not in selected_ids:
            item["pid"] = None
        rows.append(item)
    return rows


def normalize_realistic_payments(payments: Sequence[Dict[str, object]]):
    rows = []
    for row in payments:
        item = dict(row)
        # 历史 payment 只用于订单闭环；不放入在线卡池，不自动派单。
        item["status"] = 0
        item["manual_status"] = 1
        item["certified"] = 1
        item["sys_balance"] = decimal.Decimal("0.0000")
        rows.append(item)
    return rows


def ensure_time(value, fallback):
    return value or fallback


def normalize_realistic_ds_orders(rows: Sequence[Dict[str, object]], merchants_by_id: Dict[int, Dict[str, object]]):
    result = []
    for row in rows:
        item = dict(row)
        item["id"] = None
        item["amount"] = to_decimal(item.get("amount")).quantize(decimal.Decimal("0.01"))
        merchant = merchants_by_id[int(item["merchant_id"])]
        rate = to_decimal(merchant.get("rate_df"), "0.0150")
        if to_decimal(item.get("poundage")) <= 0:
            item["poundage"] = (item["amount"] * rate).quantize(decimal.Decimal("0.0001"))
        else:
            item["poundage"] = to_decimal(item.get("poundage")).quantize(decimal.Decimal("0.0001"))
        item["realpay"] = (item["amount"] - item["poundage"]).quantize(decimal.Decimal("0.0001"))
        item["merchant_rate"] = to_decimal(item.get("merchant_rate"), str(rate)).quantize(decimal.Decimal("0.0001"))
        item["earn_partner_self"] = to_decimal(item.get("earn_partner_self"), "0.0000").quantize(decimal.Decimal("0.0001"))
        item["earn_partner"] = to_decimal(item.get("earn_partner"), str(item["earn_partner_self"])).quantize(decimal.Decimal("0.0001"))
        item["earn_merchant"] = to_decimal(item.get("earn_merchant"), "0.0000").quantize(decimal.Decimal("0.0001"))
        item["earn_system"] = max(
            decimal.Decimal("0.0000"),
            (item["poundage"] - item["earn_merchant"] - item["earn_partner"]).quantize(decimal.Decimal("0.0001")),
        )
        created = item.get("time_create") or current_demo_date()
        item["time_accept"] = ensure_time(item.get("time_accept"), created + dt.timedelta(seconds=1))
        if int(item["status"]) in (3, 4):
            item["time_success"] = ensure_time(item.get("time_success"), item["time_accept"] + dt.timedelta(seconds=20))
            if not item.get("utr"):
                item["utr"] = "UTR" + str(item["code"])[-12:]
        else:
            item["time_success"] = None
        result.append(item)
    return result


def normalize_realistic_df_orders(rows: Sequence[Dict[str, object]], merchants_by_id: Dict[int, Dict[str, object]]):
    result = []
    for row in rows:
        item = dict(row)
        item["id"] = None
        item["amount"] = to_decimal(item.get("amount")).quantize(decimal.Decimal("0.01"))
        merchant = merchants_by_id[int(item["merchant_id"])]
        rate = to_decimal(merchant.get("rate_df"), "0.0150")
        fee = to_decimal(merchant.get("fee_df"), "0.0000")
        if to_decimal(item.get("poundage")) <= 0:
            item["poundage"] = (item["amount"] * rate + fee).quantize(decimal.Decimal("0.0001"))
        else:
            item["poundage"] = to_decimal(item.get("poundage")).quantize(decimal.Decimal("0.0001"))
        item["realpay"] = (item["amount"] + item["poundage"]).quantize(decimal.Decimal("0.0001"))
        item["merchant_rate"] = to_decimal(item.get("merchant_rate"), str(rate)).quantize(decimal.Decimal("0.0001"))
        item["earn_partner_self"] = to_decimal(item.get("earn_partner_self"), "0.0000").quantize(decimal.Decimal("0.0001"))
        item["earn_merchant"] = to_decimal(item.get("earn_merchant"), "0.0000").quantize(decimal.Decimal("0.0001"))
        item["earn_system"] = max(
            decimal.Decimal("0.0000"),
            (item["poundage"] - item["earn_merchant"] - item["earn_partner_self"]).quantize(decimal.Decimal("0.0001")),
        )
        item["payout_type"] = item.get("payout_type") if item.get("payout_type") is not None else 1
        created = item.get("time_create") or current_demo_date()
        item["time_accept"] = ensure_time(item.get("time_accept"), created + dt.timedelta(seconds=1))
        if int(item["status"]) in (3, 4):
            item["time_success"] = ensure_time(item.get("time_success"), item["time_accept"] + dt.timedelta(seconds=20))
            if not item.get("utr"):
                item["utr"] = "DFUTR" + str(item["code"])[-12:]
        result.append(item)
    return result


def add_balance_event(events: List[Dict[str, object]], code: str, user_type: int, user_id: int, amount: decimal.Decimal,
                      record_type: int, merchant_code: object, time_create: object, remark: str):
    events.append(
        {
            "code": code,
            "user_type": user_type,
            "user_id": user_id,
            "amount": decimal.Decimal(str(amount)).quantize(decimal.Decimal("0.0001")),
            "record_type": record_type,
            "merchant_code": merchant_code,
            "time_create": time_create,
            "remark": remark,
        }
    )


def build_business_events(ds_rows: Sequence[Dict[str, object]], df_rows: Sequence[Dict[str, object]]):
    events = []
    payment_delta = {}
    for row in ds_rows:
        status = int(row["status"])
        code = row["code"]
        if status in (-1, 3, 4):
            add_balance_event(events, code, 0, int(row["partner_id"]), -to_decimal(row["amount"]), 0,
                              row.get("merchant_code"), row.get("time_accept"), "ds accept")
        if status == -1:
            add_balance_event(events, code, 0, int(row["partner_id"]), to_decimal(row["amount"]), 0,
                              row.get("merchant_code"), row.get("time_updated") or row.get("time_accept"), "ds timeout refund")
        if status in (3, 4):
            add_balance_event(events, code, 1, int(row["merchant_id"]), to_decimal(row["realpay"]), 0,
                              row.get("merchant_code"), row.get("time_success"), "ds success settle")
            if to_decimal(row.get("earn_partner_self")) > 0:
                add_balance_event(events, code, 0, int(row["partner_id"]), to_decimal(row["earn_partner_self"]), 3,
                                  row.get("merchant_code"), row.get("time_success"), "ds commission")
            payment_delta[int(row["payment_id"])] = payment_delta.get(int(row["payment_id"]), decimal.Decimal("0.0000")) + to_decimal(row["amount"])
    for row in df_rows:
        status = int(row["status"])
        code = row["code"]
        add_balance_event(events, code, 1, int(row["merchant_id"]), -to_decimal(row["realpay"]), 1,
                          row.get("merchant_code"), row.get("time_create"), "df create debit")
        if status in (3, 4):
            add_balance_event(events, code, 0, int(row["partner_id"]), to_decimal(row["amount"]), 1,
                              row.get("merchant_code"), row.get("time_success"), "df success principal")
            if to_decimal(row.get("earn_partner_self")) > 0:
                add_balance_event(events, code, 0, int(row["partner_id"]), to_decimal(row["earn_partner_self"]), 3,
                                  row.get("merchant_code"), row.get("time_success"), "df commission")
            payment_delta[int(row["payment_id"])] = payment_delta.get(int(row["payment_id"]), decimal.Decimal("0.0000")) - to_decimal(row["amount"])
        elif status in (-1, -2):
            add_balance_event(events, code, 1, int(row["merchant_id"]), to_decimal(row["realpay"]), 1,
                              row.get("merchant_code"), row.get("time_updated") or row.get("time_create"), "df fail refund")
    return events, payment_delta


def compute_opening_balances_from_events(entity_ids: Sequence[int], events: Sequence[Dict[str, object]], user_type: int,
                                         base_amount: decimal.Decimal):
    balances = {}
    for entity_id in entity_ids:
        running = decimal.Decimal("0.0000")
        lowest = decimal.Decimal("0.0000")
        for event in sorted(events, key=lambda item: item["time_create"] or dt.datetime.min):
            if event["user_type"] == user_type and int(event["user_id"]) == int(entity_id):
                running += event["amount"]
                lowest = min(lowest, running)
        opening = base_amount
        if lowest < 0:
            opening = max(opening, (-lowest + decimal.Decimal("10000.0000")).quantize(decimal.Decimal("0.0001")))
        balances[int(entity_id)] = opening
    return balances


def insert_balance_events(cur, merchant_rows, partner_rows, events):
    merchant_balances = compute_opening_balances_from_events(
        [int(row["id"]) for row in merchant_rows], events, 1, decimal.Decimal("100000.0000")
    )
    partner_balances = compute_opening_balances_from_events(
        [int(row["id"]) for row in partner_rows], events, 0, decimal.Decimal("500000.0000")
    )
    running = {("merchant", key): value for key, value in merchant_balances.items()}
    running.update({("partner", key): value for key, value in partner_balances.items()})
    first_time = min((event["time_create"] for event in events if event.get("time_create")), default=current_demo_date())
    opening_time = first_time - dt.timedelta(seconds=1)
    for merchant_id, opening in merchant_balances.items():
        cur.execute(
            """
            INSERT INTO balance_record
                (code, user_type, user_id, change_before, amount, change_after, record_type, admin_id, remark, merchant_code, time_create)
            VALUES (%s, 1, %s, 0, %s, %s, 0, 1, %s, NULL, %s)
            """,
            (f"DEMOOPENM{merchant_id}", merchant_id, opening, opening, "demo opening merchant balance", opening_time),
        )
    for partner_id, opening in partner_balances.items():
        cur.execute(
            """
            INSERT INTO balance_record
                (code, user_type, user_id, change_before, amount, change_after, record_type, admin_id, remark, merchant_code, time_create)
            VALUES (%s, 0, %s, 0, %s, %s, 0, 1, %s, NULL, %s)
            """,
            (f"DEMOOPENP{partner_id}", partner_id, opening, opening, "demo opening partner balance", opening_time),
        )
    for event in sorted(events, key=lambda item: item["time_create"] or dt.datetime.min):
        table_key = "partner" if event["user_type"] == 0 else "merchant"
        key = (table_key, int(event["user_id"]))
        before = running[key]
        after = (before + event["amount"]).quantize(decimal.Decimal("0.0001"))
        running[key] = after
        cur.execute(
            """
            INSERT INTO balance_record
                (code, user_type, user_id, change_before, amount, change_after, record_type, admin_id, remark, merchant_code, time_create)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
            """,
            (
                event["code"],
                event["user_type"],
                event["user_id"],
                before,
                event["amount"],
                after,
                event["record_type"],
                event["remark"],
                event["merchant_code"],
                event["time_create"],
            ),
        )
    for merchant_id, opening in merchant_balances.items():
        cur.execute("UPDATE merchant SET balance=%s, balance_frozen=0 WHERE id=%s", (running[("merchant", merchant_id)], merchant_id))
    for partner_id, opening in partner_balances.items():
        cur.execute(
            "UPDATE partner SET balance=%s, balance_frozen=0, balance_deposit=0 WHERE id=%s",
            (running[("partner", partner_id)], partner_id),
        )


def insert_tree_rows(cur, table: str, rows: Sequence[Dict[str, object]]):
    tree_table = f"{table}_tree"
    id_key = "id"
    selected_ids = {int(row[id_key]) for row in rows}
    cur.execute(f"DELETE FROM {tree_table}")
    for row in rows:
        row_id = int(row[id_key])
        cur.execute(f"INSERT INTO {tree_table} (parent, child, distance) VALUES (%s, %s, 0)", (row_id, row_id))
        if row.get("pid") and int(row["pid"]) in selected_ids:
            cur.execute(f"INSERT INTO {tree_table} (parent, child, distance) VALUES (%s, %s, 1)", (int(row["pid"]), row_id))


def apply_realistic_demo_data(cur, source_db: str, hashed_password: str, whitelist_ips: str):
    admins = select_realistic_admins(cur, source_db)
    roles = select_realistic_roles(cur, source_db, [int(row["role"]) for row in admins])
    merchant_whitelist_ips = merge_csv_values(DEMO_WHITELIST_IPS)
    merchants = normalize_realistic_merchants(select_realistic_merchants(cur, source_db), hashed_password, merchant_whitelist_ips)
    partners = normalize_realistic_partners(select_realistic_partners(cur, source_db), hashed_password)
    if len(merchants) < 4 or len(partners) < 4:
        raise RuntimeError("realistic source rows are not enough")
    payments = normalize_realistic_payments(select_realistic_payments(cur, source_db, [int(row["id"]) for row in partners]))
    if not payments:
        raise RuntimeError("realistic payment rows are not enough")
    merchant_ids = [int(row["id"]) for row in merchants]
    partner_ids = [int(row["id"]) for row in partners]
    merchant_channels = select_realistic_merchant_channels(cur, source_db, merchant_ids)
    payment_ids = [int(row["id"]) for row in payments]
    ds_rows, df_rows = select_realistic_orders(cur, source_db, merchant_ids, partner_ids, payment_ids)
    if len(ds_rows) < 100 or len(df_rows) < 50:
        raise RuntimeError("realistic order rows are not enough")
    merchants_by_id = {int(row["id"]): row for row in merchants}
    ds_rows = normalize_realistic_ds_orders(ds_rows, merchants_by_id)
    df_rows = normalize_realistic_df_orders(df_rows, merchants_by_id)
    events, payment_delta = build_business_events(ds_rows, df_rows)

    reset_tables(cur)
    cur.execute("DELETE FROM admin")
    cur.execute("DELETE FROM roles")
    cur.execute("DELETE FROM merchant_channel")
    cur.execute("DELETE FROM merchant_tree")
    cur.execute("DELETE FROM merchant")
    cur.execute("DELETE FROM partner_invitation_code")
    cur.execute("DELETE FROM partner_tree")
    cur.execute("DELETE FROM partner")

    for row in roles:
        execute_insert(cur, "roles", row)
    for row in normalize_realistic_admins(admins, hashed_password):
        execute_insert(cur, "admin", row)
    for row in merchants:
        execute_insert(cur, "merchant", row)
    for row in merchant_channels:
        execute_insert(cur, "merchant_channel", row)
    insert_tree_rows(cur, "merchant", merchants)
    for row in partners:
        execute_insert(cur, "partner", row)
    insert_tree_rows(cur, "partner", partners)
    for row in payments:
        row["sys_balance"] = payment_delta.get(int(row["id"]), decimal.Decimal("0.0000")).quantize(decimal.Decimal("0.0001"))
        execute_insert(cur, "payment", row)
    for row in ds_rows:
        execute_insert(cur, "orders_ds", row)
    for row in df_rows:
        execute_insert(cur, "orders_df", row)
    insert_balance_events(cur, merchants, partners, events)
    insert_summary_rows(cur)
    update_sys_info(cur, whitelist_ips)
    return validate(cur)


def reset_tables(cur):
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in RESET_TABLES:
        if table_exists(cur, table):
            cur.execute(f"TRUNCATE TABLE {table}")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")


def clone_ds_order(seed: Dict[str, object], index: int, merchant: Dict[str, object], partner_id: int, now: dt.datetime):
    row = dict(seed)
    status_cycle = [3, 4, 3, -1, 0, 1, 2]
    status = status_cycle[index % len(status_cycle)]
    created = demo_order_created_at(now, index, len(DEMO_MERCHANT_IDS), 11)
    amount = normalize_amount(decimal.Decimal(str(seed.get("amount") or 0)), index)
    rate = decimal.Decimal(str(merchant["rate_df"] or "0.0200"))
    poundage = (amount * rate).quantize(decimal.Decimal("0.0001"))
    realpay = (amount - poundage).quantize(decimal.Decimal("0.0001"))
    time_create, time_accept, time_payed, time_success = ds_timestamps(created, status)
    row.update(
        {
            "id": None,
            "code": f"DSDEMO{now.strftime('%m%d')}{index:05d}",
            "amount": amount,
            "realpay": realpay,
            "poundage": poundage,
            "status": status,
            "callback": "https://merchant.demo.test/callback",
            "notice_api": "demo",
            "notify": "demo-notify",
            "player_ip": f"198.51.100.{index % 200 + 1}",
            "remark": "demo data",
            "pay_url": "https://pay.demo.test/order",
            "time_create": time_create,
            "time_accept": time_accept,
            "time_payed": time_payed,
            "time_success": time_success,
            "merchant_id": merchant["id"],
            "merchant_code": f"MDS{index:08d}",
            "merchant_rate": rate,
            "earn_merchant": realpay if status >= 3 else decimal.Decimal("0.0000"),
            "partner_id": partner_id if status > 0 else None,
            "earn_partner_self": decimal.Decimal("0.0000"),
            "earn_partner": decimal.Decimal("0.0000"),
            "payment_id": None,
            "upi": "demo@upi",
            "utr": f"UTRDEMO{index:08d}" if status >= 3 else None,
            "auth_code": f"AUTHDEMO{index:08d}",
            "realname": "Demo Player",
            "player_provence": "Demo Province",
            "otherpay": None,
            "earn_system": poundage if status >= 3 else decimal.Decimal("0.0000"),
            "time_updated": time_create,
            "third_party_id": "demo-third",
            "third_party_order_number": f"TPDS{index:08d}",
            "third_party_name": "Demo Third",
            "user_id": f"demo-user-{index % 20:02d}",
            "original_amount": amount,
            "tax": decimal.Decimal("0.0000"),
            "trans_id": f"TRDS{index:08d}",
            "count_statics": None,
        }
    )
    return row


def clone_df_order(seed: Dict[str, object], index: int, merchant: Dict[str, object], partner_id: int, now: dt.datetime):
    row = dict(seed)
    status_cycle = [3, 4, -1, 0, 1, 2]
    status = status_cycle[index % len(status_cycle)]
    created = demo_order_created_at(now, index, len(DEMO_MERCHANT_IDS), 17)
    amount = normalize_amount(decimal.Decimal(str(seed.get("amount") or 0)), index)
    fee = decimal.Decimal(str(merchant["fee_df"] or "5.0000")).quantize(decimal.Decimal("0.0001"))
    realpay = (amount + fee).quantize(decimal.Decimal("0.0001"))
    time_create, time_accept, time_payed, time_success = ds_timestamps(created, status)
    row.update(
        {
            "id": None,
            "code": f"DFDEMO{now.strftime('%m%d')}{index:05d}",
            "amount": amount,
            "realpay": realpay,
            "poundage": fee,
            "status": status,
            "payment_name": f"Demo Receiver {index % 20:02d}",
            "payment_account": f"DEMOACCT{index:08d}",
            "payment_bank": "Demo Bank",
            "ifsc": "DEMOIFSC",
            "notice_api": "demo",
            "notify": "demo-notify",
            "remark": "demo payout",
            "merchant_id": merchant["id"],
            "merchant_code": f"MDF{index:08d}",
            "merchant_rate": decimal.Decimal(str(merchant["rate_df"] or "0.0200")),
            "earn_merchant": decimal.Decimal("0.0000"),
            "time_create": time_create,
            "time_accept": time_accept,
            "time_payed": time_payed,
            "time_success": time_success,
            "time_updated": time_create,
            "partner_id": partner_id if status > 0 else None,
            "payment_id": None,
            "earn_partner_self": decimal.Decimal("0.0000"),
            "otherpay_id": None,
            "otherpay": None,
            "otherpay_code": None,
            "earn_system": fee if status >= 3 else decimal.Decimal("0.0000"),
            "payment_img": 0,
            "sys_remark": None,
            "utr": f"DFUTR{index:08d}" if status >= 3 else None,
            "debit_account": None,
            "parent_id": "",
            "is_split": 0,
            "is_del": 0,
            "payout_type": 0,
            "target_payment": None,
            "retry_count": 0,
        }
    )
    return row


def insert_demo_orders(cur, ds_seeds, df_seeds, merchants, partners):
    now = current_demo_date()
    ds_rows = []
    df_rows = []
    partner_ids = [p["id"] for p in partners]
    for index in range(1, 321):
        merchant = merchants[(index - 1) % len(merchants)]
        seed = ds_seeds[(index - 1) % len(ds_seeds)]
        ds_rows.append(clone_ds_order(seed, index, merchant, partner_ids[index % len(partner_ids)], now))
    for index in range(1, 121):
        merchant = merchants[(index - 1) % len(merchants)]
        seed = df_seeds[(index - 1) % len(df_seeds)]
        df_rows.append(clone_df_order(seed, index, merchant, partner_ids[index % len(partner_ids)], now))
    for row in ds_rows:
        execute_insert(cur, "orders_ds", row)
    for row in df_rows:
        execute_insert(cur, "orders_df", row)
    return ds_rows, df_rows


def order_balance_delta(order: Dict[str, object]) -> decimal.Decimal:
    if order["status"] < 3:
        return decimal.Decimal("0.0000")
    if str(order["code"]).startswith("DSDEMO"):
        return decimal.Decimal(str(order["realpay"]))
    return -decimal.Decimal(str(order["realpay"]))


def compute_opening_balances(merchants, ds_rows, df_rows):
    running = {row["id"]: decimal.Decimal("0.0000") for row in merchants}
    lowest = dict(running)
    for order in sorted(ds_rows + df_rows, key=lambda item: item["time_create"]):
        merchant_id = order["merchant_id"]
        running[merchant_id] += order_balance_delta(order)
        lowest[merchant_id] = min(lowest[merchant_id], running[merchant_id])

    balances = {}
    for index, merchant in enumerate(merchants, start=1):
        merchant_id = merchant["id"]
        base_balance = decimal.Decimal("10000.0000") + decimal.Decimal(index * 2000)
        required_balance = decimal.Decimal("10000.0000")
        if lowest[merchant_id] < 0:
            required_balance = (-lowest[merchant_id] + decimal.Decimal("10000.0000")).quantize(decimal.Decimal("0.0001"))
        balances[merchant_id] = max(base_balance, required_balance)
    return balances


def insert_balance_records(cur, merchants, ds_rows, df_rows):
    balances = compute_opening_balances(merchants, ds_rows, df_rows)
    record_index = 1
    for order in sorted(ds_rows + df_rows, key=lambda item: item["time_create"]):
        if order["status"] < 3:
            continue
        merchant_id = order["merchant_id"]
        before = balances[merchant_id]
        amount = order_balance_delta(order)
        after = (before + amount).quantize(decimal.Decimal("0.0001"))
        balances[merchant_id] = after
        cur.execute(
            """
            INSERT INTO balance_record
                (code, user_type, user_id, change_before, amount, change_after, record_type, admin_id, remark, merchant_code, time_create)
            VALUES (%s, 1, %s, %s, %s, %s, 0, 1, %s, %s, %s)
            """,
            (
                order["code"],
                merchant_id,
                before,
                amount,
                after,
                "demo order balance",
                order["merchant_code"],
                order["time_success"] or order["time_create"],
            ),
        )
        record_index += 1
    for merchant_id, balance in balances.items():
        cur.execute("UPDATE merchant SET balance=%s, balance_frozen=0 WHERE id=%s", (balance, merchant_id))


def insert_summary_rows(cur):
    cur.execute(
        """
        INSERT INTO balance_count_record
            (balance_p, balance_p_frozen, balance_p_deposit, balance_m, balance_m_frozen,
             balance_p_frozen_outside, balance_p_outside, balance_p_inside, balance_p_frozen_inside)
        SELECT
            COALESCE((SELECT SUM(balance) FROM partner), 0),
            COALESCE((SELECT SUM(balance_frozen) FROM partner), 0),
            COALESCE((SELECT SUM(balance_deposit) FROM partner), 0),
            COALESCE((SELECT SUM(balance) FROM merchant), 0),
            COALESCE((SELECT SUM(balance_frozen) FROM merchant), 0),
            COALESCE((SELECT SUM(balance_frozen) FROM partner WHERE type=1), 0),
            COALESCE((SELECT SUM(balance) FROM partner WHERE type=1), 0),
            COALESCE((SELECT SUM(balance) FROM partner WHERE type=0), 0),
            COALESCE((SELECT SUM(balance_frozen) FROM partner WHERE type=0), 0)
        """
    )
    for table, source, id_column in [
        ("statistics_daily_merchant_orders_ds", "orders_ds", "merchant_id"),
        ("statistics_daily_merchant_orders_df", "orders_df", "merchant_id"),
        ("statistics_daily_partner_orders_ds", "orders_ds", "partner_id"),
        ("statistics_daily_partner_orders_df", "orders_df", "partner_id"),
    ]:
        cur.execute(
            f"""
            INSERT INTO {table}
                ({id_column}, stats_date, order_total, order_success, order_fail,
                 order_amount, order_amount_success, order_amount_fail, order_poundage, rate)
            SELECT
                {id_column},
                DATE(time_create),
                COUNT(*),
                SUM(CASE WHEN status >= 3 THEN 1 ELSE 0 END),
                SUM(CASE WHEN status < 0 THEN 1 ELSE 0 END),
                SUM(amount),
                SUM(CASE WHEN status >= 3 THEN amount ELSE 0 END),
                SUM(CASE WHEN status < 0 THEN amount ELSE 0 END),
                SUM(CASE WHEN status >= 3 THEN poundage ELSE 0 END),
                ROUND(SUM(CASE WHEN status >= 3 THEN 1 ELSE 0 END) / COUNT(*) * 100, 2)
            FROM {source}
            WHERE {id_column} IS NOT NULL
            GROUP BY {id_column}, DATE(time_create)
            """
        )


def update_sys_info(cur, whitelist_ips: str = None):
    row = fetch_one(cur, "SELECT sys_ip_w FROM sys_info WHERE id=1")
    if not row:
        return
    ips = merge_csv_values(row.get("sys_ip_w"), whitelist_ips or DEMO_IP)
    cur.execute("UPDATE sys_info SET sys_ip_w=%s WHERE id=1", [ips])


def validate(cur):
    checks = {
        "admin_count": "SELECT COUNT(*) AS value FROM admin",
        "role_count": "SELECT COUNT(*) AS value FROM roles",
        "merchant_count": "SELECT COUNT(*) AS value FROM merchant",
        "merchant_channel_count": "SELECT COUNT(*) AS value FROM merchant_channel",
        "partner_count": "SELECT COUNT(*) AS value FROM partner",
        "payment_count": "SELECT COUNT(*) AS value FROM payment",
        "payment_active_count": "SELECT COUNT(*) AS value FROM payment WHERE status=1 OR manual_status=0",
        "payment_d_count": "SELECT COUNT(*) AS value FROM payment_d",
        "orders_ds_count": "SELECT COUNT(*) AS value FROM orders_ds",
        "orders_df_count": "SELECT COUNT(*) AS value FROM orders_df",
        "balance_record_count": "SELECT COUNT(*) AS value FROM balance_record",
        "merchant_with_target_payment": "SELECT COUNT(*) AS value FROM merchant WHERE target_payment IS NOT NULL AND target_payment != ''",
        "merchant_negative_balance": "SELECT COUNT(*) AS value FROM merchant WHERE balance < 0 OR balance_frozen < 0",
        "partner_negative_balance": "SELECT COUNT(*) AS value FROM partner WHERE balance < 0 OR balance_frozen < 0 OR balance_deposit < 0",
        "sys_info_demo_ip_count": "SELECT COUNT(*) AS value FROM sys_info WHERE id=1 AND sys_ip_w LIKE '%%103.135.100.192%%'",
        "merchant_demo_ip_count": "SELECT COUNT(*) AS value FROM merchant WHERE ip LIKE '%%103.135.100.192%%' AND ip_df LIKE '%%103.135.100.192%%'",
        "ds_demo_marker_count": "SELECT COUNT(*) AS value FROM orders_ds WHERE code LIKE 'DSDEMO%%' OR upi='demo@upi' OR realname='Demo Player'",
        "df_demo_marker_count": "SELECT COUNT(*) AS value FROM orders_df WHERE code LIKE 'DFDEMO%%' OR payment_bank='Demo Bank' OR payment_name LIKE 'Demo Receiver%%'",
        "ds_missing_payment_count": "SELECT COUNT(*) AS value FROM orders_ds o LEFT JOIN payment p ON p.id=o.payment_id WHERE o.status IN (-1,3,4) AND (o.payment_id IS NULL OR p.id IS NULL)",
        "df_missing_payment_count": "SELECT COUNT(*) AS value FROM orders_df o LEFT JOIN payment p ON p.id=o.payment_id WHERE o.status IN (-1,-2,3,4) AND (o.payment_id IS NULL OR p.id IS NULL)",
        "merchant_balance_record_last_mismatch": "SELECT COUNT(*) AS value FROM merchant m LEFT JOIN (SELECT br.user_id, br.change_after FROM balance_record br JOIN (SELECT user_id, MAX(id) id FROM balance_record WHERE user_type=1 GROUP BY user_id) t ON t.id=br.id) x ON x.user_id=m.id WHERE m.balance <> x.change_after OR x.change_after IS NULL",
        "partner_balance_record_last_mismatch": "SELECT COUNT(*) AS value FROM partner p LEFT JOIN (SELECT br.user_id, br.change_after FROM balance_record br JOIN (SELECT user_id, MAX(id) id FROM balance_record WHERE user_type=0 GROUP BY user_id) t ON t.id=br.id) x ON x.user_id=p.id WHERE p.balance <> x.change_after OR x.change_after IS NULL",
        "merchant_invalid_demo_mc_key": "SELECT COUNT(*) AS value FROM merchant WHERE mc_key IS NULL OR CHAR_LENGTH(mc_key) != 32 OR mc_key REGEXP '[^0-9a-f]'",
        "merchant_invalid_demo_gg_key": "SELECT COUNT(*) AS value FROM merchant WHERE gg_key IS NULL OR CHAR_LENGTH(gg_key) != 16 OR gg_key REGEXP '[^A-Z2-7]'",
        "merchant_duplicate_demo_mc_key": "SELECT COUNT(*) - COUNT(DISTINCT mc_key) AS value FROM merchant",
        "merchant_duplicate_demo_gg_key": "SELECT COUNT(*) - COUNT(DISTINCT gg_key) AS value FROM merchant",
    }
    return {name: fetch_one(cur, sql)["value"] for name, sql in checks.items()}


def assert_expected_result(result: Dict[str, object]):
    expected = {
        "admin_count": 6,
        "merchant_count": REALISTIC_MERCHANT_LIMIT,
        "partner_count": REALISTIC_PARTNER_LIMIT,
        "payment_d_count": 0,
        "merchant_with_target_payment": 0,
        "merchant_negative_balance": 0,
        "partner_negative_balance": 0,
        "sys_info_demo_ip_count": 1,
        "merchant_demo_ip_count": REALISTIC_MERCHANT_LIMIT,
        "payment_active_count": 0,
        "ds_demo_marker_count": 0,
        "df_demo_marker_count": 0,
        "ds_missing_payment_count": 0,
        "df_missing_payment_count": 0,
        "merchant_balance_record_last_mismatch": 0,
        "partner_balance_record_last_mismatch": 0,
        "merchant_invalid_demo_mc_key": 0,
        "merchant_invalid_demo_gg_key": 0,
        "merchant_duplicate_demo_mc_key": 0,
        "merchant_duplicate_demo_gg_key": 0,
    }
    errors = []
    for key, value in expected.items():
        if result.get(key) != value:
            errors.append(f"{key} expected {value}, got {result.get(key)}")
    if result.get("balance_record_count", 0) <= 0:
        errors.append("balance_record_count expected > 0")
    if result.get("role_count", 0) < 4:
        errors.append("role_count expected >= 4")
    if result.get("merchant_channel_count", 0) <= 0:
        errors.append("merchant_channel_count expected > 0")
    if result.get("payment_count", 0) <= 0:
        errors.append("payment_count expected > 0")
    if result.get("orders_ds_count", 0) < 100:
        errors.append("orders_ds_count expected >= 100")
    if result.get("orders_df_count", 0) < 50:
        errors.append("orders_df_count expected >= 50")
    if errors:
        raise RuntimeError("; ".join(errors))


def apply_demo_data(cur, source_db: str = None):
    cur.execute("SELECT GET_LOCK('demo_data_refresh', 30) AS locked")
    locked = cur.fetchone()["locked"]
    if locked != 1:
        raise RuntimeError("failed to acquire demo_data_refresh lock")
    try:
        try:
            cur.execute("SET SESSION sql_log_bin=0")
        except Exception:
            pass
        source_db = source_db or fetch_one(cur, "SELECT DATABASE() AS db")["db"]
        hashed_password = password_hash()
        whitelist_ips = collect_whitelist_ips(cur)
        if source_db != fetch_one(cur, "SELECT DATABASE() AS db")["db"]:
            result = apply_realistic_demo_data(cur, source_db, hashed_password, whitelist_ips)
        else:
            raise RuntimeError("realistic demo data requires --source-database pointing at the restored old-data database")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS demo_data_refresh_audit (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                refreshed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                admin_count INT NOT NULL,
                merchant_count INT NOT NULL,
                orders_ds_count INT NOT NULL,
                orders_df_count INT NOT NULL,
                note VARCHAR(255) NOT NULL
            )
            """
        )
        assert_expected_result(result)
        cur.execute(
            """
            INSERT INTO demo_data_refresh_audit
                (admin_count, merchant_count, orders_ds_count, orders_df_count, note)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                result["admin_count"],
                result["merchant_count"],
                result["orders_ds_count"],
                result["orders_df_count"],
                "realistic demo data refresh",
            ),
        )
        return result
    finally:
        cur.execute("SELECT RELEASE_LOCK('demo_data_refresh')")


def main():
    args = parse_args()
    import pymysql

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            before = validate(cur)
            host = fetch_one(cur, "SELECT @@hostname AS hostname")["hostname"]
            print(f"mysql_host={host}")
            print("before=" + repr(before))
            if not args.apply:
                print("dry_run=1")
                conn.rollback()
                return
            if not args.i_understand_this_rewrites_test_data:
                raise RuntimeError("missing --i-understand-this-rewrites-test-data")
            after = apply_demo_data(cur, args.source_database)
            conn.commit()
            print("after=" + repr(after))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
