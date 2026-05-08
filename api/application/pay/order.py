import json
import time
import traceback
from datetime import datetime, timedelta
from decimal import Decimal

import requests
import simplejson
from aiomysql import DictCursor

from application.base import BaseHandler
from application.cache.redis_order_manager import RedisOrderManager
from application.message import msg, msg_en
from urllib.parse import urlsplit

from application.utils import StringUtils
from application.websocket import callback
from application.jazzcash_gateway import build_form_body
from application.sign import SignatureAndVerification
import re
import urllib.parse
import threading

import uuid
import aiohttp

import asyncio
from config import get_config

conf = get_config()

class Order(BaseHandler):
    # 支付通道与模板映射表
    TEMPLATE_MAPPING = {
        '789pay': {
            1001: 1005,
            1002: 1006,
            1003: 1007,
            1004: 1008,
            1005: 10061,
        },
        'ospay': {
            1001: 1001,
            1002: 1002,
            1003: 1003,
            1004: 1004,
            1005: 10021,
        },
        'pakistanpay': {
            1001: 1010,
            1002: 1012,
            1003: 1013,
            1010: 10100,
        },
        # 可继续扩展更多支付通道...
    }

    # 获取模板编号函数
    def get_template_code(self, channel_code, current_pay):
        return self.TEMPLATE_MAPPING.get(current_pay, {}).get(channel_code, channel_code)

    async def get(self, token=None):
        try:
            current_pay = conf['current_pay']
            if not token:
                return await self.json_response(msg_en[10000])
            code = await self.token_decode(token)

            if code in [10016, 10017]:
                return await self.json_response(msg[code])
            ip = await self.get_ip()
            if ip:
                await self.update_result('orders_ds', {'player_ip': ip}, {'code': code})
            order_info = await self.get_result_by_condition('orders_ds',
                                                            ['code', 'channel_code', 'amount', 'auth_code', 'payment_id', 'auth_code', 'callback', 'third_party_name', 'merchant_id', 'time_create', 'original_amount', 'utr'],
                                                            {'code': code})
            
            
            self.logger.info(f"[Token二次校验] 开始处理 token 前 12 位: {token[:12] if token else 'None'}")

            # 1. 先拿到 channel_code
            channel_code = order_info['channel_code']
            self.logger.info(f"[Token二次校验] 订单 channel_code = {channel_code}")

            # 2. 根据通道决定最终的有效期
            max_age = 180 if channel_code == 1003 else 300
            self.logger.info(f"[Token二次校验] 本次严格校验使用的 max_age = {max_age} 秒 "
                             f"({'3 分钟（1003专用）' if max_age == 180 else '5 分钟（普通通道）'})")

            # 3. 用正确的 max_age 重新校验一次 token
            self.logger.info(f"[Token二次校验] 正在使用 max_age={max_age} 秒 重新解码 token...")
            code = await self.token_decode(token, max_age=max_age)

            # 4. 判断解码结果
            if isinstance(code, int):
                if code == 10016:
                    self.logger.warning(f"[Token二次校验] token 已过期！channel={channel_code} "
                                        f"max_age={max_age}秒 触发 SignatureExpired")
                elif code == 10017:
                    self.logger.error(f"[Token二次校验] token 解析异常code=10017")
                else:
                    self.logger.warning(f"[Token二次校验] token 解码返回错误码: {code}")

                return await self.json_response(msg[code])
            else:
                self.logger.info(f"[Token二次校验] 成功！最终解码得到的 order_code = {code}")

            upi = await self.get_result_by_condition('payment', ['account_type', 'account_iban', 'upi', 'phone', 'name', 'ifsc', 'account', 'bank_type', 'account_accno'], {'id': order_info['payment_id']})
            bank = await self.get_result_by_condition('bank_type', ['name'], {'id': upi.get('bank_type', '')})
            # 根据订单的 channel_code 查找 channel 表中的 is_show_qr 字段
            channel_info = await self.get_result_by_condition('channel', ['is_show_qr'], {'code': order_info['channel_code']})

            order_info['token'] = token
            order_info['upi'] = upi.get('upi')
            qr_show = 1
            logo = ''
            color = ''
            name = upi.get('name')
            ifsc = upi.get('ifsc')
            account = upi.get('account')
            account_accno = upi.get('account_accno')
            phone = upi.get('phone')
            account_iban = upi.get('account_iban')
            # 账户类型定义：10=钱包，20=银行账户
            account_type = str(upi.get('account_type', ''))
            self.logger.info(f'--- 逻辑开始 --- 收到 account_type: {account_type}')
            # 逻辑判断：优先判断明确的 account_type
            if str(upi.get('bank_type')) == '97':
                if account_type == '10':
                    self.logger.info(f"5. 订单号 {code}: 检测到类型为 10 (Wallet/钱包)")
                    account_iban = phone
                    self.logger.info(f"6. 订单号 {code}: [钱包模式] 最终显示: '{account_iban}' (来源: phone)")

                elif account_type == '20':
                    self.logger.info(f"5. 订单号 {code}: 检测到类型为 20 (Bank Account/银行账户)")
                    account_iban = account_accno
                    self.logger.info(f"6. 订单号 {code}: [银行模式] 最终显示: '{account_iban}' (来源: accno)")

                else:
                    # 兜底逻辑：如果 account_type 为空或为其他值，再尝试用 account_name 关键字匹配
                    self.logger.warning(f"5. 订单号 {code}: 未知类型 {account_type}，尝试模糊匹配 account_name")
                    # 如果是 EP，取 account_iban 后面的 8 位
                    iban = upi.get('account_iban') or ""
                    account_iban = iban[-8:] if len(iban) >= 8 else iban
                    self.logger.info(f"6. 订单号 {code}: [兜底模式] 最终显示: '{account_iban}'")
                self.logger.info(f"订单号 {code}: --- 逻辑结束 --- 最终设定 account_iban 为: {account_iban}")
            is_alipay = ''
            order_info['logo'] = logo
            order_info['color'] = color
            order_info['name'] = name
            order_info['is_alipay'] = is_alipay
            order_info['qr_show'] = qr_show
            order_info['ifsc'] = ifsc
            order_info['account'] = account
            order_info['account_iban'] = account_iban
            order_info['account_accno'] = upi.get('account_accno')
            order_info['phone'] = phone
            order_info['qr_show'] = qr_show
            order_info['bank_name'] = bank.get('name')

            call_up = await self.redis.get('call_up_id')
            order_info['call_up'] = 1 if order_info['channel_code'] == 1002 else 0
            if call_up:
                call_up = call_up.split(',')
                if str(order_info['merchant_id']) in call_up:
                    order_info['call_up'] = 1

            # 根据具体的商户号来返回是否需要输入utr,使用逗号标识
            utr_no_input = await self.redis.get('utr_no_input_id')
            order_info['utr_no_input'] = 0

            # 检查是否是小数点回调订单，如果是则隐藏UTR输入框
            if order_info.get('original_amount'):
                self.logger.info(f"检测到小数点回调订单：{code}，原始金额：{order_info['original_amount']}，小数点金额：{order_info['amount']}，自动隐藏UTR输入框")
                order_info['utr_no_input'] = 1
            elif utr_no_input:
                utr_no_input = utr_no_input.split(',')
                if str(order_info['merchant_id']) in utr_no_input:
                    order_info['utr_no_input'] = 1

            # 根据具体的商户号来返回是否需要copy upi,使用逗号标识
            order_info['upi_copy'] = 1
            # upi_copy = await self.redis.get('upi_copy_id')
            # order_info['upi_copy'] = 0
            # if upi_copy:
            #     upi_copy = upi_copy.split(',')
            #     if str(order_info['merchant_id']) in upi_copy:
            #         order_info['upi_copy'] = 1

            # 根据具体的商户号来返回是否需要显示二维码,使用逗号标识
            qrcode_not_displayed = await self.redis.get('qrcode_not_displayed_id')
            order_info['qrcode_not_displayed'] = 0
            if qrcode_not_displayed:
                qrcode_not_displayed = qrcode_not_displayed.split(',')
                if str(order_info['merchant_id']) in qrcode_not_displayed:
                    order_info['qrcode_not_displayed'] = 1

        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg_en[10000])
        else:
            time_with_7_minutes = order_info['time_create'] + timedelta(minutes=7)
            # 获取当前时间
            now = datetime.now()
            # 计算与当前时间的差值（秒）
            time_diff = int((time_with_7_minutes - now).total_seconds())
            order_info['time_diff'] = time_diff
            channel_code = order_info['channel_code']
            template_code = self.get_template_code(channel_code, current_pay)

            if channel_code == 1002:
                # easypay SOAP 代收：渲染手机号输入收银台页面
                if order_info.get('third_party_name') == 'easypay':
                    self.logger.info(f'[easypay] 渲染 SOAP 收银台页面, code={code}')
                    await self.render('easypay_soap_cashier.html', **order_info)
                    return

                # PayFast 代收：从 Redis 读取表单数据，自动 POST 到 PayFast 收银台
                if order_info.get('third_party_name') == 'payfast':
                    redis_key = f'payfast_redirect_{code}'
                    raw = await self.redis.get(redis_key)
                    if not raw:
                        self.set_status(410)
                        return self.write('Payment link expired')
                    form_data = json.loads(raw)
                    pay_url = form_data.pop('PAY_URL')
                    inputs = ''.join(f'<input type="hidden" name="{k}" value="{v}" />' for k, v in form_data.items())
                    html_content = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Redirecting to PayFast...</title></head>
<body>
<p style="text-align:center;margin-top:100px;font-size:18px;">Redirecting to PayFast, please wait...</p>
<form id="pf" method="post" action="{pay_url}">{inputs}</form>
<script>document.getElementById('pf').submit();</script>
</body></html>'''
                    self.set_header('Content-Type', 'text/html; charset=utf-8')
                    return self.write(html_content)

                order_info['upi_params_general_url_encode'] = await self._upi_params_general_handler(order_info['upi'],
                                                                                                     order_info)
                order_info['upi_params_paytm_url_encode'] = await self._upi_params_paytm_handler(order_info['upi'],
                                                                                                 order_info)
                order_info['sec_remains'] = 59
                self.logger.info('1002=================',  bank.get('name'))
                await self.render(f'order_india.{template_code}.html', **order_info)
            
            if channel_code == 1005:
                order_info['upi_params_general_url_encode'] = await self._upi_params_general_handler(order_info['upi'],
                                                                                                     order_info)
                order_info['upi_params_paytm_url_encode'] = await self._upi_params_paytm_handler(order_info['upi'],
                                                                                                 order_info)
                
                await self.render(f'order_india.{template_code}.html', **order_info)

            elif channel_code == 1001:
                if order_info['third_party_name'] in ['snakepay', 'TataPay', 'TataPay_t100037']:
                    order_ds_third_qr = await self.redis.get('order_ds_third_qr_{}'.format(code))
                    qr_url_info_dict = {param.split('=')[0]: param.split('=')[1] for param in order_ds_third_qr.split('&')}
                    order_info['upi'] = qr_url_info_dict.get('pa')
                    self.logger.info(f'{order_info['channel_code']} {order_info['third_party_name']}获取到第三方qr信息: {order_ds_third_qr} order_ds_third_qr_{code}')
                    order_info['upi_params_general_url_encode'] = order_ds_third_qr
                elif order_info['third_party_name'] in ['hkpay']:
                    order_ds_third_qr = await self.redis.get('order_ds_third_qr_{}'.format(code))
                    match = re.search(r'pa=([^&]+)', order_ds_third_qr)
                    if match:
                        order_info['upi'] = match.group(1)
                    self.logger.info(f'{order_info['channel_code']} {order_info['third_party_name']}获取到第三方qr信息: {order_ds_third_qr}')
                    order_info['upi_params_general_url_encode'] = order_ds_third_qr
                else:
                    order_info['upi_params_general_url_encode'] = await self._upi_params_general_handler(order_info['upi'],
                                                                                                     order_info)
                order_info['upi_params_paytm_url_encode'] = await self._upi_params_paytm_handler(order_info['upi'],
                                                                                                 order_info)
                # set 99999999 avoid all hidden when this value is null
                min_amount_hidden_qrcode = Decimal(await self.redis.get('min_amount_hidden_qrcode') or 99999999)
                order_info['is_hidden_qrcode'] = True if order_info['amount'] >= min_amount_hidden_qrcode else False
                order_ds_third_qr = await self.redis.get('order_ds_third_qr_{}'.format(code))
                order_info['upi'] = order_ds_third_qr
                order_info['is_show_qr'] = channel_info['is_show_qr']
                self.logger.info(f"code: {code}，upi：{order_info['upi']}")
                await self.render(f'order_india.{template_code}.html', **order_info)

            elif channel_code == 1010:
                order_ds_third_qr = await self.redis.get('order_ds_third_qr_{}'.format(code))
                if order_ds_third_qr:
                    order_info['upi'] = order_ds_third_qr
                order_info['ep_qr_payload'] = order_info.get('upi') or ''
                order_info['utr'] = order_info.get('utr') or ''
                order_info['is_show_qr'] = channel_info['is_show_qr']
                self.logger.info(f"1010 EP scan code: {code}，qr payload exists: {bool(order_info['ep_qr_payload'])}")
                await self.render(f'order_india.{template_code}.html', **order_info)

            elif channel_code == 1003:
                # PayFast 代收：从 Redis 读取表单数据，自动 POST 到 PayFast 收银台
                if order_info.get('third_party_name') == 'payfast':
                    redis_key = f'payfast_redirect_{code}'
                    raw = await self.redis.get(redis_key)
                    if not raw:
                        self.set_status(410)
                        return self.write('Payment link expired')
                    form_data = json.loads(raw)
                    pay_url = form_data.pop('PAY_URL')
                    inputs = ''.join(f'<input type="hidden" name="{k}" value="{v}" />' for k, v in form_data.items())
                    html_content = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Redirecting to PayFast...</title></head>
<body>
<p style="text-align:center;margin-top:100px;font-size:18px;">Redirecting to PayFast, please wait...</p>
<form id="pf" method="post" action="{pay_url}">{inputs}</form>
<script>document.getElementById('pf').submit();</script>
</body></html>'''
                    self.set_header('Content-Type', 'text/html; charset=utf-8')
                    return self.write(html_content)

                end_datetime = order_info['time_create'] + timedelta(minutes=10)
                order_info['end_timestamp'] = end_datetime.timestamp()
                order_info['sec_remains'] = 59
                self.logger.info(f'1003================={bank.get('name')}')
                await self.render(f'order_india.{template_code}.html', **order_info)

            elif channel_code == 1004:
                bank_name = order_info['bank_name']
                # print('bank_name', bank_name)
                # if bank_name == 'BOB BANK':  temporary delete 20241103
                if order_info['third_party_name'] in ['snakepay', 'TataPay', 'TataPay_t100037','qqpay']:
                    order_ds_third_qr = await self.redis.get('order_ds_third_qr_{}'.format(code))
                    qr_url_info_dict = {param.split('=')[0]: param.split('=')[1] for param in order_ds_third_qr.split('&')}
                    order_info['upi'] = qr_url_info_dict.get('pa')
                    self.logger.info(f'{order_info['channel_code']} {order_info['third_party_name']}获取到第三方qr信息: {order_ds_third_qr} order_ds_third_qr_{code}')
                    order_info['upi_params_general_url_encode'] = order_ds_third_qr
                    order_info['upi_params_paytm_url_encode'] = order_ds_third_qr + '&featuretype=money_transfer'
                elif order_info['third_party_name'] in ['hkpay']:
                    order_ds_third_qr = await self.redis.get('order_ds_third_qr_{}'.format(code))
                    match = re.search(r'pa=([^&]+)', order_ds_third_qr)
                    if match:
                        order_info['upi'] = match.group(1)
                    self.logger.info(f'{order_info['channel_code']} {order_info['third_party_name']}获取到第三方qr信息: {order_ds_third_qr}')
                    order_info['upi_params_general_url_encode'] = order_ds_third_qr
                    if order_ds_third_qr.endswith('featuretype=money_transfer'):  # ospay的码链接已经带有这个后缀了
                        order_info['upi_params_paytm_url_encode'] = order_ds_third_qr
                    else:
                        order_info['upi_params_paytm_url_encode'] = order_ds_third_qr + '&featuretype=money_transfer'
                else:
                    order_info['upi_params_general_url_encode'] = await self._upi_params_general_handler(order_info['upi'], order_info)
                    order_info['upi_params_paytm_url_encode'] = await self._upi_params_paytm_handler1004(order_info['upi'],
                                                                                                order_info)
                await self.render(f'order_india.{template_code}.html', **order_info)
                # else:
                #     return None  # 如果没有匹配的银行名称，可以返回 None 或其他默认值

    @staticmethod
    async def _upi_params_paytm_handler1004(upi, order_info):
        # 解析原始的 UPI 链接
        # upi = 'upi://pay?pa=saite82992@barodampay&pn=SAI%20TENT%20HOUSE&mc=&tn=Verified%20Merchant&am=&cu=INR&url=&mode=02&orgid=159012&mid=&msid=&mtid=&sign=MEUCIQDDeaJ7PRVR2RGV6hjNIVGwQEd8uCs5n3M0mPTFIaWacwIgKCW49vO8YnIAxaMTqDFDj9OUPWpRVc/DMxzfTBvA38Q='
        upi = order_info['upi']  # 从 order_info 中获取 upi 链接
        # print('upi=', upi)
        # print('net_trade_pw=', order_info['net_trade_pw'])
        parsed_url = urllib.parse.urlparse(upi)  # 解析 UPI URL
        # 将查询参数提取到字典中
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # 确保 mc、url、mid、msid、mtid 参数存在，且如果没有设置则赋空值
        empty_params = ['mc', 'url', 'mid', 'msid', 'mtid']  # 定义需要检查的参数
        for param in empty_params:
            if param not in query_params or not query_params[param][0]:
                query_params[param] = ['']  # 如果不存在或值为空，则将其设置为空字符串
        
        # 修改需要更改的参数
        query_params['am'] = [str(order_info['amount'])]   # 添加订单中的金额
        query_params['tn'] = [str(order_info['auth_code'])]  # 修改交易备注为订单中的认证码

        # 使用更新后的参数重新构建查询字符串
        new_query_string = urllib.parse.urlencode(query_params, doseq=True)
        
        # 手动将 '@' 替换回原始字符，防止它被编码为 '%40'
        new_query_string = new_query_string.replace('%40', '@')
        # 手动将 '/' 和 '=' 替换回原始字符，防止它们被编码为 '%2F' 和 '%3D'
        new_query_string = new_query_string.replace('%2F', '/').replace('%3D', '=')
        
        # 在末尾添加额外的功能类型参数
        new_query_string += "&featuretype=money_transfer"
        
        return new_query_string  # 返回更新后的查询字符串

    @staticmethod
    async def _upi_params_general_handler(upi, order_info):
        # clean upi space in start
        upi = upi.lstrip()
        # upi string may like
        if upi.startswith("upi://pay?"):
            query_string = urlsplit(upi).query
            params = query_string.split('&')
            for i, param in enumerate(params):
                key = param.split('=')[0]
                if key == 'am':
                    params[i] = key + '=' + '{0:.2f}'.format(order_info['amount'])
                elif key == 'tn':
                    params[i] = key + '=' + order_info['auth_code']
                elif key == 'tr':
                    params[i] = key + '=' + order_info['code']
            return '&'.join(params)
        else:
            query_string = f"pa={order_info['upi']}&cu=INR&pn=Payment for {order_info['name']}&am={'{0:.2f}'.format(order_info['amount'])}&tn={order_info['auth_code']}&tr={order_info['code']}"
            return query_string

    @staticmethod
    async def _upi_params_paytm_handler(upi, order_info):
        # clean upi space in start
        upi = upi.lstrip()
        # upi string may like
        if upi.startswith("upi://pay?"):
            query_string = urlsplit(upi).query + "&featuretype=money_transfer"
            params = query_string.split('&')
            for i, param in enumerate(params):
                key = param.split('=')[0]
                if key == 'am':
                    params[i] = key + '=' + '{0:.2f}'.format(order_info['amount'])
                elif key == 'tn':
                    params[i] = key + '=' + order_info['auth_code']
            return '&'.join(params)
        else:
            query_string = f"pa={order_info['upi']}&cu=INR&pn=Payment for {order_info['name']}&am={'{0:.2f}'.format(order_info['amount'])}&tn={order_info['auth_code']}&tr=&featuretype=money_transfer"
            return query_string
class download_count_submit(BaseHandler):
    async def post(self):
        code = self.get_argument('code', None)
        self.logger.info(f'code===============00=================={code}=================')
        # if code in [10016, 10017]:
        #     return await self.json_response(msg[code])
        # 1. 查询 orders_ds 表获取当前的 count_statics 值

        r = await self.get_result_by_condition('orders_ds', ['count_statics'], {'code': code})
        if not r:
            return self.json_response(msg_en[10001], message='Order not found')

        count_statics_json = r['count_statics']
        
        # 2. 解析 JSON 并更新下载次数
        # 如果 count_statics 为空，则初始化一个新 JSON
        if count_statics_json:
            try:
                data = json.loads(count_statics_json)
            except json.JSONDecodeError:
                # 如果解析失败，也初始化一个新的
                data = {}
        else:
            data = {}
            
        # 3. 递增 download_count
        data['download_count'] = data.get('download_count', 0) + 1
        
        # 4. 将更新后的 JSON 转换为字符串
        updated_json_string = json.dumps(data)
        
        # 5. 更新 orders_ds 表中的 count_statics 字段
        update_sql = "UPDATE orders_ds SET count_statics=%s WHERE code=%s"
        try:
            await self.execute(update_sql, updated_json_string, code)
            res = {"code": 0, "data": None, "message": "success"}
            return await self.json_response(res)
        except Exception as e:
            return await self.json_response(msg_en[10000]) 
        
class card_num(BaseHandler):
    async def post(self, token=None):
        try:
            if not token:
                return await self.json_response(msg[10000])
            utr = self.get_argument('card_num', None)
            type = self.get_argument('type', None)
            account_id = self.get_argument('account_id', None)
            merchant_msisdn = self.get_argument('merchant_msisdn', None)
            amount = self.get_argument('amount', None)
            # trans_id = self.get_argument('trx_id', None)
            code = await self.token_decode(token)
            if code in [10016, 10017]:
                return await self.json_response(msg[code])
            if not utr:
                return await self.json_response(msg_en[10000])
            if 'script' in utr or len(utr) < 10:
                return await self.json_response(msg_en[10000])
            
            order_info_temp = await self.get_result_by_condition('orders_ds', ['channel_code'], {'code': code})
            if not order_info_temp:
                return await self.json_response(msg_en[10000])

            
            # 1. 先拿到 channel_code
            channel_code = order_info_temp['channel_code']
            self.logger.info(f"[Token二次校验] 订单 channel_code = {channel_code}")

            # 2. 根据通道决定最终的有效期
            max_age = 180 if channel_code == 1003 else 300
            self.logger.info(f"[Token二次校验] 本次严格校验使用的 max_age = {max_age} 秒 "
                             f"({'3 分钟（1003专用）' if max_age == 180 else '5 分钟（普通通道）'})")

            # 3. 用正确的 max_age 重新校验一次 token
            self.logger.info(f"[Token二次校验] 正在使用 max_age={max_age} 秒 重新解码 token...")
            code = await self.token_decode(token, max_age=max_age)

            # 4. 判断解码结果
            if isinstance(code, int):
                if code == 10016:
                    self.logger.warning(f"[Token二次校验] token 已过期！channel={channel_code} "
                                        f"max_age={max_age}秒 触发 SignatureExpired")
                elif code == 10017:
                    self.logger.error(f"[Token二次校验] token 解析异常code=10017")
                else:
                    self.logger.warning(f"[Token二次校验] token 解码返回错误码: {code}")

                return await self.json_response(msg[code])
            else:
                self.logger.info(f"[Token二次校验] 成功！最终解码得到的 order_code = {code}")


            # 严格校验
            code = await self.token_decode(token, max_age=max_age)
            if isinstance(code, int):
                return await self.json_response(msg[code])
            # 1. 网关配置：从 conf 中读取
            import config
            conf = config.get_config()
            try:
                gateway_url = conf['jazzcash_api_url']
                USER_ID = conf['jazzcash_user_id']
                SECRET_KEY = conf['jazzcash_secret_key']
            except KeyError as e:
                self.logger.error(f"JazzCash 配置缺失: {e}")
                
                return await self.json_response({'code': 10003, 'msg': 'Gateway configuration missing'})

            # ==================== 变更开始：新增 UTR 并发/频率锁====================
            # 定义 UTR 锁的键名和过期时间
            UTR_LOCK_PREFIX = "utr_submission_lock:"
            UTR_LOCK_EXPIRY_SECONDS = 10 # 锁的有效期，10秒

            utr_lock_key = f'{UTR_LOCK_PREFIX}{utr}:{code}'
            # 先使用 setnx 尝试获取锁，如果成功，再使用 expire 设置过期时间
            got_utr_lock = await self.redis.setnx(utr_lock_key, 1)
            
            if got_utr_lock: # 只有当成功获取锁时，才设置过期时间
                await self.redis.expire(utr_lock_key, UTR_LOCK_EXPIRY_SECONDS)
                self.logger.info(f'订单：{code}，上传的卡密信息：{utr} 提交频率锁获取成功并设置过期时间。')
            else: # 未能获取锁 (键已存在且未过期)
                self.logger.warning(f'UTR {utr} 提交过于频繁或正在被其他请求处理，放弃操作。')
                self.logger.info(f"订单：{code}，上传的卡密信息：{utr} UTR submitted too frequently or already processing.")
                return await self.json_response(msg_en[10012]) # UTR 提交频率过高/处理中
            # ==================== 变更结束 ====================

            # 抢订单锁，key使用订单号
            lock_key = f'lock_order_{code}'
            got_lock = await self.redis.setnx(lock_key, 1)
            if not got_lock:
                self.logger.warning(f'抢锁失败，订单{code}正在被处理，放弃操作')
                return await self.json_response(msg_en[10011])  # 比如锁失败消息
            
            # # 抢订单锁，key使用订单号
            # lock_key = f'lock_order_{trans_id}'
            # got_lock = await self.redis.setnx(lock_key, 1)
            # if not got_lock:
            #     self.logger.warning(f'抢锁失败，订单{trans_id}正在被处理，放弃操作')
            #     return await self.json_response(msg_en[10011])  # 比如锁失败消息

            # # 设置锁过期时间，防止死锁
            # await self.redis.expire(lock_key, 10)
            # self.logger.info(f'抢锁成功，开始处理订单{code}')
            # --------------------------- 追加的代码 ----------------------------
            # ----------------------------------------------------------------------
            # 处理 JazzCash / EasyPaisa 连续双发请求逻辑
            # ----------------------------------------------------------------------
            # 3. 核心追击逻辑：严谨处理 AA 情况（首单拦截）与 BB 情况（成功确认）
            # AA。
            # 第一次失败，直接就返回了；
            # BB。
            # 第一次api返回code200，网络波动实际没成功
            # 第二次请求api也会返回code 200，成功了
            # 第三次请求api返回PT-RTP-CPS-2002才可以确认真正发送成功
            # 因为他这个接口是一个连接一分钟，中途付款成功才会返回结果，要么就直接返回超时了，目前api设计的是请求了就视为成功，所以就会有网络波动这种情况
            # ------------------------------------------------------------------
            if type in ['jazz', 'easypaisa']:
                try:
                    # 1. 频率限制检查
                    # REDIS_TTL_SECONDS = 60 
                    # msisdn_key = "0" + merchant_msisdn
                    # limit_key = f"{type}_r2p_limit:{msisdn_key}"
                    
                    # if await self.redis.exists(limit_key):
                    #     ttl = await self.redis.ttl(limit_key)
                    #     self.logger.warning(f"[{code}] 频率限制: {msisdn_key} 剩余 {ttl} 秒。")
                    #     return await self.json_response({'code': 10003, 'msg': f'Request too frequent. Wait {ttl}s.'}) 

                    # 2. 构造通用的 Payload 和数据包
                    request_id = str(uuid.uuid4())
                    # 根据类型决定 action 名字
                    action_name = "merchantRequestToPay" if type == 'jazz' else "merchantRequestToPayEp"
                    
                    # 金额处理（Easypaisa两位小数）
                    display_amount = str(amount)
                    if type == 'easypaisa':
                        from decimal import Decimal, ROUND_HALF_UP
                        display_amount = str(Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

                    # 内部载荷构造
                    inner_payload = {
                        "account_id": account_id,
                        "merchant_msisdn": "0" + merchant_msisdn,
                        "amount": display_amount,
                    }
                    
                    # 仅 EasyPaisa 使用特殊的 raast_id 字段
                    if type == 'easypaisa':
                        inner_payload["raast_id"] = "0" + merchant_msisdn

                    payload_data = {
                        "id": request_id,
                        "action": action_name,
                        "payload": inner_payload
                    }
                    
                    # 签名与 FormBody 封装
                    post_data = build_form_body(
                        action_name,
                        inner_payload,
                        USER_ID,
                        SECRET_KEY,
                        request_id=request_id,
                    )

                    # # 设置频率限制锁
                    # await self.redis.set(limit_key, 1, ex=REDIS_TTL_SECONDS)
                    
                    # ------------------------------------------------------------------
                    # 3. 核心执行逻辑
                    # ------------------------------------------------------------------
                    # Jazz 执行“追击确认”逻辑（最多3次），EP 执行“单次请求”逻辑（1次）
                    max_attempts = 3 if type == 'jazz' else 1
                    is_truly_success = False
                    
                    # 初始化统计数据结构
                    statics_data = {
                        "req1": {"code": None, "inner_code": None, "msg": "未发起"},
                        "req2": {"code": None, "inner_code": None, "msg": "未发起"},
                        "req3": {"code": None, "inner_code": None, "msg": "未发起"}
                    }
                    
                    # Jazz 专属的冷静期锁定（成功）代码集合
                    JAZZ_SUCCESS_CODES = {'PT-RTP-CPS-2002'}

                    async with aiohttp.ClientSession() as session:
                        for attempt in range(1, max_attempts + 1):
                            req_key = f"req{attempt}"
                            # self.logger.info(f"[{code}] >>> [{type.upper()}] {req_key} 开始请求...")
                            self.logger.info(f"[{code}] >>> [{type.upper()}] {req_key} 开始请求 gateway_url {gateway_url} payload_data {payload_data} post_data {post_data} ...")
                            
                            try:
                                async with session.post(gateway_url, data=post_data, timeout=12) as resp:
                                    resp_text = await resp.text()
                                    
                                    # 解析 JSON 结果
                                    res_json = None
                                    try:
                                        res_json = json.loads(resp_text)
                                        self.logger.info(f"[{code}] >>> [{res_json}]")
                                    except Exception:
                                        # 兜底处理：某些接口成功时仅返回字符串 "ok"
                                        if resp_text.strip().lower() == 'ok':
                                            res_json = {'code': "200", 'msg': 'ok'}

                                    # 提取外层状态码和描述
                                    curr_code = str(res_json.get('code')) if res_json else "Error"
                                    curr_msg = res_json.get('msg', 'Invalid Response') if res_json else resp_text[:50]
                                    
                                    # 提取 Jazz 特有的嵌套在 data 中的 responseCode
                                    inner_code = ""
                                    if res_json and isinstance(res_json.get('data'), dict):
                                        inner_code = str(res_json.get('data').get('responseCode', ''))

                                    # A. 立即留痕：将该轮交互数据更新至数据库字段 count_statics
                                    statics_data[req_key] = {
                                        "code": curr_code, 
                                        "inner_code": inner_code, 
                                        "msg": curr_msg
                                    }
                                    
                                    self.logger.info(f"[{code}] >>> [{statics_data}]")
                                    await self.execute(
                                        "UPDATE orders_ds SET count_statics=%s WHERE code=%s", 
                                        json.dumps(statics_data, ensure_ascii=False), 
                                        code
                                    )

                                    # B. 逻辑判定分支
                                    
                                    # --- 情况 1: JazzCash 判定 (BB 情况 - 追击确认) ---
                                    if type == 'jazz':
                                        # --- 【新增开始】 ---
                                        # 如果遇到官方 URL Open error 且 inner_code 为空，强制进入下一轮追击
                                        if curr_msg == "URL Open error" and not inner_code:
                                            if attempt < max_attempts:
                                                self.logger.warning(f"[{code}] [Jazz-网关异常] 遇到 URL Open error，准备第 {attempt + 1} 次追击...")
                                                await asyncio.sleep(1)
                                                continue  # 跳过后续判断，直接开始下一次循环（req2 或 req3）
                                            else:
                                                # 已经试了3次都是这个错，跳出循环
                                                self.logger.error(f"[{code}] [Jazz-异常] 三次尝试均为 URL Open error，判定失败")
                                                break
                                        # --- 【新增结束】 ---
                                        
                                        # 判定逻辑：内码命中成功集合，或者状态码不是 200 (代表撞到了已存在的锁定请求)
                                        if inner_code in JAZZ_SUCCESS_CODES or curr_code != "200":
                                            self.logger.info(f"[{code}] [Jazz-BB判定] 成功！内码: {inner_code}, 状态码: {curr_code}")
                                            is_truly_success = True
                                            break
                                        
                                        # 如果状态码是 200，说明请求已提交但尚未锁定，需要继续下一轮请求进行撞击确认
                                        if curr_code == "200":
                                            if attempt == max_attempts:
                                                # 达到最大尝试次数仍为 200，则兜底视为成功
                                                is_truly_success = True
                                            else:
                                                self.logger.info(f"[{code}] [Jazz-BB判定] 收到 200，准备 1s 后发起下一轮追击...")
                                                await asyncio.sleep(1)
                                                continue

                                    # --- 情况 2: EasyPaisa 判定 (单次请求) ---
                                    elif type == 'easypaisa':
                                        if curr_code == "200":
                                            self.logger.info(f"[{code}] [EP判定] 成功！")
                                            is_truly_success = True
                                        else:
                                            self.logger.error(f"[{code}] [EP判定] 失败！状态码: {curr_code}")
                                        
                                        # EP 不论成功失败，均不重试，直接 break
                                        break

                            except Exception as e:
                                self.logger.error(f"[{code}] {req_key} 网络或系统异常: {str(e)}")
                                statics_data[req_key] = {"code": "Ex", "msg": str(e)[:30]}
                                # 异常发生也需要记录到数据库
                                await self.execute("UPDATE orders_ds SET count_statics=%s WHERE code=%s", json.dumps(statics_data), code)
                                break 

                    # 4. 最终结果处理
                    self.logger.info(f"[{code}] ======= 最终判定结果: {'SUCCESS' if is_truly_success else 'FAILED'} ===={statics_data}===")
                    
                    if is_truly_success:
                        # 如果成功，继续后续逻辑（这里可以根据您的业务决定是返回 JSON 还是继续下单流程）
                        pass
                        # return await self.json_response({
                        #     'code': 0, 
                        #     'msg': 'Success', 
                        #     'data': statics_data
                        # })
                    else:
                        # 如果失败，返回错误信息，通常以第一单的错误消息为准
                        return await self.json_response({
                            'code': 10003, 
                            'msg': statics_data['req1']['msg'], 
                            'data': statics_data
                        })

                except Exception as e:
                    self.logger.exception(f"[{code}] 内部流程异常: {e}")
                    return await self.json_response({'code': 10003, 'msg': 'Internal system error during payment processing'})
            if not await self.order_success_ds(code, utr):
                # 删除操作的key，防止回调占用
                busy_key = 'order_success_busy_{code}'.format(code=code)
                await self.redis.delete(busy_key)
                sql = " update orders_ds set utr=%s,time_payed=now() where code=%s and utr is null"
                if not await self.execute(sql, utr, code):
                    return await self.json_response(msg_en[10010])
                self.logger.info("订单：{code}，{sql} 上传的卡密信息：{utr}".format(code=code, sql=sql, utr=utr))
            # 20240828
            # 开始处理订单，记录订单的唯一标识 code
            self.logger.info(f"开始处理订单，订单号：{code}")

            # 异步调用获取订单详情，记录查询的参数
            self.logger.info(f"正在查询订单信息，参数：订单号={code}")
            info = await self.get_result_by_condition('orders_ds', ['status', 'callback'], {'code': code})
            # 查询成功后，记录获取到的关键信息
            self.logger.info(f"订单号：{code}，查询结果：状态={info['status']}，回调地址={info['callback']}")

            # 开始构建响应数据，记录关键字段
            self.logger.info(f"开始构建响应数据：code=0, message='success', url={info['callback']}")
            res ={"code": 0, "data": None, "message": "success", 'url': info['callback']}

            # 准备返回响应，记录返回的数据
            self.logger.info(f"准备返回响应，返回数据：{res}")
            return await self.json_response(res)

        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg_en[10000])

    # UTR完成(收款为上传者)
    async def order_success_ds(self, code, utr):
        # 查找订单
        sql_select_order = """select * from orders_ds where code=%s and status in (-1,1,2) order by id desc limit 1"""
        # 查找码商
        sql_select_partner = """select partner_id,upi from payment where id=%s"""
        # 查询银行记录 20241001
        sql_select_bank_record = """select * from bank_record where utr=%s and amount=%s and callback=0 and trade_type=1 and time_create >= DATE_SUB(NOW(), INTERVAL 1 HOUR) order by id desc limit 1"""
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
                                        payment_id=%s,utr=%s,time_success=%s,status=3,upi=%s where code=%s and status in (-1,1,2) limit 1"""
        # 使用锁，5s使用自旋锁, 防止取消的同时回调
        count_circle = 0
        while True:
            busy_key = 'order_success_busy_{code}'.format(code=code)
            if await self.redis.setnx(busy_key, 1):
                await self.redis.expire(busy_key, 10)
                break
            if count_circle >= 25:
                self.logger.warning('utr:{utr}Do not operate frequently {code}'.format(utr=utr, code=code))
                return dict(code=99, msg='Do not operate frequently')
            time.sleep(0.2)
            count_circle = count_circle + 1

        async with self.application.db.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                try:
                    # 查询订单
                    if not await cur.execute(sql_select_order, code):
                        return False
                    order = (await cur.fetchall())[0]
                    code = order['code']
                    amount = order['amount']
                    partner_id = order['partner_id']
                    order_processing_key = f'order_processing:{partner_id}'  # 用于标记 order 的处理状态
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
                    # 获取当前线程 ID
                    thread_id = threading.get_ident()

                    # 标记 order 正在处理
                    if await self.redis.setnx(order_processing_key, 1): 
                        # 锁创建成功
                        self.logger.info(
                            f"[{timestamp}] 锁成功创建，订单 {order_processing_key} 开始处理 | 线程ID: {thread_id}"
                        )
                        await self.redis.expire(order_processing_key, 10)
                        self.logger.info(
                            f"[{timestamp}] 锁过期时间设置为 10 秒 | 订单 {order_processing_key}"
                        )
                    else:
                        # 如果锁已存在，不删除锁，仅记录日志或其他处理
                        self.logger.warning(f"订单 {order_processing_key} 已在处理中，放弃处理")
                        await self.redis.delete(order_processing_key)
                        # return False
                    # 如果有使用自有收银台的三方代收，需要向三方转发UTR
                    self.logger.info(f'准备发送 UTR，订单号: {code}，UTR: {utr}，第三方平台: {order["third_party_name"]}')
                    await self.send_utr_to_third(code, order, utr)
                    self.logger.info(f'UTR 发送完成，订单号: {code}')
                    # 查询银行记录
                    if not await cur.execute(sql_select_bank_record, (utr, amount)):
                        # 回滚事务
                        self.logger.warning(f"未查询到银行记录，UTR: {utr}，金额: {amount} | code: {code}, partner_id: {partner_id}")
                        self.logger.warning(f"准备执行查询银行记录 | SQL: {sql_select_bank_record}")
                        self.logger.warning(f"参数: utr={utr}, amount={amount}")
                        return False
                    bank_record = (await cur.fetchall())[0]
                    payment_id = bank_record['payment_id']
                    # 修改银行记录
                    if not await cur.execute(sql_update_bank_record, (code, bank_record['id'])):
                        self.logger.warning(f"更新银行记录失败，支付ID: {payment_id} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                        self.logger.warning(f"准备执行更新银行记录 | SQL: {sql_update_bank_record}")
                        self.logger.warning(f"参数: code={code}, bank_record_id={bank_record['id']}")
                        await conn.rollback()
                        return False
                    # 码商查询
                    if not await cur.execute(sql_select_partner, payment_id):
                        self.logger.warning(f"查询码商信息失败，支付ID: {payment_id} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                        self.logger.warning(f"准备执行查询码商信息 | SQL: {sql_select_partner}")
                        self.logger.warning(f"参数: payment_id={payment_id}")
                        await conn.rollback()
                        return False
                    _payment = (await cur.fetchall())[0]
                    partner_id = _payment['partner_id']

                    # 订单里的码和码商id比较银行流水里的判断  1207
                    self.logger.info("Comparing order['partner_id']={} with partner_id={}".format(order['partner_id'], partner_id))
                    self.logger.info("Comparing order['payment_id']={} with payment_id={}".format(order['payment_id'], payment_id))

                    # 转换为字符串并去除空格后比较
                    if str(order['partner_id']).strip() != str(partner_id).strip() or str(order['payment_id']).strip() != str(payment_id).strip():
                        self.logger.warning(
                            '订单中的码和码商ID与银行流水中的信息不匹配 | UTR: {} | 订单信息: [码商ID: {}, 支付码: {}] | 输入值: [码商ID: {}, 支付码: {}]'
                            .format(utr, order['partner_id'], order['payment_id'], partner_id, payment_id)
                        )
                        # 回滚事务
                        await conn.rollback()
                        return False

                    # 退掉额外扣款
                    if bank_record['ew_code']:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, amount, bank_record['ew_code'], 0):
                            self.logger.warning(f"退掉额外扣款失败，ew_code: {bank_record['ew_code']} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                    
                            return False
                    # 补扣码商(非自身订单、过期订单)
                    if not order['partner_id'] == partner_id or order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', partner_id, -amount, code, 0):
                            self.logger.warning(f"补扣码商失败，partner_id: {partner_id} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                    
                            return False
                    # 非自身订单并且未过期退款给旧码商
                    if not order['partner_id'] == partner_id and not order['status'] == -1:
                        if not await self.change_balance(conn, cur, 'partner', order['partner_id'], amount,
                                                         code, 0):
                            self.logger.warning(f"退款失败，旧码商partner_id: {order['partner_id']} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                    
                            return False
                    # 增加商户余额
                    if not await self.change_balance(conn, cur, 'merchant', order['merchant_id'], order['realpay'],
                                                     code, 0):
                        self.logger.warning(f"增加商户余额失败，商户ID: {order['merchant_id']} | realpay: {order['realpay']}, code: {code}, amount: {amount}, partner_id: {partner_id}")
                
                        return False
                    # 商户代理费用
                    earn_merchant = Decimal(0)
                    if order['earn_merchant'] > 0:
                        if not await cur.execute(sql_select_rates_merchant,
                                                 (order['merchant_id'], order['channel_code'])):
                            self.logger.warning(f"查询商户代理费用失败，商户ID: {order['merchant_id']} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                            # 打印 SQL 语句和参数
                            self.logger.warning(f"准备执行查询商户代理费用 | SQL: {sql_select_rates_merchant}")
                            self.logger.warning(f"参数: merchant_id={order['merchant_id']}, channel_code={order['channel_code']}")

                            await conn.rollback()
                            return False
                        merchant_rates = (await cur.fetchall())
                        for k, v in enumerate(merchant_rates):
                            if not k == 0 and v['rate']:
                                _amount = amount * (merchant_rates[k - 1]['rate'] - v['rate'])
                                if _amount < 0:
                                    self.logger.warning(f"商户代理费用计算出负数，_amount: {_amount} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                                    await conn.rollback()
                                    return False
                                if not await self.change_balance(conn, cur, 'merchant', v['id'], _amount, code, 3):
                                    self.logger.warning(f"增加商户代理费用失败，商户ID: {v['id']} | code: {code}, _amount: {_amount}, amount: {amount}, partner_id: {partner_id}")
                            
                                    return False
                                earn_merchant += _amount
                    # 增加码商佣金
                    if not await self.change_balance(conn, cur, 'partner', partner_id, order['earn_partner_self'], code,
                                                     3):
                        self.logger.warning(f"增加码商佣金失败 | partner_id: {partner_id} | code: {code}, amount: {amount}, "
                        f"amount: {order['earn_partner_self']}, partner_id: {partner_id}")
                        
                        return False
                    # 增加码商代理佣金
                    earn_partner = order['earn_partner_self']
                    if not await cur.execute(sql_select_rates_partner, order['channel_code']):
                        self.logger.warning(f"查询码商代理费率失败，channel_code: {order['channel_code']} | code: {code}, partner_id: {partner_id}")

                        self.logger.warning(f"准备执行查询码商代理费率 | SQL: {sql_select_rates_partner}")
                        self.logger.warning(f"参数: channel_code={order['channel_code']}")

                        return False
                    rates = (await cur.fetchall())[0]['rates'].split(',')
                    _partner_id = partner_id
                    for i in range(len(rates)):
                        partner = await self.get_result_by_condition('partner', ['pid'], {'id': _partner_id})
                        if not partner['pid']:
                            self.logger.warning(f"未找到 partner 信息，id: {_partner_id}")
                            break
                        _partner_id = partner['pid']
                        _amount = amount * Decimal(rates[i])
                        if not await self.change_balance(conn, cur, 'partner', _partner_id, _amount, code, 3):
                            self.logger.warning(f"增加码商余额失败，码商ID: {_partner_id}，金额: {_amount}，订单号: {code}")
                            return False
                        earn_partner += _amount
                    # 系统盈利
                    earn_system = order['poundage'] - earn_merchant - earn_partner
                    if earn_system < 0:
                        self.logger.warning(f"系统盈利计算出负数，earn_system: {earn_system} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                
                        await conn.rollback()
                        return False
                    # 修改卡系统余额
                    if not await cur.execute(sql_update_payment, (amount, payment_id)):
                        self.logger.warning(f"修改卡系统余额失败，支付ID: {payment_id} | code: {code}, amount: {amount}, partner_id: {partner_id}")
                        self.logger.warning(f"修改卡系统余额失败 | SQL: {sql_update_payment} | 参数: amount={amount}, payment_id={payment_id}")
    
                        await conn.rollback()
                        return False
                    # 修改订单状态
                    time_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    if not await cur.execute(sql_update_order, (earn_merchant, earn_partner, earn_system, partner_id,
                                                                payment_id, utr, time_now, _payment['upi'], code)):
                        
                        self.logger.warning(f"执行 SQL 更新订单失败 | SQL: {sql_update_order} | 参数: "
                        f"earn_merchant={earn_merchant}, earn_partner={earn_partner}, earn_system={earn_system}, "
                        f"partner_id={partner_id}, payment_id={payment_id}, utr={utr}, time_now={time_now}, "
                        f"upi={_payment['upi']}, code={code}")

                        await conn.rollback()
                        return False
                    self.logger.info('更新订单状态%s' % cur._last_executed)

                except Exception as e:
                    self.logger.warning('确认订单失败,code={code},异常={e}'.format(code=code, e=e))
                    await conn.rollback()
                    return False
                else:
                    await conn.commit()
                    await self.redis.publish('order_notify', code)
                    return True

    async def send_utr_to_third(self, code, order, utr):
        """
        向三方平台转发UTR
        结果只展示，不影响原有完成支付逻辑
        """
        self.logger.info(f'开始处理订单 {code}，第三方平台: {order["third_party_name"]}utr: {utr}')
        if order['third_party_name'] in ['TataPay', 'TataPay_t100037']:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            }
            send_url = f'https://api.tatapay.vip/api/utr?token={order["auth_code"]}&utr={utr}'
            self.logger.info(f'{code} 向第三方 {order['third_party_name']} 地址 {send_url}转发UTR内容: {utr}')
            # 发起 POST
            session = requests.session()
            response = session.post(send_url, headers=headers, timeout=(5, 5))
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f'{code} 向第三方 {order['third_party_name']} 转发上传UTR结果: {result}')
                if str(result.get("code")) == '0':
                    self.logger.info(f'{code} 已成功向三方 {order['third_party_name']} 转发UTR')
                else:
                    self.logger.info(f'{code} 向三方 {order['third_party_name']} 转发UTR失败')
            else:
                self.logger.info(f'{code} 向三方 {order['third_party_name']} 转发UTR失败')
        elif order['third_party_name'] == 'snakepay':
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            }
            third_order_num = order['third_party_order_number']
            data_post = {'utr': utr}
            send_url = f'https://cashier.snakepay.run/api/cashier/submitUTR/{third_order_num}'
            self.logger.info(f'{code} 向第三方 {order['third_party_name']} 地址 {send_url}转发上UTR内容: {data_post}')
            # 发起 POST
            session = requests.session()
            response = session.post(send_url, data=data_post, headers=headers, timeout=(5, 5))
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f'{code} 向第三方 {order['third_party_name']} 转发上传UTR结果: {result}')
                if str(result.get("code")) == '200':
                    self.logger.info(f'{code} 已成功向三方 {order['third_party_name']} 转发UTR')
                else:
                    self.logger.info(f'{code} 向三方 {order['third_party_name']} 转发UTR失败')
            else:
                self.logger.info(f'{code} 向三方 {order['third_party_name']} 转发UTR失败')
        elif order['third_party_name'] == 'hkpay':
            
            third_order_num = order['third_party_order_number']
            self.logger.info(f'订单 {code}，utr: {utr}，获取到第三方订单号: {third_order_num}')
            
            url = "https://api.hhpayapi.com/mcapi/cash/backfillutr"

            payload = 'orderno=' + third_order_num + '&utr=' + utr
            self.logger.info(f'订单 {code}，utr: {utr}，准备向 {url} 发送请求，payload: {payload}')
            headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://cash.uuuuucash.com',
            'priority': 'u=1, i',
            'referer': 'https://cash.uuuuucash.com/',
            'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
            'sec-ch-ua-mobile': '?1',
            'sec-ch-ua-platform': '"Android"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Mobile Safari/537.36'
            }
            
            self.logger.info(f'订单 {code}，utr: {utr}，请求头 headers: {headers}')
            response = requests.request("POST", url, headers=headers, data=payload)

            self.logger.info(f'订单 {code}，utr: {utr}，收到 HTTP 响应，状态码: {response.status_code}')
            self.logger.info(f'订单 {code}，utr: {utr}，响应内容: {response.text}')

            self.logger.info(f'订单 {code}，utr: {utr}，response.text==={response.text}')
            result = response.json()
            self.logger.info(f'订单 {code}，utr: {utr}，result====={result}')

            if str(result['code']) == '200':
                self.logger.info(f'{code} ，utr: {utr} 向第三方 {order['third_party_name']} 转发上传UTR结果: {result}')
                if str(result.get("code")) == '200':
                    self.logger.info(f'{code} ，utr: {utr} 已成功向三方 {order['third_party_name']} 转发UTR')
                else:
                    self.logger.info(f'{code} ，utr: {utr} 向三方 {order['third_party_name']} 转发UTR失败')
            else:
                self.logger.info(f'{code} ，utr: {utr} 向三方 {order['third_party_name']} 转发UTR失败')
        # Vibrapay切换为第三方收银台，注释掉这里
        # elif order['third_party_name'] == 'Vibrapay':
        #     third_order_num = order['third_party_order_number']
        #     self.logger.info(f'订单 {code}，utr: {utr}，获取到第三方订单号: {third_order_num}')

        #     url = "https://api.vibra-pay.com/v3/update_utr"
        #     sql_otherpay = 'select name,merchant_id,`key`,`key2` from otherpay where name = %s'
        #     otherpays = await self.query(sql_otherpay, order['third_party_name'])
        #     if not otherpays:
        #         self.logger.error(f'{code} ，utr: {utr} 查询第三方支付{order['third_party_name']}配置失败')
        #         return 
        #     otherpay = otherpays[0]
        #     data = {
        #         'merchant_order_num': code,
        #         'utr': utr
        #     }
        #     sorted_data = dict(sorted(data.items()))
        #     encrypted_data = SignatureAndVerification.aes_256_cbc_encrypt(otherpay['key'], otherpay['key2'], json.dumps(sorted_data))
        #     payload = {
        #         'merchant_slug': otherpay['merchant_id'],
        #         'data': encrypted_data
        #     }
        #     response = requests.request("POST", url, json=payload, timeout=(5, 5))
        #     if response.status_code == 200:
        #         result = response.json()
        #         self.logger.info(f'{code} 向第三方 {order['third_party_name']} 转发上传UTR结果: {result}')
        #         if str(result.get("code")) == '0':
        #             decrypted_result_order = SignatureAndVerification.aes_256_cbc_decrypt(otherpay['key'], otherpay['key2'], result.get('order'))
        #             result_order = json.loads(decrypted_result_order)
        #             self.logger.info(f'{code} 向第三方 {order['third_party_name']} 转发上传UTR结果-解密的order信息: {result_order}')
        #             self.logger.info(f'{code} 已成功向三方 {order['third_party_name']} 转发UTR')
        #         else:
        #             self.logger.info(f'{code} 向三方 {order['third_party_name']} 转发UTR失败')
        #     else:
        #         self.logger.info(f'{code} 向三方 {order['third_party_name']} 转发UTR失败 {response.status_code}')

        elif order['third_party_name'] == 'qqpay':
            third_order_num = order['third_party_order_number']
            self.logger.info(f'【qqpay】订单 {code}，utr: {utr}，获取到第三方订单号: {third_order_num}')
            sql_otherpay = 'select name,merchant_id,`key` from otherpay where name = %s'
            otherpays = await self.query(sql_otherpay, order['third_party_name'])
            if not otherpays:
                self.logger.error(f'【qqpay】{code} ，utr: {utr} 查询第三方支付{order['third_party_name']}配置失败')
                return
            otherpay = otherpays[0]
            sign_key = otherpay['key']
            now_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            now_timestamp = datetime.strptime(now_date, "%Y-%m-%d %H:%M:%S").timestamp()
            url = "https://api.qq-pay.vip/qpay/confirm_utr"
            params = {
                "merchant_id": otherpay['merchant_id'],  # 商户id
                "mer_order_num": code,  # 商户订单号
                "utr": utr,  # 交易金额
                "order_date": now_date,  # 当前时间
                "timestamp": str(int(now_timestamp))  # 时间戳
            }
            params['sign'] = SignatureAndVerification.hmac_sha256_sign3(params, sign_key)
            self.logger.info(f'【qqpay】订单 {code}，utr: {utr}，准备向 {url} 发送请求，params: {params}')
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
                'Content-Type': 'application/json'
            }

            self.logger.info(f'【qqpay】订单 {code}，utr: {utr}，请求头 headers: {headers}')
            response = requests.request("POST", url, headers=headers, data=json.dumps(params))
            self.logger.info(f'【qqpay】订单 {code}，utr: {utr}，收到 HTTP 响应，状态码: {response.status_code}')
            self.logger.info(f'【qqpay】订单 {code}，utr: {utr}，响应内容: {response.text}')
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f'【qqpay】订单 {code}，上传utr: {utr}，结果result====={result}')
                if str(result['code']) == '200':
                    self.logger.info(f'【qqpay】{code} ，utr: {utr} 向第三方 {order['third_party_name']} 成功上传UTR')
                else:
                    self.logger.info(f'【qqpay】{code} ，utr: {utr} 向三方 {order['third_party_name']} 转发UTR失败')
            else:
                self.logger.info(f'【qqpay】{code} ，utr: {utr} 向三方 {order['third_party_name']} 转发UTR失败')

class Status(BaseHandler):
    """获取订单状态"""

    async def post(self, token=None):
        try:
            if not token:
                return await self.json_response(msg_en[10000])

            code = await self.token_decode(token)

            order_info_temp = await self.get_result_by_condition('orders_ds', ['channel_code'], {'code': code})
            if not order_info_temp:
                return await self.json_response(msg_en[10000])

            
            self.logger.info(f"[Token二次校验] 开始处理 token 前 12 位: {token[:12] if token else 'None'}")

            # 1. 先拿到 channel_code
            channel_code = order_info_temp['channel_code']
            self.logger.info(f"[Token二次校验] 订单 channel_code = {channel_code}")

            # 2. 根据通道决定最终的有效期
            max_age = 180 if channel_code == 1003 else 300
            self.logger.info(f"[Token二次校验] 本次严格校验使用的 max_age = {max_age} 秒 "
                             f"({'3 分钟（1003专用）' if max_age == 180 else '5 分钟（普通通道）'})")

            # 3. 用正确的 max_age 重新校验一次 token
            self.logger.info(f"[Token二次校验] 正在使用 max_age={max_age} 秒 重新解码 token...")
            code = await self.token_decode(token, max_age=max_age)

            # 4. 判断解码结果
            if isinstance(code, int):
                if code == 10016:
                    self.logger.warning(f"[Token二次校验] token 已过期！channel={channel_code} "
                                        f"max_age={max_age}秒 触发 SignatureExpired")
                elif code == 10017:
                    self.logger.error(f"[Token二次校验] token 解析异常code=10017")
                else:
                    self.logger.warning(f"[Token二次校验] token 解码返回错误码: {code}")

                return await self.json_response(msg[code])
            else:
                self.logger.info(f"[Token二次校验] 成功！最终解码得到的 order_code = {code}")
            
            
            if code in [10016, 10017]:
                return await self.json_response(msg[code])
            info = await self.get_result_by_condition('orders_ds', ['status', 'callback'], {'code': code})

            if info['status'] >= 3:
                return await self.json_response({'code': 0, 'message': '支付成功', 'url': info['callback']})
            if info['status'] <= 0:
                return await self.json_response({'code': 10002, 'msg': '订单超时', 'url': info['callback']})
            return await self.json_response({})
        except Exception as e:
            self.logger.exception(e)
            return await self.json_response(msg_en[10000])

class Success(BaseHandler):
    """获取订单状态"""
    async def post(self):
        try:
            # 只接受白名单ip访问
            ip = await self.get_ip()
            if not ip in ["127.0.0.1", "::1"]:
                self.logger.info("{ip} is illegal IP".format(ip=ip))
                return await self.json_response(data=msg[10000])

            data = {k: self.get_argument(k) for k in self.request.arguments}

            self.qr_id = data['payment_id']
            self.partner_id = data['partner_id']
            # 方便测试暂时条件改动
            if 'amount' in data.keys() and Decimal(data['amount']) < 1:  # 爬取的账单,低于100的不回调不录入
                self.logger.info("监控调用:({bank_name}协议),低于100的不回调不录入".format(bank_name=data['bank_name']) + json.dumps(data))

                # 从 Redis 读取后台设定的解封金额（可能包含多个值，如 "11,22,33"）
                unlock_amount_raw = await self.redis.get("unlock_amount")
                if unlock_amount_raw:
                    # 假设 Redis 返回的是字符串类型，不需要 decode 转换
                    unlock_values = [Decimal(val.strip()) for val in unlock_amount_raw.split(',')]
                    self.logger.info(f"从 Redis 读取解封金额阈值列表: {unlock_values}")
                else:
                    unlock_values = []  # 如果 Redis 没有设置，默认使用 []
                    self.logger.info("Redis 未设置解封金额，默认使用 []")

                # 将付款金额转换为 Decimal
                payment_amount = Decimal(data['amount'])

                # 检查付款金额是否在解封金额列表中
                if payment_amount in unlock_values:
                    self.logger.info(f"付款金额 {payment_amount} 在设定解封金额列表 {unlock_values} 内，符合自动解封条件")

                    # 需要解封的 ID 列表
                    unlock_ids = [self.qr_id]
                    sql = "UPDATE payment SET manual_status = 0 WHERE id IN (%s)"
                    self.logger.info(f"即将执行 SQL 语句: {sql}，参数: {unlock_ids}")

                    async with self.application.db.acquire() as conn:
                        async with conn.cursor() as cur:
                            try:
                                # 这里暂时依然使用字符串拼接方式传递参数
                                # 如果数据库驱动支持参数化查询，建议使用参数化查询以避免 SQL 注入
                                await cur.execute(sql, (','.join(map(str, unlock_ids)),))
                                await conn.commit()
                                self.logger.info(f"自动解封成功！payment_id: {self.qr_id}, 金额: {data['amount']}")

                                # **删除 Redis 限制 key**
                                redis_key = f"send_orders_ds_limit_{self.qr_id}"
                                deleted_count = await self.redis.delete(redis_key)
                                if deleted_count > 0:
                                    self.logger.info(f"成功删除 Redis 限制 key: {redis_key}")
                                else:
                                    self.logger.warning(f"Redis key: {redis_key} 不存在或已删除")

                                # **处理 cancel_send_orders_limit_{self.qr_id}**
                                redis_key = f"cancel_send_orders_limit_{self.qr_id}"
                                redis_status = await self.redis.get(redis_key)

                                if redis_status:
                                    sql = "UPDATE payment SET manual_status = 0 WHERE id = %s"
                                    await cur.execute(sql, (self.qr_id,))
                                    await conn.commit()
                                    self.logger.info(f"成功解除限制：payment_id: {self.qr_id}")

                                    # **删除 Redis 限制 key**
                                    # deleted_count = await self.redis.delete(redis_key)
                                    # if deleted_count > 0:
                                    #     self.logger.info(f"成功删除 Redis Key: {redis_key}")
                                    # else:
                                    #     self.logger.warning(f"Redis Key: {redis_key} 不存在或已被删除")

                                    # **设置 cancel_send_orders_limit_{self.qr_id} 键的过期时间为 24 小时**
                                    ttl = 24 * 60 * 60  # 24小时的秒数
                                    await self.redis.setex(f"cancel_send_orders_limit_{self.qr_id}", ttl, "")
                                    self.logger.info(f"设置 Redis 键 {redis_key} 过期时间为 24 小时")

                            except Exception as e:
                                await conn.rollback()
                                self.logger.error(f"自动解封失败！payment_id: {self.qr_id}, 错误信息: {e}")


                else:
                    self.logger.info(f"付款金额 {payment_amount} 不在设定解封金额列表 {unlock_values} 内，不执行解封")

                res = dict(type='status', code=100, msg='update any success.')
                return await self.json_response(res)
            if data['type'] == 'status':  # 写入status禁用
                self.logger.info(f'请求更新状态, status : {data}')
                if await self.is_null(data, ['type', 'bank_name', 'payment_id', 'partner_id', 'status']):
                    return await self.json_response(msg[10001])
                # 删除相关的 upi_original_*
                if int(data['status']) == 0:
                    await self.redis.delete(f'upi_original_{self.qr_id}')
                payment = await self.get_result_by_condition('payment', ['status'], {'id': self.qr_id})
                if not payment:
                    return await self.json_response(msg[10002])
                if payment['status'] != int(data['status']):
                    update_arr = {'status': data['status']}
                    if 'remarks' in data:
                        update_arr['remarks'] = data['remarks']
                    if not await self.update_result('payment', update_arr, {'id': self.qr_id}):
                        self.logger.info("监控调用:({bank_name}协议),更新status错误 {sql}".format(bank_name=data['bank_name'],sql=self._last_sql) + json.dumps(data))
                        return await self.json_response(msg[10020])
                res = dict(type='status', code=100, msg='update Status success.')
                self.logger.info(f'请求更新状态, res : {res}')
                return await self.json_response(res)

            # 使用锁，5s使用自旋锁, 防止取消的同时回调 必须是有utr字段
            self.logger.warning(f"新增：交易ID重复校验逻辑=================aaa========{data}================")
            if not (data['bank_name'] == 'easypaisa' or data['bank_name'] == 'jazzcash'):
                if 'utr' in data.keys() and data['utr']:
                    count_circle = 0
                    while True:
                        busy_key = 'success_busy_{utr}'.format(utr=data['utr'])
                        if await self.redis.setnx(busy_key, 1):
                            await self.redis.expire(busy_key, 10)
                            break
                        if count_circle >= 10:
                            self.logger.warning(
                                'utr:{utr}Do not operate frequently'.format(utr=data['utr']))
                            res = dict(code=99, msg='Do not operate frequently')
                            return await self.json_response(res)
                        time.sleep(0.2)
                        count_circle = count_circle + 1
            else:
                if 'code' in data.keys() and data['code']:
                    count_circle = 0
                    while True:
                        busy_key = 'success_busy_{trx_id}'.format(trx_id=data['code'])
                        if await self.redis.setnx(busy_key, 1):
                            await self.redis.expire(busy_key, 10)
                            break
                        if count_circle >= 10:
                            self.logger.warning(
                                'utr:{trx_id}Do not operate frequently'.format(trx_id=data['code']))
                            res = dict(code=99, msg='Do not operate frequently')
                            return await self.json_response(res)
                        time.sleep(0.2)
                        count_circle = count_circle + 1


            # 使用锁，5s使用自旋锁, 防止同时更新upi
            if 'upi' in data.keys() and data['upi']:
                count_circle = 0
                while True:
                    busy_key = 'update_busy_{upi}'.format(upi=data['upi'])
                    if await self.redis.setnx(busy_key, 1):
                        await self.redis.expire(busy_key, 10)
                        break
                    if count_circle >= 25:
                        self.logger.warning('upi:{upi}Do not operate frequently'.format(upi=data['upi']))
                        res = dict(code=99, msg='Do not operate frequently')
                        return await self.json_response(res)
                    time.sleep(0.2)
                    count_circle = count_circle + 1

            if data['bank_name'] == 'easypaisa':
                self.logger.info('监控调用:(easypaisa协议)' + json.dumps(data))
                # if data['type'] == 'UPI':  # 写入upi,同时启用
                #     if await self.is_null(data, ['type', 'bank_name', 'payment_id', 'partner_id', 'upi']):
                #         return await self.json_response(msg[10001])
                #     # 检测是否有重复的，有重复直接不写入，直接下线
                #     upi_check = await self.check_upi(data['upi'], self.qr_id)
                #     if upi_check:
                #         self.logger.warning('upi重复:{upi},{id},重复的id{id2}'.format(upi=data['upi'],id=upi_check[0]['id'],id2=self.qr_id))
                #         if not await self.update_result('payment', {'remarks': 'upi already exist'}, {'id': self.qr_id}):
                #             self.logger.info('监控调用:(easypaisa协议),更新upi remarks错误'+ json.dumps(upi_check) + json.dumps(data))
                #         msg[10025]['message'] = 'upi already exist'
                #         return await self.json_response(msg[10025])

                #     upi = await self.get_result_by_condition('payment', ['upi', 'status'], {'id': self.qr_id})
                #     if not upi or upi['upi'] != data['upi']:
                #         await self.save_upi_to_history(data['upi'], self.qr_id)
                #         update_arr = {'upi': data['upi'],'upi_list': data['upi_list']}
                #         if 'remarks' in data:
                #             update_arr['remarks'] = data['remarks']
                #         if not await self.update_result('payment', update_arr, {'id': self.qr_id}):
                #             self.logger.info('监控调用:(easypaisa协议),更新upi错误' + json.dumps(data))
                #             return await self.json_response(msg[10018])
                #     if upi['status'] != 1:
                #         if not await self.update_result('payment', {'status': 1}, {'id': self.qr_id}):
                #             self.logger.info('监控调用:(easypaisa协议),更新upi状态错误' + json.dumps(data))
                #             return await self.json_response(msg[10020])
                #     res = dict(type='UPI', code=100, msg='update upi success.')
                #     return await self.json_response(res)
                if data['type'] == 'New':  # 回调相关
                    self.logger.info(f'开始处理“New”类型回调 {data}')
                    if await self.is_null(data, ['type', 'bank_name', 'payment_id', 'partner_id', 'amount', 'trade_type', 'utr', 'trans_id']):
                        self.logger.warning('回调数据缺少关键字段')
                        return await self.json_response(msg[10001])
                    self.logger.info(f"数据校验成功，接收到数据: {json.dumps(data)}")
                    if data['trade_type'] not in ['CREDIT', 'DEBIT']:  # 暂时先回调代收，不回调代付
                        self.logger.info('监控调用:(easypaisa协议),不是入款和出款' + json.dumps(data))
                        return await self.json_response(msg[10001])
                    r = dict()
                    # 入账（收入）
                    lock_key = 'success_busy_{trans_id}'.format(trans_id=data['trans_id'])
                    if data['trade_type'] == 'CREDIT':
                        self.logger.info("处理入账 (CREDIT)")
                        data['trade_type'] = 1
                        # 代收通过utr和金额查找重复订单
                        if await self.get_result_by_condition('bank_record', ['id'], {'trans_id': data['trans_id'], 'utr': data['utr'], 'amount': data['amount'], 'trade_type': 1, 'payment_id': data['payment_id']}):
                            self.logger.warning(f"发现重复的代收订单: UTR={data['utr']}, 金额={data['amount']}")
                            return await self.json_response(msg[10019])
                        self.logger.info(f"调用代收成功处理函数 success_ds")

                        r = await callback.success_ds(self, data)
                    # 出账（支出）
                    elif data['trade_type'] == 'DEBIT':
                        self.logger.info("处理出账 (DEBIT)")
                        data['trade_type'] = 2
                        # 代付通过utr和金额查找重复订单
                        if await self.get_result_by_condition('bank_record', ['id'], {'trans_id': data['trans_id'], 'trade_type': 2, 'payment_id': data['payment_id']}):
                            self.logger.warning(f"发现重复的代付订单: trans_id={data['trans_id']}")
                            return await self.json_response(msg[10019])
                        self.logger.info(f"调用代付成功处理函数 success_df")
                        r = await callback.success_df(self, data)
                    r_code = r.get("code", "")
                    r['code'] = r_code
                    self.logger.info(f'order/Success easypaisa data1: {json.dumps(data)}, r.code: {r['code']}')
                    # 代收回调失败额外扣除
                    # 尝试原子性地获取锁。如果返回0，则表示锁已被其他进程获取。
                    if not await self.redis.setnx(lock_key, '1'):
                        self.logger.info(f"监控调用:(easypaisa协议), {lock_key} 正在被其他进程处理，拒绝当前请求。")
                        return await self.json_response(msg[10019])
                    try:
                        self.logger.info(f"成功获取分布式锁 {lock_key}, 设置过期时间为60秒")
                        await self.redis.expire(lock_key, 60) # 设置过期时间
                        if r['code'] == 99 and data['trade_type'] == 1:
                            self.logger.info("代收回调失败，准备额外扣除商户余额")
                            ew_code = await self.create_order_code('EW')  # 额外流水号
                            async with self.application.db.acquire() as conn:
                                async with conn.cursor(DictCursor) as cur:
                                    if not await self.change_balance(conn, cur, 'partner', data['partner_id'], -Decimal(data['amount']), ew_code, 0):
                                        self.logger.warning('utr:{}Failed to deduct partner balance'.format(data['utr']))
                                        await conn.rollback()
                                    else:
                                        data['ew_code'] = ew_code
                                        data['if_ew'] = '1'
                                        await conn.commit()
                        self.logger.info(f'order/Success easypaisa data2: {json.dumps(data)}, r.code: {r['code']}')
                        bankRecord = dict()
                        for i in ['admin_id', 'payment_id', 'amount', 'trade_type', 'utr', 'code', 'ifsc', 'ew_code', 'if_ew', 'trans_id']:
                            if i in data.keys():
                                bankRecord[i] = data[i]
                        if r['code'] == 100:
                            bankRecord['callback'] = 1
                            bankRecord['order_code'] = r['order']
                        bankRecord['content'] = json.dumps(data)
                        bankRecord['partner_id'] = self.partner_id

                        self.logger.info(f'order/Success easypaisa data3: {json.dumps(data)}, r.code: {r['code']}')
                        self.logger.info(f"即将创建银行流水记录: {json.dumps(bankRecord)}")
                        await self.create_result('bank_record', bankRecord)
                        self.logger.info(f"银行流水记录创建成功")
                    finally:
                        # 确保锁最终会被释放
                        await self.redis.delete(lock_key)
                        self.logger.info(f"最终释放分布式锁 {lock_key}")

                    return await self.json_response(r)
                
            elif data['bank_name'] == 'jazzcash':
                self.logger.info('监控调用:(jazzcash协议)' + json.dumps(data))
                # if data['type'] == 'UPI':  # 写入upi,同时启用
                #     if await self.is_null(data, ['type', 'bank_name', 'payment_id', 'partner_id', 'upi']):
                #         return await self.json_response(msg[10001])
                #     # 检测是否有重复的，有重复直接不写入，直接下线
                #     upi_check = await self.check_upi(data['upi'], self.qr_id)
                #     if upi_check:
                #         self.logger.warning('upi重复:{upi},{id},重复的id{id2}'.format(upi=data['upi'],id=upi_check[0]['id'],id2=self.qr_id))
                #         if not await self.update_result('payment', {'remarks': 'upi already exist'}, {'id': self.qr_id}):
                #             self.logger.info('监控调用:(jazzcash协议),更新upi remarks错误'+ json.dumps(upi_check) + json.dumps(data))
                #         msg[10025]['message'] = 'upi already exist'
                #         return await self.json_response(msg[10025])

                #     upi = await self.get_result_by_condition('payment', ['upi', 'status'], {'id': self.qr_id})
                #     if not upi or upi['upi'] != data['upi']:
                #         await self.save_upi_to_history(data['upi'], self.qr_id)
                #         update_arr = {'upi': data['upi'],'upi_list': data['upi_list']}
                #         if 'remarks' in data:
                #             update_arr['remarks'] = data['remarks']
                #         if not await self.update_result('payment', update_arr, {'id': self.qr_id}):
                #             self.logger.info('监控调用:(jazzcash协议),更新upi错误' + json.dumps(data))
                #             return await self.json_response(msg[10018])
                #     if upi['status'] != 1:
                #         if not await self.update_result('payment', {'status': 1}, {'id': self.qr_id}):
                #             self.logger.info('监控调用:(jazzcash协议),更新upi状态错误' + json.dumps(data))
                #             return await self.json_response(msg[10020])
                #     res = dict(type='UPI', code=100, msg='update upi success.')
                #     return await self.json_response(res)
                if data['type'] == 'New':  # 回调相关
                    self.logger.info(f'开始处理“New”类型回调 {data}')
                    if await self.is_null(data, ['type', 'bank_name', 'payment_id', 'partner_id', 'amount', 'trade_type', 'utr', 'trans_id']):
                        self.logger.warning('回调数据缺少关键字段')
                        return await self.json_response(msg[10001])
                    self.logger.info(f"数据校验成功，接收到数据: {json.dumps(data)}")
                    if data['trade_type'] not in ['CREDIT', 'DEBIT']:  # 暂时先回调代收，不回调代付
                        self.logger.info('监控调用:(jazzcash协议),不是入款和出款' + json.dumps(data))
                        return await self.json_response(msg[10001])
                    r = dict()
                    # 入账（收入）
                    lock_key = 'success_busy_{trans_id}'.format(trans_id=data['trans_id'])
                    if data['trade_type'] == 'CREDIT':
                        self.logger.info("处理入账 (CREDIT)")
                        data['trade_type'] = 1
                        # 代收通过utr和金额查找重复订单
                        if await self.get_result_by_condition('bank_record', ['id'], {'trans_id': data['trans_id'], 'utr': data['utr'], 'amount': data['amount'], 'trade_type': 1, 'payment_id': data['payment_id']}):
                            self.logger.warning(f"发现重复的代收订单: UTR={data['utr']}, 金额={data['amount']}")
                            return await self.json_response(msg[10019])
                        self.logger.info(f"调用代收成功处理函数 success_ds")

                        r = await callback.success_ds(self, data)
                    # 出账（支出）
                    elif data['trade_type'] == 'DEBIT':
                        self.logger.info("处理出账 (DEBIT)")
                        data['trade_type'] = 2
                        # 代付通过utr和金额查找重复订单
                        if await self.get_result_by_condition('bank_record', ['id'], {'trans_id': data['trans_id'], 'trade_type': 2, 'payment_id': data['payment_id']}):
                            self.logger.warning(f"发现重复的代付订单: trans_id={data['trans_id']}")
                            return await self.json_response(msg[10019])
                        self.logger.info(f"调用代付成功处理函数 success_df")
                        r = await callback.success_df(self, data)
                    r_code = r.get("code", "")
                    r['code'] = r_code
                    self.logger.info(f'order/Success jazzcash data1: {json.dumps(data)}, r.code: {r['code']}')
                    # 代收回调失败额外扣除
                    # 尝试原子性地获取锁。如果返回0，则表示锁已被其他进程获取。
                    if not await self.redis.setnx(lock_key, '1'):
                        self.logger.info(f"监控调用:(jazzcash协议), {lock_key} 正在被其他进程处理，拒绝当前请求。")
                        return await self.json_response(msg[10019])
                    try:
                        self.logger.info(f"成功获取分布式锁 {lock_key}, 设置过期时间为60秒")
                        await self.redis.expire(lock_key, 60) # 设置过期时间
                        if r['code'] == 99 and data['trade_type'] == 1:
                            self.logger.info("代收回调失败，准备额外扣除商户余额")
                            ew_code = await self.create_order_code('EW')  # 额外流水号
                            async with self.application.db.acquire() as conn:
                                async with conn.cursor(DictCursor) as cur:
                                    if not await self.change_balance(conn, cur, 'partner', data['partner_id'], -Decimal(data['amount']), ew_code, 0):
                                        self.logger.warning('utr:{}Failed to deduct partner balance'.format(data['utr']))
                                        await conn.rollback()
                                    else:
                                        data['ew_code'] = ew_code
                                        data['if_ew'] = '1'
                                        await conn.commit()
                        self.logger.info(f'order/Success jazzcash data2: {json.dumps(data)}, r.code: {r['code']}')
                        bankRecord = dict()
                        for i in ['admin_id', 'payment_id', 'amount', 'trade_type', 'utr', 'code', 'ifsc', 'ew_code', 'if_ew', 'trans_id']:
                            if i in data.keys():
                                bankRecord[i] = data[i]
                        if r['code'] == 100:
                            bankRecord['callback'] = 1
                            bankRecord['order_code'] = r['order']
                        bankRecord['content'] = json.dumps(data)
                        bankRecord['partner_id'] = self.partner_id

                        self.logger.info(f'order/Success jazzcash data3: {json.dumps(data)}, r.code: {r['code']}')
                        self.logger.info(f"即将创建银行流水记录: {json.dumps(bankRecord)}")
                        await self.create_result('bank_record', bankRecord)
                        self.logger.info(f"银行流水记录创建成功")
                    finally:
                        # 确保锁最终会被释放
                        await self.redis.delete(lock_key)
                        self.logger.info(f"最终释放分布式锁 {lock_key}")

                    return await self.json_response(r)
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.info(error_message)
            ret = dict(code=99, msg='data error.')
            return await self.json_response(ret)

    async def check_upi(self, upi, payment_id):
        sql = """select id from payment where upi=%s and id != %s"""
        return await self.query(sql, upi, payment_id)

    # 更新upi到历史
    async def save_upi_to_history(self, upi, payment_id):
        db_payment = await self.get_result_by_condition('payment', ['id', 'partner_id', 'bank_type_id'], {'id': payment_id})
        if db_payment:
            paymnetUpiHistory = dict()
            paymnetUpiHistory['payment_id'] = db_payment.get('id')
            paymnetUpiHistory['partner_id'] = db_payment.get('partner_id')
            paymnetUpiHistory['bank_id'] = db_payment.get('bank_type_id')
            paymnetUpiHistory['upi'] = upi
            paymnetUpiHistory['time_create'] = datetime.now()
            result = await self.create_result('payment_upi_history', paymnetUpiHistory)
            print(f"result payment_upi_history: {result}")

# 机器人回调
class SuccessBot(BaseHandler):
    """获取订单状态"""

    async def post(self):
        try:
            ret = dict(code=99, msg='data error.')
            # 只接受白名单ip访问
            ip = await self.get_ip()
            successBotsAllowIp = await self.redis.get('successBotsAllowIp')
            if not successBotsAllowIp:
                self.logger.warning("未获取到ip白名单")
                return await self.json_response(data=msg[10000])
            else:
                successBotsAllowIp = str(successBotsAllowIp).strip().split(',')
                allow_ip = [i.strip() for i in successBotsAllowIp if i != '']
                if not ip in allow_ip:
                    self.logger.warning("非法ip" + ip)
                    return await self.json_response(data=msg[10000])

            dataJson = self.request.body
            self.logger.info("接收参数" + str(dataJson))
            data = json.loads(dataJson)
            if data['bank_name'] == "AU C":
                amount = 0
                data['debit'] = Decimal(data['debit']) if data['debit'] != '-' else 0
                data['credit'] = Decimal(data['credit']) if data['credit'] != '-' else 0
                if data['debit'] > data['credit']:
                    amount = Decimal('-{}'.format(data['debit']))
                    dataAuAmount = data['debit']
                else:
                    amount = data['credit']
                    dataAuAmount = data['credit']
                dataAu = await self.auParse(data['description'], amount)
                self.logger.info("解析数据" + json.dumps(dataAu))
                if not dataAu:
                    return await self.json_response(data=msg[10021])
                dataAu['type'] = data['type']
                dataAu['bank_name'] = data['bank_name']
                dataAu['partner_id'] = data['partner_id']
                dataAu['amount'] = dataAuAmount
                ret = await self.callBack(dataAu, data['description'])
            elif data['bank_name'] == "NAGERCOIL ENBL":
                amount = 0
                data['debit'] = Decimal(data['debit']) if data['debit'] != '' else 0
                data['credit'] = Decimal(data['credit']) if data['credit'] != '' else 0
                if data['debit'] > data['credit']:
                    amount = Decimal('-{}'.format(data['debit']))
                    dataAuAmount = data['debit']
                else:
                    amount = data['credit']
                    dataAuAmount = data['credit']
                dataNagercol = await self.nagercolParse(data['description'], amount)
                self.logger.info("解析数据" + json.dumps(dataNagercol))
                if not dataNagercol:
                    return await self.json_response(data=msg[10021])
                dataNagercol['type'] = data['type']
                dataNagercol['bank_name'] = data['bank_name']
                dataNagercol['partner_id'] = data['partner_id']
                dataNagercol['amount'] = dataAuAmount
                ret = await self.callBack(dataNagercol, data['description'])
            self.logger.info("返回数据"+str(ret))
            return await self.json_response(ret)
        except Exception as e:
            self.logger.exception("机器人回调失败:" + str(e))
            ret = dict(code=99, msg='data error.')
            return await self.json_response(ret)

    # 银行回调
    async def callBack(self, data, description):
        try:
            orders, r = await self.ordersDfQuery(data)
            if r['code'] == 99:
                self.logger.warning("订单查询异常data:{data}".format(data=simplejson.dumps(data)))
                return r
            data['payment_id'] = orders[0]["payment_id"]
            self.qr_id = data['payment_id']
            self.partner_id = data['partner_id']
            if data['type'] == 'New':  # 回调相关
                r = dict()
                self.logger.info('机器人调用:(银行{bank_name}),id:{id}, 获取ifsc：{ifsc}， 账户尾号:{code}'.format(bank_name=data['bank_name'], id=self.qr_id, ifsc=data['ifsc'], code=data['code']))
                if data['trade_type'] == 2:
                    if await self.get_result_by_condition('bank_record', ['*'],{'utr': data['utr'], 'amount': data['amount'],'trade_type': 2}):
                        self.logger.info("bank_record已存在记录data:{data}".format(data=simplejson.dumps(data)))
                        return msg[10019]

                    r = await callback.success_df(self, data)
                    self.logger.info("代付回调返回:" + json.dumps(r))
                else:
                    # 暂时回调代付的，其他的不理
                    return msg[10020]
                bankRecord = dict()
                for i in ['admin_id', 'payment_id', 'amount', 'trade_type', 'utr', 'code', 'ifsc', 'ew_code']:
                    if i in data.keys():
                        bankRecord[i] = data[i]
                if r['code'] == 100:
                    bankRecord['callback'] = 1
                    bankRecord['order_code'] = r['order']
                bankRecord['content'] = description
                bankRecord['partner_id'] = self.partner_id
                await self.create_result('bank_record', bankRecord)
                return r
        except Exception as e:
            self.logger.exception(e)
            ret = dict(code=99, msg='data error.')
            return ret

    # au银行数据解析
    async def auParse(self, content, amount):
        data = dict()
        try:
            # 转入(UPI/IMPS/NEFT)
            if content[:6] == 'UPI/CR' or (content[:5] == 'IMPS-' and Decimal(amount) > Decimal(0)) or (
                    'NEFT' in content and Decimal(amount) > Decimal(0)):
                contents = content.split('/')
                data['trade_type'] = 1
                data['utr'] = contents[2]
                data['code'] = contents[6][:5]
            # 转出(UPI/IMPS/NEFT)
            if (content[:7] == 'UPI/DR/' and Decimal(amount) < Decimal(0)) or (
                    content[:5] == 'IMPS-' and Decimal(amount) < Decimal(0)):
                data['trade_type'] = 2
                if 'UPI' in content:
                    contents = content.split('/')
                    data['utr'] = contents[2]
                    data['ifsc'] = contents[4]
                    data['code'] = contents[5][-4:]
                elif 'IMPS' in content:
                    contents = content.split('-')
                    data['utr'] = contents[1]
                    data['ifsc'] = contents[3]
                    data['code'] = contents[4][-4:]
                # else:
                #     contents = content.split('-')
                #     data['utr'] = contents[1].strip(' ')
            # 退回(UPI/IMPS)
            elif content[:10] == 'UPI/DR-REV' or 'RETURN IMPS' in content:
                data['trade_type'] = 3
                if 'UPI' in content:
                    contents = content.split('/')
                    data['utr'] = contents[2]
                    data['ifsc'] = contents[4]
                    data['code'] = contents[5]
                else:
                    contents = content.split('-')
                    data['utr'] = contents[1]
                    data['ifsc'] = contents[3]
                    data['code'] = contents[4]
            # 手续费
            elif 'IMPS OUTWARD CHARGE' in content:
                data['trade_type'] = 4
            return data
        except Exception as e:
            self.logger.exception("解析失败:" + str(e) + content)
            return False

    # nagercol银行数据解析
    async def nagercolParse(self, content, amount):
        data = dict()
        try:
            # 转出(UPI/IMPS/NEFT)
            if content[:5] == 'IMPS-' and Decimal(amount) < Decimal(0):
                data['trade_type'] = 2
                if 'IMPS' in content:
                    contents = content.split('/')
                    data['utr'] = contents[1]
                    data['ifsc'] = contents[2]
                    data['code'] = contents[3]
                # else:
                #     contents = content.split('-')
                #     data['utr'] = contents[1].strip(' ')
            return data
        except Exception as e:
            self.logger.exception("解析失败:" + str(e))
            return False

    # 代付订单查询
    async def ordersDfQuery(self, data):
        amount = abs(Decimal(data['amount']))
        if data['bank_name'] == 'AU C':
            condition = ' and ifsc=%s and right(payment_account,4)=%s and partner_id=%s'
            value = (amount, data['ifsc'], data['code'][-4:], data['partner_id'])
        elif data['bank_name'] == 'NAGERCOIL ENBL':
            condition = ' and ifsc=%s and payment_account=%s and partner_id=%s'
            value = (amount, data['ifsc'], data['code'], data['partner_id'])
        else:
            condition = ' and left(ifsc,4)=%s and right(payment_account,4)=%s' if data['ifsc'] else ''
            value = (amount, data['ifsc'][:4], data['code'][-4:]) if data['ifsc'] else (amount, data['code'][-4:])
        # 通过IFSC前四位和银行卡后四位查找订单
        sql_select_order = """select * from orders_df where amount=%s{condition} and status
                                in (-1,1,2) and date_add(time_accept, interval 3 hour ) > now() order by id limit 1""".format(
            condition=condition)
        _order = await self.query(sql_select_order, *value)
        if not _order:
            self.logger.info('机器人调用:(查找订单),sql语句:{sql_select_order}, sql值：{value}'.format(
                sql_select_order=sql_select_order, value=value))
            return _order, dict(code=99, msg='Order not found')
        return _order, dict(code=100, msg='ok')
