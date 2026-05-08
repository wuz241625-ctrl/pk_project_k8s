"""Dispatch engine — candidate selection, weighted random, order assignment."""

import datetime
import random
import re
import time

from decimal import Decimal
from typing import List, Tuple

from aiomysql import DictCursor

from application.pay.collection import (
    _collection_dispatch_extra_sql_condition,
    _is_collection_payment_online,
    _manual_lock_update_fields,
)

NOWAIT_LOCK_ERROR_CODES = {1205, 3572}


def _normalize_bank_type(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _requires_collection_qrcode(payment, bank=None, channel_code=None) -> bool:
    bank = bank or {}
    bank_name = str(bank.get('name') or '').upper()
    bank_type = _normalize_bank_type((payment or {}).get('bank_type'))
    bank_type_id = _normalize_bank_type((payment or {}).get('bank_type_id'))

    if bank_name == 'JAZZCASH' or bank_type == 98 or bank_type_id == 98:
        return False
    if bank_name == 'EASYPAISA' or bank_type == 97 or bank_type_id == 97:
        return str(channel_code) == '1010'
    return False


def _parse_payment_id_list(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = str(value).replace(' ', '').strip(',').split(',')
    payment_ids = []
    seen = set()
    for item in raw_items:
        payment_id = str(item).strip()
        if payment_id.isdigit() and payment_id not in seen:
            seen.add(payment_id)
            payment_ids.append(payment_id)
    return payment_ids


def build_ds_candidate_sql(
    amount,
    channel_code,
    target_payment_ids=None,
    dedicated_payment_ids=None,
    limit=20,
) -> Tuple[str, List[object]]:
    target_payment_ids = _parse_payment_id_list(target_payment_ids)
    dedicated_payment_ids = _parse_payment_id_list(dedicated_payment_ids)
    limit = max(1, int(limit or 20))
    collection_dispatch_condition = _collection_dispatch_extra_sql_condition("pay", channel_code)
    if str(channel_code) == '1001':
        account_identifier_condition = """
          AND (
              pay.bank_type = 98
              OR pay.bank_type_id = 98
              OR (
                  CAST(pay.account_type AS CHAR) = '10'
                  AND pay.phone IS NOT NULL
                  AND pay.phone <> ''
              )
              OR (
                  (pay.account_type IS NULL OR CAST(pay.account_type AS CHAR) <> '10')
                  AND pay.account_accno IS NOT NULL
                  AND pay.account_accno <> ''
              )
          )
    """
    else:
        account_identifier_condition = """
          AND (
              pay.bank_type = 98
              OR pay.bank_type_id = 98
              OR (
                  pay.account_iban IS NOT NULL
                  AND pay.account_iban <> ''
              )
          )
    """

    params: List[object] = [
        amount,
        amount,
        amount,
        amount,
        amount,
        amount,
    ]
    target_condition = ""
    if target_payment_ids:
        placeholders = ",".join(["%s"] * len(target_payment_ids))
        target_condition = f"AND pay.id IN ({placeholders})"
        params.extend(target_payment_ids)
    elif dedicated_payment_ids:
        placeholders = ",".join(["%s"] * len(dedicated_payment_ids))
        target_condition = f"AND pay.id NOT IN ({placeholders})"
        params.extend(dedicated_payment_ids)
    params.append(limit)

    sql = f"""
        SELECT
            pay.id,
            pay.partner_id,
            pay.amount_top,
            pay.upi,
            pay.bank_type,
            pay.manual_status,
            pay.weight,
            pay.bank_type_id,
            pay.wallet_status,
            pay.account_accno,
            pay.account_type,
            pay.phone,
            pay.collection_status,
            pay.status AS payment_status,
            pay.certified AS payment_certified,
            pay.account_iban,
            p.pid,
            p.balance,
            p.status,
            p.certified,
            p.vip,
            p.type,
            p.ds_min,
            p.ds_max,
            v.ds_min AS vip_ds_min,
            v.ds_max AS vip_ds_max,
            v.deposit_ratio,
            v.conditions,
            p.balance AS available_amount
        FROM payment pay
        JOIN partner p ON pay.partner_id = p.id
        JOIN vip v ON v.vip = p.vip
        WHERE {collection_dispatch_condition}
          {account_identifier_condition}
          AND pay.bank_type NOT IN (SELECT id FROM bank_type WHERE status = 0)
          AND (pay.bank_type_id IS NULL OR pay.bank_type_id NOT IN (SELECT id FROM bank_type WHERE status = 0))
          AND p.balance >= %s
          AND (p.ds_min <= %s OR p.ds_min = 0)
          AND (p.ds_max >= %s OR p.ds_max = 0)
          AND p.certified = 1
          AND p.status = 1
          AND v.ds_min <= %s
          AND v.ds_max >= %s
          AND (
              pay.amount_top IS NULL
              OR pay.amount_top = 0
              OR pay.amount_top >= (
                  %s + (
                      SELECT COALESCE(SUM(o.amount), 0)
                      FROM orders_ds o
                      WHERE o.payment_id = pay.id
                        AND o.time_create >= CURDATE()
                        AND o.status > 0
                  )
              )
          )
          {target_condition}
        ORDER BY COALESCE(pay.weight, 1) DESC, p.balance DESC, pay.id ASC
        LIMIT %s
    """
    return sql, params


def _is_nowait_lock_error(exc) -> bool:
    current = exc
    seen = set()
    while current and id(current) not in seen:
        seen.add(id(current))
        for arg in getattr(current, 'args', ()) or ():
            if isinstance(arg, int) and arg in NOWAIT_LOCK_ERROR_CODES:
                return True
            if isinstance(arg, str):
                text = arg.lower()
                if '3572' in text or 'nowait' in text or 'lock(s) could not be acquired' in text:
                    return True
                if '1205' in text or 'lock wait timeout' in text:
                    return True
        current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)
    return False


async def _lock_ds_dispatch_candidate(cur, partner_id, payment_id):
    sql_partner = """
        SELECT id, balance, status, certified, vip, type, ds_min, ds_max
        FROM partner
        WHERE id = %s
        FOR UPDATE NOWAIT
    """
    if not await cur.execute(sql_partner, (partner_id,)):
        return None, None
    partner = await cur.fetchone()
    if not partner:
        return None, None

    sql_payment = """
        SELECT id, partner_id, amount_top, manual_status, collection_status, status, certified
        FROM payment
        WHERE id = %s
        FOR UPDATE NOWAIT
    """
    if not await cur.execute(sql_payment, (payment_id,)):
        return None, None
    payment = await cur.fetchone()
    if not payment:
        return None, None
    return partner, payment


async def _fetch_payment_amount_today_in_tx(cur, payment_id):
    sql = """
        SELECT IFNULL(SUM(amount), 0) AS amount_today
        FROM orders_ds
        WHERE payment_id = %s
          AND time_create > CURDATE()
          AND status > 0
    """
    await cur.execute(sql, (payment_id,))
    row = await cur.fetchone()
    if not row:
        return Decimal(0)
    return row.get('amount_today') or Decimal(0)


async def _fetch_partner_uncallback_debit_amount_in_tx(cur, partner_id):
    sql = """
        SELECT IFNULL(SUM(amount), 0) AS amount_d
        FROM bank_record
        WHERE payment_id IN (SELECT id FROM payment WHERE partner_id=%s)
          AND callback=0
          AND trade_type=1
          AND invalid=0
          AND if_ew=0
    """
    await cur.execute(sql, (partner_id,))
    row = await cur.fetchone()
    if not row:
        return Decimal(0)
    return row.get('amount_d') or Decimal(0)


async def _insert_order_ds_in_tx(handler, cur, order_data):
    keys, placeholders, values = await handler.dict_to_kv(order_data)
    sql = "insert into orders_ds ({keys}) values ({vals})".format(
        keys=keys,
        vals=placeholders,
    )
    return await cur.execute(sql, (*values,))


async def fetch_mysql_dedicated_payment_ids(handler):
    target_payment_rows = await handler.query(
        "SELECT target_payment FROM merchant WHERE target_payment IS NOT NULL AND target_payment != '';"
    )
    dedicated_payment_ids = []
    for row in target_payment_rows or []:
        dedicated_payment_ids.extend(_parse_payment_id_list(row.get('target_payment')))
    return _parse_payment_id_list(dedicated_payment_ids)


async def fetch_ds_candidate_rows(handler, amount, channel_code, target_payment_ids=None, limit=20):
    dedicated_payment_ids = []
    if not target_payment_ids:
        dedicated_payment_ids = await fetch_mysql_dedicated_payment_ids(handler)
    sql, params = build_ds_candidate_sql(
        amount=amount,
        channel_code=channel_code,
        target_payment_ids=target_payment_ids,
        dedicated_payment_ids=dedicated_payment_ids,
        limit=limit,
    )
    return await handler.query(sql, *params)


async def push_order(handler, data, target_payment):
    is_push = False
    code = data['code']
    amount = data['amount']
    start_time = datetime.datetime.now().timestamp()
    upi = ''
    qrcode = ''

    gonghu_ds_payment_ids = []
    target_payment = target_payment if target_payment else ''
    target_payment = target_payment.replace(' ', '')
    if target_payment.endswith(','):
        target_payment = target_payment[:-1]
    if target_payment.startswith(','):
        target_payment = target_payment[1:]
    if not target_payment:
        target_payment_list = []
    elif not re.match(r'^\d+(,\d+)*$', target_payment):
        handler.logger.warn('code: {code}, 指定码格式错误： "{target_payment}"'.format(code=code, target_payment=target_payment))
        target_payment_list = []
    else:
        target_payment_list = target_payment.split(',') if target_payment else []
    if target_payment and target_payment_list:
        handler.logger.warn('code: {code}, 指定码{target_payment}'.format(code=code, target_payment=target_payment))

    _list = await fetch_ds_candidate_rows(
        handler,
        amount,
        data.get("channel_code"),
        target_payment_ids=target_payment_list,
        limit=20,
    )
    handler.logger.warn('code: {code}, 手写候选SQL时间：{t}, 候选数量：{count}'.format(
        code=code,
        t=datetime.datetime.now().timestamp() - start_time,
        count=len(_list or []),
    ))
    if not _list:
        return {"success": False, "upi": "", "qrcode": ""}
    _new_vip_list = {}
    for row in _list:
        _new_vip_list[row['vip']] = {
            'vip': row['vip'],
            'ds_min': row['vip_ds_min'],
            'ds_max': row['vip_ds_max'],
            'deposit_ratio': row['deposit_ratio'],
            'conditions': row['conditions'],
        }
    new_payment_list = dict()
    new_partner_list = dict()
    payment_target_payment_list = list()
    # 用以按权重来随机抽取
    weights = []
    target_weights = []
    payment_id_weights=[]
    payment_key = [
        'id', 'partner_id', 'amount_top', 'upi', 'bank_type', 'manual_status',
        'bank_type_id', 'wallet_status', 'account_accno', 'collection_status',
        'payment_status', 'payment_certified', 'account_iban', 'account_type', 'phone'
    ]
    partner_key = ['pid', 'balance', 'status', 'vip', 'type', 'ds_min', 'ds_max']
    for i in _list:
        i['weight'] = i['weight'] if i['weight'] else 1  # 默认为1
        # 获取到指定码时，放入单独的列表中
        if str(i['id']) in target_payment_list:
            target_weights.append(i['weight'])
            payment_target_payment_list.append(i['id'])
        else:
            weights.append(i['weight'])
            payment_id_weights.append(i['id'])
        new_payment = dict()
        for key in payment_key:
            new_payment[key] = i[key]
        new_payment_list[i['id']] = new_payment
        new_partner = dict()
        for key in partner_key:
            new_partner[key] = i[key]
        new_partner['id'] = i['partner_id']
        new_partner_list[i['partner_id']] = new_partner

    if not new_payment_list or not new_partner_list:
        return is_push
    # print(2220, new_payment_list, new_partner_list)
    handler.logger.warn('code: {code}, 查询前置时间：{t}'.format(code=code, t=datetime.datetime.now().timestamp() - start_time))

    while True:
        if datetime.datetime.now().timestamp() - start_time > 30:
            handler.logger.warn('code: {code}, 超过30s派单，直接丢弃'.format(code=code))
            break

        payment_id = None
        if payment_id is None:
            # 超过10s 未获取到payment_id 的直接派给公户
            if datetime.datetime.now().timestamp() - start_time > 10 and gonghu_ds_payment_ids:
                payment_id = random.choice(gonghu_ds_payment_ids)
                handler.logger.warn('code: {code}, 超过10s派单，直接派给公户{id}'.format(code=code, id=payment_id))
            if payment_id is None:
                # 不用pop，使用权重随机提取
                # payment_id = await handler.redis.lpop(list_name)
                if not payment_id_weights and not payment_target_payment_list:
                    handler.logger.warn('code: {code}, 无码派单'.format(code=code))
                    break
                # 如果存在payment_target_payment_list的值，优先取payment_target_payment_list中的值；
                # 不存在则取payment_id_weights中的值
                if payment_target_payment_list:
                    payment_id = random.choices(payment_target_payment_list, target_weights, k=1)[0]
                    handler.logger.warn('code: {code}, 有指定码，选用指定码接单: {id}'.format(code=code, id=payment_id))
                    # 随机取出的码移除出指定码商列表，避免下次重新获取到
                    del target_weights[payment_target_payment_list.index(payment_id)]
                    payment_target_payment_list.remove(payment_id)
                else:
                    payment_id = random.choices(payment_id_weights, weights, k=1)[0]
                    handler.logger.warn('code: {code}, 按照权重随机选取码接单: {id}'.format(code=code, id=payment_id))
                    # 随机取出的码移除出列表，避免下次重新获取到
                    del weights[payment_id_weights.index(payment_id)]
                    payment_id_weights.remove(payment_id)
        if payment_id is None:
            break
        order_amount = data['amount']

        # 获取收款信息
        if int(payment_id) not in new_payment_list.keys():
            handler.logger.warn('code: {code}, payment_id不在new_payment_list时间：{t}'.format(code=code, t=datetime.datetime.now().timestamp() - start_time))
            continue
        payment = new_payment_list[int(payment_id)]

        # 码异常
        if not payment:
            handler.logger.warn('码{payment_id}状态异常，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
            continue

        partner_id = payment['partner_id']
        bank_id = payment['bank_type_id']
        bank = await handler.get_result_by_condition(
            'bank_type',
            ['name'],
            {'id': bank_id}
        ) or {}
        handler.logger.info(f"Step 10: bank_id {bank_id}, {bank}")

        payment_qrcode = ''
        if _requires_collection_qrcode(payment, bank, data.get('channel_code')):
            payment_qrcode = await handler.generate_qr_code(
                payment['id'],
                payment.get('account_iban') or payment.get('account_accno') or payment.get('upi'),
                data['amount'],
            )
            if not payment_qrcode:
                handler.logger.warn(f"码 {payment_id} 生成二维码失败，已跳过, code: {code}")
                continue
            handler.logger.info(f"码 {payment_id} 已生成二维码，继续派单, code: {code}")
        else:
            handler.logger.info(f"码 {payment_id} 不需要二维码，继续派单, code: {code}")

        handler.logger.info(f"从 payment 中获取 bank_type_id，赋值 bank_id = {bank_id}")

        if await handler.redis.get('partner_grab_order_limit_{id}'.format(id=partner_id)):
            handler.logger.warn('码商{partner_id}, 码{payment_id}，暂停6分钟接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
            continue

        # 已停止接单
        if not await _is_collection_payment_online(
            handler,
            payment_id,
            bank_id,
            bank_type=payment.get('bank_type'),
            payment=payment,
        ):
            handler.logger.warn('码{payment_id}已停止接单，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
            continue
        # 先获取码商确定是否外部码商，外部码商检测60分钟内，内部码商检测15分钟内订单连续失败
        if int(partner_id) not in new_partner_list.keys():
            handler.logger.warn('code: {code}, partner_id不在new_partner_list时间：{t}'.format(code=code, t=datetime.datetime.now().timestamp() - start_time))
            continue
        partner = new_partner_list[int(partner_id)]
        # 动态限制：每个银行 bank_id 在 accept_interval 秒内最多接 max_count 单
        accept_interval_key = f"send_orders_max_sec_{bank_id}"
        max_count_key = f"send_orders_max_count_{bank_id}"

        accept_interval = await handler.redis.get(accept_interval_key)
        max_count = await handler.redis.get(max_count_key)

        handler.logger.info(f"[动态限制] 获取 Redis Key：{accept_interval_key} = {accept_interval}")
        handler.logger.info(f"[动态限制] 获取 Redis Key：{max_count_key} = {max_count}")

        # 校验是否设置动态限制
        if accept_interval and max_count:
            accept_interval = int(accept_interval)
            max_count = int(max_count)

            # 查询 orders_ds 表，统计时间窗口内该payment_id已接单数量
            # 361需求：只判断待支付
            sql = """
                SELECT COUNT(*) AS count
                FROM orders_ds
                WHERE payment_id = %s AND time_create >= NOW() - INTERVAL %s SECOND AND status = 1
            """
            result = await handler.query(sql, payment_id, accept_interval)
            order_count = result[0]['count'] if result and 'count' in result[0] else 0

            handler.logger.info(
                f"[动态限制] payment_id: {payment_id}, bank_id: {bank_id}, 时间窗口: {accept_interval}s, 当前接单数: {order_count}, 最大允许: {max_count}"
            )

            if order_count >= max_count:
                handler.logger.warning(
                    f"[动态限制] payment_id: {payment_id}, 银行 {bank_id} 在过去 {accept_interval}s 内已接 {order_count} 单，超过最大限制 {max_count}，不允许再次接单，code: {code}"
                )
                continue
        else:
            default_interval = 360
            send_orders_interval_global = await handler.redis.get("send_orders_interval")

            if data['channel_code'] in (1002, 1003):
                # 【固定 3 分钟逻辑】: 1002 和 1003 固定为 180 秒
                interval_seconds = 180
                handler.logger.info(f"[固定限制] 通道 {data['channel_code']}，固定接单间隔为 180 秒 (3 分钟)")
            else:
                # 其他通道使用全局配置，若无配置则使用默认值 360 秒
                try:
                    interval_seconds = int(send_orders_interval_global)
                except (TypeError, ValueError):
                    interval_seconds = default_interval
                handler.logger.info(f"[固定限制] 通道 {data['channel_code']}，全局接单间隔为 {interval_seconds} 秒")

            # 2. 检查固定限制 (使用 Redis EXISTS 替代时间戳比较)
            key_interval = f"send_orders_interval_{payment_id}"

            # 检查 Key 是否存在。如果存在，表示码商仍在冷却期内。
            if await handler.redis.exists(key_interval):
                handler.logger.warning(
                    f"[固定限制] 码 {payment_id} 正在冷却期 ({interval_seconds} 秒限制)，不允许再次接单，code: {code}"
                )
                continue

            handler.logger.info(f"[固定限制] Redis 中未找到 {key_interval}，可以接单")
        # 剔除死码等
        send_orders_ds_limit = await handler.redis.get("send_orders_ds_limit_{payment_id}".format(payment_id=payment_id))
        if send_orders_ds_limit and not partner['type'] == 0:
            handler.logger.warn('码商{partner_id}的码{payment_id}成功率低,暂停接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
            continue
        # 码商异常
        if not partner or not partner['vip']:
            handler.logger.warn('码商{partner_id}状态异常，不允许接单,code: {code}'.format(partner_id=partner_id, code=code))
            continue
        if payment['manual_status'] == 1:
            handler.logger.warn('码商{partner_id}的码{payment_id}失败次数过多，人工锁定不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
            continue
        if partner['ds_min'] > order_amount:
            handler.logger.warn('码商{partner_id},代收最小限额{ds_min}，订单金额{order_amount},code: {code}'.format(partner_id=partner_id,ds_min=partner['ds_min'],order_amount=order_amount, code=code))
            continue
        if partner['ds_max'] > 0 and partner['ds_max'] < order_amount:
            handler.logger.warn('码商{partner_id},代收最大限额{ds_max}，订单金额{order_amount},code: {code}'.format(partner_id=partner_id,ds_max=partner['ds_max'],order_amount=order_amount, code=code))
            continue

        # 代收成功率
        orders_ds_limit_success_rate = "orders_ds_limit_success_rate"
        redis_orders_ds_limit_success_rate_count = await handler.redis.get(orders_ds_limit_success_rate)
        redis_orders_ds_limit = "orders_ds_limit_{payment_id}".format(payment_id=payment_id)
        orders_ds_list_count = await handler.redis.get(redis_orders_ds_limit)
        if redis_orders_ds_limit_success_rate_count and not partner['type'] == 0:  # 外部码商
            redis_orders_ds_limit_count = "orders_ds_limit_count_{payment_id}".format(payment_id=payment_id)
            if orders_ds_list_count and redis_orders_ds_limit_success_rate_count and int(orders_ds_list_count) < int(redis_orders_ds_limit_success_rate_count):
                handler.logger.warn('码商{partner_id}的码{payment_id}成功率低于{redis_orders_ds_limit_success_rate_count}%,停止接单一个小时,code: {code}'.format(partner_id=partner_id,payment_id=payment_id, redis_orders_ds_limit_success_rate_count=redis_orders_ds_limit_success_rate_count, code=code))
                continue
            # 设置查询总条数
            limit = 10
            # 查询最近的10单
            sql = """select status from orders_ds where payment_id=%s and status in(4,3,-1) and date_add(time_create, interval 120 minute) > now() order by id desc limit %s"""
            orders_ds_list = await handler.query(sql, payment_id,limit)
            orders_ds_list_count = 0
            for i in orders_ds_list:
                if i['status'] == -1:
                    orders_ds_list_count += 1
            orders_ds_limit_success_rate_count = int(float(format(1 - float(orders_ds_list_count) / float(limit), ".2f")) * 100)
            if redis_orders_ds_limit_success_rate_count and orders_ds_limit_success_rate_count < int(redis_orders_ds_limit_success_rate_count):
                orders_ds_limit_count = await handler.redis.get(redis_orders_ds_limit_count)
                if orders_ds_limit_count and int(orders_ds_limit_count) > 2:
                    await handler.redis.delete(redis_orders_ds_limit_count)
                    await handler.update_result('payment', _manual_lock_update_fields(payment), {'id': payment_id})
                    handler.logger.warn('码商{partner_id},码{payment_id}成功率低于{redis_orders_ds_limit_success_rate_count}%次数过多，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id,redis_orders_ds_limit_success_rate_count=redis_orders_ds_limit_success_rate_count, code=code))
                    continue
                await handler.redis.incr(redis_orders_ds_limit_count)
                orders_ds_limit_count = await handler.redis.get(redis_orders_ds_limit_count)
                handler.logger.warn('码商{partner_id}的码{payment_id}成功率低于{redis_orders_ds_limit_success_rate_count}%,停止接单一个小时, 第{count}次,code: {code}'.format(partner_id=partner_id,payment_id=payment_id, redis_orders_ds_limit_success_rate_count=redis_orders_ds_limit_success_rate_count, count=orders_ds_limit_count, code=code))
                await handler.redis.set(redis_orders_ds_limit, orders_ds_limit_success_rate_count, 60 * 60)
                continue

        # 最高同时接单不能超过五单
        maximum_simultaneous_orders = "maximum_simultaneous_orders"
        maximum_simultaneous_orders_count = await handler.redis.get(maximum_simultaneous_orders)
        if maximum_simultaneous_orders_count and not partner['type'] == 0:  # 外部码商
            sql = """select count(*) as count from orders_ds where payment_id=%s and status in(1,2) and date_add(time_create, interval 10 minute) > now()"""
            orders_ds_count = await handler.query(sql, payment_id)
            if maximum_simultaneous_orders_count and orders_ds_count[0]['count'] > int(maximum_simultaneous_orders_count):
                handler.logger.warn('码商{partner_id}的码{payment_id}最高同时接单不能超过{maximum_simultaneous_orders_count}单,code: {code}'.format(partner_id=partner_id,payment_id=payment_id,maximum_simultaneous_orders_count=maximum_simultaneous_orders_count, code=code))
                continue
        # 接近上限
        sql = """select ifnull(sum(amount), 0) as amount_today from orders_ds where payment_id=%s and time_create > curdate() and status > 0"""
        if payment['amount_top'] and payment['amount_top'] < order_amount + (await handler.query(sql, payment_id))[0]['amount_today']:
            handler.logger.warn('码{payment_id}接近上限，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
            continue

        # 检测订单金额是否在可接范围内,并且余额是否足够
        partner_amount = _new_vip_list[partner['vip']]

        # 获取去除保证金后的余额
        partnerBalance = await handler.removeDeposit(partner['balance'], partner_amount['conditions'], partner_amount['deposit_ratio'])
        if order_amount < partner_amount['ds_min'] or order_amount > partner_amount['ds_max']:
            handler.logger.warn('码商{partner_id}不满足vip等级代收最大最小范围，订单金额{order_amount}代收最小限额{ds_min}代收最大限额{ds_max}，不允许接单,code: {code}'.format(partner_id=partner_id, order_amount=order_amount, ds_min=partner_amount['ds_min'], ds_max=partner_amount['ds_max'], code=code))
            continue
        if Decimal(order_amount) > partnerBalance:
            handler.logger.warn('码商{partner_id}去除保证金后的余额不足，接单额度{partnerBalance}，不允许接单, code: {code}'.format(partner_id=partner_id, partnerBalance=partnerBalance, code=code))
            if partnerBalance < 400: # 接单额度小于400的，且一个小时内都没有订单的，暂停接单6分钟
                sql = """select id from orders_ds where partner_id=%s and date_add(time_create, interval 1 hour) > now() limit 1"""
                if not await handler.query(sql, partner_id):
                    await handler.redis.set('partner_grab_order_limit_{id}'.format(id=partner_id), 1, 6 * 60)
                    handler.logger.warn('码商{partner_id}去除保证金后的余额不足，接单额度{partnerBalance}，且1小时未接单，暂停6分钟, code: {code}'.format(partner_id=partner_id, partnerBalance=partnerBalance, code=code))
            continue
        # 计算码商总费率
        channel = await handler.get_result_by_condition('channel', ['rate', 'rates'],
                                                     {'code': data['channel_code']})
        rates = channel['rate']
        earn_partner_self = order_amount * rates
        if partner['pid']:
            rates += Decimal(channel['rates'].split(',')[0])
            if (await handler.get_result_by_condition('partner', ['pid'], {'id': partner['pid']}))['pid']:
                rates += Decimal(channel['rates'].split(',')[1])
        earn_partner = order_amount * rates
        # 计算平台盈利
        earn_system = data['poundage'] - earn_partner - data['earn_merchant']
        if earn_system < 0:
            handler.logger.warn(
                '{code}费率设置错误{partner_id}，不允许接单'.format(code=data['code'], partner_id=partner_id))
            continue

        if not partner['type'] == 0:  # 外部码商
            # 查询码商余额是否足够, 要减去爬取后的账单中该扣未扣的金额
            sql = 'select ifnull(sum(amount), 0) as amount_d from bank_record where payment_id in (select id from payment where partner_id=%s)  and callback=0 and trade_type=1 and invalid=0 and if_ew=0'
            if partnerBalance < Decimal(order_amount + (await handler.query(sql, partner_id))[0]['amount_d']):
                handler.logger.warn('码商{partner_id}接单额度不足,码{payment_id}，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                continue
        # 相关数据
        order_data = dict()
        order_data['partner_id'] = partner_id
        order_data['payment_id'] = payment_id
        order_data['upi'] = payment['upi']
        order_data['earn_partner'] = earn_partner
        order_data['earn_partner_self'] = earn_partner_self
        order_data['status'] = 1
        order_data['earn_system'] = earn_system
        order_data['time_accept'] = datetime.datetime.now()

        # 扣除码商余额并更新状态
        async with handler.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    locked_partner, locked_payment = await _lock_ds_dispatch_candidate(cur, partner['id'], payment_id)
                    if not locked_partner or not locked_payment:
                        await conn.rollback()
                        handler.logger.warning('码商{partner_id},码{payment_id}锁后数据不存在，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                        continue
                    if int(locked_payment['partner_id']) != int(partner['id']):
                        await conn.rollback()
                        handler.logger.warning('码{payment_id}锁后归属码商变化，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                        continue
                    if locked_partner['status'] != 1 or locked_partner['certified'] != 1:
                        await conn.rollback()
                        handler.logger.warning('码商{partner_id}锁后状态异常，不允许接单,code: {code}'.format(partner_id=partner_id, code=code))
                        continue
                    if locked_payment['collection_status'] != 1:
                        await conn.rollback()
                        handler.logger.warning('码{payment_id}锁后代收状态关闭，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                        continue
                    if locked_payment['manual_status'] == 1:
                        await conn.rollback()
                        handler.logger.warning('码{payment_id}锁后人工锁定，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                        continue

                    locked_partner_balance = await handler.removeDeposit(
                        locked_partner['balance'],
                        partner_amount['conditions'],
                        partner_amount['deposit_ratio'],
                    )
                    if Decimal(order_amount) > locked_partner_balance:
                        await conn.rollback()
                        handler.logger.warning('码商{partner_id}锁后去除保证金余额不足，接单额度{balance}，不允许接单,code: {code}'.format(partner_id=partner_id, balance=locked_partner_balance, code=code))
                        continue

                    if locked_payment['amount_top']:
                        amount_today = await _fetch_payment_amount_today_in_tx(cur, payment_id)
                        if Decimal(locked_payment['amount_top']) < Decimal(order_amount) + Decimal(amount_today):
                            await conn.rollback()
                            handler.logger.warning('码{payment_id}锁后接近上限，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                            continue

                    if not locked_partner['type'] == 0:
                        amount_d = await _fetch_partner_uncallback_debit_amount_in_tx(cur, partner_id)
                        if locked_partner_balance < Decimal(order_amount) + Decimal(amount_d):
                            await conn.rollback()
                            handler.logger.warning('码商{partner_id}锁后接单额度不足,码{payment_id}，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                            continue

                    # 扣除余额
                    if not await handler.change_balance(conn, cur, 'partner', partner['id'], -data['amount'],
                                                     data['code'], 0):
                        await conn.rollback()
                        handler.logger.warning('{partner_id}接单扣除账户余额失败,code: {code}'.format(partner_id=partner_id, code=code))
                        continue

                    insert_order_data = dict(data)
                    insert_order_data.update(order_data)
                    if not await _insert_order_ds_in_tx(handler, cur, insert_order_data):
                        await conn.rollback()
                        handler.logger.warning('{partner_id}接单创建订单失败,code: {code}'.format(partner_id=partner_id, code=code))
                        continue
                except Exception as e:
                    await conn.rollback()
                    if _is_nowait_lock_error(e):
                        handler.logger.warning('码商{partner_id},码{payment_id} NOWAIT锁冲突，换下一个候选,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                        continue
                    handler.logger.exception(code + str(e))
                    continue
                else:
                    await conn.commit()
                    is_push = True
                    # 添加upi返回
                    handler.upi = order_data['upi']
                    upi = order_data['upi']
                    qrcode = payment_qrcode

                    ts_now = int(time.time())

                    send_orders_interval_global = await handler.redis.get("send_orders_interval")
                    handler.logger.info(f"获取 send_orders_interval 的值: {send_orders_interval_global}")

                    # 1. 确定最终的冷却时间 (interval_seconds)
                    # 默认值 360 秒 (6 分钟)
                    default_interval = 360

                    if send_orders_interval_global:
                        try:
                            # 默认使用全局配置
                            interval_seconds = int(send_orders_interval_global)
                        except (TypeError, ValueError):
                            interval_seconds = default_interval
                    else:
                        interval_seconds = default_interval

                    # 检查是否为 1002 或 1003 通道
                    if data.get('channel_code') in (1002, 1003):
                        # 【固定 3 分钟逻辑】: 1002 和 1003 固定为 180 秒
                        interval_seconds = 180
                        handler.logger.info(f"通道 {data.get('channel_code')} 命中固定 3 分钟限制，设置过期时间为 180 秒")

                    if send_orders_interval_global and not partner['type'] == 0:
                        handler.logger.info(f"partner['type'] 值为: {partner['type']}, 符合条件，准备设置 send_orders_interval_{payment_id}")

                        handler.logger.info(f"准备设置 Redis 键 send_orders_interval_{payment_id}，当前时间戳: {ts_now}")

                        await handler.redis.set(
                            f"send_orders_interval_{payment_id}",
                            ts_now,
                            ex=interval_seconds
                        )

                        handler.logger.info(f"已设置 send_orders_interval_{payment_id}，值: {ts_now}，过期时间: {interval_seconds} 秒")

                    if bank.get('name') == 'EASYPAISA':
                        await handler.redis.set('order_ds_third_qr_{}'.format(code), qrcode, 60 * 20)
                        if qrcode:
                            handler.logger.info(f"订单代码 {code}  , 金额 {amount} 生成的二维码文本是: {qrcode}")
                        else:
                            handler.logger.info(f"订单代码 {code}  , 金额 {amount} 未生成二维码。")
                    elif bank.get('name') == 'JAZZCASH':
                        pass

                    break
    return {"success": is_push, "upi": upi, "qrcode": qrcode}
