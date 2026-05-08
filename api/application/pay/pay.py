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


# 兼容旧 import 路径，后续逐步迁移后删除
from application.pay.raast_qr import (
    crc16_ccitt, encode_tlv, build_payload, build_payload_amount,
    _format_timestamp, _format_amount_raast, _fmt_len,
)
from application.pay.collection import (
    _to_int, _collection_dispatch_extra_sql_condition,
    _is_collection_dispatch_enabled, _is_collection_payment_online,
    _mysql_collection_ids, _collection_online_payment_ids,
    _is_collection_payment_online_by_id, _manual_lock_update_fields,
)
from application.pay.dispatch import (
    build_ds_candidate_sql, _parse_payment_id_list,
    push_order, fetch_ds_candidate_rows, fetch_mysql_dedicated_payment_ids,
    update_target_in_redis,
)
from application.pay.decimal_amount import (
    generate_unique_decimal_amount, cleanup_decimal_callback_on_success,
)
from application.pay.payout import Pay_df
from application.pay.utr_callback import ds_utr

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

            # Step 1: Validate request
            validated = await self._validate_request()
            if validated is None:
                return

            data = validated['data']
            merchant_id = validated['merchant_id']
            gateway = validated['gateway']
            amount = validated['amount']
            merchant_code = validated['merchant_code']
            user_id = validated['user_id']

            # Step 2: Check merchant
            merchant_result = await self._check_merchant(merchant_id, data)
            if merchant_result is None:
                return

            merchant = merchant_result['merchant']

            # Step 3: Check channel and fees
            channel_result = await self._check_channel_and_fees(merchant_id, gateway, amount, merchant, merchant_code)
            if channel_result is None:
                return

            channel = channel_result['channel']
            merchant_channel = channel_result['merchant_channel']
            merchant_rate = channel_result['merchant_rate']
            earn_merchant = channel_result['earn_merchant']

            # Step 4: Create order
            order_result = await self._create_order(data, merchant_rate, earn_merchant, gateway, merchant_id, merchant_code, amount, user_id)
            if order_result is None:
                return

            order_data = order_result['order_data']

            # Step 5: Dispatch and respond
            return await self._dispatch_and_respond(order_data, merchant, merchant_channel, channel, gateway, merchant_id, amount)

        except Exception as e:
             # 记录详细的错误日志，包括异常类型、异常信息和堆栈跟踪
            self.logger.exception(f"错误发生在 {datetime.datetime.now()}，异常类型: {type(e).__name__}，异常信息: {str(e)}")
            # 记录堆栈信息，帮助调试
            stack_trace = traceback.format_exc()  # 获取完整的堆栈信息
            self.logger.error(f"堆栈跟踪:\n{stack_trace}")
            return await self.json_response(data=msg[10014])

    async def _validate_request(self):
        """Parameter validation + XSS filtering + signature verification."""
        try:
            data = {k: self.get_argument(k) for k in self.request.arguments}
            self.data_receive_filter_xss = {k: await self.get_escaped_argument(k) for k in self.request.arguments}
        except Exception:
            self.logger.exception('参数异常')
            await self.json_response(msg[10001])
            return None
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
            await self.json_response(data=msg[10002])
            return None

        self.logger.info(f"检查必填字段是否为空: {not_null_keys}")
        if await self.is_null(data, not_null_keys):
            self.logger.warning("存在空值的必填字段")
            await self.json_response(data=msg[10003])
            return None

        self.logger.info("检查接收的数据和过滤后数据是否一致")
        if not await self.check_different_new(data, self.data_receive_filter_xss, valid_keys):
            self.logger.info('pay 参数非法{data}'.format(data=str(data)))
            await self.json_response(data=msg[10002])
            return None

        try:
            merchant_id = int(data['mer_id'])
        except (ValueError, TypeError):
            self.logger.warning(f"invalid merchant id format: {data['mer_id']}")
            await self.json_response(data=msg[10002])
            return None
        self.logger.info(f"解析得到码商 ID: {merchant_id}")

        try:
            gateway = int(data['gateway'])
        except (ValueError, TypeError):
            self.logger.warning(f"invalid gateway format {data['gateway']}")
            await self.json_response(data=msg[10002])
            return None
        self.logger.info(f"解析得到通道编码: {gateway}")

        try:
            amount = Decimal(data['amount']).quantize(Decimal('.01'), rounding=ROUND_DOWN)
        except (InvalidOperation, ValueError, TypeError):
            self.logger.warning(f"invalid amount format: {data['amount']}")
            await self.json_response(data=msg[10002])
            return None
        self.logger.info(f"解析得到订单金额: {amount}")

        merchant_code = data['order_id']
        self.logger.info(f"解析得到订单号: {merchant_code}")

        user_id = data['user_id'] if 'user_id' in data else ''

        return {
            'data': data,
            'merchant_id': merchant_id,
            'gateway': gateway,
            'amount': amount,
            'merchant_code': merchant_code,
            'user_id': user_id,
        }

    async def _check_merchant(self, merchant_id, data):
        """Merchant status + blacklist + user_id blacklist checks."""
        keys = {'status', 'mc_key', 'pid', 'target_payment', 'return_url', 'status', 'ds_on', 'ds_black_ips', 'ds_userid_on', 'ds_black_userids', 'decimal_amt_flag', 'notify_callback_type'}
        self.logger.info(f"查询商户信息，ID: {merchant_id}")
        merchant = await self.get_result_by_condition('merchant', keys, {'id': merchant_id})

        if not merchant:
            self.logger.warning(f"商户 ID {merchant_id} 不存在")
            await self.json_response(data=msg[10004])
            return None
        if merchant['status'] == 0:
            self.logger.warning(f"商户 ID {merchant_id} 已被禁用")
            await self.json_response(data=msg[10005])
            return None

        self.logger.info(f"商户 ID {merchant_id} 的代收启用标志: {merchant['ds_on']}")

        ds_black_ips = merchant['ds_black_ips']
        self.logger.info(f"商户 ID {merchant_id} 的黑名单 IP 列表: {ds_black_ips}")
        blacklist = set(ds_black_ips.split(',')) if ds_black_ips else set()
        self.logger.info(f"解析后的黑名单集合: {blacklist}")
        self.logger.info(f"当前玩家 IP: {data['player_ip']}")
        if (not data['player_ip'] or data['player_ip'] in blacklist) and merchant['ds_on'] == 0:
            self.logger.warning(f"商户 ID {merchant_id} 代收黑名单 IP 封禁: {data['player_ip']}")
            await self.json_response(data=msg[10027])
            return None

        self.logger.info(f"商户 ID {merchant_id} 的代收user_id启用标志: {merchant['ds_userid_on']}")

        ds_black_userids = merchant['ds_black_userids']
        self.logger.info(f"商户 ID {merchant_id} 的黑名单 user_id 列表: {ds_black_userids}")
        ds_black_userids = set(ds_black_userids.split(',')) if ds_black_userids else set()
        self.logger.info(f"解析后的user_id黑名单集合: {ds_black_userids}")
        self.logger.info(f"当前玩家 user_id: {data['user_id']}")
        if (not data['user_id'] or data['user_id'] in ds_black_userids) and merchant['ds_userid_on'] == 0:
            self.logger.warning(f"商户 ID {merchant_id} 代收黑名单 user_id 封禁: {data['user_id']}")
            await self.json_response(data=msg[10028])
            return None

        # 验签
        self.logger.info("开始进行签名验证")
        sign_data = data.copy()

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
            await self.json_response(msg[10006])
            return None

        self.logger.info("签名验证成功")

        return {'merchant': merchant}

    async def _check_channel_and_fees(self, merchant_id, gateway, amount, merchant, merchant_code):
        """Channel validation + fee calculation."""
        keys = ['code', 'rate', 'rates', 'fixed', 'amount_fixed', 'amount_min', 'amount_max', 'status', 'decimal_callback_enabled', 'decimal_min', 'decimal_max']
        self.logger.info(f"查询渠道信息，条件: {keys}, 网关: {gateway}")
        channel = await self.get_result_by_condition('channel', keys, {'code': gateway})
        if not channel:
            self.logger.warning("未找到对应的渠道信息")
            await self.json_response(data=msg[10009])
            return None

        if channel['status'] == 0:
            self.logger.warning(f"渠道 {gateway} 状态为禁用，无法继续操作")
            await self.json_response(data=msg[10010])
            return None

        self.logger.info(f"检查金额: {amount} 是否符合要求")
        if not await self.check_amount(amount, channel):
            self.logger.warning("金额不符合要求")
            await self.json_response(msg[10011])
            return None

        self.logger.info(f"获取商户渠道费率，商户ID: {merchant_id}, 网关: {gateway}")
        merchant_channel = await self.get_result_by_condition('merchant_channel',
                                                              ['rate', 'status', 'otherpay', 'is_force'],
                                                              {'merchant_id': merchant_id,
                                                               'code': gateway, 'status': 1})
        if not merchant_channel:
            self.logger.warning(f"未找到商户 {merchant_id} 的渠道费率")
            await self.json_response(data=msg[10012])
            return None

        merchant_rate = merchant_channel['rate']
        self.logger.info(f"商户费率为: {merchant_rate}")
        if merchant_rate < 0:
            self.logger.warning(f"商户费率为负值: {merchant_rate}")
            await self.json_response(data=msg[10013])
            return None

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
                await self.json_response(data=msg[10013])
                return None

            merchant_prate = Decimal(0)
            for i, v in enumerate(merchant_prates):
                if v['rate'] < 0 or (i > 0 and v['rate'] > merchant_prates[i - 1]['rate']):
                    self.logger.warning(f"上级费率存在错误，费率: {v['rate']}")
                    await self.json_response(data=msg[10013])
                    return None
                merchant_prate = Decimal(v['rate'])

            earn_merchant = amount * (merchant_rate - merchant_prate)
            self.logger.info(f"商户代理盈利: {earn_merchant}")
            if earn_merchant < 0:
                self.logger.warning("商户代理盈利为负值，无法继续操作")
                await self.json_response(data=msg[10013])
                return None

        # 检查订单重复
        self.logger.info(f"检查商户订单号 {merchant_code} 是否重复")
        if await self.get_result_by_condition('orders_ds', ['id'], {'merchant_code': merchant_code}):
            self.logger.warning(f"订单号 {merchant_code} 已存在，重复订单")
            await self.json_response(data=msg[10014])
            return None

        return {
            'channel': channel,
            'merchant_channel': merchant_channel,
            'merchant_rate': merchant_rate,
            'earn_merchant': earn_merchant,
        }

    async def _create_order(self, data, merchant_rate, earn_merchant, gateway, merchant_id, merchant_code, amount, user_id):
        """Order generation (insert into orders_ds)."""
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
        if not await self.create_result('orders_ds', order_data):
            self.logger.warning(f"订单 {order_data['code']} 创建失败")
            await self.json_response(data=msg[10014])
            return None

        return {'order_data': order_data}

    async def generate_qr_code(self, payment_id: str, account_id: str, amount: str, logger=None):
        """为 EasyPaisa 1010 生成带金额与 7 分钟过期时间的 Raast 动态 QR。"""
        log = logger or self.logger

        if not account_id or not amount:
            log.error(f"无效的输入数据：account_id={account_id}, amount={amount}")
            return None

        log.info(f'generate_qr_code====================1===========account_id={account_id}, amount={amount}===============')
        account_iban = ''
        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                sql_select_payment = """
                    SELECT account_iban FROM payment WHERE id = %s LIMIT 1
                """
                await cur.execute(sql_select_payment, (payment_id,))
                payment_info = await cur.fetchone()
                log.info(f'payment_info======={payment_info}=============')
                if not payment_info:
                    log.error(f"未在数据库中找到 ID 为 {payment_id} 的有效payment。")
                    return None

                account_iban = payment_info.get('account_iban')

        if not account_iban:
            log.error(f"payment_id={payment_id} 缺少 account_iban，无法生成 EasyPaisa QR。")
            return None

        log.info(f'generate_qr_code======account_iban======={account_iban}=======')
        expires_at = int(time.time()) + 7 * 60
        qr = build_payload_amount(iban=account_iban, amount=amount, timestamp=expires_at)
        log.info(f'qr======取得二维码数据=============={qr}')
        return qr

    async def _dispatch_and_respond(self, order_data, merchant, merchant_channel, channel, gateway, merchant_id, amount):
        """Dispatch (call push_order) + decimal amount + build response."""
        order_pay_url = ''
        self.logger.info(f"准备开始派单，订单号: {order_data['code']}")
        order_token = await self.token_generate(order_data['code'])  # 订单时效token
        use_decimal_callback = False
        original_amount = amount
        push_success = False  # 标记是否成功派单
        upi = ""
        # 调用 push_order 并将返回的字典赋给一个变量
        push_result = await push_order(self, order_data, merchant['target_payment'])

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
            channel_enabled = True
            self.logger.info(f'通道 decimal_callback_enabled 设置为: {channel_enabled}')

            if push_success and channel_enabled:
                use_decimal_callback = True

                self.logger.info(f'通道 {gateway} 启用小数点回调功能')
                self.logger.info(f'通道 {gateway} 和商户 {merchant_id} 都启用小数点回调功能')

                decimal_min = float(channel.get('decimal_min', 0.01))
                decimal_max = float(channel.get('decimal_max', 0.99))

                # 判断方向：正区间 上浮；负区间 下浮；否则报错
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
                new_amount = await generate_unique_decimal_amount(
                    self, original_amount, offset_min, offset_max, gateway, order_data['code'], payment_id
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
            return await self.json_response(result)

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

