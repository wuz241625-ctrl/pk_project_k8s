import datetime
import json
import random
import re
import secrets
import string
import time

import traceback
import random

import base64
import hashlib
import aiohttp
import uuid
import simplejson

from typing import Dict, List, Tuple, Optional, Union
from datetime import timezone, timedelta
import qrcode
from io import BytesIO

from decimal import Decimal, InvalidOperation, ROUND_DOWN
from urllib.parse import urlparse, parse_qs

import requests
from aiomysql import DictCursor

from application.base import BaseHandler
from application.message import msg, msg_en
from application.sign import SignatureAndVerification
from application.pay.payout_channel_guard import is_jazzcash_payout_request
from application.pay.thirdPart import Razorpay_upi_origin
from application.pay.thirdPart import lucky_payment, apay_payment, kingpay_payment, wepay_payment, pay777pay_payment, swiftpay_payment, quickpay_payment, snakepay_payment, hkpay_payment, skpay_payment, ospay_payment, tatapay_payment,vibrapay_payment,qqpay_payment,gamepayer_payment,payfast_payment
from application.payment_eligibility import (
    can_dispatch_ds,
    collection_sql_condition,
)


def _to_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _collection_dispatch_extra_sql_condition(alias="pay", channel_code=None) -> str:
    return collection_sql_condition(alias, channel_code)


def _is_collection_dispatch_enabled(payment) -> bool:
    return can_dispatch_ds(payment)


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

    params: List[object] = [
        amount,
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
            COALESCE(pend.pending_amount, 0) AS pending_amount,
            (p.balance - COALESCE(pend.pending_amount, 0)) AS available_amount
        FROM payment pay
        JOIN partner p ON pay.partner_id = p.id
        JOIN vip v ON v.vip = p.vip
        LEFT JOIN (
            SELECT partner_id, COALESCE(SUM(amount), 0) AS pending_amount
            FROM orders_ds
            WHERE time_create >= CURDATE()
              AND status IN (0, 1, 2)
            GROUP BY partner_id
        ) pend ON pend.partner_id = p.id
        WHERE {collection_dispatch_condition}
          AND pay.account_iban IS NOT NULL
          AND pay.account_iban <> ''
          AND pay.bank_type NOT IN (SELECT id FROM bank_type WHERE status = 0)
          AND (pay.bank_type_id IS NULL OR pay.bank_type_id NOT IN (SELECT id FROM bank_type WHERE status = 0))
          AND p.balance >= %s
          AND (p.ds_min <= %s OR p.ds_min = 0)
          AND (p.ds_max >= %s OR p.ds_max = 0)
          AND p.certified = 1
          AND p.status = 1
          AND v.ds_min <= %s
          AND v.ds_max >= %s
          AND (p.balance - COALESCE(pend.pending_amount, 0)) >= %s
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
        ORDER BY COALESCE(pend.pending_amount, 0) ASC, COALESCE(pay.weight, 1) DESC, pay.id ASC
        LIMIT %s
    """
    return sql, params


def _manual_lock_update_fields(payment):
    return {"manual_status": 1, "collection_status": 0}


async def _is_collection_payment_online(self, payment_id, bank_type_id, bank_type=None, payment=None):
    if payment is None:
        payment = await self.get_result_by_condition(
            'payment',
            ['wallet_status', 'account_accno', 'collection_status', 'status', 'certified', 'manual_status'],
            {'id': payment_id},
        )
    return _is_collection_dispatch_enabled(payment)


async def _mysql_collection_ids(self, channel_code=None):
    sql = """
        select id
        from payment pay
        where {condition}
    """.format(condition=_collection_dispatch_extra_sql_condition("pay", channel_code))
    rows = await self.query(sql)
    return {str(row["id"]) for row in rows or []}


async def _collection_online_payment_ids(self, channel_code=None):
    payment_ids = await _mysql_collection_ids(self, channel_code)
    return sorted((payment_id for payment_id in payment_ids if payment_id.isdigit()), key=int)


async def _is_collection_payment_online_by_id(self, payment_id):
    payment = await self.get_result_by_condition(
        'payment',
        ['wallet_status', 'account_accno', 'collection_status', 'status', 'certified', 'manual_status'],
        {'id': payment_id},
    )
    if not payment:
        return False
    return await _is_collection_payment_online(
        self,
        payment_id,
        (payment or {}).get('bank_type_id'),
        bank_type=(payment or {}).get('bank_type'),
        payment=payment,
    )


def crc16_ccitt(data: bytes, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """计算CRC-16/CCITT-FALSE校验和 - 匹配Java实现"""
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc
def _fmt_len(n: int) -> str:
    if n < 0 or n > 99:
        raise ValueError(f"Length out of range for 2 digits: {n}")
    return f"{n:02d}"
def encode_tlv(tag: str, value: str) -> str:
    if len(tag) != 2 or not tag.isdigit():
        raise ValueError(f"Invalid tag: {tag}")
    ln = _fmt_len(len(value))
    return f"{tag}{ln}{value}"


def _format_timestamp(ts: Union[int, float, str, datetime.datetime]) -> str:
    """Format timestamp to ddMMyyyyHHmm.

    Accepts:
    - int/float: UNIX seconds
    - datetime: naive => treated as local time; aware => used as-is
    - str: if 12 digits, assumed ddMMyyyyHHmm; if 10/13 digits, treated as UNIX seconds
    """
    pkt = timezone(timedelta(hours=5))
    if isinstance(ts, (int, float)):
        dt = datetime.datetime.fromtimestamp(ts, tz=pkt)
    elif isinstance(ts, datetime.datetime):
        dt = ts.astimezone(pkt) if ts.tzinfo is not None else ts.replace(tzinfo=pkt)
    elif isinstance(ts, str):
        s = ts.strip()
        if len(s) == 12 and s.isdigit():
            return s
        # Try epoch seconds/millis
        if s.isdigit() and len(s) in (10, 13):
            sec = int(s[:10])
            dt = datetime.datetime.fromtimestamp(sec, tz=pkt)
        else:
            # Try flexible parse: ddMMyyyyHHmm
            try:
                return datetime.datetime.strptime(s, "%d%m%Y%H%M").strftime("%d%m%Y%H%M")
            except Exception as e:
                raise ValueError(f"Unrecognized timestamp string: {ts}") from e
    else:
        raise TypeError("Unsupported timestamp type")
    return dt.strftime("%d%m%Y%H%M")


def _format_amount_raast(value: Union[int, float, str]) -> str:
    """Normalize amount to match the Android implementation:

    - Coerce to integer (drop fractional part, like parseInt in Android).
    - Left-pad a single-digit amount with a leading zero (e.g., 5 -> "05").
    - Return as string to be used as the TLV value for tag 05.
    """
    # Convert to integer similar to Java's Integer.parseInt on the displayed amount
    if isinstance(value, int):
        n = value
    else:
        s = str(value).strip()
        # Remove common formatting, if present
        s = s.replace(",", "")
        # Try Decimal to support inputs like "10.00"
        try:
            n = int(Decimal(s))
        except (InvalidOperation, ValueError):
            # Fallback: keep only leading integer part
            try:
                n = int(float(s))
            except Exception as e:
                raise ValueError(f"Invalid amount: {value}") from e
    amt_str = str(n)
    if n < 10:
        amt_str = "0" + amt_str
    return amt_str
def build_payload(
    iban: str,
    *,
    crc_tag: str = "10",
    base_fields: Optional[Dict[str, str]] = None,
) -> str:
    """Build a static QR payload (no amount/timestamp).

    Structure: 00-01-02-04-10(CRC). Matches sample:
      0002020102110202000424<IBAN>1004<CRC>

    Defaults:
    - 00 = '02'
    - 01 = '11' (static)
    - 02 = '00'
    - 04 = IBAN (variable length)
    - 10 = CRC (computed, length 04)
    """
    fields: Dict[str, str] = {
        "00": "02",
        "01": "11",
        "02": "00",
        "04": str(iban),
    }
    if base_fields:
        fields.update({k: str(v) for k, v in base_fields.items()})

    order = ["00", "01", "02", "04"]
    payload_wo_crc = "".join(encode_tlv(t, fields[t]) for t in order if t in fields)
    base_for_crc = payload_wo_crc + f"{crc_tag}04"
    crc_val = f"{crc16_ccitt(base_for_crc.encode('utf-8')):04X}"
    return base_for_crc + crc_val

def build_payload_amount(
    iban: str,
    amount: Union[int, float, str],
    timestamp: Union[int, float, str, datetime.datetime],
    *,
    crc_tag: str = "10",
    base_fields: Optional[Dict[str, str]] = None,
    timestamp_raw: bool = False,
) -> str:
    """Build a new payload by filling IBAN(tag 04), amount(tag 05), timestamp(tag 07).

    - Preserves default static fields: tag 00='02', 01='12', 02='00' unless overridden via base_fields.
    - Recomputes CRC at the end using crc_tag (default '10').
    - Amount is converted to string as-is; for decimals like 123.45 pass a preformatted string if needed.
    """
    # Base defaults from the provided sample
    fields: Dict[str, str] = {
        "00": "02",
        "01": "12",
        "02": "00",
    }
    if base_fields:
        fields.update({k: str(v) for k, v in base_fields.items()})

    fields["04"] = str(iban)
    # Match Android behavior for amount formatting
    fields["05"] = _format_amount_raast(amount)
    fields["07"] = str(timestamp) if timestamp_raw else _format_timestamp(timestamp)

    # Preserve order similar to sample
    order = ["00", "01", "02", "04", "05", "07"]
    payload_wo_crc = "".join(encode_tlv(t, fields[t]) for t in order if t in fields)
    # Append CRC tag+len (without value) to compute CRC over
    base_for_crc = payload_wo_crc + f"{crc_tag}04"
    # Android uses UTF-8 getBytes; calculate CRC-16/CCITT-FALSE to match Java implementation
    crc_val = f"{crc16_ccitt(base_for_crc.encode('utf-8')):04X}"
    return base_for_crc + crc_val

# 下单
class Pay(BaseHandler):
    async def post(self):
        try:
            r = await self.get_cache_result('sys_info', ['status_payment_service'], {'id': 1})
            if not r['status_payment_service']:
                data = {k: self.get_argument(k) for k in self.request.arguments}
                self.logger.info('pay 支付服务关闭，不再接受新订单: {data}'.format(data=str(data)))
                return await self.json_response(data=msg[10031])  # 支付服务关闭，不再接受新订单

            # 代收代付锁定
            is_locked = await self.check_dsdf_lock()
            if is_locked:
                return await self.json_response(data=msg[10026])  # 锁定状态，返回相应的消息

            try:
                data = {k: self.get_argument(k) for k in self.request.arguments}
                self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
            except Exception:
                self.logger.exception('参数异常')
                return await self.json_response(msg[10001])
            ip = await self.get_ip()
            ref = self.request.headers['Referer'] if 'Referer' in self.request.headers else ''
            self.logger.info('pay 收到参数{data},referrer={ref},ip={ip}'.format(data=str(data), ref=ref, ip=ip))


            if 'remark' not in data.keys():
                self.logger.info("未找到 key 'remark'，设为 None")
                data['remark'] = None
                self.data_receive_filter_xss['remark'] = None
            if 'notice_api' not in data.keys():
                self.logger.info("未找到 key 'notice_api'，设为 None")
                data['notice_api'] = None
                self.data_receive_filter_xss['notice_api'] = None
            if 'realname' not in data.keys():  # 增加用户的真实姓名字段
                self.logger.info("未找到 key 'realname'，设为 None")
                data['realname'] = None
                self.data_receive_filter_xss['realname'] = None
            if 'player_ip' not in data:  # 增加客户的真实ip
                self.logger.info("未找到 key 'player_ip'，设为 None")
                data['player_ip'] = None
                self.data_receive_filter_xss['player_ip'] = None
            if 'user_id' not in data:
                self.logger.info("未找到 key 'user_id'，设为 None")
                data['user_id'] = None
                self.data_receive_filter_xss['user_id'] = None

            valid_keys = ['mer_id', 'gateway', 'amount', 'callback', 'notify', 'order_id', 'sign', 'remark',
                          'notice_api', 'realname', 'player_ip', 'user_id']
            not_null_keys = ['mer_id', 'gateway', 'amount', 'callback', 'notify', 'order_id', 'sign']

            self.logger.info(f"检查参数是否包含所有必需字段: {valid_keys}")
            if not await self.is_valid_key(data, valid_keys):
                self.logger.warning("参数包含非法字段")
                return await self.json_response(data=msg[10002])

            self.logger.info(f"检查必填字段是否为空: {not_null_keys}")
            if await self.is_null(data, not_null_keys):
                self.logger.warning("存在空值的必填字段")
                return await self.json_response(data=msg[10003])

            self.logger.info("检查接收的数据和过滤后数据是否一致")
            if not await self.check_different_new(data, self.data_receive_filter_xss, valid_keys):
                self.logger.info('pay 参数非法{data}'.format(data=str(data)))
                return await self.json_response(data=msg[10002])

            try:
                merchant_id = int(data['mer_id'])  # 码商ID
            except (ValueError, TypeError):
                self.logger.warning(f"invalid merchant id format: {data['mer_id']}")
                return await self.json_response(data=msg[10002])
            self.logger.info(f"解析得到码商 ID: {merchant_id}")

            try:
                gateway = int(data['gateway'])  # 通道编码
            except (ValueError, TypeError):
                self.logger.warning(f"invalid gateway format {data['gateway']}")
                return await self.json_response(data=msg[10002])
            self.logger.info(f"解析得到通道编码: {gateway}")

            try:
                amount = Decimal(data['amount']).quantize(Decimal('.01'), rounding=ROUND_DOWN)  # 订单金额
            except (InvalidOperation, ValueError, TypeError):
                self.logger.warning(f"invalid amount format: {data['amount']}")
                return await self.json_response(data=msg[10002])
            self.logger.info(f"解析得到订单金额: {amount}")

            merchant_code = data['order_id']
            self.logger.info(f"解析得到订单号: {merchant_code}")

            # 获取并检查商户
            keys = {'status', 'mc_key', 'pid', 'target_payment', 'return_url', 'status', 'ds_on', 'ds_black_ips', 'ds_userid_on', 'ds_black_userids', 'decimal_amt_flag', 'notify_callback_type'}
            self.logger.info(f"查询商户信息，ID: {merchant_id}")
            merchant = await self.get_result_by_condition('merchant', keys, {'id': merchant_id})

            if not merchant:
                self.logger.warning(f"商户 ID {merchant_id} 不存在")
                return await self.json_response(data=msg[10004])
            if merchant['status'] == 0:
                self.logger.warning(f"商户 ID {merchant_id} 已被禁用")
                return await self.json_response(data=msg[10005])

            self.logger.info(f"商户 ID {merchant_id} 的代收启用标志: {merchant['ds_on']}")
            # if merchant['ds_on'] != 1:
            #     self.logger.warning(f"商户 ID {merchant_id} 代收已关闭")
            #     return await self.json_response(data=msg[10027])

            ds_black_ips = merchant['ds_black_ips']
            self.logger.info(f"商户 ID {merchant_id} 的黑名单 IP 列表: {ds_black_ips}")
            # 如果 ds_black_ips 是字符串，可能是以逗号分隔的 IP 列表，转换成 set 进行检查
            blacklist = set(ds_black_ips.split(',')) if ds_black_ips else set()
            self.logger.info(f"解析后的黑名单集合: {blacklist}")
            self.logger.info(f"当前玩家 IP: {data['player_ip']}")
            # 只有在 ds_on == 0 并且 IP 在黑名单中时，才进行封禁
            if (not data['player_ip'] or data['player_ip'] in blacklist) and merchant['ds_on'] == 0:
                self.logger.warning(f"商户 ID {merchant_id} 代收黑名单 IP 封禁: {data['player_ip']}")
                return await self.json_response(data=msg[10027])

            self.logger.info(f"商户 ID {merchant_id} 的代收user_id启用标志: {merchant['ds_userid_on']}")
            
            ds_black_userids = merchant['ds_black_userids']
            self.logger.info(f"商户 ID {merchant_id} 的黑名单 user_id 列表: {ds_black_userids}")
            # 如果 ds_black_userids 是字符串，可能是以逗号分隔的 user_id 列表，转换成 set 进行检查
            ds_black_userids = set(ds_black_userids.split(',')) if ds_black_userids else set()
            self.logger.info(f"解析后的user_id黑名单集合: {ds_black_userids}")
            self.logger.info(f"当前玩家 user_id: {data['user_id']}")
            # 只有在 ds_on == 0 并且 user_id 在黑名单中时，才进行封禁
            if (not data['user_id'] or data['user_id'] in ds_black_userids) and merchant['ds_userid_on'] == 0:
                self.logger.warning(f"商户 ID {merchant_id} 代收黑名单 user_id 封禁: {data['user_id']}")
                return await self.json_response(data=msg[10028])

            # 验签
            self.logger.info("开始进行签名验证")
            sign_data = data.copy()

            user_id = data['user_id'] if 'user_id' in data else ''
            if 'remark' in sign_data:
                self.logger.info("从签名数据中移除 'remark'")
                del sign_data['remark']
            if 'realname' in sign_data:
                self.logger.info("从签名数据中移除 'realname'")
                del sign_data['realname']
            if 'player_ip' in sign_data:
                self.logger.info("从签名数据中移除 'player_ip'")
                del sign_data['player_ip']
            if 'user_id' in sign_data:
                self.logger.info("从签名数据中移除 'user_id'")
                del sign_data['user_id']

            self.logger.info(f"待验签数据: {sign_data}")

            if not SignatureAndVerification.md5_verify(sign_data, sign_data['sign'], merchant['mc_key']):
                self.logger.warning("签名验证失败")
                return await self.json_response(msg[10006])

            self.logger.info("签名验证成功")

            # 下单频率限制

            # 通道在N分钟内到达多少单，就限制下单
            # busy_key = 'order_gateway_busy_{gateway}'.format(gateway=self.gateway)
            # gateway_busy_key = 'gateway_busy_key_{gateway}'.format(gateway=self.gateway)
            # gateway_busy = await self.redis.get(gateway_busy_key)
            # if gateway_busy and gateway_busy.isdigit():
            #     if await self.redis.get(busy_key):
            #         self.logger.info('通道-{gateway}-4分钟内到达订单限制{count}条，限制提单1分钟,merchant_id={merchant_id}'.format(
            #             gateway=self.gateway, count=int(gateway_busy), merchant_id=self.merchant_id))
            #         return await self.json_response(msg[10008])
            #     else:
            #         if not await self.order_gateway_busy(self.gateway, self.merchant_id, int(gateway_busy), 4, 1): \
            #                 return await self.json_response(msg[10008])
            #
            # # 10分钟内4单必须有1单成功，若4单都不成功，就限制20分钟下单
            # busy_key = 'order_user_ip_busy_{ip}'.format(ip=ip)
            # order_user_busy = await self.redis.get('order_user_busy_if')
            # if order_user_busy and order_user_busy.isdigit():
            #     if await self.redis.get(busy_key):
            #         self.logger.info('用户ip-{ip}10分钟内提单超过{count}次,无一次成功，限制提单,referrer={ref}'.format(ip=ip, ref=ref,
            #                                                                                        count=order_user_busy))
            #         return await self.json_response(msg[10007])

            # 获取并检查通道
            keys = ['code', 'rate', 'rates', 'fixed', 'amount_fixed', 'amount_min', 'amount_max', 'status', 'decimal_callback_enabled', 'decimal_min', 'decimal_max']
            self.logger.info(f"查询渠道信息，条件: {keys}, 网关: {gateway}")
            channel = await self.get_result_by_condition('channel', keys, {'code': gateway})
            if not channel:
                self.logger.warning("未找到对应的渠道信息")
                return await self.json_response(data=msg[10009])

            if channel['status'] == 0:
                self.logger.warning(f"渠道 {gateway} 状态为禁用，无法继续操作")
                return await self.json_response(data=msg[10010])

            # 检查金额
            self.logger.info(f"检查金额: {amount} 是否符合要求")
            if not await self.check_amount(amount, channel):
                self.logger.warning("金额不符合要求")
                return await self.json_response(msg[10011])

            # 获取并检查商户费率
            self.logger.info(f"获取商户渠道费率，商户ID: {merchant_id}, 网关: {gateway}")
            merchant_channel = await self.get_result_by_condition('merchant_channel',
                                                                  ['rate', 'status', 'otherpay', 'is_force'],
                                                                  {'merchant_id': merchant_id,
                                                                   'code': gateway, 'status': 1})
            if not merchant_channel:
                self.logger.warning(f"未找到商户 {merchant_id} 的渠道费率")
                return await self.json_response(data=msg[10012])

            merchant_rate = merchant_channel['rate']
            self.logger.info(f"商户费率为: {merchant_rate}")
            if merchant_rate < 0:
                self.logger.warning(f"商户费率为负值: {merchant_rate}")
                return await self.json_response(data=msg[10013])

            # 检查所有上级费率并计算代理费用
            earn_merchant = Decimal(0)
            if merchant['pid']:
                self.logger.info(f"查询商户 {merchant_id} 的上级费率")
                sql = """select pid,rate from (select @orgId id, (select @orgId:=pid from merchant where id=@orgId) pid from
                            (select @orgId:=%s) vars, merchant) t inner join merchant_channel m on m.merchant_id=pid 
                            and m.code=%s where t.pid is not null order by t.pid desc"""
                value = [merchant_id, gateway]
                merchant_prates = await self.query(sql, *value)
                if not merchant_prates:
                    self.logger.warning(f"未找到上级费率，商户 {merchant_id} 上级可能没有配置费率")
                    return await self.json_response(data=msg[10013])

                merchant_prate = Decimal(0)
                for i, v in enumerate(merchant_prates):
                    if v['rate'] < 0 or (i > 0 and v['rate'] > merchant_prates[i - 1]['rate']):
                        self.logger.warning(f"上级费率存在错误，费率: {v['rate']}")
                        return await self.json_response(data=msg[10013])
                    merchant_prate = Decimal(v['rate'])

                earn_merchant = amount * (merchant_rate - merchant_prate)
                self.logger.info(f"商户代理盈利: {earn_merchant}")
                if earn_merchant < 0:
                    self.logger.warning("商户代理盈利为负值，无法继续操作")
                    return await self.json_response(data=msg[10013])

            # 检查订单重复
            self.logger.info(f"检查商户订单号 {merchant_code} 是否重复")
            if await self.get_result_by_condition('orders_ds', ['id'], {'merchant_code': merchant_code}):
                self.logger.warning(f"订单号 {merchant_code} 已存在，重复订单")
                return await self.json_response(data=msg[10014])

            # 生成订单
            order_data = dict()
            self.logger.info(f"生成订单，订单数据准备: {order_data}")
            order_data['code'] = await self.create_order_code('S')  # 订单号
            order_data['amount'] = amount  # 金额
            order_data['poundage'] = amount * merchant_rate  # 手续费
            order_data['realpay'] = amount - order_data['poundage']  # 结算金
            order_data['channel_code'] = gateway  # 网关号
            order_data['callback'] = data['callback']  # 回调地址
            order_data['notify'] = data['notify']  # 通知地址
            order_data['merchant_id'] = merchant_id  # 商户ID
            order_data['merchant_code'] = merchant_code  # 商户订单号
            order_data['merchant_rate'] = merchant_rate  # 商户费率
            order_data['earn_merchant'] = earn_merchant  # 商户代理盈利
            order_data['user_id'] = user_id  # user_id
            order_data['auth_code'] = ''.join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(5))  # 确认码
            if 'remark' in data:
                order_data['remark'] = data['remark']  # 备注
            if 'realname' in data:
                order_data['realname'] = data['realname']  # 备注
            if 'player_ip' in data:
                order_data['player_ip'] = data['player_ip']  # 用户IP

            self.logger.info(f"创建订单: {order_data}")
            # 创建订单
            if not await self.create_result('orders_ds', order_data):
                self.logger.warning(f"订单 {order_data['code']} 创建失败")
                return await self.json_response(data=msg[10014])

            # 开始派单
            order_pay_url = ''
            # 订单时效token
            self.logger.info(f"准备开始派单，订单号: {order_data['code']}")
            order_token = await self.token_generate(order_data['code'])  # 订单时效token
            # 小数点功能只在自己的代收系统中启用
            use_decimal_callback = False
            original_amount = amount
            push_success = False  # 标记是否成功派单
            upi = ""
            # 调用 push_order 并将返回的字典赋给一个变量
            push_result = await self.push_order(order_data, merchant['target_payment'])

            if merchant_channel['is_force']:
                self.logger.info(f"强制支付，跳转到其他支付网关: {merchant_channel['otherpay']}")
                order_pay_url = await self.other_pay(merchant_channel['otherpay'], order_data)
            elif push_result and push_result.get('success'):
                # 自己的代收系统派单成功
                push_success = True
                upi = push_result.get('upi')
                order_pay_url = self.application.pay_url + '{token}'.format(token=order_token)
            elif merchant_channel['otherpay']:
                self.logger.info(f"使用其他支付网关: {merchant_channel['otherpay']}")
                order_pay_url = await self.other_pay(merchant_channel['otherpay'], order_data)
            # 判断是否是需要接入自有收银台的三方支付
            if merchant_channel['otherpay'] and order_pay_url:
                other_pay = merchant_channel['otherpay']
                sql_third = 'select merchant_id, name, channel_code, query_url from otherpay where id = %s'
                self.logger.info(f"查询三方支付数据，支付ID: {other_pay}")
                other_pay_info = await self.query(sql_third, other_pay)
                if other_pay_info[0]['name'] in ['snakepay', 'hkpay', 'TataPay', 'TataPay_t100037','qqpay']:
                    self.logger.info(f"三方支付{other_pay_info[0]['name']}接入自有收银台: {merchant_channel['otherpay']}")
                    order_pay_url = self.application.pay_url + '{token}'.format(token=order_token)

            # 新追加的通道1005 才具备小数点的功能
            self.logger.info(f'检测到 {gateway} =={push_success}，准备处理小数点回调逻辑')

            if str(gateway) == '1005':
                self.logger.info(f'检测到 gateway 为 1005，准备处理小数点回调逻辑')
                # 处理小数点回调功能（自有系统派单成功后统一处理）
                # 商户+通道双重控制：只有两者都启用才使用小数点回调
                # channel_enabled = channel.get('decimal_callback_enabled') == 1
                channel_enabled = True
                # remove 20250703
                # merchant_enabled = merchant.get('decimal_amt_flag') == 1
                self.logger.info(f'通道 decimal_callback_enabled 设置为: {channel_enabled}')

                
                if push_success and channel_enabled:
                    use_decimal_callback = True

                    self.logger.info(f'通道 {gateway} 启用小数点回调功能')
                    self.logger.info(f'通道 {gateway} 和商户 {merchant_id} 都启用小数点回调功能')

                    # 获取通道配置的小数范围
                    # decimal_min = float(channel.get('decimal_min', 0.01))
                    # decimal_max = float(channel.get('decimal_max', 0.99))
                    decimal_min = float(channel.get('decimal_min', 0.01))
                    decimal_max = float(channel.get('decimal_max', 0.99))

                    # 判断方向：正区间 → 上浮；负区间 → 下浮；否则报错
                    offset_min = 0
                    offset_max = 0
                    direction_str = ""
                    if decimal_min > 0 and decimal_max > 0:
                        offset_min = decimal_min
                        offset_max = decimal_max
                        direction_str = "上浮"
                    elif decimal_min < 0 and decimal_max < 0:
                        offset_min = decimal_max  # 更接近0的负数
                        offset_max = decimal_min  # 更远离0的负数（负方向）
                        direction_str = "下浮"
                    else:
                        self.logger.error(f"decimal_min 与 decimal_max 不一致（正负混用），配置错误: min={decimal_min}, max={decimal_max}")
                        return await self.json_response(data=msg[10014])
                    
                    self.logger.info(f'小数金额调整方向：{direction_str}，配置区间：{offset_min} ~ {offset_max}')

                    # 从数据库获取订单的payment_id（push_order成功后已经设置）
                    order_info = await self.query("SELECT payment_id FROM orders_ds WHERE code=%s", order_data['code'])
                    if not order_info or not order_info[0]['payment_id']:
                        self.logger.error(f'订单 {order_data["code"]} 未找到 payment_id，无法生成小数点金额')
                        return await self.json_response(data=msg[10014])
                    
                    payment_id = order_info[0]['payment_id']
                    self.logger.info(f'订单 {order_data["code"]} 的 payment_id: {payment_id}')

                    # 生成唯一的小数点金额
                    new_amount = await self.generate_unique_decimal_amount(
                        original_amount, offset_min, offset_max, gateway, order_data['code'], payment_id
                    )

                    if not new_amount:
                        self.logger.error(f'生成唯一小数点金额失败，订单号: {order_data["code"]}')
                        return await self.json_response(data=msg[10014])

                    # 更新数据库中的订单记录
                    await self.update_result('orders_ds', {
                        'amount': new_amount,
                        'original_amount': original_amount
                    }, {'code': order_data['code']})

                    # 移除旧的简单映射方式，使用新的List+Hash方式已在generate_unique_decimal_amount中处理
                    decimal_part = new_amount - original_amount
                    self.logger.info(f'为订单 {order_data["code"]} 生成小数点金额: {original_amount} + {decimal_part} = {new_amount}')
                    self.logger.info(f'通道配置的小数范围: {decimal_min:.2f} - {decimal_max:.2f}')
                    self.logger.info(f'将小数点金额 {new_amount:.2f} 与订单的映射关系存入Redis, key=decimal_amount:{new_amount:.2f}')
                elif push_success and not channel_enabled:
                    self.logger.info(f'通道 {gateway} 未启用小数点回调功能，使用原始金额')
                elif push_success:
                    self.logger.info(f'商户 {merchant_id} 未启用小数点回调功能，使用原始金额')
                else:
                    self.logger.info(f'小数点回调控制：通道启用={channel_enabled}, 派单成功={push_success}')

            if order_pay_url:
                result = dict(code=0, data=order_pay_url, message='下单成功')
                # # 添加upi返回
                # if hasattr(self, 'upi') and self.upi:
                #     self.logger.info(f"解析前 UPI: {self.upi}")  # 记录初始 UPI
                #     # 如果上传是 upi://pay?pa=jassbrar13@axl&pn=Jass%20Brar&mc=0000&mode=02&purpose=00 对upi进行解析
                #     if 'upi://pay' in self.upi and 'pa=' in self.upi:
                #         parsed_url = urlparse(self.upi)
                #         params = parse_qs(parsed_url.query)
                #         self.upi = params['pa'][0]
                #     self.logger.info(f"解析后的 UPI: {self.upi} code: {order_data['code']}")
                #     result['upi'] = self.upi
                # else:
                #     self.logger.warn("UPI 解析失败，返回为空")
                #     result['upi'] = ""
                result['upi'] = upi
                result['amount'] = amount
                result['token'] = order_token
                result['order_code'] = order_data['code']

                # 如果启用了小数点回调，提供额外字段说明
                if use_decimal_callback:
                    result['original_amount'] = original_amount
                    result['decimal_callback_enabled'] = True
                # 关联查询直接获取 account
                sql = """
                    SELECT p.account_accno, p.account_iban, p.bank_type 
                    FROM orders_ds o 
                    JOIN payment p ON o.payment_id = p.id 
                    WHERE o.code = %s 
                    LIMIT 1
                """
                payment_info = await self.query(sql, order_data['code'])

                if payment_info:
                    info = payment_info[0]
                    # 判断是否为 EasyPaisa (id 97 对应 EASYPAISA)
                    if info.get('bank_type') == 97:
                        # 如果是 EP，取 account_iban 后面的 8 位
                        iban = info.get('account_iban') or ""
                        result['account'] = iban[-8:] if len(iban) >= 8 else iban
                    else:
                        # 其他情况取 account_accno
                        result['account'] = info.get('account_accno') or ""
                else:
                    result['account'] = ""
                
                self.logger.info('cdee={code_s}, merchant_code={code},url={url},upi={upi},token={token},account={account}'.format(
                    code_s=order_data['code'], 
                    code=order_data['merchant_code'], 
                    url=order_pay_url, 
                    upi=result['upi'], 
                    token=result['token'],
                    account=result['account']
                ))
                # self.logger.info('cdee={code_s}, merchant_code={code},url={url},upi={upi},token={token}'.format(code_s=order_data['code'], code=order_data['merchant_code'], url=order_pay_url, upi=result['upi'], token=result['token']))
                return await self.json_response(result)

                # 返回商户支付连接或者支付页面
                #     if self._merchant_info['if_return_url']:
                #         result = dict(code=0, data=pay_url, message='')
                #         return await self.json_response(result)
                #     else:
                #         result = dict(url=pay_url)
                #         return await self.render('order/redirect_to_order.html', **result)
                # if hasattr(self, 'api_result') and self.api_result:
                #     msg[10048]['data'] = self.api_result
                # result = dict(code=0, msg='下单成功')
                # return await self.json_response(result)
            # 码不足且无三方接单，取消订单
            self.logger.info(f"更新订单状态，订单号: {order_data['code']}，设置状态为 -1")
            await self.update_result('orders_ds', {'status': -1}, {'code': order_data['code']})

            # 检查是否存在 api_result 属性并处理
            if hasattr(self, 'api_result') and self.api_result:
                self.logger.info(f"API 结果存在，返回数据: {self.api_result}")
                msg[10008]['data'] = self.api_result
            else:
                self.logger.warning("API 结果不存在，返回默认消息")

            # 返回响应
            self.logger.info(f"返回响应，数据: {msg[10008]}")
            return await self.json_response(data=msg[10008])

        except Exception as e:
            # self.logger.exception(e)
             # 记录详细的错误日志，包括异常类型、异常信息和堆栈跟踪
            self.logger.exception(f"错误发生在 {datetime.datetime.now()}，异常类型: {type(e).__name__}，异常信息: {str(e)}")
            # 记录堆栈信息，帮助调试
            stack_trace = traceback.format_exc()  # 获取完整的堆栈信息
            self.logger.error(f"堆栈跟踪:\n{stack_trace}")
            return await self.json_response(data=msg[10014])

    # in_mins 分钟内到达订单限制，就限制下单 mins 分钟
    async def order_gateway_busy(self, gateway, merchant_id, orders, in_mins, mins):
        mins_ago = datetime.datetime.now() - datetime.timedelta(minutes=in_mins)
        sql_allow = "select count(*) as trx from orders_ds where time_create > %s and status in (0,1,2) and gateway=%s"
        ret = await self.query(sql_allow, mins_ago, gateway)
        if not ret:
            return True
        if ret[0]['trx'] > orders:
            self.logger.info(
                '通道-{gateway}-{in_mins}分钟内到达限制单量{orders}，限制提单时间{mins}分钟,merchant_id={merchant_id}'.format(
                    gateway=gateway, in_mins=in_mins, orders=orders, mins=mins,
                    merchant_id=merchant_id))
            busy_key = 'order_gateway_busy_{gateway}'.format(gateway=gateway)
            await self.redis.set(key=busy_key, value=1, expire=mins * 60)
            return False
        return True

    # 检查金额是否符合通道
    @staticmethod
    async def check_amount(amount, channel):
        try:

            if channel['fixed']:
                amount_fixed = channel['amount_fixed'].split(',')  # 通道固额金额
                return str(amount).rstrip('0').rstrip('.') in amount_fixed
            else:
                return channel['amount_min'] <= amount <= channel['amount_max']
        except Exception:
            return False

    async def update_target_in_redis(self):
        """更新商户指定码的缓存"""
        target_payment_key = 'target_payment_key'

        target_payment_list = await self.query(
            "SELECT target_payment FROM merchant WHERE target_payment IS NOT NULL AND target_payment != '';")

        target_payment_set = set()
        for target_payment in target_payment_list:
            for single_id in target_payment['target_payment'].split(','):
                if single_id.strip():
                    target_payment_set.add(single_id)

        if target_payment_set:
            target_payment_str = ','.join(target_payment_set)
            await self.redis.set(target_payment_key, target_payment_str)
            self.logger.info('商户指定码已更新缓存：{}'.format(target_payment_str))
        else:
            self.logger.info('未查询到商户指定码内容')
        return target_payment_set

    async def fetch_mysql_dedicated_payment_ids(self):
        target_payment_rows = await self.query(
            "SELECT target_payment FROM merchant WHERE target_payment IS NOT NULL AND target_payment != '';"
        )
        dedicated_payment_ids = []
        for row in target_payment_rows or []:
            dedicated_payment_ids.extend(_parse_payment_id_list(row.get('target_payment')))
        return _parse_payment_id_list(dedicated_payment_ids)

    async def fetch_ds_candidate_rows(self, amount, channel_code, target_payment_ids=None, limit=20):
        dedicated_payment_ids = []
        if not target_payment_ids:
            dedicated_payment_ids = await self.fetch_mysql_dedicated_payment_ids()
        sql, params = build_ds_candidate_sql(
            amount=amount,
            channel_code=channel_code,
            target_payment_ids=target_payment_ids,
            dedicated_payment_ids=dedicated_payment_ids,
            limit=limit,
        )
        return await self.query(sql, *params)

    async def generate_unique_decimal_amount(self, original_amount, decimal_min, decimal_max, channel_code, order_code, payment_id):
        """
        生成唯一的小数点金额，使用新的 List + Hash 设计方案
        Args:
            original_amount: 原始金额
            decimal_min: 最小小数点值
            decimal_max: 最大小数点值
            channel_code: 通道代码
            order_code: 订单号
            payment_id: 收款账户ID
        Returns:
            Decimal: 唯一的小数点金额，失败返回None
        """
        max_attempts = 100  # 最大尝试次数
        order_timeout = 480   # 订单有效期8分钟（比订单超时时间7分钟稍长）
        list_timeout = 600    # List存在时间10分钟（比订单有效期长）

        for attempt in range(max_attempts):
            # 生成随机小数部分
            decimal_part = Decimal(format(random.uniform(decimal_min, decimal_max), '.2f'))
            new_amount = original_amount + decimal_part

            # Redis 键设计
            amount_key = f"decimal_amount:{new_amount:.2f}"           # List 存储 payment_id 队列
            cleanup_key = f"decimal_cleanup:{new_amount:.2f}"         # Hash 存储删除时间控制
            
            # 检查是否已有相同 payment_id 在队列中
            existing_payment_ids = await self.redis.lrange(amount_key, 0, -1)
            # 处理字节类型转换，确保类型一致性
            existing_payment_ids_str = [pid.decode() if isinstance(pid, bytes) else str(pid) for pid in existing_payment_ids]
            if str(payment_id) in existing_payment_ids_str:
                self.logger.warning(f'payment_id {payment_id} 已在金额 {new_amount:.2f} 的队列中，重新生成')
                continue

            try:
                # 原子操作：将 payment_id 添加到队列并设置删除时间
                pipe = self.redis.pipeline()
                
                # 1. 将 payment_id 添加到 List 头部
                pipe.lpush(amount_key, payment_id)
                
                # 2. 设置删除时间戳到 Hash 中
                current_time = time.time()
                expire_time = current_time + order_timeout
                pipe.hset(cleanup_key, payment_id, expire_time)
                
                # 3. 设置 payment_id 释放时间控制（使用payment_id+金额确保唯一性）
                release_key = f"{payment_id}:{new_amount:.2f}"
                pipe.hset('payment_release_time', release_key, expire_time)
                
                # 4. 设置 List 的过期时间（比订单有效期长）
                pipe.expire(amount_key, list_timeout)
                pipe.expire(cleanup_key, list_timeout)
                
                # 执行原子操作
                await pipe.execute()

                self.logger.info(f'生成唯一小数点金额成功: {new_amount:.2f}, payment_id: {payment_id} (尝试次数: {attempt + 1})')
                self.logger.info(f'设置过期时间: {expire_time}, 当前时间: {current_time}')
                return new_amount
                
            except Exception as e:
                self.logger.error(f'Redis 操作失败: {e}, 重试 (尝试次数: {attempt + 1})')
                continue

        # 超过最大尝试次数，生成失败
        self.logger.error(f'生成唯一小数点金额失败，超过最大尝试次数 {max_attempts}')
        return None

    async def cleanup_decimal_callback_on_success(self, payment_id, amount, cleanup_reason="成功回调"):
        """
        小数点回调清理函数
        可用于成功回调后清理或超时清理
        
        Args:
            payment_id: 支付ID
            amount: 金额
            cleanup_reason: 清理原因，默认为"成功回调"，可传入"超时清理"等
        """
        try:
            amount_key = f'decimal_amount:{amount:.2f}'
            cleanup_key = f'decimal_cleanup:{amount:.2f}'
            
            # 从 List 中删除 payment_id
            removed_count = await self.redis.lrem(amount_key, 1, payment_id)
            if removed_count > 0:
                self.logger.info(f'{cleanup_reason}清理: 从 {amount_key} 中删除 {payment_id}')
            
            # 从 Hash 中删除对应记录（使用payment_id+金额作为释放时间控制键）
            await self.redis.hdel(cleanup_key, payment_id)
            release_key = f"{payment_id}:{amount:.2f}"
            await self.redis.hdel('payment_release_time', release_key)
            
            self.logger.info(f'{cleanup_reason}清理完成: payment_id={payment_id}, amount={amount}')
            
        except Exception as e:
            self.logger.exception(f'{cleanup_reason}清理失败: {e}')

    # 派给三方支付
    async def other_pay(self, other_pay, data):
        self.logger.info(f"开始处理三方支付，支付方式: {other_pay}, 订单数据: {data}")
        
        if other_pay:
            # 查询三方支付信息
            sql_third = 'select merchant_id, `key`, key2, key3, pay_url, name, channel_code, query_url from otherpay where id = %s'
            self.logger.info(f"查询三方支付数据，支付ID: {other_pay}")
            r_third = await self.query(sql_third, other_pay)
            self.api_result = None
            
            if not r_third:
                self.logger.warn('查询三方支付错误 {other_pay}'.format(other_pay=other_pay))
                self.api_result = "third payment error 1"
                return False
            
            try:
                # 订单时效token
                self.logger.info(f"生成订单时效token，订单号: {data['code']}")
                order_token = await self.token_generate(data['code'])

                # 根据支付方式选择对应的支付处理
                if r_third[0]['name'] == 'Razorpay-upi-origin':
                    self.logger.info(f"选择 Razorpay-upi-origin 支付方式，订单号: {data['code']}")
                    return await Razorpay_upi_origin(self, data['code'], data['amount'], r_third[0]['key'], r_third[0]['key2'], r_third[0]['pay_url'])

                # 新增 lucky 支付逻辑
                elif r_third[0]['name'] == 'lucky':
                    self.logger.info(f"选择 Lucky 支付方式，订单号: {data['code']}")
                    return await lucky_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key2'], r_third[0]['pay_url'])

                elif r_third[0]['name'] == 'apay':
                    self.logger.info(f"选择 Apay 支付方式，订单号: {data['code']}")
                    return await apay_payment(self, data['code'], data['amount'],r_third[0]['name'] ,r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'])

                # 新增 kingpay 支付逻辑
                elif r_third[0]['name'] == 'kingpay':
                    self.logger.info(f"选择 Kingpay 支付方式，订单号: {data['code']}")
                    return await kingpay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['key3'], r_third[0]['pay_url'], '/kingpay_notify')

                elif r_third[0]['name'] == 'kingpay2':
                    self.logger.info(f"选择 Kingpay2 支付方式，订单号: {data['code']}")
                    return await kingpay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['key3'], r_third[0]['pay_url'], '/kingpay_notify2')

                # 新增 wepay 支付逻辑
                elif r_third[0]['name'] == 'wepay':
                    self.logger.info(f"选择 Wepay 支付方式，订单号: {data['code']}")
                    return await wepay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'])

                # 新增 777pay 支付逻辑
                elif r_third[0]['name'] == '777pay':
                    self.logger.info(f"选择 777pay 支付方式，订单号: {data['code']}")
                    return await pay777pay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'])

                # 新增 swiftpay 支付逻辑
                elif r_third[0]['name'] == 'swiftpay':
                    self.logger.info(f"选择 swiftpay 支付方式，订单号: {data['code']}")
                    return await swiftpay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['key2'], r_third[0]['key3'], r_third[0]['pay_url'])

                # 新增 quickpay 支付逻辑
                elif r_third[0]['name'] == 'quickpay':
                    self.logger.info(f"选择 quickpay 支付方式，订单号: {data['code']}")
                    return await quickpay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key3'], r_third[0]['pay_url'])

                # 新增 snakepay 支付逻辑
                elif r_third[0]['name'] == 'snakepay':
                    self.logger.info(f"选择 snakepay 支付方式，订单号: {data['code']}")
                    return await snakepay_payment(self, r_third[0]['name'], data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'])

                # 新增 hkpay 支付逻辑
                elif r_third[0]['name'] == 'hkpay':
                    self.logger.info(f"选择 hkpay 支付方式，订单号: {data['code']}")
                    return await hkpay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'])

                # 新增 skpay 支付逻辑
                elif r_third[0]['name'] == 'skpay':
                    self.logger.info(f"选择 skpay 支付方式，订单号: {data['code']}")
                    return await skpay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'],r_third[0]['key3'], r_third[0]['pay_url'])

                # 新增 ospay_upi 支付逻辑
                elif r_third[0]['name'] in ['ospay_upi', '789pay_upi']:
                    self.logger.info(f"选择 ospay_upi 支付方式，订单号: {data['code']}")
                    return await ospay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'], r_third[0], '1001')

                # 新增 ospay 支付逻辑
                elif r_third[0]['name'] in ['ospay', '789pay']:
                    self.logger.info(f"选择 ospay 支付方式，订单号: {data['code']}")
                    return await ospay_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'], r_third[0], '1004')


                # 新增 TataPay 支付逻辑
                elif r_third[0]['name'] in ['TataPay', 'TataPay_t100037']:
                    self.logger.info(f"选择 TataPay 支付方式，订单号: {data['code']}")
                    return await tatapay_payment(self, data['code'], data['amount'], r_third[0]['name'], r_third[0]['merchant_id'], r_third[0]['key'], r_third[0]['pay_url'])

                # 新增 Vibrapay 支付逻辑
                elif r_third[0]['name']  == 'Vibrapay':
                    self.logger.info(f"选择 Vibrapay 支付方式，订单号: {data['code']}")
                    return await vibrapay_payment(self, data['code'], data['amount'], r_third[0]['name'],r_third[0]['merchant_id'], r_third[0]['key'],r_third[0]['key2'], r_third[0]['pay_url'])

                # 新增 qqpay 支付逻辑
                elif r_third[0]['name'] == 'qqpay':
                    self.logger.info(f"选择 qqpay 支付方式，订单号: {data['code']}")
                    return await qqpay_payment(self, data['code'], data['amount'], r_third[0]['name'],r_third[0]['merchant_id'], r_third[0]['key'],r_third[0]['pay_url'])

                elif r_third[0]['name'] == 'gamepayer':
                    self.logger.info(f"选择 gamepayer 支付方式，订单号: {data['code']}")
                    return await gamepayer_payment(self, data['code'], data['amount'], r_third[0]['merchant_id'], r_third[0]['name'], r_third[0]['key'], r_third[0]['pay_url'])

                elif r_third[0]['name'] == 'easypay':
                    # Easypay SOAP 代收：不在此处调 SOAP，只返回收银台 URL
                    # SOAP 由用户在收银台输入手机号后触发 /easypay/initiate
                    self.logger.info(f"选择 Easypay SOAP 支付方式，订单号: {data['code']}, otherpay_id: {other_pay}")
                    await self.execute(
                        "UPDATE orders_ds SET third_party_name='easypay', otherpay=%s WHERE code=%s",
                        other_pay, data['code'])
                    return self.application.pay_url + '{token}'.format(token=order_token)

            except Exception as e:
                self.api_result = "third payment error 2"
                self.logger.info('{code}订单,走三方通道错误{e}'.format(code=data['code'], e=e))

        self.logger.warning(f"三方支付处理失败，订单号: {data['code']}")
        return False


    async def push_order(self, data, target_payment):
        is_push = False
        code = data['code']
        amount = data['amount']
        start_time = datetime.datetime.now().timestamp()
        upi = ''

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
            self.logger.warn('code: {code}, 指定码格式错误： "{target_payment}"'.format(code=code, target_payment=target_payment))
            target_payment_list = []
        else:
            target_payment_list = target_payment.split(',') if target_payment else []
        if target_payment and target_payment_list:
            self.logger.warn('code: {code}, 指定码{target_payment}'.format(code=code, target_payment=target_payment))

        _list = await self.fetch_ds_candidate_rows(
            amount,
            data.get("channel_code"),
            target_payment_ids=target_payment_list,
            limit=20,
        )
        self.logger.warn('code: {code}, 手写候选SQL时间：{t}, 候选数量：{count}'.format(
            code=code,
            t=datetime.datetime.now().timestamp() - start_time,
            count=len(_list or []),
        ))
        if not _list:
            return is_push
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
            'payment_status', 'payment_certified'
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
        self.logger.warn('code: {code}, 查询前置时间：{t}'.format(code=code, t=datetime.datetime.now().timestamp() - start_time))

        while True:
            if datetime.datetime.now().timestamp() - start_time > 30:
                self.logger.warn('code: {code}, 超过30s派单，直接丢弃'.format(code=code))
                break

            payment_id = None
            if payment_id is None:
                # 超过10s 未获取到payment_id 的直接派给公户
                if datetime.datetime.now().timestamp() - start_time > 10 and gonghu_ds_payment_ids:
                    payment_id = random.choice(gonghu_ds_payment_ids)
                    self.logger.warn('code: {code}, 超过10s派单，直接派给公户{id}'.format(code=code, id=payment_id))
                if payment_id is None:
                    # 不用pop，使用权重随机提取
                    # payment_id = await self.redis.lpop(list_name)
                    if not payment_id_weights and not payment_target_payment_list:
                        self.logger.warn('code: {code}, 无码派单'.format(code=code))
                        break
                    # 如果存在payment_target_payment_list的值，优先取payment_target_payment_list中的值；
                    # 不存在则取payment_id_weights中的值
                    if payment_target_payment_list:
                        payment_id = random.choices(payment_target_payment_list, target_weights, k=1)[0]
                        self.logger.warn('code: {code}, 有指定码，选用指定码接单: {id}'.format(code=code, id=payment_id))
                        # 随机取出的码移除出指定码商列表，避免下次重新获取到
                        del target_weights[payment_target_payment_list.index(payment_id)]
                        payment_target_payment_list.remove(payment_id)
                    else:
                        payment_id = random.choices(payment_id_weights, weights, k=1)[0]
                        self.logger.warn('code: {code}, 按照权重随机选取码接单: {id}'.format(code=code, id=payment_id))
                        # 随机取出的码移除出列表，避免下次重新获取到
                        del weights[payment_id_weights.index(payment_id)]
                        payment_id_weights.remove(payment_id)
            if payment_id is None:
                break
            order_amount = data['amount']

            # 获取收款信息
            # payment = await self.get_result_by_condition('payment', ['partner_id', 'amount_top', 'upi', 'bank_type', 'manual_status'],
            #                                              {'id': payment_id, 'certified': 1, 'status': 1})
            if int(payment_id) not in new_payment_list.keys():
                self.logger.warn('code: {code}, payment_id不在new_payment_list时间：{t}'.format(code=code, t=datetime.datetime.now().timestamp() - start_time))
                continue
            payment = new_payment_list[int(payment_id)]


            # 码异常
            if not payment:
                self.logger.warn('码{payment_id}状态异常，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                continue

            # # 获取收款信息
            # bank_type = await self.get_result_by_condition('bank_type',['id', 'status','name'],{'id': payment['bank_type']})
            # # 码异常
            # if bank_type['status'] == 0:
            #     self.logger.warn('银行{bank_type}状态禁用，不允许接单,code: {code}'.format(bank_type=bank_type['name'], code=code))
            #     continue

            partner_id = payment['partner_id']
            bank_id = payment['bank_type_id']
            bank = await self.get_result_by_condition(
                'bank_type',
                ['name'],
                {'id': bank_id}
            )
            self.logger.info(f"Step 10: bank_id {bank_id}, {bank}")
            # # 获取 payment 信息（条件：id = payment_id）
            # paymentNew = await self.get_result_by_condition(
            #     'payment',
            #     ['bank_type_id'],
            #     {'id': payment_id}
            # )
            # bank_id = paymentNew['bank_type_id'] if paymentNew and 'bank_type_id' in paymentNew else None
            # 获取 payment 信息（条件：id = payment_id）
            paymentNew = await self.get_result_by_condition(
                'payment',
                ['account_iban'],
                {'id': payment_id}
            )
            # 检查 account_iban 是否为空或不存在
            if not paymentNew or not paymentNew.get('account_iban'):
                # 如果条件满足，记录警告日志
                self.logger.warn(f"在获取 ID 为 {payment_id} 的支付信息时，account_iban 键不存在或为空，已跳过, code: {code}")
                # 然后跳过当前循环
                continue
            
            # 4. 如果所有检查都通过
            self.logger.info(f"成功获取 ID 为 {payment_id} 的支付信息，account_iban 存在 {paymentNew.get('account_iban')}, code: {code}")

            self.logger.info(f"从 payment 中获取 bank_type_id，赋值 bank_id = {bank_id}")

            if await self.redis.get('partner_grab_order_limit_{id}'.format(id=partner_id)):
                self.logger.warn('码商{partner_id}, 码{payment_id}，暂停6分钟接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                continue

            # 已停止接单
            if not await _is_collection_payment_online(
                self,
                payment_id,
                bank_id,
                bank_type=payment.get('bank_type'),
                payment=payment,
            ):
                self.logger.warn('码{payment_id}已停止接单，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                continue

            # 先获取码商确定是否外部码商，外部码商检测60分钟内，内部码商检测15分钟内订单连续失败
            # partner = await self.get_result_by_condition('partner', ['id', 'pid', 'balance', 'status', 'vip', 'type', 'ds_min', 'ds_max'],
            #                                              {'id': partner_id, 'status': 1, 'certified': 1})
            if int(partner_id) not in new_partner_list.keys():
                self.logger.warn('code: {code}, partner_id不在new_partner_list时间：{t}'.format(code=code, t=datetime.datetime.now().timestamp() - start_time))
                continue
            partner = new_partner_list[int(partner_id)]
            # 派单时间间隔
            # _send_orders_interval = await self.redis.get("send_orders_interval_{id}".format(id=payment_id))
            # if _send_orders_interval:
            #     self.logger.warn('码商{partner_id}的码{payment_id}时间间隔{send_orders_interval}s内有单，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, send_orders_interval=_send_orders_interval, code=code))
            #     continue
            # 动态限制：每个银行 bank_id 在 accept_interval 秒内最多接 max_count 单
            accept_interval_key = f"send_orders_max_sec_{bank_id}"
            max_count_key = f"send_orders_max_count_{bank_id}"

            accept_interval = await self.redis.get(accept_interval_key)
            max_count = await self.redis.get(max_count_key)

            self.logger.info(f"[动态限制] 获取 Redis Key：{accept_interval_key} = {accept_interval}")
            self.logger.info(f"[动态限制] 获取 Redis Key：{max_count_key} = {max_count}")

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
                result = await self.query(sql, payment_id, accept_interval)
                order_count = result[0]['count'] if result and 'count' in result[0] else 0

                self.logger.info(
                    f"[动态限制] payment_id: {payment_id}, bank_id: {bank_id}, 时间窗口: {accept_interval}s, 当前接单数: {order_count}, 最大允许: {max_count}"
                )

                if order_count >= max_count:
                    self.logger.warning(
                        f"[动态限制] payment_id: {payment_id}, 银行 {bank_id} 在过去 {accept_interval}s 内已接 {order_count} 单，超过最大限制 {max_count}，不允许再次接单，code: {code}"
                    )
                    continue
            else:
                # self.logger.info(
                #     f"[动态限制] 未配置 payment_id: {payment_id}, bank_id={bank_id} 的动态限制（accept_interval 或 max_count 缺失），跳过此限制"
                # )

                # # 固定限制：每个码 payment_id 每 6 分钟只能接一单
                # send_orders_interval = await self.redis.get("send_orders_interval")
                # _send_orders_interval = await self.redis.get(f"send_orders_interval_{payment_id}")
                # current_ts = int(time.time())

                # self.logger.info(f"从 Redis 获取 send_orders_interval 全局配置值: {send_orders_interval}")
                # self.logger.info(f"从 Redis 获取 send_orders_interval_{payment_id} 的值: {_send_orders_interval}")

                # # 检查固定限制
                # if _send_orders_interval:
                #     last_ts = int(_send_orders_interval)
                #     interval = current_ts - last_ts

                #     self.logger.info(
                #         f"[固定限制] 当前时间戳: {current_ts}，上次接单时间戳: {last_ts}，间隔: {interval} 秒"
                #     )

                #     if interval < int(send_orders_interval):
                #         self.logger.warning(
                #             f"[固定限制] 码商 {partner_id} 的码 {payment_id} 在 {interval}s 前接过单，未满 {int(send_orders_interval)} 秒，不允许再次接单，code: {code}"
                #         )
                #         continue
                # else:
                #     self.logger.info(f"[固定限制] Redis 中未找到 send_orders_interval_{payment_id}，视为首次接单或记录已过期")

                default_interval = 360 
                send_orders_interval_global = await self.redis.get("send_orders_interval")

                if data['channel_code'] in (1002, 1003):
                    # 【固定 3 分钟逻辑】: 1002 和 1003 固定为 180 秒
                    interval_seconds = 180
                    self.logger.info(f"[固定限制] 通道 {data['channel_code']}，固定接单间隔为 180 秒 (3 分钟)")
                else:
                    # 其他通道使用全局配置，若无配置则使用默认值 360 秒
                    try:
                        interval_seconds = int(send_orders_interval_global)
                    except (TypeError, ValueError):
                        interval_seconds = default_interval
                    self.logger.info(f"[固定限制] 通道 {data['channel_code']}，全局接单间隔为 {interval_seconds} 秒")

                # 2. 检查固定限制 (使用 Redis EXISTS 替代时间戳比较)
                key_interval = f"send_orders_interval_{payment_id}"

                # 检查 Key 是否存在。如果存在，表示码商仍在冷却期内。
                if await self.redis.exists(key_interval):
                    # 如果需要查看剩余时间，可以使用 TTL
                    # ttl = await self.redis.ttl(key_interval)
                    
                    self.logger.warning(
                        f"[固定限制] 码 {payment_id} 正在冷却期 ({interval_seconds} 秒限制)，不允许再次接单，code: {code}"
                    )
                    continue

                self.logger.info(f"[固定限制] Redis 中未找到 {key_interval}，可以接单")

            # 剔除死码等
            send_orders_ds_limit = await self.redis.get("send_orders_ds_limit_{payment_id}".format(payment_id=payment_id))
            if send_orders_ds_limit and not partner['type'] == 0:
                self.logger.warn('码商{partner_id}的码{payment_id}成功率低,暂停接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                continue
            # 码商异常
            if not partner or not partner['vip']:
                self.logger.warn('码商{partner_id}状态异常，不允许接单,code: {code}'.format(partner_id=partner_id, code=code))
                continue
            if payment['manual_status'] == 1:
                self.logger.warn('码商{partner_id}的码{payment_id}失败次数过多，人工锁定不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
                continue
            if partner['ds_min'] > order_amount:
                self.logger.warn('码商{partner_id},代收最小限额{ds_min}，订单金额{order_amount},code: {code}'.format(partner_id=partner_id,ds_min=partner['ds_min'],order_amount=order_amount, code=code))
                continue
            if partner['ds_max'] > 0 and partner['ds_max'] < order_amount:
                self.logger.warn('码商{partner_id},代收最大限额{ds_max}，订单金额{order_amount},code: {code}'.format(partner_id=partner_id,ds_max=partner['ds_max'],order_amount=order_amount, code=code))
                continue

            # 代收成功率
            orders_ds_limit_success_rate = "orders_ds_limit_success_rate"
            redis_orders_ds_limit_success_rate_count = await self.redis.get(orders_ds_limit_success_rate)
            redis_orders_ds_limit = "orders_ds_limit_{payment_id}".format(payment_id=payment_id)
            orders_ds_list_count = await self.redis.get(redis_orders_ds_limit)
            if redis_orders_ds_limit_success_rate_count and not partner['type'] == 0:  # 外部码商
                redis_orders_ds_limit_count = "orders_ds_limit_count_{payment_id}".format(payment_id=payment_id)
                if orders_ds_list_count and redis_orders_ds_limit_success_rate_count and int(orders_ds_list_count) < int(redis_orders_ds_limit_success_rate_count):
                    self.logger.warn('码商{partner_id}的码{payment_id}成功率低于{redis_orders_ds_limit_success_rate_count}%,停止接单一个小时,code: {code}'.format(partner_id=partner_id,payment_id=payment_id, redis_orders_ds_limit_success_rate_count=redis_orders_ds_limit_success_rate_count, code=code))
                    continue
                # 设置查询总条数
                limit = 10
                # 查询最近的10单
                sql = """select status from orders_ds where payment_id=%s and status in(4,3,-1) and date_add(time_create, interval 120 minute) > now() order by id desc limit %s"""
                orders_ds_list = await self.query(sql, payment_id,limit)
                orders_ds_list_count = 0
                for i in orders_ds_list:
                    if i['status'] == -1:
                        orders_ds_list_count += 1
                orders_ds_limit_success_rate_count = int(float(format(1 - float(orders_ds_list_count) / float(limit), ".2f")) * 100)
                if redis_orders_ds_limit_success_rate_count and orders_ds_limit_success_rate_count < int(redis_orders_ds_limit_success_rate_count):
                    orders_ds_limit_count = await self.redis.get(redis_orders_ds_limit_count)
                    if orders_ds_limit_count and int(orders_ds_limit_count) > 2:
                        await self.redis.delete(redis_orders_ds_limit_count)
                        await self.update_result('payment', _manual_lock_update_fields(payment), {'id': payment_id})
                        self.logger.warn('码商{partner_id},码{payment_id}成功率低于{redis_orders_ds_limit_success_rate_count}%次数过多，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id,redis_orders_ds_limit_success_rate_count=redis_orders_ds_limit_success_rate_count, code=code))
                        continue
                    await self.redis.incr(redis_orders_ds_limit_count)
                    orders_ds_limit_count = await self.redis.get(redis_orders_ds_limit_count)
                    self.logger.warn('码商{partner_id}的码{payment_id}成功率低于{redis_orders_ds_limit_success_rate_count}%,停止接单一个小时, 第{count}次,code: {code}'.format(partner_id=partner_id,payment_id=payment_id, redis_orders_ds_limit_success_rate_count=redis_orders_ds_limit_success_rate_count, count=orders_ds_limit_count, code=code))
                    await self.redis.set(redis_orders_ds_limit, orders_ds_limit_success_rate_count, 60 * 60)
                    continue

            # 最高同时接单不能超过五单
            maximum_simultaneous_orders = "maximum_simultaneous_orders"
            maximum_simultaneous_orders_count = await self.redis.get(maximum_simultaneous_orders)
            if maximum_simultaneous_orders_count and not partner['type'] == 0:  # 外部码商
                sql = """select count(*) as count from orders_ds where payment_id=%s and status in(1,2) and date_add(time_create, interval 10 minute) > now()"""
                orders_ds_count = await self.query(sql, payment_id)
                if maximum_simultaneous_orders_count and orders_ds_count[0]['count'] > int(maximum_simultaneous_orders_count):
                    self.logger.warn('码商{partner_id}的码{payment_id}最高同时接单不能超过{maximum_simultaneous_orders_count}单,code: {code}'.format(partner_id=partner_id,payment_id=payment_id,maximum_simultaneous_orders_count=maximum_simultaneous_orders_count, code=code))
                    continue

            # # 连续失败 外部码商 120分钟 暂时关闭
            # sql = """select count(if(status=-1,id,null)) as count from (select * from orders_ds where payment_id=%s and status not in (1, 2) and date_add(time_create, interval 120 minute) > now() order by id desc limit 10) as order_ds"""
            # if partner['type'] == 0:  # 内部码商 15分钟
            #     sql = """select count(if(status=-1,id,null)) as count from (select * from orders_ds where payment_id=%s and status not in (1, 2) and date_add(time_create, interval 15 minute) > now() order by id desc limit 10) as order_ds"""
            # else:  # 暂时不锁定内部码商
            #     if (await self.query(sql, payment_id))[0]['count'] == 10:
            #         await self.update_result('payment', {'manual_status': 1}, {'id': payment_id})
            #         self.logger.warn('码商{partner_id},码{payment_id}失败次数过多，不允许接单'.format(partner_id=partner_id, payment_id=payment_id))
            #         continue

            # 接近上限
            sql = """select ifnull(sum(amount), 0) as amount_today from orders_ds where payment_id=%s and time_create > curdate() and status > 0"""
            if payment['amount_top'] and payment['amount_top'] < order_amount + (await self.query(sql, payment_id))[0]['amount_today']:
                self.logger.warn('码{payment_id}接近上限，不允许接单,code: {code}'.format(payment_id=payment_id, code=code))
                continue

            # 检测订单金额是否在可接范围内,并且余额是否足够
            # partner_amount = await self.get_result_by_condition('vip', ['ds_min', 'ds_max', 'deposit_ratio', 'conditions'], {'vip': partner['vip']})
            partner_amount = _new_vip_list[partner['vip']]

            # 获取去除保证金后的余额
            partnerBalance = await self.removeDeposit(partner['balance'], partner_amount['conditions'], partner_amount['deposit_ratio'])
            if order_amount < partner_amount['ds_min'] or order_amount > partner_amount['ds_max']:
                self.logger.warn('码商{partner_id}不满足vip等级代收最大最小范围，订单金额{order_amount}代收最小限额{ds_min}代收最大限额{ds_max}，不允许接单,code: {code}'.format(partner_id=partner_id, order_amount=order_amount, ds_min=partner_amount['ds_min'], ds_max=partner_amount['ds_max'], code=code))
                continue
            if Decimal(order_amount) > partnerBalance:
                self.logger.warn('码商{partner_id}去除保证金后的余额不足，接单额度{partnerBalance}，不允许接单, code: {code}'.format(partner_id=partner_id, partnerBalance=partnerBalance, code=code))
                if partnerBalance < 400: # 接单额度小于400的，且一个小时内都没有订单的，暂停接单6分钟
                    sql = """select id from orders_ds where partner_id=%s and date_add(time_create, interval 1 hour) > now() limit 1"""
                    if not await self.query(sql, partner_id):
                        await self.redis.set('partner_grab_order_limit_{id}'.format(id=partner_id), 1, 6 * 60)
                        self.logger.warn('码商{partner_id}去除保证金后的余额不足，接单额度{partnerBalance}，且1小时未接单，暂停6分钟, code: {code}'.format(partner_id=partner_id, partnerBalance=partnerBalance, code=code))
                continue
            # 计算码商总费率
            channel = await self.get_result_by_condition('channel', ['rate', 'rates'],
                                                         {'code': data['channel_code']})
            rates = channel['rate']
            earn_partner_self = order_amount * rates
            if partner['pid']:
                rates += Decimal(channel['rates'].split(',')[0])
                if (await self.get_result_by_condition('partner', ['pid'], {'id': partner['pid']}))['pid']:
                    rates += Decimal(channel['rates'].split(',')[1])
            earn_partner = order_amount * rates
            # 计算平台盈利
            earn_system = data['poundage'] - earn_partner - data['earn_merchant']
            if earn_system < 0:
                self.logger.warn(
                    '{code}费率设置错误{partner_id}，不允许接单'.format(code=data['code'], partner_id=partner_id))
                continue

            if not partner['type'] == 0:  # 外部码商
                # 查询码商余额是否足够, 要减去爬取后的账单中该扣未扣的金额 原来是3天，现在是查询全部
                # sql = 'select ifnull(sum(amount), 0) as amount_d from bank_record where payment_id in (select id from payment where partner_id=%s) and date_add(time_create, interval 3 day) > now() and callback=0 and trade_type=1 and invalid=0 and ew_code is null'
                sql = 'select ifnull(sum(amount), 0) as amount_d from bank_record where payment_id in (select id from payment where partner_id=%s)  and callback=0 and trade_type=1 and invalid=0 and if_ew=0'
                if partnerBalance < Decimal(order_amount + (await self.query(sql, partner_id))[0]['amount_d']):
                    self.logger.warn('码商{partner_id}接单额度不足,码{payment_id}，不允许接单,code: {code}'.format(partner_id=partner_id, payment_id=payment_id, code=code))
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
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 扣除余额
                        if not await self.change_balance(conn, cur, 'partner', partner['id'], -data['amount'],
                                                         data['code'], 0):
                            self.logger.warning('{partner_id}接单扣除账户余额失败,code: {code}'.format(partner_id=partner_id, code=code))
                            continue

                        # 改变订单状态
                        key_update, val_update = await self.dict_to_equal(order_data)
                        sql = 'update orders_ds set {keys} where code=%s and status=0'.format(keys=key_update)
                        if not await cur.execute(sql, (*val_update, data['code'])):
                            await conn.rollback()
                            self.logger.warning('{partner_id}接单修改订单状态失败,code: {code}'.format(partner_id=partner_id, code=code))
                            continue
                    except Exception as e:
                        await conn.rollback()
                        self.logger.exception(code + str(e))
                        continue
                    else:
                        await conn.commit()
                        is_push = True
                        # 添加upi返回
                        self.upi = order_data['upi']
                        # 派单时间间隔
                        # send_orders_interval = await self.redis.get("send_orders_interval")
                        # if send_orders_interval and not partner['type'] == 0:  # 外部码商
                        #     # await self.redis.set("send_orders_interval_{id}".format(id=payment_id), int(send_orders_interval), int(send_orders_interval))
                        #     ts_now = int(time.time())
                        #     self.logger.info(f"准备设置 Redis 键 send_orders_interval_{payment_id}，当前时间戳: {ts_now}")

                        #     await self.redis.set(
                        #         f"send_orders_interval_{payment_id}",
                        #         ts_now,
                        #         ex=int(send_orders_interval)  # 设置过期时间为360秒，自动过期
                        #     )

                        #     self.logger.info(f"已设置 send_orders_interval_{payment_id}，值: {ts_now}，过期时间: {int(send_orders_interval)} 秒")

                        ts_now = int(time.time())

                        send_orders_interval_global = await self.redis.get("send_orders_interval")
                        self.logger.info(f"获取 send_orders_interval 的值: {send_orders_interval_global}")

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
                            self.logger.info(f"通道 {data.get('channel_code')} 命中固定 3 分钟限制，设置过期时间为 180 秒")


                        if send_orders_interval_global and not partner['type'] == 0:
                            self.logger.info(f"partner['type'] 值为: {partner['type']}, 符合条件，准备设置 send_orders_interval_{payment_id}")
                            
                            self.logger.info(f"准备设置 Redis 键 send_orders_interval_{payment_id}，当前时间戳: {ts_now}")

                            await self.redis.set(
                                f"send_orders_interval_{payment_id}",
                                ts_now,
                                ex=interval_seconds  # ✅ 使用计算出的最终冷却时间
                            )

                            self.logger.info(f"已设置 send_orders_interval_{payment_id}，值: {ts_now}，过期时间: {interval_seconds} 秒")
                        # ...

                        # 添加一个redis key用于提示加速爬取账单，按最短时间爬取一次
                        await self.redis.set(f"crawl_frequently_{payment_id}", 1, 60 * 8)
                        self.logger.info(f"[代收] push_order 成功设置 Redis 键: crawl_frequently_{payment_id}, paymentid: {payment_id}, 过期时间为 {8} 分钟。") 
                        # 调用封装好的函数
                        if bank.get('name') == 'EASYPAISA':
                            qr_code = await self.generate_qr_code(payment['id'], payment['upi'], data['amount'])
                            await self.redis.set('order_ds_third_qr_{}'.format(code), qr_code, 60 * 20)
                            upi = qr_code
                            if qr_code:
                                self.logger.info(f"订单代码 {code}  , 金额 {amount} 生成的QR码文本是: {qr_code}")
                            else:
                                self.logger.info(f"订单代码 {code}  , 金额 {amount} 未能生成QR码。")    
                        elif bank.get('name') == 'JAZZCASH':
                            await self.redis.set(f"crawl_frequently_{payment_id}", 1, 60 * 3)
                            self.logger.info(f"[代收] push_order_new 成功设置 Redis 键: crawl_frequently_{payment_id}, paymentid: {payment_id}, 过期时间为 {3} 分钟。")
                            pass

                        break
        return {"success": is_push, "upi": upi}

# UTR补单
class ds_utr(BaseHandler):
    async def post(self):
        try:
            try:
                data = {k: self.get_argument(k) for k in self.request.arguments}
                self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
            except Exception:
                self.logger.exception('商户utr补单 参数异常')
                return await self.json_response(msg_en[10006])
            ip = await self.get_ip()
            ref = self.request.headers['Referer'] if 'Referer' in self.request.headers else ''
            self.logger.info('商户utr补单 收到参数{data},referrer={ref},ip={ip}'.format(data=str(data), ref=ref, ip=ip))

            valid_keys = ['mer_id', 'utr', 'order_id', 'sign']
            not_null_keys = ['mer_id', 'utr', 'order_id', 'sign']
            # 验签 需要深拷贝
            sign_data = data.copy()
            is_robot = data.pop('robot', False)
            trans_id = data.pop('trans_id', False)

            if not await self.is_valid_key(data, valid_keys):
                return await self.json_response(data=msg_en[10006])

            if await self.is_null(data, not_null_keys):
                return await self.json_response(data=msg_en[10007])

            if not await self.check_different(data, self.data_receive_filter_xss, valid_keys):
                self.logger.info('商户utr补单 参数非法{data}'.format(data=str(data)))
                return await self.json_response(data=msg_en[10006])

            try:
                merchant_id = int(data['mer_id'])
                merchant_code = data['order_id'].strip()
                utr = data['utr'].strip()
            except Exception as e:
                self.logger.exception(e)
                return await self.json_response(data=msg_en[10006])
            # 1. 检查是否为非空字符串
            if not trans_id or not isinstance(trans_id, str):
                self.logger.info("错误：交易ID不能为空或非字符串类型。")
            else:
                # 2. 检查长度
                if len(trans_id) > 50:
                    self.logger.info(f"错误：交易ID长度超过50个字符。当前长度为：{len(trans_id)}")
                    return await self.json_response(data=msg_en[10030])
                else:
                    # 3. 检查是否包含特殊字符
                    # 正则表达式：只允许字母、数字、下划线和连字符
                    pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
                    if not pattern.match(trans_id):
                        self.logger.info(f"错误：交易ID包含特殊或非法字符。无效的ID为: {trans_id}")
                        return await self.json_response(data=msg_en[10030])
                    else:
                        # --- 验证通过，执行业务逻辑 ---
                        self.logger.info(f"交易ID '{trans_id}' 格式有效，开始处理补单请求...")
                        
            # 获取商户信息
            merchant = await self.get_result_by_condition('merchant', ['mc_key', 'status'], {'id': merchant_id})
            if not merchant:
                return await self.json_response(data=msg_en[10008])

            sign_data['sign'] = sign_data['sign'].upper()
            # 移除 trans_id 字段
            if 'trans_id' in sign_data:
                del sign_data['trans_id']
            
            self.logger.info(f"sign_data: '{sign_data}'")
            if not SignatureAndVerification.md5_verify(sign_data, sign_data['sign'], merchant['mc_key']):
                return await self.json_response(msg_en[10009])

            keys = ['code', 'amount', 'realpay', 'status', 'time_create', 'time_success', 'time_updated', 'utr', 'upi', 'third_party_name']
            r = await self.get_result_by_condition('orders_ds', keys, {'merchant_code': merchant_code, 'merchant_id': merchant_id})
            if not r:
                self.logger.info("商户utr补单 无此商户订单：{code}，商户：{merchant_id}".format(code=merchant_code, merchant_id=merchant_id))
                return await self.json_response(msg[10016])
            code = r['code']
            if r['utr'] and not is_robot:
                self.logger.info("商户utr补单 已存在utr：{code}，商户：{merchant_id}".format(code=merchant_code, merchant_id=merchant_id))

            # ==================== 变更开始：新增 UTR 并发/频率锁====================
            # 定义 UTR 锁的键名和过期时间
            UTR_LOCK_PREFIX = "utr_submission_lock:"
            UTR_LOCK_EXPIRY_SECONDS = 10 # 锁的有效期，10秒
            utr_lock_key = f'{UTR_LOCK_PREFIX}{utr}:{code}'
            # 先使用 setnx 尝试获取锁，如果成功，再使用 expire 设置过期时间
            got_utr_lock = await self.redis.setnx(utr_lock_key, 1)
            
            if got_utr_lock: # 只有当成功获取锁时，才设置过期时间
                await self.redis.expire(utr_lock_key, UTR_LOCK_EXPIRY_SECONDS)
                self.logger.info(f'订单：{merchant_code}，上传的卡密信息：{utr} 提交频率锁获取成功并设置过期时间。')
            else: # 未能获取锁 (键已存在且未过期)
                self.logger.warning(f'UTR {utr} 提交过于频繁或正在被其他请求处理，放弃操作。')
                self.logger.info(f"订单：{merchant_code}，上传的卡密信息：{utr} UTR submitted too frequently or already processing.")
                return await self.json_response(msg_en[10012]) # UTR 提交频率过高/处理中

            if trans_id:
                count_circle = 0
                while True:
                    busy_key = 'success_busy_{trans_id}'.format(trans_id=trans_id)
                    if await self.redis.setnx(busy_key, 1):
                        await self.redis.expire(busy_key, 10)
                        break
                    if count_circle >= 10:
                        self.logger.warning(
                            'trans_id:{trans_id}Do not operate frequently'.format(trans_id=trans_id))
                        res = dict(code=99, msg='Do not operate frequently')
                        return await self.json_response(msg_en[10012])
                    time.sleep(0.2)
                    count_circle = count_circle + 1

                sql_check_trans_id = """
                    SELECT code FROM orders_ds WHERE trans_id=%s AND code != %s LIMIT 1
                """
                # 这里的 _order[0]['id'] 是当前找到的订单的ID
                existing_order = await self.query(sql_check_trans_id, trans_id, code)
                
                # 打印即将执行的查询日志，包含SQL和参数
                self.logger.info(
                    f"新增：交易ID重复校验查询 | SQL: {sql_check_trans_id.strip()} | 参数: ({trans_id}, {merchant_code})"
                )
                
                # 如果查询结果不为空，则说明有其他订单已使用此交易ID
                if existing_order:
                    self.logger.warning(f"交易ID {trans_id} 已被其他订单使用。冲突订单号: {existing_order[0]['code']}")
                    # 返回一个错误提示
                    res = dict(code=99, msg='交易ID已使用')
                    return await self.json_response(msg_en[10029])
            # ==================== 变更结束 ====================

            # 判断需要转发补单接口的三方订单
            if r['third_party_name'] in ['ospay', 'ospay_upi']:
                # 如果有使用自有收银台的三方代收，需要向三方转发UTR
                self.logger.info(f'准备转发补单信息，订单号: {code}，UTR: {utr}，第三方平台: {r["third_party_name"]}')
                await self.ds_utr_to_third(code, r, utr)
                self.logger.info(f'补单转发完成，订单号: {code}')
                self.logger.info("商户utr补单 订单：{code}，商户utr：{utr}".format(code=code, utr=utr))

            if 'script' in utr or len(utr) < 10:
                return await self.json_response(msg_en[10004])
            # 开始回调
            if not await self.order_success_ds(code, utr, trans_id):
                # 删除操作的key，防止回调占用
                busy_key = 'order_success_busy_{code}'.format(code=code)
                await self.redis.delete(busy_key)
                sql = " update orders_ds set utr=%s,trans_id=%s,time_payed=now() where code=%s and utr is null"
                if not await self.execute(sql, utr, trans_id, code):
                    return await self.json_response(msg_en[10000])
                self.logger.info("商户utr补单 订单：{code}，商户utr补单 失败：{utr}".format(code=code, utr=utr))
                return await self.json_response(msg_en[10005])
            else:
                self.logger.info("商户utr补单 订单：{code}，商户utr补单成功：{utr}".format(code=code, utr=utr))
                return await self.json_response(msg_en[0])
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg_en[10005])

    async def ds_utr_to_third(self, code, order, utr):
        """
        向三方平台转发补单
        不返回参数影响原有补单逻辑
        """
        if order['third_party_name'] in ['ospay', 'ospay_upi']:
            # 查一下订单，获取token
            otherpay = await self.get_result_by_condition('otherpay', '*', {'name': order['third_party_name']})
            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['mer_id'] = otherpay['merchant_id']
            data_post['utr'] = utr
            data_post['order_id'] = code
            data_post['sign'] = SignatureAndVerification.md5_sign(data_post, otherpay['key'])
            # 发起 POST
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            }
            response = requests.post('https://ospay2.com/api/pay/ds/utr', data=data_post, headers=headers, timeout=(5, 5), verify=False)
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f"{code} 向第三方 {order['third_party_name']} 转发补单结果: {result}")
                if str(result.get("code")) == '0':
                    self.logger.info(f"{code} 已成功向三方 {order['third_party_name']} 转发补单")
                else:
                    self.logger.info(f"{code} 向三方 {order['third_party_name']} 转发补单失败 {response.text}")
            else:
                self.logger.info(f"{code} 向三方 {order['third_party_name']} 转发补单失败")

    # UTR完成(收款为上传者) 与pay/order.py card_num 一致
    async def order_success_ds(self, code, utr, trans_id_param=''):
        # 查找订单
        sql_select_order = """select * from orders_ds where code=%s and status in (-1,1,2) order by id desc limit 1"""
        # 查找码商
        sql_select_partner = """select partner_id,upi from payment where id=%s"""
        # 查询银行记录
        sql_select_bank_record = """select * from bank_record where utr=%s and amount=%s and callback=0 and trade_type=1 order by id desc limit 1"""
        # 修改银行记录
        sql_update_bank_record = """update bank_record set callback=1,order_code=%s where id=%s and callback=0"""
        # 商户代理费率
        sql_select_rates_merchant = """select mid as id,rate from (select @orgId mid, (select @orgId:=pid from merchant 
                                    where id=@orgId) pid from (select @orgId:=%s) vars,merchant) t inner join 
                                    merchant_channel m on m.merchant_id=mid and m.code=%s where m.merchant_id is not null  order by m.merchant_id desc"""
        # 码商代理费率
        sql_select_rates_partner = """select rates from channel where code=%s"""
        # 更新系统余额
        sql_update_payment = """update payment set sys_balance=sys_balance+%s where id=%s"""
        # 更新订单
        sql_update_order = """update orders_ds set earn_merchant=%s,earn_partner=%s,earn_system=%s,partner_id=%s,
                                        payment_id=%s,utr=%s,time_success=%s,status=3,upi=%s,trans_id=%s where code=%s and status in (-1,1,2) limit 1"""
        # 使用锁，5s使用自旋锁, 防止取消的同时回调
        count_circle = 0
        while True:
            busy_key = 'order_success_busy_{code}'.format(code=code)
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                break
            if count_circle >= 25:
                self.logger.warning('商户utr补单 utr:{utr}Do not operate frequently {code}'.format(utr=utr, code=code))
                return dict(code=99, msg='Do not operate frequently')
            time.sleep(0.2)
            count_circle = count_circle + 1

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 查询订单
                    if not await cur.execute(sql_select_order, code):
                        self.logger.error('商户utr补单 utr:{utr} 查不到相应的订单 {code}'.format(utr=utr, code=code))
                        return False
                    order = (await cur.fetchall())[0]
                    code = order['code']
                    amount = order['amount']
                    self.logger.error(f'order: {order}')
                    # 查询银行记录
                    if not await cur.execute(sql_select_bank_record, (utr, amount)):
                        self.logger.error('商户utr补单 utr:{utr} 查不到相应的bank_record {code}'.format(utr=utr, code=code))
                        return False
                    bank_record = (await cur.fetchall())[0]
                    payment_id = bank_record['payment_id']
                    trans_id = bank_record['trans_id']
                    self.logger.info(f"交易ID trans_id_param: {trans_id_param} , trans_id: {trans_id}")
                    if trans_id_param and trans_id and trans_id_param != trans_id:
                        self.logger.warning(f"交易ID trans_id_param: {trans_id_param} , trans_id: {trans_id}")
                        # 返回一个错误提示
                        # return await self.json_response(msg[10330])
                        await conn.rollback()
                        return False
                    
                    # ----------------- 交易ID重复校验逻辑 -----------------
                    if trans_id:
                        sql_check_trans_id = """
                            SELECT code FROM orders_ds WHERE trans_id=%s AND id != %s LIMIT 1
                        """
                        # 这里的 _order[0]['id'] 是当前找到的订单的ID
                        existing_order = await self.query(sql_check_trans_id, trans_id, order['id'])
                        
                        # 打印即将执行的查询日志，包含SQL和参数
                        self.logger.info(
                            f"新增：交易ID重复校验查询 | SQL: {sql_check_trans_id.strip()} | 参数: ({trans_id}, {order['id']})"
                        )
                        
                        # 如果查询结果不为空，则说明有其他订单已使用此交易ID
                        if existing_order:
                            self.logger.warning(f"交易ID {trans_id} 已被其他订单使用。冲突订单号: {existing_order[0]['code']}")
                            # # 返回一个错误提示
                            # return await self.json_response(msg[10330])
                            await conn.rollback()
                            return False
                    # ==================== 变更结束 ====================

                    # 修改银行记录
                    if not await cur.execute(sql_update_bank_record, (code, bank_record['id'])):
                        self.logger.error('商户utr补单 utr:{utr} update_bank_record 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    # 码商查询
                    if not await cur.execute(sql_select_partner, payment_id):
                        self.logger.error('商户utr补单 utr:{utr} 码商查询 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    _payment = (await cur.fetchall())[0]
                    partner_id = _payment['partner_id']

                    # 订单里的码和码商id比较银行流水里的判断  1207
                    self.logger.info("Checking order values: order['partner_id']={}, partner_id={}".format(order['partner_id'], partner_id))
                    self.logger.info("Checking payment values: order['payment_id']={}, payment_id={}".format(order['payment_id'], payment_id))

                    # 比较前确保数据一致性，转换为字符串并去除前后空格
                    if str(order['partner_id']).strip() != str(partner_id).strip() or str(order['payment_id']).strip() != str(payment_id).strip():
                        # 如果不匹配，记录警告日志并回滚事务
                        self.logger.warning(
                            '订单中的码和码商ID与银行流水中的信息不匹配 | UTR: {} | 订单信息: [码商ID: {}, 支付码: {}] | 输入值: [码商ID: {}, 支付码: {}]'
                            .format(utr, order['partner_id'], order['payment_id'], partner_id, payment_id)
                        )
                        await conn.rollback()
                        return False

                    # 退掉额外扣款
                    if bank_record['ew_code']:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, amount,  bank_record['ew_code'], 0):
                            self.logger.error('商户utr补单 utr:{utr} 退掉额外扣款 失败 {code}'.format(utr=utr, code=code))
                            return False
                    # 补扣码商(非自身订单、过期订单)
                    if not order['partner_id'] == partner_id or order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0):
                            self.logger.error('商户utr补单 utr:{utr} 补扣码商(非自身订单、过期订单) 失败 {code}'.format(utr=utr, code=code))
                            return False
                    # 非自身订单并且未过期退款给旧码商
                    if not order['partner_id'] == partner_id and not order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount, code, 0):
                            self.logger.error('商户utr补单 utr:{utr} 退款给码商 失败 {code}'.format(utr=utr, code=code))
                            return False
                    # 增加商户余额
                    if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'], code, 0):
                        self.logger.error('商户utr补单 utr:{utr} 增加商户余额 失败 {code}'.format(utr=utr, code=code))
                        return False
                    # 商户代理费用
                    earn_merchant = Decimal(0)
                    if order['earn_merchant'] > 0:
                        if not await cur.execute(sql_select_rates_merchant, (order['merchant_id'], order['channel_code'])):
                            await conn.rollback()
                            return False
                        merchant_rates = (await cur.fetchall())
                        for k, v in enumerate(merchant_rates):
                            if not k == 0 and v['rate']:
                                _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                                if _amount < 0:
                                    await conn.rollback()
                                    return False
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    return False
                                earn_merchant += _amount
                    # 增加码商佣金
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code, 3):
                        self.logger.error('商户utr补单 utr:{utr} 增加码商佣金 失败 {code}'.format(utr=utr, code=code))
                        return False
                    # 增加码商代理佣金
                    earn_partner = order['earn_partner_self']
                    if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                        return False
                    rates = (await cur.fetchall())[0]['rates'].split(',')
                    _partner_id = partner_id
                    for i in range(len(rates)):
                        partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                        if not partner['pid']:
                            break
                        _partner_id = partner['pid']
                        _amount = amount * Decimal(rates[i])
                        if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                            return False
                        earn_partner += _amount
                    # 系统盈利
                    earn_system = order['poundage'] - earn_merchant - earn_partner
                    if earn_system < 0:
                        self.logger.error('商户utr补单 utr:{utr} earn_system小于0 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    # 修改卡系统余额
                    if not await cur.execute(sql_update_payment, (amount, payment_id)):
                        self.logger.error('商户utr补单 utr:{utr} 修改卡系统余额 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    # 修改订单状态
                    time_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id, payment_id, utr, time_now, _payment['upi'], trans_id, code)):
                        self.logger.error('商户utr补单 utr:{utr} 修改订单状态 失败 {code}'.format(utr=utr, code=code))
                        await conn.rollback()
                        return False
                    self.logger.info('商户utr补单 更新订单状态%s' % cur._last_executed)
                except Exception as e:
                    self.logger.warning('商户utr补单 确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                    await conn.rollback()
                    return False
                else:
                    await conn.commit()
                    await self.redis.publish('order_notify', code)
                    return True

# 代付订单
class Pay_df(BaseHandler):
    async def post(self):
        try:
            request_data = {k: self.get_argument(k, "") for k in self.request.arguments}
            r = await self.get_cache_result('sys_info', ['status_payment_service'], {'id': 1})
            if not r['status_payment_service']:
                self.logger.info('pay 支付服务关闭，不再接受新订单: {data}'.format(data=str(request_data)))
                return await self.json_response(data=msg[10031])  # 支付服务关闭，不再接受新订单

            r = await self.get_cache_result('sys_info', ['status_jazzcash_payout_service'], {'id': 1})
            if not r['status_jazzcash_payout_service'] and is_jazzcash_payout_request(request_data):
                self.logger.info('JazzCash单独代付渠道关闭，不再接受新订单: {data}'.format(data=str(request_data)))
                return await self.json_response(data=msg[10010])  # 通道维护

            is_locked = await self.check_dsdf_lock()
            if is_locked:
                return await self.json_response(data=msg[10026])  # 锁定状态，返回相应的消息
            
            try:
                data = request_data
                self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
            except Exception:
                self.logger.exception('参数异常')
                return await self.json_response(msg[10001])
            ip = await self.get_ip()
            ref = self.request.headers['Referer'] if 'Referer' in self.request.headers else ''
            self.logger.info('pay_df 收到参数{data},referrer={ref},ip={ip}'.format(data=str(data), ref=ref, ip=ip))
            r = await self.get_cache_result('sys_info', ['status_df'], {"id": 1})
            if r['status_df'] == 0:
                return await self.json_response(data=msg[10022])
            if 'notice_api' not in data.keys():
                data['notice_api'] = None
                self.data_receive_filter_xss['notice_api'] = None

            valid_keys = ['mer_id', 'order_id', 'gateway', 'amount', 'account', 'user', 'bank_code', 'bank', 'notify',
                          'notice_api', 'sign']
            not_null_keys = ['mer_id', 'order_id', 'gateway', 'amount', 'account', 'user', 'bank_code', 'bank', 'sign']

            if not await self.is_valid_key(data, valid_keys):
                return await self.json_response(data=msg[10002])

            if await self.is_null(data, not_null_keys):
                return await self.json_response(data=msg[10003])

            self.logger.info("检查接收的数据和过滤后数据是否一致")
            if not await self.check_different_new(data, self.data_receive_filter_xss, valid_keys):
                self.logger.info('pay 参数非法{data}'.format(data=str(data)))
                return await self.json_response(data=msg[10002])

            merchant_id = int(data['mer_id'])
            amount = Decimal(data['amount'])
            if '.' in str(amount) and not set(str(amount).split('.')[1]) == {'0'}:
                return await self.json_response(data=msg[10024])
            merchant_code = data['order_id']

            # 获取并检查商户
            keys = {'status', 'mc_key', 'status', 'balance', 'fee_df', 'rate_df', 'pid', 'ip_df', 'status_df', 'amount_fixed', 'amount_fixed_max', 'target_payment'}
            merchant = await self.get_result_by_condition('merchant', keys, {'id': merchant_id})
            if not merchant:
                return await self.json_response(data=msg[10004])
            if merchant['status'] == 0:
                return await self.json_response(data=msg[10005])
            if merchant['status_df'] == 0:
                return await self.json_response(data=msg[10023])
            
            # region 检查商户固定金额是否有效
            amount_fixed_min = merchant.get('amount_fixed')
            amount_fixed_min = 0 if amount_fixed_min is None else amount_fixed_min
            
            amount_fixed_max = merchant.get('amount_fixed_max')
            amount_fixed_max = 0 if amount_fixed_max is None else amount_fixed_max
            
            # if amount < merchant['amount_fixed']:
            #     return await self.json_response(data=msg[10011])
            # 记录输入的金额和商户的固定金额
            self.logger.info("检查金额逻辑: 输入金额: %s, 商户限制金额: %s - %s", amount, amount_fixed_min, amount_fixed_max)
            
            if amount_fixed_min <= 0:
                self.logger.info("商户最小限制金额小于等于0，不参与判断.")
            else:
                # 检查逻辑
                if amount < amount_fixed_min:
                    self.logger.warning("金额小于商户最小限制金额: %s < %s", amount, amount_fixed_min)
                    return await self.json_response(data=msg[10011])
                else:
                    self.logger.info("金额大于或等于商户最小限制金额: %s >= %s", amount, amount_fixed_min)
            
            if amount_fixed_max <= 0:
                self.logger.info("商户最大限制金额小于等于0，不参与判断.")
            else:
                # 检查逻辑
                if amount > amount_fixed_max:
                    self.logger.warning("金额小于商户最大限制金额: %s < %s", amount, amount_fixed_max)
                    return await self.json_response(data=msg[10011])
                else:
                    self.logger.info("金额小于或等于商户最大限制金额: %s >= %s", amount, amount_fixed_max)
            # endregion
            
            # 检查ip
            merchant['ip_df'] = merchant['ip_df'] if merchant['ip_df'] else ''
            ips = [_ip.strip() for _ip in merchant['ip_df'].split(',') if _ip]
            if not ip in ["127.0.0.1", "::1"] and (not merchant['ip_df'] or not ip in ips):
                return await self.json_response(data=msg[10000])

            # 验签
            sign_data = data
            if not SignatureAndVerification.md5_verify(sign_data, sign_data['sign'], merchant['mc_key']):
                return await self.json_response(msg[10006])

            # 检查IFSC
            ifsc = data['bank_code']
            if not await self.query("""select * from bank_ifsc where ifsc=%s limit 1""", ifsc):
                try:
                    url = "https://ifsc.razorpay.com/{}".format(ifsc)
                    r = requests.get(url, timeout=(5, 5), verify=False)
                    if r.text == '"Not Found"':
                        return await self.json_response(msg[10017])
                except Exception:
                    return await self.json_response(msg[10017])

            # 检查商户费率
            if not merchant['rate_df'] and not merchant['fee_df']:
                return await self.json_response(data=msg[10013])
            # 检查商户余额
            poundage = amount * merchant['rate_df'] + merchant['fee_df']
            if merchant['balance'] < amount + poundage:
                return await self.json_response(msg[10015])
            # 检查所有上级费率并计算代理费用
            earn_merchant = Decimal(0)
            if merchant['pid']:
                sql = """select id,rate_df from 
                        (select 
                            @orgId id,
                            (select rate_df from merchant where id = @orgId) rate_df,
                            (select @orgId := pid from merchant where id = @orgId) pid
                        from (select @orgId := %s) vars,merchant) t where id is not null order by pid desc"""
                merchant_prates = await self.query(sql, merchant_id)
                if not merchant_prates:
                    return await self.json_response(data=msg[10013])
                merchant_prate = Decimal(0)
                for k, v in enumerate(merchant_prates):
                    if v['rate_df'] < 0 or (k > 0 and v['rate_df'] > merchant_prates[k - 1]['rate_df']):
                        return await self.json_response(data=msg[10013])
                    merchant_prate = Decimal(v['rate_df'])
                earn_merchant = amount * (merchant['rate_df'] - merchant_prate)
                if earn_merchant < 0:
                    return await self.json_response(data=msg[10013])
            # 码商盈利
            rate_df = (await self.get_cache_result('sys_info', ['rate_df']))['rate_df']
            earn_partner_self = rate_df * amount

            # 系统盈利
            earn_system = poundage - earn_merchant - earn_partner_self
            if earn_system <= Decimal(0):
                return await self.json_response(data=msg[10013])
            # 检查订单重复
            if await self.get_result_by_condition('orders_df', ['id'], {'merchant_code': merchant_code}):
                return await self.json_response(data=msg[10014])
            # 生成订单
            order_data = dict()
            order_data['code'] = await self.create_order_code('F')  # 订单号
            order_data['amount'] = amount  # 金额
            order_data['poundage'] = poundage  # 手续费
            order_data['realpay'] = amount + poundage  # 结算金
            order_data['merchant_id'] = merchant_id  # 商户ID
            order_data['merchant_code'] = merchant_code  # 商户订单号
            order_data['merchant_rate'] = merchant['rate_df']  # 商户费率
            order_data['earn_merchant'] = earn_merchant  # 商户代理盈利
            order_data['earn_partner_self'] = earn_partner_self  # 码商盈利
            order_data['earn_system'] = earn_system  # 系统盈利
            order_data['ifsc'] = data['bank_code']
            order_data['payment_account'] = data['account']
            order_data['payment_name'] = data['user']
            order_data['payment_bank'] = data['bank']
            order_data['notify'] = data['notify']  # 通知地址
            order_data['target_payment'] = merchant['target_payment']  # 专卡专户
            
            # 检查自动代付开关状态并设置payout_type字段
            try:
                emergency_stop = await self.redis.get("easypaisa_emergency_stop")
                # 如果紧急停止为"0"或未设置，启用自动代付(payout_type=1)，否则设为0(手动代付)
                order_data['payout_type'] = 1 if (emergency_stop is None or emergency_stop == b"0" or emergency_stop == "0") else 0
                self.logger.info(f"紧急停止状态: {emergency_stop}, payout_type: {order_data['payout_type']}")
            except Exception as e:
                # 如果Redis查询失败，默认设为0(手动代付)
                order_data['payout_type'] = 0
                self.logger.warning(f"获取紧急停止状态失败，默认设置为手动代付: {e}")
            
            # 扣除商户余额并创建订单
            async with self.application.db.acquire() as conn:
                async with conn.cursor(DictCursor) as cur:
                    try:
                        # 扣除商户余额
                        if not await self.change_balance(conn, cur, 'merchant', merchant_id, -order_data['realpay'],order_data['code'], 1, None, merchant_code):
                            await conn.rollback()
                            return await self.json_response(data=msg[10014])
                        # 生成订单
                        keys = ', '.join(order_data.keys())
                        values = ', '.join(['%s'] * len(order_data))
                        sql = "insert into {table} ({keys}) values ({vals})".format(table="orders_df", keys=keys, vals=values)
                        if not await cur.execute(sql, tuple(order_data.values())):
                            await conn.rollback()
                            return await self.json_response(data=msg[10014])
                    except Exception as e:
                        self.logger.warning(
                            '下单失败,merchant_id={merchant_id},非法数据={e}'.format(merchant_id=merchant_id, e=e))
                        await conn.rollback()
                        return await self.json_response(data=msg[10014])
                    else:
                        await conn.commit()
                        return await self.json_response(({'code': 0, 'massage': '下单成功', 'order_code': order_data['code'], 'amount': amount}))
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(data=msg[10014])

    # in_mins 分钟内到达订单限制，就限制下单 mins 分钟
    async def order_gateway_busy(self, gateway, merchant_id, orders, in_mins, mins):
        mins_ago = datetime.datetime.now() - datetime.timedelta(minutes=in_mins)
        sql_allow = "select count(*) as trx from orders_ds where time_create > %s and status in (0,1,2) and gateway=%s"
        ret = await self.query(sql_allow, mins_ago, gateway)
        if not ret:
            return True
        if ret[0]['trx'] > orders:
            self.logger.info(
                '通道-{gateway}-{in_mins}分钟内到达限制单量{orders}，限制提单时间{mins}分钟,merchant_id={merchant_id}'.format(
                    gateway=gateway, in_mins=in_mins, orders=orders, mins=mins,
                    merchant_id=merchant_id))
            busy_key = 'order_gateway_busy_{gateway}'.format(gateway=gateway)
            await self.redis.set(key=busy_key, value=1, expire=mins * 60)
            return False
        return True
