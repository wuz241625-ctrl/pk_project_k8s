import decimal
import html
import re
import time
import traceback

import razorpay
import simplejson as json
import hashlib
import requests
import random

from application.sign import SignatureAndVerification
from urllib.parse import urlencode, quote
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import urllib.parse
from urllib.parse import urlparse
from datetime import datetime

async def Razorpay_upi_origin(self, code, amount, mer_key, mer_key2, pay_url):
    try:
        client = razorpay.Client(auth=(mer_key, mer_key2))
        # 超时30分钟不能支付
        data_post = {
            "upi_link": True,
            "accept_partial": False,
            "amount": int(decimal.Decimal(amount)*100),
            "currency": "INR",
            "description": code,
            "expire_by": int(time.time()) + 60*30,
            "reference_id": code,
            # "customer": {
            #     "name": "Gaurav Kumar",
            #     "email": "gaurav.kumar@example.com",
            #     "contact": "+919000090000"
            # },
            "notify": {
                "sms": True,
                "email": True
            },
            "reminder_enable": True,
            # "notes": {
            #     "policy_name": "Jeevan Bima"
            # }
        }
        self.logger.info('noticeRazorpay_upi_origin 请求参数:{p}'.format(p=json.dumps(data_post)))
        r = client.payment_link.create(data_post)
        # print(r)
        self.logger.info('noticeOSpay_upi 发送地址{url},返回数据{data}'.format(url=pay_url, data=r))
        if "error" not in r.keys() and r['status'] == "created":
            return r['short_url']
        else:
            self.logger.error('noticeRazorpay_upi_origin 错误：发送地址{url},结果{ret}'.format(url=pay_url, ret=r))
            self.api_result = r['error']['description']
            # self.write(json.dumps(ret, ensure_ascii=False))
            return False
    except Exception as e:
        self.logger.exception('noticeRazorpay_upi_origin 错误：发送地址{url},错误{ret}'.format(url=pay_url, ret=e))
        return False
# lucky_payment代收
async def lucky_payment(self, code, amount, merchant_id, mer_key2, pay_url):
    # 第一步：生成 callback URL Return url
    callback = '/lucky_notify'
    # 第二步：生成 notify URL
    notify = '/lucky_notify'
    try:
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        # 打印 host + notify
        self.logger.info('host + notify===', host + notify)
        # 打印 host + callback
        self.logger.info('host + callback===', host + callback)
        # 当前时间戳（13位）
        request_timestamp = str(int(time.time() * 1000))

        # 计算签名
        sign_str = f"{merchant_id}&BANK&INR&{code}&{request_timestamp}{mer_key2}"
        # print(f"生成的签名字符串: {sign_str}")  # 打印签名字符串供调试
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
        # print(f"生成的签名: {sign}")  # 打印生成的签名

        # 定义请求数据
        # 回调地址 "https://be99-47-238-21-150.ngrok-free.app/lucky_notify"
        data_post = {
            "clientCode": merchant_id,
            "chainName": "BANK",
            "coinUnit": "INR",
            "clientNo": code,
            "requestAmount": str(decimal.Decimal(amount)),
            "requestTimestamp": request_timestamp,
            "callbackurl": host + notify,
            "hrefbackurl": host + callback,
            "sign": sign,
            "toPayQr": "0"
        }

        # 设置请求头
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        # 记录请求参数日志
        self.logger.info(f'lucky_payment 请求参数: {json.dumps(data_post)}')

        # 使用 requests.post 发起请求
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

        # 解析返回数据
        result = response.json()
        self.logger.info(f'lucky_payment 发送地址{pay_url},返回数据{result}')

        if result.get('success') and result.get('code') == 200 and result['data'].get('status') == 'CREATE':
            third_party_id = merchant_id
            third_party_order_number = result['data'].get('orderNo')

            sql = """
            SELECT name
            FROM otherpay
            WHERE merchant_id = %s
            """
            value = [third_party_id]

            # 执行查询获取 name
            otherpay = await self.query(sql, *value)
            name = otherpay[0]['name'] if otherpay else None

            # 准备更新的数据和条件
            update_data = {
                'third_party_id': third_party_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': name
            }
            condition = {'code': code}

            # 调用更新方法
            await self.update_result('orders_ds', update_data, condition)
            return result['data'].get('payUrl')
        else:
            self.logger.error(f'lucky_payment 错误：发送地址{pay_url},结果{result}')
            self.api_result = result.get('message', '未知错误')
            return False

    except Exception as e:
        self.logger.exception(f'lucky_payment 错误：发送地址{pay_url},错误{e}')
        return False


# apay
async def apay_payment(self, code, amount,name, merchant_id, mer_key, pay_url):
    callback = '/apay_notify'
    notify = '/apay_notify'
    try:
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info('host + notify=== {}'.format(host + notify))
        self.logger.info('host + callback=== {}'.format(host + callback))
        request_time = time.strftime('%Y%m%d%H%M%S', time.localtime())

        # 定义请求数据
        # 回调地址 "https://be99-47-238-21-150.ngrok-free.app/lucky_notify"
        data_post = {
            "version": "1.6",
            "cid": merchant_id,
            "tradeNo": code,
            "amount": int(decimal.Decimal(amount) * 100),
            "payType": "23",
            # "acctName": "testName",
            # "customerEmail": "test@Email.com",
            # "customerPhone": "1234567890",
            "returnType": "2",
            "requestTime": request_time,
            "returnUrl": host + callback,
            "notifyUrl": host + notify,
            "orderContent": "JSON"
        }

        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key).lower()

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            # 'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        self.logger.info(f"[apay_payment]请求地址 ({pay_url}),发送的参数： ({json.dumps(data_post)})")
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        self.logger.info(f"[apay_payment]请求地址 ({pay_url}),headers ({headers}),发送的参数： ({json.dumps(data_post)}),返回结果： ({response.text})")
        # 响应内容为html
        result = response.json()
        self.logger.info(f'[apay_payment] 返回数据 {result}')
        if not str(result.get('retcode')) == '0':  # 0 表示请求成功
            self.logger.error(f'[apay_payment] 错误：[{result.get('retcode')}] [{result.get('retmsg')}]')
            self.api_result = result.get('retmsg', '未知错误')
            return False
        pay_url = result.get('redirectUrl')

        third_party_id = merchant_id
        third_party_order_number = result.get('rockTradeNo')
        # 准备更新的数据和条件
        update_data = {
            'third_party_id': third_party_id,
            'third_party_order_number': third_party_order_number,
            'status': 1,
            'third_party_name': name
        }
        condition = {'code': code}
        # 调用更新方法
        await self.update_result('orders_ds', update_data, condition)
        return pay_url

    except Exception as e:
        self.logger.exception(f'apay_payment 错误：发送地址{pay_url},错误{e}')
        return False

# kingpay_payment 代收
async def kingpay_payment(self, code, amount, merchant_id, app_id, private_key, pay_url, notify_url):
        # 生成 returnUrl 和 notifyUrl
        return_url = notify_url
        try:
            # 生成 host 地址
            notice_domain_api_list = await self.redis.get('notice_domain_api_list')
            if not notice_domain_api_list:
                host = self.request.protocol + '://' + self.request.host
            else:
                notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
                notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i]
                host = random.choice(notice_domain_api_list)

            self.logger.info(f'host + notify_url****{host + notify_url}')
            self.logger.info(f'host + return_url****{host + return_url}')

            # 请求参数
            # 定义请求参数
            timestamp = int(time.time() * 1000)  # 13位时间戳
            amount_str = str(decimal.Decimal(amount))

            # 公共参数字典
            common_params = {
                "merchantId": merchant_id,
                "appId": app_id,
                "timestamp": timestamp,
                "outOrderId": code,
                "payType": 301,
                "product": code,
                "describe": code,
                "amount": amount_str,
                "payerPhone": '7027888888',
                "payerEmail": 'payer@gmail.com',
                "returnUrl": f"{host}{return_url}",
                "notifyUrl": f"{host}{notify_url}"
            }

            # 签名字段
            sign_fields = common_params.copy()

            # 构建请求体
            request_data = {
                **common_params,
                "sign": SignatureAndVerification.sha256_sign(sign_fields, private_key),
                "extendInfo": 'extendInfo'
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
            response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5,10))

            # 处理响应
            # print("request_data:", data_post)
            # print("Status Code:", response.status_code)
            # print("Response Data:", response.json())
            # 解析返回数据
            result = response.json()
            self.logger.info(f'kingpay_payment 发送地址{pay_url},返回数据{result}')

            if result.get('code') == '0' and result['status'] == 3:
                third_party_id = merchant_id
                third_party_order_number = result.get('orderId')

                # 查询商户名称
                sql = """
                SELECT name
                FROM otherpay
                WHERE merchant_id = %s
                """
                value = [third_party_id]
                otherpay = await self.query(sql, *value)
                name = otherpay[0]['name'] if otherpay else None

                # 准备更新的数据和条件
                update_data = {
                    'third_party_id': third_party_id,
                    'third_party_order_number': third_party_order_number,
                    'status': 1,
                    'third_party_name': name
                }
                condition = {'code': code}

                # 调用更新方法
                print("update_data:", update_data)
                print("condition:", condition)
                await self.update_result('orders_ds', update_data, condition)
                return result.get('payUrl')
            else:
                self.logger.error(f'kingpay_payment 错误：发送地址{pay_url},结果{result}')
                self.api_result = result.get('message', '未知错误')
                return False

        except Exception as e:
            self.logger.exception(f'kingpay_payment 错误：发送地址{pay_url},错误{e}')
            return False

# wepay_payment 代收
async def wepay_payment(self, code, amount, merchant_id, private_key, pay_url):
        # 生成 returnUrl 和 notifyUrl
        notify_url = '/wepay_notify'
        page_url = '/wepay_return'

        try:
            # 获取 host
            notice_domain_api_list = await self.redis.get('notice_domain_api_list')
            if not notice_domain_api_list:
                host = self.request.protocol + '://' + self.request.host
            else:
                notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
                notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
                rs = len(notice_domain_api_list)
                rs = random.randint(0, rs - 1)
                host = notice_domain_api_list[rs]

            self.logger.info(f'host + notify_url****{host + notify_url}')
            self.logger.info(f'host + page_url****{host + page_url}')

            # 代收请求参数
            order_date = time.strftime("%Y-%m-%d %H:%M:%S")  # 格式化时间
            amount_str = f"{decimal.Decimal(amount):.2f}"  # 确保最多2位小数
            # host = 'https://api.jsa23.com'  #test
            request_params = {
                "version": "1.0",  # 固定值
                "mch_id": merchant_id,  # 商户号
                "notify_url": f"{host}{notify_url}",  # 后台通知地址
                "page_url": f"{host}{page_url}",  # 前台通知地址
                "mch_order_no": code,  # 订单号
                "pay_type": "151",  # 印度二类A
                "trade_amount": amount_str,  # 交易金额
                "order_date": order_date,  # 订单时间
                "goods_name": "Product Name",  # 商品名称
                "mch_return_msg": "buy Vip",  # 透传参数
                "sign_type": "MD5"  # 固定值
            }

            self.logger.info(f'private_key****{private_key}')
            # 计算签名
            sign = generate_md5_signature(request_params, private_key)
            request_params["sign"] = sign  # 添加签名

            # 发送请求
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            self.logger.info(f"请求地址 ({pay_url}):")
            self.logger.info(f"请求参数 ({request_params}):")
            for key, value in request_params.items():
                self.logger.info(f"  {key}: {value}")

            response = requests.post(pay_url, data=request_params, headers=headers, timeout=(5, 10))

            # 解析返回数据
            result = response.json()
            self.logger.info(f'wepay_payment 发送地址{pay_url},返回数据{result}')

            if result.get('tradeResult') == '1':
                third_party_order_number = result.get('orderNo')

                # 更新数据库
                update_data = {
                    'third_party_id': merchant_id,
                    'third_party_order_number': third_party_order_number,
                    'status': 1,
                    'third_party_name': "WePay"
                }
                condition = {'code': code}
                await self.update_result('orders_ds', update_data, condition)
                return result.get('payInfo')

            else:
                self.logger.error(f'wepay_payment 错误：{result}')
                self.api_result = result.get('message', '未知错误')
                return False

        except Exception as e:
            self.logger.exception(f'wepay_payment 错误：{e}')
            return False

@staticmethod
def generate_md5_signature(params, private_key):
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


# apay
async def pay777pay_payment(self, code, amount, merchant_id, mer_key, pay_url):
    callback = '/777_notify'
    notify = '/777_notify'
    try:
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info('host + notify=== {}'.format(host + notify))
        self.logger.info('host + callback=== {}'.format(host + callback))
        # 定义请求数据
        # 回调地址 "https://be99-47-238-21-150.ngrok-free.app/lucky_notify"
        data_post = {
            "app_id": merchant_id,
            "merchant_order_id": code,
            "amount": amount,
            "pay_channel": 'INDIA_NATIVE',
            "notify_url": host + notify,
            "page_return_url": host + callback,
        }
        data_post['sign'] = SignatureAndVerification.md5_sign(data_post, mer_key).lower()

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        self.logger.info(f'apay_payment 请求参数: {json.dumps(data_post)}')
        self.logger.info(f'pay_url: {pay_url}')
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

        # 响应内容为html
        result = response.json()
        pay_url = result.get('data', {}).get('pay_url')

        # 输出提取到的网址
        if pay_url:
            url = pay_url
            self.logger.info(f'支付链接: {url}')

            third_party_id = merchant_id
            third_party_order_number = result.get('data', {}).get('system_order_id')

            sql = """SELECT name FROM otherpay WHERE merchant_id = %s"""
            value = [third_party_id]
            otherpay = await self.query(sql, *value)
            name = otherpay[0]['name'] if otherpay else None

            # 准备更新的数据和条件
            update_data = {
                'third_party_id': third_party_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': name
            }
            condition = {'code': code}

            # 调用更新方法
            await self.update_result('orders_ds', update_data, condition)
            return url
        else:
            self.logger.error(f'apay_payment 错误：发送地址{pay_url},结果{result}')
            self.api_result = result.get('message', '未知错误')
            return False

    except Exception as e:
        self.logger.exception(f'apay_payment 错误：发送地址{pay_url},错误{e}')
        return False


# apay
async def swiftpay_payment(self, code, amount, merchant_id, mer_key, mer_key2, mer_key3, pay_url):
    callback = '/swiftpay_notify'
    notify = '/swiftpay_notify'
    try:
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info('host + notify=== {}'.format(host + notify))
        self.logger.info('host + callback=== {}'.format(host + callback))
        # 定义请求数据
        # 回调地址 "https://be99-47-238-21-150.ngrok-free.app/lucky_notify"
        data_post = {
            "merchantNo": merchant_id,
            "orderId": code,
            "payment": int(amount),
            "callback": host + notify,
        }
        data_post['sign'] = SignatureAndVerification.sha1_sign(data_post, mer_key3)
        data_post = json.dumps(data_post)
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/json'
        }
        self.logger.info(f'apay_payment 请求参数: {data_post}')
        self.logger.info(f'pay_url: {pay_url}')
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

        # 响应内容为html
        result = response.json()
        pay_url = result.get('data', {}).get('payUrl')

        # 输出提取到的网址
        if pay_url:
            url = pay_url
            self.logger.info(f'支付链接: {url}')

            third_party_id = merchant_id
            third_party_order_number = result.get('data', {}).get('orderNo')

            sql = """SELECT name FROM otherpay WHERE merchant_id = %s"""
            value = [third_party_id]
            otherpay = await self.query(sql, *value)
            name = otherpay[0]['name'] if otherpay else None

            # 准备更新的数据和条件
            update_data = {
                'third_party_id': third_party_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': name
            }
            condition = {'code': code}

            # 调用更新方法
            await self.update_result('orders_ds', update_data, condition)
            return url
        else:
            self.logger.error(f'apay_payment 错误：发送地址{pay_url},结果{result}')
            self.api_result = result.get('message', '未知错误')
            return False

    except Exception as e:
        self.logger.exception(f'apay_payment 错误：发送地址{pay_url},错误{e}')
        return False

# quickpay_payment 代收
async def quickpay_payment(self, code, amount, merchant_id, private_key, pay_url):
    # 生成 returnUrl 和 notifyUrl
    notify_url = '/quickpay_notify'
    page_url = '/quickpay_return'

    try:
        # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info(f'host + notify_url****{host + notify_url}')
        self.logger.info(f'host + page_url****{host + page_url}')

        # 代收请求参数
        amount_str = str(int(amount))  # QuickPay 不支持小数，转换为整数
        request_params = {
            "merchantNo": merchant_id,  # 商户号
            "orderId": code,  # 订单号
            "payment": amount_str,  # 交易金额
            "callback": f"{host}{notify_url}",  # 后台通知地址
        }

        self.logger.info(f'private_key****{private_key}')
        # 计算签名
        sign = SignatureAndVerification.rsa_sha1_sign(request_params, private_key)
        request_params["sign"] = sign  # 添加签名

        # 发送请求
        headers = {
            "Content-Type": "application/json"
        }

        for key, value in request_params.items():
            self.logger.info(f"  {key}: {value}")

        request_params = json.dumps(request_params)
        response = requests.post(pay_url, data=request_params, headers=headers, timeout=(5, 10))

        # 解析返回数据
        result = response.json()
        self.logger.info(f"请求地址 ({pay_url}):")
        self.logger.info(f"请求参数 ({request_params}):")
        self.logger.info(f'quickpay_payment 发送地址{pay_url}, 返回数据{result}')

        if str(result.get('errNo')) == '0':  # 0 表示请求成功
            third_party_order_number = result['data'].get('orderNo')

            sql = """SELECT name FROM otherpay WHERE merchant_id = %s"""
            value = [merchant_id]
            otherpay = await self.query(sql, *value)
            name = otherpay[0]['name'] if otherpay else None

            # 更新数据库
            update_data = {
                'third_party_id': merchant_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': name
            }
            condition = {'code': code}
            await self.update_result('orders_ds', update_data, condition)
            return result['data'].get('payUrl')  # 返回支付链接

        else:
            self.logger.error(f'quickpay_payment 错误：{result}')
            self.api_result = result.get('errStr', '未知错误')
            return False

    except Exception as e:
        self.logger.exception(f'quickpay_payment 错误：{e}')
        return False


# snake
async def snakepay_payment(self, pay_name, code, amount, merchant_id, mer_key, pay_url):
    callback = '/snakepay_notify'
    notify = '/snakepay_notify'
    try:
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
            # host = "https://zk1.ipay268.cc"
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info('host + notify=== {}'.format(host + notify))
        self.logger.info('host + callback=== {}'.format(host + callback))
        # 定义请求数据
        data_post = {
            "merchantNo": merchant_id,
            "orderNo": code,
            "amount": amount,
            "notifyUrl": host + notify,
            "returnUrl": host + notify,
        }
        data_post['sign'] = SignatureAndVerification.hmac_sha256_sign(data_post, mer_key)
        data_post = json.dumps(data_post)
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/json'
        }
        self.logger.info(f'snakepay 请求参数: {data_post}')
        self.logger.info(f'pay_url: {pay_url}')
        response = requests.post(pay_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

        # 响应内容为html
        result = response.json()
        payUrl = result.get('data', {}).get('payUrl')

        # 输出提取到的网址
        if payUrl:
            url = payUrl
            self.logger.info(f'支付链接: {url}')

            third_party_id = merchant_id
            third_party_order_number = result.get('data', {}).get('platformOrderNo')
            # 获取信息接入本地收银台 拼装二维码信息获取地址，并从二维码地址中获取到upi和auth_code
            third_party_qr_url = 'https://cashier.snakepay.run/api/cashier/' + third_party_order_number
            response = requests.get(third_party_qr_url, headers=headers, timeout=(5, 5), verify=False)
            third_party_qr_info = response.json()
            qr_url = third_party_qr_info.get('data', {}).get('url')
            qr_url_info_dict = {param.split('=')[0]: param.split('=')[1] for param in qr_url.split('&')}
            upi = qr_url_info_dict.get('pa')
            auth_code = qr_url_info_dict.get('tn')
            await self.redis.set('order_ds_third_qr_{}'.format(code), qr_url, 60 * 20)
            # 准备更新的数据和条件
            update_data = {
                'third_party_id': third_party_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': pay_name,
                'upi': upi,
                'auth_code': auth_code,
            }
            condition = {'code': code}

            # 调用更新方法
            await self.update_result('orders_ds', update_data, condition)
            return url
        else:
            self.logger.error(f'snakepay 错误：发送地址{pay_url},结果{result}')
            self.api_result = result.get('message', '未知错误')
            return False

    except Exception as e:
        self.logger.exception(f'snakepay 错误：发送地址{pay_url},错误{e}')
        return False

# hkpay 代收
async def hkpay_payment(self, code, amount, merchant_id, private_key, pay_url):
    # 生成 returnUrl 和 notifyUrl
    notify_url = '/hkpay_notify'
    callback_url = '/hkpay_return'

    try:
        # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info(f'host + notify_url****{host + notify_url}')
        self.logger.info(f'host + callback_url****{host + callback_url}')
        final_notify_url = host + notify_url
        # final_notify_url = 'https://30f9-47-238-21-150.ngrok-free.app/hkpay_notify'


        # 格式化金额为两位小数
        amount_str = "{:.2f}".format(float(amount))

        # 代收请求参数
        request_params = {
            "merchantid": merchant_id,  # 商户号
            "merchant_orderno": code,  # 商户订单号
            "passage_code": "100001",  # 通道代码
            "currency": "INR",  # 货币类型
            "amount": amount_str,  # 交易金额
            "notify_url": f"{final_notify_url}",  # 异步通知地址
            "callback_url": f"{host}{callback_url}",  # 同步回调地址
            "payer_id": "917893305473",  # 付款人 ID
        }

        # 计算签名
        sorted_params = sorted(request_params.items())  # 按 ASCII 排序
        sign_string = "&".join(f"{k}={v.strip()}" for k, v in sorted_params if v)  # 拼接字符串
        sign_string += f"&key={private_key}"  # 追加私钥
        self.logger.info(f"签名原始字符串: {sign_string}")

        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()  # MD5 签名
        request_params["sign"] = sign  # 添加签名

        # 发送请求
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        request_data = urlencode(request_params)  # 转换为 form-data 格式
        response = requests.post(pay_url, data=request_data, headers=headers, timeout=(5, 10))

        # 解析返回数据
        result = response.json()
        self.logger.info(f"请求地址 ({pay_url}):")
        self.logger.info(f"请求参数 ({request_data}):")
        self.logger.info(f'hkpay_payment 返回数据 {result}')

        if result.get('code') == 200:  # 200 表示请求成功
            third_party_order_number = result['data'].get('orderno')

            url = result['data'].get('payurl')
            orderno = str(result['data'].get('orderno'))

            # 获取信息接入本地收银台 拼装二维码信息获取地址，并从二维码地址中获取到upi和auth_code
            url = "https://api.hhpayapi.com/mcapi/cashplaceorder/v2/" + orderno

            payload = 'payer_id=f9vbWufrFCj1qjuRoXkjmPh0lG08P0bv'
            headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://cash.uuuuucash.com',
            'priority': 'u=1, i',
            'referer': 'https://cash.uuuuucash.com/',
            'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'cross-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
            }

            response = requests.request("POST", url, headers=headers, data=payload)

            self.logger.info(f'response.text==={response.text}')
            result_upi = response.json()
            self.logger.info(f'result_upi====={result_upi}')

            # 获取 'wakeup_params' 中的 'qr' 字符串
            qr_string = result_upi["data"]["cash_params"]["wakeup_params"]["qr"]

            # 解析该字符串中的 'pa' 和 'tn' 参数
            url_params = urllib.parse.parse_qs(urllib.parse.urlparse(qr_string).query)

            # 获取 'pa' 和 'tn' 参数的值
            upi = url_params.get('pa', [None])[0]
            auth_code = url_params.get('tn', ['ospay'])[0]


            await self.redis.set('order_ds_third_qr_{}'.format(code), qr_string, 60 * 20)
            # 输出结果
            self.logger.info(f"upi: {upi}")
            self.logger.info(f"auth_code: {auth_code}")
            self.upi = upi

            sql = """SELECT name FROM otherpay WHERE merchant_id = %s"""
            value = [merchant_id]
            otherpay = await self.query(sql, *value)
            name = otherpay[0]['name'] if otherpay else None

            # 更新数据库
            update_data = {
                'third_party_id': merchant_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': name,
                'upi': upi,
                'auth_code': auth_code,
            }
            condition = {'code': code}
            await self.update_result('orders_ds', update_data, condition)
            return result['data'].get('payurl')  # 返回支付链接

        else:
            self.logger.error(f'hkpay_payment 错误：{result}')
            self.api_result = result.get('errmsg', '未知错误')
            return False

    except Exception as e:
        self.logger.exception(f'hkpay_payment 发生错误：{e}')
        return False

# skpay 代收
async def skpay_payment(self, code, amount, merchant_id, accesskey, secretkey, pay_url):
    # 生成 returnUrl 和 notifyUrl
    notify_url = '/skpay_notify'  # 异步通知地址
    callback_url = '/skpay_notify'  # 同步回调地址
    try:
        # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        final_notify_url = host + notify_url
        final_callback_url = host + callback_url

        self.logger.info(f'host + notify_url****{final_notify_url}')
        self.logger.info(f'host + callback_url****{final_callback_url}')

        # 格式化金额为两位小数
        amount_str = "{:.2f}".format(float(amount))
        # 代收请求参数
        request_params = {
            "merchantOrderNo": code,  # 商户订单号
            "channelCode": "ch70471",  # 通道代码
            "amount": amount_str,  # 交易金额
            "currency": "inr",  # 货币类型
            "notifyUrl": f"{final_notify_url}",  # 异步通知地址
            "jumpUrl": f"{final_callback_url}",  # 同步回调地址
        }
        url_path = urlparse(pay_url).path

        signature_info = SignatureAndVerification.generate_signature_skpay("POST", url_path, accesskey, secretkey)
        headers = {
            "Content-Type": "application/json",  # 根据你实际请求类型调整
            "accessKey": accesskey,
            "timestamp": signature_info["timestamp"],
            "nonce": signature_info["nonce"],
            "sign": signature_info["sign"]
        }
        request_data = json.dumps(request_params)
        self.logger.info(f"请求地址 ({pay_url}),发送的参数： ({request_data})")
        response = requests.post(pay_url, data=request_data, headers=headers, timeout=(5, 10))
        self.logger.info(f"请求地址 ({pay_url}),headers ({headers}),发送的参数： ({request_data}),返回结果： ({response.text})")

        # 解析返回数据
        result = response.json()
        self.logger.info(f"请求地址 ({pay_url}):")
        self.logger.info(f"请求参数 ({request_data}):")
        self.logger.info(f'skpay_payment 返回数据 {result}')

        if str(result.get('code')) == '200000':  # 0 表示请求成功
            third_party_order_number = result['data'].get('orderNo')
            sql = """SELECT name FROM otherpay WHERE merchant_id = %s"""
            value = [merchant_id]
            otherpay = await self.query(sql, *value)
            name = otherpay[0]['name'] if otherpay else None
            # 更新数据库
            update_data = {
                'third_party_id': merchant_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': name
            }
            condition = {'code': code}
            await self.update_result('orders_ds', update_data, condition)
            # 目标页面 URL
            pay_url = result['data'].get('payUrl')
            return pay_url  # 返回支付链接

        elif result.get('code') == '400001':
            self.logger.error(f'skpay_payment 错误：{result.get('code').get('message')}')
            self.api_result = result.get('code').get('message')
            return False
        else:
            self.logger.error(f'skpay_payment 错误：{result}')
            self.api_result = result.get('message', '未知错误')
            return False

    except Exception as e:
         # 使用 traceback.format_exc() 获取堆栈信息，并写入日志
        error_details = traceback.format_exc()  # 获取详细的异常堆栈信息
        self.logger.exception(f'skpay_payment 发生错误：{error_details}')
        return False


# ospay 代收
async def ospay_payment(self, code, amount, merchant_id, mer_key, pay_url, other_pay, gateway):
    # 生成 returnUrl 和 notifyUrl
    notify_url = '/ospay_notify'  # 异步通知地址
    callback_url = '/ospay_notify'  # 同步回调地址
    try:
        # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        final_notify_url = host + notify_url
        final_callback_url = host + callback_url

        self.logger.info(f'host + notify_url****{final_notify_url}')
        self.logger.info(f'host + callback_url****{final_callback_url}')

        # 代收请求参数
        request_params = {
            "mer_id": merchant_id,
            "order_id": code,
            "gateway": gateway,
            "amount": amount,
            "callback": final_callback_url,
            "notify": final_notify_url
        }
        request_params['sign'] = SignatureAndVerification.md5_sign(request_params, mer_key)
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        self.logger.info(f"请求地址 ({pay_url}),发送的参数： ({request_params})")
        response = requests.post(pay_url, data=request_params, headers=headers, timeout=(5, 10))
        self.logger.info(f"请求地址 ({pay_url}),headers ({headers}),发送的参数： ({request_params}),返回结果： ({response.text})")

        # 解析返回数据
        result = response.json()
        self.logger.info(f"请求地址 ({pay_url}):")
        self.logger.info(f"请求参数 ({request_params}):")
        self.logger.info(f'ospay_payment 返回数据 {result}')

        if str(result.get('code')) == '0':  # 0 表示请求成功
            third_party_order_number = result.get('order_code')
            # 目标页面 URL
            pay_url = result.get('data')
            upi = result.get('upi')

            # 更新数据库
            update_data = {
                'third_party_id': merchant_id,
                'third_party_order_number': third_party_order_number,
                'status': 1,
                'third_party_name': other_pay['name'],
                'upi': upi
            }
            condition = {'code': code}
            await self.update_result('orders_ds', update_data, condition)
            return pay_url  # 返回支付链接
        else:
            self.logger.error(f'ospay_payment 错误：{result}')
            self.api_result = result.get('message', '未知错误')
            return False

    except Exception as e:
         # 使用 traceback.format_exc() 获取堆栈信息，并写入日志
        error_details = traceback.format_exc()  # 获取详细的异常堆栈信息
        self.logger.exception(f'ospay_payment 发生错误：{error_details}')
        return False

# tatapay 代收
async def tatapay_payment(self, code, amount, name, merchant_id, accesskey, pay_url):
    try:
        # 格式化金额为两位小数
        amount_str = "{:.2f}".format(float(amount))
        # 代收请求参数
        request_params = {
            "merchNo": merchant_id,  # 商户号
            "orderNo": code,  # 商户订单号
            "amount": amount_str,  # 交易金额
            "currency": "INR"  # 货币类型
        }

        sorted_items = sorted(request_params.items())
        source = '&'.join(f"{k}={v}" for k, v in sorted_items)
        request_params['sign'] = hashlib.md5((source + accesskey).encode()).hexdigest()

        headers = {
            "Content-Type": "application/json",  # 根据你实际请求类型调整
        }
        request_data = json.dumps(request_params)
        self.logger.info(f"请求地址 ({pay_url}),发送的参数： ({request_data})")
        response = requests.post(pay_url, data=request_data, headers=headers, timeout=(5, 10))
        self.logger.info(f"请求地址 ({pay_url}),headers ({headers}),发送的参数： ({request_data}),返回结果： ({response.text})")

        # 解析返回数据
        result = response.json()
        self.logger.info(f"请求地址 ({pay_url}):")
        self.logger.info(f"请求参数 ({request_data}):")
        self.logger.info(f'TataPay_payment 返回数据 {result}')

        if not str(result.get('code')) == '0':  # 0 表示请求成功
            self.logger.error(f'TataPay_payment 错误：[{result.get('code')}] [{result.get('msg')}]')
            self.api_result = result.get('msg', '未知错误')
            return False

        qr_url = result.get('data', {}).get('deepLink')
        qr_url_info_dict = {param.split('=')[0]: param.split('=')[1] for param in qr_url.split('&')}
        self.upi = qr_url_info_dict.get('pa')
        auth_code = qr_url_info_dict.get('tn')
        await self.redis.set('order_ds_third_qr_{}'.format(code), qr_url, 60 * 20)
        self.logger.info(f'订单 {code} 已存入二维码信息: {qr_url}, upi: {self.upi}')

        # 更新数据库
        update_data = {
            'third_party_id': merchant_id,
            'third_party_order_number': result['data'].get('businessNo'),
            'status': 1,
            'third_party_name': name,
            'upi': self.upi,
            'auth_code': auth_code,
        }
        condition = {'code': code}
        await self.update_result('orders_ds', update_data, condition)
        # 目标页面 URL
        pay_url = result['data'].get('code_url')
        return pay_url  # 返回支付链接

    except Exception as e:
        # 使用 traceback.format_exc() 获取堆栈信息，并写入日志
        error_details = traceback.format_exc()  # 获取详细的异常堆栈信息
        self.logger.exception(f'TataPay_payment 发生错误：{error_details}')
        return False


# vibrapay 代收
async def vibrapay_payment(self, code, amount, name, merchant_id, accesskey1, accesskey2, pay_url):
    try:
        callback_url = '/vibrapay_notify'
        #
        # # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info(f'host + callback_url****{host + callback_url}')
        final_notify_url = host + callback_url

        # 格式化金额为两位小数
        amount_str = "{:.2f}".format(float(amount))
        # 代收请求参数
        params = {
            "gateway": "upi_wake",  # 支付渠道
            "device": "mobile",  # 用户使用装置
            "amount": amount_str,  # 交易金额
            "merchant_order_time": str(datetime.now().timestamp()),  # 当前时间
            "merchant_order_num": code,  # 商户订单号
            "uid": merchant_id,  # 商户号
            "callback_url": final_notify_url,
            "user_ip": "127.0.0.1"  # IP
        }

        sorted_items = sorted(params.items())
        param_data = json.dumps({k: v for k,v in sorted_items})
        request_params = dict()
        request_params['merchant_slug'] = str(merchant_id)
        request_params['data'] = SignatureAndVerification.aes_256_cbc_encrypt(accesskey1,accesskey2,param_data)

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/json'
        }
        request_data = json.dumps(request_params)
        self.logger.info(f"请求地址 ({pay_url}),发送的参数： ({request_data})")
        response = requests.post(pay_url, data=request_data, headers=headers, timeout=(5, 10))
        self.logger.info(f"请求地址 ({pay_url}),headers ({headers}),发送的参数： ({request_data}),返回结果： ({response.text})")

        # 解析返回数据
        result = response.json()
        self.logger.info(f"请求地址 ({pay_url}):")
        self.logger.info(f"请求参数 ({request_data}):")
        self.logger.info(f'vibrapay_payment 返回数据 {result}')

        if not str(result.get('code')) == '0':  # 0 表示请求成功
            self.logger.error(f'vibrapay_payment 错误：[{result.get('code')}] [{result.get('msg')}]')
            self.api_result = result.get('msg', '未知错误')
            return False

        result_order = SignatureAndVerification.aes_256_cbc_decrypt(accesskey1, accesskey2, result.get('order'))
        result_order = json.loads(result_order)
        payUrl = result_order.get('navigate_url')
        # 输出提取到的网址
        self.logger.info(f'vibrapay支付链接: {payUrl}')
        third_party_order_number = payUrl.split('?')[1].split('=')[1]
        # 25/6/30 直接使用第三方的收银台（这里注释掉）
        # # 获取信息接入本地收银台 拼装二维码信息获取地址，并从二维码地址中获取到upi和auth_code
        # third_party_qr_url = f'https://pay.haoxpay.com/findRealChannel?type=5&orderId={third_party_order_number}&queryQR=1'
        # response = requests.get(third_party_qr_url, headers=headers, timeout=(5, 5), verify=False)
        # third_party_qr_info = response.json()
        # qr_url = third_party_qr_info.get('data', {}).get('upi')
        # qr_url_info_dict = {param.split('=')[0]: param.split('=')[1] for param in qr_url.split('&')}
        # self.upi = qr_url_info_dict.get('pa')
        # auth_code = qr_url_info_dict.get('tn')
        # await self.redis.set('order_ds_third_qr_{}'.format(code), qr_url, 60 * 20)
        # 更新数据库
        update_data = {
            'third_party_id': merchant_id,
            'third_party_order_number': third_party_order_number,
            'status': 1,
            'third_party_name': name,
            # 'upi': self.upi,
            # 'auth_code': auth_code,
        }
        condition = {'code': code}
        await self.update_result('orders_ds', update_data, condition)
        return payUrl  # 返回支付链接

    except Exception as e:
        # 使用 traceback.format_exc() 获取堆栈信息，并写入日志
        error_details = traceback.format_exc()  # 获取详细的异常堆栈信息
        self.logger.exception(f'TataPay_payment 发生错误：{error_details}')
        return False

# qqpay_payment 代收
async def qqpay_payment(self, code, amount, name, merchant_id, accesskey, pay_url):
    try:
        callback_url = '/qqpay_notify'
        #
        # # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        self.logger.info(f'host + callback_url****{host + callback_url}')
        final_notify_url = host + callback_url

        # 格式化金额为两位小数
        amount_str = "{:.2f}".format(float(amount))
        now_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now_timestamp = datetime.strptime(now_date, "%Y-%m-%d %H:%M:%S").timestamp()
        # 代收请求参数
        params = {
            "merchant_id": merchant_id,  # 商户id
            "mer_order_num": code,  # 商户订单号
            "price": amount_str,  # 交易金额
            "pay_code": "101",  # 通道编码
            "attach": "",  # 附带参数
            "notify_url": final_notify_url,  # 回调地址
            "page_url": "",  # 跳转地址
            "order_date": now_date,  # 当前时间
            "timestamp": str(int(now_timestamp))   # 时间戳
        }
        params['sign'] = SignatureAndVerification.hmac_sha256_sign3(params, accesskey)

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/json'
        }
        self.logger.info(f"请求地址 ({pay_url}),发送的参数： ({params})")
        response = requests.post(pay_url, data=json.dumps(params), headers=headers, timeout=(5, 10))
        self.logger.info(f"请求地址 ({pay_url}),headers ({headers}),发送的参数： ({params}),返回结果： ({response.text})")

        # 解析返回数据
        result = response.json()
        self.logger.info(f'qqpay_payment 返回数据 {result}')
        if not str(result.get('code')) == '200':  # 0 表示请求成功
            self.logger.error(f'qqpay_payment 错误：[{result.get('code')}] [{result.get('msg')}]')
            self.api_result = result.get('msg', '未知错误')
            return False

        qr_url = result.get('data', {}).get('pay_url')
        order_num = result.get('data', {}).get('order_num')

        # 获取信息接入本地收银台 拼装二维码信息获取地址，并从二维码地址中获取到upi和auth_code
        url = "https://cashier.qq-pay.cc/payment/orders"
        payload = f'order_num={qr_url.split('=')[1]}'
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }
        response = requests.request("POST", url, headers=headers, data=payload)
        self.logger.info(f'response.text==={response.text}')
        result_upi = response.json()
        self.logger.info(f'result_upi====={result_upi}')
        # 获取 'wakeup_params' 中的 'qr' 字符串
        qr_url = result_upi["data"]["qrcode"]
        qr_url = qr_url.split('?')
        if len(qr_url) >1:
            qr_url = qr_url[1]
        else:
            qr_url = qr_url[0]
        qr_url_info_dict = {param.split('=')[0]: param.split('=')[1] for param in qr_url.split('&') if param}
        self.upi = qr_url_info_dict.get('pa')
        auth_code = qr_url_info_dict.get('tn')
        await self.redis.set('order_ds_third_qr_{}'.format(code), qr_url, 60 * 20)
        self.logger.info(f'订单 {code} 已存入二维码信息: {qr_url}, upi: {self.upi}')
        # 更新数据库
        update_data = {
            'third_party_id': merchant_id,
            'third_party_order_number': order_num,
            'status': 1,
            'third_party_name': name,
            'upi': self.upi,
            'auth_code': auth_code,
        }
        condition = {'code': code}
        await self.update_result('orders_ds', update_data, condition)
        return qr_url  # 返回支付链接

    except Exception as e:
        # 使用 traceback.format_exc() 获取堆栈信息，并写入日志
        error_details = traceback.format_exc()  # 获取详细的异常堆栈信息
        self.logger.exception(f'qqpay_payment 发生错误：{error_details}')
        return False


async def gamepayer_payment(self, code, amount, merchant_id, name, mer_key, pay_url):
    """
    gamepayer 代收请求函数
    """
    pay_name = "gamepayer"
    notifyurl = '/gamepayer_notify'
    try:

        # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        notifyurl = host + notifyurl
        self.logger.info(f'host + callback_url****{notifyurl}')

        # 代收请求参数
        params = {
            "money": str(amount),  # 交易金额
            "merchant_id": merchant_id,  # 商户id
            "merchant_orderid": code,  # 商户订单号
            # "paytype": "JazzCash",
            "paytype": "PKR-JAZZCASH",
            "notifyurl": notifyurl
        }
        params['sign'] = SignatureAndVerification.md5_sign(params, mer_key, "catspay").lower()

        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        self.logger.info(f"请求地址 ({pay_url}),发送的参数： ({params})")
        response = requests.post(pay_url, data=params, headers=headers, timeout=(5, 10))
        self.logger.info(f"请求地址 ({pay_url}),返回结果： ({response.text})")

        result = response.json()
        self.logger.info(f'{pay_name} 返回数据 {result}')
        if not str(result.get('status')) == '1':
            self.logger.error(f'{pay_name} 错误：[{result.get('status')}] [{result.get('message')}]')
            self.api_result = result.get('msg', result.get('message'))
            return False

        qr_url = result.get('data', {}).get('url')
        # order_num = result.get('data', {}).get('tx')

        # 更新数据库
        update_data = {
            'third_party_id': merchant_id,
            # 'third_party_order_number': order_num,
            'status': 1,
            'third_party_name': name,
        }
        condition = {'code': code}
        await self.update_result('orders_ds', update_data, condition)
        return qr_url  # 返回支付链接

    except Exception as e:
        # 使用 traceback.format_exc() 获取堆栈信息，并写入日志
        error_details = traceback.format_exc()  # 获取详细的异常堆栈信息
        self.logger.exception(f'gamepayer_payment 错误：{e}\n{error_details}')
        return False


async def payfast_payment(self, code, amount, merchant_id, secured_key, token_url, pay_url, merchant_callback=''):
    """
    PayFast 代收请求函数（巴基斯坦）
    两步流程：1) GetAccessToken  2) 浏览器表单 POST 到 PayFast
    """
    pay_name = "payfast"
    notifyurl = '/payfast_notify'
    try:
        # 获取 host
        notice_domain_api_list = await self.redis.get('notice_domain_api_list')
        if not notice_domain_api_list:
            host = self.request.protocol + '://' + self.request.host
        else:
            notice_domain_api_list = str(notice_domain_api_list).strip().split(',')
            notice_domain_api_list = [i.strip() for i in notice_domain_api_list if i != '']
            rs = len(notice_domain_api_list)
            rs = random.randint(0, rs - 1)
            host = notice_domain_api_list[rs]

        notify_full = host + notifyurl
        self.logger.info(f'[{pay_name}] host + callback_url: {notify_full}')

        # ---- Step 1: GetAccessToken ----
        token_params = (
            f'MERCHANT_ID={merchant_id}'
            f'&SECURED_KEY={secured_key}'
            f'&TXNAMT={amount}'
            f'&BASKET_ID={code}'
            f'&CURRENCY_CODE=PKR'
        )
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'CURL/PHP PayFast Example'
        }
        self.logger.info(f'[{pay_name}] GetAccessToken 请求: {token_url}')
        resp = requests.post(token_url, data=token_params, headers=headers, timeout=(5, 10))
        self.logger.info(f'[{pay_name}] GetAccessToken 返回: {resp.text}')

        token_data = resp.json()
        access_token = token_data.get('ACCESS_TOKEN', '')
        if not access_token:
            self.logger.error(f'[{pay_name}] GetAccessToken 失败: {token_data}')
            self.api_result = token_data.get('err_msg', 'Failed to get PayFast access token')
            return False

        # ---- Step 2: 将表单参数存入 Redis，由 /payfast/redirect/<code> 页面自动提交 ----
        order_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        form_data = {
            'MERCHANT_ID': str(merchant_id),
            'MERCHANT_NAME': 'Hamza Traders',
            'TOKEN': access_token,
            'PROCCODE': '00',
            'TXNAMT': str(amount),
            'CUSTOMER_MOBILE_NO': '',
            'CUSTOMER_EMAIL_ADDRESS': '',
            'SIGNATURE': f'PAYFAST-{code}',
            'VERSION': 'MERCHANTCART-0.1',
            'TXNDESC': f'Order {code}',
            'SUCCESS_URL': merchant_callback or notify_full,
            'FAILURE_URL': merchant_callback or notify_full,
            'BASKET_ID': code,
            'ORDER_DATE': order_date,
            'CHECKOUT_URL': notify_full,
            'CURRENCY_CODE': 'PKR',
            'Transaction_Instrument': '4',
            'PAY_URL': pay_url,
        }
        redis_key = f'payfast_redirect_{code}'
        await self.redis.set(redis_key, json.dumps(form_data), ex=1800)  # 30 min TTL
        self.logger.info(f'[{pay_name}] 表单数据已存入 Redis: {redis_key}')

        # 更新数据库
        update_data = {
            'third_party_id': str(merchant_id),
            'status': 1,
            'third_party_name': pay_name,
        }
        await self.update_result('orders_ds', update_data, {'code': code})

        # 返回 True 标记成功，实际跳转由 pay.py 接入自有收银台 /order/<token> 处理
        self.logger.info(f'[{pay_name}] 下单成功，表单数据已缓存，等待收银台跳转')
        return True

    except Exception as e:
        error_details = traceback.format_exc()
        self.logger.exception(f'[{pay_name}] payfast_payment 错误：{e}\n{error_details}')
        return False
