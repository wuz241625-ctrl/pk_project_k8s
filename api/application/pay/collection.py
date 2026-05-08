"""Collection dispatch eligibility checks."""

from typing import List
from application.payment_eligibility import can_dispatch_ds, collection_sql_condition


def _to_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _collection_dispatch_extra_sql_condition(alias="pay", channel_code=None) -> str:
    return collection_sql_condition(alias, channel_code)


def _is_collection_dispatch_enabled(payment) -> bool:
    return can_dispatch_ds(payment)


def _manual_lock_update_fields(payment):
    return {"manual_status": 1, "collection_status": 0}


async def _is_collection_payment_online(handler, payment_id, bank_type_id, bank_type=None, payment=None):
    if payment is None:
        payment = await handler.get_result_by_condition(
            'payment',
            ['wallet_status', 'account_accno', 'collection_status', 'status', 'certified', 'manual_status'],
            {'id': payment_id},
        )
    return _is_collection_dispatch_enabled(payment)


async def _mysql_collection_ids(handler, channel_code=None):
    sql = """
        select id
        from payment pay
        where {condition}
    """.format(condition=_collection_dispatch_extra_sql_condition("pay", channel_code))
    rows = await handler.query(sql)
    return {str(row["id"]) for row in rows or []}


async def _collection_online_payment_ids(handler, channel_code=None):
    payment_ids = await _mysql_collection_ids(handler, channel_code)
    return sorted((payment_id for payment_id in payment_ids if payment_id.isdigit()), key=int)


async def _is_collection_payment_online_by_id(handler, payment_id):
    payment = await handler.get_result_by_condition(
        'payment',
        ['wallet_status', 'account_accno', 'collection_status', 'status', 'certified', 'manual_status'],
        {'id': payment_id},
    )
    if not payment:
        return False
    return await _is_collection_payment_online(
        handler,
        payment_id,
        (payment or {}).get('bank_type_id'),
        bank_type=(payment or {}).get('bank_type'),
        payment=payment,
    )
