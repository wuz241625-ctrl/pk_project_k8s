import hashlib
import hmac
import json
import xml.etree.ElementTree as ET
from datetime import datetime

import pytz
import requests
from requests.adapters import HTTPAdapter
from urllib3 import Retry
from decimal import Decimal, InvalidOperation
import base64
import urllib
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization
import re
import time
from urllib.parse import urlencode
from application.message import msg
from urllib.parse import urlparse
import random
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad

async def md5_sign(data, api_key):
    if "sign" in data:
        del data["sign"]
    dataList = []
    for key in sorted(data):
        if data[key]:
            dataList.append("%s=%s" % (key, data[key]))
    data_str = "&".join(dataList).strip() + "&" + 'key' + "=" + api_key.strip()
    md5 = hashlib.md5()
    md5.update(data_str.encode(encoding='UTF-8'))
    ret = md5.hexdigest().upper()
    return ret


async def query_lucky_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    # 生成签名
    sign_string = f"{mer_id}&{code}{mc_key2}"
    sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()

    # 发起 GET 请求到查询接口
    params = {
        'clientCode': mer_id,
        'clientNo': code,
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
    self.logger.info(f'lucky query_order 请求URL: {response.url}')
    self.logger.info(f'lucky query_order 请求params: {params}')

    # 处理查询返回的数据
    if response.status_code == 200:
        result = response.json()
        if result.get("success") and result.get("code") == 200:
            data = result.get("data", {})
            order_status = data.get("status")
            pay_url = data.get("payUrl")

            # 在处理订单时使用查询结果
            if order_status == "PAID":
                self.logger.info(f"lucky 订单已支付。支付链接: {pay_url}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"lucky 订单状态: {order_status}")
                return False
        else:
            self.logger.error("lucky 查询失败:", result.get("code"), result.get("message"))
            return False
    else:
        self.logger.error("lucky 请求失败，状态码:", response.status_code)
        return False
    # return True


async def query_apay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
        data_post = dict()
        data_post['cid'] = mer_id
        data_post['tradeNo'] = code
        data_post['type'] = '003'
        data_post['sign'] = await md5_sign(data_post, mc_key)
        data_post['sign'] = data_post['sign'].lower()
        self.logger.info('{third_party_name}-查询订单-发送地址{url}，发送{data}'.format(third_party_name=third_party_name, url=query_url, data=data_post))

        s = requests.Session()
        s.mount('http://', HTTPAdapter(max_retries=Retry(total=5)))
        s.mount('https://', HTTPAdapter(max_retries=Retry(total=5)))
        try:
            response = s.post(query_url, data=data_post, timeout=(5, 5), verify=False)
        except Exception as e:
            self.logger.error('%s-查询订单%s,接口超时错误 %s,%s' % (third_party_name, code, query_url, e))
            return False
        s.close()
        self.logger.info('{third_party_name}-查询订单{code},结果{ret}'.format(third_party_name=third_party_name, code=code, ret=response.text))

        # 处理查询返回的数据
        if response.status_code == 200:
            result = response.json()
            if result.get("retcode") == '0':
                order_status = result.get("status")

                # 在处理订单时使用查询结果
                if order_status == "1":
                    self.logger.info(f"apay 订单已支付。支付订单： {code}")
                    return True
                else:
                    self.logger.error(f"apay 订单状态: {order_status}")
                    return False
            else:
                self.logger.error("apay 查询失败: {} {}".format(result.get("retcode"), result.get("status")))
                return False
        else:
            self.logger.error("apay 请求失败，状态码:", response.status_code)
            return False
        # return True

def regex_process(cls, query_string):
    # 使用正则表达式替换空值的键值对，变成只有键名
    result = re.sub(r'([&?])([^=]+)=([^&]*)', lambda m: m.group(1) + m.group(2) if m.group(3) == '' else m.group(0), query_string)
    
    return result

def sha256_sign(cls, data, private_key_pem, flag=False):
    """sha256签名生成"""
    private_key_pem = """-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----""".format(private_key_pem)
    # 排序并转换成 URL 参数形式
    sorted_params = sorted(data.items())
    sign_data = urllib.parse.urlencode(sorted_params, encoding='utf-8', doseq=True)
    if flag:
        # 使用正则表达式处理
        sign_data = regex_process(cls, sign_data)
    # 加载私钥
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None,
        backend=default_backend()
    )
    # 进行 SHA256withRSA 签名
    signature = private_key.sign(
        sign_data.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    encoded_signature = base64.b64encode(signature).decode()
    return encoded_signature

async def query_kingpay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    # 生成签名字段和签名
    sign_fields = {
        'merchantId': mer_id,
        'appId': mc_key,
        'timestamp': int(time.time() * 1000),  # 13-digit timestamp
        'outOrderId': code,
        'orderId': ''
    }
    sign = sha256_sign(self, sign_fields, private_key, True)

    # 请求数据
    request_data = {
        'merchantId': mer_id,
        'appId': mc_key,
        'outOrderId': code,
        'timestamp': sign_fields['timestamp'],
        'sign': sign
    }

    # 设置请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 "
                      "MQQBrowser/8.9 Mobile Safari/537.36",
        "Content-Type": "application/json"
    }

    # 发送 POST 请求
    data_post = json.dumps(request_data)
    response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

    # 打印请求日志
    self.logger.info(f'{third_party_name} query_order 请求URL: {query_url}')
    self.logger.info(f'{third_party_name} query_order 请求params: {request_data}')
    self.logger.info(f'{third_party_name} query_order 返回response: {response}')

    # 处理查询返回的数据
    if response.status_code == 200:
        result = response.json()
        self.logger.info(f'{third_party_name} query_order 返回result: {result}')
        if result.get("message") and result.get("code") == "0":
            # data = result.get("data", {})
            order_status = result.get("status")
            # 在处理订单时使用查询结果
            if order_status == 4:
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {result.get('code')}, {result.get('message')}")
            return False
    else:
        self.logger.error(f"{third_party_name} 请求失败，状态码: {response.status_code}")
        return False
    # return True

async def query_kingpay2_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    # 生成签名字段和签名
    sign_fields = {
        'merchantId': mer_id,
        'appId': mc_key,
        'timestamp': int(time.time() * 1000),  # 13-digit timestamp
        'outOrderId': code,
        'orderId': ''
    }
    sign = sha256_sign(self, sign_fields, private_key, True)

    # 请求数据
    request_data = {
        'merchantId': mer_id,
        'appId': mc_key,
        'outOrderId': code,
        'timestamp': sign_fields['timestamp'],
        'sign': sign
    }

    # 设置请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 "
                      "MQQBrowser/8.9 Mobile Safari/537.36",
        "Content-Type": "application/json"
    }

    # 发送 POST 请求
    data_post = json.dumps(request_data)
    response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

    # 打印请求日志
    self.logger.info(f'{third_party_name} query_order 请求URL: {query_url}')
    self.logger.info(f'{third_party_name} query_order 请求params: {request_data}')
    self.logger.info(f'{third_party_name} query_order 返回response: {response}')

    # 处理查询返回的数据
    if response.status_code == 200:
        result = response.json()
        self.logger.info(f'{third_party_name} query_order 返回result: {result}')
        if result.get("message") and result.get("code") == "0":
            # data = result.get("data", {})
            order_status = result.get("status")
            # 在处理订单时使用查询结果
            if order_status == 4:
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {result.get('code')}, {result.get('message')}")
            return False
    else:
        self.logger.error(f"{third_party_name} 请求失败，状态码: {response.status_code}")
        return False
    # return True


async def query_wepay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    """ 查询 WePay 订单状态 """

    # 生成签名字段
    params = {
        "mch_id": mer_id,
        "mch_order_no": code,
        "sign_type": "MD5",
    }

    # 生成签名
    params["sign"] = generate_wepay_md5_sign(params, mc_key)

    # 设置请求头
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # 配置请求重试机制
    session = requests.Session()
    session.mount("http://", HTTPAdapter(max_retries=3))
    session.mount("https://", HTTPAdapter(max_retries=3))

    try:
        # 发送 POST 请求
        response = session.post(query_url, data=urlencode(params), headers=headers, timeout=(5, 5))

        # 记录请求日志
        self.logger.info(f'{third_party_name} query_order 请求URL: {query_url}')
        self.logger.info(f'{third_party_name} query_order 请求params: {params}')
        self.logger.info(f'{third_party_name} query_order 返回response: {response.text}')

        # 处理返回数据
        if response.status_code == 200:
            result = response.json()
            self.logger.info(f'{third_party_name} query_order 返回result: {result}')
            
            if result.get("respCode") == "SUCCESS":
                order_status = result.get("tradeResult")  # 获取订单状态
                
                if int(order_status) == 1:  # 假设 1 表示支付成功
                    self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                    return True
                else:
                    self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                    return False
            else:
                self.logger.error(f"{third_party_name} 查询失败: {result.get('respCode')}, {result.get('respMsg')}")
                return False
        else:
            self.logger.error(f"{third_party_name} 请求失败，状态码: {response.status_code}")
            return False

    except Exception as e:
        self.logger.error(f"{third_party_name} 查询订单 {code} 发生异常: {e}")
        return False

    finally:
        session.close()

def generate_wepay_md5_sign(params, private_key):
    """
    生成 WePay MD5 签名
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


async def query_777pay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    data_post = {
        "app_id": mer_id,
        "merchant_order_id": code
    }

    # 生成签名
    data_post["sign"] = generate_wepay_md5_sign(data_post, mc_key)

    # 设置请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 "
                      "MQQBrowser/8.9 Mobile Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    # 发送 POST 请求
    response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

    # 打印请求日志
    self.logger.info(f'{third_party_name} query_order 请求URL: {query_url}')
    self.logger.info(f'{third_party_name} query_order 请求params: {data_post}')
    self.logger.info(f'{third_party_name} query_order 返回response: {response}')

    # 处理查询返回的数据
    if response.status_code == 200:
        result = response.json()
        self.logger.info(f'{third_party_name} query_order 返回result: {result}')
        if str(result.get("code")) == "200":
            data = result.get("data", {})
            order_status = data.get("order_status")
            # 在处理订单时使用查询结果
            if order_status == 'PAY_SUCCESS':
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {result.get('code')}, {result.get('message')}")
            return False
    else:
        self.logger.error(f"{third_party_name} 请求失败，状态码: {response.status_code}")
        return False
    # return True


def sha1_swiftpay_sign(data, private_key_pem):
    """sha1签名生成"""
    private_key_pem = """-----BEGIN RSA PRIVATE KEY-----\n{}\n-----END RSA PRIVATE KEY-----""".format(private_key_pem)
    # 排序并转换成 URL 参数形式
    sorted_params = sorted(data.items())
    sign_data = urllib.parse.urlencode(sorted_params, encoding='utf-8', doseq=True)
    # 加载私钥
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode(),
        password=None,
        backend=default_backend()
    )
    # 进行 SHA1withRSA 签名
    signature = private_key.sign(
        sign_data.encode(),
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    encoded_signature = base64.b64encode(signature).decode()
    return encoded_signature


async def query_swiftpay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    data_post = {
        "merchantNo": mer_id,
        "orderId": code
    }
    # 生成签名
    data_post["sign"] = sha1_swiftpay_sign(data_post, private_key)
    data_post = json.dumps(data_post)

    # 设置请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 "
                      "MQQBrowser/8.9 Mobile Safari/537.36",
        "Content-Type": "application/json"
    }
    # 发送 POST 请求
    response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

    # 打印请求日志
    self.logger.info(f'{third_party_name} query_order 请求URL: {query_url}')
    self.logger.info(f'{third_party_name} query_order 请求params: {data_post}')
    self.logger.info(f'{third_party_name} query_order 返回response: {response}')
    self.logger.info(f'{third_party_name} query_order 返回content: {response.text}')

    # 处理查询返回的数据
    if response.status_code == 200:
        result = response.json()
        self.logger.info(f'{third_party_name} query_order 返回result: {result}')
        if str(result.get("errNo")) == "0":
            data = result.get("data", {})
            order_status = data.get("status")
            # 在处理订单时使用查询结果
            if str(order_status) == '2':
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {result.get('code')}, {result.get('message')}")
            return False
    else:
        self.logger.error(f"{third_party_name} 请求失败，状态码: {response.status_code}")
        return False
    # return True


def data_processing(data):
    if "sign" in data:
        del data["sign"]
    dataList = []
    for key in sorted(data):
        if data[key]:
            dataList.append("%s=%s" % (key, data[key]))
    return "&".join(dataList).strip()


def hmac_sha256_sign(data: dict, secret_key: str) -> str:
    """
    生成 HMAC-SHA256 签名

    参数说明：
    params - 包含所有请求参数的字典(需包含除sign外的所有有效参数)
    secret_key - 商户平台分配的密钥

    返回：
    Base64编码的签名字符串
    """
    # 构造签名字符串
    sign_str = data_processing(data)

    # 计算HMAC-SHA256
    digest = hmac.new(
        secret_key.encode('utf-8'),
        sign_str.encode('utf-8'),
        hashlib.sha256
    ).digest()

    # Base64编码
    return base64.b64encode(digest).decode('utf-8').strip()


async def query_snakepay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    order = await self.get_result_by_condition('orders_ds', '*', {'code': code})
    if not order['utr']:
        self.logger.error(f"{third_party_name} 订单 {code} 无utr，无法补单")
        return False

    # 发起 POST 请求到查询接口
    data_post = dict()
    data_post['merchantNo'] = mer_id
    data_post['utr'] = order['utr']
    data_post['sign'] = hmac_sha256_sign(data_post, mc_key)
    data_post = json.dumps(data_post)
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
        'Content-Type': 'application/json'
    }
    # 发起 POST
    response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

    # 打印请求日志
    self.logger.info(f'{third_party_name} query_order 请求URL: {query_url}')
    self.logger.info(f'{third_party_name} query_order 请求params: {data_post}')
    self.logger.info(f'{third_party_name} query_order 返回response: {response}')
    self.logger.info(f'{third_party_name} query_order 返回content: {response.text}')

    # 处理查询返回的数据
    if response.status_code == 200:
        result = response.json()
        self.logger.info(f'{third_party_name} query_order 返回result: {result}')
        if str(result.get("code")) == "200":
            order_status = str(result.get("data", {}).get('status'))
            # 在处理订单时使用查询结果
            if str(order_status) == '2':
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {result}")
            return False
    else:
        self.logger.error(f"{third_party_name} 请求失败，状态码: {response.status_code}")
        return False
    # return True


async def query_quickpay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    """
    代收订单查询
    """
    params = {
        "merchantNo": mer_id,
        "orderId": code,
    }

    # 生成签名
    params["sign"] = rsa_sha1_sign(params, private_key)

    headers = {"Content-Type": "application/json"}
    params = json.dumps(params)
    try:
        self.logger.info(f'QuickPay 发送地址 {query_url}, 发送数据 {params}')
        response = requests.post(query_url, data=params, headers=headers, timeout=(5, 10))
        self.logger.info(f"查询订单 {code}, 返回结果: {response.text}")

        if response.status_code != 200:
            self.logger.error(f"查询订单 {code} 失败，HTTP 状态码: {response.status_code}")
            return False

        result = response.json()
        if result.get("errNo") != "0":
            self.logger.error(f"查询订单 {code} 失败, 返回: {result}")
            return False
        
        self.logger.info(f'{third_party_name} query_order 返回result: {result}')
        if str(result.get("errNo")) == "0":
            data = result.get("data", {})
            order_status = data.get("status")
            self.logger.info(f'{third_party_name} query_order 返回result: {order_status}')
            # 在处理订单时使用查询结果
            if str(order_status) == '2':
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {result.get('code')}, {result.get('message')}")
            return False

    except Exception as e:
        self.logger.error(f"查询订单 {code} 发生异常: {e}")
        return False
    # return True

def rsa_sha1_sign(data, private_key_pem):
        """使用 RSA 私钥对数据进行 SHA1 签名"""
        private_key_pem = """-----BEGIN PRIVATE KEY-----\n{}\n-----END PRIVATE KEY-----""".format(private_key_pem)
        # 1. 过滤掉值为空的参数（保留 0、False）
        filtered_data = {k: v for k, v in data.items() if v is not None and v != ""}
        # 2. 按参数名 ASCII 码顺序排序
        sorted_params = sorted(filtered_data.items())
        # 3. URL 编码值，并拼接成签名字符串（确保空格转换为 +）
        sign_data = urllib.parse.urlencode(sorted_params, encoding='utf-8', doseq=False)
        try:
            # 4. 解析 PKCS#8 私钥
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),  # 确保私钥是字节格式
                password=None,
                backend=default_backend()
            )
            # 5. 进行 SHA1 with RSA 签名
            signature = private_key.sign(
                sign_data.encode(),  # 需要签名的数据（字节格式）
                padding.PKCS1v15(),  # 填充方式
                hashes.SHA1()  # 哈希算法
            )
            # 6. 对签名结果进行 Base64 编码
            encoded_signature = base64.b64encode(signature).decode()
            return encoded_signature
        except Exception as e:
            raise ValueError(f"签名失败: {str(e)}")

async def query_hkpay_order(self, mer_id, code, mc_key, mc_key2, query_url, third_party_name, private_key='', third_party_order_number=''):
    """
    代收订单查询
    """
    params = {
        "merchantid": mer_id,
        "merchant_orderno": code,
        "type": "collect",
    }

    # 生成签名
    params["sign"] = generate_md5_sign(params, mc_key)

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        self.logger.info(f'HKPay 查询订单，URL: {query_url}, 发送数据: {params}')
        response = requests.post(query_url, data=params, headers=headers, timeout=(5, 10))
        self.logger.info(f"查询订单 {code}, 返回结果: {response.text}")

        if response.status_code != 200:
            self.logger.error(f"查询订单 {code} 失败，HTTP 状态码: {response.status_code}")
            return None

        res_data = response.json()
        if res_data.get("code") != 200:
            self.logger.error(f"查询订单 {code} 失败, 返回: {res_data}")
            return None
        
        self.logger.info(f'{third_party_name} query_order 返回result: {res_data}')
        if str(res_data.get("code")) == "200":
            data = res_data.get("data", {})
            order_status = data.get("status")
            self.logger.info(f'{third_party_name} query_order 返回result: {order_status}')
            # 在处理订单时使用查询结果
            if str(order_status) == 'success':
                self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
                # 进行下一步处理
                return True
            else:
                self.logger.error(f"{third_party_name} 订单状态: {order_status}")
                return False
        else:
            self.logger.error(f"{third_party_name} 查询失败: {res_data.get('code')}, {res_data.get('message')}")
            return False

    except Exception as e:
        self.logger.error(f"查询订单 {code} 发生异常: {e}")
        return False
    # return True

def generate_md5_sign(data, md5_key):
    """
    生成 MD5 签名
    """
    sign_string = "&".join(f"{k}={str(v).strip()}" for k, v in sorted(data.items()) if v) + f"&key={md5_key}"
    return hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()

async def query_skpay_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name, access_secret='', third_party_order_number=''):
    """
    SKPay 查询订单接口（基于新签名方式）
    """
    try:
        url_path = urlparse(query_url).path
        signature_info = generate_signature_skpay("POST", url_path, access_key, access_secret)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 9; MI MAX 3...)',
            "Content-Type": "application/json",
            "accessKey": access_key,
            "timestamp": signature_info["timestamp"],
            "nonce": signature_info["nonce"],
            "sign": signature_info["sign"]
        }

        # 发起 POST 请求到查询接口
        data_post = dict()
        data_post['orderNo'] = third_party_order_number
        data_post['merchantOrderNo'] = code

        data_post_str = json.dumps(data_post)
        self.logger.info(f'[SKPay] 查询订单 URL: {query_url}, headers: {headers}, request: {data_post_str}')

        response = requests.post(query_url, data=data_post_str, headers=headers, timeout=(5, 10))
        self.logger.info(f'[SKPay] 查询订单返回: {response}')
        result = response.json()

        self.logger.info(f'[SKPay] 查询订单返回: {result}')

        query_status = str(result.get("data", {}).get("status"))
        status = str(data_post.get("status", ""))

        self.logger.info(f"[SKPay] 查询订单状态: {query_status}")
        self.logger.info(f"[SKPay] 回调通知状态: {status}")

        if query_status is None:
            # return self.write("error: query failed")
            return False
        
        if status == "success":
            self.logger.error('[SKPay] 订单支付成功')
            return True

        if status != "success":
            self.logger.error('[SKPay] 订单未支付成功')
            # return self.write({"code": "1", "message": "not paid"})
            return False

    except Exception as e:
        self.logger.error(f"[SKPay] 查询订单异常: {e}")
        # return self.write("error: exception occurred")
        return False

    # return self.write("success")

def generate_signature_skpay(method, url_path, access_key, access_secret):
    method = method.upper()  # 确保是大写
    timestamp = str(int(time.time()))
    nonce = str(random.randint(100000, 999999))
    # 拼接字符串
    raw_string = f"{method}&{url_path}&{access_key}&{timestamp}&{nonce}"
    # HMAC-SHA256 + Base64
    # 生成 HMAC-SHA256，然后 Base64 编码
    hmac_obj = hmac.new(access_secret.encode(), raw_string.encode(), hashlib.sha256)
    sign = base64.b64encode(hmac_obj.digest()).decode()
    # 返回签名相关参数
    return {
        "sign": sign,
        "timestamp": timestamp,
        "nonce": nonce
    }


async def query_ospay_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name, access_secret='', third_party_order_number=''):
    """
    ospay 查询订单接口（基于新签名方式）
    """
    try:
        data_post = dict()
        data_post['mer_id'] = mer_id
        data_post['order_id'] = code
        data_post['sign'] = generate_md5_sign(data_post, access_key).upper()
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        # 发起 POST
        response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        result = response.json()
        # 打印请求参数日志
        self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

        if response.status_code != 200:
            self.logger.error(f"查询订单 {code} 失败，HTTP 状态码: {response.status_code}")
            return None

        query_status = str(result.get("data", {}).get('status'))
        self.logger.info(f"[{third_party_name}] 查询订单状态: {query_status}")

        # 在处理订单时使用查询结果
        if str(query_status) == '0':
            self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
            # 进行下一步处理
            return True
        else:
            self.logger.error(f"{third_party_name} 订单状态: {query_status}")
            return False

    except Exception as e:
        self.logger.error(f"查询订单 {code} 发生异常: {e}")
        return None
    # return True


async def query_ospay_upi_order(*args, **kwargs):
    return await query_ospay_order(*args, **kwargs)

async def query_789pay_upi_order(*args, **kwargs):
    return await query_ospay_order(*args, **kwargs)

async def query_789pay_order(*args, **kwargs):
    return await query_ospay_order(*args, **kwargs)

async def query_TataPay_t100037_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name, access_secret='', third_party_order_number=''):
    return await query_TataPay_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name, access_secret, third_party_order_number)

async def query_TataPay_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name, access_secret='', third_party_order_number=''):
    """
    tatapay 查询订单接口
    """
    try:
        data_post = dict()
        data_post['merchNo'] = mer_id
        data_post['orderNo'] = code
        # data_post['UTR'] = code
        sorted_items = sorted(data_post.items())
        source = '&'.join(f"{k}={v}" for k, v in sorted_items)
        data_post['sign'] = hashlib.md5((source + access_key).encode()).hexdigest()
        headers = {
            # "User-Agent": "Mozilla/5.0 (Linux; U; Android 8.1.0; zh-cn; BLA-AL00 Build/HUAWEIBLA-AL00) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/57.0.2987.132 MQQBrowser/8.9 Mobile Safari/537.36",
            'Content-Type': 'application/json'
        }
        # 发起 POST
        response = requests.post(query_url, json=data_post, headers=headers, timeout=(5, 5), verify=False)
        result = response.json()
        # 打印请求参数日志
        self.logger.info(f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

        if response.status_code != 200:
            self.logger.error(f"查询订单 {code} 失败，HTTP 状态码: {response.status_code}")
            return None

        if result.get('code'): # code 不为 0
            self.logger.error(f"查询订单 {code} 失败，状态: {result.get('code')}，msg：{result.get('msg')}")
            return None

        query_status =  str(result.get("data", {}).get('orderState'))
        self.logger.info(f"[{third_party_name}] 查询订单状态: {query_status}")

        # 在处理订单时使用查询结果
        if str(query_status) == '1':
            self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
            # 进行下一步处理
            return True
        else:
            self.logger.error(f"{third_party_name} 订单状态: {query_status}")
            return False

    except Exception as e:
        self.logger.error(f"查询订单 {code} 发生异常: {e}")
        return None
    # return True

async def query_Vibrapay_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name,
                                  access_secret='', third_party_order_number=''):
    """
    Vibrapay 查询订单接口
    """
    try:
        # 发起 POST 请求到查询接口
        data_post = dict()
        data_post['merchant_slug'] = mer_id
        data_param_code = dict()
        data_param_code['merchant_order_num'] = code
        data_post['data'] = aes_256_cbc_encrypt(access_key, mc_key2,json.dumps(data_param_code))

        # 构造请求头 ， 查询订单
        headers = {
            "Content-Type": "application/json",
        }

        data_post = json.dumps(data_post)
        # 发起 POST
        response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)

        if response.status_code != 200:
            self.logger.error(f"查询订单 {code} 失败，HTTP 状态码: {response.status_code}")
            return None

        result = response.json()

        # 打印请求参数日志
        self.logger.info(
            f'query_order 请求URL: {response.url}, header: {headers}, request data: {data_post}, result: {result}')

        if not str(result.get('code')) == '0':
            self.logger.error(f"查询订单 {code} 失败，状态: {result.get('code')}，msg：{result.get('msg')}")
            return None

        query_order = aes_256_cbc_decrypt(access_key, mc_key2,result['order'])
        query_order = json.loads(query_order)
        query_status = query_order.get('status')
        self.logger.info(f"[{third_party_name}] 查询订单状态: {query_status}")

        # 在处理订单时使用查询结果
        if str(query_status) == 'success':
            self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
            # 进行下一步处理
            return True
        else:
            self.logger.error(f"{third_party_name} 订单状态: {query_status}")
            return False

    except Exception as e:
        self.logger.error(f"查询订单 {code} 发生异常: {e}")
        return None

def aes_256_cbc_encrypt(key, iv, data):
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    encrypted = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
    return base64.b64encode(encrypted).decode('utf-8')

def aes_256_cbc_decrypt(key, iv, data):
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    decrypted = cipher.decrypt(base64.b64decode(data))
    return unpad(decrypted, AES.block_size).decode('utf-8')

async def query_qqpay_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name,
                                  access_secret='', third_party_order_number=''):
    """
    qqpay 查询订单接口
    """
    try:
        # 发起 POST 请求到查询接口
        data_post = dict()
        data_post['merchant_id'] = mer_id
        data_post['mer_order_num'] = code
        data_post['timestamp'] = str(int(time.time()))
        data_post['type'] = 1
        # 计算验证签名
        data_post['sign'] = hmac_sha256_sign(data_post, access_key)

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
            self.logger.error(f"查询订单 {code} 失败，HTTP 状态码: {response.status_code}")
            return None

        query_status = str(result.get("data", {}).get('status'))
        self.logger.info(f"[qqpay] 查询订单返回值: {query_status}")

        # 在处理订单时使用查询结果
        if str(query_status) == '2':
            self.logger.info(f"{third_party_name} 订单已支付。订单号: {code}")
            # 进行下一步处理
            return True
        else:
            self.logger.error(f"{third_party_name} 订单状态: {query_status}")
            return False

    except Exception as e:
        self.logger.error(f"查询订单 {code} 发生异常: {e}")
        return None

async def query_gamepayer_order(self, mer_id, code, access_key, mc_key2, query_url, third_party_name,
                                  private_key, third_party_order_number=''):
    """
    gamepayer 查询订单接口
    """
    try:
        pay_name = "gamepayer"
        # 发起 POST 请求到查询接口
        data_post = dict()
        data_post['merchant_id'] = mer_id
        data_post['merchant_orderid'] = code
        data_post['datetime'] = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')

        # 计算验证签名
        query_str = f'{"&".join(f"{key}={value}" for key, value in dict(sorted(data_post.items(), key=lambda item: item[0])).items())}{access_key}'
        data_post['sign'] = hashlib.md5(query_str.encode('utf-8')).hexdigest().lower()

        # 构造请求头 ， 查询订单
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        self.logger.info(f'[{pay_name}] query_order 请求URL: {query_url}, data: {data_post}')
        response = requests.post(query_url, data=data_post, headers=headers, timeout=(5, 5), verify=False)
        result = response.json()
        # 打印请求参数日志
        self.logger.info(f'[{pay_name}] query_order 请求URL: {response.url}, result: {result}')

        if not str(result.get('status')) == '1':
            self.logger.error(f"查询错误: [{result.get('status')}]")
            return self.write(f"查询错误: {result.get('status')}")

        query_status = str(result.get('data', {}).get("status", None))
        self.logger.info(f"[{pay_name}] 查询订单返回值: {query_status}")

        # 在处理订单时使用查询结果
        if query_status == '1':
            self.logger.info(f"[{pay_name}] {third_party_name} 订单已支付。订单号: {code}")
            # 进行下一步处理
            return True
        else:
            return False

    except Exception as e:
        self.logger.error(f"[{pay_name}] 查询订单 {code} 发生异常: {e}")
        return None


# ---------------------------------------------------------------------------
# easypay (SOAP inquireTransaction)
# ---------------------------------------------------------------------------
_EASYPAY_INQUIRE_SKIP_TAGS = ('Envelope', 'Body', 'inquireTransactionResponseType')


def _easypay_norm_msisdn(raw):
    digits = re.sub(r'\D', '', str(raw or ''))
    digits = digits.lstrip('0')
    if digits.startswith('92'):
        digits = digits[2:]
    return digits


def _easypay_xml_escape(value):
    return (str(value if value is not None else '')
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))


def _easypay_build_inquire_xml(username, password, order_id, account_num):
    esc = _easypay_xml_escape
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap-env:Envelope xmlns:soap-env="http://schemas.xmlsoap.org/soap/envelope/">'
        '<soap-env:Body>'
        '<ns0:inquireTransactionRequestType'
        ' xmlns:ns0="http://dto.transaction.partner.pg.systems.com/">'
        f'<ns1:username xmlns:ns1="http://dto.common.pg.systems.com/">{esc(username)}</ns1:username>'
        f'<ns2:password xmlns:ns2="http://dto.common.pg.systems.com/">{esc(password)}</ns2:password>'
        f'<orderId>{esc(order_id)}</orderId>'
        f'<accountNum>{esc(account_num)}</accountNum>'
        '</ns0:inquireTransactionRequestType>'
        '</soap-env:Body>'
        '</soap-env:Envelope>'
    )


def _easypay_parse_inquire(text):
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    result = {}
    for elem in root.iter():
        local = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if local in _EASYPAY_INQUIRE_SKIP_TAGS:
            continue
        if elem.text and elem.text.strip():
            result[local] = elem.text.strip()
    return result


async def query_easypay_order(self, mer_id, code, mc_key, mc_key2, query_url,
                              third_party_name, private_key='',
                              third_party_order_number=''):
    """
    easypay 三方补单：SOAP inquireTransaction 查询订单。

    死规则（返回 True 的所有条件）:
      1. responseCode == '0000' 且 transactionStatus == 'PAID'
      2. 响应 msisdn 存在，且归一化后等于 admin 输入的 utr 归一化值
      3. 响应 transactionAmount 存在，且按 Decimal 比较等于 orders_ds.amount

    返回:
      True  — 全部通过，可回调
      False — SOAP 有响应但任意校验未通过 / 关键字段缺失
      None  — 网络异常 / 配置缺失 / 解析失败 / 其他不确定

    注: query_url 参数被忽略。生产 otherpay.query_url 为垃圾值；
        SOAP endpoint 从 otherpay.pay_url 读取。
    """
    pay_name = 'easypay'
    setattr(self, '_easypay_query_result', None)
    try:
        # admin 输入的 utr 由 handleOrderFromThird 挂在 self 上（与事务共享连接无关）
        admin_utr = getattr(self, '_easypay_admin_utr', None) or ''
        expected_msisdn_norm = _easypay_norm_msisdn(admin_utr)
        if not expected_msisdn_norm:
            self.logger.error(f"[{pay_name}] 缺少 admin 输入的手机号（utr），code={code}")
            return False

        # 1. 从 otherpay 重新取 SOAP endpoint（query_url 字段生产上是垃圾值）
        otherpay_rows = await self.query(
            'SELECT pay_url FROM otherpay WHERE name=%s AND merchant_id=%s LIMIT 1',
            third_party_name, mer_id,
        )
        if not otherpay_rows or not otherpay_rows[0].get('pay_url'):
            self.logger.error(
                f"[{pay_name}] otherpay config missing, name={third_party_name} merchant_id={mer_id}")
            return None
        soap_url = otherpay_rows[0]['pay_url']

        # 2. 取订单金额
        order_rows = await self.query(
            'SELECT amount FROM orders_ds WHERE code=%s LIMIT 1', code,
        )
        if not order_rows:
            self.logger.error(f"[{pay_name}] 订单不存在，code={code}")
            return None
        try:
            expected_amount = Decimal(str(order_rows[0]['amount']))
        except (InvalidOperation, TypeError):
            self.logger.error(
                f"[{pay_name}] 订单金额非法 {order_rows[0].get('amount')}，code={code}")
            return None

        # 3. 发起 SOAP inquireTransaction
        xml_body = _easypay_build_inquire_xml(mc_key, mc_key2, code, mer_id)
        headers = {'Content-Type': 'text/xml; charset=utf-8'}
        self.logger.info(
            f'[{pay_name}] query_order 请求 URL: {soap_url}, order_id={code}, account_num={mer_id}')
        response = requests.post(
            soap_url, data=xml_body, headers=headers, timeout=(5, 30), verify=False)
        self.logger.info(
            f'[{pay_name}] query_order 原始响应, code={code}: {response.text}')

        if response.status_code != 200:
            self.logger.error(
                f"[{pay_name}] HTTP 状态异常 {response.status_code}，code={code}")
            return None

        parsed = _easypay_parse_inquire(response.text)
        if parsed is None:
            self.logger.error(f"[{pay_name}] XML 解析失败，code={code}")
            return None
        self.logger.info(
            f'[{pay_name}] query_order 解析结果, code={code}: {parsed}')

        # 4. responseCode 校验
        if parsed.get('responseCode') != '0000':
            self.logger.warning(
                f"[{pay_name}] responseCode={parsed.get('responseCode')} 非 0000，code={code}")
            return False

        # 5. transactionStatus 校验
        if parsed.get('transactionStatus') != 'PAID':
            self.logger.warning(
                f"[{pay_name}] transactionStatus={parsed.get('transactionStatus')} 非 PAID，code={code}")
            return False

        # 6. 死规则 — 响应 msisdn 必须存在且匹配
        resp_msisdn = parsed.get('msisdn')
        if not resp_msisdn:
            self.logger.error(
                f"[{pay_name}] 响应缺 msisdn 字段，拒绝补单，code={code}")
            return False
        resp_msisdn_norm = _easypay_norm_msisdn(resp_msisdn)
        if resp_msisdn_norm != expected_msisdn_norm:
            self.logger.warning(
                f"[{pay_name}] 手机号不匹配，期望={expected_msisdn_norm} "
                f"响应={resp_msisdn_norm} (raw={resp_msisdn})，code={code}")
            return False

        # 7. 死规则 — 响应 transactionAmount 必须存在且匹配
        resp_amount_raw = parsed.get('transactionAmount')
        if not resp_amount_raw:
            self.logger.error(
                f"[{pay_name}] 响应缺 transactionAmount 字段，拒绝补单，code={code}")
            return False
        try:
            resp_amount = Decimal(resp_amount_raw)
        except (InvalidOperation, TypeError):
            self.logger.error(
                f"[{pay_name}] transactionAmount 非法 {resp_amount_raw}，code={code}")
            return False
        if resp_amount != expected_amount:
            self.logger.warning(
                f"[{pay_name}] 金额不匹配，期望={expected_amount} 响应={resp_amount}，code={code}")
            return False

        setattr(self, '_easypay_query_result', parsed)
        self.logger.info(
            f"[{pay_name}] 订单已支付且手机号+金额校验通过，可回调，code={code}")
        return True

    except requests.RequestException as e:
        self.logger.error(f"[{pay_name}] 网络异常 code={code}: {e}")
        return None
    except Exception as e:
        self.logger.error(f"[{pay_name}] 查询异常 code={code}: {e}")
        return None
