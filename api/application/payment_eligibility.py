def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def field(row, name, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def can_collect_statement(row):
    return to_int(field(row, "wallet_status")) == 1


def can_dispatch_ds(row):
    return to_int(field(row, "collection_status")) == 1


def can_dispatch_df(row):
    return to_int(field(row, "payout_status")) == 1


def channel_sql_condition(alias="pay", channel_code=None):
    if channel_code is None:
        return "1 = 1"
    safe_channel_code = str(channel_code).replace("'", "''")
    return "find_in_set('{channel_code}', replace(coalesce({alias}.channel, ''), ' ', '')) > 0".format(
        alias=alias,
        channel_code=safe_channel_code,
    )


def collection_sql_condition(alias="pay", channel_code=None):
    return (
        "({alias}.collection_status = 1 "
        "AND {channel_condition})"
    ).format(
        alias=alias,
        channel_condition=channel_sql_condition(alias, channel_code),
    )


def payout_sql_condition(alias="pay"):
    return "({alias}.payout_status = 1)".format(alias=alias)


def statement_collection_sql_condition(alias="pay"):
    return "({alias}.wallet_status = 1)".format(alias=alias)
