import json
import logging
import os
import random
import re
import secrets
import sys
import time
import traceback
import uuid
# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

import redis
import requests
import simplejson
from requests import Response
from requests.adapters import HTTPAdapter
from sshtunnel import SSHTunnelForwarder

import datetime_utils
from beneficiary import Beneficiary
from device import AndroidDeviceInfo

from maha_request import MahaRequest, MahaResult
from maha_result_status import MahaResultStatusCode, PayProcessStatus
from user_info import UserInfo

current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
parent2_dir = os.path.dirname(parent_dir)
sys.path.append(parent2_dir)

import config
from application.cache.redis_order_manager import RedisOrderManager
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
LOG_FILE = f"maha_{os.getpid()}.log"
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

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# 同步交易记录最大失败次数，达到后，下线
SYNC_TRANSACTION_HISTORY_MAX_FAILURES_NUM = 30
# payment_id绑定的android_id的过期时间
PAYMENT_ANDROID_ID_DEFAULT_EXPIRE_SECONDS = 60 * 60 * 24 * 100

# 配置信息
FUNDS_TRANSFER_SERVICE_PAYMENT_MODE = "NEFT"  # 协议支付方式：P2A (即 IMPS ), NEFT
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

    def __init__(self):
        self.name = 'maha'
        self.list_key = 'login_maha'
        self.hash_key = 'login_maha_hash'
        self.set_key = 'login_maha_set'
        self.cache_key_transaction_history_synced_utr = 'login_maha_transaction_history_utr_synced'
        self.lock_time = 60  # 操作锁的锁定时间
        self.order_time_out = 5 * 60
        self.upi_try_limit = 10  # 最大尝试爬取upi，(爬取upi失败还可以爬取账单)
        self.order_grab_time_out = 4 * 60 * 60  # 检测爬取的账单时间是否在规定范围内，不是则舍弃
        self.domain = API_SERVER_DOMAIN
        self.session = None
        self.logger = None
        self.login_data = None
        self.try_count = 8  # 重试次数
        self.list_count = 4  # 当list个数小于某个值之后暂缓pop，避免导致爬取过快
        self.list_count_time = 4
        self.payment_id = None  # payment id
        self.task_lock = None
        self.task_begin_time = None
        self.local_mock = False

        if self.local_mock:
            logger.info(f"{'=' * 10}协议启动 本地测试模式{'=' * 10}")
        else:
            logger.info(f"{'=' * 10}协议启动{'=' * 10}")

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
                self.logger.info(f"bank: {self.name},id: {self.payment_id}; Redis服务未能ping通,3秒后重新连接")
                # self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
                self.redis = self.connection_redis()
        except Exception as e:
            self.logger.info(f"bank: {self.name},id: {self.payment_id}; Redis 连接失败,3秒后重试: {e}")
            time.sleep(3)
            # self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.redis = self.connection_redis()
            self.check_redis_connection()  # 递归尝试，不恢复连接不进行下一步

    def init_function(self, exist_logger):
        self.session = requests.Session()
        self.session.mount('http://', HTTPAdapter(max_retries=1))
        self.session.mount('https://', HTTPAdapter(max_retries=1))
        self.logger = exist_logger
        # 检测是否联通，如果断联需重新连接
        self.check_redis_connection()
        self.login_data = None
        self.payment_id = None  # payment id
        self.task_lock = None
        self.task_begin_time = None
        self.local_mock = False
        
        

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

    # 获取payment_id的设备信息
    def get_or_create_a_new_device(self, payment_id, expire_seconds=None) -> AndroidDeviceInfo:

        # 构造Redis键名
        redis_key = f"payment_device_android:{payment_id}"

        device_hash = self.redis.hgetall(redis_key)

        if device_hash:
            # Convert bytes to strings and create AndroidDeviceInfo object
            device_hash = {k.decode('utf-8'): v.decode('utf-8') if isinstance(v, bytes) else v for k, v in
                           device_hash.items()}
            return AndroidDeviceInfo.from_dict(device_hash)
        else:
            device_info = AndroidDeviceInfo()
            self.redis.hset(name=redis_key, mapping=device_info.to_dict())

            # 设置过期时间
            expiry = expire_seconds if expire_seconds is not None else PAYMENT_ANDROID_ID_DEFAULT_EXPIRE_SECONDS

            # 设置过期时间
            self.redis.expire(name=redis_key, time=expiry)
            return device_info

    # 获取payment_id的设备信息
    def delete_a_device(self, payment_id):
        # 构造Redis键名
        redis_key = f"payment_device_android:{payment_id}"
        self.redis.delete(redis_key)


    def get_lock(self, id):
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, id)
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value)  # 返回 0 已存在, 1 不存在且设置成功
            if not _lock:
                # 防止死锁
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"payment.id: {id}, 查询缓存键 {busy_key} 的剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"payment.id: {id}, 死锁并删除缓存键 {busy_key}!!!")
                return False
            else:
                self.logger.info(f"payment.id: {id}, 缓存键 {busy_key} 不存在，并新保存键值 _value: {_value}")
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(
                f"payment.id: {id}, 更新缓存键 {busy_key} 的剩余生存时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'get_lock 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    """
    延长锁的过期时间
    """
    def extend_lock_expire_time(self):
        now_time = datetime.now()
        # 计算2个时间差
        calculate_time_diff = datetime_utils.calculate_time_diff(self.task_begin_time, now_time)
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, self.payment_id)
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == self.task_lock:
                self.redis.expire(busy_key, self.lock_time)
                self.logger.info(f"循环任务 执行延长锁时间 Lock {busy_key}: {self.task_lock}, 任务执行时长: {calculate_time_diff}s, now_time: {now_time}, _lock:{type(_lock)} {_lock}")
                return True
            else:
                self.logger.warning(f"循环任务 执行延长锁时间 Lock {busy_key}: {self.task_lock} 失败, 任务执行时长: {calculate_time_diff}s, now_time: {now_time}, _lock:{type(_lock)} {_lock}")
                return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f"循环任务 执行延长锁时间 _lock: {self.task_lock}, 任务执行时长: {calculate_time_diff}s, now_time: {now_time}"
                f"del_lock 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}"
            )
            return False

    def del_lock(self, id, _lock_value):
        now_time = datetime.now()
        # 计算2个时间差
        calculate_time_diff = datetime_utils.calculate_time_diff(self.task_begin_time, now_time)
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, id)
            _lock = self.redis.get(busy_key)
            delete_result = None
            if _lock and _lock.decode() == _lock_value:
                delete_result = self.redis.delete(busy_key)

            self.logger.info(f"循环任务 执行结束 _lock: {_lock_value}, 删除Lock: {delete_result}, 任务执行时长: {calculate_time_diff}s, now_time: {now_time}, _lock:{type(_lock)} {_lock}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f"循环任务 执行结束 _lock: {_lock_value}, 任务执行时长: {calculate_time_diff}s, now_time: {now_time}"
                f"del_lock 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}"
            )
            return False

    def make_request(self, method, url, headers=None, params=None, data=None, json_data=None, proxies=None) -> Response:
        self.logger.info(
            '请求 {method} {url}, params:{params} data:{data} json_data:{json_data}  代理： {proxies}'.format(
                method=method, url=url, params=params, data=data, json_data=json_data, proxies=proxies))
        begin_time = datetime.now()
        try:
            response = None
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params, proxies=proxies, verify=False,
                                            allow_redirects=True, timeout=(30, 30))
            elif method.upper() == 'POST':
                if data != None:
                    response = self.session.post(url, headers=headers, data=data, proxies=proxies, verify=False,
                                                 allow_redirects=True, timeout=(30, 30))
                elif json_data != None:
                    response = self.session.post(url, headers=headers, json=json_data, proxies=proxies, verify=False,
                                                 allow_redirects=True, timeout=(30, 30))
                elif data == None and json_data == None:
                    response = self.session.post(url, headers=headers, proxies=proxies, verify=True, timeout=(30, 30))
            else:
                response = None
            if response is not None:
                nowtime = datetime.now()
                # 计算两个时间点的秒差
                delta_seconds = (nowtime - begin_time).total_seconds()
                self.logger.info(
                    f'请求 {method} {url}, 响应 {delta_seconds}s, params:{params}, data:{data} json_data:{json_data}, response: {response}, response.text: {response.text}')
            return response
        except requests.exceptions.Timeout as e:
            self.logger.error(f"网络请求错误1： url: {url}; 错误详情:{e}")
            return None
        except requests.RequestException as e:
            self.logger.error(f"网络请求错误2： url: {url}; 错误详情:{e}")
            return None
        except Exception as e:
            self.logger.error(f"网络请求错误3： url: {url}; 错误详情:{e}")
            return None

    def retry_make_request(self, *args, **kwargs) -> Response:
        res = self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.info(f"make_request() second try, args: {args}, kwargs: {kwargs}")
            res = self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.warning(f"make_request() 获取响应错误, args: {str(args)}, kwargs: {str(kwargs)}")
            return res
        return res

    def call_api(self, url="", publish_data=None, method="POST") -> bool:
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            }
            # headers['Host'] = conf['websocket_api_allow_host'][0]  # 上测试时删除
            self.logger.info(f"url: {url}, publish_data: {publish_data}, headers: {headers}")
            res = self.retry_make_request(method=method, url=url, headers=headers, params=None, data=publish_data,
                                          json_data=None, proxies=None)
            if res is None:
                self.logger.error(
                    f"发送{self.list_key} 通知url：{json.dumps(publish_data)} 结果：None")
                return False
            if not 200 <= res.status_code < 300:
                self.logger.error(
                    f"发送{self.list_key} 通知url：{simplejson.dumps(publish_data)} 结果：{res.text}")
                return False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, notify 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                       simplejson.dumps(self.login_data)))
            return False

    def request_api_server(self, method="POST", url="", publish_data=None):
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            }
            # headers['Host'] = conf['websocket_api_allow_host'][0]  # 上测试时删除
            self.logger.info(f"url: {url}, publish_data: {publish_data}, headers: {headers}")
            res = self.retry_make_request(method=method, url=url, headers=headers, params=None, data=publish_data,
                                          json_data=None, proxies=None)
            if res is None:
                self.logger.error(
                    f"发送{self.list_key} 通知url：{json.dumps(publish_data)} 结果：None")
                return None
            if not 200 <= res.status_code < 300:
                self.logger.error(
                    f"发送{self.list_key} 通知url：{simplejson.dumps(publish_data)} 结果：{res.text}")
                return None
            return res.json()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, notify 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                       simplejson.dumps(self.login_data)))
            return None

    def call_api_server(self, type="", status=False, value=None) -> bool:
        self.logger.info(f"type: {type}, status: {status}, value: {value}")
        try:
            if type in [
                'get_transaction_history',
                'verification_client_send_sms',
                'sync_a_transaction_record',
                'orders_df_status_to_pending',
                'tpin_error',
                PaymentLoginProgress.SEND_SMS_CHECK.name.lower(),
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

            elif type == 'get_send_sms_info':
                url = self.domain + '/v1/websocket/get_send_sms_info'

                publish_data = {
                    'payment_id': self.login_data['id']
                }

                if status is True:
                    publish_data['to_phone'] = value['targetPhoneNumber']
                    publish_data['content'] = value['targetSmsContent']
                else:
                    publish_data['error_code'] = value.get("error_code", "")
                    publish_data['error_msg'] = value.get("error_message", ""),

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

            return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'调用远程Api错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
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
                error_message = f"发送{self.list_key}回调信息：None"
                self.logger.error(error_message)
                result['error_message'] = error_message
                return result
            self.logger.info(f"发送{self.list_key}回调信息：{res.text}")
            _res = simplejson.loads(res.text)

            # 如果是10025 upi重复，则直接下线
            if 'type' in request_data and request_data['type'] == 'UPI' and _res['code'] == 10025:
                request_data['id'] = request_data['payment_id']
                # 通知监控一键下线
                _key3 = 'login_off_realtime_{}_{}'.format(self.name, request_data['id'])
                self.redis.set(_key3, 1, 60)
                self.call_api_server('push_payment_information', False, 'upi already exist')  # upi重复通知
                self.logger.info(
                    f"{self.list_key} 更新upi重复，下线:{self.login_data['id']}, 结果：{res.text}")

            if res and (_res['code'] == 100):
                result["is_success"] = True
                return result
            else:
                error_message = f"请求{url}失败：{{request_data}}"
                result["error_code"] = _res['code']
                result["error_message"] = error_message
                self.logger.warning(f"result: {json.dumps(result)}")
                return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = f"call_api_order_success 脚本运行错误: {e}\n{''.join(tb_str)}\n{simplejson.dumps(self.login_data)}"
            self.logger.error(error_message)
            result["error_message"] = error_message
            return result

    def get_device_info_from_redis(self) -> AndroidDeviceInfo:
        device_info = AndroidDeviceInfo.from_json(self.login_data['device_info'])
        return device_info

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
        self.logger.info(f"source: {source} 开始读取业务缓存")
        try:
            cache_key_lock = f'{self.name}_operate_{self.login_data['id']}'
            cache_key_login_on = f'login_on_{self.name}_{self.login_data['id']}'
            cache_key_upi_active_payment = f'upi_active_payment:{self.login_data['id']}'
            # cache_key_payment_online_ds = f'payment_online_ds'
            cache_key_payment_online_df = f'payment_online_df'
            cache_key_payment_active_qr_channel = f'payment_active_{self.login_data['qr_channel']}'
            cache_key_kick_off = f'kick_off_{self.login_data['id']}'

            self.logger.info(
                f"read_cache() key: {self.set_key}, 成员 {self.login_data['id']}, score: {self.redis.zscore(self.set_key, self.login_data['id'])}, ttl: {self.redis.ttl(self.set_key)}")
            self.logger.info(
                f"read_cache() key: {self.hash_key}, 成员 {self.login_data['id']}, hash value: {self.redis.hget(self.hash_key, self.login_data['id'])}, ttl: {self.redis.ttl(self.hash_key)}")
            self.logger.info(
                f"read_cache() key: {cache_key_lock}, value: {self.redis.get(cache_key_lock)}, ttl: {self.redis.ttl(cache_key_lock)}")
            self.logger.info(
                f"read_cache() key: {cache_key_login_on}, value: {self.redis.get(cache_key_login_on)}, ttl: {self.redis.ttl(cache_key_login_on)}")
            self.logger.info(
                f"read_cache() key: {cache_key_upi_active_payment}, value: {self.redis.get(cache_key_upi_active_payment)}, ttl: {self.redis.ttl(cache_key_upi_active_payment)}")
            # self.logger.info(
            #     f"read_cache() key: {cache_key_payment_online_ds}, 成员: {self.login_data['id']}, 是否在set集合中 {self.redis.sismember(cache_key_payment_online_ds, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_payment_online_ds)}")
            self.logger.info(
                f"read_cache() key: {cache_key_payment_online_df}, 成员: {self.login_data['id']}, 是否在set集合中 {self.redis.sismember(cache_key_payment_online_df, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_payment_online_df)}")
            self.logger.info(
                f"read_cache() key: {cache_key_payment_active_qr_channel}, 成员: {self.login_data['id']}, 是否在list列表中 {self.login_data['id'] in self.read_redis_list(cache_key_payment_active_qr_channel)}, ttl: {self.redis.ttl(cache_key_payment_active_qr_channel)}")
            self.logger.info(
                f"read_cache() key: {cache_key_kick_off}, value: {self.redis.get(cache_key_kick_off)}, ttl: {self.redis.ttl(cache_key_kick_off)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, read_cache 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                           simplejson.dumps(self.login_data)))

    def read_zset(self, key):
        # 获取有序集合中的所有元素及其分数
        # withscores=True 表示返回元素及其分数
        elements_with_scores = self.redis.zrange(key, 0, -1, withscores=True)
        # 将元素和分数存储到字典中
        result_dict = {element.decode(): score for element, score in elements_with_scores}
        self.logger.info(f"读取 zset key: {key}, value: {result_dict}")

    """
    redis hash数据 读取
    """

    def redis_hash_scan(self, pattern, count=100) -> dict:

        # 初始化游标
        cursor = 0
        result_dicts = {}

        # 使用SCAN命令遍历所有匹配的Key
        while True:
            # 执行SCAN命令
            cursor, keys = self.redis.scan(cursor=cursor, match=f"{pattern}*", count=count)

            # 遍历匹配的Key
            for key in keys:
                # 检查Key的类型是否为Hash
                if self.redis.type(key) == b'hash':
                    # 获取Hash的所有字段和值
                    hash_data = self.redis.hgetall(key)
                    # 将bytes类型的字段和值转换为字符串
                    hash_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in hash_data.items()}
                    # 将结果保存到字典中
                    result_dicts[key.decode('utf-8')] = hash_data

            # 如果游标为0，表示遍历结束
            if cursor == 0:
                break

        # 打印所有匹配的Hash数据
        for key, hash_data in result_dicts.items():
            self.logger.info(f"key[{type(key)}]: {key}, data[{type(hash_data)}]: {hash_data}")
            self.logger.info("-" * 40)
        return result_dicts

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
            # 更新hash里的值
            self.redis.hset(self.hash_key, self.login_data['id'], simplejson.dumps(self.login_data))

            # 更新有序集合
            if "status" in self.login_data and "send_sms_check" == self.login_data.get("status"):
                # 需要验证短信发送，标记分数为0，下次循环时，优先最高
                self.redis.zadd(self.set_key, {self.login_data.get("id"): 0})
            elif "status" in self.login_data and "prepare_login" == self.login_data.get("status"):
                # 需要登录，标记分数为1
                self.redis.zadd(self.set_key, {self.login_data.get("id"): 1})
            else:
                # 需要处理账单或订单
                self.redis.zadd(self.set_key, {self.login_data.get("id"): int(time.time())})
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                'payment_id: {}, update_key 脚本运行错误{}\n{}\n{}'.format(self.login_data['id'], e, error_message,
                                                                           simplejson.dumps(self.login_data)))

    def on_off(self, _on=1):
        try:
            if _on == 1:
                self.logger.info(f"处理上下线 上线")
                self.redis.delete('kick_off_{}'.format(self.login_data['id']))
                # 放入接单集合
                # self.redis.sadd('payment_online_ds', self.login_data['id'])
                self.redis.sadd('payment_online_df', self.login_data['id'])
                self.redis.lrem('payment_active_{}'.format(self.login_data['qr_channel']), 0, self.login_data['id'])
                self.redis.lpush('payment_active_{}'.format(self.login_data['qr_channel']), self.login_data['id'])
                self.redis.setex('login_on_{}_{}'.format(self.name, self.login_data['id']), 11 * 60, 1)
                self.redis.delete(f'upi_active_payment:{self.login_data['id']}')
                self.call_api_server('push_payment_information', True, 'Login success')  # 登录成功通知
                self.call_api_server(PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(), True, 'Login success')  # 登录成功通知
                self.logger.info(
                    f"{self.list_key} 上线接单： {self.login_data['id']}")
                self.read_cache('on_off(1)')
                return True
            # 计算上线总时长
            online_time_total = datetime_utils.time_and_time_str_diff(self.login_data.get("online_time", ""))
            self.logger.info(f"处理上下线 下线, 上线总时长：{online_time_total}")
            # 防止代收派单的时候，协议爬取同时操作，导致payment id无法下线
            self.redis.setex('kick_off_{}'.format(self.login_data['id']), 60 * 20, 1)
            # 解除接单集合
            # self.redis.srem('payment_online_ds', self.login_data['id'])
            self.redis.srem('payment_online_df', self.login_data['id'])
            self.redis.lrem('payment_active_{}'.format(self.login_data['qr_channel']), 0, self.login_data['id'])
            self.redis.delete('login_on_{}_{}'.format(self.name, self.login_data['id']))
            self.call_api_server('push_payment_information', False, 'Login failed and quit')  # 退出登录进行通知
            self.call_api_server(PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(), False, 'Login failed and quit')  # 退出登录进行通知
            self.logger.error(f"{self.list_key} 下线接单： {self.login_data['id']}")
            self.read_cache('on_off() 清除缓存 & 通知api type = push_payment_information')
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
                    f"status状态修改成功：{simplejson.dumps(orders_send)}")
            else:
                self.logger.info(
                    f"status状态修改失败：{simplejson.dumps(orders_send)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(
                f'payment_id: {self.login_data['id']}, set_payment_status0 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
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
                self.logger.info(f"处理登录 send_sms_check 从缓存读取到客户端已发送短信的通知")
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

    def is_transaction_synced(self, utr: str) -> bool:
        """检查交易是否已同步"""
        return self.redis.sismember(f"{self.cache_key_transaction_history_synced_utr}:{self.login_data['id']}", utr)

    def mark_transaction_synced(self, utr: str):
        """标记交易为已同步"""
        self.redis.sadd(f"{self.cache_key_transaction_history_synced_utr}:{self.login_data['id']}", utr)

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

    # 匹配imps付款的12位数字的utr
    def get_urt_by_imps(self, text: str) -> str:
        # 使用正则表达式匹配长度为12的数字字符串
        match = re.search(r'\b\d{12}\b', text)
        if match:
            return match.group(0)  # 返回匹配到的数字字符串
        else:
            return None  # 如果没有匹配到，返回 None

    def get_hash_name_orders_df_success_to_paid(self, payment_id):
        hash_name = f"orders_df_success_to_paid_maha:{payment_id}"
        return hash_name

    def get_hash_key_orders_df_success_to_paid_time(self, hash_code):
        hash_code_time_key = f"{hash_code}_time"
        return hash_code_time_key

    # 同步1条交易记录
    def sync_a_transaction_record(self, user_info: UserInfo, record: dict) -> bool:
        self.logger.info(f"读取到1个详细账单记录: {record}")

        tranParticulars = str(record.get("tranParticulars"))

        # 交易类型
        trade_type = str(record.get("drCRIndicator"))  # CR: 收入, DR: 支出

        # 仅处理支出
        if "DR" != trade_type.upper():
            return False

        # 交易支出固定值
        trade_type = "debit"

        # 交易金额
        tranAmount = record.get("tranAmount")

        if "NEFT" == FUNDS_TRANSFER_SERVICE_PAYMENT_MODE:
            # 排除非IMPS的付款
            if "NEFT" not in tranParticulars or " " not in tranParticulars:
                self.logger.info(f"非NEFT的付款: {tranParticulars}")
                return False
            # 交易号utr
            utr = tranParticulars.split("NEFT")[1].split(" ")[1]
            self.logger.info(f"匹配到NEFT付款方式的utr: {utr}")
            # 交易人名称
            transfer_name = tranParticulars.split(utr)[1].strip()
        elif "P2A" == FUNDS_TRANSFER_SERVICE_PAYMENT_MODE:
            # 排除非IMPS的付款
            if "IMPS" not in tranParticulars or "/" not in tranParticulars:
                self.logger.info(f"非IMPS的付款: {tranParticulars}")
                return False
            # 交易号utr
            utr = self.get_urt_by_imps(tranParticulars)
            if utr is None or len(str(utr)) != 12:
                return False

            # 交易人名称
            transfer_name = tranParticulars.split("/")[-2]
        else:
            self.logger.info(f"不需要处理的订单： {tranParticulars}")
            return False
        utr = str(utr)
        # 检查是否已同步
        if self.is_transaction_synced(utr):
            self.logger.info(f"交易UTR {utr} 已同步，跳过")
            return True

        hash_name = self.get_hash_name_orders_df_success_to_paid(self.login_data['id'])

        if "NEFT" == FUNDS_TRANSFER_SERVICE_PAYMENT_MODE:

            # 通过hash_code从缓存中读取对应的订单号
            orders_df_code = self.redis.hget(name=hash_name, key=utr)
            if isinstance(orders_df_code, bytes):
                orders_df_code = orders_df_code.decode()

            if not orders_df_code:
                self.logger.warning(f"未找到抓取到账单对应的订单号，utr: {utr}, 订单数据: {record}")
                orders_df_code = utr

            orders_send = {
                'type': 'New',
                'bank_name': self.name,
                'payment_id': self.login_data['id'],
                'partner_id': self.login_data['partner_id'],
                'amount': tranAmount,
                'utr': utr,
                'trade_type': trade_type,
                'status': "",
                'remarks': tranParticulars,
                'code': orders_df_code,
                'account': transfer_name,
                'upi': user_info.customerId
            }
            """同步单条交易记录到远程数据库"""
            try:
                result_call_api_order_success = self.call_api_order_success(orders_send)
                paid_time = self.redis.hget(hash_name, self.get_hash_key_orders_df_success_to_paid_time(utr)) \
                    if self.redis.hexists(hash_name, self.get_hash_key_orders_df_success_to_paid_time(utr)) \
                    else None
                if result_call_api_order_success["is_success"] == True:
                    self.logger.info(f"sync_transaction() 同步成功, transaction: {record}")
                    self.mark_transaction_synced(utr)
                    self.call_api_server(type="sync_a_transaction_record", status=True)
                    redis_hdel_result = self.redis.hdel(hash_name, utr, orders_df_code, self.get_hash_key_orders_df_success_to_paid_time(utr))
                    self.logger.info(f"同步账单回调完成[NEFT方式], utr: {utr}, orders_df_code: {orders_df_code}, paid_time: {paid_time}, redis_hdel_result: {redis_hdel_result}")
                    return True
                else:
                    self.logger.error(f"同步账单回调失败[NEFT方式], utr: {utr}, orders_df_code: {orders_df_code}, paid_time: {paid_time}, transaction: {record}")
                    self.call_api_server(
                        type="sync_a_transaction_record",
                        status=False,
                        value=result_call_api_order_success
                    )
                    return False
            except Exception as e:
                self.logger.info(f"同步账单回调异常[NEFT方式] utr: {utr}, orders_df.hash_code: {orders_df_code}: {str(e)}")
                return False
        elif "P2A" == FUNDS_TRANSFER_SERVICE_PAYMENT_MODE:
            # 付款时备注的代付订单号对应的hash短码 orders_df.hash_code
            code = tranParticulars.split("/")[-1]

            # 通过hash_code从缓存中读取对应的订单号
            orders_df_code = self.redis.hget(name=hash_name, key=code)
            if isinstance(orders_df_code, bytes):
                orders_df_code = orders_df_code.decode()

            if not orders_df_code:
                self.logger.warning(f"未找到抓取到账单对应的订单号，hash_code: {code}, 订单数据: {record}")
                orders_df_code = code if not code else utr

            orders_send = {
                'type': 'New',
                'bank_name': self.name,
                'payment_id': self.login_data['id'],
                'partner_id': self.login_data['partner_id'],
                'amount': tranAmount,
                'utr': utr,
                'trade_type': trade_type,
                'status': "",
                'remarks': tranParticulars,
                'code': orders_df_code,
                'account': transfer_name,
                'upi': user_info.customerId
            }
            """同步单条交易记录到远程数据库"""
            try:
                result_call_api_order_success = self.call_api_order_success(orders_send)
                paid_time = self.redis.hget(hash_name, self.get_hash_key_orders_df_success_to_paid_time(code)) \
                    if self.redis.hexists(hash_name, self.get_hash_key_orders_df_success_to_paid_time(code)) \
                    else None
                if result_call_api_order_success["is_success"] == True:
                    self.mark_transaction_synced(utr)
                    self.call_api_server(type="sync_a_transaction_record", status=True)
                    redis_hdel_result = self.redis.hdel(hash_name, code, self.get_hash_key_orders_df_success_to_paid_time(code))
                    self.logger.info(f"同步账单回调完成[IMPS方式], utr: {utr}, orders_df_code: {orders_df_code}, paid_time: {paid_time}, redis_hdel_result: {redis_hdel_result}")
                    return True
                else:
                    self.logger.error(f"同步账单回调失败[IMPS方式], utr: {utr}, orders_df_code: {orders_df_code}, paid_time: {paid_time}, transaction: {record}")
                    self.call_api_server(
                        type="sync_a_transaction_record",
                        status=False,
                        value=result_call_api_order_success
                    )
                    return False
            except Exception as e:
                self.logger.info(f"同步账单回调异常[IMPS方式] utr: {utr}, orders_df.hash_code: {code}: {str(e)}")
                return False

        return False

    # 获得要发送短信的目标号码及内容
    def get_vmn(self, account_number, phone, mpin, tpin) -> MahaResult:
        # 创建用户信息实例
        user_info = UserInfo()
        user_info.accountNumber = account_number
        user_info.password = ""
        user_info.phone = phone
        user_info.os = "Android"
        user_info.osVersion = "13"
        user_info.deviceId = self.get_device_info_from_redis().android_id
        user_info.latitude = self.get_device_info_from_redis().latitude
        user_info.longitude = self.get_device_info_from_redis().longitude
        user_info.location = self.get_device_info_from_redis().location
        user_info.ipv6Address = self.get_device_info_from_redis().ipv6Address
        user_info.mpin = mpin
        user_info.tpin = tpin
        user_info.key = "c592eb91208ac6d7"

        proxies = self.login_data['socks_ip']
        if not proxies:
            error_message = f"没有配置代理"
            self.logger.error(error_message)
            return MahaResult(status_code=MahaResultStatusCode.NO_PROXY, error_message=error_message)
        # 创建主类实例
        maha = MahaRequest(user_info=user_info, proxies=proxies, logger=self.logger, local_mock=self.local_mock)

        # 执行操作流程
        result_get_vmn = maha.get_vmn()
        self.login_data["get_vmn_time"] = datetime.now().strftime(DATETIME_FORMAT)
        return result_get_vmn

    # 同步用户信息
    def sync_user_info(self, user_info: UserInfo, maha: MahaRequest = None):
        if user_info is not None:
            self.logger.info(f"maha用户信息同步前 user_info: {json.dumps(self.login_data['user_info'])}")
            self.logger.info(f"maha用户信息同步前: sessionId: {self.login_data.get('user_info').get('sessionId', '') if 'user_info' in self.login_data else None}")
            # 保存user_info
            self.login_data['user_info'] = user_info.to_dict()
            self.logger.info(f"maha用户信息同步后 user_info: {json.dumps(self.login_data['user_info'])}")
            self.logger.info(f"maha用户信息同步后: sessionId: {self.login_data.get('user_info').get('sessionId', '') if 'user_info' in self.login_data else None}")
            if maha is not None:
                maha.user_info = user_info

    # 处理预登录
    def handle_prepare_login(self) -> MahaResult:
        if 'account' not in self.login_data or self.login_data['account'] is None:
            self.logger.error(f"缺失参数：account")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT)
        """ 数据库中存储的为pin，当mpin使用 """
        if 'pin' not in self.login_data or self.login_data['pin'] is None:
            self.logger.error(f"缺失参数：pin")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT)
        if 'tpin' not in self.login_data or self.login_data['tpin'] is None:
            self.logger.error(f"缺失参数：tpin")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT)
        if 'phone' not in self.login_data or self.login_data['phone'] is None:
            self.logger.error(f"缺失参数：phone")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT)
        # 取得账号
        account_number = self.login_data['account']
        # 取得手机号
        phone = self.login_data['phone']
        # 取得mpin
        mpin = self.login_data['pin']
        # 取得tpin
        tpin = self.login_data['tpin']

        # 获得要发送短信的目标号码及内容
        result = self.get_vmn(account_number=account_number, phone=phone, mpin=mpin, tpin=tpin)
        if not result.is_success:
            call_apio_server_data = {
                "error_code": result.status_code,
                "error_message": result.error_message
            }
            self.call_api_server('get_send_sms_info', False, call_apio_server_data)
            return result
        # 把获取到的要发送短信的目标号码及内容，通知给 api服务
        self.call_api_server('get_send_sms_info', True, result.data)
        return result

    # 处理验证客户端发送短信的状态
    def handle_verification_client_send_sms(self, user_info: UserInfo) -> MahaResult:
        # 读取客户端发送短信的状态
        result_get_status_client_send_sms = self.get_status_client_send_sms()
        if not result_get_status_client_send_sms:
            return MahaResult(status_code=MahaResultStatusCode.KEEP_WAITING)
        # 延长锁时间
        self.extend_lock_expire_time()

        # 计算两个时间点的秒差
        get_vmn_time = datetime.strptime(self.login_data.get("get_vmn_time"), DATETIME_FORMAT)
        nowtime = datetime.now()
        delta_seconds = (nowtime - get_vmn_time).total_seconds()
        self.logger.info(f"登录用时：{delta_seconds}s, 获取vmn的时间：{get_vmn_time}, 收到短信发送通知的时间：{nowtime}")

        proxies = self.login_data['socks_ip']
        if not proxies:
            error_message = f"没有配置代理"
            self.logger.error(error_message)
            self.call_api_server(PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), False, {"error_message": "Please try again later."})
            return MahaResult(status_code=MahaResultStatusCode.NO_PROXY, error_message=error_message)
        # 创建主类实例
        maha = MahaRequest(user_info=user_info, proxies=proxies, logger=self.logger, local_mock=self.local_mock)
        # 验证是否发短信，获取customerId
        result = maha.verification_client_send_sms()
        self.sync_user_info(result.user_info, maha)
        if not result.is_success:
            self.logger.warning(f"超时停止检查客户端发送短信的状态，{result}")
            self.call_api_server(PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), False, {"error_message": result.error_message})
            return result
        self.logger.info(f"MobileVerificationService(), resp: {json.dumps(result.user_info.to_dict())}")

        """ 暂时不请求
        # 验证通过后，使用Password登录 todo 尝试不请求
        # result = maha.customer_login_ib_service()
        # self.sync_user_info(result.user_info)
        # if not result.is_success:
        #     self.logger.warning(f"ib登录失败，{result}")
            # return self.handle_client_send_sms_failed_return(result)
        """
        # 完成注册服务
        result = maha.complete_registration_service()
        self.sync_user_info(result.user_info, maha)
        if not result.is_success:
            self.logger.warning(f"注册失败，{result}")
            self.handle_client_send_sms_failed_return(result)
            return result
        self.call_api_server(PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), True, {"is_success": True})

        user_info = UserInfo.from_dict(self.login_data['user_info'])
        # 延长锁时间
        self.extend_lock_expire_time()
        # 处理登录操作
        result = self.handle_login(user_info)

        return result

    """
    检查代付订单的状态是否允许继续支付
    """

    def check_orders_df_is_allow_to_pay(self, orders_df: dict) -> bool:
        if orders_df is None or "code" not in orders_df.keys():
            return False
        code = orders_df.get("code")
        # 优先从缓存检查是否已完成支付
        redis_order_manager = RedisOrderManager(self.logger, self.redis)
        is_paid = redis_order_manager.contains_order(code)
        if is_paid:
            self.logger.warning(f"检查代付订单，当前状态：已经支付，code: {code}")
            return False
        # 通过接口查询代付订单的最新状态
        self.logger.info(f"通过接口查询代付订单的最新状态 /v1/websocket/orders_df, code: {code})")
        result = self.request_api_server(method="GET", url=f"{self.domain}/v1/websocket/orders_df?code={code}")
        self.logger.info(f"通过接口查询代付订单的最新状态 /v1/websocket/orders_df, code: {code}, result: {result})")
        if result is None or "is_success" not in result.keys() or "data" not in result.keys():
            return False
        if not result.get("is_success"):
            return False
        if result.get("data") is None:
            return False
        # 订单状态 0派单中，1待支付，2待确认，3回调中，4已完成，-1已取消
        status = int(result.get("data").get("status"))
        if status == 0:
            self.logger.warning(f"检查代付订单，当前状态：派单中，code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
            return False
        elif status == 1:
            self.logger.info(f"检查代付订单，当前状态：待支付，code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
            return True
        elif status == 2:
            self.logger.warning(f"检查代付订单，当前状态：待确认，code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
            return False
        elif status == 3:
            self.logger.warning(f"检查代付订单，当前状态：回调中，code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
            return False
        elif status == 4:
            self.logger.warning(f"检查代付订单，当前状态：已完成，code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
            return False
        elif status == -1:
            self.logger.warning(f"检查代付订单，当前状态：已取消，code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
            return False
        self.logger.error(
            f"检查代付订单，当前状态：未处理的状态，status: {status}, code: {code}, amount: {orders_df.get('amount')}, realpay: {orders_df.get('realpay')}")
        return False

    """
    检查受益人的名称是否在[beneficiary_list_dict, pending_beneficiaries_dict] 2个列表中
    """
    def get_beneficiary(self, beneficiary_list: list, payment_name: str) -> dict | None:
        if beneficiary_list is None:
            return None
        payment_name_upper = payment_name.replace(" ", "").upper()
        for item in beneficiary_list:
            if (
                    str(item.get("beneName", "")) == payment_name_upper
                    or str(item.get("beneNickName", "")) == payment_name_upper
            ):
                return item
        return None

    """
    执行付款流程
    """
    def execute_pay_process(self, user_info: UserInfo, orders_df: dict) -> MahaResult:
        self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}, pay_process_status: 【{orders_df.get("pay_process_status")}】, orders_df: {json.dumps(orders_df)}")
        proxies = self.login_data['socks_ip']
        if not proxies:
            error_message = f"没有配置代理"
            self.logger.error(error_message)
            return MahaResult(status_code=MahaResultStatusCode.NO_PROXY, error_message=error_message)

        # 创建主类实例
        maha = MahaRequest(user_info=user_info, proxies=proxies, logger=self.logger, local_mock=self.local_mock)

        # 刷新sessionId
        mahaResult = maha.customer_login_service()
        self.sync_user_info(mahaResult.user_info, maha)
        if not mahaResult.is_success:
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，customer_login_service() 请求失败 {mahaResult.to_json_str()}")
            return mahaResult

        # 查看所有受益人列表
        mahaResult = maha.view_beneficiary()
        self.sync_user_info(mahaResult.user_info, maha)
        if not mahaResult.is_success:
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，view_beneficiary() 查看所有受益人姓名失败 {mahaResult.to_json_str()}")
            return mahaResult
        # 受益人列表
        beneficiary_map = mahaResult.data

        # 已审核通过的受益人列表，示例：[{"transactionType":"ACC","beneName":"AMUDAMAHENDRAREDDY","beneNickName":"AMUDAMAHENDRAREDDY","beneficiaryStatus":"I"},{"transactionType":"ACC","beneName":"AMUDAMMAHENDRAREDDY","beneNickName":"AMUDAMMAHENDRAREDDY","beneficiaryStatus":"A"}]
        beneficiary_list_dict = beneficiary_map.get("BeneficiaryList") if "BeneficiaryList" in beneficiary_map else None
        # 审核中的受益人列表，示例：[{"transactionType":"ACC","beneName":"MATLASREEKANTH","beneNickName":"MATLASREEKANTH","beneficiaryStatus":"P"}]
        pending_beneficiaries_dict = beneficiary_map.get("PendingBeneficiaries") if "PendingBeneficiaries" in beneficiary_map else None

        # 添加受益人的名称
        payment_name = str(orders_df.get("payment_name")).replace(" ", "").upper()
        # 从审核中的 列表中获取受益人信息
        beneficiary_pending = self.get_beneficiary(pending_beneficiaries_dict, payment_name)
        # 从审核通过的 列表中获取受益人信息
        beneficiary_audited = self.get_beneficiary(beneficiary_list_dict, payment_name)

        self.logger.info(
            f"代付进度，orders_df.code: {orders_df.get("code")}，view_beneficiary() 查看所有受益人姓名 {beneficiary_map}"
            f" {"="*3} "
            f"审核通过的 所有受益人姓名 {beneficiary_list_dict}"
            f" {"="*3} "
            f"审核中的 所有受益人姓名 {pending_beneficiaries_dict}"
            f" {"="*3} "
            f"要添加受益人的姓名 {orders_df.get("payment_name")}"
            f" {"="*3} "
            f"从审核中的 受益人列表中，匹配结果：{beneficiary_pending}"
            f" {"="*3} "
            f"从审核通过的 受益人列表中，匹配结果：{beneficiary_audited}"
        )

        beneficiary = Beneficiary()
        beneficiary.bene_acc_no = orders_df.get("payment_account")
        beneficiary.bene_ifsc = orders_df.get("ifsc")
        beneficiary.bene_name = orders_df.get("payment_name")
        beneficiary.nick_name = payment_name

        # 添加受益人 (2个都为空时)
        if beneficiary_pending is None and beneficiary_audited is None:
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，受益人状态 添加：{payment_name}")

            # 添加受益人
            mahaResult = maha.add_beneficiary(beneficiary)
            # 添加受益人成功
            if mahaResult.is_success:
                # 延长锁时间
                self.extend_lock_expire_time()
                self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}：申请审核受益人 mahaResult: {mahaResult.to_json_str()}")
                # 响应正常，但提示重复时
                if MahaResultStatusCode.ADDED_BENEFICIARY_REPEAT == mahaResult.status_code:
                    self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}：添加受益人发现已存在，先删除，再重新添加 mahaResult: {mahaResult.to_json_str()}")
                    maha.delete_beneficiary(payment_name)
                    return self.execute_pay_process(user_info, orders_df)

                beneficiary = mahaResult.beneficiary
                orders_df['payment_name'] = beneficiary.bene_name
                orders_df['nick_name'] = beneficiary.nick_name
                # 申请审核受益人
                mahaResult = maha.approve_beneficiary(beneficiary)
                self.sync_user_info(mahaResult.user_info, maha)
                if mahaResult.is_success:
                    # 延长锁时间
                    self.extend_lock_expire_time()
                    self.logger.info(
                        f"代付进度，orders_df.code: {orders_df.get("code")}：申请审核受益人成功 pay_process_status 变更为 {PayProcessStatus.WAITING_FOR_AUDIT_ADD_BENEFICIARY}")
                    # 成功
                    orders_df['pay_process_status'] = PayProcessStatus.WAITING_FOR_AUDIT_ADD_BENEFICIARY.name
                    orders_df['pay_process_msg'] = mahaResult.error_message
                    orders_df['beneficiary'] = mahaResult.beneficiary
                    mahaResult = MahaResult(
                        is_success=mahaResult.is_success,
                        status_code=MahaResultStatusCode.ADDED_BENEFICIARY_AUDITING,
                        user_info=mahaResult.user_info,
                        data=mahaResult.data,
                        beneficiary=mahaResult.beneficiary,
                        orders_df=orders_df
                    )
                    return mahaResult
                else:
                    self.logger.info(
                        f"代付进度，orders_df.code: {orders_df.get("code")}：申请审核受益人失败, mahaResult: {mahaResult.to_json_str()}")
                    # 失败
                    if MahaResultStatusCode.FAIL_TO_APPROVE_BENEFICIARY == mahaResult.status_code:
                        orders_df['pay_process_status'] = MahaResultStatusCode.FAIL_TO_APPROVE_BENEFICIARY.name
                    else:
                        orders_df['pay_process_status'] = PayProcessStatus.FAILED_ADD_BENEFICIARY.name
                    orders_df['pay_process_msg'] = mahaResult.error_message
                    mahaResult = MahaResult(
                        is_success=mahaResult.is_success,
                        status_code=mahaResult.status_code,
                        error_message=mahaResult.error_message,
                        user_info=mahaResult.user_info,
                        data=mahaResult.data,
                        beneficiary=mahaResult.beneficiary,
                        orders_df=orders_df
                    )
                    return mahaResult
            else:
                self.logger.error(
                    f"代付进度，orders_df.code: {orders_df.get("code")}: 添加受益人失败, mahaResult: {mahaResult.to_json_str()}")
                orders_df['pay_process_status'] = PayProcessStatus.FAILED_ADD_BENEFICIARY.name
                orders_df['pay_process_msg'] = mahaResult.error_message
                mahaResult = MahaResult(
                    is_success=mahaResult.is_success,
                    status_code=MahaResultStatusCode.ADDED_BENEFICIARY_FAILED,
                    error_message=mahaResult.error_message,
                    user_info=mahaResult.user_info,
                    data=mahaResult.data,
                    beneficiary=mahaResult.beneficiary,
                    orders_df=orders_df
                )
                return mahaResult

        # 开始转账（受益人被审核）
        elif beneficiary_pending is None and beneficiary_audited is not None:
            if "beneficiaryStatus" not in beneficiary_audited:
                self.logger.error(
                    f"代付进度，orders_df.code: {orders_df.get("code")}，受益人状态 {payment_name} 响应参数缺少 beneficiaryStatus")
                return MahaResult(
                    status_code=MahaResultStatusCode.BENEFICIARY_INFO_ERROR,
                    error_message=f"Beneficiary's status error"
                )
            elif "A" != beneficiary_audited.get("beneficiaryStatus"):
                self.logger.error(
                    f"代付进度，orders_df.code: {orders_df.get("code")}，受益人状态 {payment_name} 不是A beneficiaryStatus: {beneficiary_audited.get("beneficiaryStatus")}")
                return MahaResult(
                    status_code=MahaResultStatusCode.ADDED_BENEFICIARY_AUDITING,
                    error_message=f"Beneficiary's status auditing"
                )
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，受益人状态 审核通过：{payment_name}")
            # 检查余额是否充足
            mahaResult = maha.account_enquiry()
            self.sync_user_info(mahaResult.user_info, maha)
            if not mahaResult.is_success and MahaResultStatusCode.RESPONSE_01_FAILED == mahaResult.status_code:
                wait_seconds = 30
                self.logger.info(f"代付进度，查账户响应 status:01, msg:FAILED, 等待{wait_seconds}秒再查账户, mahaResult: {mahaResult.to_json_str()}")
                time.sleep(wait_seconds)
                mahaResult = maha.customer_login_service()
                if not mahaResult.is_success and (
                        MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                    return mahaResult
                self.sync_user_info(mahaResult.user_info, maha)
                time.sleep(wait_seconds/2)
                mahaResult = maha.account_enquiry()
                self.sync_user_info(mahaResult.user_info, maha)
                if not mahaResult.is_success and MahaResultStatusCode.RESPONSE_01_FAILED == mahaResult.status_code:
                    self.logger.info(f"代付进度，查账户响应 status:01, msg:FAILED, 中止代付")
                    return MahaResult(
                        is_success=False,
                        status_code=MahaResultStatusCode.ACCOUNT_BLOCKED,
                        error_message=MahaResultStatusCode.ACCOUNT_BLOCKED.en_cue_words
                    )

            if not mahaResult.is_success or mahaResult.account_balance is None:
                return mahaResult
            elif mahaResult.account_balance.AvailableBalance - float(orders_df.get("amount")) < 0:
                self.logger.info(
                    f"代付进度，orders_df.code: {orders_df.get("code")}：可用余额不足以支付订单，被取消, 可用余额：{mahaResult.account_balance.AvailableBalance}, 需要支付：{orders_df.get("amount")}")
                mahaResult = MahaResult(
                    is_success=False,
                    status_code=MahaResultStatusCode.BALANCE_INSUFFICIENT,
                    error_message=MahaResultStatusCode.BALANCE_INSUFFICIENT.en_cue_words
                )
                return mahaResult

            """
            开始处理支付
            """
            # 延长锁时间
            self.extend_lock_expire_time()
            # 查询受益人详情
            mahaResult = maha.view_beneficiary_details(beneficiary)
            self.sync_user_info(mahaResult.user_info, maha)
            if not mahaResult.is_success:
                self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")} 查询受益人 {orders_df.get("payment_name")} 详情失败, mahaResult: {mahaResult.to_json_str()}")
                return mahaResult
            # 延长锁时间
            self.extend_lock_expire_time()
            # 检查收款人是否正确
            bank_beneficiary = mahaResult.beneficiary
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")} 比较受益人 {orders_df.get("payment_name")}，添加的信息：account: {orders_df.get("payment_account")}, ifsc: {orders_df.get("ifsc")}")
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")} 比较受益人 {beneficiary.bene_name}，查到的信息：account: {bank_beneficiary.bene_acc_no}, ifsc: {bank_beneficiary.bene_ifsc}")
            if bank_beneficiary.bene_acc_no != orders_df.get("payment_account") or bank_beneficiary.bene_ifsc != orders_df.get("ifsc"):
                maha.delete_beneficiary(orders_df.get("payment_name"))
                self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}：发现受益人姓名相同，但账户信息不同的情况，删除旧的受益人：{orders_df.get("payment_name")}")
                return self.execute_pay_process(user_info, orders_df)
            beneficiary = bank_beneficiary
            beneficiary.transfer_amount = orders_df.get("amount")
            beneficiary.orders_df_code = orders_df.get("hash_code")
            beneficiary.payment_mode = FUNDS_TRANSFER_SERVICE_PAYMENT_MODE
            # 执行支付
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}：准备支付 支付方式：{FUNDS_TRANSFER_SERVICE_PAYMENT_MODE}")
            mahaResult = maha.funds_transfer_service(beneficiary)
            self.sync_user_info(mahaResult.user_info, maha)
            if not mahaResult.is_success:
                self.logger.info(
                    f"代付进度，orders_df.code: {orders_df.get("code")}：支付失败： {mahaResult.to_json_str()}")
                orders_df['pay_process_status'] = PayProcessStatus.FAILED_TO_PAID.name
                orders_df['pay_process_msg'] = mahaResult.error_message
                mahaResult.orders_df = orders_df
                return mahaResult
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}：支付完成： {mahaResult.to_json_str()}")
            # 支付成功
            orders_df['pay_process_status'] = PayProcessStatus.PAID_SUCCESS.name
            orders_df['utr'] = mahaResult.beneficiary.utr
            mahaResult = MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.PAID_SUCCESS,
                orders_df=orders_df,
                beneficiary=beneficiary
            )
            return mahaResult

        # 继续等待受益人被审核（受益人存在于审核中列表时）
        elif beneficiary_pending is not None:
            mahaResult = maha.approve_beneficiary(beneficiary)
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，申请审核受益人：{payment_name}, mahaResult: {mahaResult.to_json_str()}")
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.ADDED_BENEFICIARY_AUDITING,
                orders_df=orders_df
            )
        else:
            if (
                    "pay_process_status" in orders_df
                    and MahaResultStatusCode.FAIL_TO_APPROVE_BENEFICIARY.name == orders_df['pay_process_status']
            ):
                self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，发现受益人上次申请审核失败，尝试再次申请审核：{payment_name}")
                mahaResult = maha.approve_beneficiary(beneficiary)
                if not mahaResult.is_success:
                    self.logger.warning(f"代付进度，orders_df.code: {orders_df.get("code")}，受益人上次申请审核失败，尝试再次申请审核仍然失败，删除受益人：{payment_name}, mahaResult: {mahaResult.to_json_str()}")
                    return mahaResult
            self.logger.info(f"代付进度，orders_df.code: {orders_df.get("code")}，受益人状态 等待审核：{payment_name}")
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.ADDED_BENEFICIARY_AUDITING,
                orders_df=orders_df
            )
    """
    处理代付
    """
    def handle_orders_df(self, orders_df_items, user_info: UserInfo):
        for hash_name, hash_data in orders_df_items:
            self.logger.info(f"准备开始 处理代付订单 user_info = {user_info.__str__()}")
            self.logger.info(f"准备开始 处理代付订单 hash_data = {hash_name} = {hash_data}")
            self.logger.info(f"准备开始 处理代付订单 login_data: {json.dumps(self.login_data)}")
            orders_df_code = hash_data.get("code")
            check_result = self.check_orders_df_is_allow_to_pay(hash_data)
            if not check_result:
                continue
            # 延长锁时间
            self.extend_lock_expire_time()
            mahaResult = self.execute_pay_process(user_info, hash_data)
            self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code}, 返回的结果: {mahaResult.to_json_str()}")
            if mahaResult is None:
                continue
            # 执行代付失败
            if mahaResult.is_success:
                # 延长锁时间
                self.extend_lock_expire_time()
                # 处理支付成功
                if mahaResult.status_code == MahaResultStatusCode.PAID_SUCCESS:
                    beneficiary = mahaResult.beneficiary
                    orders_df_hash_code = hash_data.get("hash_code")
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code}, hash_code: {orders_df_hash_code} 完成代付，开始处理缓存，mahaResult： {mahaResult.to_json_str()}")
                    hash_name_orders_df_success_to_paid = self.get_hash_name_orders_df_success_to_paid(self.login_data['id'])
                    # 优先保存已支付的订单号到缓存，防止重复支付
                    redis_order_manager = RedisOrderManager(self.logger, self.redis)
                    redis_order_manager.add_paid_ok_order(orders_df_code)
                    if "NEFT" == beneficiary.payment_mode or "NEFT" == FUNDS_TRANSFER_SERVICE_PAYMENT_MODE:
                        self.redis.hset(name=hash_name_orders_df_success_to_paid,
                                        key=orders_df_code,
                                        value=beneficiary.utr)
                        self.redis.hset(name=hash_name_orders_df_success_to_paid,
                                        key=beneficiary.utr,
                                        value=orders_df_code)
                        self.redis.hset(name=hash_name_orders_df_success_to_paid,
                                        key=self.get_hash_key_orders_df_success_to_paid_time(beneficiary.utr),
                                        value=f"{datetime.now().strftime(DATETIME_FORMAT)}")
                    elif "P2A" == beneficiary.payment_mode:
                        # 把hashcode和对应的订单号，保存到缓存，以便抓取账单时获取订单号
                        self.redis.hset(name=hash_name_orders_df_success_to_paid,
                                        key=orders_df_hash_code,
                                        value=orders_df_code)
                        self.redis.hset(name=hash_name_orders_df_success_to_paid,
                                        key=self.get_hash_key_orders_df_success_to_paid_time(orders_df_hash_code),
                                        value=f"{datetime.now().strftime(DATETIME_FORMAT)}")
                    self.redis.delete(hash_name)
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 完成代付，处理缓存完成")

                    # 成功后跳出循环
                    break
                # 其它情况跳过,不做任何处理
                else:
                    self.logger.info(
                        f"处理代付订单 orders_df.code: {orders_df_code} 未完成代付，继续... 更新缓存{hash_name} : mahaResult.orders_df: {mahaResult.orders_df}")
                    if mahaResult.orders_df is not None:
                        # 更新缓存
                        self.redis.hset(name=hash_name, mapping=mahaResult.orders_df)
            else:
                if mahaResult.status_code == MahaResultStatusCode.LOGOUT:
                    # 通知订单返回订单池，并记录 partner,payment 的当前代付订单已因账户异常取消
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": mahaResult.error_message,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 准备下线 payment {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                    return mahaResult
                elif mahaResult.status_code == MahaResultStatusCode.SESSION_EXPIRED:
                    # 通知订单返回订单池，并记录 partner,payment 的当前代付订单已因upi下线取消，需要重新登录再接单
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": "UPI offline",
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} Session expired, UPI offline，取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                    return MahaResult(status_code=MahaResultStatusCode.LOGOUT)
                # 处理余额不足
                elif mahaResult.status_code == MahaResultStatusCode.BALANCE_INSUFFICIENT:
                    # 通知订单返回订单池，并记录 partner,payment 的当前代付订单已因余额不足取消
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": mahaResult.error_message,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 可用余额不足以支付订单，取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                # 处理TPIN错误
                elif mahaResult.status_code == MahaResultStatusCode.TPIN_ERROR:
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": "Your tpin is incorrect. Please change it and try again",
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} TPIN 错误 {mahaResult.error_message}")
                    self.call_api_server(type="tpin_error", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                elif mahaResult.status_code == MahaResultStatusCode.BENEFICIARY_INFO_ERROR:
                    # 通知订单返回订单池，并记录 partner,payment 的当前代付订单已因受益人信息错误取消
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": MahaResultStatusCode.BENEFICIARY_INFO_ERROR.en_cue_words,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 受益人信息错误取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                elif mahaResult.status_code == MahaResultStatusCode.ADDED_BENEFICIARY_FAILED:
                    # 通知订单返回订单池，并记录 partner,payment 的当前代付订单已因添加受益人失败而取消
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": mahaResult.error_message,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 添加受益人失败而取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                elif mahaResult.status_code == MahaResultStatusCode.ACCOUNT_BLOCKED:
                    # 通知订单返回订单池，并记录 partner,payment 的当前代付订单已因账户异常取消
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": mahaResult.error_message,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 账户查询异常，取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                elif mahaResult.status_code == MahaResultStatusCode.CANNOT_TRANSFER_TO_YOURSELF:
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": mahaResult.error_message,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 转账给了自己，取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                elif mahaResult.status_code == MahaResultStatusCode.FUND_SOME_CONNECTIVITY_ISSUES:
                    api_request_data = {
                        "error_code": orders_df_code,
                        "error_message": mahaResult.error_message,
                    }
                    self.logger.info(f"处理代付订单 orders_df.code: {orders_df_code} 转账频繁 或 受益人账号有未知问题，取消订单 {mahaResult.error_message}")
                    self.call_api_server(type="orders_df_status_to_pending", status=False, value=api_request_data)
                    self.redis.delete(hash_name)
                else:
                    self.logger.info(
                        f"处理代付订单 orders_df.code: {orders_df_code} 代付失败，不做任何处理 status_code: {mahaResult.status_code}, error_message: {mahaResult.error_message}")

        # return MahaResult(is_success=True, status_code=MahaResultStatusCode.TRUE)

    """
    抓取账单
    """

    def handle_grab_transaction_history(self, user_info: UserInfo) -> MahaResult:
        self.logger.info(f"准备开始读取账单，user_info: {user_info.__str__()}")
        self.logger.info(f"准备开始读取账单，login_data: {json.dumps(self.login_data)}")
        proxies = self.login_data['socks_ip']
        if not proxies:
            error_message = f"没有配置代理"
            self.logger.error(error_message)
            return MahaResult(status_code=MahaResultStatusCode.NO_PROXY, error_message=error_message)
        # 创建主类实例
        maha = MahaRequest(user_info=user_info, proxies=proxies, logger=self.logger, local_mock=self.local_mock)
        # 延长锁时间
        self.extend_lock_expire_time()
        result = maha.account_enquiry()
        self.sync_user_info(result.user_info, maha)
        if result.is_success and result.account_balance is not None:
            self.login_data['account_balance'] = result.account_balance.to_dict()

        time.sleep(2)
        # 查账单
        result = maha.mini_statement_service()
        self.sync_user_info(result.user_info, maha)

        if not result.is_success or not result.data or "transactionDetails" not in result.data.keys():
            return result
        # 更新缓存
        self.redis.setex('login_on_{}_{}'.format(self.name, self.login_data['id']), 11 * 60, 1)
        
        for transaction in result.data.get("transactionDetails"):
            if transaction is None:
                continue

            # 延长锁时间
            self.extend_lock_expire_time()
            self.sync_a_transaction_record(user_info, transaction)

        return result

    """
    处理检查客户端发送失败
    """

    def handle_client_send_sms_failed_return(self, result):
        if result is not None and result.status_code is not None:
            if result.status_code == MahaResultStatusCode.DEVICE_LOCKED:
                call_api_server_data = {
                    "error_code": MahaResultStatusCode.DEVICE_LOCKED.name,
                    "error_message": "Please try again later."
                }
            else:
                call_api_server_data = {
                    "error_code": result.status_code,
                    "error_message": result.error_message
                }
        else:
            call_api_server_data = {
                "error_code": "unknown",
                "error_message": "Unknown error, please try again later."
            }
        self.call_api_server(PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), False, call_api_server_data)

    # 处理登录失败
    def handle_login_failed_return(self, result: MahaResult) -> MahaResult:
        if result.status_code == MahaResultStatusCode.LOGOUT:
            request_data = {
                "error_code": result.status_code,
                "error_message": result.error_message
            }
            # 抓取个人信息状态检查成功
            self.call_api_server(type=PaymentLoginProgress.GET_PROFILE.name.lower(), status=False, value=request_data)
            self.logger.error(f"下线，原因：{request_data}")
            self.on_off(0)
        return result

    # 处理登录
    def handle_login(self, user_info: UserInfo) -> MahaResult:
        proxies = self.login_data['socks_ip']
        if not proxies:
            error_message = f"没有配置代理"
            self.logger.error(error_message)
            return MahaResult(status_code=MahaResultStatusCode.NO_PROXY, error_message=error_message)
        maha = MahaRequest(user_info=user_info, proxies=proxies, logger=self.logger, local_mock=self.local_mock)
        result = maha.get_banner_images()
        self.sync_user_info(result.user_info, maha)
        if not result.is_success:
            self.logger.warning(f"get_banner_images() 失败，{result}")
            return self.handle_login_failed_return(result)

        time.sleep(2)
        result = maha.customer_login_service()
        self.sync_user_info(result.user_info, maha)
        if not result.is_success:
            self.logger.warning(f"customer_login_service() 失败，{result}")
            return self.handle_login_failed_return(result)
        # 通知获取个人信息成功
        call_api_server_result = self.call_api_server(type=PaymentLoginProgress.GET_PROFILE.name.lower(), status=True, value={})
        if not call_api_server_result:
            self.logger.error(f"调用api服务，通知[get_profile]失败")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT)

        # 回调api, 通知payment有绑定新的upi
        request_data = {
            'type': 'UPI',
            'bank_name': self.name,
            'payment_id': self.login_data['id'],
            'partner_id': self.login_data['partner_id'],
            'upi': result.user_info.customerId if not self.local_mock else f"MOCK_{self.login_data.get("id")}"
        }
        result_call_api_order_success = self.call_api_order_success(request_data)
        if not result_call_api_order_success or not result_call_api_order_success.get("is_success"):
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT)

        time.sleep(2)
        # 查账单
        result = maha.mini_statement_service()
        self.sync_user_info(result.user_info, maha)
        if not result.is_success:
            self.logger.warning(f"mini_statement_service() 失败，{result}")
            self.call_api_server(type='get_transaction_history', status=False, value={})
            return self.handle_login_failed_return(result)
        """
        处理登录成功
        更改缓存上线
        """
        self.on_off(1)
        self.login_data['online_time'] = datetime_utils.get_current_time_as_string()

        self.call_api_server(type='get_transaction_history', status=True, value={})
        return result

    # 获得并删除最新的tpin
    def get_tpin_newest(self, payment_id):
        redis_key = f"payment_tpin_newest:{payment_id}"
        value = self.redis.get(redis_key)
        if value is not None:
            self.logger.info(f"redis key: {redis_key}，新的tpin: {value}, type: {type(value)}, str: {str(value)}")
            self.redis.delete(redis_key)
        if isinstance(value, bytes):
            value = value.decode('utf-8')
        return value

    def main(self):
        try:
            # 生成新的trace_id
            trace_id = f"{os.getpid()} {uuid.uuid4()}"
            self.logger.info(f"开始一次循环任务: {trace_id}")
            trace_id_filter.trace_id = trace_id

            # 1 先检查list中与hash的比较，是否hash中已有，如果有，则抛弃，如果没有则放置hash和有序集合
            pop_data = self.redis.lpop(self.list_key)
            if not pop_data:
                self.logger.debug(f"循环任务 没有要处理的 新登录 {self.list_key}")
                pass
            # 添加新的登录任务
            else:
                self.logger.info(f"循环任务 发现要处理的payment 需要新登录 redis key: {self.list_key}: {pop_data}")
                pop_data_set = simplejson.loads(pop_data.decode())
                if self.redis.hexists(self.hash_key, pop_data_set['id']):
                    # 如果有，则抛弃
                    self.logger.warning(f"循环任务 正在处理payment redis key: {self.hash_key}: {pop_data_set['id']} ")
                else:
                    # 如果没有则放置在hash和有序集合
                    self.logger.info(f"循环任务 准备处理新登录 redis key: {self.hash_key} 不包含payment.id: {pop_data_set['id']}")
                    self.redis.hset(self.hash_key, pop_data_set['id'], simplejson.dumps(pop_data_set))
                    # 新登录，分数设置为1，优先级仅次于检查发送短信
                    self.redis.zadd(self.set_key, {pop_data_set['id']: 1})

            self.read_zset(self.set_key)
            # 从有序集合中，获取1S外的成员，限100个
            reduced_time = 1
            zrangebyscore_max = int(time.time()) - reduced_time
            members = self.redis.zrangebyscore(self.set_key, 0, zrangebyscore_max, 0, 10, withscores = True)
            if members is None or not members:
                self.logger.debug(f"循环任务 没有要处理的 payment {self.set_key} min: 0, max: {zrangebyscore_max}")
                time.sleep(5)
                return
            for i, score in members:
                _id = i.decode()
                self.logger.debug(f"循环任务 发现要处理的 payment.id: {_id} {self.set_key} min: 0, max: {zrangebyscore_max} score: {score}")
                # 读取缓存，确定是否本地模拟
                payment_mock = self.redis.exists(f"payment_mock:{_id}")
                if payment_mock:
                    # 标记本次为本地模拟
                    self.local_mock = True
                self.payment_id = _id
                trace_id_filter.trace_id = f"{trace_id} payment.id:{_id}"
                login_data = self.redis.hget(self.hash_key, _id)

                # 获得当前时间的字符串格式
                current_time_as_string = datetime_utils.get_current_time_as_string()
                if not login_data:
                    # 不存在hash数据，则删除有序集合的元素
                    self.logger.warning(f"循环任务 处理 payment_id: {_id} {self.hash_key} 中不存在数据，从set列表缓存 {self.set_key} 中删除 {self.payment_id}！")
                    self.redis.zrem(self.set_key, _id)
                    continue
                else:
                    # 存在hash数据，则开始登录或者爬取账单等
                    _lock = self.get_lock(_id)
                    if _lock:
                        self.task_begin_time = datetime.now()
                        self.task_lock = _lock
                        self.logger.info(f"循环任务 处理 payment_id: {_id} 获取到锁: {_lock}, {self.task_begin_time}, {self.hash_key}: {login_data}")
                        # 操作前获取锁
                        self.login_data = simplejson.loads(login_data.decode())

                        tpin = self.get_tpin_newest(_id)
                        if tpin is not None:
                            self.login_data['tpin'] = tpin
                        self.read_cache('main() init login_data')
                        # 获取payment_id绑定的设备
                        device_info = self.get_or_create_a_new_device(_id)
                        self.login_data['device_info'] = device_info.__str__()
                        # 获取代理ip
                        proxy = self.get_proxies()
                        if not proxy:
                            self.logger.error(f"循环任务 redis key: {self.list_key} payment_id: {_id} 无代理！")
                            continue
                        self.login_data['socks_ip'] = proxy if 'socks_ip' not in self.login_data or not self.login_data['socks_ip'] else self.login_data['socks_ip']
                        self.logger.info(f"循环任务 开始处理任务，hash_key: {self.hash_key}, login_data: {self.login_data}")
                        maha_result = MahaResult(status_code=MahaResultStatusCode.FALSE)

                        # 处理登录
                        if self.login_data['status'] == 'prepare_login':
                            self.logger.info(f"处理登录 prepare_login")
                            # 记录登录时间
                            self.login_data['prepare_login_time_sync'] = current_time_as_string
                            # 记录同步时间
                            self.login_data['last_time_sync'] = current_time_as_string
                            # 处理预登录
                            maha_result = self.handle_prepare_login()
                            if maha_result.is_success:
                                # 记录获取发送短信号码及内容的成功的时间
                                self.login_data['get_send_sms_info_time'] = datetime_utils.get_current_time_as_string()
                                self.login_data['user_info'] = maha_result.user_info.to_dict()
                                self.login_data['status'] = 'send_sms_check'

                        # 检查短信发送
                        elif self.login_data['status'] == 'send_sms_check':
                            verification_client_send_sms_times = self.login_data.get("verification_client_send_sms_times", 0)
                            self.logger.info(f"处理登录 send_sms_check 第{verification_client_send_sms_times + 1}次检查发送短信的状态")

                            # 获取user_info对象
                            user_info = UserInfo.from_dict(self.login_data['user_info'])

                            # 处理验证客户端发送短信的状态
                            maha_result = self.handle_verification_client_send_sms(user_info)
                            self.read_cache(f'main() handle_verification_client_send_sms, res: {maha_result}')
                            if maha_result.is_success:
                                self.logger.info(f"处理登录 send_sms_check 第{verification_client_send_sms_times + 1}次检查发送短信的状态 成功")
                                self.login_data['status'] = 'grab_transaction_history'
                                self.login_data['user_info'] = maha_result.user_info.to_dict()
                            # 没收到客户端发送短信的通知时，继续等待
                            elif MahaResultStatusCode.KEEP_WAITING == maha_result.status_code:
                                get_vmn_time = datetime.strptime(self.login_data.get("get_vmn_time"), DATETIME_FORMAT)
                                nowtime = datetime.now()
                                # 计算两个时间点的秒差
                                delta_seconds = (nowtime - get_vmn_time).total_seconds()
                                self.logger.info(f"处理登录 send_sms_check 第{verification_client_send_sms_times + 1}次检查发送短信的状态 继续等待 已等待{delta_seconds}s")

                                # 超时终止
                                if delta_seconds >= 30:
                                    verification_client_send_sms_error_message = f"Please complete the SMS within 30 seconds"
                                    self.logger.warning(f"处理登录 send_sms_check 客户端未在30秒内完成短信发送, get_vmn_time: {get_vmn_time}, delta_seconds: {delta_seconds}s, {verification_client_send_sms_error_message}")
                                    # 通知客户端 短信发送超时
                                    self.call_api_server(PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), False, {"error_message": verification_client_send_sms_error_message})
                                    maha_result = MahaResult(status_code=MahaResultStatusCode.LOGOUT, error_message=verification_client_send_sms_error_message)
                                # 未超时，继续等待
                                else:
                                    self.login_data["verification_client_send_sms_times"] = verification_client_send_sms_times + 1

                            else:
                                self.logger.info(f"处理登录 send_sms_check 第{verification_client_send_sms_times + 1}次检查发送短信的状态 失败：{maha_result.to_json_str()}")

                        elif self.login_data['status'] == 'grab_transaction_history':
                            if "last_time_sync" not in self.login_data or self.login_data.get("last_time_sync") == None:
                                self.login_data["last_time_sync"] = current_time_as_string
                            # 获取最后一次同步时间
                            last_time_sync = datetime_utils.string_to_datetime(self.login_data["last_time_sync"])
                            now_time = datetime.now()
                            # 计算2个时间差
                            calculate_time_diff = datetime_utils.calculate_time_diff(last_time_sync, now_time)
                            # 从redis中，取出所有待处理的代付订单
                            key_header = f"orders_df_maha_payment:{self.login_data['id']}"
                            hash_datas = self.redis_hash_scan(key_header)
                            if len(hash_datas) > 0 or calculate_time_diff.seconds > 60 * 10:
                                self.logger.info(f"处理代付或账单，匹配需要处理代付订单 key: {key_header} {len(hash_datas)} 个，与上次同步时间间隔: {calculate_time_diff}s, last_time_sync: {last_time_sync}, now_time: {now_time}")
                                self.login_data['last_time_sync'] = current_time_as_string
                                # 获取user_info对象
                                user_info = UserInfo.from_dict(self.login_data['user_info'])
                                user_info.tpin = self.login_data['tpin']
                                self.login_data['user_info'] = user_info.to_dict()
                                # 处理代付
                                maha_result = self.handle_orders_df(hash_datas.items(), user_info)
                                if (
                                    maha_result is not None
                                    and not maha_result.is_success
                                    and (
                                        maha_result.status_code == MahaResultStatusCode.LOGOUT
                                        or maha_result.status_code == MahaResultStatusCode.SESSION_EXPIRED
                                    )
                                ):
                                    pass
                                else:
                                    # 抓取账单
                                    maha_result = self.handle_grab_transaction_history(user_info)
                            else:
                                self.logger.info(f"处理代付或账单 跳过，匹配需要处理代付订单 key: {key_header} {len(hash_datas)} 个，与上次同步时间间隔: {calculate_time_diff}s, last_time_sync: {last_time_sync}, now_time: {now_time}")
                        else:
                            # status有问题
                            self.logger.error(
                                f"payment.id: {_id} {self.list_key} 下线，原因：有未处理的status={self.login_data['status']}")
                            self.login_off()
                            self.on_off(0)
                            self.read_cache(f'main() status error')

                        self.logger.info(f"type(maha_result): {type(maha_result)}")

                        if (
                                maha_result is not None
                                and isinstance(maha_result, MahaResult)
                                and (
                                    MahaResultStatusCode.LOGOUT == maha_result.status_code
                                    or MahaResultStatusCode.SESSION_EXPIRED == maha_result.status_code
                                    or MahaResultStatusCode.DEVICE_LOCKED == maha_result.status_code
                                )
                        ):
                            # 删除相关的hash和set中的值
                            self.logger.error(
                                f"payment.id: {_id}, {self.list_key} 下线, 逻辑下线，status_code: {maha_result.status_code}, error_message: {maha_result.error_message}")
                            self.login_off()
                            self.on_off(0)
                            # 如果设备被锁时，删除设备，下次登录生成新的设备
                            if MahaResultStatusCode.DEVICE_LOCKED == maha_result.status_code:
                                self.delete_a_device(_id)
                            self.read_cache(f'main() logout')
                        else:
                            # 更新集合和hash里的值
                            self.update_key()
                            self.read_cache(f'main() True')

                        # 删除锁
                        self.del_lock(_id, _lock)
                    else:
                        self.logger.info(f"循环任务 获取锁 未获取到锁")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('过程错误： 错误详情：{}\n{}'.format(e, error_message))


if __name__ == '__main__':
    bank = BankLogin()
    while True:
        try:
            bank.init_function(logger)
            bank.main()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logger.error('脚本运行错误,3秒后重试: id: {} {}\n{}'.format(bank.payment_id, e, error_message))
            # 插入redis，防止非主逻辑内的出错
            bank.redis = bank.connection_redis()
        finally:
            logger.info(f"循环任务 结束一次循环 {'=' * 66}")
            time.sleep(1)
