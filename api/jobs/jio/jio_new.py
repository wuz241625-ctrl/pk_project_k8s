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

from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Dict

import redis
import requests
import simplejson
from Cryptodome.Cipher import AES
from requests.adapters import HTTPAdapter
from response_logger import ResponseLogger

# 将项目的主目录添加进系统path，才能直接调用application文件夹下面的模块等
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
parent2_dir = os.path.dirname(parent_dir)
sys.path.append(parent2_dir)

import config
from application.lakshmi_api.enums.payment_login_progress import PaymentLoginProgress

#jio爬取账单，需要发送短信

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

class BankLogin(object):
    versionNo = 4085
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
        self.if_callback_key = 'jio_if_callback_key' # 存放已经第一次采集或这已经回调过的账单,使用有序集合存放,分数为时间,在2分钟内不成功回调会自动再回调
        self.clean_if_callback_key_time = 60 * 60 * 24 * 60 # 清理 if_callback_key 中时间较久的utr ,避免已经回调过的utr数据量过大
        self.lock_time = 40  # 操作锁的锁定时间
        self.lock_time2 = 15  # 登录锁的锁定时间
        self.time_grab = 40  # 短时间频繁爬取
        self.time_grab2 = 10 * 60  # 长时间爬取
        self.order_time_out = 5 * 60
        self.check_client_send_sms_time_out = 90 # 等待发送短信的最长时间
        self.try_sendOTP_limit = 3  # 最大尝试发送OTP的次数
        self.try_verify_otp_limit = 2  # 最大尝试验证OTP的次数
        self.try_device_check_limit = 3  # 最大尝试device_check的次数
        self.try_send_sms_limit = 3  # 最大尝试获取短信内容的次数
        self.try_verify_sms_limit = 3  # 最大尝试验证短信的次数
        self.try_count_limit = 10  # 最大尝试爬取账单的次数
        self.try_upi_limit = 10  # 最大尝试爬取upi的次数，(爬取upi失败还可以爬取账单)-----
        self.order_grab_time_out = 4 * 60 * 60  # 检测爬取的账单时间是否在规定范围内，不是则舍弃
        self.upi_time = 5 * 60 # 隔多久爬取一次upi
        self.domain = API_SERVER_DOMAIN  # 接口域名
        self.session = None
        self.logger = None
        self.response_logger = None # 打印的请求的全部过程日志，包括请求头和返回头等
        self.id = None  # payment id
        self.login_data = None # 整个过程使用的数据
        self.try_count = 8  # 爬取最大重试次数，超过则直接下线
        self.list_count = 4  # 当list个数小于某个值之后暂缓pop，避免导致爬取过快
        self.list_count_time = 4
        self.local_mock = False  # 是否模拟测试
        self.android_id = None
        # 与设备相关的参数过期时间
        self.device_timeout = 60 * 60 * 24 * 60
        # sessionId参数过期时间,真正过期大概在30分钟,为确保在2个10分钟之后能够更新sessionId,设置为19分钟
        self.session_id_timeout = 60 * 19

        # 连接redis
        self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')

    def init_function(self, exist_logger):
        self.session = requests.Session()
        self.session.mount('http://', HTTPAdapter(max_retries=1))
        self.session.mount('https://', HTTPAdapter(max_retries=1))
        self.logger = exist_logger
        # 打印的请求的全部过程日志，包括请求头和返回头等
        self.response_logger = ResponseLogger(exist_logger)
        # 检测是否联通，如果断联需重新连接
        self.local_mock = False
        self.check_redis_connection()

    def check_redis_connection(self):
        try:
            redis_response = self.redis.ping()
            if not redis_response:
                self.logger.info(f"bank: {self.name},id: {self.id}; Redis服务未能ping通,3秒后重新连接")
                self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        except Exception as e:
            self.logger.info(f"bank: {self.name},id: {self.id}; Redis 连接失败,3秒后重试: {e}")
            time.sleep(2)
            self.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
            self.check_redis_connection()  # 递归尝试，不恢复连接不进行下一步

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
            self.logger.error('get_proxies 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    # 检测代理是否在有效库里
    def check_proxy(self):
        try:
            _indian_socks_ip = self.redis.get(f'indian_socks_ip_{self.name}')
            if not _indian_socks_ip:
                self.logger.error(f'check_proxy（） 无 indian_socks_ip_{self.name}')
                return False
            _indian_socks_ip = _indian_socks_ip.decode().split(',')
            _indian_socks_ip = [item for item in _indian_socks_ip if item.strip()]
            for i in _indian_socks_ip:
                proxies = {
                    'http': i if i.startswith('socks5://') else 'socks5://{}'.format(i),
                    'https': i if i.startswith('socks5://') else 'socks5://{}'.format(i)
                }
                if proxies == self.login_data['socks_ip']:
                    self.logger.info(f'check_proxy（） 代理ip仍有效 indian_socks_ip_{self.name}')
                    return proxies
            self.logger.error(f'check_proxy（） 代理ip无效，更新 indian_socks_ip_{self.name}')
            return self.get_proxies()
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_proxies 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    def get_lock(self, id):
        try:
            # 获取锁
            busy_key = '{}_operate_{}'.format(self.name, id)
            _value = secrets.token_hex(8)
            _lock = self.redis.setnx(busy_key, _value) # 返回 0 已存在, 1 不存在且设置成功
            if not _lock:
                # 防止死锁
                _ttl = self.redis.ttl(busy_key)
                self.logger.info(f"{id}, {busy_key} 剩余生存时间 {_ttl} s")
                if _ttl and int(_ttl) > self.lock_time:
                    self.redis.delete(busy_key)
                    self.logger.error(f"{id}, 死锁并删除 {_value}")
                return False
            self.redis.expire(busy_key, self.lock_time)
            self.logger.info(f"{id},{busy_key} 加锁时间 {self.lock_time} s, _value: {_value}")
            return _value
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_lock 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    def del_lock(self, id, value):
        try:
            # 获取锁，30秒内锁定
            busy_key = '{}_operate_{}'.format(self.name, id)
            self.logger.info(f"{self.login_data['id']} 准备删除Lock {busy_key}")
            _lock = self.redis.get(busy_key)
            if _lock and _lock.decode() == value:
                result = self.redis.delete(busy_key)
                self.logger.info(f"{self.login_data['id']} 删除Lock {busy_key}, result: {result}")
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('del_lock 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    def login_off(self):
        try:
            # 删除hash和set，退出
            self.redis.zrem(self.set_key, self.login_data['id'])
            self.redis.hdel(self.hash_key, self.login_data['id'])
            self.redis.delete(f'upi_active_payment:{self.login_data['id']}') # 结束upi激活的流程
            self.redis.hdel(f'{self.name}_device', self.login_data['id']) # 删除hash里面的设备值，防止下一次会发送短信失败
            self.sendMsg('push_payment_information', False, 'Login failed and exit')  # 退出登录进行通知(通知payment状态信息)
            self.on_off(0)  # 下线接单
            self.callbackStatus()  # 回调status,置payment_id的status为0
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('login_off 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))

    def on_off(self, _on=1):
        self.logger.info(f"{self.login_data['id']} on_off(_on={_on}) 处理上下线")
        try:
            if _on == 1:
                self.redis.delete('kick_off_{}'.format(self.login_data['id']))
                # 放入接单集合
                self.redis.sadd('payment_online_ds', self.login_data['id'])
                self.redis.sadd('payment_online_df', self.login_data['id'])
                self.redis.lrem('payment_active_{}'.format(self.login_data['qr_channel']), 0, self.login_data['id'])
                self.redis.lpush('payment_active_{}'.format(self.login_data['qr_channel']), self.login_data['id'])
                # self.sendMsg('push_payment_information', True, 'Login success')  # 登录成功通知
                # self.sendMsg(PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(), True, 'Login success')  # 登录成功通知
                self.logger.info(f"{self.login_data['id']}, {self.list_key} 上线接单： {self.login_data['id']}")
                # self.read_cache('on_off(1)')
                return True
            # 防止代收派单的时候，协议爬取同时操作，导致payment id无法下线
            self.redis.setex('kick_off_{}'.format(self.login_data['id']), 60 * 20, 1)
            # 解除接单集合
            self.redis.srem('payment_online_ds', self.login_data['id'])
            self.redis.srem('payment_online_df', self.login_data['id'])
            self.redis.lrem('payment_active_{}'.format(self.login_data['qr_channel']), 0, self.login_data['id'])
            # self.sendMsg('push_payment_information', False, 'Login failed and quit')  # 退出登录进行通知
            # self.sendMsg(PaymentLoginProgress.STATUS_OF_LOGIN.name.lower(), False, 'Login failed and quit')  # 退出登录进行通知
            self.logger.error(f"{self.login_data['id']}, {self.list_key} 下线接单： {self.login_data['id']}")
            # self.read_cache('on_off()')
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('on_off 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    def update_key(self):
        try:
            # 更新集合和hash里的值
            self.redis.hset(self.hash_key, self.login_data['id'], simplejson.dumps(self.login_data))
            self.redis.zadd(self.set_key, {self.login_data['id']: int(time.time())})
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('update_key() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))

    def make_request(self, method, url, headers=None, params=None, data=None, json_data=None, proxies=None):
        self.logger.info('请求 {method} {url}, params:{params} data:{data} json_data:{json_data}  代理： {proxies}'.format(method=method, url=url, params=params, data=data, json_data=json_data, proxies=proxies))
        try:
            response = None
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params, proxies=proxies, verify=False, allow_redirects=True, timeout=(10, 10))
            elif method.upper() == 'POST':
                if data != None:
                    response = self.session.post(url, headers=headers, data=data, proxies=proxies, verify=False, allow_redirects=True, timeout=(10, 10))
                elif json_data != None:
                    response = self.session.post(url, headers=headers, json=json_data, proxies=proxies, verify=False, allow_redirects=True, timeout=(10, 10))
                elif data == None and json_data == None:
                    response = self.session.post(url, headers=headers, proxies=proxies, verify=False, timeout=(10, 10))
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
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{self.login_data['id']}, make_request 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            return False
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

    # 打印所有的缓存,比较耗性能,生产环境可注释掉
    def read_cache(self, source):
        self.logger.info(f"{self.login_data['id']}, source: {source} 开始读取业务缓存")
        try:
            cache_key_lock = f'{self.name}_operate_{self.login_data['id']}'
            cache_key_login_on = f'login_on_{self.name}_{self.login_data['id']}'
            cache_key_upi_active_payment = f'upi_active_payment:{self.login_data['id']}'
            cache_key_payment_online_ds = f'payment_online_ds'
            cache_key_payment_online_df = f'payment_online_df'
            cache_key_payment_active_qr_channel = f'payment_active_{self.login_data['qr_channel']}'
            cache_key_kick_off = f'kick_off_{self.login_data['id']}'
            cache_key_device = f'{self.name}_device'

            self.logger.info(f"{self.login_data['id']}, read_cache() key: {self.set_key}, 成员 {self.login_data['id']}, score: {self.redis.zscore(self.set_key, self.login_data['id'])}, ttl: {self.redis.ttl(self.set_key)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {self.hash_key}, 成员 {self.login_data['id']}, hash value: {self.redis.hget(self.hash_key, self.login_data['id'])}, ttl: {self.redis.ttl(self.hash_key)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_lock}, value: {self.redis.get(cache_key_lock)}, ttl: {self.redis.ttl(cache_key_lock)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_login_on}, value: {self.redis.get(cache_key_login_on)}, ttl: {self.redis.ttl(cache_key_login_on)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_upi_active_payment}, value: {self.redis.get(cache_key_upi_active_payment)}, ttl: {self.redis.ttl(cache_key_upi_active_payment)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_payment_online_ds}, 成员: {self.login_data['id']}, 是否在set集合中 {self.redis.sismember(cache_key_payment_online_ds, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_payment_online_ds)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_payment_online_df}, 成员: {self.login_data['id']}, 是否在set集合中 {self.redis.sismember(cache_key_payment_online_df, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_payment_online_df)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_payment_active_qr_channel}, 成员: {self.login_data['id']}, 是否在list列表中 {self.login_data['id'] in self.read_redis_list(cache_key_payment_active_qr_channel)}, ttl: {self.redis.ttl(cache_key_payment_active_qr_channel)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {cache_key_kick_off}, value: {self.redis.get(cache_key_kick_off)}, ttl: {self.redis.ttl(cache_key_kick_off)}")
            self.logger.info(f"{self.login_data['id']}, read_cache() key: {self.hash_key}, 成员 {self.login_data['id']}, hash value: {self.redis.hget(cache_key_device, self.login_data['id'])}, ttl: {self.redis.ttl(cache_key_device)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('read_cache 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))

    # 打印集合中所有的元素,生产环境可注释掉
    def read_zset(self, key):
        # 获取有序集合中的所有元素及其分数
        # withscores=True 表示返回元素及其分数
        elements_with_scores = self.redis.zrange(key, 0, -1, withscores=True)
        # 将元素和分数存储到字典中
        result_dict = {element.decode(): score for element, score in elements_with_scores}
        self.logger.info(f"read_zset() zset key: {key},共{len(result_dict)}个 value: {result_dict}")

    # 获取payment_id的android_id, 与设备相关的参数可以放此
    def get_device(self, payment_id):
        if self.redis.hexists(f'{self.name}_device', payment_id):
            device = self.redis.hget(f'{self.name}_device', payment_id)
            device = simplejson.loads(device.decode())
            if device['time'] + self.device_timeout > int(time.time()):
                # 未过期
                self.login_data['android_id'] = device['android_id']
                time_left = device['time'] + self.device_timeout - int(time.time())
                self.logger.info(f"{payment_id}, android_id未过期：{device['android_id']},剩余时间为{time_left}s")
            else:
                # 已过期
                device['android_id'] = self.generate_android_id()
                self.login_data['android_id'] = device['android_id']
                device['time'] = int(time.time())
                self.redis.hset(f'{self.name}_device', payment_id, simplejson.dumps(device))
                self.logger.info(f"{payment_id}, android_id已过期：{device['android_id']},重新建立,剩余时间为{self.device_timeout} s")
        else:
            device = dict()
            device['android_id'] = self.generate_android_id()
            self.login_data['android_id'] = device['android_id']
            device['time'] = int(time.time())
            self.redis.hset(f'{self.name}_device', payment_id, simplejson.dumps(device))
            self.logger.info(f"{payment_id}, 新建：{device['android_id']},剩余时间为{self.device_timeout} s")
        return True

    @staticmethod
    def generate_android_id():
        """Generate a random 16-character Android ID."""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(16))

    def get_session(self, force=True):
        # force 为强制更新
        if self.local_mock:
            return False

        # 先判断session是否过期,不过期,则直接返回
        if 'session_id' in self.login_data and 'session_id_time' in self.login_data and force is False:
            if self.login_data['session_id_time'] + self.session_id_timeout > int(time.time()):
                # 未过期,直接使用
                return True

        """Obtain a new session ID and identifier from the server."""
        url = "https://jiopay.jpb.jio.com/papigateway/getSession/v2"
        payload_dict = {
            "data": f"{random.random()}|7781537675402928",
            "versionNo": self.versionNo,
            "platform": "ANDROID",
            "appChannel": "jio-finance"
        }
        payload = json.dumps(payload_dict)
        headers = self.get_standard_headers()
        self.logger.info(f"{self.login_data['id']}, get_session(): 发起请求：{url}, headers: {headers}, data: {payload}, proxies:{self.login_data['socks_ip']}")
        response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])

        """记录响应的详细信息"""
        self.response_logger.log_response(response)

        if response is None:
            self.logger.error(f"{self.login_data['id']}, get_session() 方法响应失败")
            return False
        if not 200 <= response.status_code < 300:
            self.logger.error(f"{self.login_data['id']}, get_session() 方法失败,响应码： {response.status_code}，原因：{response.text}")
            return False

        self.logger.info(f"{self.login_data['id']}, get_session() 方法 响应: {response.text}")
        response_data = response.json()
        # 即使是200的status code也是,有可能 sessionId 为null
        if response_data["sessionId"] is None or not response_data["sessionId"]:
            self.logger.error(f"{self.login_data['id']}, get_session() 方法失败,sessionId为空： {response.status_code}，原因：{response.text}")
            return False

        self.login_data['session_id_time'] = int(time.time())
        self.logger.info(f"old session_id: {self.login_data['session_id'] if 'session_id' in self.login_data else 'None'}, new session_id: {response_data['sessionId']}")
        self.login_data['session_id'] = response_data["sessionId"]
        if 'identifier' not in self.login_data:
            self.login_data['identifier'] = response_data["identifier"]
            self.logger.info(f"{self.login_data['id']}, get_session() 获取session_id 成功, Session ID: {self.login_data['session_id']}, Identifier: {self.login_data['identifier']}")

        return True

    # 发送OTP
    def get_sendOTP(self):
        try:
            # 超时10分钟，舍去
            if self.login_data['time'] < int(time.time()) - self.order_time_out:
                self.logger.error(f"{self.login_data['id']}, {self.list_key} sendOTP超时，登出:" + simplejson.dumps(self.login_data))
                self.sendMsg('send_otp', False, 'otp sending failed, timeout')  # 获取otp失败进行通知
                self.login_off()
                return 'logout'

            # 获取session id 30分钟有效期 爬取账单时,identifier必须是登录之后返回的那个值，不能从get_session里面获取
            get_session = self.get_session()
            if not get_session:
                time.sleep(0.5)
                get_session = self.get_session()
            if not get_session:
                self.login_data['try_sendOTP'] = 1 if 'try_sendOTP' not in self.login_data else self.login_data['try_sendOTP'] + 1
                self.logger.error(f"{self.login_data['id']} get_sendOTP(), get_session()失败,try_sendOTP失败次数:{self.login_data['try_sendOTP']}")
                if 'try_sendOTP' in self.login_data and self.login_data['try_sendOTP'] > self.try_sendOTP_limit:
                    # 下线接单
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,get_sendOTP(), get_session()失败,try_sendOTP失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type='send_otp', status=False, value="Failed to get the sessionId.")  # 退出登录进行通知
                    return 'logout'
                return False

            sendOTP = self.sendOTP()
            if sendOTP['is_success'] is False:
                time.sleep(0.5)
                sendOTP = self.sendOTP()
            if sendOTP['is_success'] is False:
                self.login_data['try_sendOTP'] = 1 if 'try_sendOTP' not in self.login_data else self.login_data['try_sendOTP'] + 1
                self.logger.error(f"{self.login_data['id']} ,get_sendOTP(), sendOTP()失败, try_sendOTP失败次数:{self.login_data['try_sendOTP']}")
                if 'try_sendOTP' in self.login_data and self.login_data['try_sendOTP'] > self.try_sendOTP_limit:
                    # 下线接单
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,sendOTP()失败,try_sendOTP失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type='send_otp', status=False, value=sendOTP)  # 退出登录进行通知
                    return 'logout'
                return False

            self.login_data['time'] = int(time.time())
            # 发送OTP成功
            self.sendMsg('send_otp', True, None)
            self.login_data['status'] = 'grabOTP'

            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_sendOTP 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

    # 原 send_otp
    def sendOTP(self):
        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            """Send OTP to the specified phone number."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/otp/send"
            data = json.dumps({
                "mobileNumber": self.login_data['phone'],
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
            self.logger.info(f"{self.login_data['id']}, sendOTP(): phone_number: {self.login_data['phone']}, 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, sendOTP() 方法响应失败")
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, sendOTP() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, sendOTP() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, sendOTP() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, sendOTP() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                # 请求也是不成功的
                return result

            self.logger.info(f"{self.login_data['id']}, sendOTP(): phone_number: {self.login_data['phone']} OTP发送成功")
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f"{self.login_data['id']}, sendOTP(): phone_number: {self.login_data['phone']} 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}")
            result['error_message'] = error_message
        return result

    # 原 call_api_server
    def sendMsg(self, type: str = "", status=False, value=None):
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

                return self.notify(url, publish_data)

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
                return self.notify(url, publish_data)

            elif type == 'push_payment_information':
                # 通知payment状态
                url = self.domain + '/v1/websocket/push_payment_information'
                publish_data = {
                    'id': self.login_data['id']
                }
                if not self.notify(url, publish_data):
                    return False
                url = self.domain + '/v1/websocket/push_message_to_user'
                publish_data = {
                    'id': self.login_data['partner_id'],
                    'message': value
                }
                return self.notify(url, publish_data)

            elif type == 'push_message_to_user':
                url = self.domain + '/v1/websocket/push_message_to_user'
                publish_data = {
                    'id': self.login_data['partner_id'],
                    'message': value
                }
                return self.notify(url, publish_data)

            elif type == 5:
                url = self.domain + '/v1/websocket/payment_bind_upi_success'
                if status == 0:
                    url = self.domain + '/v1/websocket/push_cancel_payment_get_upi'
                publish_data = {
                    'id': self.login_data['id']
                }
                return self.notify(url, publish_data)

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

                return self.notify(url, publish_data)

            return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('sendMsg 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

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
            # 'Cache-Control': 'no-cache',
            # 'Pragma': 'no-cache',
            'appChannel': 'jio-finance'
        }

    # 通知前端 原 call_api
    def notify(self, url, publish_data):
        try:
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
            }
            self.logger.info(f"url: {url}, publish_data: {publish_data}, headers: {headers}")
            res = self.retry_make_request("POST", url=url, headers=headers, params=None, data=publish_data, json_data=None, proxies=None)
            if res is None:
                self.logger.error(f"{self.login_data['id']}, 发送{self.list_key} 通知url：{json.dumps(publish_data)} 结果：None")
                return False
            if not 200 <= res.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, 发送{self.list_key} 通知url：{simplejson.dumps(publish_data)} 结果：{res.text}")
                return False
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('notify 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    # 调用API接口 /order/Success 用以修改status状态 原 call_api_order_success
    def send(self, orders_send):
        result = {"is_success": False}
        try:
            url = self.domain + '/order/Success'
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            }
            self.logger.info(f"{self.login_data['id']},send()发起请求：{url}, headers: {headers}, data: {orders_send}")
            res = self.retry_make_request("POST", url=url, headers=headers, params=None, data=orders_send, json_data=None, proxies=None)
            if res is None:
                error_message = f"error:{self.login_data['id']}, send {self.list_key}, callback message：None"
                self.logger.error(error_message)
                result['error_message'] = error_message
                return result
            self.logger.info(f"{self.login_data['id']}, 发送{self.list_key}回调信息：{res.text}")
            _res = simplejson.loads(res.text)

            # 如果是10025 upi重复，则直接下线
            if 'type' in orders_send and orders_send['type'] == 'UPI' and _res['code'] == 10025:
                orders_send['id'] = orders_send['payment_id']
                # 通知监控一键下线
                _key3 = 'login_off_realtime_{}_{}'.format(self.name, orders_send['id'])
                self.redis.set(_key3, 1, 60)
                self.sendMsg('push_payment_information', False, 'upi already exist')  # upi重复通知
                self.logger.info(f"{self.login_data['id']}, {self.list_key} 更新upi重复，下线:{self.login_data['id']}, 结果：{res.text}")

            if res and (_res['code'] == 100):
                result["is_success"] = True
                return result
            else:
                error_message = f"payment_id: {self.login_data['id']}, 请求{url}失败：{orders_send}"
                result["error_code"] = _res['code']
                result["error_message"] = error_message
                return result
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = f"send() 脚本运行错误: {e}\n{''.join(tb_str)}\n{simplejson.dumps(self.login_data)}"
            self.logger.error(error_message)
            result["error_message"] = error_message
            return result

    # 用以修改payment_id的status状态 原 set_payment_status0
    def callbackStatus(self):
        try:
            # status状态修改
            orders_send = {
                'type': 'status',
                'bank_name': self.name,
                'payment_id': self.login_data['id'],
                'partner_id': self.login_data['partner_id'],
                'status': 0
            }
            if_send = self.send(orders_send)
            if if_send['is_success'] is False:
                time.sleep(0.5)
                if_send = self.send(orders_send)
            if if_send['is_success'] is True:
                self.logger.info(f"payment_id: {self.login_data['id']}, status状态修改成功：{simplejson.dumps(orders_send)}")
            else:
                self.logger.info(f"payment_id: {self.login_data['id']}, status状态修改失败：{simplejson.dumps(orders_send)}")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{self.login_data['id']}, callbackStatus 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            return False

    # 检测otp
    def verify_otp(self):
        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            """Verify the OTP received on the phone number."""
            url = "https://jiopay.jpb.jio.com/papigateway/v1/l1auth/otp/verify"
            data = json.dumps({
                "mobileNumber": self.login_data['phone'],
                "referredBy": "",
                "otp": str(self.login_data['otp']),
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
            self.logger.info(f"{self.login_data['id']}, verify_otp(): phone_number: {self.login_data['phone']}, 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)
            self.readResponseType(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, verify_otp() 方法响应失败")
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, verify_otp() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                # 失败响应码： 400，原因：{'responseCode': 'B102', 'responseMessage': 'Invalid OTP entered! Please try again'}
                # 失败响应码： 401，原因：{"payload":{"responseCode":"-1","responseMsg":"Invalid SessionId..."},"context":{"sessionId":"24bcaad7-008f-423d-b53e-545dc6350fa9","encryption":null}}
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, verify_otp() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, verify_otp() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, verify_otp() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            self.login_data['jtoken'] = response_data["jtoken"]
            self.logger.info(f"payment_id: {self.login_data['id']}, verify_otp(),OTP Verified. JToken: {self.login_data['jtoken']}")
            result['is_success'] = True
            # 保存 jtoken 到redis
            device = self.redis.hget(f'{self.name}_device', self.login_data['id'])
            device = simplejson.loads(device.decode())
            device['android_id'] = self.login_data['android_id']
            device['time'] = int(time.time())
            device['identifier'] = self.login_data['identifier']
            device['jtoken'] = self.login_data['jtoken']
            self.redis.hset(f'{self.name}_device', self.login_data['id'], simplejson.dumps(device))
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('verify_otp 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
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
            self.logger.error(f"get_response_data() 解析response遇到问题，e: {e}")
            response_data['responseMessage'] = "decrypt response message error"
            return False
        return response_data

    # 原 验证OTP check_otp
    def get_grabOTP(self):
        result = {"is_success": False}
        try:
            # 读取OTP
            grabOTP = self.grabOTP()
            if not grabOTP:
                if self.login_data['time'] < int(time.time()) - self.order_time_out:
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} 获取otp超时，登出:" + simplejson.dumps(self.login_data))
                    self.sendMsg('push_message_to_user', False, 'grab otp failed, timeout')  # 退出登录进行通知
                    self.login_off()
                    return 'logout'
                return result

            # 接收OTP成功
            self.logger.info(f"{self.login_data['id']} 接收otp成功:{grabOTP}")
            self.login_data['otp'] = grabOTP

            result_verify_otp = self.verify_otp()
            if result_verify_otp['is_success'] is False and result_verify_otp['error_code'] in [401, 403]:
                if not self.get_session(True):  # 强制更新 session_id
                    self.login_data['try_verify_otp'] = 1 if 'try_verify_otp' not in self.login_data else self.login_data['try_verify_otp'] + 1
                    return result
                time.sleep(0.5)
                result_verify_otp = self.verify_otp()
            if result_verify_otp['is_success'] is False:
                error_code =  None if 'error_code' not in result_verify_otp else result_verify_otp['error_code']
                error_message = None if 'error_message' not in result_verify_otp else result_verify_otp['error_message']
                if error_code in ['B102', 'B100']:
                    self.sendMsg(PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(), False, result_verify_otp)
                self.logger.error(f"{self.login_data['id']}, {self.list_key} get_grabOTP(),验证OTP 错误, error_code: {error_code}, error_message: {error_message}")
                # 下线接单
                self.on_off(0)
                result = result_verify_otp
                # 超过次数直接退出
                self.login_data['try_verify_otp'] = 1 if 'try_verify_otp' not in self.login_data else self.login_data['try_verify_otp'] + 1
                self.logger.error(f"{self.login_data['id']} get_grabOTP()失败, try_verify_otp失败次数:{self.login_data['try_verify_otp']}")
                if 'try_verify_otp' in self.login_data and self.login_data['try_verify_otp'] > self.try_verify_otp_limit:
                    # 登出
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,get_grabOTP()失败, try_verify_otp失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type='send_otp', status=False, value="Failed to verify otp.")  # 退出登录进行通知
                    return 'logout'
            else:
                self.login_data['time'] = int(time.time())
                result['is_success'] = True
                self.login_data['status'] = 'device_check' # 验证otp之后,就进入device_check,检测为 OTP就需要发送服务短信,如果不是,就可以直接表面登录成功,可以爬取账单和upi
                self.sendMsg(PaymentLoginProgress.STATUS_OF_VERIFY_OTP.name.lower(), True, result_verify_otp)
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_grabOTP 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

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
            self.logger.error('grabOTP 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

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
            self.logger.info(f"{self.login_data['id']}, device_check(): 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, device_check() 方法响应失败")
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, device_check() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, device_check() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, device_check() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, device_check() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']
            result['setUpMode'] = response_data["setUpMode"]
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('device_check() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

    # 设备检查 原device_check()
    def get_device_check(self):
        if self.local_mock:
            return {"is_success": True}

        result = {"is_success": False}
        try:
            # 超时10分钟，舍去
            if self.login_data['time'] < int(time.time()) - self.order_time_out:
                self.logger.error(f"{self.login_data['id']}, {self.list_key} get_device_check超时，登出:" + simplejson.dumps(self.login_data))
                self.sendMsg('push_message_to_user', False, 'get_device_check failed, timeout')  # 退出登录进行通知
                self.login_off()
                return 'logout'

            # 获取session id 30分钟有效期 爬取账单时,identifier必须是登录之后返回的那个值，不能从get_session里面获取
            get_session = self.get_session()
            if not get_session:
                time.sleep(0.5)
                get_session = self.get_session()
            if not get_session:
                self.login_data['try_device_check'] = 1 if 'try_device_check' not in self.login_data else self.login_data['try_device_check'] + 1
                self.logger.error(f"{self.login_data['id']} get_device_check, get_session()失败,try_device_check_limit 失败次数:{self.login_data['try_device_check']}")
                if 'try_device_check' in self.login_data and self.login_data['try_device_check'] > self.try_device_check_limit:
                    # 下线接单
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,get_device_check, get_session()失败,try_device_check 失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type='send_otp', status=False, value="Failed to device_check.")  # 退出登录进行通知
                    return 'logout'
                return result

            result_device_check = self.device_check()
            if result_device_check['is_success'] is False:
                time.sleep(0.5)
                result_device_check = self.device_check()
            if result_device_check['is_success'] is False:
                error_code = None if 'error_code' not in result_device_check else result_device_check['error_code']
                error_message = None if 'error_message' not in result_device_check else result_device_check['error_message']
                self.logger.error(f"{self.login_data['id']}, {self.list_key} get_device_check(),验证device 错误, error_code: {error_code}, error_message: {error_message}")
                # 下线接单
                self.on_off(0)
                result = result_device_check
                # 超过次数直接退出
                self.login_data['try_device_check'] = 1 if 'try_device_check' not in self.login_data else self.login_data['try_device_check'] + 1
                self.logger.error(f"{self.login_data['id']} ,get_device_check()失败, try_device_check 失败次数:{self.login_data['try_device_check']}")
                if 'try_device_check' in self.login_data and self.login_data['try_device_check'] > self.try_device_check_limit:
                    # 下线接单
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,get_device_check()失败,try_device_check 失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type='send_otp', status=False, value="Failed to device_check.")  # 退出登录进行通知
                    return 'logout'
            else:
                self.login_data['time'] = int(time.time())
                result['is_success'] = True
                if result_device_check['setUpMode'] == 'OTP': # 需要发送短信来进一步验证
                    self.login_data['status'] = 'send_sms'
                else:
                    self.login_data['status'] = 'grabstatement'  # setUpMode 为 OBS 直接登录成功,可以爬取账单和upi
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_device_check() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

    # 获取发送短信的目标号码、指定内容，并通知api服务 原 get_send_number_content_send_api
    def get_send_sms(self):
        try:
            # 超时10分钟，舍去
            if self.login_data['time'] < int(time.time()) - self.order_time_out:
                self.logger.error(f"{self.login_data['id']}, {self.list_key} get_send_sms() 超时，登出:" + simplejson.dumps(self.login_data))
                self.sendMsg('push_message_to_user', False, 'get send number and content timeout')  # 退出登录进行通知
                self.login_off()
                return 'logout'

            result_send_sms = self.send_sms()
            if result_send_sms['is_success'] is False:
                time.sleep(0.5)
                result_send_sms = self.send_sms()
            if result_send_sms['is_success'] is False:
                error_code = None if 'error_code' not in result_send_sms else result_send_sms['error_code']
                error_message = None if 'error_message' not in result_send_sms else result_send_sms['error_message']
                self.logger.error(f"{self.login_data['id']}, {self.list_key} get_send_sms(),获取短信内如 错误, error_code: {error_code}, error_message: {error_message}")
                # 下线接单
                self.on_off(0)
                # 超过次数直接退出
                self.login_data['try_send_sms'] = 1 if 'try_send_sms' not in self.login_data else self.login_data['try_send_sms'] + 1
                self.logger.error(f"{self.login_data['id']} ,get_send_sms()失败, try_send_sms 失败次数:{self.login_data['try_send_sms']}")
                if 'try_send_sms' in self.login_data and self.login_data['try_send_sms'] > self.try_send_sms_limit:
                    # 登出
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,get_send_sms()失败,try_send_sms 失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type='get_send_sms_info', status=False, value=result_send_sms) # 退出登录进行通知
                    return 'logout'
                return False
            else:
                self.login_data['time'] = int(time.time())
                # 通知api服务获取到的内容，发送短信的目标号码、指定内容
                res = self.sendMsg(type='get_send_sms_info', status=True, value=result_send_sms)
                if not res:
                    self.sendMsg(type='get_send_sms_info', status=True, value=result_send_sms)
                # 进入下一步等待客户端通知已发送短信
                self.login_data['status'] = 'wait_client_send_sms'
                return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_send_sms 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

    # 获取发送短信的目标号码、指定内容 原 get_send_number_content
    def send_sms(self):
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
            self.logger.info(f"{self.login_data['id']}, send_sms(), 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, send_sms() 方法响应失败")
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, send_sms() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, send_sms() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, send_sms() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, send_sms() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                # 请求也是不成功的
                return result

            result['receive_sms_number'] = response_data["longCode"]
            result['receive_sms_content'] = response_data["code"]
            self.login_data['receive_sms_number'] = result['receive_sms_number']
            self.login_data['receive_sms_content'] = result['receive_sms_content']

            self.logger.info(f"{self.login_data['id']}, receive_sms_number: {result['receive_sms_number']}")
            self.logger.info(f"{self.login_data['id']}, receive_sms_content: {result['receive_sms_content']}")
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('send_sms() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            result['error_message'] = error_message
        return result

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
                self.logger.info(f"{self.login_data['id']}, get_status_client_send_sms() -> True 客户端已发送短信")
                self.redis.lrem(_hash_key, 0, check_elements)
                return True
            else:
                return False
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_status_client_send_sms() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            return False

    # 向银行检查短信发送状态 原 outboundsms_check
    def verify_sms(self):
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
            headers = self.get_standard_headers()
            self.logger.info(f"{self.login_data['id']}, verify_sms(), 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, verify_sms() 方法响应失败")
                result['error_message'] = "verify_sms fail"
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, verify_sms() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, verify_sms() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, verify_sms() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, verify_sms() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                # 请求也是不成功的
                return result
            self.logger.info(f"payment_id: {self.login_data['id']}, verify_sms(),成功. JToken: {self.login_data['jtoken']} ; {response_data["jtoken"]}")
            if response_data["jtoken"]: # 有可能 jtoken 是空的，防止赋值空的 {'responseCode': '0', 'responseMessage': 'SUCCESS', 'mobileNumber': '919352947931', 'token': None, 'setUpMode': 'OTP', 'loginNumberMismatch': False, 'jtoken': None, 'jToken': None}
                self.login_data['jtoken'] = response_data["jtoken"]
            result['is_success'] = True
            # 保存 jtoken 到redis
            device = self.redis.hget(f'{self.name}_device', self.login_data['id'])
            device = simplejson.loads(device.decode())
            device['android_id'] = self.login_data['android_id']
            device['time'] = int(time.time())
            device['identifier'] = self.login_data['identifier']
            device['jtoken'] = self.login_data['jtoken']
            self.redis.hset(f'{self.name}_device', self.login_data['id'], simplejson.dumps(device))
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_status_client_send_sms() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            result['error_message'] = error_message
        return result

    # 获取upi 原get_upi
    def grabUpi(self):
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
            headers = self.get_standard_headers()
            self.logger.info(f"{self.login_data['id']}, grabUpi(), 发起请求：{url}, headers: {headers}, data: {payload}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, grabUpi() 方法响应失败")
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, grabUpi() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, grabUpi() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, grabUpi() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, grabUpi() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                return result

            linked_accounts_keys = list(response_data.get("linkedAccountsMap", {}).keys()) # 这个有对应绑定的卡
            upi_list = [] if 'upi_list' not in self.login_data else self.login_data['upi_list']
            for upi in linked_accounts_keys:
                self.logger.info(f"payment_id: {self.login_data['id']}, get_upi() ,获取upi成功,upi: {upi}")
                if upi not in upi_list :
                    upi_list.append(upi)
            upi = linked_accounts_keys[0]  # 只获取第一个的upi
            # upi有更新时
            if 'upi' in self.login_data and upi != self.login_data['upi']:
                self.logger.info(f"{self.login_data['id']}, get_upi(),upi更改,upi: {upi}")
            self.login_data['upi'] = upi
            self.login_data['upi_list'] = upi_list
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'grabUpi() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            result['error_message'] = error_message
        return result

    # 抓取账单 原 transaction_history
    def getBills(self):
        if self.local_mock:
            return {"is_success": True}

        self.logger.info(f"payment_id: {self.login_data['id']}, getBills(upi = {self.login_data['upi']})")
        result = {"is_success": False}
        try:
            """Retrieve transaction history for the specified VPA."""
            url = "https://jiopay.jpb.jio.com/papigateway/v2/upi/prf/transaction/composite/history"
            data = json.dumps({"virtualPaymentAddress": self.login_data['upi'], "rowNum": 20})
            payload = json.dumps({
                "context": {
                    "encryption": True,
                    "sessionId": self.login_data['session_id'],
                    "encryptionV2": True
                },
                "payload": self.encrypt_message(data, self.login_data['session_id'].encode())
            })
            headers = self.get_standard_headers()
            self.logger.info(f"{self.login_data['id']}, getBills(), 发起请求：{url}, headers: {headers}, data: {data}, proxies: {self.login_data['socks_ip']}")
            response = self.retry_make_request("POST", url=url, headers=headers, params=None, data=payload, json_data=None, proxies=self.login_data['socks_ip'])
            """记录响应的详细信息"""
            self.response_logger.log_response(response)

            if response is None:
                self.logger.error(f"{self.login_data['id']}, getBills() 方法响应失败")
                return result
            if not 200 <= response.status_code < 300:
                self.logger.error(f"{self.login_data['id']}, getBills() 方法失败,响应码： {response.status_code}，原因：{response.text}")
                result['error_code'] = response.status_code
                result['error_message'] = response.text
                if response.text:
                    response_data = self.get_response_data(response)
                    self.logger.error(f"{self.login_data['id']}, getBills() 方法失败,响应码： {response.status_code}，原因：{response_data}")
                return result

            self.logger.info(f"{self.login_data['id']}, getBills() 方法 响应: {response.text}")
            response_data = self.get_response_data(response)
            self.logger.info(f"{self.login_data['id']}, getBills() 方法 解密之后响应: {response_data}")

            result['error_code'] = response_data['responseCode']
            result['error_message'] = response_data['responseMessage']

            if response_data['responseCode'] != "0":
                # 请求也是不成功的
                # {"transactionHistoryList":null,"responseCode":"-1","responseMessage":"We are unable to process your request at this moment. Please try again later| S041"}
                return result

            transactionHistoryList = response_data["transactionHistoryList"]
            self.logger.info(f"{self.login_data['id']}, 爬取交易记录：{transactionHistoryList}")
            if not transactionHistoryList:
                result['transaction_history_list'] = []
            else:
                # 按照交易时间正序排序 可不用排序
                transactionHistoryList = sorted(
                    transactionHistoryList,
                    key=lambda x: datetime.strptime(x['transactionDate'], '%Y-%m-%dT%H:%M:%S')
                )
                result['transaction_history_list'] = transactionHistoryList
            result['is_success'] = True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error(f'{self.login_data['id']}, getBills() 脚本运行错误{e}\n{error_message}\n{simplejson.dumps(self.login_data)}')
            result['error_message'] = error_message
        return result

    # 检测交易是否已回调过的, 原 is_transaction_synced
    def if_callback(self, utr: str) -> bool:
        """检测交易是否已回调过的"""
        # 判断有序集合中是否存在元素
        if self.redis.zscore(self.if_callback_key, f"{self.login_data['id']}_{utr}") is not None:
            # 已经回调过
            return True
        else:
            return False

    # 将账单记录标记为已回调过的,原 mark_transaction_synced
    def mark_transaction_callback(self, utr: str):
        self.redis.zadd(self.if_callback_key, {f"{self.login_data['id']}_{utr}": int(time.time())})

    def check_client_send_sms(self):
        try:
            # 超时10分钟，舍去
            if self.login_data['time'] < int(time.time()) - self.check_client_send_sms_time_out:
                self.logger.error(f"{self.login_data['id']}, {self.list_key} check_client_send_sms() 超时，登出:" + simplejson.dumps(self.login_data))
                self.sendMsg('push_message_to_user', False, 'check_client_send_sms timeout')  # 退出登录进行通知
                self.login_off()
                return 'logout'

            # 读取客户端发送短信的状态
            result_get_status_client_send_sms = self.get_status_client_send_sms()
            if result_get_status_client_send_sms is False:
                self.logger.error(f"{self.login_data['id']}, 客户端未发送短信")
                return False

            self.login_data['time'] = int(time.time())
            # 进入下一步检测发送的短信是否通过系统验证
            self.login_data['status'] = 'verify_sms'
            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('check_client_send_sms 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

    # 检查协议登录状态 原 check_signin_status
    def check_login(self):
        try:
            # 超时10分钟，舍去
            if self.login_data['time'] < int(time.time()) - self.order_time_out:
                self.logger.error(f"{self.login_data['id']}, {self.list_key} check_login() 超时，登出:" + simplejson.dumps(self.login_data))
                self.sendMsg('push_message_to_user', False, 'check signin status timeout')  # 退出登录进行通知
                self.login_off()
                return 'logout'

            # 向银行检查短信发送状态
            result_verify_sms = self.verify_sms()
            if result_verify_sms['is_success'] is False:
                time.sleep(0.5)
                result_verify_sms = self.verify_sms()
            if result_verify_sms['is_success'] is False:
                # 下线接单
                self.on_off(0)
                # 超过次数直接退出
                self.login_data['try_verify_sms'] = 1 if 'try_verify_sms' not in self.login_data else self.login_data['try_verify_sms'] + 1
                self.logger.error(f"{self.login_data['id']} check_login()失败, try_verify_sms 失败次数:{self.login_data['try_verify_sms']}")
                if 'try_verify_sms' in self.login_data and self.login_data['try_verify_sms'] > self.try_verify_sms_limit:
                    # 登出
                    self.login_off()
                    self.logger.error(f"{self.login_data['id']}, {self.list_key} ,check_login()失败, try_verify_sms 失败太多，登出: {simplejson.dumps(self.login_data)}")
                    self.sendMsg(type=PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), status=False, value=result_verify_sms) # 退出登录进行通知
                    return 'logout'
                return False

            self.login_data['time'] = int(time.time())
            self.login_data['status'] = 'grabstatement' # 改状态为可以抓取账单
            self.logger.info(f"payment_id: {self.login_data['id']}, check_login() 登录成功")
            # 发送登录成功的消息
            res = self.sendMsg(type=PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), status=True, value=result_verify_sms)
            if not res:
                self.sendMsg(type=PaymentLoginProgress.SEND_SMS_CHECK.name.lower(), status=True, value=result_verify_sms)
            # 登录成功，开始首次爬取账单等, 获取个人信息 UPI
            grabstatement = self.grabstatement()
            if isinstance(grabstatement, bool) and grabstatement is True:
                self.on_off()
            # 添加判断在线的key
            _key1 = 'login_on_{}_{}'.format(self.name, self.login_data['id'])
            self.redis.setex(_key1, 11 * 60, 1)
            self.redis.delete(f'upi_active_payment:{self.login_data['id']}')

            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('check_login 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

    # 爬取账单和upi
    def grabstatement(self, if_first_time=False):
        try:
            self.login_data['time'] = int(time.time())
            self.login_data['count'] = 1 if 'count' not in self.login_data else self.login_data['count'] + 1

            # device_check 先进行这个,确保在 sessionId 失效之前,先get sessionId
            get_session = self.get_session()
            if not get_session:
                time.sleep(0.5)
                get_session = self.get_session()
            if not get_session:
                return False

            # 爬取账单之前先 device_check
            result_device_check = self.device_check()
            if result_device_check['is_success'] is False:
                time.sleep(0.5)
                result_device_check = self.device_check()
            if result_device_check['is_success'] is False:
                return False
            if result_device_check['setUpMode'] == 'OTP':  # 需要再次发短信,直接退出
                return 'logout'
            time.sleep(0.5)

            #  爬取upi
            if 'upi_time' not in self.login_data or self.login_data['upi_time'] + self.upi_time < int(time.time()):
                # if 'upi_time' not in self.login_data: # 暂时只爬取一次
                grabUpi = self.grabUpi()
                if grabUpi['is_success'] is False:
                    time.sleep(0.5)
                    grabUpi = self.grabUpi()
                if grabUpi['is_success'] is False:
                    self.login_data['upi_try'] = 1 if 'upi_try' not in self.login_data else self.login_data['upi_try'] + 1
                    self.logger.info(f"{self.login_data['id']} 爬取upi失败：" + simplejson.dumps(self.login_data))
                    self.on_off(0)
                    # self.login_data['upi_try_fail'] = 1  # 标定是否upi爬取失败
                    self.login_data['upi_time'] = int(time.time()) - 4 * 60  # 更新时间，否则爬取失败会一直爬取，约1分钟爬取一次
                    self.login_data['time'] = int(time.time()) - self.time_grab2 + 1 * 60  # 更新时间，爬取upi失败后，约1分钟爬取一次，加快爬取，在限制次数下尝试多次不成功则退出
                    # return False  # 爬取upi失败也要爬取账单
                else:
                    # 发回upi, 写入upi
                    orders_send = {
                        'type': 'UPI',
                        'bank_name': self.name,
                        'payment_id': self.login_data['id'],
                        'partner_id': self.login_data['partner_id'],
                        'upi': self.login_data['upi'],
                    }
                    if_send = self.send(orders_send)
                    if if_send['is_success'] is False:
                        time.sleep(0.5)
                        if_send = self.send(orders_send)
                    if if_send['is_success'] is False:
                        self.on_off(0)
                        self.logger.error(f"{self.login_data['id']} 发送upi失败：" + simplejson.dumps(self.login_data))
                        # return False
                    self.logger.info(f"{self.login_data['id']} 发送upi成功：{grabUpi}")
                    self.login_data['upi_time'] = int(time.time())
                    self.login_data['upi_try'] = 0
                    # self.login_data.pop('upi_try_fail', None)

            self.logger.info(f"{self.login_data['id']} 爬取账单：")
            # 开始爬取账单
            getBills = self.getBills()
            if getBills['is_success'] is False:
                if getBills['error_code'] == '5001':
                    self.login_data['try_count'] = 0
                    self.logger.info(f"{self.login_data['id']},grabstatement(),爬取账单，成功,账单为空, {getBills}")
                    # {'transactionHistoryList': None, 'responseCode': '5001', 'responseMessage': 'No transactions found'}
                    return True

                self.logger.error(f"{self.login_data['id']},grabstatement(),爬取账单失败1, {getBills}")
                # 下线接单
                self.on_off(0)
                self.login_data['time'] = int(time.time()) - self.time_grab2 + 1 * 60  # 更新时间，爬取upi失败后，约1分钟爬取一次，加快爬取，在限制次数下尝试多次不成功则退出
                return False

            self.login_data['try_count'] = 0
            self.logger.info(f"爬取账单，成功 {self.login_data['id']}")
            # 抓取交易记录为空
            if 'transaction_history_list' not in getBills or getBills['transaction_history_list'] is None:
                self.logger.info(f"{self.login_data['id']} 爬取账单为空：" + simplejson.dumps(self.login_data))
                return True

            # 开始检测哪些账单需要回调,根据utr来确认唯一性
            for transaction in getBills['transaction_history_list']:
                utr = transaction['approvalRefNum']
                if 'transactionStatus' not in transaction or transaction['transactionStatus'] != 'SUCCESS':
                    continue
                if if_first_time:
                    # 首次爬取账单, 将账单记录标记为已回调过的
                    self.mark_transaction_callback(utr)
                    continue
                # 检查是否已回调
                if self.if_callback(utr):
                    # self.logger.info(f"{self.login_data['id']}, 交易 {utr} 已回调过，跳过")
                    continue
                self.logger.info(f"{self.login_data['id']}, 准备回调交易 {utr}, {transaction}")
                # 回调
                self.transaction_callback(transaction)
                # 将账单记录标记为已回调过的
                self.mark_transaction_callback(utr)

            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('grabstatement() 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

    # 爬取账单和upi 原 get_profile
    def get_grabstatement(self):
        try:
            # 添加判断在线的key
            _key1 = 'login_on_{}_{}'.format(self.name, self.login_data['id'])
            self.redis.setex(_key1, 11 * 60, 1)

            # 通知监控下线
            _key2 = 'login_off_{}_{}'.format(self.name, self.login_data['id'])
            login_off = self.redis.get(_key2)
            if login_off:  # 180分钟之后才真正下线
                # if int(login_off) + 180*60 < int(time.time()):
                #     # 删除标识在线的key
                #     self.redis.delete(_key1)
                #     self.redis.delete(_key2)
                #     self.logger.error(f"{self.list_key} 180分钟之后通知监控下线，登出:" + simplejson.dumps(self.login_data))
                #     self.login_off()
                #     return 'logout'
                # 下线接单
                self.on_off(0)

            # 通知监控一键下线
            _key3 = 'login_off_realtime_{}_{}'.format(self.name, self.login_data['id'])
            login_off = self.redis.get(_key3)
            if login_off:  # 直接下线
                # 删除标识在线的key
                self.redis.delete(_key1)
                self.redis.delete(_key2)
                self.redis.delete(_key3)
                # 登出
                self.logger.error(f"{self.list_key} 通知监控一键下线，登出:" + simplejson.dumps(self.login_data))
                self.login_off()
                return 'logout'

            grabstatement = False
            #  如果有相关的key，按短时间爬取一次，如果没有，则按长时间一次
            crawl_frequently = self.redis.get('crawl_frequently_{}'.format(self.login_data['id']))
            if crawl_frequently or ('try_count' in self.login_data and self.login_data['try_count'] > 0):
                # 有相关的key或者有重试的，都按指定的最短时间爬取一次
                _time_grab = self.time_grab
            else:
                _time_grab = self.time_grab2
            if 'count' not in self.login_data or self.login_data['time'] < int(time.time()) - _time_grab:
                grabstatement = self.grabstatement()
                if isinstance(grabstatement, bool) and grabstatement is False:
                    self.login_data['try_count'] = 1 if 'try_count' not in self.login_data else self.login_data['try_count'] + 1
                if (isinstance(grabstatement, str) and grabstatement == 'logout') or ('count' in self.login_data and self.login_data['try_count'] > self.try_count_limit):
                    # 删除标识在线的key
                    self.redis.delete(_key1)
                    self.redis.delete(_key2)
                    self.redis.delete(_key3)
                    # 登出
                    self.logger.error(f"{self.list_key} try_count太多，登出:" + simplejson.dumps(self.login_data))
                    self.login_off()
                    return 'logout'

            # 爬取upi失败次数过多
            if 'upi_try' in self.login_data and self.login_data['upi_try'] > self.try_upi_limit:
                # 删除标识在线的key
                self.redis.delete(_key1)
                self.redis.delete(_key2)
                self.redis.delete(_key3)
                # 登出
                # self.login_data['upi_try_fail'] = 1 # 标定是否upi爬取太多失败次数
                self.logger.error(f"{self.list_key} upi_try太多，登出:" + simplejson.dumps(self.login_data))
                self.login_off()
                return 'logout'

            login_off = self.redis.get(_key2)
            if not login_off and isinstance(grabstatement, bool) and grabstatement is True:
                self.on_off()
                # if 'login_if' not in self.login_data:
                #     self.sendMsg('push_payment_information', True, 'Login success')  # 登录成功通知
                #     self.login_data['login_if'] = 1

            return True
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            self.logger.error('get_grabstatement 脚本运行错误{}\n{}\n{}'.format(e, error_message, simplejson.dumps(self.login_data)))
            # 更新集合和hash里的值
            self.update_key()
            return False

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
        try:
            return text.split('@')[0]
        except Exception as e:
            self.logger.info(f"extract_payment_account() 失败 {text}: {str(e)}")
            return ""

    # 原 sync_transaction 回调账单
    def transaction_callback(self, transaction: Dict) -> bool:
        self.logger.info(f"{self.login_data['id']}, transaction_callback(), 开始回调 transaction: {transaction}")
        account = ""
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
                self.logger.error(f"{self.login_data['id']}, transaction_callback() 失败,不支持的交易类型: {transaction}")
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
                'ifsc': str(ifsc).upper(),
                'account': account
            }
            if_send = self.send(orders_send)
            if if_send['is_success'] is False:
                time.sleep(0.5)
                if_send = self.send(orders_send)
            if if_send['is_success'] is True:
                self.logger.info(f"{self.login_data['id']}, transaction_callback 成功：{simplejson.dumps(orders_send)}")
                return True
            else:
                self.logger.info(f"{self.login_data['id']}, transaction_callback 失败：{simplejson.dumps(orders_send)}")
                return False
        except Exception as e:
            self.logger.error(f"回调交易记录失败 {transaction['approvalRefNum']}: {str(e)}")
            return False

    # 清理 if_callback_key 中时间较久的utr ,避免已经回调过的utr数据量过大
    def clean_if_callback_key(self):
        # 设定时间阈值
        threshold = int(time.time()) - self.clean_if_callback_key_time
        # 移除有序集合if_callback_key中，所有时间戳早于threshold的成员
        removed_count = self.redis.zremrangebyscore(self.if_callback_key, '-inf', threshold)
        self.logger.info(f" {self.if_callback_key} 移除过期的utr数据： {removed_count} 个")
        # 后面可添加清理 f'{self.name}_device' 相关的hash key数据

    def main(self):
        try:
            # 生成新的trace_id
            trace_id_filter.trace_id = f"{os.getpid()}_{uuid.uuid4()}"
            
            # 1 先检查list中与hash的比较，是否hash中已有，如果有，则抛弃，如果没有则放置hash和有序集合
            pop_data = self.redis.lpop(self.list_key)
            if not pop_data:
                # 清理 if_callback_key 中时间较久的utr ,避免已经回调过的utr数据量过大
                self.clean_if_callback_key()
                self.logger.error(f"{self.list_key} redis list中没有数据")
                pass
            else:
                self.logger.info(f" {self.list_key} redis list pop数据： {pop_data}")
                pop_data_set = simplejson.loads(pop_data.decode())
                if self.redis.hexists(self.hash_key, pop_data_set['id']):
                    # 如果有，则抛弃
                    self.logger.error(f" {self.hash_key} {pop_data_set['id']} 已存在数据！")
                else:
                    # 如果没有则放置在hash和有序集合
                    self.logger.info(f" {self.hash_key} {pop_data_set['id']} 不存在数据，新登录！")
                    self.redis.hset(self.hash_key, pop_data_set['id'], simplejson.dumps(pop_data_set))
                    # 如果是需要登录的，则可以在此设置分数为0来标明是登录状态,标明优先处理
                    # self.redis.zadd(self.set_key, {pop_data_set['id']: int(time.time())})
                    self.redis.zadd(self.set_key, {pop_data_set['id']: 0})

            # 打印集合中所有的元素,生产环境可注释掉
            self.read_zset(self.set_key)
            # 从有序集合中，获取10S外的成员，限100个
            zrangebyscore_max = int(time.time()) - 10
            members = self.redis.zrangebyscore(self.set_key, 0, zrangebyscore_max, 0, 100)
            if not members:
                self.logger.info(f"{self.set_key} min:0, max:{zrangebyscore_max} set中没有数据")
                time.sleep(2)
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
                    self.logger.error(f"{self.hash_key} {_id} 不存在数据！从set列表{self.set_key}中删除")
                    self.redis.zrem(self.set_key, _id)
                    continue
                else:
                    self.logger.info(f"merbers[{i}], hash_key: {self.hash_key}, login_data: {login_data}")
                    # 存在hash数据，则开始登录或者爬取账单等
                    self.logger.info(f"{_id},尝试获取锁")
                    _lock = self.get_lock(_id)
                    if _lock:
                        self.logger.info(f"{_id}, 获取到锁: {_lock}")
                        # 操作前获取锁
                        self.login_data = simplejson.loads(login_data.decode())
                        # 打印所有的缓存,比较耗性能,生产环境可注释掉
                        # self.read_cache('main() init login_data')
                        # 获取payment_id的android_id
                        self.get_device(_id)
                        # 获取代理ip
                        proxy = self.get_proxies()
                        if not proxy:
                            self.logger.error(f"{self.list_key} {_id} 无代理！")
                            # 删除锁
                            self.del_lock(_id, _lock)
                            continue
                        # 检测是否需要换代理
                        if 'socks_ip' not in self.login_data or not self.login_data['socks_ip']:
                            self.login_data['socks_ip'] = proxy
                        if 'socks_ip' in self.login_data and self.login_data['socks_ip']:
                            self.login_data['socks_ip'] = self.check_proxy()
                        # self.login_data['socks_ip'] = proxy if 'socks_ip' not in self.login_data or not self.login_data['socks_ip'] else self.login_data['socks_ip']

                        self.logger.info(f"{_id}, hash_key: {self.hash_key}, login_data: {self.login_data}")
                        res = None
                        if self.login_data['status'] == 'sendOTP':
                            # 发送otp
                            res = self.get_sendOTP()
                            self.logger.info(f"{self.login_data['id']}, get_sendOTP(), res {type(res)}： {res}")
                            self.read_cache(f'main() sendOTP res: {res}')
                        elif self.login_data['status'] == 'grabOTP':
                            # 输入otp并登录
                            res = self.get_grabOTP()
                            self.logger.info(f"{self.login_data['id']}, get_grabOTP() res {type(res)}： {res}")

                        if self.login_data['status'] == 'device_check': #此处是想直接进入到 device_check 流程,所以不用elif直接另开if,如果是其他可以使用elif走流程
                            res = self.get_device_check()
                            self.logger.info(f"{self.login_data['id']}, get_device_check() res {type(res)}： {res}")

                        if self.login_data['status'] == 'send_sms':  # 此处是想直接进入到 send_sms 流程,所以不用elif直接另开if,如果是其他可以使用elif走流程
                            # 获取要发送的短信的目标号码及内容
                            res = self.get_send_sms()
                            self.logger.info(f"{self.login_data['id']}, get_send_sms() res {type(res)}： {res}")
                        elif self.login_data['status'] == 'wait_client_send_sms':
                            # 检查协议登录状态
                            res = self.check_client_send_sms()
                            self.logger.info(f"{self.login_data['id']}, check_login() res {type(res)}： {res}")

                        if self.login_data['status'] == 'verify_sms': # 此处是想直接进入到 verify_sms 流程,所以不用elif直接另开if,如果是其他可以使用elif走流程
                            # 检查协议登录状态
                            res = self.check_login()
                            self.logger.info(f"{self.login_data['id']}, check_login() res {type(res)}： {res}")
                        elif self.login_data['status'] == 'grabstatement':
                            # 登录成功后爬取upi和账单
                            res = self.get_grabstatement()
                            self.logger.info(f"{self.login_data['id']}, get_grabstatement() res {type(res)}： {res}")

                        # 综上所有的状态都没有,则直接退出
                        if self.login_data['status'] not in ['sendOTP', 'grabOTP', 'device_check', 'send_sms', 'wait_client_send_sms', 'verify_sms', 'grabstatement'] :
                            # status有问题
                            self.logger.error(f"{self.login_data['id']}, {self.list_key} {_id} status存在问题，舍去！")
                            self.login_off()
                            self.read_cache(f'main() status error')

                        if isinstance(res, str) and res == 'logout':
                            # 删除相关的hash和set中的值
                            self.logger.error(f"{self.login_data['id']}, {self.list_key} {_id} 登出，删除相关的hash和set中的值")
                            self.login_off()
                            self.read_cache(f'main() logout')
                        else:
                            # 更新集合和hash里的值
                            self.update_key()
                            # 对检测短信是否发送的时间有要求, 必须放到前面
                            if self.login_data['status'] == 'wait_client_send_sms':
                                self.redis.zadd(self.set_key, {self.login_data['id']: 0})
                            self.read_cache(f'main() True')

                        # 删除锁
                        self.del_lock(_id, _lock)
                    else:
                        self.logger.warning(f"{_id},未获取到锁！")
        except Exception as e:
            tb_str = traceback.format_exc()
            error_message = ''.join(tb_str)
            logging.error('main过程错误： 错误详情：{}\n{}'.format(e, error_message))


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
            logger.error('主脚本运行错误,3秒后重试: id: {} {}\n{}'.format(bank.id, e, error_message))
            # 插入redis，防止非主逻辑内的出错
            bank.redis = redis.Redis(host=conf['redis_host'], port=6379, db=0, encoding='utf-8')
        finally:
            time.sleep(2)