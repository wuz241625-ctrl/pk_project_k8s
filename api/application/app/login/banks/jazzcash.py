import json
import time
import hashlib
import base64
import random
import string
import secrets
import bcrypt
import logging
from sqlalchemy import update

from application.jazzcash_gateway import build_form_body, calculate_final_status, decode_response, mask_sensitive_payload
# 错误处理相关导入
from application.lakshmi_api.services.error_manager import ErrorManager
from application.lakshmi_api.exceptions.api_error import NewApiError
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.models.bank_type import BankType
from sqlalchemy import update
import re
import uuid
import os
from datetime import datetime
from config import get_config

conf = get_config()

# 服务名
SVRNAME = 'jazzcash'
APIKEY = conf.get('jazzcash_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
APISECRET = conf.get('jazzcash_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')
CDSCOPE = 60 * 60 * 2 # 登录冷却秒 - 2小时
SESSIONSCOPE = 60 * 60 * 24 * 5 # 会话持续秒 - 5天
PIN_CHANGE_ATTEMPTS_MAXIMUM = 3  # JazzCash 不需要，但保留常量定义
FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM = 3  # JazzCash 不需要，但保留常量定义
ISTEST = False
CODE_VER = '20250101001'  # JazzCash版本

# ⚠️ 测试模式配置：跳过指纹上传，使用固定指纹文件
USE_TEST_FINGERPRINT = False  # 改为 False 关闭测试模式
TEST_FINGERPRINT_PATH = '/www/python/dev/api/application/app/login/banks/20251114-105902.815899848-hand_data_1763117938015.zip'

# ========== API版本控制 ==========
JAZZCASH_VERSION = conf.get('jazzcash_api_version', 'v1.6')
if JAZZCASH_VERSION != 'v1.6':
    raise RuntimeError(f'Unsupported JazzCash API version: {JAZZCASH_VERSION}')
JAZZCASH_SHOULD_VERIFY_FINGERPRINT = True

# Redis状态常量
class LoginStatus:
    PRE_LOGIN = "preLogin"                      # 预登录状态
    SEND_OTP = "sendOtp"                        # OTP发送
    VERIFY_OTP = "verifyOtp"                    # OTP验证
    SECOND_LOGIN_READY = "secondLoginReady"     # 已绑定账号等待二次登录
    LOGIN_SUCCESSFUL = "loginSuccessful"        # 登录成功
    ACTIVE_SUCCESSFUL = "activeSuccessful"      # 激活成功

# 状态转换规则定义
STATUS_TRANSITIONS = {
    LoginStatus.PRE_LOGIN: [ LoginStatus.SEND_OTP ],
    LoginStatus.SEND_OTP: [ LoginStatus.VERIFY_OTP ],
    LoginStatus.VERIFY_OTP: [ LoginStatus.LOGIN_SUCCESSFUL ],  # ⭐ 改：只能到 LOGIN_SUCCESSFUL
    LoginStatus.LOGIN_SUCCESSFUL: [ LoginStatus.ACTIVE_SUCCESSFUL ],
    LoginStatus.ACTIVE_SUCCESSFUL: []  # 终态
}

# 状态转换规则定义
class ErrorCode:
    MissingParams = '20001'
    InvalidPhone = '20002'
    InvalidBankOrPayment = '20003'
    InvalidPaswd = '20004'
    PaymentPhoneMismatch = '20005'
    Logined = '20101'
    Logined2 = '20102'
    Logined3 = '20103'
    Logined4 = '20104'
    Unsupported = '20105'
    LoginAttemps = '20106'
    SessionNotExist = '20201'
    PaymentLocked = '20203'
    DBWriteFail = '20601'
    SendOTPFail = '20401'
    VerifyOTPFail = '20307'
    VerifyAccount = '31001'
    VerifyFingerPrint = '31002'
    ActiveAccount = '31003'
    ChangePin = '31004'
    UploadFingerPrint = '31005'
    QueryAccts = '31006'
    SelectAccts = '31007'
    Retry = '66666'


class AccountStatus:
    IsSuccess = False
    IsInCoolDown = False
    IsNeedRelogin = False
    IsNeedChangePin = False
    IsNeedFingerPrint = False
    data = None  # JazzCash: 用于保存 secondLogin 响应数据（包含 IBAN 等）

class JazzCash:

    LOGIN_TYPE = 'sms_otp_pin'

    # 银行名称映射
    BANK_NAME_MAPPING = {
        'jazzcash': 'JAZZCASH',
    }

    # 登录失败次数限制常量
    LOGIN_FAILED_COUNT_KEY = 'login_failed_count_{bankname}_{phone}'
    LOGIN_FAILED_MAX_ATTEMPTS = 3  # 最大失败次数
    LOGIN_FAILED_LOCK_TIME = 60 * 60 * 2  # 锁定时间：2小时

    PROXIES_IP_KEY = 'indian_socks_ip_{bankname}'
    PRELOGIN_KEY = 'pre_login_{bankname}_{payment_id}'
    LOGIN_LOCK_PHONE_KEY = 'login_on_{bankname}_{phone}'
    LOGIN_LOCK_PAYMENT_KEY = 'login_on_{bankname}_{payment_id}'
    PAYMENT_INTERFACE_LOCK_KEY = 'payment_interface_lock:{payment_id}:{operation_name}'


    FINGERPRINT_PATH = '/fingerprint/'
    FINGERPRINT_FILENAME = '{bankname}_{payment_id}_{phone}.zip'

    API_ENDPOINTS = {
        'base_url': conf.get('jazzcash_api_url', 'http://34.150.42.92:84'),
        # JazzCash legacy 接口
        'is_logined': 'isLogined',       # 查询云机实体分配情况
        'send_otp': 'loginStep1',        # 发送OTP（需要提前上传指纹）
        'verify_otp': 'loginStep2',      # 验证OTP
        'verify_account': 'secondLogin', # 验证账户状态
        'fingerprint_upload_url': 'https://jazzcashbusiness.zpay.today/upload_data',  # 指纹上传专用域名
        'fingerprint_check_url': 'https://jazzcashbusiness.zpay.today/is_data_uploaded',  # 查询指纹是否已上传
    }

    def __init__(self, request_handler):
        self.handler = request_handler
        self.redis = request_handler.redis
        self.logger = logging.getLogger(self.__class__.__name__)

        # 添加锁相关的属性
        self.name = SVRNAME
        self.login_data = {}  # 登录数据，用于错误日志
        self.lock_time_payment_interface = 300  # 操作锁的锁定时间（秒） - 5分钟
        self.lock_time_payment_interface_diff = 10  # 操作锁的锁定时间（秒） - 10秒差
        self.lock_time_login_duplicate_avoid = 600  # 操作锁的锁定时间（秒） - 10分钟
        self.expire_time_login_pending = 300
        # 两次 send_otp 之间的最小间隔（秒）。Resend 比此短会返回 PaymentLocked，
        # 既保护银行上游不被刷、也让 UI 有明确等待时长。
        self.RESEND_COOLDOWN_SECONDS = 20

        # 添加错误管理器
        self.error_manager = ErrorManager()

    # ================== 加密相关方法 ==================
    @staticmethod
    def generate_android_id():
        """生成16位十六进制Android ID - 格式如: 193668a83c8d4539"""
        import random
        # 十六进制字符：0-9 和 a-f
        hex_chars = '0123456789abcdef'
        return ''.join(random.choice(hex_chars) for _ in range(16))

    @staticmethod
    def generate_safety_net_id():
        """生成SafetyNet ID"""
        uuid_bytes = secrets.token_bytes(16)
        # UUID v4格式化
        uuid_hex = uuid_bytes.hex()
        uuid_formatted = f'{uuid_hex[:8]}-{uuid_hex[8:12]}-4{uuid_hex[13:16]}-{random.choice('89ab')}{uuid_hex[17:20]}-{uuid_hex[20:]}'
        # 去掉短横线，转大写，截取前26位，加上INDB前缀
        return "INDB" + uuid_formatted.replace('-', '').upper()[:26]

    @staticmethod
    def generate_app_gen_id():
        """生成app_gen_id"""
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(32))

    @staticmethod
    def generate_device_model():
        """生成设备型号，格式：8位数字+1个大写字母（如55041234C）"""
        # 生成8位随机数字（10000000-99999999）
        random_number = random.randint(10000000, 99999999)

        # 生成1个随机大写字母
        random_letter = random.choice(string.ascii_uppercase)

        # 组合成字符串
        device_model = f'{random_number}{random_letter}'

        return device_model

    @staticmethod
    def generate_india_geocode():
        """使用faker库生成印度地区的随机坐标"""
        try:
            from faker import Faker

            # 创建印度本地化的faker实例
            fake = Faker('hi_IN')  # Hindi India locale

            # 生成印度境内的坐标
            # 印度的大致坐标范围：纬度 8°-37°N，经度 68°-97°E
            lat = round(random.uniform(8.0, 37.0), 6)
            lng = round(random.uniform(68.0, 97.0), 6)

            return f'{lat},{lng}'

        except ImportError:
            # 如果faker库不可用，使用备用方案
            # 印度的大致坐标范围
            lat = round(random.uniform(8.0, 37.0), 6)
            lng = round(random.uniform(68.0, 97.0), 6)
            return f'{lat},{lng}'

    @staticmethod
    def generate_india_location():
        """使用faker库生成印度地区的随机地址"""
        try:
            from faker import Faker

            # 创建印度本地化的faker实例
            fake = Faker('hi_IN')  # Hindi India locale

            # 生成印度地址信息
            city = fake.city()
            state = fake.state()

            # 格式化为 "城市,邦,India"
            location = f'{city},{state},India'

            return location

        except ImportError:
            # 如果faker库不可用，使用备用方案
            # 简单的印度地址格式
            cities = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune", "Ahmedabad"]
            states = ["Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "West Bengal", "Telangana", "Gujarat"]

            city = random.choice(cities)
            state = random.choice(states)

            return f'{city},{state},India'

    # ================== 基础工具方法 ==================
    async def _check_login_failed_attempts(self, phone):
        """检查登录失败次数是否超过限制"""
        funcName = '检查登录失败次数是否超过限制'
        try:
            failed_key = self.LOGIN_FAILED_COUNT_KEY.format(bankname=self.name, phone=phone)
            failed_count = await self.redis.get(failed_key)
            if failed_count and int(failed_count) >= self.LOGIN_FAILED_MAX_ATTEMPTS:
                self.logger.warning(f'{self._log_key(funcName)} 用户 {phone} 登录失败超过{self.LOGIN_FAILED_MAX_ATTEMPTS}次，限制登录')
                return True
            return False
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return False

    async def _record_login_failed_attempt(self, phone):
        """记录登录失败次数"""
        funcName = '记录登录失败次数'
        try:
            failed_key = self.LOGIN_FAILED_COUNT_KEY.format(bankname=self.name, phone=phone)
            failed_count = await self.redis.get(failed_key)

            if failed_count:
                failed_count = int(failed_count) + 1
            else:
                failed_count = 1

            # 设置Redis键，过期时间为2小时
            await self.redis.set(failed_key, failed_count, self.LOGIN_FAILED_LOCK_TIME)
            self.logger.warning(f'{self._log_key(funcName)} 用户 {phone} 登录失败，当前失败次数: {failed_count}')
            return failed_count
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return 0

    async def _clear_login_failed_attempts(self, phone):
        """清除登录失败次数（登录成功时调用）"""
        funcName = '清除登录失败次数（登录成功时调用）'
        try:
            failed_key = self.LOGIN_FAILED_COUNT_KEY.format(bankname=self.name, phone=phone)
            await self.redis.delete(failed_key)
            self.logger.info(f'{self._log_key(funcName)} 用户 {phone} 登录成功，清除失败计数')
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')

    async def _verify_payment_password_bcrypt(self, password, hashed_password, phone):
        """验证交易密码 - 使用bcrypt算法）"""
        funcName = '验证交易密码'
        if not password:
            raise NewApiError(ErrorCode.LoginAttemps, 'Payment password cannot be empty')
        if not hashed_password:
            raise NewApiError(ErrorCode.LoginAttemps, 'User payment password not set')

        try:
            if not bcrypt.checkpw(password.encode('utf8'), hashed_password.encode('utf8')):
                # 记录登录失败次数
                await self._record_login_failed_attempt(phone)
                raise NewApiError(ErrorCode.LoginAttemps, 'Payment password verification failed')
            else:
                # 密码验证成功，清除失败计数
                await self._clear_login_failed_attempts(phone)
        except NewApiError:
            raise  # 重新抛出 NewApiError
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            # 记录登录失败次数
            await self._record_login_failed_attempt(phone)
            raise NewApiError(ErrorCode.InvalidPaswd, 'Payment password verification failed')

    def _format_phone_number(self, phone: str) -> str:
        """格式化手机号"""
        if not phone:
            return phone
        phone = re.sub(r'[\s\-\+]', '', phone) # 去掉空格和特殊字符
        match = re.match(r'^(?:\+?92|0092)?0?3(\d{9})$', phone) # 规则：移除国际前缀（92、0092），并转换成 03XXXXXXXXX
        if match:
            return '03' + match.group(1)
        return phone

    def _validate_phone_number(self, phone):
        """验证手机号"""
        if not phone:
            return phone
        phone = re.sub(r'[\s\-\+]', '', phone) # 去掉空格和特殊字符
        match = re.match(r'^(?:\+?92|0092)?0?3(\d{9})$', phone) # 规则：移除国际前缀（92、0092），并转换成 03XXXXXXXXX
        return match

    def _get_pre_login_key(self):
        bankname = self.login_data.get('bankname', '')
        payment_id = self.login_data.get('payment_id', '')
        payment_id = payment_id if payment_id else self.login_data.get('phone', '')
        redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
        return redis_key

    def _log_key(self, funcName):
        return f'{self.name} {self._get_pre_login_key()} {funcName}'

    def _log_response(self, funcName, response):
        try:
            # 检查response是否为None
            if response is None:
                self.logger.error(f'{self._log_key(funcName)} 响应为None，无法记录日志')
                return

            # 基本信息
            self.logger.info(f'{self._log_key(funcName)} 请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}')
            self.logger.info(f'{self._log_key(funcName)} 请求URL: {response.url}')
            self.logger.info(f'{self._log_key(funcName)} 请求方法: {response.request.method}')
            self.logger.info(f'{self._log_key(funcName)} 状态码: {response.status_code}')

            self.logger.info(f'{self._log_key(funcName)} 状态码: {response.status_code}')

            # 请求头信息
            reqHeaders = ""
            for key, value in dict(response.request.headers).items():
                reqHeaders = f'{key}: {value}, '
            self.logger.info(f'{self._log_key(funcName)} 请求头: {reqHeaders}')

            # 响应头信息
            rspHeaders = ""
            for key, value in dict(response.headers).items():
                rspHeaders = f'{key}: {value}, '
            self.logger.info(f'{self._log_key(funcName)} 响应头: {rspHeaders}')

            self.logger.info(f'{self._log_key(funcName)} HTTP状态码: {response.status_code}')

            # 尝试解析为JSON
            try:
                json_data = response.json()
                self.logger.info(f'{self._log_key(funcName)} 响应体: {json.dumps(json_data, ensure_ascii=False, indent=2)}')
            except:
                # 尝试获取文本内容
                try:
                    text_content = response.text
                    if text_content:
                        if len(text_content) > 1000:
                            self.logger.info(f'{self._log_key(funcName)} 响应体: {text_content[:1000]}... (内容已截断)')
                        else:
                            self.logger.info(f'{self._log_key(funcName)} 响应体: {text_content}')
                    else:
                        self.logger.info(f'{self._log_key(funcName)} 响应体为空')
                except Exception as e:
                    self.logger.error(f'{self._log_key(funcName)} 读取响应体文本失败: {str(e)}')

            # 响应编码信息
            if hasattr(response, 'encoding'):
                self.logger.info(f'{self._log_key(funcName)} 响应编码: {response.encoding}')

            # 耗时信息
            if hasattr(response, 'elapsed'):
                self.logger.info(f'{self._log_key(funcName)} 请求耗时: {response.elapsed.total_seconds():.3f} 秒')

            # 如果是重定向，记录重定向历史
            if hasattr(response, 'history') and response.history:
                redicHis = ""
                for hist in response.history:
                    redicHis = f'{hist.status_code} -> {hist.url}, '
                self.logger.info(f'{self._log_key(funcName)} 重定向历史: {redicHis}')

        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)

    # ================== 基础支持方法 ==================
    async def _select_proxy_ip(self, bankname):
        """
        选择代理IP，保持一致性
        参考历史代理实现的_select_proxy_ip方法
        """
        funcName = '选择代理IP'
        try:
            # 获取新的代理IP（返回纯净字符串格式，用于存储到session）
            proxy_ip = await self._get_proxies(bankname)
            if not proxy_ip:
                self.logger.error(f'{self._log_key(funcName)} 无可用代理IP')
                return ""
            self.logger.info(f'{self._log_key(funcName)} 选择代理IP成功（session存储格式）: {proxy_ip}')
            return proxy_ip
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return ""

    async def _get_proxies(self, bankname):
        """
        从Redis获取可用的代理IP列表并随机选择一个
        参考历史代理实现的_get_proxies()方法（使用被注释的Redis逻辑）
        """
        funcName = '从Redis获取可用的代理IP列表并随机选择一个'
        # ================ Redis代理获取逻辑 (来自历史代理实现注释代码) ================
        try:
            # 从Redis获取印度SOCKS代理IP列表
            redis_key = self.PROXIES_IP_KEY.format(bankname=bankname)
            indian_socks_ip = await self.redis.get(redis_key)

            if not indian_socks_ip:
                self.logger.error(f'{self._log_key(funcName)} Redis中无{redis_key}代理IP配置')
                return False

            # 解析代理IP列表
            if isinstance(indian_socks_ip, bytes):
                indian_socks_ip = indian_socks_ip.decode('utf-8')

            proxy_list = indian_socks_ip.split(',')
            proxy_list = [item.strip() for item in proxy_list if item.strip()]

            if not proxy_list:
                self.logger.error(f'{self._log_key(funcName)} {redis_key}代理IP列表为空')
                return False

            # 随机选择一个代理IP
            import random
            selected_proxy = random.choice(proxy_list)

            # 确保返回的是纯净的字符串格式（去掉socks5://前缀）
            if selected_proxy.startswith('socks5://'):
                selected_proxy = selected_proxy[9:]  # 移除 'socks5://' 前缀

            self.logger.info(f'{self._log_key(funcName)} 从{len(proxy_list)}个Redis代理中选择: {selected_proxy}')
            return selected_proxy  # 返回字符串格式，用于存储到session

        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return False

    async def _get_proxy_for_request(self, session_data):
        """
        为HTTP请求获取代理配置
        返回requests库可用的代理字典格式
        """
        funcName = '为HTTP请求获取代理配置'
        try:
            # 从 socks_ip 字段获取代理IP（存储格式为 username:password@IP:PORT）
            socks_ip = session_data.get('socks_ip', '')
            if not socks_ip:
                return None

            # 添加 socks5:// 前缀用于HTTP请求
            proxy_url = f'socks5://{socks_ip}'

            # 返回 requests 库格式的代理字典
            proxy_dict = {
                'http': proxy_url,
                'https': proxy_url
            }

            self.logger.info(f'{self._log_key(funcName)} 获取请求代理配置: {proxy_url}')
            return proxy_dict

        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return None

    def _generate_device_id(self):
        """生成设备ID"""
        import uuid
        return str(uuid.uuid4()).replace('-', '')

    def _get_standard_headers(self, session_data=None):
        """获取动态HTTP头，包含动态生成的User-Agent"""
        if session_data:
            model = session_data.get('model', '55041234C')
        else:
            model = '55041234C'

        return {
            'Content-Type': 'application/json; charset=utf-8',
            'Connection': 'Keep-Alive',
            'User-Agent': f'Dalvik/2.1.0 (Linux; U; Android 13; {model} Build/TQ3A.230901.001)'
        }

    async def _get_payment_interface_lock(self, payment_id, operation_name):
        """获取基于payment_id的接口锁"""
        funcName = '获取基于payment_id的接口锁'
        try:
            lock_key = self.PAYMENT_INTERFACE_LOCK_KEY.format(payment_id=payment_id, operation_name=operation_name)
            lock_value = f'{int(time.time())}_{random.randint(1000, 9999)}'

            # 尝试获取锁，如果成功设置过期时间
            lock_acquired = await self.redis.set(lock_key, lock_value, nx=True, ex=self.lock_time_payment_interface)

            if lock_acquired:
                self.logger.info(f'{self._log_key(funcName)} 获取接口锁成功: {payment_id}:{operation_name}')
                return {
                    'status': 'success',
                    'lock_id': lock_key,
                    'lock_value': lock_value
                }
            else:
                self.logger.warning(f'{self._log_key(funcName)} 获取接口锁失败，已被占用: {payment_id}:{operation_name}')
                raise NewApiError(ErrorCode.PaymentLocked, 'Operation too frequent, please try again later')

        except NewApiError:
            raise  # 重新抛出NewApiError
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            raise NewApiError(ErrorCode.PaymentLocked, 'System error')

    async def _release_payment_interface_lock(self, lock_id, lock_value):
        """释放基于payment_id的接口锁"""
        funcName = '释放基于payment_id的接口锁'
        try:
            _lock = await self.redis.get(lock_id)
            if _lock and _lock == lock_value:

                # 获取剩余时长
                ttl_residue = await self.redis.ttl(lock_id)

                # 如果 key 不存在，返回 -2
                if ttl_residue == -2:
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, key已经不存在')
                    return True

                # 如果 key 存在但没有设置过期时间，返回 -1
                if ttl_residue == -1:
                    await self.redis.delete(lock_id)
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, key没有设置TTL')
                    return True

                if ttl_residue == 0:
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, key已经过期')
                    return True

                # 计算用户已经待的时长
                alreadyStay = self.lock_time_payment_interface - ttl_residue
                if alreadyStay >= self.lock_time_payment_interface_diff:
                    await self.redis.delete(lock_id)
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, 已等待: {alreadyStay}')
                    return True
                else:
                    ttl_new = self.lock_time_payment_interface_diff - alreadyStay
                    await self.redis.set(lock_id, lock_value, ex=ttl_new)
                    self.logger.info(f'{self._log_key(funcName)} 调整接口锁成功: {lock_id}, 剩: {ttl_new}')
                    return True
            else:
                self.logger.warning(f'{self._log_key(funcName)} 释放接口锁失败，锁值不匹配: {lock_id}')
                return False
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return False

    # ================== 会话管理方法 ==================
    async def _get_session_data(self, redis_key):
        """获取会话数据"""
        funcName = '获取会话数据'
        try:
            if not redis_key:
                return None
            session_json = await self.redis.get(redis_key)
            if session_json:
                return json.loads(session_json)
            return None
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return None

    async def _update_session_status(self, redis_key, session_data, status_new, additional_data=None) -> int:
        """更新会话状态"""
        funcName = '更新会话状态'
        se_until = 0
        try:
            session_data['status'] = status_new
            session_data['last_status_change'] = int(time.time())
            session_data['last_request_time'] = int(time.time())

            if 'status_history' not in session_data:
                session_data['status_history'] = []

            if additional_data:
                session_data.update(additional_data)

            # pre_login 时，会话只会短暂存在，且可以被续期
            # verify_otp 时，会话将持续较长时间，此时状态必为 LoginStatus.LOGIN_SUCCESSFUL
            # verify_otp 后，只会更改内容，不会续期，直到状态被改为 LoginStatus.Active_SUCCESSFUL
            # LoginStatus.Active_SUCCESSFUL 后，会话会被爬单程序命中且删除

            if LoginStatus.LOGIN_SUCCESSFUL not in session_data['status_history']:
                if status_new != LoginStatus.LOGIN_SUCCESSFUL:
                    expire_time = self.expire_time_login_pending
                    expire_desc = f'{self.expire_time_login_pending / 60}分钟'
                else:
                    expire_time = SESSIONSCOPE
                    expire_desc = f'{SESSIONSCOPE / 60}分钟'

                se_until = int(time.time() + expire_time)
                session_data['se_until'] = se_until
                session_data['status_history'].append(status_new)

                await self.redis.setex(redis_key, expire_time, json.dumps(session_data))
                self.logger.info(f'{self._log_key(funcName)} {redis_key} -> {status_new} (过期时间: {expire_desc})')
            else:
                se_until = session_data.get('se_until', 0)
                session_data['status_history'].append(status_new)

                await self.redis.set(redis_key, json.dumps(session_data))
                self.logger.info(f'{self._log_key(funcName)} {redis_key} -> {status_new})')
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
        return se_until

    async def _validate_status_transition(self, session_data, expected_current_status, target_status, operation_name):
        """验证状态转换是否有效"""
        funcName = '验证状态转换是否有效'
        current_status = session_data.get('status')
        if current_status != expected_current_status:
            message = f'{self._log_key(funcName)} 状态转换无效 {operation_name}: 期望 {expected_current_status}, 实际 {current_status}'
            self.logger.error(message)
            return {'valid': False, 'message': message}
        if target_status not in STATUS_TRANSITIONS.get(current_status, []):
            message = f'{self._log_key(funcName)} 状态转换无效 {operation_name}: {current_status} -> {target_status}'
            self.logger.error(message)
            return {'valid': False, 'message': message}
        return {'valid': True, 'message': '状态转换有效'}

    # ================== HTTP请求方法 ==================
    def make_request(self, method, url, headers=None, data=None, files=None, proxies=None):
        self.logger.info('请求 {method} {url}, headers:{headers} data:{data} 代理:{proxies}'.format(method=method, url=url, headers=headers, data=data, proxies=proxies))
        try:
            headers = headers or {}

            import requests
            if not hasattr(self, 'session'):
                self.session = requests.Session()

            response = None
            if method.upper() == 'GET':
                response = self.session.get(url, proxies=proxies, verify=False, allow_redirects=True, timeout=(30, 30))
            elif method.upper() == 'POST':
                headers['Content-Type'] = 'application/x-www-form-urlencoded'
                response = self.session.post(url, headers=headers, data=data, proxies=proxies, verify=False, allow_redirects=True, timeout=(30, 30))
            else:
                # headers['Content-Type'] = 'multipart/form-data'
                response = self.session.post(url, headers=headers, data=data, files=files, proxies=proxies, verify=False, allow_redirects=True, timeout=(30, 30))

            if response is not None:
                self.logger.info(f'请求 {method} {url}, data:{data}, response: {response}, response.text: {response.text}')
            return response
        except Exception as e:
            self.logger.error(f'网络请求错误： 错误详情:{e}')
            return None

    def retry_make_request(self, *args, **kwargs):
        """简化的retry_make_request - 保持与历史代理实现一致"""
        # 第一次尝试
        res = self.make_request(*args, **kwargs)
        if res is not None and (200 <= res.status_code < 300):
            return res

        # 第二次尝试
        self.logger.info(f'make_request() second try, args: {args}, kwargs: {kwargs}')
        res = self.make_request(*args, **kwargs)

        if res is None or not (200 <= res.status_code < 300):
            self.logger.warning(f'make_request() 两次尝试均失败, args: {str(args)}, kwargs: {str(kwargs)}')

        return res

    # ================== 核心登录流程方法 ==================
    async def pre_login_http(self, data):
        """
        预登录HTTP接口 - 处理用户登录前的准备工作

        📋 功能说明：
        - 只做会话初始化，不调用银行API（与JioBank保持一致的架构）
        - 生成设备标识（android_id、safety_net_id、app_gen_id）
        - 创建Redis会话数据，为后续流程做准备

        📥 输入参数：
        - bankname: 银行名称 (必需)
        - phone: 手机号 (必需，会自动格式化为91+10位数字)
        - password: 密码 (必需)
        - partner_id: 合作伙伴ID (可选)
        - is_new_user: 是否新用户 (可选，默认True)
        - payment_id: 支付ID (可选，如果提供则验证phone是否匹配)

        [SESSION] 会话数据创建：
        - Redis键格式: pre_login_{bankname}_{payment_id}
        - 包含：设备标识、认证信息、银行特定数据等
        - 过期时间：? 秒

        📤 返回格式：
        {
            'status': 'success/error',
            'message': '描述信息',
            'data': {
                'id': payment_id,
                'redis_key': 'pre_login_{bankname}_xxx',
                'expires_in': ?,
                'next_step': 'send_sms'
            }
        }

        🔄 下一步：调用 send_sms_http
        """
        funcName = 'pre_login_http'
        lockName = 'pre_login'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'=== 当前代码版本 code_ver: {CODE_VER} ===')
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            if data.get('step', 'unknown') != 'complete_login':
                raise NewApiError(ErrorCode.Unsupported, f'Unsupported step: {data.get('step', 'unknown')}')

            # 检查用户类型 完成登录信息提交
            self.logger.info(f'{self._log_key(funcName)} 执行步骤: {data.get('step', 'complete_login')}')

            required_fields = ['bankname', 'phone', 'password', 'pin', 'name']
            if not all(field in data and data[field] for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data or not data[field]]
                error_msg = f'Missing required parameters: {', '.join(missing_fields)}'
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: {error_msg}')
                raise NewApiError(ErrorCode.MissingParams, error_msg)

            bankname = data['bankname']
            original_phone = data['phone']  # 保存原始号码
            phone = self._format_phone_number(original_phone)
            password = data['password']
            pin = data['pin']
            name = data['name']  # name 已在 required_fields 中验证，必须存在
            expire_second = self.expire_time_login_pending

            self.logger.info(f'{self._log_key(funcName)} 前端传递的name参数: {name}')

            if not self._validate_phone_number(phone):
                raise NewApiError(ErrorCode.InvalidPhone, f'Invalid phone number format: {phone}, should start with 03 and be 11 digits long')

            # 检查登录失败次数限制
            is_locked = await self._check_login_failed_attempts(phone)
            if is_locked:
                raise NewApiError(ErrorCode.LoginAttemps, 'Try too many times, try again after two hours.')

            # 验证交易密码 - 参考UPI controller的密码验证逻辑
            try:
                await self._verify_payment_password_bcrypt(password, self.handler.current_user.hash_trade, phone)
                self.logger.info(f'{self._log_key(funcName)} 密码验证成功: 用户={self.handler.current_user.id}, 手机号={phone}')
            except Exception as e:
                self.logger.error(f'{self._log_key(funcName)} 密码验证异常: 用户={self.handler.current_user.id}, 手机号={phone}, 错误={str(e)}')
                raise NewApiError(ErrorCode.LoginAttemps, 'Payment password verification failed')

            # 从认证的用户信息中获取码商ID
            user_id = self.handler.current_user.id  # ← 获取码商ID
            is_new_user = data.get('is_new_user', True)
            payment_id = data.get('payment_id')  # 获取payment_id
            bound_payment = None

            self.logger.info(f'{self._log_key(funcName)} 预登录参数: 银行={bankname}, 手机号={phone}, 码商ID={user_id}')
            self.logger.info(f'{self._log_key(funcName)} 当前认证用户信息: ID={user_id}, 手机号={getattr(self.handler.current_user, 'cellphone', 'Unknown')}')

            # 立即检查协议进程锁 - 在任何复杂处理前进行早期检查
            # 检查 payment_id 登录状态
            if payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=bankname, payment_id=payment_id)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            # 检查 phone 登录状态
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=bankname, phone=phone)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')

            # 如果提供了payment_id，验证phone是否匹配
            if payment_id:
                # 获取银行类型ID
                bank_type_id = await self._get_bank_type_id(bankname)
                if not bank_type_id:
                    raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Bank type not found for: {bankname}')

                with self.handler.db_orm.sessionmaker() as session:
                    existing_payment = session.query(Payment).filter(
                        Payment.id == payment_id,
                        Payment.bank_type_id == bank_type_id
                    ).first()
                    if not existing_payment:
                        raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Payment record not found: {payment_id}')
                    if existing_payment.phone != phone:
                        raise NewApiError(ErrorCode.PaymentPhoneMismatch, f'Phone number mismatch for payment {payment_id}, expected {existing_payment.phone}')
                    if int(getattr(existing_payment, 'user_id', 0) or 0) != int(user_id):
                        raise NewApiError('10402', 'UPI already occupied by another user')
                    bound_payment = {
                        'id': existing_payment.id,
                        'phone': existing_payment.phone,
                        'user_id': existing_payment.user_id,
                        'pin': getattr(existing_payment, 'pin', None),
                        'name': getattr(existing_payment, 'name', '') or '',
                        'account_entire': getattr(existing_payment, 'account_entire', None),
                        'account_accno': getattr(existing_payment, 'account_accno', None),
                        'account_iban': getattr(existing_payment, 'account_iban', None),
                        'channel': getattr(existing_payment, 'channel', None),
                    }
                    phone_owner = await self._check_payment(bankname, phone, user_id)
                    if phone_owner and str(phone_owner.get('id')) != str(existing_payment.id):
                        raise NewApiError('10402', 'UPI already occupied by another payment id')
                    self.logger.info(f'{self._log_key(funcName)} Payment record validation successful: {payment_id}')

                    # 找到了 Payment 记录，说明是老用户
                    is_new_user = False
            else:
                # 检查现有payment记录
                existing_payment = await self._check_payment(bankname, phone, user_id)
                is_new_user = existing_payment is None
                self.logger.info(f'{self._log_key(funcName)} 用户类型检查: {phone} - partner_id: {user_id} - 新用户: {is_new_user}')

                if existing_payment:
                    if int(existing_payment.get('user_id') or 0) != int(user_id):
                        self.logger.error(f'{self._log_key(funcName)} UPI已被占用: phone={phone}, current_user={user_id}, owner_user={existing_payment["user_id"]}')
                        raise NewApiError('10402', 'UPI already occupied by another user')  # UPI已被其他用户占用
                    self.logger.info(
                        f'{self._log_key(funcName)} JazzCash 已绑定当前码商: phone={phone}, '
                        f'user_id={user_id}, payment_id={existing_payment["id"]}'
                    )
                    payment_id = existing_payment.get('id')
                    bound_payment = existing_payment
                else:
                    payment_id = phone  # 直接使用手机号作为临时ID
                    self.logger.info(f'{self._log_key(funcName)} 使用手机号作为payment_id: {payment_id}')

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            if bound_payment:
                session_data = self._build_bound_prelogin_session(
                    bankname=bankname,
                    payment_id=payment_id,
                    phone=phone,
                    original_phone=original_phone,
                    password=password,
                    pin=pin,
                    name=name,
                    user_id=user_id,
                    bound_payment=bound_payment,
                )
                is_logined = await self._is_logined(session_data)
                if is_logined.get('data') is True:
                    redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
                    await self.redis.delete(redis_key)

                    result = {
                        'status': 'success',
                        'message': '成功',
                        'data': {
                            'id': payment_id,
                            'redis_key': None,
                            'expires_in': 0,
                            'total_timeout': 120,
                            'is_new_user': False,
                            'bank_type': self.LOGIN_TYPE,
                            'fingerprint_uploaded': True,
                            'next_step': 'second_login'
                        }
                    }
                    self.logger.info(f'{self._log_key(funcName)} 已绑定JazzCash账号通过isLogined，返回second_login: {result}')
                    return result

                self.logger.warning(
                    f'{self._log_key(funcName)} 已绑定JazzCash账号isLogined失败，回退首次登录流程: '
                    f'phone={phone}, payment_id={payment_id}, result={is_logined}'
                )

            # 创建Redis登录会话
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            self.logger.info(f'{self._log_key(funcName)} 创建Redis会话key: {redis_key}')

            # 检查是否已存在会话
            existing_session = await self._get_session_data(redis_key)
            if existing_session:
                current_status = existing_session.get('status')
                self.logger.warning(f'{self._log_key(funcName)} 发现已存在会话: {redis_key} - 状态: {current_status}')
                if current_status == LoginStatus.LOGIN_SUCCESSFUL:
                    self.logger.error(f'{self._log_key(funcName)} 账户已登录成功，拒绝重复登录')
                    raise NewApiError(ErrorCode.Logined2, f'Account already logged in successfully, duplicate login denied')
                elif current_status == LoginStatus.PRE_LOGIN:
                    self.logger.error(f'{self._log_key(funcName)} 已经开始走登录流程，拒绝重复登录')
                    raise NewApiError(ErrorCode.Logined3, f'Account already started login process, duplicate login denied')
                elif current_status in [LoginStatus.SEND_OTP, LoginStatus.VERIFY_OTP]:
                    self.logger.error(f'{self._log_key(funcName)} 登录流程进行中，拒绝重复登录')
                    raise NewApiError(ErrorCode.Logined4, f' status: {current_status}')

            # 选择代理IP
            proxy_ip = await self._select_proxy_ip(bankname)
            self.logger.info(f'{self._log_key(funcName)} 选择代理IP: {proxy_ip}')

            # 一次生成、整个流程不变的设备标识
            android_id = self.generate_android_id()
            safety_net_id = self.generate_safety_net_id()
            app_gen_id = self.generate_app_gen_id()  # 重要：一次生成，后续复用

            # 生成动态设备信息
            device_model = self.generate_device_model()
            india_geocode = self.generate_india_geocode()
            india_location = self.generate_india_location()

            # 构建特定的会话数据（纯会话初始化，不调用银行API）
            session_data = {
                # === 标准必要字段（参考e_wallet_handler.py） ===
                'id': payment_id,                           # payment数据库ID或临时ID
                'partner_id': user_id,                      # 用户/合作伙伴ID
                'phone': phone,                             # 手机号（格式化后，带91前缀）
                'original_phone': original_phone,           # 原始手机号（前端传来的）
                'status': LoginStatus.PRE_LOGIN,            # 当前状态
                'time': int(time.time()),                   # 创建时间戳（标准字段）
                'try_count': 0,                             # 重试次数（标准字段）
                'socks_ip': proxy_ip or '',                 # 代理IP（标准字段名）
                'to': self.name,                            # 目标key
                'qr_channel': data.get('channel', '1003'),  # 渠道 - JazzCash 默认只支持 1003
                'pinCode': pin,                             # PIN码
                'id_num': '',                               # 身份证号

                # === 扩展必要字段 ===
                'bankname': bankname,                       # 银行名称
                'password': password,                       # 密码
                'account': data.get('account', ''),         # 账户信息
                'is_new_user': is_new_user,                 # 是否新用户
                'status_history': [LoginStatus.PRE_LOGIN], # 状态历史
                'name': name,                               # 账户名称（从前端获取）

                # === 时间管理 ===
                'login_time': int(time.time()),             # 登录开始时间
                'last_status_change': int(time.time()),     # 最后状态变更时间
                'last_request_time': int(time.time()),      # 最后请求时间
                'expires_at': int(time.time()) + expire_second,       # 过期时间
                'total_timeout': int(time.time()) + 120,    # 总超时时间
                'sendOTPTime': 0,                           # OTP发送时间
                'sendSMSTime': 0,                           # SMS发送时间
                'retry_count': 0,                           # 重试计数

                # === 网络和代理信息 ===
                'headers': self._get_standard_headers({'model': device_model}),    # 动态HTTP头

                # === 认证信息（初始为空，将在send_sms_http中获取） ===
                'authorization': '',                        # 认证信息
                'access_token': '',                         # 访问令牌
                'session_token': '',                        # 会话令牌
                'client_secret': '',                        # 客户端密钥

                # === 设备信息（一次生成，保持一致） ===
                'device_id': self._generate_device_id(),    # 设备ID
                'androidId': android_id,                    # Android ID (与PHP版本一致)
                'safetyNetId': safety_net_id,               # SafetyNet ID (与PHP版本一致)
                'app_gen_id': app_gen_id,                   # App生成ID
                'model': device_model,                      # 设备型号
                'geoCode': india_geocode,                   # 印度地区坐标
                'location': india_location,                 # 印度地区地址
                'fcmToken': "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R",  # FCM Token

                # === 特定的认证数据 ===
                'bank_auth_data': {
                    'client_id': '',                        # 客户端ID
                    'client_secret': '',                    # 客户端密钥
                    'bearer_token': '',                     # Bearer令牌
                    'serv_gen_id': '',                      # 将在OTP验证后获取
                },

                # === UPI相关 ===
                'selected_upi': '',                         # 选择的UPI
                'upi_list': [],                             # UPI列表
                'upi_list_fetched': False,                  # UPI列表是否已获取

                # === 特定数据 ===
                'bank_specific_data': {
                    'need_sms': True,                       # 需要短信验证
                    'sms_sent': False,                      # 短信是否已发送
                    'sms_verified': False,                  # 短信是否已验证
                    'sms_number': '',                       # 短信号码(将在send_sms_http中获取)
                    'sms_content': '',                      # 短信内容(将在send_sms_http中获取)
                    'otp_sent': False,                      # OTP是否已发送
                    'otp_verified': False,                  # OTP是否已验证
                    'pin_verified': False                   # PIN是否已验证
                },

                # === JazzCash legacy 特有字段 ===
                'fingerprint_uploaded': False,              # 指纹是否已上传（is_data_uploaded 结果）
                'fingerprint_check_time': 0,                # 指纹检查时间戳
            }

            self.logger.info(f'{self._log_key(funcName)} Redis待存储数据: {json.dumps(session_data)}')

            # 存储到Redis
            await self.redis.setex(redis_key, expire_second, json.dumps(session_data))
            self.logger.info(f'{self._log_key(funcName)} 会话数据已存储到Redis: {redis_key} - 过期时间: {expire_second}秒')

            # ========== [已移除] isLogined 云机状态检查 ==========
            # 说明：现在只通过 fingerprint_uploaded 来决定 next_step
            # 日期：2024-11-19
            # 已移除 cloud_exists 和 cloud_check_time 相关字段

            # ========== [新增] 查询指纹是否已上传 ==========
            self.logger.info(f'{self._log_key(funcName)} ========================================')
            self.logger.info(f'{self._log_key(funcName)} 当前API版本: {JAZZCASH_VERSION}')
            self.logger.info(f'{self._log_key(funcName)} 开始查询指纹上传状态')
            self.logger.info(f'{self._log_key(funcName)} 查询账号: phone={phone}')
            fingerprint_uploaded = False  # 默认值

            # ========== 根据API版本决定是否检查指纹 ==========
            if JAZZCASH_VERSION == 'v1.6':
                # v1.6流程：先发送OTP，再上传指纹，最后触发loginStep2
                self.logger.info(f'{self._log_key(funcName)} v1.6流程：指纹上传延后到OTP发送后')
                fingerprint_uploaded = False
            else:
                # legacy流程：检查指纹（保持原有逻辑）
                self.logger.info(f'{self._log_key(funcName)} legacy流程：检查指纹上传状态')
                try:
                    # 调用指纹查询 API
                    self.logger.info(f'{self._log_key(funcName)} 调用 _check_fingerprint_uploaded 方法...')
                    api_result_fingerprint = await self._check_fingerprint_uploaded(phone)

                    self.logger.info(f'{self._log_key(funcName)} _check_fingerprint_uploaded 返回结果: {api_result_fingerprint}')

                    fingerprint_uploaded = api_result_fingerprint.get('uploaded', False)
                    fingerprint_status = api_result_fingerprint.get('status', 'error')
                    fingerprint_message = api_result_fingerprint.get('message', '未知')

                    self.logger.info(f'{self._log_key(funcName)} 解析返回结果:')
                    self.logger.info(f'{self._log_key(funcName)}   - uploaded: {fingerprint_uploaded}')
                    self.logger.info(f'{self._log_key(funcName)}   - status: {fingerprint_status}')
                    self.logger.info(f'{self._log_key(funcName)}   - message: {fingerprint_message}')

                    if fingerprint_uploaded:
                        self.logger.info(f'{self._log_key(funcName)} ✅ 指纹查询成功: 指纹已上传')
                    else:
                        self.logger.warning(f'{self._log_key(funcName)} ⚠️ 指纹查询成功: 指纹未上传')

                        # ========== [新增] 云端未上传时,尝试使用本地指纹自动重新上传 ==========
                        self.logger.info(f'{self._log_key(funcName)} ========================================')
                        self.logger.info(f'{self._log_key(funcName)} 开始尝试自动重新上传本地指纹')

                        # 构建本地指纹文件路径
                        fingerprint_filename = self.FINGERPRINT_FILENAME.format(
                            bankname=bankname,
                            payment_id=payment_id,
                            phone=phone
                        )
                        local_fingerprint_path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            self.FINGERPRINT_PATH,
                            fingerprint_filename
                        )

                        self.logger.info(f'{self._log_key(funcName)} 本地指纹路径: {local_fingerprint_path}')

                        # 检查本地文件是否存在
                        if os.path.exists(local_fingerprint_path):
                            self.logger.info(f'{self._log_key(funcName)} ✅ 发现本地指纹文件,尝试自动重新上传...')

                            try:
                                # 读取本地文件
                                with open(local_fingerprint_path, 'rb') as f:
                                    file_body = f.read()

                                file_size = len(file_body)
                                self.logger.info(f'{self._log_key(funcName)} 本地指纹文件大小: {file_size} bytes')

                                # 重新上传到云端
                                filename = os.path.basename(local_fingerprint_path)
                                self.logger.info(f'{self._log_key(funcName)} 正在上传: {filename}')

                                await self._upload_fingerprint(session_data, filename, file_body)

                                # 验证上传是否成功
                                self.logger.info(f'{self._log_key(funcName)} 验证上传结果...')
                                verify_result = await self._check_fingerprint_uploaded(phone)

                                if verify_result.get('uploaded'):
                                    self.logger.info(f'{self._log_key(funcName)} ✅ 本地指纹自动重新上传成功!')
                                    fingerprint_uploaded = True
                                else:
                                    self.logger.error(f'{self._log_key(funcName)} ❌ 本地指纹重新上传失败,验证未通过')
                                    fingerprint_uploaded = False

                            except Exception as upload_error:
                                self.logger.error(f'{self._log_key(funcName)} ❌ 自动重新上传异常: {str(upload_error)}')
                                self.logger.error(f'{self._log_key(funcName)} 异常类型: {type(upload_error).__name__}')
                                import traceback
                                self.logger.error(f'{self._log_key(funcName)} 异常堆栈:')
                                for line in traceback.format_exc().split('\n'):
                                    if line.strip():
                                        self.logger.error(f'{self._log_key(funcName)}   {line}')
                                fingerprint_uploaded = False
                        else:
                            self.logger.warning(f'{self._log_key(funcName)} ⚠️ 本地指纹文件不存在: {local_fingerprint_path}')
                            fingerprint_uploaded = False

                        self.logger.info(f'{self._log_key(funcName)} 自动重新上传流程结束')
                        self.logger.info(f'{self._log_key(funcName)} ========================================')

                except Exception as e:
                    # 容错处理：指纹查询失败不影响主流程
                    self.logger.error(f'{self._log_key(funcName)} ❌ 指纹查询异常: {str(e)}')
                    self.logger.error(f'{self._log_key(funcName)} 异常类型: {type(e).__name__}')
                    import traceback
                    self.logger.error(f'{self._log_key(funcName)} 异常堆栈:')
                    for line in traceback.format_exc().split('\n'):
                        if line.strip():
                            self.logger.error(f'{self._log_key(funcName)}   {line}')
                    self.logger.error(f'{self._log_key(funcName)} 继续流程，默认指纹未上传')
                    fingerprint_uploaded = False

            self.logger.info(f'{self._log_key(funcName)} 指纹查询流程结束')
            self.logger.info(f'{self._log_key(funcName)} ========================================')

            # 更新会话数据
            self.logger.info(f'{self._log_key(funcName)} 正在更新会话数据到Redis...')
            session_data['fingerprint_uploaded'] = fingerprint_uploaded
            session_data['fingerprint_check_time'] = int(time.time())
            self.logger.info(f'{self._log_key(funcName)} 会话数据更新字段:')
            self.logger.info(f'{self._log_key(funcName)}   - fingerprint_uploaded: {fingerprint_uploaded}')
            self.logger.info(f'{self._log_key(funcName)}   - fingerprint_check_time: {session_data["fingerprint_check_time"]}')

            # 重新保存到 Redis
            await self.redis.setex(redis_key, expire_second, json.dumps(session_data))
            self.logger.info(f'{self._log_key(funcName)} ✅ 会话数据已更新到Redis')
            self.logger.info(f'{self._log_key(funcName)} Redis Key: {redis_key}')
            self.logger.info(f'{self._log_key(funcName)} 过期时间: {expire_second}秒')

            self.logger.info(f'{self._log_key(funcName)} ==========================================')
            self.logger.info(f'{self._log_key(funcName)} pre_login 流程总结:')
            self.logger.info(f'{self._log_key(funcName)}   - phone: {phone}')
            self.logger.info(f'{self._log_key(funcName)}   - payment_id: {payment_id}')
            self.logger.info(f'{self._log_key(funcName)}   - 新用户: {is_new_user}')
            self.logger.info(f'{self._log_key(funcName)}   - 指纹状态: {"✅ 已上传" if fingerprint_uploaded else "❌ 未上传"}')

            # 根据用户类型和指纹上传状态决定 next_step
            self.logger.info(f'{self._log_key(funcName)} 正在决定 next_step...')

            # ========== 根据API版本决定next_step ==========
            if JAZZCASH_VERSION == 'v1.6':
                # v1.6流程：先发送OTP，再上传指纹，最后触发loginStep2
                fingerprint_uploaded = False
                next_step = 'send_otp'
                message = '预登录成功，请先发送OTP，发送后上传指纹'
                self.logger.info(f'{self._log_key(funcName)} v1.6流程: next_step=send_otp，指纹上传延后到OTP发送后')
            else:
                # legacy流程：根据用户类型和指纹状态决定（保持原有逻辑）
                if is_new_user:
                    # 新用户：强制要求上传指纹（不管查询结果如何）
                    fingerprint_uploaded = False  # 强制设置为未上传
                    next_step = 'upload_fingerprint'
                    message = '预登录成功，新用户需要先上传指纹'
                    self.logger.warning(f'{self._log_key(funcName)} 🆕 next_step: upload_fingerprint (新用户强制要求上传指纹，fingerprint_uploaded={fingerprint_uploaded})')
                elif fingerprint_uploaded:
                    # 老用户 + 已上传 → 可以发送OTP
                    next_step = 'send_otp'
                    message = '预登录成功，指纹已上传，可以发送OTP'
                    self.logger.info(f'{self._log_key(funcName)} ✅ next_step: send_otp (老用户指纹已上传，跳过上传)')
                else:
                    # 老用户 + 未上传 → 需要上传
                    next_step = 'upload_fingerprint'
                    message = '预登录成功，指纹未上传，需要先上传指纹'
                    self.logger.warning(f'{self._log_key(funcName)} ⚠️ next_step: upload_fingerprint (老用户指纹未上传，需要上传)')

            result = {
                'status': 'success',
                'message': message,
                'data': {
                    'id': payment_id,
                    'redis_key': redis_key,
                    'expires_in': expire_second,
                    'total_timeout': 120,
                    'is_new_user': is_new_user,
                    'bank_type': self.LOGIN_TYPE,
                    'fingerprint_uploaded': fingerprint_uploaded,  # ⭐ 指纹上传状态
                    'next_step': next_step                      # ⭐ 根据指纹状态决定下一步
                }
            }

            self.logger.info(f'{self._log_key(funcName)} ==========================================')
            self.logger.info(f'{self._log_key(funcName)} 准备返回结果给前端:')
            self.logger.info(f'{self._log_key(funcName)} 返回结果详情:')
            self.logger.info(f'{self._log_key(funcName)}   - status: {result["status"]}')
            self.logger.info(f'{self._log_key(funcName)}   - message: {result["message"]}')
            self.logger.info(f'{self._log_key(funcName)}   - data.id: {result["data"]["id"]}')
            self.logger.info(f'{self._log_key(funcName)}   - data.fingerprint_uploaded: {result["data"]["fingerprint_uploaded"]}')
            self.logger.info(f'{self._log_key(funcName)}   - data.next_step: {result["data"]["next_step"]}')
            self.logger.info(f'{self._log_key(funcName)} 完整返回结果: {result}')
            self.logger.info(f'{self._log_key(funcName)} ========== pre_login_http 执行成功 ==========')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.LoginAttemps, f'{str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            if payment_lock_id and payment_lock_value:
                await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
                self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def send_otp_http(self, data):
        """OTP发送"""
        funcName = 'send_otp_http'
        lockName = 'send_otp'
        self.login_data = data
        payment_lock_id = None
        payment_lock_value = None
        try:
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            # 获取会话数据
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_data = await self._get_session_data(redis_key)

            if not session_data:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不存在')
                self.logger.error(f'{self._log_key(funcName)} 请确保按正确流程调用:')
                self.logger.error(f'{self._log_key(funcName)}    1. pre_login_http (初始化会话)')
                self.logger.error(f'{self._log_key(funcName)}    2. send_otp_http ← 当前步骤')
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')

            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname', 'app_gen_id', 'androidId', 'safetyNetId']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)

            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f'Session data incomplete, missing fields: {', '.join(missing_fields)}')

            # 检查登录锁状态
            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            if session_phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=session_phone)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')

            self.logger.info(f'{self._log_key(funcName)} 成功获取会话数据！')
            self.logger.info(f'{self._log_key(funcName)} === 会话数据详细信息 ===')
            self.logger.info(f'{self._log_key(funcName)} 手机号: {session_data.get('phone', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} 当前状态: {session_data.get('status', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} 目标状态: {LoginStatus.SEND_OTP}')
            self.logger.info(f'{self._log_key(funcName)} app_gen_id: {session_data.get('app_gen_id', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} android_id: {session_data.get('androidId', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} safety_net_id: {session_data.get('safetyNetId', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} authorization存在: {'是' if session_data.get('authorization') else '否'}')
            if session_data.get('authorization'):
                auth_preview = session_data.get('authorization')[:50] + "..." if len(session_data.get('authorization', '')) > 50 else session_data.get('authorization')
                self.logger.info(f'{self._log_key(funcName)} authorization预览: {auth_preview}')

            self.logger.info(f'{self._log_key(funcName)} 会话数据完整性检查通过！')

            # 状态转换 — 支持幂等重发:
            #   preLogin → sendOtp  首次 Send OTP（状态推进）
            #   sendOtp  → sendOtp  Resend OTP（状态保持；只重发 SMS + 记录时间）
            # 其它态（未 pre_login / 已 verify）一律拒绝
            current_status = session_data.get('status', 'UNKNOWN')
            is_resend = (current_status == LoginStatus.SEND_OTP)

            if current_status not in (LoginStatus.PRE_LOGIN, LoginStatus.SEND_OTP):
                self.logger.error(f'{self._log_key(funcName)} 状态转换无效! 当前状态: {current_status}')
                raise NewApiError(ErrorCode.Logined2, f'Invalid status transition, current status: {current_status}')

            if is_resend:
                # Throttle: 同一 session 内两次 send_otp 至少间隔 RESEND_COOLDOWN 秒
                last_send_ts = int(session_data.get('sendOTPTime') or 0)
                now_ts = int(time.time())
                elapsed = now_ts - last_send_ts if last_send_ts else None
                if last_send_ts and elapsed < self.RESEND_COOLDOWN_SECONDS:
                    wait_left = self.RESEND_COOLDOWN_SECONDS - elapsed
                    self.logger.warning(
                        f'{self._log_key(funcName)} resend 节流拒绝: last={last_send_ts}, now={now_ts}, need wait {wait_left}s')
                    raise NewApiError(
                        ErrorCode.PaymentLocked,
                        f'Please wait {wait_left}s before requesting a new OTP',
                    )
                self.logger.info(f'{self._log_key(funcName)} 检测到 resend 请求（当前状态 {current_status}），重新触发 loginStep1')
            else:
                self.logger.info(f'{self._log_key(funcName)} 状态转换验证通过！(preLogin → sendOtp)')

            # 调用API
            api_result = await self._send_otp(session_data)

            # ========== [新增] 处理 loginStep1 的冷却期 ==========
            if api_result.get('status') == 'cooldown':
                # loginStep1 返回冷却期
                self.logger.warning(f'{self._log_key(funcName)} loginStep1 返回冷却期')

                cd_until = api_result.get('cd_until', 0)
                cooldown_msg = api_result.get('message', '账号处于冷却期')

                # 保存冷却期到 session
                if cd_until:
                    await self._update_session_status(
                        redis_key,
                        session_data,
                        session_data.get('status'),  # 保持当前状态不变
                        {'cd_until': cd_until}
                    )

                    cd_time_str = datetime.fromtimestamp(cd_until).strftime('%Y-%m-%d %H:%M:%S')
                    return {
                        'status': 'error',
                        'message': f'账号处于冷却期，请等待至 {cd_time_str}',
                        'data': {
                            'isInCoolDown': True,
                            'cd_until': cd_until,
                            'isNeedReLogin': False,
                            'isNeedChangePin': False,
                            'isNeedFingerPrint': False,
                        }
                    }
                else:
                    return {
                        'status': 'error',
                        'message': f'账号处于冷却期: {cooldown_msg}',
                        'data': {
                            'isInCoolDown': True,
                            'isNeedReLogin': False,
                            'isNeedChangePin': False,
                            'isNeedFingerPrint': False,
                        }
                    }

            # ========== [新增] 处理 loginStep1 的指纹缺失 ==========
            if api_result.get('status') == 'fingerprint_missing':
                # legacy流程：loginStep1 返回指纹缺失
                if JAZZCASH_VERSION == 'legacy':
                    self.logger.warning(f'{self._log_key(funcName)} loginStep1 返回指纹缺失（legacy）')
                    fingerprint_msg = api_result.get('message', '指纹数据不存在，请先上传指纹')

                    return {
                        'status': 'error',
                        'message': fingerprint_msg,
                        'data': {
                            'isInCoolDown': False,
                            'isNeedReLogin': False,
                            'isNeedChangePin': False,
                            'isNeedFingerPrint': True,
                            'next_step': 'upload_fingerprint'  # 提示需要上传指纹
                        }
                    }
                else:
                    # v1.6不应该出现指纹缺失错误
                    self.logger.error(f'{self._log_key(funcName)} v1.6不应该返回指纹缺失错误')
                    raise NewApiError(ErrorCode.SendOTPFail, 'Unexpected fingerprint error in v1.6')

            # ========== 处理成功 ==========
            self.logger.info(
                f'{self._log_key(funcName)} 正在更新会话状态. {current_status} → {LoginStatus.SEND_OTP} (resend={is_resend})')
            await self._update_session_status(
                redis_key, session_data, LoginStatus.SEND_OTP,
                {'sendOTPTime': int(time.time()), 'resend_count': int(session_data.get('resend_count', 0)) + (1 if is_resend else 0)}
            )

            self.logger.info(f'{self._log_key(funcName)} 完成')

            result = {
                'status': 'success',
                'message': 'OTP发送成功，请上传指纹后再验证OTP',
                'data': {
                    'next_status': LoginStatus.SEND_OTP,
                    'next_step': 'upload_fingerprint',
                    'phone': session_data.get('phone'),
                    'instruction': f'请查看手机 {session_data.get('phone')} 收到的OTP验证码短信；收到OTP后先上传指纹，再提交OTP验证'
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def verify_otp_http(self, data):
        """OTP验证"""
        funcName = 'verify_otp_http'
        lockName = 'verify_otp'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id', 'otp']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            otp = data.get('otp', '').strip()
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)

            if not otp:
                raise NewApiError(ErrorCode.MissingParams, 'OTP code cannot be empty')

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            # 获取会话数据
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_data = await self._get_session_data(redis_key)

            if not session_data:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不存在')
                self.logger.error(f'{self._log_key(funcName)} 请确保按正确流程调用:')
                self.logger.error(f'{self._log_key(funcName)}   1. pre_login_http (初始化会话)')
                self.logger.error(f'{self._log_key(funcName)}   2. send_otp_http (OTP发送)')
                self.logger.error(f'{self._log_key(funcName)}   3. verify_otp_http ← 当前步骤')
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call send_otp_http first')

            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)

            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f'Session data incomplete, missing fields: {', '.join(missing_fields)}')

            # 检查登录锁状态
            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            if session_phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=session_phone)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')

            self.logger.info(f'{self._log_key(funcName)} 成功获取会话数据！')
            self.logger.info(f'{self._log_key(funcName)} === 会话数据详细信息 ===')
            self.logger.info(f'{self._log_key(funcName)} 手机号: {session_data.get('phone', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} 当前状态: {session_data.get('status', 'UNKNOWN')}')
            self.logger.info(f'{self._log_key(funcName)} 目标状态: {LoginStatus.VERIFY_OTP}')

            self.logger.info(f'{self._log_key(funcName)} 会话数据完整性检查通过！')

            # 验证状态转换
            status_check = await self._validate_status_transition(
                session_data, session_data.get('status', 'UNKNOWN'), LoginStatus.VERIFY_OTP, f'{self._log_key(funcName)}'
            )
            if not status_check['valid']:
                current_status = session_data.get('status', 'UNKNOWN')
                self.logger.error(f'{self._log_key(funcName)} 状态转换无效! 期望状态: {LoginStatus.VERIFY_OTP}, 需要状态: {LoginStatus.SEND_OTP}, 当前状态: {current_status}')
                raise NewApiError(ErrorCode.Logined2, f'Invalid status transition, current status: {current_status}')

            self.logger.info(f'{self._log_key(funcName)} 状态转换验证通过！')

            if not session_data.get('fingerprint_uploaded') or not session_data.get('fingerprint_path'):
                self.logger.error(f'{self._log_key(funcName)} 指纹尚未上传，拒绝触发loginStep2')
                raise NewApiError(ErrorCode.UploadFingerPrint, 'Please upload fingerprint before OTP verification')

            # 调用API
            api_result_verify_otp = await self._verify_otp(session_data, otp)

            # ========== [新增] 处理 loginStep2 (verify_otp) 的冷却期 ==========
            if api_result_verify_otp.get('status') == 'cooldown':
                # OTP验证返回冷却期（和 EasyPaisa 一致：返回 success）
                self.logger.warning(f'{self._log_key(funcName)} loginStep2 返回冷却期，但OTP验证成功')

                cd_until = api_result_verify_otp.get('cd_until', 0)
                cooldown_msg = api_result_verify_otp.get('message', '账号处于冷却期')

                # ⭐ 重要：保存 Payment 记录（和 EasyPaisa 一致）
                fingerprint_path = session_data.get('fingerprint_path')
                self.logger.info(f'{self._log_key(funcName)} 冷却期也需要保存 Payment，指纹路径: {fingerprint_path}')

                # 从session中获取name参数（name已是必需参数）
                name = session_data.get('name', '')
                self.logger.info(f'{self._log_key(funcName)} 从session获取name: {name}')

                real_payment_id = await self._save_payment(session_data, name=name, fingerprint_path=fingerprint_path)

                if not real_payment_id:
                    raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')

                # 如果是新用户，更新 redis_key
                is_new_user = session_data.get('is_new_user', False)
                if is_new_user:
                    self.logger.info(f'{self._log_key(funcName)} 新用户，更新 redis_key')
                    await self.redis.delete(redis_key)
                    redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id)

                # 保存冷却期到 session，状态更新为 LOGIN_SUCCESSFUL
                if cd_until:
                    se_until = await self._update_session_status(
                        redis_key,
                        session_data,
                        LoginStatus.LOGIN_SUCCESSFUL,  # ⭐ 状态改为成功
                        {
                            'cd_until': cd_until,
                            'id': real_payment_id,
                            'redis_key': redis_key,
                            'real_payment_id': real_payment_id,
                        }
                    )

                    cd_time_str = datetime.fromtimestamp(cd_until).strftime('%Y-%m-%d %H:%M:%S')
                    self.logger.warning(f'{self._log_key(funcName)} OTP验证成功，但账号冷却至 {cd_time_str}')

                    return {
                        'status': 'success',  # ⭐ 改为 success（和 EasyPaisa 一致）
                        'message': 'OTP验证成功',
                        'data': {
                            'serv_gen_id': api_result_verify_otp.get('data', {}).get('requestId', ''),
                            'cd_until': cd_until,
                            'se_until': se_until,
                            'next_step': 'active_account'  # ⭐ 提示需要继续激活
                        }
                    }
                else:
                    # 无冷却期时间，返回基本成功信息
                    se_until = await self._update_session_status(
                        redis_key,
                        session_data,
                        LoginStatus.LOGIN_SUCCESSFUL,
                        {
                            'id': real_payment_id,
                            'redis_key': redis_key,
                            'real_payment_id': real_payment_id,
                        }
                    )

                    return {
                        'status': 'success',
                        'message': 'OTP验证成功',
                        'data': {
                            'serv_gen_id': api_result_verify_otp.get('data', {}).get('requestId', ''),
                            'cd_until': 0,
                            'se_until': se_until,
                            'next_step': 'active_account'
                        }
                    }

            session_data['serv_gen_id'] = api_result_verify_otp['data'].get('requestId')

            # 调用 secondLogin 验证账户状态并获取账号信息
            api_result_verify_acct = await self._verify_account(session_data)

            # 处理账号验证结果
            if api_result_verify_acct.IsSuccess:
                # ✅ 账户正常：仅保存基础信息，不提取账户详情
                self.logger.info(f'{self._log_key(funcName)} 账户验证成功，保存基础信息...')

                # ✅ 改：保存基础信息（包含指纹路径，但不保存 account_entire、account_accno、account_iban）
                # 从 session_data 中获取指纹路径（在 upload_fingerprint_http 中已保存）
                fingerprint_path = session_data.get('fingerprint_path')
                self.logger.info(f'{self._log_key(funcName)} 指纹路径: {fingerprint_path}')

                # 从session中获取name参数（name已是必需参数）
                name = session_data.get('name', '')
                self.logger.info(f'{self._log_key(funcName)} 从session获取name: {name}')

                real_payment_id = await self._save_payment(session_data, name=name, fingerprint_path=fingerprint_path)

                if real_payment_id:
                    is_new_user = session_data.get('is_new_user', False)
                    if is_new_user:
                        # 如果是新用户，payment_id 从 phone 变为了数据库生成的 ID
                        self.logger.info(f'{self._log_key(funcName)} 新用户，更新 redis_key: {redis_key} → pre_login_{bankname}_{real_payment_id}')
                        await self.redis.delete(redis_key)
                        redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id)

                    # ✅ 建立登录进程锁 - 防止N分钟内重复登录

                    # 1. Payment ID锁 - 防止用户用payment_id重复登录
                    login_on_payment_key = self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)
                    await self.redis.setex(login_on_payment_key, self.lock_time_login_duplicate_avoid, 1)

                    # 2. 手机号锁 - 防止用户用手机号重复登录
                    login_on_phone_key = self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=session_phone)
                    await self.redis.setex(login_on_phone_key, self.lock_time_login_duplicate_avoid, 1)

                    self.logger.info(f'{self._log_key(funcName)} Payment锁: {login_on_payment_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')
                    self.logger.info(f'{self._log_key(funcName)} Phone锁: {login_on_phone_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')

                    # 计算时间戳
                    now_ts = time.time()

                    # ✅ 改：状态更新为 LOGIN_SUCCESSFUL（不是 ACTIVE_SUCCESSFUL）
                    self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态. {session_data.get('status')} → {LoginStatus.LOGIN_SUCCESSFUL}')
                    se_until = await self._update_session_status(
                        redis_key, session_data, LoginStatus.LOGIN_SUCCESSFUL,
                        {
                            'id': real_payment_id,
                            'redis_key': redis_key,
                            'real_payment_id': real_payment_id,
                            'serv_gen_id': api_result_verify_otp['data'].get('requestId'),
                            'selected_upi': session_phone,
                            'upi_list': [ session_phone ],
                            'completion_time': int(now_ts),
                            'cd_until': 0,  # 账户正常，无冷却期
                        }
                    )

                    self.logger.info(f'{self._log_key(funcName)} OTP验证完成！')

                    # ✅ 改：返回简化信息（不返回账户信息）
                    result = {
                        'status': 'success',
                        'message': 'OTP验证成功',
                        'data': {
                            'serv_gen_id': api_result_verify_otp['data'].get('requestId'),
                            'se_until': se_until,
                            'next_step': 'active_account'  # ⚠️ 新增：提示需要继续
                        }
                    }
                    self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
                    return result
                else:
                    raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')

            # ========== 处理 secondLogin 返回的冷却期 ==========
            elif api_result_verify_acct.IsInCoolDown:
                # ⚠️ 账户处于冷却期（和 EasyPaisa 一致：保存 Payment 并返回 success）
                self.logger.warning(f'{self._log_key(funcName)} verify_otp 中 secondLogin 返回冷却期，但OTP验证成功')

                # cd_until 已经在 _verify_account 中计算并保存到 session_data 了
                cd_until = session_data.get('cd_until', 0)

                # 保存基础信息（和 EasyPaisa 一样：即使冷却期也保存 Payment）
                fingerprint_path = session_data.get('fingerprint_path')
                self.logger.info(f'{self._log_key(funcName)} 指纹路径: {fingerprint_path}')

                # 从session中获取name参数（name已是必需参数）
                name = session_data.get('name', '')
                self.logger.info(f'{self._log_key(funcName)} 从session获取name: {name}')

                real_payment_id = await self._save_payment(session_data, name=name, fingerprint_path=fingerprint_path)

                if real_payment_id:
                    is_new_user = session_data.get('is_new_user', False)
                    if is_new_user:
                        await self.redis.delete(redis_key)
                        redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id)

                    # 建立登录进程锁（和 EasyPaisa 一样：即使冷却期也设置锁）
                    login_on_payment_key = self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)
                    await self.redis.setex(login_on_payment_key, self.lock_time_login_duplicate_avoid, 1)

                    login_on_phone_key = self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=session_phone)
                    await self.redis.setex(login_on_phone_key, self.lock_time_login_duplicate_avoid, 1)

                    self.logger.info(f'{self._log_key(funcName)} Payment锁: {login_on_payment_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')
                    self.logger.info(f'{self._log_key(funcName)} Phone锁: {login_on_phone_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')

                    # 计算时间戳
                    now_ts = time.time()

                    # 更新会话状态为 LOGIN_SUCCESSFUL（和 EasyPaisa 一样）
                    se_until = await self._update_session_status(
                        redis_key, session_data, LoginStatus.LOGIN_SUCCESSFUL,
                        {
                            'id': real_payment_id,
                            'redis_key': redis_key,
                            'real_payment_id': real_payment_id,
                            'cd_until': cd_until,
                            'completion_time': int(now_ts),
                        }
                    )

                    # ⭐ 返回 success（和 EasyPaisa 一致）
                    self.logger.warning(f'{self._log_key(funcName)} OTP验证成功，账号冷却至 {datetime.fromtimestamp(cd_until).strftime("%Y-%m-%d %H:%M:%S") if cd_until else "未知"}')

                    result = {
                        'status': 'success',  # ⭐ 改为 success
                        'message': 'OTP验证成功',
                        'data': {
                            'serv_gen_id': api_result_verify_otp['data'].get('requestId'),
                            'cd_until': cd_until,  # ⭐ 返回冷却期时间（前端/后续流程会用到）
                            'se_until': se_until,
                            'next_step': 'active_account'  # ⭐ 提示需要继续激活
                        }
                    }
                    self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
                    return result
                else:
                    raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')

            else:
                # ❌ 账户状态异常（需要重新登录、修改PIN等）
                self.logger.error(f'{self._log_key(funcName)} 账户状态异常')
                self.logger.error(f'{self._log_key(funcName)} IsNeedRelogin={api_result_verify_acct.IsNeedRelogin}')
                self.logger.error(f'{self._log_key(funcName)} IsNeedChangePin={api_result_verify_acct.IsNeedChangePin}')

                raise NewApiError(
                    ErrorCode.VerifyAccount,
                    f'Account verification failed, please login again or contact support'
                )
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def active_account_http(self, data):
        """
        账号激活（EasyPaisa 风格 + JazzCash 特色）

        状态要求：LOGIN_SUCCESSFUL（在 verify_otp_http 之后）

        功能：
        1. 调用 secondLogin 验证账户状态
        2. 从 secondLogin 响应中提取账户信息（IBAN 等）
        3. 建立登录进程锁（payment锁 + phone锁）
        4. 更新数据库（保存完整账户信息）
        5. 更新状态为 ACTIVE_SUCCESSFUL

        JazzCash 特色：
        - 直接从 secondLogin 提取账户信息（不需要调用 queryAccountList）
        - 账号 = 手机号

        参数：
        - bankname: jazzcash
        - payment_id: 从 verify_otp_http 返回的 id

        返回格式：
        成功：{'status': 'success', 'message': '账号激活成功', 'data': {'account_iban': ..., 'account_accno': ...}}
        冷却期：{'status': 'error', 'message': '账号处于冷却期', 'data': {'isInCoolDown': True, 'cd_until': ...}}
        需要上传指纹：{'status': 'error', 'message': '账号状态异常', 'data': {'isNeedFingerPrint': True}}
        """
        funcName = 'active_account_http'
        lockName = 'active_account'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            # ========== 3. 检查账号状态 ==========
            if not await self._check_pamynet_status(payment_id):
                raise NewApiError(ErrorCode.ActiveAccount, f'This account is already activated. Please do not activate it again.')

            # ========== 4. 获取会话数据 ==========
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_data = await self._get_session_data(redis_key)

            # 若 redis->pre_login 不存在，则重新走【用户登录】流程
            if not session_data:
                self.logger.error(f'{redis_key} 会话数据不存在, 需要重新登录')
                return {
                    'status': 'error',
                    'message': '会话数据不存在, 需要重新登录',
                    'data': {
                        'isInCoolDown': False,
                        'isNeedReLogin': True,
                        'isNeedChangePin': False,
                        'isNeedFingerPrint': False,
                    }
                }

            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)

            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f'Session data incomplete, missing fields: {', '.join(missing_fields)}')

            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            session_status = session_data.get('status', 'UNKNOWN')

            # ========== 5. 状态检查 ==========
            if session_status == LoginStatus.ACTIVE_SUCCESSFUL:
                return {
                    'status': 'success',
                    'message': '账号已经激活成功，请勿重复激活'
                }

            # ⭐ 关键：必须是 LOGIN_SUCCESSFUL 状态（在 verify_otp 之后）
            if session_status != LoginStatus.LOGIN_SUCCESSFUL:
                raise NewApiError(ErrorCode.SessionNotExist, 'please call pre_login_http first')

            # ========== 6. 调用 secondLogin 验证账号状态 ==========
            self.logger.info(f'{self._log_key(funcName)} 调用 secondLogin 验证账号状态...')
            api_result_verify_acct = await self._verify_account(session_data)

            # ========== 7. 处理成功 ==========
            if api_result_verify_acct.IsSuccess:
                self.logger.info(f'{self._log_key(funcName)} 账号状态正常')

                # ========== JazzCash 特色：从 secondLogin 提取账户信息 ==========
                # JazzCash: 直接从 secondLogin 响应中获取账号信息（不需要调用 queryAccountList）
                # 注意：JazzCash secondLogin 返回的数据有两层嵌套
                # response_data['data']['data'] 才是真正的账户信息
                secondlogin_outer_data = api_result_verify_acct.data
                secondlogin_account_data = secondlogin_outer_data.get('data', {})  # 提取内层 data

                account_iban = secondlogin_account_data.get('iban', '')
                account_accno = session_phone  # JazzCash 的账号就是手机号
                account_entire_json = json.dumps(secondlogin_account_data, ensure_ascii=False)  # 保存内层账户数据

                self.logger.info(f'{self._log_key(funcName)} 账号信息: IBAN={account_iban}, AccNo={account_accno}')
                self.logger.info(f'{self._log_key(funcName)} businessDetails: {secondlogin_account_data.get("businessDetails", {})}')

                # ========== 8. 建立登录进程锁 - 防止N分钟内重复登录 ==========

                # 1. Payment ID锁 - 防止用户用payment_id重复登录
                login_on_payment_key = self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)
                await self.redis.setex(login_on_payment_key, self.lock_time_login_duplicate_avoid, 1)

                # 2. 手机号锁 - 防止用户用手机号重复登录
                login_on_phone_key = self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=session_phone)
                await self.redis.setex(login_on_phone_key, self.lock_time_login_duplicate_avoid, 1)

                self.logger.info(f'{self._log_key(funcName)} Payment锁: {login_on_payment_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')
                self.logger.info(f'{self._log_key(funcName)} Phone锁: {login_on_phone_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')

                # ========== 9. 更新状态 ==========
                self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态. {session_data.get('status')} → {LoginStatus.ACTIVE_SUCCESSFUL}')
                await self._update_session_status(
                    redis_key, session_data, LoginStatus.ACTIVE_SUCCESSFUL
                )

                # ========== 10. 更新数据库（保存完整账户信息）==========
                self.logger.info(f'{self._log_key(funcName)} 正在更新payment...')
                await self._update_payment(session_payment_id, session_data, account_entire=account_entire_json, account_accno=account_accno, account_iban=account_iban)

                # ========== 11. MySQL 三最终态是唯一资格源 ==========
                self.logger.info(
                    f'{self._log_key(funcName)} 不写旧 Redis 接单投影: payment_id={session_payment_id}'
                )

                # ========== 12. 返回成功 ==========
                self.logger.info(f'{self._log_key(funcName)} 账号激活成功')
                result = {
                    'status': 'success',
                    'message': '账号激活成功',
                    'data': {
                        'account_iban': account_iban,
                        'account_accno': account_accno
                    }
                }
                self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
                return result

            # ========== 13. 处理各种异常状态 ==========
            # ========== 处理冷却期 ==========
            if api_result_verify_acct.IsInCoolDown:
                cd_until = session_data.get('cd_until', 0)
                self.logger.warning(f'{self._log_key(funcName)} ========== secondLogin 返回冷却期 ==========')
                self.logger.error(f'{self._log_key(funcName)} 冷却中，cd_until={cd_until}')

                if cd_until:
                    cd_time_str = datetime.fromtimestamp(cd_until).strftime('%Y-%m-%d %H:%M:%S')
                    self.logger.error(f'{self._log_key(funcName)} 冷却至: {cd_time_str}')
                    result = {
                        'status': 'error',
                        'message': f'账号处于冷却期，请等待至 {cd_time_str}',
                        'data': {
                            'isInCoolDown': True,
                            'cd_until': cd_until,
                            'isNeedReLogin': False,
                            'isNeedChangePin': False,
                            'isNeedFingerPrint': False,
                        }
                    }
                else:
                    result = {
                        'status': 'error',
                        'message': '账号处于冷却期',
                        'data': {
                            'isInCoolDown': True,
                            'isNeedReLogin': False,
                            'isNeedChangePin': False,
                            'isNeedFingerPrint': False,
                        }
                    }
                self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
                return result

            # ========== 处理需要重新登录 ==========
            if api_result_verify_acct.IsNeedRelogin:
                self.logger.error(f'{self._log_key(funcName)} 需要重新登录，清理登录锁和会话')
                login_on_payment_key = self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)
                await self.redis.delete(login_on_payment_key)
                login_on_phone_key = self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=session_phone)
                await self.redis.delete(login_on_phone_key)
                await self.redis.delete(redis_key)

            # ========== 处理需要修改PIN ==========
            if api_result_verify_acct.IsNeedChangePin:
                self.logger.error(f'{self._log_key(funcName)} 需要修改PIN')

            # ========== 处理需要上传指纹 ==========
            if api_result_verify_acct.IsNeedFingerPrint:
                self.logger.error(f'{self._log_key(funcName)} 需要上传指纹')

            # ========== 返回账号状态异常 ==========
            result = {
                'status': 'error',
                'message': '账号状态异常',
                'data': {
                    'isInCoolDown': api_result_verify_acct.IsInCoolDown,
                    'isNeedReLogin': api_result_verify_acct.IsNeedRelogin,
                    'isNeedChangePin': api_result_verify_acct.IsNeedChangePin,
                    'isNeedFingerPrint': api_result_verify_acct.IsNeedFingerPrint,
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.ActiveAccount, f'Account active failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def second_login_http(self, data):
        """已绑定 JazzCash 账号二次登录。"""
        funcName = 'second_login_http'
        lockName = 'second_login'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {", ".join(missing_fields)}')

            bankname = data['bankname']
            payment_id = str(data['payment_id'])
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)

            lock_result = await self._get_payment_interface_lock(payment_id, lockName)
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')

            session_data = await self._get_session_data(redis_key)
            if not session_data:
                session_data = await self._build_bound_second_login_session(bankname, payment_id)

            current_status = session_data.get('status')
            if current_status == LoginStatus.ACTIVE_SUCCESSFUL:
                return {
                    'status': 'success',
                    'message': '账号已经激活成功，请勿重复激活',
                    'data': {'phase': LoginStatus.ACTIVE_SUCCESSFUL}
                }

            api_result_verify_acct = await self._verify_account(session_data)

            if api_result_verify_acct.IsSuccess:
                secondlogin_outer_data = api_result_verify_acct.data or {}
                secondlogin_account_data = secondlogin_outer_data.get('data', secondlogin_outer_data)
                account_iban = secondlogin_account_data.get('iban', '')
                account_entire_json = json.dumps(secondlogin_account_data, ensure_ascii=False)

                await self._update_session_status(redis_key, session_data, LoginStatus.LOGIN_SUCCESSFUL)
                await self._update_session_status(redis_key, session_data, LoginStatus.ACTIVE_SUCCESSFUL)
                await self._update_payment(
                    payment_id,
                    session_data,
                    account_entire=account_entire_json,
                    account_iban=account_iban,
                )

                return {
                    'status': 'success',
                    'message': '二次登录成功',
                    'data': {
                        'phase': LoginStatus.ACTIVE_SUCCESSFUL,
                        'payment_id': payment_id,
                        'account_iban': account_iban,
                    }
                }

            if api_result_verify_acct.IsInCoolDown:
                return {
                    'status': 'error',
                    'message': '当前处于冷却期',
                    'data': {
                        'code': 'SL_COOLDOWN',
                        'phase': 'inCooldown',
                        'cd_until': session_data.get('cd_until', 0),
                    }
                }

            if api_result_verify_acct.IsNeedChangePin:
                return {
                    'status': 'error',
                    'message': '需要修改 PIN',
                    'data': {
                        'code': 'SL_NEEDS_PIN_CHANGE',
                        'phase': 'awaitingPinChange',
                    }
                }

            if api_result_verify_acct.IsNeedRelogin:
                return {
                    'status': 'error',
                    'message': '会话已过期，请重新开始',
                    'data': {
                        'code': 'SL_SESSION_EXPIRED',
                        'phase': 'needsRelogin',
                    }
                }

            return {
                'status': 'error',
                'message': '上游错误',
                'data': {
                    'code': 'SL_UPSTREAM_ERROR',
                    'phase': 'failed',
                }
            }
        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            raise NewApiError(ErrorCode.VerifyAccount, f'Second login failed: {str(e)}')
        finally:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def change_pin_http(self, data):
        """PIN修改 - JazzCash 不支持此功能"""
        funcName = 'change_pin_http'
        self.logger.warning(f'{self._log_key(funcName)} JazzCash 不支持PIN修改功能')
        raise NewApiError(ErrorCode.Unsupported, 'JazzCash does not support PIN change via this interface.')

        # 以下代码保留但不会执行（JazzCash 不支持此功能）
        lockName = 'change_pin'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id', 'pin']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            pin = data['pin']
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            # 获取会话数据
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_data = await self._get_session_data(redis_key)

            if not session_data:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不存在')
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')

            if session_data.get('status', 'UNKNOWN') != LoginStatus.LOGIN_SUCCESSFUL:
                raise NewApiError(ErrorCode.SessionNotExist, 'please call pre_login_http first')

            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)

            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f'Session data incomplete, missing fields: {', '.join(missing_fields)}')

            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            session_pin_times = session_data.get('pin_times', 0)

            # 不限制次数了
            # if session_pin_times >= PIN_CHANGE_ATTEMPTS_MAXIMUM:
            #     self.logger.error(f'{redis_key} PIN Changing failed, reach maximum attempts time')
            #     return {
            #         'status': 'error',
            #         'message': f'PIN Changing failed, reach maximum attempts time',
            #         'data': {
            #             'maximum': PIN_CHANGE_ATTEMPTS_MAXIMUM,
            #             'current': session_pin_times
            #         }
            #     }

            session_pin_times = session_pin_times + 1

            # 调用API
            await self._change_pin(session_data, pin)

            await self._save_payment(session_data, pin=pin)

            self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态')
            await self._update_session_status(
                redis_key, session_data, session_data.get('status'),
                {
                    'pin_times': session_pin_times,
                    'pinCode': pin
                }
            )

            result = {
                'status': 'success',
                'message': 'PIN修改成功',
                'data': {
                    'maximum': PIN_CHANGE_ATTEMPTS_MAXIMUM,
                    # 'current': session_pin_times
                    'current': 0
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.ChangePin, f'PIN Changing failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def upload_fingerprint_http(self, data):
        """
        指纹上传（必需功能 - 根据 JazzCash legacy 文档）

        状态要求：PRE_LOGIN（在 pre_login_http 之后）

        功能：
        1. 上传指纹ZIP文件到云端
        2. 保存指纹数据到数据库
        3. 记录上传次数

        JazzCash legacy 流程（根据文档）：
        - pre_login（调用 isLogined）
          ├─ cloud_exists = false → upload_fingerprint（必需，上传指纹）→ send_otp
          └─ cloud_exists = true  → send_otp（云机已存在，直接发OTP）

        参数：
        - bankname: jazzcash
        - payment_id: 从 pre_login_http 返回的 id
        - file: ZIP文件（最大16MB）

        上传域名：https://jazzcashbusiness.zpay.today/upload_data
        app参数：appjazzcash_merchant

        ⚠️ 注意：根据文档Line 117："JazzCashBusiness要求强制使用指纹进行登录，请提前上传指纹数据"
        """
        funcName = 'upload_fingerprint_http'
        lockName = 'upload_fingerprint'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            file = data.pop("file", None)
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)

            # ⚠️ 测试模式：跳过文件检查，直接使用固定指纹文件
            if USE_TEST_FINGERPRINT:
                self.logger.warning(f'{self._log_key(funcName)} ⚠️ 测试模式：使用固定指纹文件 {TEST_FINGERPRINT_PATH}')
                file = None  # 不使用前端上传的文件
            else:
                if not file:
                    raise NewApiError(ErrorCode.MissingParams, 'file cannot be empty')

                # 检查文件后缀
                if file["content_type"] not in ["application/zip", "application/x-zip-compressed", "multipart/x-zip"]:
                    raise NewApiError(ErrorCode.MissingParams, 'file ext should be .zip')

                # 检查文件大小, 1MB
                if len(file["body"]) > 1024 * 1024 * 16:
                    raise NewApiError(ErrorCode.MissingParams, 'file size can not over 16MB')

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            # ========== 获取会话数据 ==========
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_data = await self._get_session_data(redis_key)

            if not session_data:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不存在')
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')

            # ⭐ 关键：允许在 PRE_LOGIN 或 SEND_OTP 状态下上传指纹
            # - PRE_LOGIN: pre_login 发现没有指纹，直接上传
            # - SEND_OTP: send_otp 返回 code 403（指纹缺失），上传后重新发送OTP
            current_status = session_data.get('status', 'UNKNOWN')
            allowed_statuses = [LoginStatus.PRE_LOGIN, LoginStatus.SEND_OTP]
            if current_status not in allowed_statuses:
                self.logger.error(f'{self._log_key(funcName)} 状态错误: {current_status}, 期望 {allowed_statuses}')
                raise NewApiError(ErrorCode.SessionNotExist, f'Invalid status: {current_status}, expected one of {allowed_statuses}')

            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)

            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f'Session data incomplete, missing fields: {', '.join(missing_fields)}')

            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            session_fg_times = session_data.get('fg_times', 0)

            self.logger.info(f'{self._log_key(funcName)} 会话状态: {current_status}, 上传次数: {session_fg_times}')

            # 不限制次数了
            # if session_fg_times >= FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM:
            #     self.logger.error(f'{redis_key} FingerPrint Upload failed, reach maximum attempts time')
            #     return {
            #         'status': 'error',
            #         'message': f'FingerPrint Upload failed, reach maximum attempts time',
            #         'data': {
            #             'maximum': FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM,
            #             'current': session_fg_times
            #         }
            #     }

            session_fg_times = session_fg_times + 1

            # ========== 上传指纹到云端 & 保存到本地 ==========
            if USE_TEST_FINGERPRINT:
                # ⚠️ 测试模式：读取固定路径的指纹文件并上传
                self.logger.warning(f'{self._log_key(funcName)} ⚠️ 测试模式：读取固定指纹文件 {TEST_FINGERPRINT_PATH}')

                # 读取固定路径的 ZIP 文件
                import os
                if not os.path.exists(TEST_FINGERPRINT_PATH):
                    raise NewApiError(ErrorCode.MissingParams, f'测试指纹文件不存在: {TEST_FINGERPRINT_PATH}')

                with open(TEST_FINGERPRINT_PATH, 'rb') as f:
                    test_file_body = f.read()

                test_file_name = os.path.basename(TEST_FINGERPRINT_PATH)
                self.logger.info(f'{self._log_key(funcName)} 读取到测试文件: {test_file_name}, 大小: {len(test_file_body)} bytes')

                # 上传到云端
                self.logger.info(f'{self._log_key(funcName)} 正在上传指纹到云端: {test_file_name}')
                await self._upload_fingerprint(session_data, test_file_name, test_file_body)

                # 验证上传是否成功
                self.logger.info(f'{self._log_key(funcName)} 正在验证指纹上传是否成功...')
                verify_result = await self._check_fingerprint_uploaded(session_phone)
                if verify_result.get('uploaded'):
                    self.logger.info(f'{self._log_key(funcName)} ✅ 指纹上传验证成功')
                else:
                    self.logger.warning(f'{self._log_key(funcName)} ⚠️ 指纹上传验证失败: {verify_result.get("message", "未知原因")}')

                # 保存到本地
                self.logger.info(f'{self._log_key(funcName)} 正在保存指纹到本地...')
                fingerprint_path = await self._save_fingerprint(session_data, test_file_body, session_bankname, session_payment_id, session_phone)
                self.logger.info(f'{self._log_key(funcName)} 指纹文件已保存: {fingerprint_path}')
            else:
                # 正常模式：上传到云端并保存到本地
                self.logger.info(f'{self._log_key(funcName)} 正在上传指纹到云端: {file["filename"]}')
                await self._upload_fingerprint(session_data, file["filename"], file["body"])

                # 验证上传是否成功
                self.logger.info(f'{self._log_key(funcName)} 正在验证指纹上传是否成功...')
                verify_result = await self._check_fingerprint_uploaded(session_phone)
                if verify_result.get('uploaded'):
                    self.logger.info(f'{self._log_key(funcName)} ✅ 指纹上传验证成功')
                else:
                    self.logger.warning(f'{self._log_key(funcName)} ⚠️ 指纹上传验证失败: {verify_result.get("message", "未知原因")}')

                self.logger.info(f'{self._log_key(funcName)} 正在保存指纹到本地...')
                fingerprint_path = await self._save_fingerprint(session_data, file["body"], session_bankname, session_payment_id, session_phone)
                self.logger.info(f'{self._log_key(funcName)} 指纹文件已保存: {fingerprint_path}')

            # ========== 更新会话（记录上传次数和指纹路径）==========
            self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态，记录上传次数: {session_fg_times}')
            await self._update_session_status(
                redis_key, session_data, session_data.get('status'),
                {
                    'fg_times': session_fg_times,
                    'fingerprint_path': fingerprint_path,  # 保存指纹路径到 session
                    'fingerprint_uploaded': True,
                    'fingerprint_check_time': int(time.time()),
                }
            )

            self.logger.info(f'{self._log_key(funcName)} 指纹上传成功！')
            result = {
                'status': 'success',
                'message': '指纹上传成功，请继续验证OTP',
                'data': {
                    'maximum': FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM,
                    # 'current': session_fg_times
                    'current': 0,
                    'next_step': 'verify_otp'  # 告诉前端下一步应该调用 verify_otp
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.UploadFingerPrint, f'FingerPrint Upload failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def query_accts_http(self, data):
        """账户查询 - JazzCash 不支持此功能"""
        funcName = 'query_accts_http'
        self.logger.warning(f'{self._log_key(funcName)} JazzCash 不支持账户查询功能')
        raise NewApiError(ErrorCode.Unsupported, 'JazzCash does not support account query. Account info is already included in activation response.')

        # 以下代码保留但不会执行（JazzCash 不支持此功能）
        lockName = 'query_accts'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            existing_payment = await self._query_payment(payment_id)
            if not existing_payment:
                raise NewApiError(ErrorCode.QueryAccts, f'Query Accounts failed, payment does not exist')

            if existing_payment.get('status', '') != 1:
                raise NewApiError(ErrorCode.QueryAccts, f'Please active your account before this action')

            # 调用API
            api_result = await self._query_accts(existing_payment['phone'])

            accts_json = api_result.get('data')
            accts_data = json.loads(accts_json)
            if len(accts_data) == 0:
                raise NewApiError(ErrorCode.QueryAccts, f'can not find any account')

            self.logger.info(f'{self._log_key(funcName)} 正在更新payment...')
            await self._update_payment(existing_payment['id'], {'phone': existing_payment['phone']}, account_entire=accts_json)

            result = {
                'status': 'success',
                'data': {
                    'account_selected': existing_payment.get('account_accno', ''),
                    'account_entire': [item for item in accts_data if item.get('accountStatus', '') == "ACTIVE"]
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.ChangePin, f'Query Accounts failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def select_acct_http(self, data):
        """账户选择 - JazzCash 不支持此功能"""
        funcName = 'select_acct_http'
        self.logger.warning(f'{self._log_key(funcName)} JazzCash 不支持账户选择功能')
        raise NewApiError(ErrorCode.Unsupported, 'JazzCash does not support account selection. Default account is used automatically.')

        # 以下代码保留但不会执行（JazzCash 不支持此功能）
        lockName = 'select_acct'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')

            # 验证必要参数
            required_fields = ['bankname', 'payment_id', 'accno']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            accno = data['accno']

            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error

            existing_payment = await self._query_payment(payment_id)
            if not existing_payment:
                raise NewApiError(ErrorCode.SelectAccts, f'Select Account failed, payment does not exist')

            if existing_payment.get('status', '') != 1:
                raise NewApiError(ErrorCode.SelectAccts, f'Please active your account before this action')

            raw = existing_payment.get('account_entire')
            accounts = json.loads(raw) if raw else []
            iban = next((acc['IBAN'] for acc in accounts if acc['accno'] == accno), None)
            if not iban:
                raise NewApiError(ErrorCode.SelectAccts, f'IBAN can not be found')

            self.logger.info(f'{self._log_key(funcName)} 正在更新payment...')
            await self._update_payment(existing_payment['id'], {'phone': existing_payment['phone']}, account_accno=accno, account_iban=iban)

            result = {
                'status': 'success',
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            self.logger.error(f'异常类型: {type(e).__name__}')
            self.logger.error(f'异常信息: {str(e)}')
            import traceback
            self.logger.error(f'完整异常堆栈:')
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f'   {line}')
            raise NewApiError(ErrorCode.SelectAccts, f'Select Account failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def payment_status_http(self, data):
        funcName = 'payment_status_http'
        self.login_data = data
        try:
            # 验证必要参数
            required_fields = ['bankname', 'payment_ids']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {', '.join(missing_fields)}')

            # 获取参数
            bankname = data['bankname']
            payment_ids = data['payment_ids']
            paymentIDArray = [x.strip() for x in payment_ids.split(",") if x.strip()]

            objs = []
            for payment_id in paymentIDArray:
                redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
                session_data = await self._get_session_data(redis_key)
                if not session_data:
                    continue

                # 获取 upi_list
                upi_list = session_data.get('upi_list', [])
                # 如果 upi_list 为空，使用 phone 作为默认值
                if not upi_list and session_data.get('phone'):
                    upi_list = [session_data.get('phone')]

                obj = {
                    "payment_id": payment_id,
                    "phone": session_data.get('phone', ''),
                    "cd_until": session_data.get('cd_until', 0),
                    "upi_list": upi_list,  # ⭐ 添加 upi_list
                }
                objs.append(obj)

            result = {
                'status': 'success',
                'message': 'success',
                'datas' : objs
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result
        except Exception as e:
            raise NewApiError(ErrorCode.MissingParams, f'{str(e)}')

    # ================== 内部辅助方法 ==================
    async def _send_otp(self, session_data):
        funcName = 'OTP发送'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        # 构建请求数据
        request_data = self._build_send_otp_request(session_data)

        if ISTEST:
            status = 100
            status_desc = ''
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            response_data = self._decode_indus_response(funcName, response.text)

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending decode failed')

            # 分析响应状态
            status = response_data.get('code')
            status_desc = response_data.get('msg', '无状态描述')

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')

        # ========== 处理冷却期 (code 501 + responseCode='JC-CPS-COOL-T01') ==========
        if status == 501:
            inner_data = response_data.get('data', {})
            response_code = inner_data.get('responseCode', '')

            if response_code == 'JC-CPS-COOL-T01':
                # 冷却期
                self.logger.warning(f'{self._log_key(funcName)} loginStep1 返回冷却期 code 501, responseCode={response_code}')
                response_msg = inner_data.get('message_en', status_desc)

                # 计算冷却期结束时间
                cd_until = self._parse_cooldown_time(response_msg)

                return {
                    'status': 'cooldown',
                    'message': response_msg,
                    'cd_until': cd_until,
                    'data': response_data.get('data', {})
                }
            else:
                # 其他 501 错误
                self.logger.error(f'{self._log_key(funcName)} loginStep1 失败 code 501, responseCode={response_code}')
                raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending failed: {status_desc}')

        # ========== 处理指纹缺失 (code 403) ==========
        if status == 403:
            self.logger.warning(f'{self._log_key(funcName)} loginStep1 返回指纹缺失 code 403')
            return {
                'status': 'fingerprint_missing',
                'message': status_desc,
                'data': response_data.get('data', {})
            }

        # ========== 处理成功 ==========
        if status in [ 100, 200 ]:
            return {
                'status': 'success',
                'message': 'OTP发送成功'
            }
        else:
            raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending failed: {status_desc}')

    async def _verify_otp(self, session_data, otp):
        funcName = 'OTP验证'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        # 构建请求数据
        request_data = self._build_verify_otp_request(session_data, otp)

        if ISTEST:
            status = 200
            status_desc = ''
            serv_gen_id = '123123'
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            # 解析响应
            response_data = self._decode_indus_response(funcName, response.text)

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification decode failed')

            # 分析响应状态
            status = response_data.get('code')
            status_desc = response_data.get('msg', '无状态描述')
            serv_gen_id = ((response_data or {}).get('data') or {}).get('requestId', '')

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}, serv_gen_id: {serv_gen_id}')

        # ========== 处理冷却期 (code 501 + responseCode='JC-CPS-COOL-T01') ==========
        if status == 501:
            inner_data = response_data.get('data', {})
            response_code = inner_data.get('responseCode', '')

            if response_code == 'JC-CPS-COOL-T01':
                # 冷却期
                self.logger.warning(f'{self._log_key(funcName)} OTP验证返回冷却期 code 501, responseCode={response_code}')
                response_msg = inner_data.get('message_en', status_desc)

                # 计算冷却期结束时间
                cd_until = self._parse_cooldown_time(response_msg)

                return {
                    'status': 'cooldown',
                    'message': response_msg,
                    'cd_until': cd_until,
                    'data': response_data.get('data', {})
                }
            else:
                # 其他 501 错误
                self.logger.error(f'{self._log_key(funcName)} OTP验证失败 code 501, responseCode={response_code}')
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {status_desc}')

        # ========== 处理 500 错误 ==========
        if status == 500:
            inner_data = response_data.get('data', {})
            response_code = inner_data.get('responseCode', '')
            self.logger.error(f'{self._log_key(funcName)} OTP验证失败 code 500, responseCode={response_code}')
            raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {status_desc}')

        # ========== 处理成功 ==========
        if status in [ 100, 200 ]:
            return {
                'status': 'success',
                'message': 'OTP验证成功',
                'data': {'serv_gen_id': serv_gen_id}
            }
        else:
            raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {status_desc}')

    async def _is_logined(self, session_data):
        """
        查询云机实体分配情况

        根据 JazzCash legacy 文档：
        - 用途：当前account_id未分配云机实体时应当触发loginStep首先分配云机
        - 返回 code=200, data=true → 云机在线
        - 返回 code=403, data=false → 云机不存在
        """
        funcName = 'isLogined查询'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        # 构建请求数据
        request_data = self._build_is_logined_request(session_data)

        if ISTEST:
            # 测试模式：默认云机不存在
            return {
                'code': 403,
                'msg': 'isLogined查询测试',
                'data': False
            }

        response = self.retry_make_request(
            method='POST',
            url=url,
            data=request_data,
        )

        # 记录响应的详细信息
        self._log_response(funcName, response)

        if not response:
            self.logger.error(f'{self._log_key(funcName)} HTTP请求失败')
            # 容错：默认返回云机不存在
            return {
                'code': 403,
                'msg': 'isLogined查询失败',
                'data': False
            }

        status_code = response.status_code

        if status_code != 200:
            self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
            # 容错：默认返回云机不存在
            return {
                'code': 403,
                'msg': f'HTTP错误: {status_code}',
                'data': False
            }

        self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

        response_data = self._decode_indus_response(funcName, response.text)

        if not response_data:
            self.logger.error(f'{self._log_key(funcName)} 解码失败!')
            # 容错：默认返回云机不存在
            return {
                'code': 403,
                'msg': 'isLogined解码失败',
                'data': False
            }

        # 返回响应数据
        code = response_data.get('code')
        msg = response_data.get('msg', '')
        data = response_data.get('data', False)

        self.logger.info(f'{self._log_key(funcName)} 云机状态: code={code}, data={data}, msg={msg}')

        return {
            'code': code,
            'msg': msg,
            'data': data
        }

    async def _check_fingerprint_uploaded(self, phone):
        """
        查询指纹是否已上传

        接口: GET https://jazzcashbusiness.zpay.today/is_data_uploaded?app=appjazzcash_merchant&phone=03499328834
        返回: {"status": "ok"} 或 {"status": "error"}
        """
        funcName = '查询指纹上传状态'

        self.logger.info(f'{self._log_key(funcName)} ========== 开始查询指纹上传状态 ==========')
        self.logger.info(f'{self._log_key(funcName)} 查询参数: phone={phone}')

        url = self.API_ENDPOINTS['fingerprint_check_url']
        params = {
            'app': 'jazzcash_merchant',
            'phone': phone
        }

        # 构建完整 URL
        full_url = f"{url}?app={params['app']}&phone={params['phone']}"
        self.logger.info(f'{self._log_key(funcName)} 请求方法: GET')
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {full_url}')
        self.logger.info(f'{self._log_key(funcName)} 请求参数: {params}')

        try:
            self.logger.info(f'{self._log_key(funcName)} 正在发送HTTP请求...')

            # 使用 GET 请求查询（直接拼接参数到 URL）
            response = self.retry_make_request(
                method='GET',
                url=full_url,  # ← 使用完整 URL（已包含查询参数）
                data=None
            )

            self.logger.info(f'{self._log_key(funcName)} HTTP请求已发送，等待响应...')

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                self.logger.error(f'{self._log_key(funcName)} ❌ HTTP请求失败: response is None')
                # 容错：默认返回未上传
                result = {
                    'uploaded': False,
                    'status': 'error',
                    'message': '查询失败'
                }
                self.logger.error(f'{self._log_key(funcName)} 返回结果: {result}')
                return result

            status_code = response.status_code
            self.logger.info(f'{self._log_key(funcName)} HTTP状态码: {status_code}')

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} ❌ HTTP状态码错误: {status_code}')
                # 容错：默认返回未上传
                result = {
                    'uploaded': False,
                    'status': 'error',
                    'message': f'HTTP错误: {status_code}'
                }
                self.logger.error(f'{self._log_key(funcName)} 返回结果: {result}')
                return result

            self.logger.info(f'{self._log_key(funcName)} ✅ HTTP请求成功! 状态码: {status_code}')

            # 解析响应（JSON格式）
            try:
                self.logger.info(f'{self._log_key(funcName)} 开始解析响应数据...')

                # 获取原始响应文本
                response_text = response.text
                self.logger.info(f'{self._log_key(funcName)} 响应原始文本: {response_text}')

                # 解析为JSON
                response_data = response.json()
                self.logger.info(f'{self._log_key(funcName)} 响应JSON数据: {response_data}')
                self.logger.info(f'{self._log_key(funcName)} 响应数据类型: {type(response_data).__name__}')

                # ⚠️ 修复：支持两种返回格式
                # 格式1: 布尔值 true/false
                # 格式2: 字典 {"status": "ok"} 或 {"status": "error"}

                if isinstance(response_data, bool):
                    # 布尔值格式：true 表示已上传，false 表示未上传
                    uploaded = response_data
                    status = 'ok' if uploaded else 'error'
                    self.logger.info(f'{self._log_key(funcName)} 响应格式: 布尔值, uploaded={uploaded}')
                elif isinstance(response_data, dict):
                    # 字典格式：提取 status 字段
                    status = response_data.get('status', 'error')
                    uploaded = (status == 'ok')
                    self.logger.info(f'{self._log_key(funcName)} 响应格式: 字典, status={status}, uploaded={uploaded}')
                else:
                    # 未知格式，默认未上传
                    self.logger.warning(f'{self._log_key(funcName)} ⚠️ 未知响应格式: {type(response_data).__name__}')
                    uploaded = False
                    status = 'error'

                self.logger.info(f'{self._log_key(funcName)} 最终解析结果: uploaded={uploaded}, status={status}')

                if uploaded:
                    self.logger.info(f'{self._log_key(funcName)} ✅ 指纹已上传 (phone={phone})')
                else:
                    self.logger.warning(f'{self._log_key(funcName)} ⚠️ 指纹未上传 (phone={phone})')

                result = {
                    'uploaded': uploaded,
                    'status': status,
                    'message': '已上传' if uploaded else '未上传'
                }
                self.logger.info(f'{self._log_key(funcName)} 最终返回结果: {result}')
                self.logger.info(f'{self._log_key(funcName)} ========== 查询完成 ==========')
                return result

            except Exception as e:
                self.logger.error(f'{self._log_key(funcName)} ❌ 解析响应失败: {str(e)}')
                self.logger.error(f'{self._log_key(funcName)} 异常类型: {type(e).__name__}')
                import traceback
                self.logger.error(f'{self._log_key(funcName)} 异常堆栈: {traceback.format_exc()}')

                # 尝试记录原始响应内容
                try:
                    response_text = response.text if response else 'None'
                    self.logger.error(f'{self._log_key(funcName)} 原始响应内容: {response_text}')
                except:
                    self.logger.error(f'{self._log_key(funcName)} 无法获取原始响应内容')

                # 容错：默认返回未上传
                result = {
                    'uploaded': False,
                    'status': 'error',
                    'message': f'解析失败: {str(e)}'
                }
                self.logger.error(f'{self._log_key(funcName)} 返回结果: {result}')
                return result

        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} ❌ 请求异常: {str(e)}')
            self.logger.error(f'{self._log_key(funcName)} 异常类型: {type(e).__name__}')
            import traceback
            self.logger.error(f'{self._log_key(funcName)} 异常堆栈: {traceback.format_exc()}')

            # 容错：默认返回未上传
            result = {
                'uploaded': False,
                'status': 'error',
                'message': f'查询异常: {str(e)}'
            }
            self.logger.error(f'{self._log_key(funcName)} 返回结果: {result}')
            self.logger.error(f'{self._log_key(funcName)} ========== 查询异常结束 ==========')
            return result

    async def _verify_account(self, session_data) -> AccountStatus:
        baseName = '账号验证'
        funcName = f'{baseName}'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        isNeedFingerPring = True
        result = AccountStatus()

        if ISTEST:
            # raise NewApiError(ErrorCode.Retry, 'unstable network, please try agagin')
            # result.IsSuccess = True
            result.IsInCoolDown = False
            result.IsNeedRelogin = False
            result.IsNeedChangePin = False
            isNeedFingerPring = False
        else:
            funcName = f'{baseName} - 基本信息'
            # region verify_account
            # 构建请求数据
            request_data = self._build_verify_account_request(session_data)

            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.VerifyAccount, 'Account verification request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.VerifyAccount, 'Account verification request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            response_data = self._decode_indus_response(funcName, response.text)

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.VerifyAccount, 'Account verification decode failed')

            # 分析响应状态
            status = response_data.get('code')
            status_desc = response_data.get('msg', '无状态描述')  # JazzCash 的 msg 在顶层，不在 data 中

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')

            # JazzCash: 保存完整的 secondLogin 响应数据（包含 IBAN 等账号信息）
            data_field = response_data.get('data', {})

            # ⚠️ 修复：如果 data 是字符串，需要先解析为字典
            if isinstance(data_field, str):
                try:
                    result.data = json.loads(data_field)
                except json.JSONDecodeError:
                    self.logger.error(f'{self._log_key(funcName)} 解析 data 字段失败: {data_field}')
                    result.data = {}
            else:
                result.data = data_field

            self.logger.info(f'{self._log_key(funcName)} 保存账号数据: {json.dumps(result.data, ensure_ascii=False)}')
            # endregion verify_account

            # JazzCash 错误码处理（根据 doc_JazzCashMerchant legacy.txt）
            if status == 501:
                # code 501 需要区分：冷却期 vs 账号异常
                # ⚠️ 直接使用已经解析好的 result.data
                inner_data = result.data if result.data else {}

                response_code = inner_data.get('responseCode', '')
                response_msg = inner_data.get('message_en', status_desc)

                if response_code == 'JC-CPS-COOL-T01':
                    # 冷却期（参考 EasyPaisa：只设置标志，不计算时间）
                    # cd_until 已在 verify_otp_http 时计算并保存到 session_data
                    self.logger.warning(f'{self._log_key(funcName)} 账号处于冷却期 code 501: {response_msg}')
                    result.IsInCoolDown = True
                else:
                    # 其他 501 错误 - 账号异常
                    self.logger.error(f'{self._log_key(funcName)} 账号异常 code 501, responseCode={response_code}: {status_desc}')
                    raise NewApiError(ErrorCode.VerifyAccount, f'Account invalid (code 501): {status_desc}')

            elif status == 503:
                # 网络错误，需要重试
                raise NewApiError(ErrorCode.Retry, f'Network error, please try again: {status_desc}')

            elif status == 401:
                # 会话失效
                self.logger.warning(f'{self._log_key(funcName)} 会话失效 code 401: {status_desc}')
                result.IsNeedRelogin = True

            elif status not in [ 100, 200 ]:
                # 其他错误码统一处理
                self.logger.error(f'{self._log_key(funcName)} 验证失败 code {status}: {status_desc}')

                # JazzCash 错误状态码细分处理（不包含冷却期）
                # if status_desc in [ 'URM40008' ]:  # JazzCash 不返回冷却期错误码
                #     result.IsInCoolDown = True
                if status_desc in [ 'URM20060' ]:
                    result.IsNeedRelogin = True
                if status_desc in [ 'URM20008', 'URM20017' ]:
                    result.IsNeedChangePin = True

                # 默认需要重新登录（如果没有其他特殊状态）
                if not result.IsNeedChangePin:
                    result.IsNeedRelogin = True

            # JazzCash 不需要指纹验证
            isNeedFingerPring = False

        result.IsNeedFingerPrint = isNeedFingerPring

        if not result.IsInCoolDown and not result.IsNeedRelogin and not result.IsNeedChangePin and not result.IsNeedFingerPrint:
            result.IsSuccess = True
        return result

    async def _verify_fingerprint(self, session_data) -> bool:
        funcName = '指纹验证'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        # 构建请求数据
        request_data = self._build_verify_fingerprint_request(session_data)

        if ISTEST:
            status = 200
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.VerifyFingerPrint, 'FingerPrint verification request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.VerifyFingerPrint, 'FingerPrint verification request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            response_data = self._decode_indus_response(funcName, response.text)

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.VerifyFingerPrint, 'FingerPrint verification decode failed')

            # 分析响应状态
            status = response_data.lower()
            status_desc = response_data.lower()

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')
        if status == 'true':
            return True
        else:
            return False

    async def _change_pin(self, session_data, pin):
        funcName = 'PIN修改'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        # 构建请求数据
        request_data = self._build_change_pin_request(session_data, pin)

        if ISTEST:
            status = 200
            status_desc = ''
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.ChangePin, f'PIN Changing request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.ChangePin, f'PIN Changing request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            response_data = self._decode_indus_response(funcName, response.text)

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.ChangePin, f'PIN Changing decode failed')

            # 分析响应状态
            status = response_data.get('code')
            status_desc = response_data.get('msg', '无状态描述')

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')
        if status not in [ 100, 200 ]:
            raise NewApiError(ErrorCode.ChangePin, f'PIN Changing failed: {status_desc}')

    async def _upload_fingerprint(self, session_data, file_name, file_body):
        funcName = '指纹上传'

        url = self.API_ENDPOINTS['fingerprint_upload_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        data, files = self._build_upload_fingerprint_request(session_data, file_name, file_body)

        if ISTEST:
            status = 'ok'
            status_desc = ''
        else:
            response = self.retry_make_request(
                method='',
                url=url,
                data=data,
                files=files,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.UploadFingerPrint, f'FingerPrint upload request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.UploadFingerPrint, f'FingerPrint upload request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            response_data = response.text

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.UploadFingerPrint, f'FingerPrint upload decode failed')

            # 分析响应状态
            status = response_data
            status_desc = response_data

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')
        if status != 'ok':
            raise NewApiError(ErrorCode.UploadFingerPrint, f'FingerPrint upload failed: {status_desc}')

    async def _query_accts(self, phone):
        funcName = '账户查询'

        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')

        # 构建请求数据
        request_data = self._build_query_accts_request(phone)

        if ISTEST:
            # JazzCash 测试数据（注意：JazzCash 不支持此接口，此数据仅为测试保留）
            data = [
                {
                    "accno": "03001234567",
                    "accountFri": "FRI:03001234567/JC",
                    "accountKey": "icLQm3g6KW7HvLXP0SKaTw==",
                    "accountLevel": "3",
                    "accountProfile": "L1",
                    "accountName": "JazzCash Wallet",
                    "accountNameUr": "جاز کیش والیٹ",
                    "accountBalance": "20763.00",
                    "accountStatus": "ACTIVE",
                    "eligibleForAda": "false",
                    "IBAN": "PK12JAZZ0000000012345678"
                },
                {
                    "accno": "03001234568",
                    "accountFri": "FRI:03001234568/JC",
                    "accountKey": "icLQm3g6KW7HvLXP0SKaTw==",
                    "accountLevel": "3",
                    "accountProfile": "L1",
                    "accountName": "JazzCash Account",
                    "accountNameUr": "جاز کیش اکاؤنٹ",
                    "accountBalance": "500.00",
                    "accountStatus": "ACTIVE",
                    "eligibleForAda": "false",
                    "IBAN": "PK12JAZZ0000000012345679"
                }
            ]

            status = 200
            status_desc = json.dumps(data)
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
                # proxies=await self._get_proxy_for_request(session_data) # 获取代理配置
            )

            # 记录响应的详细信息
            self._log_response(funcName, response)

            if not response:
                raise NewApiError(ErrorCode.QueryAccts, f'Query Accounts request failed')

            status_code = response.status_code

            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.ChangePin, f'Query Accounts request failed')

            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')

            response_data = self._decode_indus_response(funcName, response.text)

            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.ChangePin, f'Query Accounts decode failed')

            # 分析响应状态
            status = response_data.get('code')
            status_desc = json.dumps(response_data.get("data") or [])

            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')
        if status in [ 100, 200 ]:
            return {
                'status': 'success',
                'data': status_desc
            }
        else:
            raise NewApiError(ErrorCode.ChangePin, f'Query Accounts failed: {response_data.get('msg')}')

    def _query_accts_default(self, accounts):
        # JazzCash 不使用此方法（不支持 queryAccountList 接口）
        # 保留此方法仅为兼容性
        record = next((acc for acc in accounts if acc.get("accountName") == "JazzCash Wallet"), None)
        return record

    # ================== 请求构建方法 ==================
    def _build_is_logined_request(self, session_data):
        """构建 isLogined 请求"""
        funcName = '构建isLogined查询'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')

        request_msg = {
            "account_id": phone
        }

        self.logger.info(f'{self._log_key(funcName)} payload数据: {json.dumps(request_msg, ensure_ascii=False)}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['is_logined'], request_msg)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _build_send_otp_request(self, session_data):
        funcName = '构建OTP发送'

        # 获取基础参数
        phone = session_data.get('phone')
        pinCode = session_data.get('pinCode')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, pin: ******')

        # JazzCash 使用 msisdn 和 mpin 字段
        request_msg = {
            "account_id": phone,
            "msisdn": phone,      # JazzCash 使用 msisdn 而不是 phone
            "mpin": pinCode       # JazzCash 使用 mpin 而不是 pwd
        }

        self.logger.info(f'{self._log_key(funcName)} payload数据: {json.dumps(request_msg, ensure_ascii=False)}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['send_otp'], request_msg)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _build_verify_otp_request(self, session_data, otp):
        funcName = '构建OTP验证'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, otp: {otp}')

        request_msg = {
            "account_id": phone,
            "otpcode": otp,
            "should_verify_otpcode": False,
            "should_verify_fingerprint": True,
        }
        self.logger.info(
            f'{self._log_key(funcName)} v1.6模式: should_verify_otpcode=False, '
            f'should_verify_fingerprint=True'
        )

        self.logger.info(f'{self._log_key(funcName)} payload数据: {json.dumps(request_msg, ensure_ascii=False)}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['verify_otp'], request_msg)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _build_verify_account_request(self, session_data):
        funcName = '构建账号验证'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')

        request_msg = {
            "account_id": phone,
        }

        self.logger.info(f'{self._log_key(funcName)} payload数据: {json.dumps(request_msg, ensure_ascii=False)}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['verify_account'], request_msg)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _build_verify_fingerprint_request(self, session_data):
        funcName = '构建指纹验证'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')

        request_msg = {
            "account_id": phone,
        }

        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['verify_fingerprint'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _build_change_pin_request(self, session_data, newPin):
        funcName = '构建账号验证'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, pin: {newPin}')

        request_msg = {
            "account_id": phone,
            "phone": phone,
            "pwd": newPin,
        }

        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['change_pin'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _build_upload_fingerprint_request(self, session_data, file_name, file_body):
        funcName = '构建指纹上传'

        # 获取基础参数
        phone = session_data.get('phone')

        self.logger.info(f'{self._log_key(funcName)} 构建请求所需参数: app: jazzcash_merchant, phone: {phone}, file: ***')

        data = {
            "app": "jazzcash_merchant",  # 固定值
            "phone": phone,
        }

        files = {
            "file": (file_name, file_body, "application/zip"),
        }

        # request_msg = aiohttp.FormData()
        # request_msg.add_field("app", "jazzcash")
        # request_msg.add_field("phone", phone)
        # request_msg.add_field("file", file_body, filename=file_name, content_type="application/zip")

        self.logger.info(f'{self._log_key(funcName)} 完成')

        return data, files

    def _build_query_accts_request(self, phone):
        funcName = '构建账户查询'

        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')

        request_msg = {
            "account_id": phone,
        }

        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')

        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['query_acct_list'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 字段: {list(encoded_msg.keys()) if isinstance(encoded_msg, dict) else 'form-body'}')

        return encoded_msg

    def _parse_cooldown_time(self, cooldown_msg: str) -> int:
        """
        计算冷却期结束时间戳

        JazzCash 的冷却期消息不包含具体时间信息，因此使用默认冷却时长 CDSCOPE（2小时）。
        参考 jazzcash_副本.py 的实现。

        参数：
        - cooldown_msg: 冷却期消息（仅用于日志记录）

        返回：Unix时间戳 (int) = 当前时间 + 2小时
        """
        try:
            # 使用默认冷却时长：2小时（CDSCOPE = 7200秒）
            current_time = int(time.time())
            cd_until = current_time + CDSCOPE

            cd_time_str = datetime.fromtimestamp(cd_until).strftime('%Y-%m-%d %H:%M:%S')
            self.logger.info(f'冷却期计算: 当前时间={time.strftime("%Y-%m-%d %H:%M:%S")}, 冷却至={cd_time_str}, 冷却时长={CDSCOPE}秒(2小时)')
            if cooldown_msg:
                self.logger.info(f'冷却期原始消息: {cooldown_msg}')

            return cd_until

        except Exception as e:
            self.logger.error(f'解析冷却期时间失败: {str(e)}')
            # 出错时返回默认值
            return int(time.time()) + CDSCOPE

    def _encode_indus_request(self, funcName, action: str, payload: dict) -> dict:
        funcName = '消息编码'
        try:
            result = build_form_body(action, payload, APIKEY, APISECRET)
            safe_payload = mask_sensitive_payload(payload)
            self.logger.info(
                f'{self._log_key(funcName)} 加密成功，action: {action}, '
                f'payload: {safe_payload}, sign: {result.get("sign")}'
            )
            return result
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return {}

    def _decode_indus_response(self, funcName, response_data):
        funcName = funcName + ' 消息解码'
        try:
            result = decode_response(response_data)
            self.logger.info(f'{self._log_key(funcName)} 解码后: {result}')
            return result
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}, raw data: {response_data}', exc_info=True)
            return response_data if isinstance(response_data, dict) else {}

    # =========================== 数据库操作方法 ===========================
    async def _get_bank_type_id(self, bankname):
        funcName = '获取银行类型ID'
        try:
            normalized_bankname = self.BANK_NAME_MAPPING.get(bankname.lower(), bankname.upper())

            # 查询银行类型ID
            with self.handler.db_orm.sessionmaker() as session:
                bank_type = session.query(BankType).filter(
                    BankType.name == normalized_bankname
                ).first()

                if bank_type:
                    bank_type_id = bank_type.id
                    return bank_type_id
                else:
                    self.logger.warning(f'{self._log_key(funcName)} 失败, 未找到银行类型: {normalized_bankname}')
                    return None
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _check_payment(self, bankname, phone, partner_id):
        funcName = '检查是否存在现有payment记录'
        try:
            self.logger.info(f'{self._log_key(funcName)} 参数: partner_id={partner_id}, bankname={bankname}, phone={phone}')

            # 获取银行类型ID
            bank_type_id = await self._get_bank_type_id(bankname)
            if not bank_type_id:
                return None

            # 查询现有记录（Paytm模式：一个手机号只能有一条记录，不区分partner_id）
            with self.handler.db_orm.sessionmaker() as session:
                existing_payment = session.query(Payment
                ).filter(
                    Payment.bank_type == bank_type_id,
                    Payment.bank_type_id == bank_type_id,
                    Payment.phone == phone
                ).first()

                if existing_payment:
                    payment_info = {
                        'id': existing_payment.id,
                        'pin': existing_payment.pin,
                        'bank_type': existing_payment.bank_type,
                        'phone': existing_payment.phone,
                        'upi': existing_payment.upi,
                        'user_id': existing_payment.user_id,
                        'status': existing_payment.status,
                        'time_create': existing_payment.created_at.isoformat() if existing_payment.created_at else None
                    }
                    return payment_info
                else:
                    self.logger.info(f'{self._log_key(funcName)} 未找到')
            return None
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    def _build_bound_prelogin_session(
        self,
        *,
        bankname,
        payment_id,
        phone,
        original_phone,
        password,
        pin,
        name,
        user_id,
        bound_payment,
    ):
        return {
            'id': payment_id,
            'partner_id': user_id,
            'phone': phone,
            'original_phone': original_phone,
            'status': LoginStatus.SECOND_LOGIN_READY,
            'status_history': [LoginStatus.SECOND_LOGIN_READY],
            'time': int(time.time()),
            'try_count': 0,
            'bankname': bankname,
            'password': password,
            'pinCode': pin or bound_payment.get('pin'),
            'name': name or bound_payment.get('name', ''),
            'is_new_user': False,
            'last_status_change': int(time.time()),
            'last_request_time': int(time.time()),
            'account_entire': bound_payment.get('account_entire'),
            'account_accno': bound_payment.get('account_accno'),
            'account_iban': bound_payment.get('account_iban'),
            'qr_channel': bound_payment.get('channel') or '1003',
        }

    async def _query_bound_payment_for_current_partner(self, bankname, payment_id):
        funcName = '查询当前码商绑定JazzCash payment'
        bank_type_id = await self._get_bank_type_id(bankname)
        if not bank_type_id:
            raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Bank type not found for: {bankname}')

        with self.handler.db_orm.sessionmaker() as session:
            payment = session.query(Payment).filter(
                Payment.id == payment_id,
                Payment.bank_type_id == bank_type_id,
            ).first()

        if not payment:
            raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Payment record not found: {payment_id}')

        current_partner_id = int(getattr(self.handler.current_user, 'id', 0) or 0)
        owner_partner_id = int(getattr(payment, 'user_id', 0) or 0)
        if owner_partner_id != current_partner_id:
            self.logger.warning(
                f'{self._log_key(funcName)} 码商归属不匹配: payment_id={payment_id}, '
                f'current_partner={current_partner_id}, owner_partner={owner_partner_id}'
            )
            raise NewApiError('10402', 'UPI already occupied by another user')

        return payment

    async def _build_bound_second_login_session(self, bankname, payment_id):
        payment = await self._query_bound_payment_for_current_partner(bankname, payment_id)
        phone = getattr(payment, 'phone', None)
        if not phone:
            raise NewApiError(ErrorCode.PaymentPhoneMismatch, f'Phone number missing for payment {payment_id}')

        session_data = {
            'id': str(payment_id),
            'partner_id': getattr(payment, 'user_id', None),
            'phone': phone,
            'original_phone': phone,
            'status': LoginStatus.SECOND_LOGIN_READY,
            'status_history': [LoginStatus.SECOND_LOGIN_READY],
            'time': int(time.time()),
            'try_count': 0,
            'bankname': bankname,
            'pinCode': getattr(payment, 'pin', None),
            'password': getattr(payment, 'net_trade_pw', None),
            'name': getattr(payment, 'name', '') or '',
            'is_new_user': False,
            'last_status_change': int(time.time()),
            'last_request_time': int(time.time()),
            'account_entire': getattr(payment, 'account_entire', None),
            'account_accno': getattr(payment, 'account_accno', None),
            'account_iban': getattr(payment, 'account_iban', None),
            'qr_channel': getattr(payment, 'channel', None) or '1003',
        }

        is_logined = await self._is_logined(session_data)
        if is_logined.get('data') is not True:
            raise NewApiError(
                'JAZZCASH_CLOUD_NOT_LOGGED',
                'Bound JazzCash account is not assigned to cloud machine; reset manually before second login'
            )
        return session_data

    async def _query_payment(self, payment_id):
        funcName = '查询payment'
        try:
            self.logger.info(f'{self._log_key(funcName)} 参数: payment_id={payment_id}')

            # 查询现有记录
            with self.handler.db_orm.sessionmaker() as session:
                existing_payment = session.query(Payment
                ).filter(
                    Payment.id == payment_id,
                ).first()

                if existing_payment:
                    payment_info = {
                        'id': existing_payment.id,
                        'pin': existing_payment.pin,
                        'bank_type': existing_payment.bank_type,
                        'phone': existing_payment.phone,
                        'upi': existing_payment.upi,
                        'user_id': existing_payment.user_id,
                        'status': existing_payment.status,
                        'certified': existing_payment.certified,
                        'manual_status': existing_payment.manual_status,
                        'wallet_status': getattr(existing_payment, 'wallet_status', 0),
                        'collection_status': getattr(existing_payment, 'collection_status', 0),
                        'payout_status': getattr(existing_payment, 'payout_status', 0),
                        'time_create': existing_payment.created_at.isoformat() if existing_payment.created_at else None,
                        'account_entire': existing_payment.account_entire,
                        'account_accno': existing_payment.account_accno,
                        'account_iban': existing_payment.account_iban,
                        'channel': existing_payment.channel,  # 添加 channel 字段
                    }
                    return payment_info
                else:
                    self.logger.info(f'{self._log_key(funcName)} 未找到')
            return None
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _save_payment(self, session_data, name=None, pin=None, fingerprint_path=None,
                           account_entire=None, account_accno=None, account_iban=None):
        """保存/更新 payment 信息

        参数:
            session_data: 会话数据
            name: 账户名称
            pin: PIN码
            fingerprint_path: 指纹文件路径
            account_entire: 完整账号信息JSON（新增，用于一次性保存完整信息）
            account_accno: 账号号码（新增）
            account_iban: IBAN账号（新增）
        """
        funcName = '保存payment数据到数据库'
        try:
            # 从session_data获取必要信息
            bankname = session_data['bankname']
            phone = session_data['phone']
            partner_id = session_data.get('partner_id')

            self.logger.info(f'{self._log_key(funcName)} 参数: partner_id={partner_id}, bankname={bankname}, phone={phone}')

            existing_payment = await self._check_payment(bankname, phone, partner_id)
            if not existing_payment:
                return await self._create_payment(session_data, name, fingerprint_path, account_entire, account_accno, account_iban)
            else:
                return await self._update_payment(existing_payment['id'], session_data, name, pin, fingerprint_path,
                                                 account_entire, account_accno, account_iban)
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _create_payment(self, session_data, name, fingerprint_path=None, account_entire=None, account_accno=None, account_iban=None):
        funcName = '创建新的payment记录'
        try:
            bankname = session_data['bankname']
            phone = session_data['phone']
            password = session_data.get('password', '')
            pin = session_data.get('pinCode')
            partner_id = session_data.get('partner_id')

            self.logger.info(f'{self._log_key(funcName)} 参数: partner_id={partner_id}, bankname={bankname}, phone={phone}, upi={phone}')

            # 获取银行类型ID
            bank_type_id = await self._get_bank_type_id(bankname)

            # 构建payment数据（使用正确的Python模型字段名）
            payment_data = {
                'bank_type': bank_type_id,  # 存储银行名称字符串
                'bank_type_id': bank_type_id,   # 存储银行类型ID
                'phone': phone,
                'pin': pin,  # 将MPIN存储在pin字段
                'net_trade_pw': password,  # 同时也存储在net_trade_pw字段
                'user_id': partner_id,  # 对应数据库中的partner_id字段
                'status': 0,  # 可用状态
                'certified': 1,  # 激活、认证状态
                'remarks': None,  # 清理remarks字段，新建时清空之前的错误信息
                'upi': phone,
                'upi_list': ','.join([ phone ]),  # UPI列表，逗号分隔
                'fingerprint_path': fingerprint_path,  # 指纹文件路径（新增支持）
                'account_entire': account_entire,   # 第三方账号-完整的（新增支持）
                'account_accno': account_accno,     # 第三方账号-选中的accno（新增支持）
                'account_iban': account_iban,       # 第三方账号-选中的iban（新增支持）
                'channel': '1003',  # JazzCash 默认只支持渠道 1003
                'wallet_status': 0,
                'collection_status': 0,
                'payout_status': 0,
                # created_at字段有默认值，不需要手动设置
            }

            # 只有当name不为空时才设置name字段
            if name:
                payment_data['name'] = name
                self.logger.info(f'{self._log_key(funcName)} 设置 name: {name}')

            # 记录指纹路径（如果有）
            if fingerprint_path:
                self.logger.info(f'{self._log_key(funcName)} 设置 fingerprint_path: {fingerprint_path}')

            # 使用SQLAlchemy插入数据
            with self.handler.db_orm.sessionmaker() as session:
                new_payment = Payment(**payment_data)
                session.add(new_payment)
                session.commit()
                payment_id = new_payment.id

            self.logger.info(f'{self._log_key(funcName)} 数据库插入成功: ID={payment_id}')
            return payment_id

        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _update_payment(self, existing_payment_id, session_data, name=None, pin=None, fingerprint_path=None, account_entire=None, account_accno=None, account_iban=None):
        funcName = '更新现有payment记录'
        try:
            phone = session_data.get('phone', '')

            # 构建更新数据（使用正确的Python模型字段名）
            update_data = {
                'remarks': None,  # 清理remarks字段，重新登录时清空之前的错误信息
                'upi': phone,
                'upi_list': ','.join([ phone ]),  # UPI列表，逗号分隔
            }

            # 只有 channel 为空时才赋值（避免覆盖已有渠道配置）
            existing_payment_info = await self._query_payment(existing_payment_id)
            if existing_payment_info and not existing_payment_info.get('channel'):
                update_data['channel'] = '1003'
                self.logger.info(f'{self._log_key(funcName)} channel 为空，更新为: 1003')

            if name:
                update_data['name'] = name
                self.logger.info(f'{self._log_key(funcName)} 更新 name: {name}')

            if pin:
                update_data['pin'] = pin
                self.logger.info(f'{self._log_key(funcName)} 更新 pin: {pin}')

            if fingerprint_path:
                update_data['fingerprint_path'] = fingerprint_path
                self.logger.info(f'{self._log_key(funcName)} 更新 fingerprint_path: {fingerprint_path}')

            if account_entire:
                update_data['account_entire'] = account_entire
                self.logger.info(f'{self._log_key(funcName)} 更新 account_entire: {account_entire}')

            if account_accno:
                update_data['account_accno'] = account_accno
                self.logger.info(f'{self._log_key(funcName)} 更新 account_accno: {account_accno}')

            if account_iban:
                update_data['account_iban'] = account_iban
                self.logger.info(f'{self._log_key(funcName)} 更新 account_iban: {account_iban}')

            isOn = 1 if session_data.get('status', '') == LoginStatus.ACTIVE_SUCCESSFUL else 0
            if isOn == 1:
                update_data['status'] = 1
                final_status = calculate_final_status(
                    status=1,
                    certified=(existing_payment_info or {}).get('certified', 1),
                    manual_status=(existing_payment_info or {}).get('manual_status', 0),
                    wallet_status=1,
                )
                update_data.update(final_status)
                self.logger.info(f'{self._log_key(funcName)} 更新 status: 1, final_status: {final_status}')

            # 使用SQLAlchemy更新数据
            with self.handler.db_orm.sessionmaker() as session:
                session.execute(
                    update(Payment).
                    where(Payment.id == existing_payment_id).
                    values(**update_data)
                )
                session.commit()

            self.logger.info(f'{self._log_key(funcName)} 数据库更新成功: ID={existing_payment_id}')
            return existing_payment_id

        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _check_pamynet_status(self, payment_id) -> bool:
        funcName = '检查payment.status'
        try:
            # 查询银行类型ID
            with self.handler.db_orm.sessionmaker() as session:
                payment = session.query(Payment).filter(
                    Payment.id == payment_id
                ).first()

                if payment and payment.status == 0:
                    self.logger.info(f'{self._log_key(funcName)} 成功: {payment_id}, {payment.status}')
                    return True
                else:
                    self.logger.error(f'{self._log_key(funcName)} 失败, {payment_id}, {payment.status}, 该状态不允许激活')
                    return False
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return False

    async def _save_fingerprint(self, session_data, file_body, bankname, payment_id, phone) -> str:
        """
        保存指纹文件到本地
        ⚠️ 注意：不再创建 Payment 记录，只保存指纹文件并返回路径
        Payment 记录的创建已移至 verify_otp_http（与 EasyPaisa 保持一致）
        """
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.FINGERPRINT_PATH)
        os.makedirs(path, exist_ok=True)
        save_path = os.path.join(path, self.FINGERPRINT_FILENAME.format(bankname=bankname, payment_id=payment_id, phone=phone))
        with open(save_path, "wb") as f:
            f.write(file_body)

        # 将指纹路径保存到 session 中，稍后在 verify_otp 时创建 Payment 记录
        session_data['fingerprint_path'] = save_path

        return save_path
