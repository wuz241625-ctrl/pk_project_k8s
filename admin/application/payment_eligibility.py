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


def can_dispatch_df(row):
    return to_int(field(row, "payout_status")) == 1


def can_dispatch_ds(row):
    return to_int(field(row, "collection_status")) == 1


def payout_sql_condition(alias="payment"):
    return "({alias}.payout_status = 1)".format(alias=alias)
