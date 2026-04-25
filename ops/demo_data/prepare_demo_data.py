#!/usr/bin/env python3
import argparse
import datetime as dt
import decimal
import fnmatch
import hashlib
import random
from typing import Dict, Iterable, List, Sequence, Tuple


DEMO_IP = "103.135.100.192"
DEMO_PASSWORD = "123456"
DEMO_TOTP_SECRET = "JBSWY3DPEHPK3PXP"

DEMO_ADMIN_IDS = [1, 9001, 9002, 9003, 9004]
DEMO_MERCHANT_IDS = [9101, 9102, 9103, 9104, 9105, 9106, 9107, 9108]
DEMO_PARTNER_IDS = [9201, 9202, 9203, 9204]

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
                "gg_key": DEMO_TOTP_SECRET,
                "balance": decimal.Decimal("0.0000"),
                "balance_frozen": decimal.Decimal("0.0000"),
                "fee_df": fee_df,
                "rate_df": rate_df if rate_df > 0 else decimal.Decimal("0.0200"),
                "mc_key": hashlib.md5(f"demo-merchant-{index}".encode()).hexdigest(),
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
    created = now - dt.timedelta(days=index % 10, minutes=(index * 11) % 480)
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
    created = now - dt.timedelta(days=index % 10, minutes=(index * 17) % 480)
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


def update_sys_info(cur):
    row = fetch_one(cur, "SELECT sys_ip_w FROM sys_info WHERE id=1")
    if not row:
        return
    ips = [item.strip() for item in str(row.get("sys_ip_w") or "").split(",") if item.strip()]
    if DEMO_IP not in ips:
        ips.append(DEMO_IP)
    cur.execute("UPDATE sys_info SET sys_ip_w=%s WHERE id=1", [",".join(ips)])


def validate(cur):
    checks = {
        "admin_count": "SELECT COUNT(*) AS value FROM admin",
        "demo_role_count": "SELECT COUNT(*) AS value FROM roles WHERE id IN (1,9001,9002,9003,9004)",
        "merchant_count": "SELECT COUNT(*) AS value FROM merchant",
        "partner_count": "SELECT COUNT(*) AS value FROM partner",
        "payment_count": "SELECT COUNT(*) AS value FROM payment",
        "payment_d_count": "SELECT COUNT(*) AS value FROM payment_d",
        "orders_ds_count": "SELECT COUNT(*) AS value FROM orders_ds",
        "orders_df_count": "SELECT COUNT(*) AS value FROM orders_df",
        "balance_record_count": "SELECT COUNT(*) AS value FROM balance_record",
        "merchant_with_target_payment": "SELECT COUNT(*) AS value FROM merchant WHERE target_payment IS NOT NULL AND target_payment != ''",
        "merchant_negative_balance": "SELECT COUNT(*) AS value FROM merchant WHERE balance < 0 OR balance_frozen < 0",
        "sys_info_demo_ip_count": "SELECT COUNT(*) AS value FROM sys_info WHERE id=1 AND sys_ip_w LIKE '%%103.135.100.192%%'",
        "merchant_demo_ip_count": "SELECT COUNT(*) AS value FROM merchant WHERE ip LIKE '%%103.135.100.192%%' AND ip_df LIKE '%%103.135.100.192%%'",
    }
    return {name: fetch_one(cur, sql)["value"] for name, sql in checks.items()}


def assert_expected_result(result: Dict[str, object]):
    expected = {
        "admin_count": 5,
        "demo_role_count": 5,
        "merchant_count": 8,
        "partner_count": 4,
        "payment_count": 0,
        "payment_d_count": 0,
        "orders_ds_count": 320,
        "orders_df_count": 120,
        "merchant_with_target_payment": 0,
        "merchant_negative_balance": 0,
        "sys_info_demo_ip_count": 1,
        "merchant_demo_ip_count": 8,
    }
    errors = []
    for key, value in expected.items():
        if result.get(key) != value:
            errors.append(f"{key} expected {value}, got {result.get(key)}")
    if result.get("balance_record_count", 0) <= 0:
        errors.append("balance_record_count expected > 0")
    if errors:
        raise RuntimeError("; ".join(errors))


def apply_demo_data(cur):
    cur.execute("SELECT GET_LOCK('demo_data_refresh', 30) AS locked")
    locked = cur.fetchone()["locked"]
    if locked != 1:
        raise RuntimeError("failed to acquire demo_data_refresh lock")
    try:
        try:
            cur.execute("SET SESSION sql_log_bin=0")
        except Exception:
            pass
        seeds = select_merchant_seeds(cur)
        seed_ids = [int(row["id"]) for row in seeds]
        ds_seeds = select_order_seeds(cur, "orders_ds", seed_ids, 320)
        df_seeds = select_order_seeds(cur, "orders_df", seed_ids, 120)
        hashed_password = password_hash()
        reset_tables(cur)
        prepare_roles(cur)
        prepare_admins(cur, hashed_password)
        merchants = prepare_merchants(cur, hashed_password, seeds)
        partners = prepare_partners(cur, hashed_password)
        ds_rows, df_rows = insert_demo_orders(cur, ds_seeds, df_seeds, merchants, partners)
        insert_balance_records(cur, merchants, ds_rows, df_rows)
        insert_summary_rows(cur)
        update_sys_info(cur)
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
        result = validate(cur)
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
                "demo data refresh",
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
            after = apply_demo_data(cur)
            conn.commit()
            print("after=" + repr(after))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
