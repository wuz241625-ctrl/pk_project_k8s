import base64
import hashlib
import json
import logging
import os
import random
import secrets
import string
import sys
import time
import traceback
import uuid
# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Dict

import redis
import requests
import simplejson
from Cryptodome.Cipher import AES
from requests.adapters import HTTPAdapter
from sshtunnel import SSHTunnelForwarder

from response_logger import ResponseLogger

current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
parent2_dir = os.path.dirname(parent_dir)
sys.path.append(parent2_dir)

import config
from application.lakshmi_api.enums.payment_login_progress import PaymentLoginProgress

# 添加一个Filter来处理trace_id
class TraceIDFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.trace_id = '-'
    
    def filter(self, record):
        if not hasattr(record, 'trace_id'):
            record.trace_id = self.trace_id
        return True

# 先创建trace_id filter
trace_id_filter = TraceIDFilter()

date_format = '%Y-%m-%d %H:%M:%S'
format_str = '%(asctime)s %(levelname)s [%(trace_id)s] %(filename)s.%(funcName)s():%(lineno)d -> %(message)s '
formatter = logging.Formatter(format_str, date_format)

# 设置控制台日志
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.DEBUG)
console_handler.addFilter(trace_id_filter)

# 设置文件日志
LOG_FILE = f"jio_{os.getpid()}.log"
file_handler = TimedRotatingFileHandler(LOG_FILE, when='MIDNIGHT', interval=1, backupCount=15, encoding='utf-8')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)
file_handler.addFilter(trace_id_filter)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

conf = config.get_config()

API_SERVER_DOMAIN = conf['ospay_api_host']

# 同步交易记录最大失败次数，达到后，下线
SYNC_TRANSACTION_HISTORY_MAX_FAILURES_NUM = 30

# payment_id绑定的android_id的过期时间
PAYMENT_ANDROID_ID_DEFAULT_EXPIRE_SECONDS = 60 * 60 * 24 * 100

# 配置信息
CONNECTION_REDIS_METHOD = 'DIRECT'  # 连接redis服务的2种方式('SSH', 'DIRECT')
SSH_HOST = '127.0.0.1'
SSH_PORT = 22
SSH_USERNAME = 'root'
SSH_PKEY_PATH = 'id_rsa_2048_ceshi'
REDIS_HOST = '127.0.0.1'  # Redis在远程服务器上的主机
REDIS_PORT = 6379  # Redis端口
REDIS_PASSWORD = None  # Redis密码，如果有的话


def connect_redis_via_ssh(
        ssh_host,
        ssh_port,
        ssh_username,
        ssh_pkey_path,
        redis_host='127.0.0.1',
        redis_port=6379,
        redis_password=None
):
    try:
        # 创建SSH隧道
        tunnel = SSHTunnelForwarder(
            ssh_address_or_host=(ssh_host, ssh_port),
            ssh_username=ssh_username,
            ssh_pkey=ssh_pkey_path,  # SSH私钥路径
            remote_bind_address=(redis_host, redis_port)
        )

        # 启动隧道
        tunnel.start()

        # 连接Redis
        redis_client = redis.Redis(
            host=redis_host,
            port=tunnel.local_bind_port,
            password=redis_password,
            decode_responses=False,
            encoding='utf-8'
        )

        return tunnel, redis_client

    except Exception as e:
        logger.error(f"连接错误: {str(e)}")
        return None, None


class BankLogin(object):
    versionNo = 4072
    SECRET_KEY = (
        "MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGBAMGemlD5EnjK2Vv+iaJVsrJj69c2nTeT5h7kKf3Y8Di0Q+gbCkpstwy9woFFGUjGz2K+HWnb7gWMseK/"
        "Xfz80dNR20KeEoZbfDzxLgbnAnkMjuBFi1XqvlLbT4m/KRbRJUjPAj7WcAujxxZUc7Ur6UFVz9lkrOUThTJNVFyfH0IRAgMBAAECgYBd/6r5jsJqBEkcQWn+ds6Hjr0rw"
        "ab4GYSKEMlWJSES1ml1YNNRKJCBzgqFCc/ppiN+07+h6hUXeqPN6owty2vt7A3bq7c4ZtP33l9YLcdXcEweNDK5jyDtsoU7f4VNuwDLEQ9nmNtH/2v+wXHLKOtgKgLL"
        "/+bubmmiHNYpeg/f1QJBAPH6e9d4GN/sAqQcJmDtNXgbO3k0d6bL8KW5TYyp1i6N3ltm9Dc++BUhAdGJcduRa6viJh+ePzXcfyoCGZ/XmzMCQQDM1sLqyXrUo0h7wlZ4"
        "IpgvxomsLARhbGkufaeIdlfxI/aIqtKzs7RgEgg0m1vfYX06GOhDYlsfqO/ZctyT4w2rAkBgcArBMfz/6SiYTRvCj2c66eeHA7EYCblr4vEUOW/B+AqBdQOprO/kQ9Z"
        "csyFsd4Vo6GV3PnNEvQ71KAccXCpfAkEAhFK317QQBQz15fzEnxa5+SLoDLDio4zE5aOGdkD8zmnM+LxhIHUWMHl1k4ZI8ySnIMC2SdFfzDP1vSLWGzKxwQJANcIVSZ"
        "szFlM9MHaUbpf0A9Z1Cio8Rehib+xUVOuGEVZCftKcDzzsTjA6i0o2f4PPpJ008cr3bFs0Y3MNzhl2BQ=="
    )

    def __init__(self):
        self.name = 'jio'
        self.list_key = 'login_jio'
        self.hash_key = 'login_jio_hash'
        self.set_key = 'login_jio_set'
        self.cache_key_transaction_history_synced_utr = 'login_jio_transaction_history_utr_synced'
        self.lock_time = 40  # 操作锁的锁定时间
        self.lock_time2 = 15  # 登录锁的锁定时间
        self.time_grab = 30  # 短时间频繁爬取
        self.time_grab2 = 10 * 60  # 长时间爬取
        self.order_time_out = 5 * 60
        self.upi_try_limit = 10  # 最大尝试爬取upi，(爬取upi失败还可以爬取账单)
        self.order_grab_time_out = 4 * 60 * 60  # 检测爬取的账单时间是否在规定范围内，不是则舍弃
        self.domain = API_SERVER_DOMAIN
        self.session = None
        self.logger = None
        self.response_logger = None
        self.id = None  # payment id
        self.login_data = None
        self.try_count = 8  # 重试次数
        self.list_count = 4  # 当list个数小于某个值之后暂缓pop，避免导致爬取过快
        self.list_count_time = 4
        self.android_id = None
        self.local_mock = False

        # 连接redis
        if CONNECTION_REDIS_METHOD == 'SSH':
            # 通过SSH隧道连接redis服务
            tunnel, redis_client = connect_redis_via_ssh(
                ssh_host=SSH_HOST,
                ssh_port=SSH_PORT,
                ssh_username=SSH_USERNAME,
                ssh_pkey_path=SSH_PKEY_PATH,
                redis_host=REDIS_HOST,
                redis_port=REDIS_PORT,
                redis_password=REDIS_PASSWORD
            )
            self.redis = redis_client
            self.tunnel = tunnel
        else:
            # 直连redis服务
            self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    @staticmethod
    def generate_android_id():
        """Generate a random 16-character Android ID."""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(16))

    @classmethod
    def generate_key(cls):
        """Generate a 256-bit key using SHA-256 hash of the SECRET_KEY."""
        sha256 = hashlib.sha256()
        sha256.update(cls.SECRET_KEY.encode())
        return sha256.digest()[:32]

    @classmethod
    def encrypt_message(cls, plaintext, iv):
        """Encrypt the plaintext message using AES GCM."""
        try:
            key = cls.generate_key()
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv[:12])
            ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
            combined = iv[:12] + ciphertext + tag
            return base64.b64encode(combined).decode()
        except Exception as e:
            print(f"Encryption error: {str(e)}")
            return ""

    @classmethod
    def decrypt_message(cls, encrypted_message, iv):
        """Decrypt the encrypted message using AES GCM."""
        try:
            key = cls.generate_key()
            encrypted_data = base64.b64decode(encrypted_message)
            nonce = iv[:12]
            ciphertext = encrypted_data[12:-16]
            tag = encrypted_data[-16:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted_data = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted_data.decode()
        except Exception as e:
            print(f"Decryption error: {str(e)}")
            return ""

    def get_standard_headers(self):
        """Get standard headers for requests."""
        return {
            'User-Agent': 'okhttp/4.12.0',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
            'appVersion': str(self.versionNo),
            'app_language': 'en_US',
            'Content-Type': 'application/json; charset=UTF-8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }

    def get_session(self):
        if self.local_mock:
            return False
        """Obtain a new session ID and identifier from the server."""
        url = "https://jiopay.jpb.jio.com/papigateway/getSession/v2"
        payload_dict = {
            "data": f"{random.random()}|7781537675402928",
            "versionNo": self.versionNo,
            "platform": "ANDROID"
        }
        self.logger.info(f"获取请求session payload_dict: {payload_dict}")
        payload = json.dumps(payload_dict)
        headers = self.get_standard_headers()
        response = requests.post(url, headers=headers, data=payload, verify=False, proxies=self.login_data['socks_ip'])

        if response is None:
            self.logger.error(f"payment_id: {self.login_data['id']}, get_session() 方法 响应失败")
            return False

        """记录响应的详细信息"""
        self.response_logger.log_response(response)

        if response.status_code == 200:
            response_data = response.json()
            self.logger.info(f"old session_id: {self.login_data['session_id'] if 'session_id' in self.login_data else 'None'}, new session_id: {response_data['sessionId']}")
            self.login_data['session_id'] = response_data["sessionId"]
            if 'identifier' not in self.login_data:
                self.login_data['identifier'] = response_data["identifier"]
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, get_session() Success to get session, Session ID: {self.login_data['session_id']}, Identifier: {self.login_data['identifier']}")
        else:
            self.logger.info(
                f"payment_id: {self.login_data['id']}, get_session() 方法 失败响应码： {response.status_code}，原因：{response.text}")

    def connection_redis(self):
        if CONNECTION_REDIS_METHOD == 'SSH':
            # 通过SSH隧道连接redis服务
            tunnel, redis_client = connect_redis_via_ssh(
                ssh_host=SSH_HOST,
                ssh_port=SSH_PORT,
                ssh_username=SSH_USERNAME,
                ssh_pkey_path=SSH_PKEY_PATH,
                redis_host=REDIS_HOST,
                redis_port=REDIS_PORT,
                redis_password=REDIS_PASSWORD
            )
        else:
            # 直连redis服务
            redis_client = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        return redis_client

    def check_redis_connection(self):
        try:
            redis_response = self.redis.ping()
            if not redis_response:
                self.logger.info(f"bank: {self.name},id: {self.id}; Redis服务未能ping通,3秒后重新连接")
                # self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
                self.redis = self.connection_redis()
        except Exception as e:
            self.logger.info(f"bank: {self.name},id: {self.id}; Redis 连接失败,3秒后重试: {e}")
            time.sleep(3)
            # self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.redis = self.connection_redis()
            self.check_redis_connection()  # 递归尝试，不恢复连接不进行下一步

    def init_function(self, exist_logger):
        self.session = requests.Session()
        self.session.mount('http://', HTTPAdapter(max_retries=1))
        self.session.mount('https://', HTTPAdapter(max_retries=1))
        self.logger = exist_logger
        self.response_logger = ResponseLogger(exist_logger)
        self.local_mock = False
        # 检测是否联通，如果断联需重新连接
        self.check_redis_connection()

    def get_proxies(self):
        try:
            _indian_socks_ip = self.redis.get(f'indian_socks_ip_{self.name}')
            if not _indian_socks_ip:
                self.logger.error(f'无 indian_socks_ip_{self.name}')
                return False
            _indian_socks_ip = _indian_socks_ip.decode().split(',')
            _indian_socks_ip = [item for item in _indian_socks_ip if item.strip()]
            proxy = random.choice(_indian_socks_ip)
            proxies = {
                'http': proxy if proxy.startswith('socks5://') else 'socks5://{}'.format(proxy),
                'https': proxy if proxy.startswith('socks5://') else 'socks5://{}'.format(proxy)
            }
            return proxies
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'get_proxies 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    def get_lock(self, id):
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, id)
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value) # 返回 0 已存在, 1 不存在且设置成功
            if not _lock:
                # 防止死锁
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"payment_id: {id}, 查询缓存键 {busy_key} 的剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"payment_id: {id}, 死锁并删除缓存键 {busy_key}!!!")
                return False
            else:
                self.logger.info(f"payment_id: {id}, 缓存键 {busy_key} 不存在，并新保存键值 _value: {_value}")
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(f"payment_id: {id}, 更新缓存键 {busy_key} 的剩余生存时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'get_lock 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    def make_request(self, method, url, headers=None, params=None, data=None, json_data=None, proxies=None):
        self.logger.info(
            '请求 {method} {url}, params:{params} data:{data} json_data:{json_data}  代理： {proxies}'.format(
                method=method, url=url, params=params, data=data, json_data=json_data, proxies=proxies))
        try:
            response = None
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params, proxies=proxies, verify=False,
                                            allow_redirects=True, timeout=(10, 10))
            elif method.upper() == 'POST':
                if data != None:
                    response = self.session.post(url, headers=headers, data=data, proxies=proxies, verify=False,
                                                 allow_redirects=True, timeout=(10, 10))
                elif json_data != None:
                    response = self.session.post(url, headers=headers, json=json_data, proxies=proxies, verify=False,
                                                 allow_redirects=True, timeout=(10, 10))
                elif data == None and json_data == None:
                    response = self.session.post(url, headers=headers, proxies=proxies, verify=True, timeout=(10, 10))
            else:
                response = None
            if response is not None:
                self.logger.info(f'请求 {method} {url}, params:{params}, data:{data} json_data:{json_data}, response: {response}, response.text: {response.text}')
            return response
        except requests.exceptions.Timeout as e:
            self.logger.error(f"网络请求错误1： uid: {self.login_data['id']}; 错误详情:{e}")
            return None
        except requests.RequestException as e:
            self.logger.error(f"网络请求错误2： uid: {self.login_data['id']}; 错误详情:{e}")
            return None
        except Exception as e:
            self.logger.error(f"网络请求错误3： uid: {self.login_data['id']}; 错误详情:{e}")
            return None

    def retry_make_request(self, *args, **kwargs):
        res = self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.info(f"make_request() second try, args: {args}, kwargs: {kwargs}")
            res = self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.warning(f"make_request() 获取响应错误, args: {str(args)}, kwargs: {str(kwargs)}")
            return res
        return res

    def call_api(self, url, publish_data):
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            }
            # headers['Host'] = conf['websocket_api_allow_host'][0]
            self.logger.info(f"url: {url}, publish_data: {publish_data}, headers: {headers}")
            res = self.retry_make_request("POST", url=url, headers=headers, params=None, data=publish_data,
                                          json_data=None, proxies=None)
            if res is None:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, 发送{self.list_key} 通知url：{json.dumps(publish_data)} 结果：None")
                return False
            if not 200 <= res.status_code < 300:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, 发送{self.list_key} 通知url：{simplejson.dumps(publish_data)} 结果：{res.text}")
                return False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, notify 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                       simplejson.dumps(self.login_data)))
            return False

    def call_api_server(self, type: str = "", status=False, value=None):
        self.logger.info(f"type: {type}, status: {status}, value: {value}")
        try:
            if type in [
                'get_transaction_history',
                'sync_a_transaction_record',
                PaymentLoginProgress.SEND_SMS_CHECK.name.lower(),
                PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(),
                PaymentLoginProgress.GET_PROFILE.name.lower(),
                PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(),
            ]:
                url = self.domain + '/v1/websocket/payment_protocol_status_notify'


                publish_data = {
                    'type': type,
                    'is_success': status,
                    'payment_id': self.login_data['id'],
                    'error_code': value.get("error_code", "") if isinstance(value, dict) else "",
                    'error_msg': value.get("error_message", "") if isinstance(value, dict) else (
                        value if isinstance(value, str) else ""),
                }

                return self.call_api(url, publish_data)

            elif type == 'send_otp':
                if status:
                    # OTP发送成功的通知
                    url = self.domain + '/v1/websocket/push_upi_opt_success'
                    publish_data = {
                        'id': self.login_data['id']
                    }
                else:
                    # OTP发送失败
                    url = self.domain + '/v1/websocket/push_upi_opt_fail'
                    publish_data = {
                        'id': self.login_data['id'],
                        'error_message': value
                    }
                return self.call_api(url, publish_data)

            elif type == 'push_payment_information':
                # 通知payment状态
                url = self.domain + '/v1/websocket/push_payment_information'
                publish_data = {
                    'id': self.login_data['id']
                }
                if not self.call_api(url, publish_data):
                    return False
                url = self.domain + '/v1/websocket/push_message_to_user'
                publish_data = {
                    'id': self.login_data['partner_id'],
                    'message': value
                }
                return self.call_api(url, publish_data)

            elif type == 'push_message_to_user':
                url = self.domain + '/v1/websocket/push_message_to_user'
                publish_data = {
                    'id': self.login_data['partner_id'],
                    'message': value
                }
                return self.call_api(url, publish_data)

            elif type == 5:
                url = self.domain + '/v1/websocket/payment_bind_upi_success'
                if status == 0:
                    url = self.domain + '/v1/websocket/push_cancel_payment_get_upi'
                publish_data = {
                    'id': self.login_data['id']
                }
                return self.call_api(url, publish_data)

            elif type == 'get_send_sms_info':
                url = self.domain + '/v1/websocket/get_send_sms_info'

                publish_data = {
                    'payment_id': self.login_data['id']
                }

                if status is True:
                    publish_data['to_phone'] = value['receive_sms_number']
                    publish_data['content'] = value['receive_sms_content']
                else:
                    publish_data['error_code'] = value['error_code']
                    publish_data['error_msg'] = value['error_message']

                return self.call_api(url, publish_data)

            return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, sendMsg 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                        simplejson.dumps(self.login_data)))
            return False

    # 调用API接口 /order/Success
    def call_api_order_success(self, request_data):
        result = {"is_success": False}
        try:
            # 开始发送回调信息
            url = self.domain + '/order/Success'

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            }

            res = self.retry_make_request("POST", url=url, headers=headers, params=None, data=request_data,
                                          json_data=None, proxies=None)
            if res is None:
                error_message = f"payment_id: {self.login_data['id']}, 发送{self.list_key}回调信息：None"
                self.logger.error(error_message)
                result['error_message'] = error_message
                return result
            self.logger.info(f"payment_id: {self.login_data['id']}, 发送{self.list_key}回调信息：{res.text}")
            _res = simplejson.loads(res.text)

            # 如果是10025 upi重复，则直接下线
            if 'type' in request_data and request_data['type'] == 'UPI' and _res['code'] == 10025:
                request_data['id'] = request_data['payment_id']
                # 通知监控一键下线
                _key3 = 'login_off_realtime_{}_{}'.format(self.name, request_data['id'])
                self.redis.set(_key3, 1, 60)
                self.call_api_server('push_payment_information', False, 'upi already exist')  # upi重复通知
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, {self.list_key} 更新upi重复，下线:{self.login_data['id']}, 结果：{res.text}")

            if res and (_res['code'] == 100 or _res['code'] == 99):
                result["is_success"] = True
                return result
            else:
                error_message = f"payment_id: {self.login_data['id']}, 请求{url}失败：{{request_data}}"
                result["error_code"] = _res['code']
                result["error_message"] = error_message
                return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = f"payment_id: {self.login_data['id']},call_api_order_success 脚本运行错误: {e}\n{''.join(tb_str)}\n{simplejson.dumps(self.login_data)}"
            self.logger.error(error_message)
            result["error_message"] = error_message
            return result

    def get_device_info(self):
        """Get device information."""
        return {
            "geocodeValue": "",
            "fcmId": "",
            "imsi": self.login_data['identifier'],
            "platform": "ANDROID",
            "mac": self.login_data['identifier'],
            "manufacturer": "OnePlus",
            "xandroidId": self.login_data['android_id'],
            "carrierName": "Jio",
            "appId": "in.jfs.jiofinance",
            "osValue": "13",
            "host": "IN2010",
            "model": "IN2010",
            "locationValue": "",
            "androidId": self.login_data['android_id'],
            "mobileCountryCode": "91",
            "capablityValue": "520000020001000400701392929292920000000000",
            "bluetoothAddress": self.login_data['identifier'],
            "sdkInt": 33,
            "isoCountryCode": "91",
            "version": self.versionNo,
            "cpuAbi": "myphone",
            "name": "myphone",
            "imei": self.login_data['identifier'],
            "typeValue": "MOB",
            "device": self.login_data['identifier']
        }

    def del_lock(self, id, value):
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, id)
            self.logger.info(f"payment_id: {self.login_data['id']} 准备删除Lock {busy_key}")
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(busy_key)
                self.logger.info(f"payment_id: {self.login_data['id']} 删除Lock {busy_key}, result: {result}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, del_lock 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                         simplejson.dumps(self.login_data)))
            return False

    def login_off(self):
        try:
            # 删除hash和set，退出
            self.redis.zrem(self.set_key, self.login_data['id'])
            self.redis.hdel(self.hash_key, self.login_data['id'])
            self.redis.delete(f'upi_active_payment:{self.login_data['id']}')
            self.call_api_server('push_payment_information', False, 'Login failed and exit')  # 退出登录进行通知
            self.set_payment_status0()  # 回调status
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, login_off 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                          simplejson.dumps(self.login_data)))

    def update_key(self):
        try:
            # 更新集合和hash里的值
            self.redis.hset(self.hash_key, self.login_data['id'], simplejson.dumps(self.login_data))
            self.redis.zadd(self.set_key, {self.login_data['id']: int(time.time())})
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, update_key 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                           simplejson.dumps(self.login_data)))
    # 获取payment_id的android_id
    def get_or_create_android_id(self, payment_id, expire_seconds=None):
        """
        获取或创建与payment_id关联的android_id

        Args:
            payment_id: 数字ID
            expire_seconds: 过期时间(秒)，如果不指定则使用默认值

        Returns:
            str: android_id
        """
        # 构造Redis键名
        redis_key = f"payment_android_id:{payment_id}"

        # 尝试从Redis获取现有字符串
        android_id = self.redis.get(redis_key)

        if android_id:
            return android_id.decode('utf-8')

        # 如果不存在或已过期，生成新的唯一字符串
        new_android_id = self.generate_android_id()

        # 设置过期时间
        expiry = expire_seconds if expire_seconds is not None else PAYMENT_ANDROID_ID_DEFAULT_EXPIRE_SECONDS

        # 保存到Redis
        self.redis.setex(
            name=redis_key,
            time=expiry,
            value=new_android_id
        )

        return new_android_id

    # 获取列表中的所有元素
    def read_redis_list(self, key):
        # 使用 lrange 获取列表中的所有元素
        elements = self.redis.lrange(key, 0, -1)  # 0 表示第一个元素，-1 表示最后一个元素

        # 将字节字符串解码为普通字符串
        decoded_elements = [element.decode('utf-8') for element in elements]

        # 转换为集合（自动去重）
        element_set = set(decoded_elements)
        
        # # 打印列表中的元素
        # if elements:
        #     self.logger.info(f"列表 '{key}' 中的元素如下：")
        #     for i, element in enumerate(elements):
        #         # 将字节字符串解码为普通字符串
        #         self.logger.info(f"{i + 1}: {element.decode('utf-8')}")
        # else:
        #     self.logger.info(f"列表 '{key}' 为空或不存在")

        return element_set
    def read_cache(self, source):
        self.logger.info(f"payment_id: {self.login_data['id']}, source: {source} 开始读取业务缓存")
        try:
            cache_key_lock = f'{self.name}_operate_{self.login_data['id']}'
            cache_key_login_on = f'login_on_{self.name}_{self.login_data['id']}'
            cache_key_upi_active_payment = f'upi_active_payment:{self.login_data['id']}'
            cache_key_payment_online_ds = f'payment_online_ds'
            cache_key_payment_online_df = f'payment_online_df'
            cache_key_payment_active_qr_channel = f'payment_active_{self.login_data['qr_channel']}'
            cache_key_kick_off = f'kick_off_{self.login_data['id']}'

            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {self.set_key}, 成员 {self.login_data['id']}, score: {self.redis.zscore(self.set_key, self.login_data['id'])}, ttl: {self.redis.ttl(self.set_key)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {self.hash_key}, 成员 {self.login_data['id']}, hash value: {self.redis.hget(self.hash_key, self.login_data['id'])}, ttl: {self.redis.ttl(self.hash_key)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_lock}, value: {self.redis.get(cache_key_lock)}, ttl: {self.redis.ttl(cache_key_lock)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_login_on}, value: {self.redis.get(cache_key_login_on)}, ttl: {self.redis.ttl(cache_key_login_on)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_upi_active_payment}, value: {self.redis.get(cache_key_upi_active_payment)}, ttl: {self.redis.ttl(cache_key_upi_active_payment)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_payment_online_ds}, 成员: {self.login_data['id']}, 是否在set集合中 {self.redis.sismember(cache_key_payment_online_ds, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_payment_online_ds)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_payment_online_df}, 成员: {self.login_data['id']}, 是否在set集合中 {self.redis.sismember(cache_key_payment_online_df, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_payment_online_df)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_payment_active_qr_channel}, 成员: {self.login_data['id']}, 是否在list列表中 {self.login_data['id'] in self.read_redis_list(cache_key_payment_active_qr_channel)}, ttl: {self.redis.ttl(cache_key_payment_active_qr_channel)}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, read_cache() key: {cache_key_kick_off}, value: {self.redis.get(cache_key_kick_off)}, ttl: {self.redis.ttl(cache_key_kick_off)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, read_cache 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                           simplejson.dumps(self.login_data)))

    def on_off(self, _on=1):
        self.logger.info(f"payment_id: {self.login_data['id']} on_off(_on={_on}) 处理上下线")
        try:
            if _on == 1:
                self.redis.delete('kick_off_{}'.format(self.login_data['id']))
                # 放入接单集合
                self.redis.sadd('payment_online_ds', self.login_data['id'])
                self.redis.sadd('payment_online_df', self.login_data['id'])
                self.redis.lrem('payment_active_{}'.format(self.login_data['qr_channel']), 0, self.login_data['id'])
                self.redis.lpush('payment_active_{}'.format(self.login_data['qr_channel']), self.login_data['id'])
                self.redis.setex('login_on_{}_{}'.format(self.name, self.login_data['id']), 11 * 60, 1)
                self.call_api_server('push_payment_information', True, 'Login success')  # 登录成功通知
                self.call_api_server(PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(), True, 'Login success')  # 登录成功通知
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, {self.list_key} 上线接单： {self.login_data['id']}")
                self.read_cache('on_off(1)')
                return True
            # 防止代收派单的时候，协议爬取同时操作，导致payment id无法下线
            self.redis.setex('kick_off_{}'.format(self.login_data['id']), 60 * 20, 1)
            # 解除接单集合
            self.redis.srem('payment_online_ds', self.login_data['id'])
            self.redis.srem('payment_online_df', self.login_data['id'])
            self.redis.lrem('payment_active_{}'.format(self.login_data['qr_channel']), 0, self.login_data['id'])
            self.redis.delete('login_on_{}_{}'.format(self.name, self.login_data['id']))
            self.call_api_server('push_payment_information', False, 'Login failed and quit')  # 退出登录进行通知
            self.call_api_server(PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(), False, 'Login failed and quit')  # 退出登录进行通知
            self.logger.error(f"payment_id: {self.login_data['id']}, {self.list_key} 下线接单： {self.login_data['id']}")
            self.read_cache('on_off()')
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, on_off 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                       simplejson.dumps(self.login_data)))
            return False

    def set_payment_status0(self):
        try:
            # status状态修改
            orders_send = {
                'type': 'status',
                'bank_name': self.name,
                'payment_id': self.login_data['id'],
                'partner_id': self.login_data['partner_id'],
                'status': 0
            }
            if_send = self.call_api_order_success(orders_send)
            if if_send:
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, status状态修改成功：{simplejson.dumps(orders_send)}")
            else:
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, status状态修改失败：{simplejson.dumps(orders_send)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f'payment_id: {self.login_data['id']}, set_payment_status0 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            return False

    """ 发送短信 """

    def send_otp(self, phone_number):
        self.login_data['time'] = int(time.time())

        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:

            """Send OTP to the specified phone number."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/otp/send"
            data = json.dumps({
                "mobileNumber": phone_number,
                "deviceInfo": self.get_device_info()
            })
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(data, self.login_data['session_id'].encode())
            })
            headers = self.get_standard_headers()
            self.logger.info(
                f"payment_id: {self.login_data['id']}, send_otp(): phone_number: {phone_number}, 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.get_proxies()}")
            response = requests.post(url, headers=headers, data=payload, verify=False, proxies=self.get_proxies())
            self.logger.info(f"payment_id: {self.login_data['id']}, send_otp() 方法 响应: {response}")
            if response is None:
                self.logger.error(f"payment_id: {self.login_data['id']}, send_otp() 方法 响应失败")
                return result
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            response_data = self.get_response_data(response)

            self.logger.info(f"payment_id: {self.login_data['id']}, send_otp() 方法响应：{response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response.status_code != 200:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, send_otp() 方法 失败响应码： {response.status_code}，原因：{response_data}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                return result

            if response_data['responseCode'] != "0":
                return result

            self.logger.info(
                f"payment_id: {self.login_data['id']}, send_otp(): phone_number: {phone_number} OTP发送成功")
            result['is_success'] = True

        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f"payment_id: {self.login_data['id']}, send_otp(): phone_number: {phone_number} 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}")
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

    """ 发送OTP """

    def get_sendOTP(self):
        try:
            # 超时10分钟，舍去
            if self.login_data['time'] < int(time.time()) - self.order_time_out:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, {self.list_key} sendOTP超时，登出:" + simplejson.dumps(
                        self.login_data))
                self.call_api_server('send_otp', False, 'otp sending failed, timeout')  # 获取otp失败进行通知
                return 'logout'

            result_send_otp = self.send_otp(phone_number=self.login_data['phone'])
            # if result_send_otp['is_success'] == False:
            #     time.sleep(1)
            #     result_send_otp = self.send_otp(phone_number = self.login_data['phone'])
            if result_send_otp['is_success'] == False:
                self.login_data['try_sendOTP'] = 1 if 'try_sendOTP' not in self.login_data else self.login_data[
                                                                                                    'try_sendOTP'] + 1
                self.logger.error(
                    f"payment_id: {self.login_data['id']} try_sendOTP失败:{self.login_data['try_sendOTP']}")
                if 'try_sendOTP' in self.login_data and self.login_data['try_sendOTP'] > 5:
                    # 下线接单
                    self.login_off()
                    self.on_off(0)
                    self.logger.error(
                        f"payment_id: {self.login_data['id']}, {self.list_key} try_sendOTP失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.set_payment_status0()  # 回调status
                    self.call_api_server(type='send_otp', status=False, value=result_send_otp)  # 退出登录进行通知
                    return 'logout'
                return False

            # otp已发送通知
            result_call_api_server = self.call_api_server('send_otp', True, None)
            if result_call_api_server:
                # 发送OTP成功
                self.login_data['status'] = 'grabOTP'
            else:
                return 'logout'
            return result_call_api_server
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, get_sendOTP 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                            simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

    # 读取OTP
    def grabOTP(self):
        try:
            _key = 'login_{}_OTP_{}'.format(self.name, self.login_data['id'])
            _otp = self.redis.get(_key)
            if not _otp:
                return False
            return _otp.decode('utf-8')
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, grabOTP 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                        simplejson.dumps(self.login_data)))
            return False

    def verify_otp(self, phone_number, otp):

        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            """Verify the OTP received on the phone number."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/otp/verify"
            data = json.dumps({
                "mobileNumber": phone_number,
                "referredBy": "",
                "otp": str(otp),
                "deviceInfo": self.get_device_info()
            })
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(data, self.login_data['session_id'].encode())
            })
            headers = self.get_standard_headers()
            self.logger.info(
                f"payment_id: {self.login_data['id']}, verify_otp(): phone_number: {phone_number}, 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.get_proxies()}")
            response = requests.post(url, headers=headers, data=payload, verify=False, proxies=self.get_proxies())
            self.logger.info(f"payment_id: {self.login_data['id']}, verify_otp() 方法 响应: {response}")
            if response is None:
                self.logger.error(f"payment_id: {self.login_data['id']}, verify_otp() 方法 响应失败")
                result['error_message'] = "方法响应为空"
                return result

            """记录响应的详细信息"""
            self.response_logger.log_response(response)
            self.readResponseType(response)

            if response.status_code == 400:
                response_data = self.get_response_data(response)
                # 失败响应码： 400，原因：{'responseCode': 'B102', 'responseMessage': 'Invalid OTP entered! Please try again'}
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, verify_otp() 方法 失败响应码： {response.status_code}，原因：{response_data}")
                result['error_code'] = response_data['responseCode']
                result['error_message'] = response_data['responseMessage']
                return result
            elif response.status_code == 401:
                response_data = self.get_response_data(response)
                # 失败响应码： 401，原因：{"payload":{"responseCode":"-1","responseMsg":"Invalid SessionId..."},"context":{"sessionId":"24bcaad7-008f-423d-b53e-545dc6350fa9","encryption":null}}
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, verify_otp() 方法 失败响应码<401>，原因：{response.text}")
                result['error_code'] = 401
                result['error_message'] = response_data['responseMessage']
                return result
            elif response.status_code == 403:
                response_data = self.get_response_data(response)
                # 如果响应是JSON格式
                try:
                    self.logger.error(f"payment_id: {self.login_data['id']}, verify_otp() 方法 失败响应码<403> {response.status_code}，header: {dict(response.headers)}, 原因：{response.json()}")
                except Exception as e:
                    self.logger.error(f"payment_id: {self.login_data['id']}, verify_otp() 方法 失败响应码<403> {response.status_code}，原因：{response}, e: {e}")
                result['error_code'] = 403
                result['error_message'] = response_data['responseMessage']
                return result
            if response.status_code != 200:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, verify_otp() 方法 失败响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                return result

            response_data = self.get_response_data(response)

            self.logger.info(f"payment_id: {self.login_data['id']}, response_data: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            self.login_data['jtoken'] = response_data["jtoken"]
            self.logger.info(f"payment_id: {self.login_data['id']}, OTP Verified. JToken: {self.login_data['jtoken']}")
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, verify_otp 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                           simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

    def readResponseType(self, response):
        try:
            self.logger.info(f"payment_id: {self.login_data['id']}, type(response): {type(response)}")
        except Exception as e:
            self.logger.error(f"payment_id: {self.login_data['id']}, type(response) 读取错误")
        try:
            self.logger.info(f"payment_id: {self.login_data['id']}, type(response.headers): {type(response.headers)}")
        except Exception as e:
            self.logger.error(f"payment_id: {self.login_data['id']}, type(response.headers) 读取错误")
        try:
            self.logger.info(f"payment_id: {self.login_data['id']}, type(response.json()): {type(response.json())}")
        except Exception as e:
            self.logger.error(f"payment_id: {self.login_data['id']}, type(response.json()) 读取错误")
        try:
            self.logger.info(f"payment_id: {self.login_data['id']}, type(response.text): {type(response.text)}")
        except Exception as e:
            self.logger.error(f"payment_id: {self.login_data['id']}, type(response.text) 读取错误")

    def get_response_data(self, response):
        try:
            decrypted_message = self.decrypt_message(
                encrypted_message=response.json()["payload"],
                iv=self.login_data['session_id'].encode()
            )
            response_data = json.loads(decrypted_message)
        except Exception as e:
            self.logger.error(f"解析response遇到问题，e: {e}")
            response_data['responseMessage'] = "decrypt response message error"
        return response_data

    """ 验证OTP """

    def check_otp(self):

        result = {"is_success": False}
        try:
            # 读取OTP
            grabOTP = self.grabOTP()
            if not grabOTP:
                if self.login_data['time'] < int(time.time()) - self.order_time_out:
                    self.logger.error(
                        f"payment_id: {self.login_data['id']}, {self.list_key} 获取otp超时，登出:" + simplejson.dumps(
                            self.login_data))
                    self.set_payment_status0()  # 回调status
                    self.call_api_server('push_message_to_user', False, 'check otp get timeout')  # 退出登录进行通知
                    self.redis.delete(f'upi_active_payment:{self.login_data['id']}')
                    return 'logout'
                error_message = f"payment_id: {self.login_data['id']}, get_grabOTP() payment_id: {self.login_data['id']} 没有收到otp"
                result['error_code'] = 408
                result['error_message'] = error_message
                self.logger.warning(error_message)
                return result

            # 接收OTP成功
            self.logger.info(f"payment_id: {self.login_data['id']} otp:{grabOTP}")
            self.login_data['otp'] = grabOTP

            result_verify_otp = self.verify_otp(self.login_data['phone'], self.login_data['otp'])
            if result_verify_otp['is_success'] == False and result_verify_otp['error_code'] in [401, 403]:
                self.get_session()  # 更新 session_id
                time.sleep(3)
                result_verify_otp = self.verify_otp(self.login_data['phone'], self.login_data['otp'])
            if result_verify_otp['is_success'] == False:
                error_code = result_verify_otp['error_code']
                error_message = result_verify_otp['error_message']
                if error_code == 'B102':
                    self.call_api_server(PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(), False, result_verify_otp)
                elif error_code == 'B100':
                    self.call_api_server(PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(), False, result_verify_otp)
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, {self.list_key} 验证 OTP 错误, error_code: {error_code}, error_message: {error_message}")
                # 下线接单
                self.login_off()
                self.on_off(0)
                self.set_payment_status0()  # 回调status
                result = result_verify_otp
            else:
                self.call_api_server(PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(), True, result_verify_otp)
                result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, get_grabOTP 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                            simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

    # 设备检查
    def device_check(self):

        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:

            """Check if the device is bound to the account."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/jiopay/devicebinding/check"
            data = json.dumps({
                "integrityVerdict": {},
                "deviceInfo": self.get_device_info(),
                "hashValue": "",
                "token": self.login_data['jtoken']
            })
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(data, self.login_data['session_id'].encode())
            })
            headers = self.get_standard_headers()
            response = requests.post(url, headers=headers, data=payload, verify=False, proxies=self.get_proxies())

            if response is None:
                self.logger.error(f"payment_id: {self.login_data['id']}, device_check() 方法 响应失败")
                return False

            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            decrypted_message = self.decrypt_message(
                encrypted_message=response.json()["payload"],
                iv=self.login_data['session_id'].encode()
            )
            self.logger.info(f"payment_id: {self.login_data['id']}, device_check() 方法响应：{decrypted_message}")
            response_data = json.loads(decrypted_message)

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response.status_code != 200:
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, device_check() 方法 失败响应码： {response.status_code}，原因：{response_data}, response.test: {response.text}")
                return result
            setUpMode = response_data["setUpMode"]
            result['setUpMode'] = setUpMode
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, get_send_number_content() 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e,
                                                                                          error_message,
                                                                                          simplejson.dumps(
                                                                                              self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message

        return result

    # 获取发送短信的目标号码、指定内容
    def get_send_number_content(self):

        if self.local_mock:
            return {"is_success": True, "receive_sms_number": "9999999999", "receive_sms_content": "Mock Data"}

        result = {"is_success": False}
        try:
            """Get outbound SMS code."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/jiopay/outboundsms/get"
            data = json.dumps({
                "deviceInfo": self.get_device_info()
            })
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(plaintext=data, iv=self.login_data['session_id'].encode())
            })
            headers = self.get_standard_headers()
            response = requests.post(url, data=payload, headers=headers, verify=False, proxies=self.get_proxies())

            if response is None:
                self.logger.error(f"payment_id: {self.login_data['id']}, get_send_number_content() 方法 响应失败")
                return False

            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            decrypted_message = self.decrypt_message(
                encrypted_message=response.json()["payload"],
                iv=self.login_data['session_id'].encode()
            )
            self.logger.info(
                f"payment_id: {self.login_data['id']}, get_send_number_content() 方法响应：{decrypted_message}")
            response_data = json.loads(decrypted_message)

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response.status_code != 200:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, get_send_number_content() 方法 失败响应码： {response.status_code}，原因：{response_data}")
                return result

            if response_data['responseCode'] != "0":
                return result

            result['receive_sms_number'] = response_data["longCode"]
            result['receive_sms_content'] = response_data["code"]

            self.login_data['receive_sms_number'] = result['receive_sms_number']
            self.login_data['receive_sms_content'] = result['receive_sms_content']

            self.logger.info(f"payment_id: {self.login_data['id']}, receive_sms_number: {result['receive_sms_number']}")
            self.logger.info(
                f"payment_id: {self.login_data['id']}, receive_sms_content: {result['receive_sms_content']}")

            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, get_send_number_content() 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e,
                                                                                          error_message,
                                                                                          simplejson.dumps(
                                                                                              self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

    # 获取发送短信的目标号码、指定内容，并通知api服务
    def get_send_number_content_send_api(self):
        if self.login_data['time'] < int(time.time()) - self.order_time_out:
            self.logger.error(
                f"payment_id: {self.login_data['id']}, {self.list_key} 获取otp超时，登出:" + simplejson.dumps(
                    self.login_data))
            self.set_payment_status0()  # 回调status
            self.call_api_server('push_message_to_user', False, 'get send number and content timeout')  # 退出登录进行通知
            self.redis.delete(f'upi_active_payment:{self.login_data['id']}')
            return 'logout'
        result = self.get_send_number_content()
        # 通知api服务获取到的内容，发送短信的目标号码、指定内容
        if result['is_success'] is True:
            # 等待3秒，再通知前端收到的目标号码、指定内容
            time.sleep(1)
            result_call_api_server = self.call_api_server(type='get_send_sms_info', status=True, value=result)
            if not result_call_api_server:
                return "logout"
            # 进入下一步等待客户端通知已发送短信
            self.login_data['status'] = 'wait_client_send_sms'
            return True
        else:
            self.call_api_server(type='get_send_sms_info', status=False, value=result)
            return False

    # 读取客户端发送短信的状态
    def get_status_client_send_sms(self):
        try:
            _hash_key = f"send_{self.name}_sms_success"
            # 获取列表的所有元素
            list_elements = self.redis.lrange(_hash_key, 0, -1)
            # 将列表元素转换为集合以便快速查找
            list_elements_set = set(list_elements)
            check_elements = str(self.login_data['id']).encode('utf-8')
            # 检查元素是否存在
            if check_elements in list_elements_set:
                self.logger.info(f"payment_id: {self.login_data['id']}, get_status_client_send_sms() -> True")
                self.redis.lrem(_hash_key, 0, check_elements)
                return True
            else:
                return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, get_status_client_send_sms() 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e,
                                                                                             error_message,
                                                                                             simplejson.dumps(
                                                                                                 self.login_data)))
            return False

    def outboundsms_check(self):

        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            """Check the outbound SMS code."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/jiopay/outboundsms/check"
            data = json.dumps({
                "code": self.login_data['receive_sms_content'],
                "referredBy": "",
                "longCode": self.login_data['receive_sms_number'],
                "deviceInfo": self.get_device_info()
            })
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(plaintext=data, iv=self.login_data['session_id'].encode())
            })
            self.logger.info(f"payment_id: {self.login_data['id']}, outboundsms_check(), payload: {payload}")
            headers = self.get_standard_headers()
            response = requests.post(url, data=payload, headers=headers, verify=False, proxies=self.get_proxies())
            self.logger.info(f"payment_id: {self.login_data['id']}, outbonudsms_check() 方法 响应: {response}")
            if response is None:
                self.logger.error(f"payment_id: {self.login_data['id']}, outbonudsms_check() 方法 响应失败")
                result['error_message'] = "outboundsms check fail"
                return result

            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            response_data = self.get_response_data(response)
            if response.status_code != 200:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, outbonudsms_check() 方法 失败响应码： {response.status_code}，原因：{response_data}, response.text: {response.text}")
                result['error_code'] = response_data['responseCode']
                result['error_message'] = "outboundsms response error"
                return result

            self.logger.info(f"payment_id: {self.login_data['id']}, outboundsms_check() response_data: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                return result
            self.login_data['jtoken'] = response_data["jtoken"]
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, get_status_client_send_sms() 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e,
                                                                                             error_message,
                                                                                             simplejson.dumps(
                                                                                                 self.login_data)))
            result['error_message'] = error_message
        return result

    """Get user profile information."""

    def get_upi(self):

        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            url = "https://jiopay.jpb.jio.com/papigateway/v2/upi/prf/composit/profileV2"
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                }
            })
            self.logger.info(f"payment_id: {self.login_data['id']}, get_upi(), payload: {payload}")
            headers = self.get_standard_headers()
            response = requests.post(url, data=payload, headers=headers, verify=False, proxies=self.get_proxies())

            if response is None:
                self.logger.error(f"payment_id: {self.login_data['id']}, get_upi() 方法 响应失败")
                return result

            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response.status_code != 200:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, get_upi() 方法 失败响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                return result
            decrypt_message = self.decrypt_message(encrypted_message=response.json()["payload"],
                                                   iv=self.login_data['session_id'].encode())
            response_data = simplejson.loads(decrypt_message)

            self.logger.info(f"payment_id: {self.login_data['id']}, get_upi() response_data: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                return result

            linked_accounts_keys = list(response_data.get("linkedAccountsMap", {}).keys())
            upi_list = [] if 'new_upi_list' not in self.login_data else self.login_data['new_upi_list']
            for upi in linked_accounts_keys:
                self.logger.info(f"payment_id: {self.login_data['id']}, get_upi() upi: {upi}")
                if upi not in upi_list :
                    upi_list.append(upi)
            upi = linked_accounts_keys[0]
            self.login_data['new_upi'] = upi
            self.login_data['new_upi_list'] = upi_list

            # upi有更新时
            if 'upi' not in self.login_data or (self.login_data['upi'] and upi != self.login_data['new_upi']):
                self.login_data['upi'] = upi

            # 回调api, 通知payment有绑定新的upi
            request_data = {
                'type': 'UPI',
                'bank_name': self.name,
                'payment_id': self.login_data['id'],
                'partner_id': self.login_data['partner_id'],
                'upi': upi
            }
            result_call_api_order_success = self.call_api_order_success(request_data)
            self.logger.info(
                f"payment_id: {self.login_data['id']}, get_upi() call_api_order_success = {result_call_api_order_success}")
            if not result_call_api_order_success or result_call_api_order_success['is_success'] is not True:
                result['error_message'] = result_call_api_order_success
                return result

            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f'payment_id: {self.login_data['id']}, get_upi() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            result['error_message'] = error_message
        return result

    """ 抓取账单 """

    def transaction_history(self, upi):


        if self.local_mock:
            return {"is_success": True}

        if upi is None:
            upi = self.login_data['upi']
        self.logger.info(f"payment_id: {self.login_data['id']}, transaction_history(upi = {upi})")
        result = {"is_success": False}
        try:
            """Retrieve transaction history for the specified VPA."""
            url = "https://jiopay.jpb.jio.com/papigateway/v2/upi/prf/transaction/composite/history"
            data = json.dumps({"virtualPaymentAddress": upi, "rowNum": 20})
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(data, self.login_data['session_id'].encode())
            })
            headers = self.get_standard_headers()
            response = requests.post(url, data=payload, headers=headers, verify=False, proxies=self.get_proxies())

            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, transaction_history(upi=\"{upi}\") 方法 响应失败")
                return False

            elif response.status_code == 401:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, transaction_history(upi=\"{upi}\") 方法 响应失败，response: {response.json()["payload"]["responseMsg"]}，稍后再试")
                return False
            elif 500 <= response.status_code < 550:
                single_line_response = ''.join(response.text.splitlines())
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, transaction_history(upi=\"{upi}\") 方法 响应失败，response.status_code: {response.status_code}, response.text: {single_line_response}")
                time.sleep(5)
                return False

            elif response.status_code != 200:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, transaction_history(upi=\"{upi}\") 方法 响应失败，response.status_code: {response.status_code}, response.text: {response.text}")
                return False
            # 解密数据
            decrypted_message = self.decrypt_message(
                encrypted_message=response.json()["payload"],
                iv=self.login_data['session_id'].encode()
            )
            self.logger.info(
                f"payment_id: {self.login_data['id']}, transaction_history(upi=\"{upi}\") 解密数据：{decrypted_message}")
            response_data = json.loads(decrypted_message)

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] == "5001":
                result['is_success'] = True
                return result
            elif response_data['responseCode'] == "-1":
                # {"transactionHistoryList":null,"responseCode":"-1","responseMessage":"We are unable to process your request at this moment. Please try again later| S041"}
                result['is_success'] = True
                return result
            elif response_data['responseCode'] != "0":
                self.logger.warning(
                    f"payment_id: {self.login_data['id']}, transaction_history(upi=\"{upi}\") 发现未处理的响应码：{response_data['responseCode']}, 响应信息: {response_data['responseMessage']}"
                )
                return result
            transactionHistoryList = response_data["transactionHistoryList"]
            if transactionHistoryList is None:
                result['transaction_history_list'] = []
            else:
                # 按照交易时间正序排序
                transaction_history_list = sorted(
                    transactionHistoryList,
                    key=lambda x: datetime.strptime(x['transactionDate'], '%Y-%m-%dT%H:%M:%S')
                )
                result['transaction_history_list'] = transaction_history_list
                for transaction_history in transaction_history_list:
                    self.logger.info(f"payment_id: {self.login_data['id']}, 交易记录：{transaction_history}")
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f'payment_id: {self.login_data['id']}, transaction_history() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            result['error_message'] = error_message
        return result

    def is_transaction_synced(self, utr: str) -> bool:
        """检查交易是否已同步"""
        return self.redis.sismember(f"{self.cache_key_transaction_history_synced_utr}:{self.login_data['id']}", utr)

    def mark_transaction_synced(self, utr: str):
        """标记交易为已同步"""
        self.redis.sadd(f"{self.cache_key_transaction_history_synced_utr}:{self.login_data['id']}", utr)

    # 检查协议登录状态
    def check_signin_status(self, wait_times=0, wait_times_by_get_profile=0):
        if self.login_data['time'] < int(time.time()) - self.order_time_out:
            self.logger.error(
                f"payment_id: {self.login_data['id']}, {self.list_key} check_signin_status，登出:" + simplejson.dumps(
                    self.login_data))
            self.set_payment_status0()  # 回调status
            self.call_api_server('push_message_to_user', False, 'check signin status timeout')  # 退出登录进行通知
            self.redis.delete(f'upi_active_payment:{self.login_data['id']}')
            return 'logout'
        # 读取客户端发送短信的状态
        result_get_status_client_send_sms = self.get_status_client_send_sms()
        self.logger.info(f"payment_id: {self.login_data['id']}, 第{wait_times}次获取发送短信的目标号码及内容的状态")
        if not result_get_status_client_send_sms:
            if wait_times == 60:
                return 'logout'
            time.sleep(1)
            return self.check_signin_status(wait_times=wait_times + 1)

        # 向银行检查短信发送状态
        result_outboundsms_check = self.outboundsms_check()
        # 短信发送状态检查失败
        if result_outboundsms_check is None or result_outboundsms_check['is_success'] is None or \
                result_outboundsms_check['is_success'] != True:
            self.call_api_server(type=PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), status=False, value=result_outboundsms_check)
            return "logout"
        result_call_api_server = self.call_api_server(type=PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), status=True, value=result_outboundsms_check)
        if not result_call_api_server:
            return "logout"
        # 获取个人信息 UPI
        self.logger.info(f"payment_id: {self.login_data['id']}, 第{wait_times_by_get_profile}次尝试获取个人信息")
        result_get_upi = self.get_upi()
        if result_get_upi is None or result_get_upi['is_success'] != True:
            if wait_times_by_get_profile == 10:
                self.login_off()
                self.on_off(0)
                # 抓取个人信息状态检查成功
                self.call_api_server(type=PaymentLoginProgress.GET_PROFILE.name.lower(), status=False, value=result_get_upi)
                return 'logout'
            time.sleep(1)
            return self.check_signin_status(wait_times_by_get_profile=wait_times_by_get_profile + 1)
        result_call_api_server = self.call_api_server(type=PaymentLoginProgress.GET_PROFILE.name.lower(), status=True, value=result_get_upi)
        if not result_call_api_server:
            return "logout"
        self.logger.info(
            f"payment_id: {self.login_data['id']}, 第{wait_times_by_get_profile}次获取个人信息成功, result_get_upi: {result_get_upi}")
        # 抓取1次账单
        self.logger.info(f"payment_id: {self.login_data['id']}, 尝试抓取账单")
        result_transaction_history = self.transaction_history(upi=self.login_data.get("upi", ""))
        self.logger.info(f"payment_id: {self.login_data['id']}, 尝试抓取账单, 结果：{result_transaction_history}")
        if isinstance(result_transaction_history, str) and result_transaction_history == 'logout':
            self.logger.info(f"payment_id: {self.login_data['id']}, check_signin_status() return 'logout'")
            return 'logout'
        elif isinstance(result_transaction_history, bool) and result_transaction_history == False:
            self.logger.info(f"payment_id: {self.login_data['id']}, check_signin_status() return False")
            self.call_api_server(type='get_transaction_history', status=False, value=result_transaction_history)
            return False
        elif isinstance(result_transaction_history, dict) and result_transaction_history['is_success'] != True:
            self.logger.info(f"payment_id: {self.login_data['id']}, check_signin_status()['is_success'] return False")
            self.call_api_server(type='get_transaction_history', status=False, value=result_transaction_history)
            return False
        # 更改缓存上线
        self.on_off(1)
        result_call_api_server = self.call_api_server(type='get_transaction_history', status=True, value=result_transaction_history)
        if not result_call_api_server:
            return "logout"
        # 改状态为可以抓取账单
        self.login_data['status'] = 'grabstatement'
        self.logger.info(f"payment_id: {self.login_data['id']}, check_signin_status() return True")
        return True

    def get_profile(self):
        # 获取个人信息 UPI
        result_get_upi = self.get_upi()
        if result_get_upi is None or result_get_upi['is_success'] != True:
            return False
        # 抓取1次账单
        result_transaction_history = self.transaction_history(upi=self.login_data.get("upi", ""))
        if isinstance(result_transaction_history, str) and result_transaction_history == 'logout':
            return 'logout'
        elif isinstance(result_transaction_history, bool) and result_transaction_history == False:
            return False
        elif isinstance(result_transaction_history, dict) and result_transaction_history['is_success'] != True :
            self.call_api_server(type='get_transaction_history', status=False, value=result_transaction_history)
            return False

        self.on_off(1)
        result_call_api_server = self.call_api_server(type='get_transaction_history', status=True, value=result_transaction_history)
        if not result_call_api_server:
            return "logout"
        # 改状态为可以抓取账单
        self.login_data['status'] = 'grabstatement'
        return True

    """ 转化为时间戳 """

    def parse_to_timestamp(self, time_str):
        try:
            date = datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S')
            timestamp = date.timestamp()
        except ValueError:
            timestamp = None
        return timestamp

    def check_order_time(self, timestamp):
        try:
            return int(time.time()) - int(timestamp) > self.order_grab_time_out
        except Exception as e:
            return False
    # 取出IFSC
    def extract_code_split(self, text: str) -> str:
        # 先用@分割，取第二部分，再用.分割，取第一部分
        return text.split('@')[1].split('.')[0]

    # 取出账号
    def extract_payment_account(self, text: str) -> str:
        return text.split('@')[0]

    def sync_transaction(self, transaction: Dict) -> bool:
        self.logger.info(f"payment_id: {self.login_data['id']}, sync_transaction(), transaction: {transaction}")
        account = ""
        """同步单条交易记录到远程数据库"""
        try:
            # transaction['transactionType'] is None or transaction['transactionType'] == 'null' or
            if self.login_data['upi'] in transaction['payeeVirtualPaymentAddress']:
                # upi 收款
                transaction['txnType'] = 'credit'
                account = self.extract_payment_account(transaction['payerVirtualPaymentAddress'])
            # transaction['transactionType'] == "PAY" or
            elif self.login_data['upi'] in transaction['payerVirtualPaymentAddress']:
                # upi 付款
                transaction['txnType'] = 'debit'
                account = self.extract_payment_account(transaction['payeeVirtualPaymentAddress'])
            else:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, sync_transaction() 同步失败, 不支持的交易类型: {transaction}")
                return False
            payerVirtualPaymentAddress = ""
            payeeVirtualPaymentAddress = ""
            ifsc = ""

            if 'payerVirtualPaymentAddress' in transaction:
                payerVirtualPaymentAddress = transaction['payerVirtualPaymentAddress']
            if 'payeeVirtualPaymentAddress' in transaction:
                payeeVirtualPaymentAddress = transaction['payeeVirtualPaymentAddress']
                if 'ifsc' in payeeVirtualPaymentAddress:
                    ifsc = self.extract_code_split(payeeVirtualPaymentAddress)
                    if len(ifsc) != 11:
                        ifsc = ""
            orders_send = {
                'type': 'New',
                'bank_name': self.name,
                'payment_id': self.login_data['id'],
                'partner_id': self.login_data['partner_id'],
                'amount': transaction['amount'],
                'utr': transaction['approvalRefNum'],
                'trade_type': transaction['txnType'],
                'status': transaction['transactionStatus'],
                'remarks': transaction['remarks'],
                'payerVirtualPaymentAddress': payerVirtualPaymentAddress,
                'payeeVirtualPaymentAddress': payeeVirtualPaymentAddress,
                'ifsc': ifsc,
                'account': account
            }
            result_call_api_order_success = self.call_api_order_success(orders_send)
            if result_call_api_order_success["is_success"] == True:
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, sync_transaction() 同步成功, transaction: {transaction}")
                return True
            else:
                self.logger.error(
                    f"payment_id: {self.login_data['id']}, sync_transaction() 同步失败, transaction: {transaction}")
                return False
        except Exception as e:
            self.logger.info(f"同步交易记录失败 {transaction['approvalRefNum']}: {str(e)}")
            return False

    def sync_transaction_history(self):
        self.login_data['time'] = int(time.time())
        self.login_data['count'] = 1 if 'count' not in self.login_data else self.login_data['count'] + 1
        """执行同步任务"""
        self.logger.info(f"payment_id: {self.login_data['id']}, 开始同步任务 - {datetime.now()}")

        # 通知监控一键下线
        cache_key_login_off_realtime_jio = f'login_off_realtime_jio_{self.login_data['id']}'
        cache_value_login_off_realtime_jio = self.redis.get(cache_key_login_off_realtime_jio)
        if cache_value_login_off_realtime_jio:
            self.logger.info(f"payment_id: {self.login_data['id']} 处理通知一键下线 {cache_key_login_off_realtime_jio}： {cache_value_login_off_realtime_jio}")
            return 'logout'

        cache_key_login_on = 'login_on_{}_{}'.format(self.name, self.login_data['id'])
        self.redis.setex(cache_key_login_on, 11 * 60, 1)
        self.logger.info(f"payment_id: {self.login_data['id']} 重置缓存 {cache_key_login_on}")

        if 'sync_transaction_history_failures_count' not in self.login_data:
            self.login_data['sync_transaction_history_failures_count'] = 0
        # 获取最新交易记录
        transaction_history = self.transaction_history(None)
        if isinstance(transaction_history, str) and transaction_history == 'logout' :
            self.logger.warning(f"payment_id: {self.login_data['id']} 获取交易记录失败，强制下线, login_data: {self.login_data}")
            return 'logout'

        if (isinstance(transaction_history, bool) and transaction_history == False) or (isinstance(transaction_history, dict) and transaction_history['is_success'] == False):
            # 交易记录同步失败次数+1
            self.login_data['sync_transaction_history_failures_count'] = int(self.login_data['sync_transaction_history_failures_count']) + 1
            if int(self.login_data['sync_transaction_history_failures_count']) == SYNC_TRANSACTION_HISTORY_MAX_FAILURES_NUM:
                self.logger.warning(f"payment_id: {self.login_data['id']} 同步交易记录失败次数过多，强制下线, login_data: {self.login_data}")
                return 'logout'
            time.sleep(int(self.login_data['sync_transaction_history_failures_count']) + 5)
            return False

        # 读取交易记录成功
        self.login_data['sync_transaction_history_failures_count'] = 0
        # 抓取交易记录为空
        if 'transaction_history_list' not in transaction_history or transaction_history['transaction_history_list'] is None:
            return True
        # 遍历同步交易记录
        for transaction in transaction_history['transaction_history_list']:
            approval_ref_num = transaction['approvalRefNum']
            if 'transactionStatus' not in transaction or transaction['transactionStatus'] != 'SUCCESS':
                continue
            # 检查是否已同步
            if self.is_transaction_synced(approval_ref_num):
                self.logger.info(f"payment_id: {self.login_data['id']}, 交易 {approval_ref_num} 已同步，跳过")
                continue

            # 同步交易记录
            if self.sync_transaction(transaction):
                self.mark_transaction_synced(approval_ref_num)
                self.logger.info(f"payment_id: {self.login_data['id']}, 交易 {approval_ref_num} 同步成功")
            else:
                self.logger.info(
                    f"payment_id: {self.login_data['id']}, 交易 {approval_ref_num} 同步失败，将在下次任务中重试")
        return True

    def read_zset(self, key):
        # 获取有序集合中的所有元素及其分数
        # withscores=True 表示返回元素及其分数
        elements_with_scores = self.redis.zrange(key, 0, -1, withscores=True)
        # 将元素和分数存储到字典中
        result_dict = {element.decode(): score for element, score in elements_with_scores}
        self.logger.info(f"read_zset() zset key: {key}, value: {result_dict}")

    def main(self):
        try:
            # 生成新的trace_id
            trace_id_filter.trace_id = f"{os.getpid()} {uuid.uuid4()}"
            
            # 1 先检查list中与hash的比较，是否hash中已有，如果有，则抛弃，如果没有则放置hash和有序集合
            pop_data = self.redis.lpop(self.list_key)
            if not pop_data:
                self.logger.info(f"redis key: {self.list_key} 中没有要处理的 payment")
                pass
            else:
                self.logger.info(f"redis key: {self.list_key} 发现要处理的payment： {pop_data}")
                pop_data_set = simplejson.loads(pop_data.decode())
                if self.redis.hexists(self.hash_key, pop_data_set['id']):
                    # 如果有，则抛弃
                    self.logger.warning(f"redis key: {self.hash_key} 中已包含 payment_id: {pop_data_set['id']} ！")
                else:
                    # 如果没有则放置在hash和有序集合
                    self.logger.info(f"redis key: {self.hash_key} 不包含 payment_id {pop_data_set['id']}, 准备处理新登录！")
                    self.redis.hset(self.hash_key, pop_data_set['id'], simplejson.dumps(pop_data_set))
                    # 如果是需要登录的，则可以在此设置分数为0来标明是登录状态,标明优先处理
                    self.redis.zadd(self.set_key, {pop_data_set['id']: 0})

            self.read_zset(self.set_key)
            # 从有序集合中，获取10S外的成员，限100个
            reduced_time = 10
            zrangebyscore_max = int(time.time()) - reduced_time
            members = self.redis.zrangebyscore(self.set_key, 0, zrangebyscore_max, 0, 100)
            if members is None or not members:
                self.logger.info(f"redis key: {self.set_key} ZScoreBoundT min:0, max:{zrangebyscore_max} 中没有要处理的 payment_id")
                time.sleep(5)
                return
            for i in members:
                _id = i.decode()
                # 读取缓存，确定是否本地模拟
                payment_mock = self.redis.exists(f"payment_mock:{_id}")
                if payment_mock:
                    # 标记本次为本地模拟
                    self.local_mock = True
                self.id = _id
                login_data = self.redis.hget(self.hash_key, _id)
                if not login_data:
                    # 不存在hash数据，则删除有序集合的元素
                    self.logger.error(f"payment_id: {_id}, hash_key: {self.hash_key} 不存在数据，从set列表缓存 key: {self.set_key} 中删除！")
                    self.redis.zrem(self.set_key, _id)
                    continue
                else:
                    self.logger.info(f"payment_id: {_id}, merbers[{i}], hash_key: {self.hash_key}, login_data: {login_data}")
                    # 存在hash数据，则开始登录或者爬取账单等
                    self.logger.info(f"payment_id: {_id}, {self.list_key} 尝试获取锁")
                    _lock = self.get_lock(_id)
                    if _lock:
                        self.logger.info(f"payment_id: {_id}, {self.list_key} 获取到锁 _lock: {_lock}")
                        # 操作前获取锁
                        self.login_data = simplejson.loads(login_data.decode())
                        self.read_cache('main() init login_data')
                        # 获取payment_id的android_id
                        self.login_data['android_id'] = self.get_or_create_android_id(_id)
                        # 获取代理ip
                        proxy = self.get_proxies()
                        if not proxy:
                            self.logger.error(f"redis key: {self.list_key} payment_id: {_id} 无代理！")
                            continue
                        self.login_data['socks_ip'] = proxy if 'socks_ip' not in self.login_data or not self.login_data[
                            'socks_ip'] else self.login_data['socks_ip']
                        self.logger.info(
                            f"payment_id: {_id}, hash_key: {self.hash_key}, login_data: {self.login_data}")
                        res = None

                        if self.login_data['status'] == 'sendOTP':
                            # 发送otp
                            self.get_session()
                            res = self.get_sendOTP()
                            self.logger.info(f"payment_id: {self.login_data['id']}, sendOTP, res {type(res)}： {res}")
                            self.read_cache(f'main() sendOTP res: {res}')
                        elif self.login_data['status'] == 'grabOTP':
                            # 输入otp并登录
                            res = self.check_otp()
                            self.logger.info(f"payment_id: {self.login_data['id']}, grabOTP res {type(res)}： {res}")
                            if isinstance(res, dict) and res['is_success'] == False:
                                if res['error_code'] == 408:
                                    self.read_cache(f'main() grabOTP false error code 408, res: {res}')
                                    res = False
                                # elif res['error_code'] == 'B102':
                                #     res = False
                                else:
                                    self.read_cache(f'main() grabOTP logout failed, res: {res}')
                                    res = 'logout'
                            elif isinstance(res, dict) and res['is_success'] == True:
                                self.get_session()  # 更新 session_id
                                result_device_check = self.device_check()
                                self.logger.info(
                                    f"payment_id: {self.login_data['id']}, grabOTP 更新session_id, device_check()： {result_device_check}")
                                if isinstance(result_device_check, dict) and result_device_check['is_success'] == False:
                                    self.read_cache(f'main() grabOTP false is true, res: {res}')
                                    res = True
                                elif isinstance(result_device_check, bool) :
                                    res = True
                                else:
                                    if self.local_mock:
                                        result_device_check['setUpMode'] = 'OTP'

                                    if result_device_check['setUpMode'] == 'OTP':
                                        # 获取要发送的短信的目标号码及内容
                                        res = self.get_send_number_content_send_api()
                                        self.read_cache(f'main() grabOTP true OTP, res: {res}')
                                    else:
                                        res = self.get_profile()
                                        self.read_cache(f'main() grabOTP true, res: {res}')

                        elif self.login_data['status'] == 'wait_client_send_sms':
                            # 检查协议登录状态
                            res = self.check_signin_status()
                            self.read_cache(f'main() wait_client_send_sms, res: {res}')
                        elif self.login_data['status'] == 'grabstatement':
                            crawl_frequently = self.redis.get('crawl_frequently_{}'.format(self.login_data['id']))
                            if crawl_frequently or ('try_count' in self.login_data and self.login_data['try_count'] > 0):
                                # 有相关的key或者有重试的，都按指定的最短时间爬取一次
                                _time_grab = self.time_grab
                            else:
                                _time_grab = self.time_grab2
                            if 'count' not in self.login_data or login_data['time'] < int(time.time()) - _time_grab:
                                self.get_session()  # 更新 session_id
                                result_device_check = self.device_check()
                                self.logger.info(f"payment_id: {self.login_data['id']}, grabstatement 更新session_id, device_check(): {result_device_check}")
                                if isinstance(result_device_check, dict) and result_device_check['is_success'] == True:
                                    # device_check() 失败次数归0
                                    self.login_data['count_device_check_failed_num'] = 0

                                    if self.local_mock:
                                        result_device_check['setUpMode'] = 'OBS'

                                    if result_device_check['setUpMode'] == 'OBS':
                                        # 登录成功且更新session_id成功后获取upi和交易账单
                                        res = self.get_profile()
                                        if isinstance(res, bool):
                                            res = self.sync_transaction_history()
                                            self.read_cache(f'main() sync_transaction_history, res: {res}')
                                            if isinstance(res, bool) :
                                                self.login_data['try_count'] = 1 if 'try_count' not in self.login_data else self.login_data['try_count'] + 1
                                            if 'count' in self.login_data and self.login_data['try_count'] > 15:
                                                res = 'logout'
                                    # setUpMode 为OTP，需要二次发送短信，处理为 直接退出
                                    elif result_device_check['setUpMode'] == 'OTP':
                                        self.logger.warning(
                                            f"payment_id: {self.login_data['id']}, grabstatement 更新session_id, device_check() response.setUpMode: {result_device_check['setUpMode']}, 强制 logout")
                                        # 直接退出
                                        res = 'logout'
                                        # 获取要发送的短信的目标号码及内容 选择再次获取 要发送短信的目标号码、内容
                                        # self.login_data['time'] = int(time.time())
                                        # res = self.get_send_number_content_send_api()
                                    else:
                                        res = False
                            else:
                                if 'count_device_check_failed_num' in self.login_data:
                                    # device_check() 失败次数累加
                                    self.login_data['count_device_check_failed_num'] = int(self.login_data['count_device_check_failed_num']) + 1
                                    # device_check() 失败次数满10次下线
                                    if int(self.login_data['count_device_check_failed_num']) == 10:
                                        self.logger.warning(
                                            f"payment_id: {self.login_data['id']}, grabstatement device_check() 失败次数累计 {self.login_data['count_device_check_failed_num']} 次, 强制 logout")
                                        res = 'logout'
                                    else:
                                        time.sleep(int(self.login_data['count_device_check_failed_num']) + 30)
                                        res = False
                                else:
                                    self.login_data['count_device_check_failed_num'] = 1
                                    time.sleep(int(self.login_data['count_device_check_failed_num']) + 30)
                                    res = False
                        else:
                            # status有问题
                            self.logger.error(
                                f"payment_id: {self.login_data['id']}, {self.list_key} {_id} status存在问题，舍去！")
                            self.login_off()
                            self.on_off(0)
                            self.read_cache(f'main() status error')
                        if isinstance(res, str) and res == 'logout':
                            # 删除相关的hash和set中的值
                            self.logger.error(
                                f"payment_id: {self.login_data['id']}, {self.list_key} {_id} 登出，删除相关的hash和set中的值")
                            self.login_off()
                            self.on_off(0)
                            self.read_cache(f'main() logout')
                        else:
                            # 更新集合和hash里的值
                            self.update_key()
                            self.read_cache(f'main() True')

                        # 删除锁
                        self.del_lock(_id, _lock)
                    else:
                        self.logger.warning(f"payment_id: {_id}, {self.list_key} 未获取到锁！")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('过程错误： 错误详情：{}\n{}'.format(e, error_message))


if __name__ == '__main__':
    logger.info(f"{'='*10}协议启动{'='*10}")
    bank = BankLogin()
    while True:
        try:
            bank.init_function(logger)
            bank.main()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logger.error('脚本运行错误,3秒后重试: id: {} {}\n{}'.format(bank.id, e, error_message))
            # 插入redis，防止非主逻辑内的出错
            bank.redis = bank.connection_redis()
        finally:
            time.sleep(3)