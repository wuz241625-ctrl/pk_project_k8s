import decimal
from datetime import datetime
from urllib import parse

import pytz
import razorpay
from application.base import BaseHandler
import simplejson as json
from .success import order_success_ds, order_success_ds_third
import hashlib
import requests

from requests.adapters import HTTPAdapter
from urllib.parse import urlencode, quote

from application.sign import SignatureAndVerification
import time
import random
from urllib.parse import urlparse


class NoticeRazorpay_upi_origin(BaseHandler):
    async def post(self):
        sql_t = 'select merchant_id,`key`,key2,key3,pay_url,name,channel_code,query_url,notify_ip from otherpay where name = %s'
        r_t = await self.query(sql_t, 'Razorpay-upi-origin')
        self.set_status(403)
        # 检查是否设定的回调ip
        if not r_t[0]['notify_ip']:
            self.logger.error('无回调通知ip，请加回调通知ip Razorpay-upi-origin')
            return self.write('not notify_ip')
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error('ip:{ip} ,回调ip错误 Razorpay-upi-origin'.format(ip=ip))
            return self.write('notify_ip error')

        mc_key = r_t[0]['key']
        mc_key2 = r_t[0]['key2']
        mer_id = r_t[0]['merchant_id']

        try:
            webhook_body = str(self.request.body, encoding="utf-8")
            client = razorpay.Client(auth=(mc_key, mc_key2))
            webhook_secret = mc_key2
            webhook_signature = self.request.headers.get('X-Razorpay-Signature')
            verify_sign = client.utility.verify_webhook_signature(webhook_body, webhook_signature, webhook_secret)
            if not verify_sign:
                return self.write('sign error')
            data = json.loads(webhook_body)
            self.logger.info('Razorpay-upi-origin 收到回调参数{data}'.format(data=str(data)))

            if not data['payload']['payment_link']['entity']['status'] == "paid":
                return self.write('not success')
            if not "acc_" + mer_id == data['account_id']:
                return self.write('merchant_id error')

            code = data['payload']['payment_link']['entity']['reference_id']
            amount = decimal.Decimal(data['payload']['payment_link']['entity']['amount'])/100
            # 若订单已经成功了，则直接返回回调成功
            sql_order_info = 'select code, amount, partner_id, payment_id,status from orders_ds  where code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error('Razorpay-upi-origin-错误，无此订单 %s' % code)
                return await self.json_response({'success': False, 'message': 'error 无此订单'})

            if _order_info[0]['status'] > 2:
                self.logger.error('Razorpay-upi-origin-订单已经回调成功过 %s,确认成功' % code)
                self.set_status(200)
                return self.write('SUCCESS')

            if not decimal.Decimal(_order_info[0]['amount']) == amount:
                self.logger.error('错误：Razorpay-upi-origin-查询订单{code},金额不一致，订单金额为{ret}'.format(code=code, ret=amount))
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})
        except Exception as e:
            self.logger.exception('参数异常:' + str(e))
            return self.write('params error')

        if not await order_success_ds(self, code):
            # 删除操作的key，防止回调占用
            busy_key = 'order_success_busy_{code}'.format(code=code)
            await self.redis.delete(busy_key)
            self.logger.error('错误：Razorpay-upi-origin-订单{code}，更新失败'.format(code=code))
            return self.write('upadate order error')
        self.logger.info('Razorpay-upi-origin-订单 %s,确认成功' % code)
        self.set_status(200)
        return self.write('SUCCESS')

class lucky_notify(BaseHandler):
    async def post(self):
        # 打印接收到的所有 form-data 参数
        self.logger.info("[lucky] 开始处理 lucky 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, 'lucky')
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[lucky] 无回调通知 IP，请加回调通知 IP lucky_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[lucky] IP: {ip}, 回调 IP 错误 lucky_notify')
            return self.write('notify_ip error')

        mc_key = r_t[0]['key']
        mc_key2 = r_t[0]['key2']
        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 从 form-data 获取并打印所有参数
            webhook_body = self.request.body_arguments  # 获取所有 form-data 参数
            self.logger.info("[lucky] 接收到的参数:", webhook_body)  # 打印接收的参数

            # 将字节参数转换为字符串格式，确保签名计算时一致
            webhook_body = {
                key: [item.decode('utf-8') if isinstance(item, bytes) else item for item in value]
                for key, value in webhook_body.items()
            }
            self.logger.info("[lucky] 转换后的参数:", webhook_body)  # 打印转换后的参数
            # 提取所需的参数
            client_code = webhook_body.get('clientCode', [''])[0]
            client_no = webhook_body.get('clientNo', [''])[0]
            order_no = webhook_body.get('orderNo', [''])[0]
            chain_name = webhook_body.get('chainName', [''])[0]
            coin_unit = webhook_body.get('coinUnit', [''])[0]
            pay_amount = webhook_body.get('payAmount', [''])[0]
            status = webhook_body.get('status', [''])[0]
            txid = webhook_body.get('txid', [''])[0]
            received_sign = webhook_body.get('sign', [''])[0]
            # 拼接签名字符串并计算签名
            sign_str = f"{client_code}&{client_no}&{order_no}&{pay_amount}&{status}&{txid}{mc_key2}"
            calculated_sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()

            # 验证签名
            if received_sign != calculated_sign:
                self.logger.error(f"[lucky] 签名错误: 接收到的签名 {received_sign}, 计算的签名 {calculated_sign}")
                return self.write('sign error')

            # 获取参数并解析
            code = client_no
            amount = decimal.Decimal(pay_amount)
            account_id = mer_id

            self.logger.info(f'[lucky] lucky_notify 收到回调参数 {webhook_body}')

            # 生成签名
            sign_string = f"{client_code}&{client_no}{mc_key2}"
            sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()

            # 发起 GET 请求到查询接口
            params = {
                'clientCode': client_code,
                'clientNo': client_no,
                'sign': sign
            }

            # 设置请求头
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
                "Content-Type": "application/json"
            }

            # 发起 GET 请求并传递参数
            response = requests.get(query_url, params=params, headers=headers, timeout=(5, 5), verify=False)

            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}')

            # 处理查询返回的数据
            if response.status_code == 200:
                result = response.json()
                if result.get("success") and result.get("code") == 200:
                    data = result.get("data", {})
                    order_status = data.get("status")
                    pay_url = data.get("payUrl")

                    # 在处理订单时使用查询结果
                    if order_status == "PAID":
                        self.logger.info(f"订单已支付。支付链接: {pay_url}")
                        # 进行下一步处理
                    else:
                        self.logger.error(f"订单状态: {order_status}")
                        return self.write(f"订单状态: {order_status}")
                else:
                    self.logger.error("查询失败:", result.get("code"), result.get("message"))
                    return self.write("查询失败:", result.get("code"), result.get("message"))
            else:
                self.logger.error("请求失败，状态码:", response.status_code)
                return self.write("请求失败，状态码:", response.status_code)

            # 检查支付状态和 merchant_id
            if status != "PAID":
                return self.write('not ok')
            if not account_id == webhook_body.get('clientCode', [''])[0]:
                return self.write('merchant_id error')

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error(f'[lucky] lucky_notify-错误，无此订单 {code}')
                return await self.json_response({'success': False, 'message': 'error 无此订单'})

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[lucky] lucky_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('ok')

            # 检查金额
            if not decimal.Decimal(_order_info[0]['amount']) == amount:
                self.logger.error(f'[lucky] 错误：lucky_notify-查询订单 {code}, 金额不一致，订单金额为 {amount}')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        except Exception as e:
            self.logger.exception(f'[lucky] 参数异常: {str(e)}')
            return self.write('params error')

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[lucky] 错误：lucky_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[lucky] lucky_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('ok')


class ApayNotify(BaseHandler):
    async def post(self):
        try:
            # 打印接收到的所有 form-data 参数
            self.logger.info("[apay] 开始处理 apay 回调通知")
            # 从 form-data 获取并打印所有参数
            webhook_body = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info(f'[apay] apay_notify 收到回调参数 {webhook_body}')
            sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE merchant_id = %s'
            r_t = await self.query(sql_t, webhook_body.get('cid'))
            self.set_status(403)

            # 检查是否设定的回调 IP
            if not r_t[0]['notify_ip']:
                self.logger.error('[apay] 无回调通知 IP，请加回调通知 IP apay_notify')
                return self.write('not notify_ip')
            ips = r_t[0]['notify_ip'].split(',')
            ip = await self.get_ip()
            if ip not in ips:
                self.logger.error(f'[apay] IP: {ip}, 回调 IP 错误 apay_notify')
                return self.write('notify_ip error')

            mc_key = r_t[0]['key']
            mer_id = r_t[0]['merchant_id']
            query_url = r_t[0]['query_url']

            sign = webhook_body.pop('sign')
            sign = sign.upper()
            # 验证签名
            if not SignatureAndVerification.md5_verify(webhook_body, sign, mc_key):
                self.logger.error(f"[apay] 签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')

            # 获取参数并解析
            code = webhook_body.get('tradeNo')
            amount = decimal.Decimal(webhook_body.get('amount'))
            account_id = mer_id

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['cid'] = webhook_body['cid']
            data_post['tradeNo'] = webhook_body['tradeNo']
            data_post['type'] = '003'

            data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key)
            data_post['sign'] = data_post['sign'].lower()

            # 发起 POST 请求并传递参数0
            response = requests.post(query_url, data=data_post, timeout=(5, 5), verify=False)

            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}')

            # 处理查询返回的数据
            if response.status_code == 200:
                result = response.json()
                if result.get("retcode") == '0':
                    order_status = result.get("status")

                    # 在处理订单时使用查询结果
                    if order_status == "1":
                        self.logger.info(f"订单已支付。支付订单： {code}")
                    else:
                        self.logger.error(f"订单状态: {order_status}")
                        return self.write(f"订单状态: {order_status}")
                else:
                    self.logger.error("查询失败: {} {}".format(result.get("retcode"), result.get("status")))
                    return self.write("查询失败: {} {}".format(result.get("retcode"), result.get("status")))
            else:
                self.logger.error("请求失败，状态码:", response.status_code)
                return self.write("请求失败，状态码:", response.status_code)

            # 检查merchant_id
            if account_id != webhook_body.get('cid'):
                return self.write('merchant_id error')

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error(f'[apay] apay_notify-错误，无此订单 {code}')
                return await self.json_response({'success': False, 'message': 'error 无此订单'})

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[apay] apay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('SUCCESS')

            # 检查金额
            if not int(decimal.Decimal(_order_info[0]['amount']) * 100) == amount:
                self.logger.error(f'[apay] 错误：apay_notify-查询订单 {code}, 金额不一致，订单金额为 {amount}')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        except Exception as e:
            self.logger.exception(f'[apay] 参数异常: {str(e)}')
            return self.write('params error')

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[apay] 错误：apay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[apay] apay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('SUCCESS')
class kingpay_notify(BaseHandler):
    pay_name = 'kingpay'
    async def post(self):
        self.logger.info("[kingpay] 开始处理 kingpay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, self.pay_name)
        self.set_status(403)
        if not r_t[0]['notify_ip']:
            self.logger.error('[kingpay] 无回调通知 IP，请加回调通知 IP kingpay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[kingpay] IP: {ip}, 回调 IP 错误 kingpay_notify')
            return self.write('notify_ip error')

        app_id = r_t[0]['key']
        public_key = r_t[0]['key2']
        private_key = r_t[0]['key3']
        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']
        try:
            data_receive = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info('[kingpay] data_receive-收到回调参数{data},{ip}'.format(data=str(data_receive), ip=ip))
            data = data_receive
            data['payTime'] = ''
            # 验签
            is_verify = SignatureAndVerification.verify_sha256_sign(public_key, data, data['sign'])
            if not is_verify:
                self.logger.error('[kingpay] 验签错误')
                return self.write('sign error')
            self.logger.info('[kingpay] 验签正确')
            # 参与签名的字段和对应值
            sign_fields = {
                'merchantId': mer_id,
                'appId': app_id,
                'timestamp': int(time.time() * 1000),  # 13-digit timestamp
                'outOrderId': data['outOrderId'],
                'orderId': ''
            }
            # Prepare data for query interface
            request_data = {
                'merchantId': mer_id,
                'appId': app_id,
                'timestamp': int(time.time() * 1000),  # 13-digit timestamp
                'outOrderId': data['outOrderId'],
                "sign": SignatureAndVerification.sha256_sign(sign_fields, private_key, True),
            }
            # 发送 POST 请求
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) '
                            'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 '
                            'UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 '
                            'NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) '
                            'AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            data_post = json.dumps(request_data)
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5,10))

            # 处理响应
            # print("request_data:", data_post)
            # print("Status Code:", response.status_code)
            # print("Response Data:", response.json())
            # 解析返回数据
            result = response.json()
            self.logger.info(f'kingpay_payment 发送地址{query_url},返回数据{result}')

            if response.status_code == 200:
                if result.get("code") == "0":
                    order_status = result.get("status")
                    # Process order status
                    if order_status == 4:  # Paid status
                        self.logger.info(f"订单已支付")
                    else:
                        self.logger.error(f"订单状态: {order_status}")
                        return self.write({"code": "1", "message": "失败"})
                else:
                    self.logger.error("查询失败:", result.get("code"), result.get("message"))
                    return self.write({"code": "1", "message": "失败"})
            else:
                self.logger.error("请求失败，状态码:", response.status_code)
                return self.write({"code": "1", "message": "请求失败"})

            # Check the status and merchant ID from the callback
            if data['status'] != 4:
                return self.write({"code": "1", "message": "not ok"})

            # 查询订单
            code = data['outOrderId']
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error(f'[kingpay] kingpay_notify-错误，无此订单 {code}')
                return self.write({"code": "1", "message": "error 无此订单"})

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.info(f'[kingpay] kingpay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write({"code": "0", "message": "success"})

            # 检查金额是否一致
            if not decimal.Decimal(_order_info[0]['amount']) == decimal.Decimal(data['amount']):
                self.logger.error(f'[kingpay] 错误：kingpay_notify-查询订单 {code}, 金额不一致')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

        except Exception as e:
            self.logger.exception(f'[kingpay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        if not await order_success_ds_third(self, code):
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[kingpay] 错误：kingpay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[kingpay] kingpay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write({"code": "0", "message": "success"})


class KingpayNotify2(kingpay_notify):
    pay_name = 'kingpay2'

class wepay_notify(BaseHandler):
    async def post(self):
        self.logger.info("[wepay] 开始处理 wepay 回调通知")

        # 查询商户配置
        sql_t = ('SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, '
                 'query_url, notify_ip FROM otherpay WHERE name = %s')
        r_t = await self.query(sql_t, 'wepay')

        # 默认拒绝请求
        self.set_status(403)

        # test
        # ip = '1.1.1.1'
        # 检查是否有回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[wepay] 无回调通知 IP，请加回调通知 IP wepay_notify')
            return self.write('not notify_ip')

        # 校验回调 IP
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[wepay] IP: {ip}, 回调 IP 错误 wepay_notify')
            return self.write('notify_ip error')

        # 获取密钥
        private_key = r_t[0]['key']

        try:
            # 解析回调数据
            data_receive = {k: v[0].decode('utf-8') for k, v in self.request.arguments.items()}
            self.logger.info(f'[wepay] data_receive-收到回调参数: {data_receive}, 来自 IP: {ip}')

            # 校验签名
            sign_valid = self.verify_md5_signature(data_receive, private_key)
            if not sign_valid:
                self.logger.error('[wepay] 验签错误')
                return self.write('sign error')

            self.logger.info('[wepay] 验签正确')

            # 判断订单支付状态
            if str(data_receive.get('tradeResult')) != '1':
                self.logger.error('[wepay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

            # 获取订单号
            code = data_receive['mchOrderNo']

            # 查询订单
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[wepay] wepay_notify-错误，无此订单 {code}')
                return self.write({"code": "1", "message": "error 无此订单"})

            # 检查订单是否已处理
            if _order_info[0]['status'] > 2:
                self.logger.info(f'[wepay] wepay_notify-订单 {code} 已回调成功，确认成功')
                self.set_status(200)
                return self.write("success")

            # 校验金额
            if decimal.Decimal(_order_info[0]['amount']) != decimal.Decimal(data_receive['amount']):
                self.logger.error(f'[wepay] 订单 {code} 金额不一致')
                return await self.json_response({'success': False, 'message': 'error 金额不一致'})

            # **新加：查询订单，确保回调数据的正确性**
            query_status = await self.query_order_status(r_t[0]['merchant_id'], data_receive['mchOrderNo'], private_key, r_t[0]['query_url'])
            self.logger.error(f"[wepay] -查询订单返回值-{query_status}")
            self.logger.error(f"[wepay] -通知返回返回值-{data_receive.get("tradeResult")}")
            if query_status is None:
                return self.write("error: query failed")
            if query_status != str(data_receive.get("tradeResult")):
                self.logger.error(f"[wepay] 回调状态 {data_receive['tradeResult']} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

        except Exception as e:
            self.logger.exception(f'[wepay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 更新订单状态
        if not await order_success_ds_third(self, code):
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[wepay] 订单 {code} 更新失败')
            return self.write('update order error')

        self.logger.info(f'[wepay] wepay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write("success")

    async def query_order_status(self, mch_id, mer_transfer_id, mch_key, query_url):
        """ 查询订单状态 """
        params = {
            "mch_id": mch_id,
            "mch_order_no": mer_transfer_id,
            "sign_type": "MD5",
        }

        # 生成 MD5 签名
        params["sign"] = self.generate_md5_sign(params, mch_key)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        s = requests.Session()
        s.mount("http://", HTTPAdapter(max_retries=3))
        s.mount("https://", HTTPAdapter(max_retries=3))

        try:
            response = s.post(query_url, data=urlencode(params), headers=headers, timeout=(5, 5))
            self.logger.info(f"查询订单 {mer_transfer_id}, 返回结果: {response.text}")

            if response.status_code != 200:
                self.logger.error(f"查询订单 {mer_transfer_id} 失败，HTTP 状态码: {response.status_code}")
                return None

            res_data = response.json()
            if res_data.get("respCode") != "SUCCESS":
                self.logger.error(f"查询订单 {mer_transfer_id} 失败, 返回: {res_data}")
                return None

            return str(res_data.get("tradeResult"))  # 返回交易状态

        except Exception as e:
            self.logger.error(f"查询订单 {mer_transfer_id} 发生异常: {e}")
            return None

        finally:
            s.close()

    def generate_md5_sign(self, params, private_key):
        """
        生成 WePay 签名
        :param params: 需要签名的参数字典 (不包含 sign 和 sign_type)
        :param private_key: 商户私钥
        :return: MD5 签名 (小写)
        """
        # 过滤掉 sign 和 sign_type，并移除值为空的字段
        filtered_params = {k: v for k, v in params.items() if k not in ["sign", "sign_type"] and v}

        # 按照 **ASCII 码** 升序排序
        sorted_params = sorted(filtered_params.items())

        # 按照 `k=v&k=v` 格式拼接字符串
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        # 在字符串后面拼接商户私钥 `&key=x`
        query_string += f"&key={private_key}"

        # print("请求参数签名串：", query_string)  # 打印待签名字符串

        # 进行 MD5 加密，并转换为小写
        md5_hash = hashlib.md5(query_string.encode('utf-8')).hexdigest().lower()

        return md5_hash

    def verify_md5_signature(self, params, private_key):
        """
        校验 MD5 签名
        :param params: 回调参数 (dict)
        :param private_key: 商户私钥
        :return: bool
        """
        # 过滤掉 sign 和 signType
        filtered_params = {k: v for k, v in params.items() if k not in ["sign", "signType"]}

        # 按 ASCII 码排序并拼接
        sorted_params = sorted(filtered_params.items())
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)

        # 拼接密钥
        query_string += f"&key={private_key}"

        self.logger.info(f"[wepay] 计算签名字符串: {query_string}")

        # 计算 MD5 并转换为小写
        calculated_sign = hashlib.md5(query_string.encode('utf-8')).hexdigest().lower()

        # 比较签名
        return calculated_sign == params.get("sign", "").lower()


class Pay777PayNotify(BaseHandler):
    async def post(self):
        # 打印接收到的所有 form-data 参数
        self.logger.info("[777Pay] 开始处理 777Pay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, '777Pay')
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[777Pay] 无回调通知 IP，请加回调通知 IP 777Pay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[777Pay] IP: {ip}, 回调 IP 错误 777Pay_notify')
            return self.write('notify_ip error')

        mc_key = r_t[0]['key']
        mc_key2 = r_t[0]['key2']
        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 从 form-data 获取并打印所有参数
            webhook_body = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info(f'[777Pay] data_receive-收到回调参数: {webhook_body}, 来自 IP: {ip}')
            # sign = webhook_body.pop('sign')
            # sign = sign.upper()
            # # 验证签名
            # if not SignatureAndVerification.md5_verify(webhook_body, sign, mc_key):
            #     self.logger.error(f"[777Pay] 签名错误: 接收到的签名 {sign}, ip: {ip}")
            #     return self.write('sign error')

            self.logger.info(f'[777Pay] 777Pay_notify 收到回调参数 {webhook_body}')
            # 获取参数并解析
            code = webhook_body.get('merchant_order_id')
            amount = decimal.Decimal(webhook_body.get('amount'))
            account_id = mer_id

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error(f'[777Pay] 777Pay_notify-错误，无此订单 {code}')
                return await self.json_response({'success': False, 'message': 'error 无此订单'})
            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[777Pay] 777Pay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('success')

            # 检查merchant_id
            if account_id != webhook_body.get('app_id'):
                return self.write('merchant_id error')

            # 检查金额
            if not decimal.Decimal(_order_info[0]['amount']) == amount:
                self.logger.error(f'[777Pay] 错误：777Pay_notify-查询订单 {code}, 金额不一致，订单金额为 {amount}')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['app_id'] = mer_id
            data_post['merchant_order_id'] = code
            data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key)
            data_post['sign'] = data_post['sign'].lower()

            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}')

            # 处理查询返回的数据
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f'query_order 查询结果: {result}')
                if str(result.get("code")) == '200':
                    order_status = result.get("data", {}).get('order_status')

                    # 在处理订单时使用查询结果
                    if order_status == "PAY_SUCCESS" and order_status == webhook_body.get('order_status'):
                        self.logger.info(f"订单已支付。支付订单： {code}")
                    else:
                        self.logger.error(f"订单状态: {order_status}")
                        return self.write(f"订单状态: {order_status}")
                else:
                    self.logger.error("查询失败: {} {}".format(result.get("code"), result.get("message")))
                    return self.write("查询失败: {} {}".format(result.get("code"), result.get("message")))
            else:
                self.logger.error("请求失败，状态码:", response.status_code)
                return self.write("请求失败，状态码:", response.status_code)

        except Exception as e:
            self.logger.exception(f'[777Pay] 参数异常: {str(e)}')
            return self.write('params error')

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[777Pay] 错误：777Pay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[777Pay] 777Pay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('success')


class SwiftPayNotify(BaseHandler):
    async def post(self):
        # 打印接收到的所有 form-data 参数
        self.logger.info("[SwiftPay] 开始处理 SwiftPay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, 'swiftpay')
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[SwiftPay] 无回调通知 IP，请加回调通知 IP SwiftPay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[SwiftPay] IP: {ip}, 回调 IP 错误 SwiftPay_notify')
            return self.write('notify_ip error')

        mc_key = r_t[0]['key']
        mc_key2 = r_t[0]['key2']
        mc_key3 = r_t[0]['key3']
        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 从 form-data 获取并打印所有参数
            webhook_body = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info(f'[SwiftPay] data_receive-收到回调参数: {webhook_body}, 来自 IP: {ip}')
            sign = webhook_body.pop('sign')
            # 验证签名
            if not SignatureAndVerification.verify_sha1_sign(mc_key2, webhook_body, sign):
                self.logger.error(f"[SwiftPay] 签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')

            self.logger.info(f'[SwiftPay] SwiftPay_notify 收到回调参数 {webhook_body}')
            # 获取参数并解析
            code = webhook_body.get('orderId')
            amount = decimal.Decimal(webhook_body.get('payment'))
            account_id = mer_id

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error(f'[SwiftPay] SwiftPay_notify-错误，无此订单 {code}')
                return await self.json_response({'success': False, 'message': 'error 无此订单'})
            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[SwiftPay] SwiftPay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('success')

            # 检查merchant_id
            if account_id != webhook_body.get('merchantNo'):
                return self.write('merchant_id error')

            # 检查金额
            if not decimal.Decimal(_order_info[0]['amount']) == amount:
                self.logger.error(f'[SwiftPay] 错误：SwiftPay_notify-查询订单 {code}, 金额不一致，订单金额为 {amount}')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['merchantNo'] = mer_id
            data_post['orderId'] = code
            data_post['sign'] = SignatureAndVerification.sha1_sign(data_post, mc_key3)
            data_post = json.dumps(data_post)

            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
                'Content-Type': 'application/json'
            }

            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}; 请求参数： {data_post}')

            # 处理查询返回的数据
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f'query_order 查询结果: {result}')
                if str(result.get("errNo")) == '0':
                    order_status = str(result.get("data", {}).get('status'))

                    # 在处理订单时使用查询结果  0已创建，1支付中，2支付成功，3支付超时
                    if order_status == "2" and order_status == webhook_body.get('status'):
                        self.logger.info(f"订单已支付。支付订单： {code}")
                    else:
                        self.logger.error(f"订单状态: {order_status}")
                        return self.write(f"订单状态: {order_status}")
                else:
                    self.logger.error("查询失败: {} {}".format(result.get('data', {}).get("orderId"), result.get("errStr")))
                    return self.write("查询失败: {} {}".format(result.get('data', {}).get("orderId"), result.get("errStr")))
            else:
                self.logger.error("请求失败，状态码:", response.status_code)
                return self.write("请求失败，状态码:", response.status_code)

        except Exception as e:
            self.logger.exception(f'[SwiftPay] 参数异常: {str(e)}')
            return self.write('params error')

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[SwiftPay] 错误：SwiftPay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[SwiftPay] SwiftPay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('success')

class quickpay_notify(BaseHandler):
    async def post(self):
        self.logger.info("[quickpay] 开始处理 quickpay 回调通知")

        # 查询商户配置
        sql_t = ('SELECT merchant_id, `key`, pay_url, name, query_url, notify_ip, key2, key3 FROM otherpay WHERE name = %s')
        r_t = await self.query(sql_t, 'quickpay')

        # 默认拒绝请求
        self.set_status(403)

        if not r_t or not r_t[0].get('notify_ip'):
            self.logger.error('[quickpay] 无回调通知 IP，请加回调通知 IP quickpay_notify')
            return self.write('not notify_ip')

        # 校验回调 IP
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[quickpay] IP: {ip}, 回调 IP 错误 quickpay_notify')
            return self.write('notify_ip error')

        # 获取密钥
        key2 = r_t[0]['key2']
        key3 = r_t[0]['key3']

        try:
            # 解析回调数据
            data_receive = json.loads(self.request.body)
            self.logger.info(f'[quickpay] data_receive-收到回调参数: {data_receive}, 来自 IP: {ip}')

            # 校验签名
            if not SignatureAndVerification.verify_rsasha1_sign(key2, data_receive, data_receive["sign"]):
            # if not sign_valid:
                self.logger.error('[quickpay] 验签错误')
                return self.write('sign error')

            self.logger.info('[quickpay] 验签正确')

            # 先查询订单状态，确保回调数据的正确性
            query_status = await self.query_order_status(
                r_t[0]['merchant_id'],
                data_receive.get('orderId'),
                key3,
                r_t[0]['query_url']
            )
            self.logger.info(f"[quickpay] 查询订单返回值: {query_status}")
            self.logger.info(f"[quickpay] 回调通知状态: {data_receive.get('status')}")

            if query_status is None:
                return self.write("error: query failed")

            if query_status != str(data_receive.get("status")):
                self.logger.error(f"[quickpay] 回调状态 {data_receive['status']} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

            # 判断订单支付状态
            if str(data_receive.get('status')) != "2":  # 2 表示支付成功
                self.logger.error('[quickpay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

            # 获取订单号
            code = data_receive['orderId']

            # 查询订单
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[quickpay] quickpay_notify-错误，无此订单 {code}')
                return self.write({"code": "1", "message": "error 无此订单"})

            # 检查订单是否已处理
            # 在处理订单时使用查询结果  0已创建，1支付中，2支付成功，3支付超时
            if str(data_receive.get('status')) == "2":
                self.logger.info(f"订单已支付。支付订单： {code}")
            else:
                self.logger.error(f"订单状态: {data_receive.get('status')}")
                return self.write(f"订单状态: {data_receive.get('status')}")

            # 校验金额
            self.logger.info(f"[quickpay] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[quickpay] payment: {data_receive['payment']}")
            if str(int(decimal.Decimal(_order_info[0]['amount']))) != str(int(decimal.Decimal(data_receive['payment']))):
                self.logger.error(f'[quickpay] 订单 {code} 金额不一致')
                return self.write('error 金额不一致')

        except Exception as e:
            self.logger.exception(f'[quickpay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 更新订单状态
        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[quickpay] 错误：quickpay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[quickpay] SwiftPay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('success')

    async def query_order_status(self, merchant_no, order_id, private_key, query_url):
        """
        代收订单查询
        """
        params = {
            "merchantNo": merchant_no,
            "orderId": order_id,
        }

        # 生成签名
        params["sign"] = SignatureAndVerification.rsa_sha1_sign(params, private_key)

        headers = {"Content-Type": "application/json"}
        params = json.dumps(params)
        try:
            self.logger.info(f'QuickPay 发送地址 {query_url}, 发送数据 {params}')
            response = requests.post(query_url, data=params, headers=headers, timeout=(5, 10))
            self.logger.info(f"查询订单 {order_id}, 返回结果: {response.text}")

            if response.status_code != 200:
                self.logger.error(f"查询订单 {order_id} 失败，HTTP 状态码: {response.status_code}")
                return None

            res_data = response.json()
            if res_data.get("errNo") != "0":
                self.logger.error(f"查询订单 {order_id} 失败, 返回: {res_data}")
                return None

            return str(res_data["data"]["status"])  # 返回订单状态

        except Exception as e:
            self.logger.error(f"查询订单 {order_id} 发生异常: {e}")
            return None


class SnakePayNotify(BaseHandler):
    async def post(self):
        # 打印接收到的所有 form-data 参数
        self.logger.info("[SnakePay] 开始处理 SnakePay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, 'snakepay')
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[SnakePay] 无回调通知 IP，请加回调通知 IP SnakePay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[SnakePay] IP: {ip}, 回调 IP 错误 SnakePay_notify')
            return self.write('notify_ip error')

        mc_key = r_t[0]['key']
        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 从 form-data 获取并打印所有参数
            webhook_body = json.loads(self.request.body, parse_float=decimal.Decimal)
            self.logger.info(f'[SnakePay] data_receive-收到回调参数: {webhook_body}, 来自 IP: {ip}')
            # 获取参数并解析
            code = webhook_body.get('orderNo')
            amount = decimal.Decimal(webhook_body.get('amount'))
            account_id = mer_id

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)
            if not _order_info:
                self.logger.error(f'[SnakePay] SnakePay_notify-错误，无此订单 {code}')
                return await self.json_response({'success': False, 'message': 'error 无此订单'})
            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[SnakePay] SnakePay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('ok')

            # 检查merchant_id
            if account_id != str(webhook_body.get('merchantNo')):
                return self.write('merchant_id error')

            # 检查金额
            if not decimal.Decimal(_order_info[0]['amount']) == amount:
                self.logger.error(f'[SnakePay] 错误：SnakePay_notify-查询订单 {code}, 金额不一致，订单金额为 {amount}')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['merchantNo'] = mer_id
            data_post['utr'] = webhook_body['utr']
            data_post['sign'] = SignatureAndVerification.hmac_sha256_sign(data_post, mc_key)
            data_post = json.dumps(data_post)
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
                'Content-Type': 'application/json'
            }
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}; 请求参数： {data_post}')

            # 处理查询返回的数据
            if response.status_code == 200:
                result = response.json()
                self.logger.info(f'query_order 查询结果: {result}')
                if str(result.get("code")) == '200':
                    order_status = str(result.get("data", {}).get('status'))

                    # 在处理订单时使用查询结果  0:UTR不存在,1:UTR未领取,可补单,2:UTR已被领取; 回调状态只有：0:未支付；1：支付成功
                    if order_status == "2" and str(webhook_body.get('status')) == '1':
                        self.logger.info(f"订单已支付。支付订单： {code}")
                    else:
                        self.logger.error(f"订单状态: {order_status}")
                        return self.write(f"订单状态: {order_status}")
                else:
                    self.logger.error("查询失败: {} {}".format(result.get('data', {}).get("orderNo"), result.get("msg")))
                    return self.write("查询失败: {} {}".format(result.get('data', {}).get("orderNo"), result.get("msg")))
            else:
                self.logger.error("请求失败，状态码:", response.status_code)
                return self.write("请求失败，状态码:", response.status_code)

        except Exception as e:
            self.logger.exception(f'[SnakePay] 参数异常: {str(e)}')
            return self.write('params error')

        utr = webhook_body['utr']
        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code, utr):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[SnakePay] 错误：SnakePay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[SnakePay] SnakePay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('ok')

class hkpay_notify(BaseHandler):
    async def post(self):
        self.logger.info("[HKPay] 开始处理 HKPay 回调通知")

        # 查询商户配置
        sql_t = ('SELECT merchant_id, `key`, pay_url, name, query_url, notify_ip FROM otherpay WHERE name = %s')
        r_t = await self.query(sql_t, 'hkpay')

        # 默认拒绝请求
        self.set_status(403)

        if not r_t or not r_t[0].get('notify_ip'):
            self.logger.error('[HKPay] 无回调通知 IP，请配置 notify_ip')
            return self.write('not notify_ip')

        # 校验回调 IP
        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[HKPay] IP: {ip}, 回调 IP 错误')
            return self.write('notify_ip error')

        # 获取密钥
        md5_key = r_t[0]['key']

        try:
            # 解析回调数据
            data_receive = json.loads(self.request.body)
            self.logger.info(f'[HKPay] 收到回调参数: {data_receive}, 来自 IP: {ip}')

            # 校验签名
            if not self.verify_md5_sign(data_receive, md5_key):
                self.logger.error('[HKPay] 验签错误')
                return self.write('sign error')

            self.logger.info('[HKPay] 验签正确')

            # 获取订单号
            code = data_receive['merchant_orderno']
            # utr
            utr = data_receive['utr']

            # 查询订单
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[HKPay] 错误，无此订单 {code}')
                return self.write({"code": "1", "message": "error 无此订单"})

            # 检查订单是否已处理
            if str(data_receive.get('status')) == "success":
                self.logger.info(f"订单已支付。支付订单： {code}")
            else:
                self.logger.error(f"订单状态: {data_receive.get('status')}")
                return self.write(f"订单状态: {data_receive.get('status')}")

            # 校验金额
            self.logger.info(f"[HKPay] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[HKPay] payment: {data_receive['amount']}")
            if str(decimal.Decimal(_order_info[0]['amount'])) != str(decimal.Decimal(data_receive['amount'])):
                self.logger.error(f'[HKPay] 订单 {code} 金额不一致')
                return self.write('error 金额不一致')
            # 先查询订单状态，确保回调数据的正确性
            query_status = await self.query_order_status(
                r_t[0]['merchant_id'],
                data_receive.get('merchant_orderno'),
                md5_key,
                r_t[0]['query_url']
            )
            self.logger.info(f"[HKPay] 查询订单返回值: {query_status}")
            self.logger.info(f"[HKPay] 回调通知状态: {data_receive.get('status')}")

            if query_status is None:
                return self.write("error: query failed")

            if query_status != str(data_receive.get("status")):
                self.logger.error(f"[HKPay] 回调状态 {data_receive['status']} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

            # 判断订单支付状态
            if str(data_receive.get('status')) != "success":
                self.logger.error('[HKPay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[HKPay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 更新订单状态
        if not await order_success_ds_third(self, code, utr):
            self.logger.error(f'[HKPay] 错误：订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[HKPay] 订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('success')

    def verify_md5_sign(self, data, md5_key):
        """
        校验 MD5 签名
        """
        if "sign" not in data:
            return False

        sign = data.pop("sign")  # 取出签名字段，不参与签名计算

        # 按照 ASCII 排序，拼接参数
        sign_string = "&".join(f"{k}={str(v).strip()}" for k, v in sorted(data.items()) if v) + f"&key={md5_key}"

        # 计算 MD5
        calculated_sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()
        return calculated_sign == sign

    async def query_order_status(self, merchant_id, merchant_orderno, md5_key, query_url):
        """
        代收订单查询
        """
        params = {
            "merchantid": merchant_id,
            "merchant_orderno": merchant_orderno,
            "type": "collect",
        }

        # 生成签名
        params["sign"] = self.generate_md5_sign(params, md5_key)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            self.logger.info(f'HKPay 查询订单，URL: {query_url}, 发送数据: {params}')
            response = requests.post(query_url, data=params, headers=headers, timeout=(5, 10))
            self.logger.info(f"查询订单 {merchant_orderno}, 返回结果: {response.text}")

            if response.status_code != 200:
                self.logger.error(f"查询订单 {merchant_orderno} 失败，HTTP 状态码: {response.status_code}")
                return None

            res_data = response.json()
            if res_data.get("code") != 200:
                self.logger.error(f"查询订单 {merchant_orderno} 失败, 返回: {res_data}")
                return None

            return str(res_data["data"]["status"])  # 返回订单状态

        except Exception as e:
            self.logger.error(f"查询订单 {merchant_orderno} 发生异常: {e}")
            return None

    def generate_md5_sign(self, data, md5_key):
        """
        生成 MD5 签名
        """
        sign_string = "&".join(f"{k}={str(v).strip()}" for k, v in sorted(data.items()) if v) + f"&key={md5_key}"
        return hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()

# SkPayNotify
class skpay_notify(BaseHandler):
    async def post(self):

        self.logger.info("[Skpay] 开始处理 Skpay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, 'Skpay')
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[Skpay] 无回调通知 IP,请加回调通知 IP Skpay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[Skpay] IP: {ip}, 回调 IP 错误 Skpay_notify')
            return self.write('notify_ip error')

        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            data_receive = json.loads(self.request.body)
            self.logger.info(f'[Skpay] 收到回调参数: {data_receive}, 来自 IP: {ip}')

            # 验证签名
            headers = self.request.headers
            sign = headers.get('sign')
            method = 'POST'
            accesskey = headers.get('accesskey')
            timstamp = headers.get('timestamp')
            nonce = headers.get('nonce')
            url_path = '/api/skpay_notify'
            # url_path = ''
            self.logger.info(f'[Skpay] 收到回调参数headers: {headers}, 来自 IP: {ip}')
            raw_string = f"{method}&{url_path}&{accesskey}&{timstamp}&{nonce}"
            self.logger.info(f"[Skpay] raw_string: {raw_string}")
            self.logger.info(f"[Skpay] key3: {r_t[0]['key3']}")
            if not SignatureAndVerification.verify_signature_skpay(raw_string, r_t[0]['key3'], sign):
                self.logger.error(f"[Skpay] {data_receive}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[Skpay]  收到回调参数: {data_receive}, 签名通过')

            # 获取参数并解析
            code = data_receive.get('merchantOrderNo')
            orderNo = data_receive.get('orderNo')
            amount = decimal.Decimal(data_receive.get('amount'))

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status , third_party_order_number FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[HKPay] 错误，无此订单 {code}')
                return self.write({"code": "1", "message": "error 无此订单"})

            # 检查订单是否已处理
            if str(data_receive.get('status')) == "success":
                self.logger.info(f"订单已支付。支付订单： {code}")
            else:
                self.logger.error(f"订单状态: {data_receive.get('status')}")
                return self.write(f"订单状态: {data_receive.get('status')}")

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[Skpay] SnakePay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('success')

            # 检查金额
            self.logger.info(f"[Skpay] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[Skpay] payment: {amount}")
            if int(decimal.Decimal(_order_info[0]['amount'])) != int(decimal.Decimal(amount)):
                self.logger.error(f'[Skpay] 订单 {code} 金额不一致')
                return self.write('error 金额不一致')

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['orderNo'] = orderNo
            data_post['merchantOrderNo'] = code

            # 计算验证签名
            url_path = urlparse(query_url).path
            signature_info = SignatureAndVerification.generate_signature_skpay("POST", url_path, r_t[0]['key'], r_t[0]['key3'])

            # 构造请求头 ， 查询订单
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; U; Android 9; zh-CN; MI MAX 3 Build/PKQ1.190223.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.108 UCBrowser/11.8.8.968 UWS/2.13.2.91 Mobile Safari/537.36 UCBS/2.13.2.91_190617211143 NebulaSDK/1.8.100112 Nebula AlipayDefined(nt:4G,ws:393|0|2.75) AliApp(AP/10.1.68.7434) AlipayClient/10.1.68.7434 Language/zh-Hans useStatusBar/true isConcaveScreen/false Region/CN',
                "Content-Type": "application/json",
                "accessKey": r_t[0]['key'],
                "timestamp": signature_info["timestamp"],
                "nonce": signature_info["nonce"],
                "sign": signature_info["sign"]
            }

            data_post = json.dumps(data_post)
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

            query_status = str(result.get("data", {}).get('status'))
            status = str(data_receive.get('status'))

            self.logger.info(f"[Skpay] 查询订单返回值: {query_status}")
            self.logger.info(f"[Skpay] 回调通知状态: {status}")

            if query_status is None:
                return self.write("error: query failed")

            if query_status != status:
                self.logger.error(f"[Skpay] 回调状态 {data_receive['status']} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

            # 判断订单支付状态
            if status != "success":
                self.logger.error('[Skpay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[Skpay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[Skpay] 错误：Skpay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[Skpay] Skpay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('success')

class OsPayNotify(BaseHandler):
    async def post(self):
        # 多个账户回调至此，先筛选订单
        webhook_body = dict(parse.parse_qsl(self.request.body.decode()))
        self.logger.info(f'[OsPay/789Pay] data_receive-收到回调参数: {webhook_body}')
        code = webhook_body.get('order_id')
        sql_order_info = 'SELECT code, amount, partner_id, payment_id, status, third_party_name FROM orders_ds WHERE code = %s'
        _order_info = await self.query(sql_order_info, code)

        # 查询订单信息
        if not _order_info:
            self.logger.error(f'[OsPay/789Pay] OsPay_notify-错误，无此订单 {code}')
            return await self.json_response({'success': False, 'message': 'error 参数错误'})
        ds_name = _order_info[0]['third_party_name']

        # 打印接收到的所有 form-data 参数
        self.logger.info(f"[{ds_name}] 开始处理 OsPay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, channel_code, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, _order_info[0]['third_party_name'])
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error(f'[{ds_name}] 无回调通知 IP，请加回调通知 IP')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        ip = await self.get_ip()
        if ip not in ips:
            self.logger.error(f'[{ds_name}] IP: {ip}, 回调 IP 错误')
            return self.write('notify_ip error')

        mc_key = r_t[0]['key']
        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 从 form-data 获取并打印所有参数
            self.logger.info(f'[{ds_name}] data_receive-收到回调参数: {webhook_body}, 来自 IP: {ip}')
            # 获取参数并解析
            amount = decimal.Decimal(webhook_body.get('amount'))
            account_id = mer_id

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[{ds_name}] OsPay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('ok')

            # 检查merchant_id
            if account_id != str(webhook_body.get('mer_id')):
                return self.write('merchant_id error')
            # 检查金额
            if not decimal.Decimal(_order_info[0]['amount']) == amount:
                self.logger.error(f'[{ds_name}] 错误：OsPay_notify-查询订单 {code}, 金额不一致，订单金额为 {amount}')
                return await self.json_response({'success': False, 'message': 'error 查询订单与回调结果不一致,金额不一致'})

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['mer_id'] = mer_id
            data_post['order_id'] = code
            data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mc_key)
            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            utr = result.get('data', {}).get('utr')

            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

            query_status = str(result.get("data", {}).get('status'))
            upi = str(result.get("data", {}).get('upi'))
            status = str(webhook_body.get('status'))

            self.logger.info(f"[{ds_name}] 查询订单返回值: {query_status}, 获取到UPI: {upi}")
            self.logger.info(f"[{ds_name}] 回调通知状态: {status}")

            if query_status is None:
                return self.write("error: query failed")

            if not ((status == 'ok' and query_status == '0') or (status == 'error' and query_status == '2')):
                self.logger.error(f"[{ds_name}] 回调状态 {webhook_body['status']} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

            # 判断订单支付状态
            if status != "ok":
                self.logger.error(f'[{ds_name}] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[{ds_name}] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code, utr, upi=upi):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[{ds_name}] 错误：OsPay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[{ds_name}] OsPay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('ok')

# TataPayNotify
class tatapay_notify(BaseHandler):
    async def post(self):
        data_receive = json.loads(self.request.body)
        ip = await self.get_ip()
        self.logger.info(f'[TataPay] 收到回调参数: {data_receive}, 来自 IP: {ip}')

        if not str(data_receive.get('code')) == "0":
            self.logger.error(f"回调状态错误: {data_receive.get('code')}")
            return self.write(f"回调状态错误: {data_receive.get('code')}")
        result_data = data_receive.get('data')
        self.logger.info("[TataPay] 开始处理 TataPay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, query_url, notify_ip FROM otherpay WHERE merchant_id = %s'
        r_t = await self.query(sql_t, result_data.get('merchNo'))
        r_t = [o for o in r_t if 'TataPay' in o['name']]
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[TataPay] 无回调通知 IP,请加回调通知 IP TataPay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        if ip not in ips:
            self.logger.error(f'[TataPay] IP: {ip}, 回调 IP 错误 TataPay_notify')
            return self.write('notify_ip error')

        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 验证签名
            sign = result_data.pop('sign')
            sorted_items = sorted(result_data.items())
            source = '&'.join(f"{k}={v}" for k, v in sorted_items)
            check_sign = hashlib.md5((source + r_t[0]['key']).encode()).hexdigest()
            if not sign == check_sign:
                self.logger.error(f"[TataPay] {data_receive}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[TataPay] 签名通过')

            # 获取参数并解析
            code = result_data.get('orderNo')
            # orderNo = result_data.get('businessNo')
            amount = decimal.Decimal(result_data.get('amount'))

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status , third_party_order_number FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[TataPay] 错误，无此订单 {code}')
                return self.write({"订单不存在"})

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[TataPay] TataPay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('ok')

            # 检查金额
            self.logger.info(f"[TataPay] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[TataPay] payment: {amount}")
            if int(decimal.Decimal(_order_info[0]['amount'])) != int(decimal.Decimal(amount)):
                self.logger.error(f'[TataPay] 订单 {code} 金额不一致')
                return self.write('金额不一致')

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['merchNo'] = mer_id
            data_post['orderNo'] = code
            # 计算验证签名
            sorted_items = sorted(data_post.items())
            source = '&'.join(f"{k}={v}" for k, v in sorted_items)
            data_post['sign'] = hashlib.md5((source + r_t[0]['key']).encode()).hexdigest()

            # 构造请求头 ， 查询订单
            headers = {
                "Content-Type": "application/json",
            }

            data_post = json.dumps(data_post)
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

            if not str(result.get('code')) == '0':
                self.logger.error(f"查询错误: [{result.get('code')}]")
                return self.write(f"查询错误: {result.get('code')}")

            query_status = str(result.get("data", {}).get('orderState'))
            status = str(result_data.get('orderState'))

            self.logger.info(f"[TataPay] 查询订单返回值: {query_status}")
            self.logger.info(f"[TataPay] 回调通知状态: {status}")

            if query_status is None:
                return self.write("error: query failed")

            if query_status != status:
                self.logger.error(f"[TataPay] 回调状态 {status} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

            # 判断订单支付状态
            if status != "1":
                self.logger.error('[TataPay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[TataPay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[TataPay] 错误：TataPay_notify-订单 {code}，更新失败')
            return self.write('update order error')

        self.logger.info(f'[TataPay] TataPay_notify-订单 {code}, 确认成功')
        self.set_status(200)
        return self.write('ok')

# vibrapay_notify
class vibrapay_notify(BaseHandler):
    async def post(self):
        # data_receive = json.loads(self.request.body)
        data_receive = dict(parse.parse_qsl(self.request.body.decode()))
        ip = await self.get_ip()
        self.logger.info(f'[Vibrapay] 收到回调参数: {data_receive}, 来自 IP: {ip}')

        if not str(data_receive.get('code')) == "0":
            self.logger.error(f"回调状态错误: {data_receive.get('code')}")
            return self.write(f"回调状态错误: {data_receive.get('code')}")

        self.logger.info("[Vibrapay] 开始处理 Vibrapay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, query_url, notify_ip FROM otherpay WHERE merchant_id = %s'
        r_t = await self.query(sql_t, data_receive.get('merchant'))
        r_t = [o for o in r_t if 'Vibrapay' in o['name']]
        self.set_status(403)

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[Vibrapay] 无回调通知 IP,请加回调通知 IP Vibrapay')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        if ip not in ips:
            self.logger.error(f'[Vibrapay] IP: {ip}, 回调 IP 错误 Vibrapay_notify')
            return self.write('notify_ip error')

        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 获取参数并解析
            code = data_receive.get('merchant_order_num')
            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status , third_party_order_number FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[TataPay] 错误，无此订单 {code}')
                return self.write({"订单不存在"})

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[TataPay] TataPay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('ok')
            result_order = SignatureAndVerification.aes_256_cbc_decrypt(r_t[0]['key'],r_t[0]['key2'],data_receive['order'])
            result_order = json.loads(result_order)
            callback_status = result_order.get('status')

            # 检查金额
            self.logger.info(f"[TataPay] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[TataPay] payment: {result_order['amount']}")
            if int(decimal.Decimal(_order_info[0]['amount'])) != int(decimal.Decimal(result_order['amount'])):
                self.logger.error(f'[TataPay] 订单 {code} 金额不一致')
                return self.write('金额不一致')

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['merchant_slug'] = mer_id
            data_param_code = dict()
            data_param_code['merchant_order_num'] = code
            data_post['data'] = SignatureAndVerification.aes_256_cbc_encrypt(r_t[0]['key'],r_t[0]['key2'],json.dumps(data_param_code))

            # 构造请求头 ， 查询订单
            headers = {
                "Content-Type": "application/json",
            }

            data_post = json.dumps(data_post)
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

            if not str(result.get('code')) == '0':
                self.logger.error(f"查询错误: [{result.get('code')}]")
                return self.write(f"查询错误: {result.get('code')}")

            query_order = SignatureAndVerification.aes_256_cbc_decrypt(r_t[0]['key'],r_t[0]['key2'],result['order'])
            query_order = json.loads(query_order)
            query_status = query_order.get('status')

            self.logger.info(f"[Vibrapay] 查询订单返回值: {query_status}")
            self.logger.info(f"[Vibrapay] 回调通知状态: {callback_status}")

            if query_status is None:
                return self.write("error: query failed")

            if query_status != callback_status:
                self.logger.error(f"[Vibrapay] 回调状态 {callback_status} 与查询状态 {query_status} 不一致")
                return self.write("error: status mismatch")

            # 判断订单支付状态
            if query_status != "success":
                self.logger.error('[Vibrapay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[Vibrapay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[Vibrapay] 错误：Vibrapay_notify-订单 {code}，更新失败')
            return self.write('update order error')
        self.set_status(200)
        self.logger.info(f'[Vibrapay] Vibrapay_notify-订单 {code}, 确认成功')
        return self.write('ok')

# qqpay_notify
class qqpay_notify(BaseHandler):
    async def post(self):
        data_receive = json.loads(self.request.body)
        ip = await self.get_ip()
        self.logger.info(f'[qqpay] 收到回调参数: {data_receive}, 来自 IP: {ip}')
        self.set_status(403)
        if not str(data_receive.get('code')) == "200":
            self.logger.error(f"回调状态错误: {data_receive.get('code')}")
            return self.write(f"回调状态错误: {data_receive.get('code')}")
        result_data = data_receive.get('data')
        self.logger.info("[qqpay] 开始处理 qqpay 回调通知")
        sql_t = 'SELECT merchant_id, `key`, `key2`, `key3`, pay_url, name, query_url, notify_ip FROM otherpay WHERE merchant_id = %s'
        r_t = await self.query(sql_t, result_data.get('merchant_id'))
        r_t = [o for o in r_t if 'qqpay' in o['name']]

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error('[qqpay] 无回调通知 IP,请加回调通知 IP TataPay_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        if ip not in ips:
            self.logger.error(f'[qqpay] IP: {ip}, 回调 IP 错误 TataPay_notify')
            return self.write('notify_ip error')

        mer_id = r_t[0]['merchant_id']
        query_url = r_t[0]['query_url']

        try:
            # 验证签名
            sign = result_data.pop('sign')
            check_sign = SignatureAndVerification.hmac_sha256_sign3(result_data, r_t[0]['key'])
            if not sign == check_sign:
                self.logger.error(f"[qqpay] {data_receive}签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[qqpay] 签名通过')

            # 获取参数并解析
            code = result_data.get('mer_order_num')
            amount = decimal.Decimal(result_data.get('price'))

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status , third_party_order_number FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[qqpay] 错误，无此订单 {code}')
                return self.write({"订单不存在"})

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[qqpay] qqpay_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('success')

            # 检查金额
            self.logger.info(f"[qqpay] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[qqpay] payment: {amount}")
            if int(decimal.Decimal(_order_info[0]['amount'])) != int(decimal.Decimal(amount)):
                self.logger.error(f'[TataPay] 订单 {code} 金额不一致')
                return self.write('金额不一致')

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['merchant_id'] = mer_id
            data_post['mer_order_num'] = code
            data_post['timestamp'] = str(int(time.time()))
            data_post['type'] = 1
            # 计算验证签名
            data_post['sign'] = SignatureAndVerification.hmac_sha256_sign3(data_post, r_t[0]['key'])

            # 构造请求头 ， 查询订单
            headers = {
                "Content-Type": "application/json",
            }

            data_post = json.dumps(data_post)
            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

            if not str(result.get('code')) == '200':
                self.logger.error(f"查询错误: [{result.get('code')}]")
                return self.write(f"查询错误: {result.get('code')}")

            query_status = str(result.get("data", {}).get('status'))
            self.logger.info(f"[qqpay] 查询订单返回值: {query_status}")


            if query_status is None:
                return self.write("error: query failed")

            # 判断订单支付状态
            if query_status != "2":
                self.logger.error('[qqpay] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[qqpay] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[qqpay] 错误：qqpay_notify-订单 {code}，更新失败')
            return self.write('update order error')
        self.set_status(200)
        self.logger.info(f'[qqpay] qqpay_notify-订单 {code}, 确认成功')
        return self.write('success')


class gamepayer_notify(BaseHandler):
    async def get(self):
        pay_name = "gamepayer"
        result_data = {k: self.get_argument(k) for k in self.request.arguments}
        ip = await self.get_ip()
        self.logger.info(f'[{pay_name}] 收到回调参数: {result_data}, 来自 IP: {ip}')
        self.set_status(403)

        self.logger.info(f"[{pay_name}] 开始处理 回调通知")
        mer_id = result_data.get('merchant_id')
        sql_t = 'SELECT merchant_id, `key`, pay_url, name, query_url, notify_ip FROM otherpay WHERE merchant_id = %s'
        r_t = await self.query(sql_t, mer_id)
        r_t = [o for o in r_t if pay_name in o['name']]

        # 检查是否设定的回调 IP
        if not r_t[0]['notify_ip']:
            self.logger.error(f'[{pay_name}] 无回调通知 IP,请加回调通知 IP {pay_name}_notify')
            return self.write('not notify_ip')

        ips = r_t[0]['notify_ip'].split(',')
        if ip not in ips:
            self.logger.error(f'[{pay_name}] IP: {ip}, 回调 IP 错误 {pay_name}_notify')
            return self.write('notify_ip error')

        query_url = r_t[0]['query_url']
        key = r_t[0]['key']

        try:
            sign = result_data.pop('sign', None)
            sign_str = f'merchant_id={result_data.get('merchant_id', '')}&merchant_orderid={result_data.get('merchant_orderid', '')}&merchant_para={result_data.get('merchant_para', '')}&money={result_data.get('money', '')}&orderid={result_data.get('orderid', '')}&paytype={result_data.get('paytype', '')}&status={result_data.get('status', '')}{key}'
            if SignatureAndVerification.get_md5_str(sign_str).lower() != sign:
                self.logger.error(f"[{pay_name}] 签名错误: 接收到的签名 {sign}, ip: {ip}")
                return self.write('sign error')
            self.logger.info(f'[{pay_name}] 签名通过')

            # 获取参数并解析
            code = result_data.get('merchant_orderid')
            amount = decimal.Decimal(result_data.get("money"))

            # 下单时没有返回三方订单号，在回调中更新
            update_data = { 'third_party_order_number': result_data.get('orderid') }
            await self.update_result('orders_ds', update_data, {'code': code })

            # 查询订单信息
            sql_order_info = 'SELECT code, amount, partner_id, payment_id, status , third_party_order_number FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order_info, code)

            if not _order_info:
                self.logger.error(f'[{pay_name}] 错误，无此订单 {code}')
                return self.write("No such order!")

            # 检查订单状态
            if _order_info[0]['status'] > 2:
                self.logger.error(f'[{pay_name}] {pay_name}_notify-订单已经回调成功过 {code}, 确认成功')
                self.set_status(200)
                return self.write('SUCCESS')

            # 检查金额
            self.logger.info(f"[{pay_name}] amount: {_order_info[0]['amount']}")
            self.logger.info(f"[{pay_name}] payment: {amount}")
            if decimal.Decimal(_order_info[0]['amount']) != amount:
                self.logger.error(f'[{pay_name}] 订单 {code} 金额不一致')
                return self.write('金额不一致')

            # 发起 POST 请求到查询接口
            data_post = dict()
            data_post['merchant_id'] = mer_id
            data_post['merchant_orderid'] = code
            data_post['datetime'] = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            # 计算验证签名
            data_post['sign'] = SignatureAndVerification.md5_sign(data_post, key, "catspay").lower()

            # 构造请求头 ， 查询订单
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }

            # 发起 POST
            response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
            result = response.json()
            # 打印请求参数日志
            self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

            if not str(result.get('status')) == '1':
                self.logger.error(f"查询错误: [{result.get('status')}]")
                return self.write(f"查询错误: {result.get('status')}")

            query_status = str(result.get("data", {}).get("status", None))
            self.logger.info(f"[{pay_name}] 查询订单返回值: {query_status}")
            # 判断订单支付状态
            if query_status != "1":
                self.logger.error(f'[{pay_name}] 订单未支付成功')
                return self.write({"code": "1", "message": "not paid"})

        except Exception as e:
            self.logger.exception(f'[{pay_name}] 参数异常: {str(e)}')
            return self.write({"code": "1", "message": "params error"})

        # 订单处理成功后的操作
        if not await order_success_ds_third(self, code):
            # 删除操作的 key，防止回调占用
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[{pay_name}] 错误：{pay_name}_notify-订单 {code}，更新失败')
            return self.write('update order error')
        self.set_status(200)
        self.logger.info(f'[{pay_name}] {pay_name}_notify-订单 {code}, 确认成功')
        return self.write('SUCCESS')


class PayfastRedirect(BaseHandler):
    """PayFast 自动提交表单页面 —— 从 Redis 读取表单参数，浏览器自动 POST 到 PayFast"""
    async def get(self, code):
        pay_name = "payfast"
        redis_key = f'payfast_redirect_{code}'
        raw = await self.redis.get(redis_key)
        if not raw:
            self.set_status(410)
            return self.write('Payment link expired or invalid')

        form_data = json.loads(raw)
        pay_url = form_data.pop('PAY_URL')

        # 构建 hidden inputs
        inputs = ''.join(
            f'<input type="hidden" name="{k}" value="{v}" />'
            for k, v in form_data.items()
        )
        html_content = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Redirecting to PayFast...</title></head>
<body>
    <p style="text-align:center;margin-top:100px;font-size:18px;">Redirecting to PayFast, please wait...</p>
    <form id="payfast_form" method="post" action="{pay_url}">
        {inputs}
    </form>
    <script>document.getElementById('payfast_form').submit();</script>
</body>
</html>'''
        self.set_header('Content-Type', 'text/html; charset=utf-8')
        self.write(html_content)


class PayfastNotify(BaseHandler):
    """PayFast IPN 回调（GET + POST）—— 验证 validation_hash 并更新订单"""
    async def post(self):
        return await self._handle_notify()

    async def get(self):
        return await self._handle_notify()

    async def _handle_notify(self):
        pay_name = "payfast"
        result_data = {k: self.get_argument(k) for k in self.request.arguments}
        ip = await self.get_ip()
        self.logger.info(f'[{pay_name}] 收到回调参数: {result_data}, 来自 IP: {ip}')
        self.set_status(403)

        sql_t = 'SELECT merchant_id, `key`, pay_url, name, query_url, notify_ip FROM otherpay WHERE name = %s'
        r_t = await self.query(sql_t, 'payfast')
        if not r_t:
            self.logger.error(f'[{pay_name}] otherpay 中未找到 payfast 配置')
            return self.write('config not found')

        # 检查回调 IP
        if r_t[0]['notify_ip']:
            ips = r_t[0]['notify_ip'].split(',')
            if ip not in ips:
                self.logger.error(f'[{pay_name}] IP: {ip}, 回调 IP 错误')
                return self.write('notify_ip error')

        secured_key = r_t[0]['key']
        mer_id = r_t[0]['merchant_id']

        try:
            err_code = result_data.get('err_code', '')
            err_msg = result_data.get('err_msg', '')
            basket_id = result_data.get('basket_id', '')
            transaction_id = result_data.get('transaction_id', '')
            validation_hash = result_data.get('validation_hash', '')
            transaction_amount = result_data.get('transaction_amount', '')

            self.logger.info(f'[{pay_name}] basket_id={basket_id}, err_code={err_code}, transaction_id={transaction_id}')

            # 验证 validation_hash = SHA256(basket_id|secured_key|merchant_id|err_code)
            hash_str = f'{basket_id}|{secured_key}|{mer_id}|{err_code}'
            expected_hash = hashlib.sha256(hash_str.encode('utf-8')).hexdigest()
            if expected_hash != validation_hash:
                self.logger.error(f'[{pay_name}] validation_hash 不匹配: expected={expected_hash}, got={validation_hash}')
                return self.write('hash error')
            self.logger.info(f'[{pay_name}] validation_hash 验证通过')

            # 判断是否支付成功
            if err_code not in ('000', '00'):
                self.logger.info(f'[{pay_name}] 支付未成功, err_code={err_code}, err_msg={err_msg}')
                return self.write(f'payment not success: {err_code} {err_msg}')

            code = basket_id  # basket_id 就是我们的订单号

            # 更新三方订单号
            update_data = {'third_party_order_number': transaction_id}
            await self.update_result('orders_ds', update_data, {'code': code})

            # 查询订单信息
            sql_order = 'SELECT code, amount, partner_id, payment_id, status FROM orders_ds WHERE code = %s'
            _order_info = await self.query(sql_order, code)

            if not _order_info:
                self.logger.error(f'[{pay_name}] 无此订单 {code}')
                return self.write('No such order')

            if _order_info[0]['status'] > 2:
                self.logger.info(f'[{pay_name}] 订单 {code} 已成功，忽略重复回调')
                self.set_status(200)
                return self.write('SUCCESS')

            # 验证金额
            if transaction_amount:
                order_amount = decimal.Decimal(_order_info[0]['amount'])
                callback_amount = decimal.Decimal(transaction_amount)
                if order_amount != callback_amount:
                    self.logger.error(f'[{pay_name}] 订单 {code} 金额不一致: order={order_amount}, callback={callback_amount}')
                    return self.write('amount mismatch')

        except Exception as e:
            self.logger.exception(f'[{pay_name}] 参数异常: {str(e)}')
            return self.write('params error')

        # 订单成功处理
        if not await order_success_ds_third(self, code):
            busy_key = f'order_success_busy_{code}'
            await self.redis.delete(busy_key)
            self.logger.error(f'[{pay_name}] 订单 {code} 更新失败')
            return self.write('update order error')

        self.set_status(200)
        self.logger.info(f'[{pay_name}] 订单 {code} 确认成功')
        return self.write('SUCCESS')
