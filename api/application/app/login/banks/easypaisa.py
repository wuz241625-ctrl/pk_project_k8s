import json
import time
import asyncio
import hashlib
import base64
import random
import string
import secrets
import bcrypt
import logging
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

# 错误处理相关导入
from application.lakshmi_api.services.error_manager import ErrorManager
from application.lakshmi_api.exceptions.api_error import NewApiError
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.models.bank_type import BankType
import re
import uuid
import os
from datetime import datetime
from config import get_config

conf = get_config()

# 账户类型常量（使用间隔值避免与现有数据冲突）
ACCOUNT_TYPE_UNKNOWN = 0     # 未知/未检测
ACCOUNT_TYPE_WALLET = 10     # 钱包账户
ACCOUNT_TYPE_BANK = 20       # 银行账户
ACCOUNT_TYPE_MERCHANT = 30   # 商户账户（仅JazzCash）

# 服务名
SVRNAME = 'easypaisa'
APIKEY = conf.get('easypaisa_user_id', 'ba08c3c0e4f546ad92dd2c2e8542ca36')
APISECRET = conf.get('easypaisa_secret_key', 'ca45b35e132b46b9b68dd55f1ab077de')
CDSCOPE = 60 * 60 * 2 # 登录冷却秒 - 2小时
SESSIONSCOPE = 60 * 60 * 24 * 5 # 会话持续秒 - 5天
PIN_CHANGE_ATTEMPTS_MAXIMUM = 3
FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM = 3
ISTEST = False
CODE_VER = '20250917002'
EASYPAISA_API_VERSION = 'v1.6'  # API版本控制：v1.6需要指纹验证，v1.8不需要指纹验证

# Redis状态常量
class LoginStatus:
    PRE_LOGIN_CREATED = "preLoginCreated"
    OTP_SENT = "otpSent"
    OTP_VERIFIED = "otpVerified"
    FINGERPRINT_UPLOAD_REQUIRED = "fingerprintUploadRequired"
    FINGERPRINT_UPLOADED = "fingerprintUploaded"
    FINGERPRINT_VERIFIED = "fingerprintVerified"
    SECOND_LOGIN_READY = "secondLoginReady"
    SECOND_LOGIN_PASSED = "secondLoginPassed"
    AWAITING_PIN_CHANGE = "awaitingPinChange"
    ACCOUNT_SELECTION_REQUIRED = "accountSelectionRequired"
    ACTIVE_SUCCESSFUL = "activeSuccessful"

    # 兼容旧代码路径，避免遗留辅助方法在导入期失效。
    PRE_LOGIN = PRE_LOGIN_CREATED
    SEND_OTP = OTP_SENT
    VERIFY_OTP = OTP_VERIFIED
    LOGIN_SUCCESSFUL = SECOND_LOGIN_PASSED

# 状态转换规则定义
STATUS_TRANSITIONS = {
    LoginStatus.PRE_LOGIN_CREATED: [LoginStatus.OTP_SENT],
    LoginStatus.OTP_SENT: [LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED],
    LoginStatus.OTP_VERIFIED: [
        LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
        LoginStatus.FINGERPRINT_UPLOADED,
    ],
    LoginStatus.FINGERPRINT_UPLOAD_REQUIRED: [LoginStatus.FINGERPRINT_UPLOADED],
    LoginStatus.FINGERPRINT_UPLOADED: [
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
    ],
    LoginStatus.FINGERPRINT_VERIFIED: [
        LoginStatus.SECOND_LOGIN_PASSED,
        LoginStatus.AWAITING_PIN_CHANGE,
    ],
    LoginStatus.SECOND_LOGIN_READY: [
        LoginStatus.SECOND_LOGIN_PASSED,
        LoginStatus.AWAITING_PIN_CHANGE,
    ],
    LoginStatus.SECOND_LOGIN_PASSED: [LoginStatus.ACCOUNT_SELECTION_REQUIRED],
    LoginStatus.AWAITING_PIN_CHANGE: [LoginStatus.FINGERPRINT_VERIFIED],
    LoginStatus.ACCOUNT_SELECTION_REQUIRED: [LoginStatus.ACTIVE_SUCCESSFUL],
    LoginStatus.ACTIVE_SUCCESSFUL: [],
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
    """账号验证状态"""
    def __init__(self):
        self.IsSuccess = False
        self.IsInCoolDown = False
        self.IsNeedRelogin = False
        self.IsNeedChangePin = False
        self.IsNeedFingerPrint = False

class EasyPaisa:

    LOGIN_TYPE = 'sms_otp_pin'

    # 银行名称映射
    BANK_NAME_MAPPING = {
        'easypaisa': 'EASYPAISA',
    }

    # 登录失败次数限制常量
    LOGIN_FAILED_COUNT_KEY = 'login_failed_count_{bankname}_{phone}'
    LOGIN_FAILED_MAX_ATTEMPTS = 3  # 最大失败次数
    LOGIN_FAILED_LOCK_TIME = 60 * 60 * 2  # 锁定时间：2小时

    PROXIES_IP_KEY = 'indian_socks_ip_{bankname}'
    PRELOGIN_KEY = 'pre_login_{bankname}_{payment_id}'
    PAYMENT_INTERFACE_LOCK_KEY = 'payment_interface_lock:{payment_id}:{operation_name}'
    
    
    FINGERPRINT_PATH = '/fingerprint/'
    FINGERPRINT_FILENAME = '{bankname}_{payment_id}_{phone}.zip'

    API_ENDPOINTS = {
        'base_url': conf.get('easypaisa_api_url', 'http://34.150.42.92:83'),
        'fingerprint_upload_url': 'https://easypaisa.zpay.today/upload_data',
        # 'logincheck': 'isLogined',
        'send_otp': 'loginStep1',
        'verify_otp': 'loginStep2',
        'verify_account': 'secondLogin',
        'verify_fingerprint': 'verifyFingerprint',
        'change_pin': 'secondLogin',
        'query_acct_list': 'queryAccountList',
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
        uuid_formatted = (
            f"{uuid_hex[:8]}-{uuid_hex[8:12]}-4{uuid_hex[13:16]}-"
            f"{random.choice('89ab')}{uuid_hex[17:20]}-{uuid_hex[20:]}"
        )
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

    # ================== 账户类型检测方法 ==================
    def _determine_account_type(self, account_entire, account_accno=None, account_iban=None):
        """
        判断账户类型：钱包 / 银行账户 / 商户账户
        
        Args:
            account_entire: JSON字符串，包含完整账户信息
            account_accno: 账号（可选）
            account_iban: IBAN号（可选）
        
        Returns:
            str: "wallet" | "bank" | "merchant" | "unknown"
        """
        funcName = '账户类型检测'
        
        # 1. 解析 account_entire
        if not account_entire:
            self.logger.debug(f'{self._log_key(funcName)} account_entire为空，返回unknown')
            return "unknown"
        
        try:
            account_data = json.loads(account_entire)
            self.logger.debug(f'{self._log_key(funcName)} 成功解析account_entire，包含字段: {list(account_data.keys())}')
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f'{self._log_key(funcName)} 解析account_entire失败: {str(e)}，返回unknown')
            return "unknown"
        
        # 2. 判断 JazzCash 商户账户（最高优先级）
        customer_type = account_data.get("customerType", "")
        scope = account_data.get("scope", "")
        
        if customer_type == "merchant" or scope == "merchant":
            self.logger.info(f'{self._log_key(funcName)} 检测到商户账户 (customerType={customer_type}, scope={scope})，返回merchant')
            return "merchant"
        
        # 3. 判断钱包 - 通过 accountName
        account_name = account_data.get("accountName", "")
        
        if account_name == "Easypaisa Wallet":
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accountName=Easypaisa Wallet)，返回wallet')
            return "wallet"
        
        if account_name == "JazzCash Wallet":
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accountName=JazzCash Wallet)，返回wallet')
            return "wallet"
        
        if account_name == "JazzCash Account":
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accountName=JazzCash Account)，返回wallet')
            return "wallet"  # JazzCash Account 也是个人账户
        
        # 4. 判断 - 通过 accountProfile
        account_profile = account_data.get("accountProfile", "")
        
        # 钱包等级
        if account_profile in ["L0", "L1"]:
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accountProfile={account_profile})，返回wallet')
            return "wallet"
        
        # 银行账户等级
        if account_profile in [
            "ADA", "DA", 
            "Current MA", "Savings MA",
            "Joint Current MA", "Joint Savings MA"
        ]:
            self.logger.info(f'{self._log_key(funcName)} 检测到银行账户 (accountProfile={account_profile})，返回bank')
            return "bank"
        
        # 5. 通过 IBAN 前缀判断（辅助）
        iban = account_iban or account_data.get("IBAN") or account_data.get("iban", "")
        
        if iban:
            iban_upper = iban.upper()
            
            # Telenor Microfinance Bank = EasyPaisa 钱包
            if "TMFB" in iban_upper:
                self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (IBAN包含TMFB: {iban})，返回wallet')
                return "wallet"
            
            # JazzCash Merchant Account
            if "JCMA" in iban_upper:
                # 需要进一步判断是商户还是个人
                if "businessDetails" in account_data:
                    self.logger.info(f'{self._log_key(funcName)} 检测到商户账户 (IBAN包含JCMA且有businessDetails: {iban})，返回merchant')
                    return "merchant"
                else:
                    self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (IBAN包含JCMA但无businessDetails: {iban})，返回wallet')
                    return "wallet"  # JazzCash 个人账户
        
        # 6. 通过账号格式判断（EasyPaisa 钱包特征）
        accno = account_accno or account_data.get("accno", "")
        
        if accno and len(str(accno)) == 8 and str(accno).isdigit():
            # EasyPaisa 钱包账号是8位数字
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accno为8位数字: {accno})，返回wallet')
            return "wallet"
        
        # 7. 如果 accountName 存在且不是钱包名称，判断为银行账户
        if account_name and account_name not in [
            "Easypaisa Wallet", 
            "JazzCash Wallet", 
            "JazzCash Account",
            ""
        ]:
            self.logger.info(f'{self._log_key(funcName)} 检测到银行账户 (accountName={account_name})，返回bank')
            return "bank"
        
        # 8. 默认返回 unknown
        self.logger.warning(f'{self._log_key(funcName)} 无法确定账户类型 (accountName={account_name}, accountProfile={account_profile}, IBAN={iban}, accno={accno})，返回unknown')
        return "unknown"

    def _convert_account_type_to_int(self, account_type_str):
        """
        将账户类型字符串转换为整数值
        
        Args:
            account_type_str: "wallet" | "bank" | "merchant" | "unknown"
        
        Returns:
            int: 0 | 10 | 20 | 30
        """
        account_type_map = {
            'wallet': ACCOUNT_TYPE_WALLET,      # 10
            'bank': ACCOUNT_TYPE_BANK,          # 20
            'merchant': ACCOUNT_TYPE_MERCHANT,  # 30
            'unknown': ACCOUNT_TYPE_UNKNOWN     # 0
        }
        return account_type_map.get(account_type_str, ACCOUNT_TYPE_UNKNOWN)

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

    @staticmethod
    def _login_lock_payment_key(payment_id):
        return f'login_lock_easypaisa_payment_{payment_id}'

    @staticmethod
    def _login_lock_phone_key(phone):
        return f'login_lock_easypaisa_phone_{phone}'

    @staticmethod
    def _normalize_channels(channels) -> list:
        if channels in (None, '', []):
            return []
        if isinstance(channels, (list, tuple, set)):
            raw_items = list(channels)
        else:
            raw_items = [channels]

        normalized = []
        seen = set()
        for item in raw_items:
            if isinstance(item, bytes):
                item = item.decode('utf-8')
            for part in str(item).split(','):
                text = part.strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                normalized.append(text)
        return normalized

    @staticmethod
    def _current_login_session_keys(payment_id, phone=None):
        keys = [
            f'pre_login_easypaisa_{payment_id}',
            f'login_on_easypaisa_{payment_id}',
        ]
        if phone:
            keys.extend(
                [
                    f'login_on_easypaisa_{phone}',
                ]
            )
        return keys

    def _log_key(self, funcName):
        return f'{self.name} {self._get_pre_login_key()} {funcName}'

    def _log_response(self, funcName, response):
        try:
            # 检查response是否为None
            if response is None:
                self.logger.error(f'{self._log_key(funcName)} 响应为None，无法记录日志')
                return
            
            # 基本信息
            self.logger.info(f"{self._log_key(funcName)} 请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    async def _read_prelogin_entry(self, redis_key):
        """读取 pre_login Redis 记录，可能是真实 session，也可能是 alias 文档。"""
        try:
            if not redis_key:
                return None
            session_json = await self.redis.get(redis_key)
            if not session_json:
                return None
            return json.loads(session_json)
        except (TypeError, json.JSONDecodeError) as exc:
            self.logger.warning(f'{self._log_key("读取pre_login记录")} JSON解析失败: key={redis_key}, exc={exc}')
            return None

    @staticmethod
    def _normalize_payment_id(payment_id):
        if payment_id in [None, '']:
            return None
        return str(payment_id)

    @staticmethod
    def _is_payment_id_alias_entry(entry):
        return bool(
            isinstance(entry, dict)
            and entry.get('kind') == 'payment_id_alias'
            and entry.get('target_payment_id') not in [None, '']
        )

    def _build_payment_id_alias_entry(self, *, target_payment_id, bankname, phone=None):
        return {
            'kind': 'payment_id_alias',
            'target_payment_id': self._normalize_payment_id(target_payment_id),
            'bankname': bankname,
            'phone': phone,
            'updated_at': int(time.time()),
        }

    async def _resolve_session_context(self, bankname, payment_id):
        """把请求携带的 payment_id 解析到当前真实会话。"""
        requested_payment_id = self._normalize_payment_id(payment_id)
        requested_redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=requested_payment_id)
        resolved_payment_id = requested_payment_id
        resolved_redis_key = requested_redis_key
        visited = set()

        while resolved_payment_id and resolved_payment_id not in visited:
            visited.add(resolved_payment_id)
            resolved_redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=resolved_payment_id)
            entry = await self._read_prelogin_entry(resolved_redis_key)
            if self._is_payment_id_alias_entry(entry):
                resolved_payment_id = self._normalize_payment_id(entry.get('target_payment_id'))
                continue
            if entry:
                return {
                    'requested_payment_id': requested_payment_id,
                    'resolved_payment_id': resolved_payment_id,
                    'requested_redis_key': requested_redis_key,
                    'redis_key': resolved_redis_key,
                    'session_data': entry,
                    'is_aliased': requested_payment_id != resolved_payment_id,
                }
            break

        return {
            'requested_payment_id': requested_payment_id,
            'resolved_payment_id': resolved_payment_id or requested_payment_id,
            'requested_redis_key': requested_redis_key,
            'redis_key': resolved_redis_key,
            'session_data': None,
            'is_aliased': requested_payment_id != (resolved_payment_id or requested_payment_id),
        }

    async def _get_session_data(self, redis_key):
        """获取会话数据"""
        funcName = '获取会话数据'
        try:
            if not redis_key:
                return None
            entry = await self._read_prelogin_entry(redis_key)
            if entry:
                if self._is_payment_id_alias_entry(entry):
                    target_payment_id = self._normalize_payment_id(entry.get('target_payment_id'))
                    if target_payment_id:
                        target_redis_key = self.PRELOGIN_KEY.format(
                            bankname=entry.get('bankname') or self.name,
                            payment_id=target_payment_id,
                        )
                        target_entry = await self._read_prelogin_entry(target_redis_key)
                        if target_entry and not self._is_payment_id_alias_entry(target_entry):
                            return target_entry
                return entry
            return None
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return None

    async def _clear_stale_active_session_if_offline(self, redis_key, session_data):
        """当 MySQL 钱包最终态已离线时，清理残留的成功会话。"""
        payment_id = self._extract_payment_id_from_redis_key(redis_key)
        if payment_id is None:
            return False

        payment = await self._query_payment(payment_id)
        if not payment:
            return False

        wallet_status = payment.get('wallet_status', 0)
        try:
            wallet_status = int(wallet_status or 0)
        except (TypeError, ValueError):
            wallet_status = 0
        if wallet_status == 1:
            return False

        resolved_phone = session_data.get("phone") or payment.get("phone")
        await self.redis.delete(redis_key)
        await self.redis.delete(f'login_on_easypaisa_{payment_id}')
        if resolved_phone:
            await self.redis.delete(f'login_on_easypaisa_{resolved_phone}')
        return True

    def _session_ttl_for_status(self, status):
        if status == LoginStatus.ACTIVE_SUCCESSFUL:
            return SESSIONSCOPE
        return self.expire_time_login_pending

    async def _persist_session_data(self, redis_key, session_data):
        expire_time = self._session_ttl_for_status(session_data.get('status'))
        session_data['se_until'] = int(time.time() + expire_time)
        await self.redis.setex(redis_key, expire_time, json.dumps(session_data))
        previous_payment_id = self._normalize_payment_id(session_data.get('previous_payment_id'))
        current_payment_id = self._normalize_payment_id(session_data.get('id'))
        if previous_payment_id and current_payment_id and previous_payment_id != current_payment_id:
            alias_key = self.PRELOGIN_KEY.format(
                bankname=session_data.get('bankname') or self.name,
                payment_id=previous_payment_id,
            )
            alias_entry = self._build_payment_id_alias_entry(
                target_payment_id=current_payment_id,
                bankname=session_data.get('bankname') or self.name,
                phone=session_data.get('phone'),
            )
            await self.redis.setex(alias_key, expire_time, json.dumps(alias_entry))
        return session_data['se_until']

    @staticmethod
    def _extract_payment_id_from_redis_key(redis_key):
        if not redis_key:
            return None
        return str(redis_key).rsplit('_', 1)[-1]

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

            session_data['status_history'].append(status_new)
            se_until = await self._persist_session_data(redis_key, session_data)
            self.logger.info(f'{self._log_key(funcName)} {redis_key} -> {status_new} (se_until: {se_until})')
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
        return se_until

    def _assert_status_transition(self, session_data, expected_current_status, target_status, operation_name):
        """验证状态转换是否有效，无效时直接抛 INVALID_TRANSITION。"""
        funcName = '验证状态转换是否有效'
        current_status = session_data.get('status')
        if current_status != expected_current_status:
            message = f'{self._log_key(funcName)} 状态转换无效 {operation_name}: 期望 {expected_current_status}, 实际 {current_status}'
            self.logger.error(message)
            raise NewApiError('INVALID_TRANSITION', message)
        if target_status not in STATUS_TRANSITIONS.get(current_status, []):
            message = f'{self._log_key(funcName)} 状态转换无效 {operation_name}: {current_status} -> {target_status}'
            self.logger.error(message)
            raise NewApiError('INVALID_TRANSITION', message)
        return True

    async def _promote_session_to_active_successful(self, redis_key, session_data, operation_name):
        """将 loginSuccessful 会话安全推进到 activeSuccessful。"""
        funcName = f'{operation_name} - 推进activeSuccessful'

        required_session_fields = ['phone', 'id', 'bankname']
        missing_fields = [field for field in required_session_fields if not session_data.get(field)]
        if missing_fields:
            self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
            raise NewApiError(ErrorCode.SessionNotExist, f'Session data incomplete, missing fields: {", ".join(missing_fields)}')

        session_phone = session_data.get('phone')
        session_payment_id = session_data.get('id')
        session_bankname = session_data.get('bankname')
        session_status = session_data.get('status', 'UNKNOWN')

        if session_status == LoginStatus.ACTIVE_SUCCESSFUL:
            result = {
                'status': 'success',
                'message': '账号已经激活成功，请勿重复激活'
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result

        if session_status != LoginStatus.LOGIN_SUCCESSFUL:
            raise NewApiError(ErrorCode.SessionNotExist, f'Invalid status transition, current status: {session_status}')

        api_result_verify_acct = await self._verify_account(session_data)

        if api_result_verify_acct.IsSuccess:
            self.logger.info(f'{self._log_key(funcName)} 账号状态正常')

            api_result_query_accts = await self._query_accts(session_phone)
            accts_json = api_result_query_accts.get('data')
            accts_data = json.loads(accts_json)
            acct = self._query_accts_default(accts_data)
            if not acct:
                raise NewApiError(ErrorCode.QueryAccts, 'Easypaisa Wallet account not found')

            login_lock_payment_key = self._login_lock_payment_key(session_payment_id)
            await self.redis.setex(login_lock_payment_key, self.lock_time_login_duplicate_avoid, 1)

            login_lock_phone_key = self._login_lock_phone_key(session_phone)
            await self.redis.setex(login_lock_phone_key, self.lock_time_login_duplicate_avoid, 1)

            self.logger.info(f'{self._log_key(funcName)} Payment锁: {login_lock_payment_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')
            self.logger.info(f'{self._log_key(funcName)} Phone锁: {login_lock_phone_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')

            self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态. {session_data.get("status")} → {LoginStatus.ACTIVE_SUCCESSFUL}')
            await self._update_session_status(redis_key, session_data, LoginStatus.ACTIVE_SUCCESSFUL)

            self.logger.info(f'{self._log_key(funcName)} 正在更新payment...')
            await self._update_payment(
                session_payment_id,
                session_data,
                account_entire=accts_json,
                account_accno=acct.get('accno'),
                account_iban=acct.get('IBAN'),
            )

            result = {
                'status': 'success',
                'message': '账号激活成功',
                'data': {
                    'account_accno': acct.get('accno', ''),
                    'account_iban': acct.get('IBAN', ''),
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result

        if api_result_verify_acct.IsInCoolDown:
            self.logger.error(f'{self._log_key(funcName)} 冷却中，当前：{datetime.now()}, 冷却至：{datetime.fromtimestamp(session_data.get("cd_until", 0))}')

        if api_result_verify_acct.IsNeedRelogin:
            self.logger.error(f'{self._log_key(funcName)} 需要重新登录（会话过期），执行强制下线流程')

            logout_success = await self._force_logout(
                payment_id=session_payment_id,
                bankname=session_bankname,
                reason='SESSION_EXPIRED_URM10004'
            )

            if logout_success:
                self.logger.warning(f'{self._log_key(funcName)} 强制下线成功')
            else:
                self.logger.error(f'{self._log_key(funcName)} 强制下线失败')

            login_lock_phone_key = self._login_lock_phone_key(session_phone)
            await self.redis.delete(login_lock_phone_key)

            result = {
                'status': 'error',
                'message': '会话已过期，账号已强制下线，请重新登录',
                'data': {
                    'isNeedReLogin': True,
                    'isInCoolDown': False,
                    'isNeedChangePin': False,
                    'isNeedFingerPrint': False,
                }
            }
            self.logger.info(f'{self._log_key(funcName)} 返回结果: {result}')
            return result

        if api_result_verify_acct.IsNeedChangePin:
            self.logger.error(f'{self._log_key(funcName)} 需要修改PIN')

        if api_result_verify_acct.IsNeedFingerPrint:
            self.logger.error(f'{self._log_key(funcName)} 需要修改指纹')

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

    async def _try_promote_session_from_payment_status(self, payment_id, redis_key, session_data):
        """在 payment_status 轮询时尝试补推进登录成功但未激活的会话。"""
        funcName = 'payment_status_http'
        payment_lock_id = None
        payment_lock_value = None

        if session_data.get('status') != LoginStatus.LOGIN_SUCCESSFUL:
            return session_data

        try:
            lock_result = await self._get_payment_interface_lock(payment_id, 'payment_status_promote')
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')

            latest_session_data = await self._get_session_data(redis_key)
            if not latest_session_data:
                return None

            if latest_session_data.get('status') != LoginStatus.LOGIN_SUCCESSFUL:
                return latest_session_data

            result = await self._promote_session_to_active_successful(redis_key, latest_session_data, funcName)
            self.logger.info(f'{self._log_key(funcName)} payment_status 自动补推进结果: {result}')
        except NewApiError as e:
            self.logger.warning(f'{self._log_key(funcName)} payment_status 自动补推进跳过: {e.code} {e.message}')
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} payment_status 自动补推进异常: {str(e)}', exc_info=True)
        finally:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)

        return await self._get_session_data(redis_key)

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
                raise NewApiError(ErrorCode.Unsupported, f"Unsupported step: {data.get('step', 'unknown')}")
            
            # 检查用户类型 完成登录信息提交
            self.logger.info(f"{self._log_key(funcName)} 执行步骤: {data.get('step', 'complete_login')}")
            
            required_fields = ['bankname', 'phone', 'password', 'pin', 'name']
            if not all(field in data and data[field] for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data or not data[field]]
                error_msg = f"Missing required parameters: {', '.join(missing_fields)}"
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
            self.logger.info(f"{self._log_key(funcName)} 当前认证用户信息: ID={user_id}, 手机号={getattr(self.handler.current_user, 'cellphone', 'Unknown')}")

            # 立即检查协议进程锁 - 在任何复杂处理前进行早期检查
            # 检查 payment_id 登录状态
            if payment_id and await self.redis.get(self._login_lock_payment_key(payment_id)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            # 检查 phone 登录状态
            if phone and await self.redis.get(self._login_lock_phone_key(phone)):
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
                        'account_entire': getattr(existing_payment, 'account_entire', None),
                        'account_accno': getattr(existing_payment, 'account_accno', None),
                        'account_iban': getattr(existing_payment, 'account_iban', None),
                    }
                    phone_owner = await self._check_payment(bankname, phone, user_id)
                    if phone_owner and str(phone_owner.get('id')) != str(existing_payment.id):
                        raise NewApiError('10402', 'UPI already occupied by another payment id')
                    self.logger.info(f'{self._log_key(funcName)} Payment record validation successful: {payment_id}')
            else:
                # 检查现有payment记录
                existing_payment = await self._check_payment(bankname, phone, user_id)
                is_new_user = existing_payment is None
                self.logger.info(f'{self._log_key(funcName)} 用户类型检查: {phone} - partner_id: {user_id} - 新用户: {is_new_user}')

                if existing_payment:
                    if existing_payment.get('user_id') == user_id:
                        self.logger.error(
                            f'{self._log_key(funcName)} payment已存在且属于当前用户: phone={phone}, user_id={user_id}'
                        )
                        payment_id = existing_payment.get('id')
                        bound_payment = existing_payment
                    else:
                        self.logger.error(
                            f'{self._log_key(funcName)} payment已被其他码商占用: phone={phone}, '
                            f'current_user={user_id}, owner_user={existing_payment.get("user_id")}'
                        )
                        raise NewApiError('10402', 'UPI already occupied by another user')
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
                is_registered = await self._is_account_registered(phone)
                if is_registered:
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
                            'next_step': 'second_login'
                        }
                    }
                    self.logger.info(f'{self._log_key(funcName)} 已绑定账号通过归属校验，返回second_login: {result}')
                    return result

                self.logger.warning(
                    f'{self._log_key(funcName)} 已绑定EasyPaisa账号云机未注册，回退首次上号流程: '
                    f'phone={phone}, payment_id={payment_id}'
                )

            # 创建Redis登录会话
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            self.logger.info(f'{self._log_key(funcName)} 创建Redis会话key: {redis_key}')
            
            # 检查是否已存在会话
            existing_session = await self._get_session_data(redis_key)
            if existing_session:
                current_status = existing_session.get('status')
                self.logger.warning(f'{self._log_key(funcName)} 发现已存在会话: {redis_key} - 状态: {current_status}')
                if current_status == LoginStatus.ACTIVE_SUCCESSFUL:
                    if await self._clear_stale_active_session_if_offline(redis_key, existing_session):
                        self.logger.warning(
                            f'{self._log_key(funcName)} MySQL 已离线，已清理当前成功会话并允许重新登录: {redis_key}'
                        )
                        existing_session = None
                    else:
                        self.logger.error(f'{self._log_key(funcName)} 账户已登录成功，拒绝重复登录')
                        raise NewApiError(ErrorCode.Logined2, f'Account already logged in successfully, duplicate login denied')
                if existing_session and current_status == LoginStatus.ACTIVE_SUCCESSFUL:
                    self.logger.error(f'{self._log_key(funcName)} 账户已登录成功，拒绝重复登录')
                    raise NewApiError(ErrorCode.Logined2, f'Account already logged in successfully, duplicate login denied')
                elif existing_session and current_status == LoginStatus.PRE_LOGIN_CREATED:
                    self.logger.error(f'{self._log_key(funcName)} 已经开始走登录流程，拒绝重复登录')
                    raise NewApiError(ErrorCode.Logined3, f'Account already started login process, duplicate login denied')
                elif existing_session and current_status in [
                    LoginStatus.OTP_SENT,
                    LoginStatus.OTP_VERIFIED,
                    LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
                    LoginStatus.FINGERPRINT_UPLOADED,
                    LoginStatus.FINGERPRINT_VERIFIED,
                    LoginStatus.SECOND_LOGIN_PASSED,
                    LoginStatus.AWAITING_PIN_CHANGE,
                    LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                ]:
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
                'status': LoginStatus.PRE_LOGIN_CREATED,    # 当前状态
                'time': int(time.time()),                   # 创建时间戳（标准字段）
                'try_count': 0,                             # 重试次数（标准字段）
                'socks_ip': proxy_ip or '',                 # 代理IP（标准字段名）
                'to': self.name,                            # 目标key
                'qr_channel': data.get('channel', 1001),    # 渠道
                'pinCode': pin,                             # PIN码
                'id_num': '',                               # 身份证号

                # === 扩展必要字段 ===
                'bankname': bankname,                       # 银行名称
                'password': password,                       # 密码
                'account': data.get('account', ''),         # 账户信息
                'is_new_user': is_new_user,                 # 是否新用户
                'status_history': [LoginStatus.PRE_LOGIN_CREATED], # 状态历史
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
                }
            }

            self.logger.info(f'{self._log_key(funcName)} Redis待存储数据: {json.dumps(session_data)}')
            
            # 存储到Redis
            await self._persist_session_data(redis_key, session_data)
            self.logger.info(f'{self._log_key(funcName)} 会话数据已存储到Redis: {redis_key} - 过期时间: {expire_second}秒')
            
            self.logger.info(f'{self._log_key(funcName)} 成功: {phone} - {payment_id} - 新用户: {is_new_user}')
            
            result = {
                'status': 'success',
                'message': f'成功',
                'data': {
                    'id': payment_id,
                    'redis_key': redis_key,
                    'expires_in': expire_second,
                    'total_timeout': 120,
                    'is_new_user': is_new_user,
                    'bank_type': self.LOGIN_TYPE,
                    'next_step': 'send_sms'
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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
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
                raise NewApiError(ErrorCode.SessionNotExist, f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
            
            # 检查登录锁状态
            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self._login_lock_payment_key(session_payment_id)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            if session_phone and await self.redis.get(self._login_lock_phone_key(session_phone)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')

            self.logger.info(f'{self._log_key(funcName)} 成功获取会话数据！')
            self.logger.info(f'{self._log_key(funcName)} === 会话数据详细信息 ===')
            self.logger.info(f"{self._log_key(funcName)} 手机号: {session_data.get('phone', 'UNKNOWN')}")
            self.logger.info(f"{self._log_key(funcName)} 当前状态: {session_data.get('status', 'UNKNOWN')}")
            self.logger.info(f'{self._log_key(funcName)} 目标状态: {LoginStatus.OTP_SENT}')
            self.logger.info(f"{self._log_key(funcName)} app_gen_id: {session_data.get('app_gen_id', 'UNKNOWN')}")
            self.logger.info(f"{self._log_key(funcName)} android_id: {session_data.get('androidId', 'UNKNOWN')}")
            self.logger.info(f"{self._log_key(funcName)} safety_net_id: {session_data.get('safetyNetId', 'UNKNOWN')}")
            self.logger.info(f"{self._log_key(funcName)} authorization存在: {'是' if session_data.get('authorization') else '否'}")
            if session_data.get('authorization'):
                auth_preview = session_data.get('authorization')[:50] + "..." if len(session_data.get('authorization', '')) > 50 else session_data.get('authorization')
                self.logger.info(f'{self._log_key(funcName)} authorization预览: {auth_preview}')
            
            self.logger.info(f'{self._log_key(funcName)} 会话数据完整性检查通过！')

            current_status = session_data.get('status', 'UNKNOWN')
            is_resend = current_status == LoginStatus.OTP_SENT
            if current_status not in (LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_SENT):
                self._assert_status_transition(
                    session_data,
                    LoginStatus.PRE_LOGIN_CREATED,
                    LoginStatus.OTP_SENT,
                    funcName,
                )

            if is_resend:
                last_send_ts = int(session_data.get('sendOTPTime') or 0)
                now_ts = int(time.time())
                if last_send_ts and (now_ts - last_send_ts) < self.RESEND_COOLDOWN_SECONDS:
                    wait_left = self.RESEND_COOLDOWN_SECONDS - (now_ts - last_send_ts)
                    raise NewApiError(
                        ErrorCode.PaymentLocked,
                        f'Please wait {wait_left}s before requesting a new OTP',
                    )
                self._assert_status_transition(
                    session_data,
                    LoginStatus.OTP_SENT,
                    LoginStatus.OTP_SENT,
                    funcName,
                )
                self.logger.info(f'{self._log_key(funcName)} 状态转换验证通过！(otpSent → otpSent resend)')
            else:
                self._assert_status_transition(
                    session_data,
                    LoginStatus.PRE_LOGIN_CREATED,
                    LoginStatus.OTP_SENT,
                    funcName,
                )
                self.logger.info(f'{self._log_key(funcName)} 状态转换验证通过！(preLoginCreated → otpSent)')

            # 调用API
            api_result = await self._send_otp(session_data)

            self.logger.info(
                f'{self._log_key(funcName)} 正在更新会话状态. {current_status} → {LoginStatus.OTP_SENT}')
            await self._update_session_status(
                redis_key, session_data, LoginStatus.OTP_SENT,
                {
                    'sendOTPTime': int(time.time()),
                    'resend_count': int(session_data.get('resend_count', 0)) + (1 if is_resend else 0),
                }
            )
            
            self.logger.info(f'{self._log_key(funcName)} 完成')
            
            result = {
                'status': 'success',
                'message': 'OTP发送成功，请输入收到的验证码',
                'data': {
                    'next_status': LoginStatus.OTP_VERIFIED,
                    'phone': session_data.get('phone'),
                    'instruction': f"请查看手机 {session_data.get('phone')} 收到的OTP验证码短信"
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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            payment_id = self._normalize_payment_id(data['payment_id'])
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
                raise NewApiError(ErrorCode.SessionNotExist, f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
            
            # 检查登录锁状态
            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self._login_lock_payment_key(session_payment_id)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            if session_phone and await self.redis.get(self._login_lock_phone_key(session_phone)):
                raise NewApiError(ErrorCode.Logined, f'Account is in login process, please try again later')
            
            self.logger.info(f'{self._log_key(funcName)} 成功获取会话数据！')
            self.logger.info(f'{self._log_key(funcName)} === 会话数据详细信息 ===')
            self.logger.info(f"{self._log_key(funcName)} 手机号: {session_data.get('phone', 'UNKNOWN')}")
            self.logger.info(f"{self._log_key(funcName)} 当前状态: {session_data.get('status', 'UNKNOWN')}")
            self.logger.info(f'{self._log_key(funcName)} 目标状态: {LoginStatus.OTP_VERIFIED}')

            self.logger.info(f'{self._log_key(funcName)} 会话数据完整性检查通过！')
            self._assert_status_transition(
                session_data,
                LoginStatus.OTP_SENT,
                LoginStatus.OTP_VERIFIED,
                funcName,
            )
            self.logger.info(f'{self._log_key(funcName)} 状态转换验证通过！')

            api_result_verify_otp = await self._verify_otp(session_data, otp)
            session_data['serv_gen_id'] = api_result_verify_otp['data'].get('requestId')

            name = session_data.get('name', '')
            self.logger.info(f'{self._log_key(funcName)} 从session获取name: {name}')

            real_payment_id = await self._save_payment(session_data, name=name)
            if not real_payment_id:
                raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')

            old_payment_id = self._normalize_payment_id(session_payment_id)
            real_payment_id_text = self._normalize_payment_id(real_payment_id)
            old_redis_key = redis_key
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id_text)
            if old_redis_key != redis_key:
                await self.redis.delete(old_redis_key)

            login_lock_payment_key = self._login_lock_payment_key(real_payment_id)
            await self.redis.setex(login_lock_payment_key, self.lock_time_login_duplicate_avoid, 1)

            login_lock_phone_key = self._login_lock_phone_key(session_phone)
            await self.redis.setex(login_lock_phone_key, self.lock_time_login_duplicate_avoid, 1)

            self.logger.info(f'{self._log_key(funcName)} Payment锁: {login_lock_payment_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')
            self.logger.info(f'{self._log_key(funcName)} Phone锁: {login_lock_phone_key} ({self.lock_time_login_duplicate_avoid / 60}分钟)')

            now_ts = int(time.time())
            session_data.update({
                'id': real_payment_id,
                'redis_key': redis_key,
                'real_payment_id': real_payment_id,
                'selected_upi': session_phone,
                'upi_list': [session_phone],
                'completion_time': now_ts,
                'last_error': None,
                'previous_payment_id': old_payment_id,
            })

            self.logger.info(f"{self._log_key(funcName)} 正在更新会话状态. {session_data.get('status')} → {LoginStatus.OTP_VERIFIED}")
            await self._update_session_status(redis_key, session_data, LoginStatus.OTP_VERIFIED)

            try:
                replay_ok = await self._replay_saved_fingerprint(real_payment_id, session_phone)
            except Exception:
                replay_ok = False

            next_phase = (
                LoginStatus.FINGERPRINT_UPLOADED
                if replay_ok else LoginStatus.FINGERPRINT_UPLOAD_REQUIRED
            )
            self._assert_status_transition(session_data, LoginStatus.OTP_VERIFIED, next_phase, funcName)
            se_until = await self._update_session_status(redis_key, session_data, next_phase)

            result = {
                'status': 'success',
                'message': 'OTP验证成功',
                'data': {
                    'serv_gen_id': api_result_verify_otp['data'].get('serv_gen_id'),
                    'se_until': se_until,
                    'next_phase': next_phase,
                    'payment_id': real_payment_id,
                    'previous_payment_id': old_payment_id,
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
            raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def verify_fingerprint_http(self, data):
        """指纹验证。"""
        funcName = 'verify_fingerprint_http'
        lockName = 'verify_fingerprint'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                raise NewApiError(ErrorCode.MissingParams, f'Missing required parameters: {", ".join(missing_fields)}')

            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id

            lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')

            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            redis_key = session_ctx.get('redis_key')
            session_data = session_ctx.get('session_data')
            if not session_data:
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call verify_otp_http first')
            if session_ctx.get('is_aliased'):
                self.logger.info(
                    f'{self._log_key(funcName)} payment_id桥接: requested={requested_payment_id} -> resolved={resolved_payment_id}'
                )

            self._assert_status_transition(
                session_data,
                LoginStatus.FINGERPRINT_UPLOADED,
                LoginStatus.FINGERPRINT_VERIFIED,
                funcName,
            )

            verify_result = await self._perform_verify_fingerprint(session_data)
            if verify_result.get('outcome') == 'success':
                se_until = await self._update_session_status(
                    redis_key,
                    session_data,
                    LoginStatus.FINGERPRINT_VERIFIED,
                    {'last_error': None},
                )
                return {
                    'status': 'success',
                    'message': '指纹验证成功',
                    'data': {
                        'phase': LoginStatus.FINGERPRINT_VERIFIED,
                        'se_until': se_until,
                    }
                }

            if verify_result.get('outcome') == 'session_expired':
                session_data['last_error'] = {'code': 'FP_SESSION_EXPIRED'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': '会话已过期，请重新开始',
                    'data': {
                        'code': 'FP_SESSION_EXPIRED',
                        'phase': 'needsRelogin',
                    }
                }

            if verify_result.get('outcome') == 'cooldown':
                session_data['last_error'] = {'code': 'FP_COOLDOWN'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': '当前处于冷却期',
                    'data': {
                        'code': 'FP_COOLDOWN',
                        'phase': 'inCooldown',
                        'cd_until': session_data.get('cd_until', 0),
                    }
                }

            if verify_result.get('outcome') == 'transient':
                session_data['last_error'] = {'code': 'FP_UPSTREAM_TRANSIENT'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': verify_result.get('message') or '上游临时错误，请重试',
                    'data': {
                        'code': 'FP_UPSTREAM_TRANSIENT',
                        'phase': LoginStatus.FINGERPRINT_UPLOADED,
                    }
                }

            fingerprint_path = self._get_payment_fingerprint_path(resolved_payment_id)
            self._assert_status_transition(
                session_data,
                LoginStatus.FINGERPRINT_UPLOADED,
                LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
                funcName,
            )
            await self._clear_payment_fingerprint_path(resolved_payment_id)
            if fingerprint_path:
                try:
                    os.remove(fingerprint_path)
                except Exception:
                    self.logger.warning(f'{self._log_key(funcName)} 删除本地指纹失败: {fingerprint_path}')
            await self._update_session_status(
                redis_key,
                session_data,
                LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
                {'last_error': {'code': 'FP_UPSTREAM_REJECTED'}},
            )
            return {
                'status': 'error',
                'message': '上游拒绝当前指纹，请重新上传',
                'data': {
                    'code': 'FP_UPSTREAM_REJECTED',
                    'phase': LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
                }
            }
        except NewApiError:
            raise
        except Exception as e:
            raise NewApiError(ErrorCode.VerifyFingerPrint, f'FingerPrint verification failed: {str(e)}')
        finally:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)

    async def second_login_http(self, data):
        """二次登录。"""
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
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id

            lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')

            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            redis_key = session_ctx.get('redis_key')
            session_data = session_ctx.get('session_data')
            if not session_data:
                session_data = await self._build_bound_second_login_session(bankname, requested_payment_id)
                redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=requested_payment_id)
            if session_ctx.get('is_aliased'):
                self.logger.info(
                    f'{self._log_key(funcName)} payment_id桥接: requested={requested_payment_id} -> resolved={resolved_payment_id}'
                )

            current_status = session_data.get('status')
            if current_status not in (LoginStatus.FINGERPRINT_VERIFIED, LoginStatus.SECOND_LOGIN_READY):
                self._assert_status_transition(
                    session_data,
                    LoginStatus.FINGERPRINT_VERIFIED,
                    LoginStatus.SECOND_LOGIN_PASSED,
                    funcName,
                )
            self._assert_status_transition(
                session_data,
                current_status,
                LoginStatus.SECOND_LOGIN_PASSED,
                funcName,
            )

            second_login_result = await self._perform_second_login(session_data)
            outcome = second_login_result.get('outcome')

            if outcome == 'success':
                se_until = await self._update_session_status(
                    redis_key,
                    session_data,
                    LoginStatus.SECOND_LOGIN_PASSED,
                    {'last_error': None},
                )
                return {
                    'status': 'success',
                    'message': '二次登录成功',
                    'data': {
                        'phase': LoginStatus.SECOND_LOGIN_PASSED,
                        'se_until': se_until,
                    }
                }

            if outcome == 'needs_pin_change':
                self._assert_status_transition(
                    session_data,
                    current_status,
                    LoginStatus.AWAITING_PIN_CHANGE,
                    funcName,
                )
                await self._update_session_status(
                    redis_key,
                    session_data,
                    LoginStatus.AWAITING_PIN_CHANGE,
                    {'last_error': {'code': 'SL_NEEDS_PIN_CHANGE'}},
                )
                return {
                    'status': 'error',
                    'message': '需要修改 PIN',
                    'data': {
                        'code': 'SL_NEEDS_PIN_CHANGE',
                        'phase': LoginStatus.AWAITING_PIN_CHANGE,
                    }
                }

            if outcome == 'session_expired':
                session_data['last_error'] = {'code': 'SL_SESSION_EXPIRED'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': '会话已过期，请重新开始',
                    'data': {
                        'code': 'SL_SESSION_EXPIRED',
                        'phase': 'needsRelogin',
                    }
                }

            if outcome == 'cooldown':
                session_data['last_error'] = {'code': 'SL_COOLDOWN'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': '当前处于冷却期',
                    'data': {
                        'code': 'SL_COOLDOWN',
                        'phase': 'inCooldown',
                        'cd_until': session_data.get('cd_until', 0),
                    }
                }

            # upstream_error: 根据错误类型分别处理
            message = second_login_result.get('message', '')

            # 423 ServerBusy：等待 2 秒后重试一次，仍失败则报错
            if self._is_server_busy(message):
                await asyncio.sleep(2)
                retry_result = await self._perform_second_login(session_data)
                if retry_result.get('outcome') == 'success':
                    session_data['status'] = 'secondLoginPassed'
                    await self._persist_session_data(redis_key, session_data)
                    return {
                        'status': 'success',
                        'message': 'Second login passed',
                        'data': {
                            'code': 'SL_OK',
                            'phase': 'secondLoginPassed',
                        }
                    }
                # 423 重试仍失败，直接报错
                session_data['last_error'] = {'code': 'SL_UPSTREAM_ERROR'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': message or '云机正忙，请稍后重试',
                    'data': {
                        'code': 'SL_UPSTREAM_ERROR',
                        'phase': 'failed',
                    }
                }

            # 501 被抢登：回退到 loginStep1 重新注册云机
            if '501' in str(message) or 'AccountInvalid' in str(message):
                # 防循环：已经 fallback 过一次不再二次回退
                if session_data.get('fallback_from') == 'secondLogin':
                    self.logger.warning(
                        f'{self._log_key(funcName)} 二次secondLogin仍失败(501)，不再回退, '
                        f'phone={session_data.get("phone")}'
                    )
                    return {
                        'status': 'error',
                        'message': f'secondLogin二次失败: {message}',
                        'data': {
                            'code': 'SL_UPSTREAM_ERROR',
                            'phase': 'failed',
                        }
                    }
                return await self._fallback_to_first_login(session_data, redis_key, reason=message)

            # 503/网络错误/其他：直接报错，不做 fallback
            session_data['last_error'] = {'code': 'SL_UPSTREAM_ERROR'}
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': message or '上游错误',
                'data': {
                    'code': 'SL_UPSTREAM_ERROR',
                    'phase': 'failed',
                }
            }
        except NewApiError:
            raise
        except Exception as e:
            raise NewApiError(ErrorCode.VerifyAccount, f'Second login failed: {str(e)}')
        finally:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)

    async def active_account_http(self, data):
        self.login_data = data
        return {
            'code': 'API_DEPRECATED',
            'hint': 'use verify_fingerprint + second_login',
        }

    async def change_pin_http(self, data):
        """PIN修改"""
        funcName = 'change_pin_http'
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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            pin = data['pin']
            
            # [LOCK] 获取基于真实payment_id的接口锁
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error
            
            # 获取会话数据
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            redis_key = session_ctx.get('redis_key')
            session_data = session_ctx.get('session_data')
            
            if not session_data:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不存在')
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')
            if session_ctx.get('is_aliased'):
                self.logger.info(
                    f'{self._log_key(funcName)} payment_id桥接: requested={requested_payment_id} -> resolved={resolved_payment_id}'
                )
            
            self._assert_status_transition(
                session_data,
                LoginStatus.AWAITING_PIN_CHANGE,
                LoginStatus.FINGERPRINT_VERIFIED,
                funcName,
            )
            
            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
            
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
            if session_pin_times > PIN_CHANGE_ATTEMPTS_MAXIMUM:
                session_data['last_error'] = {'code': 'PIN_CHANGE_LIMIT_EXCEEDED'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': 'PIN 修改次数已超限',
                    'data': {
                        'code': 'PIN_CHANGE_LIMIT_EXCEEDED',
                        'phase': 'needsRelogin',
                        'maximum': PIN_CHANGE_ATTEMPTS_MAXIMUM,
                        'current': session_pin_times,
                    }
                }

            try:
                await self._change_pin(session_data, pin)
            except NewApiError as e:
                session_data['last_error'] = {'code': 'PIN_CHANGE_REJECTED'}
                await self._persist_session_data(redis_key, session_data)
                return {
                    'status': 'error',
                    'message': e.message or 'PIN 修改被拒绝',
                    'data': {
                        'code': 'PIN_CHANGE_REJECTED',
                        'phase': LoginStatus.AWAITING_PIN_CHANGE,
                        'maximum': PIN_CHANGE_ATTEMPTS_MAXIMUM,
                        'current': session_pin_times,
                    }
                }

            await self._save_payment(session_data, pin=pin)

            self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态')
            await self._update_session_status(
                redis_key,
                session_data,
                LoginStatus.FINGERPRINT_VERIFIED,
                {
                    'pin_times': session_pin_times,
                    'pinCode': pin,
                    'last_error': None,
                }
            )

            result = {
                'status': 'success',
                'message': 'PIN修改成功',
                'data': {
                    'maximum': PIN_CHANGE_ATTEMPTS_MAXIMUM,
                    'current': session_pin_times,
                    'phase': LoginStatus.FINGERPRINT_VERIFIED,
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
        """指纹上传"""
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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            
            if not file:
                raise NewApiError(ErrorCode.MissingParams, 'file cannot be empty')
            
            # 检查文件后缀
            if file["content_type"] not in ["application/zip", "application/x-zip-compressed", "multipart/x-zip"]:
                raise NewApiError(ErrorCode.MissingParams, 'file ext should be .zip')
            
            # 检查文件大小, 1MB
            if len(file["body"]) > 1024 * 1024 * 16:
                raise NewApiError(ErrorCode.MissingParams, 'file size can not over 16MB')
            
            # [LOCK] 获取基于真实payment_id的接口锁
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error
            
            # 获取会话数据
            self.logger.info(f'{self._log_key(funcName)} 正在从Redis获取会话数据...')
            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            redis_key = session_ctx.get('redis_key')
            session_data = session_ctx.get('session_data')
            
            if not session_data:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不存在')
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')
            if session_ctx.get('is_aliased'):
                self.logger.info(
                    f'{self._log_key(funcName)} payment_id桥接: requested={requested_payment_id} -> resolved={resolved_payment_id}'
                )
            
            self._assert_status_transition(
                session_data,
                LoginStatus.FINGERPRINT_UPLOAD_REQUIRED,
                LoginStatus.FINGERPRINT_UPLOADED,
                funcName,
            )
            
            # 检查必需字段
            required_session_fields = ['phone', 'id', 'bankname']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                self.logger.error(f'{self._log_key(funcName)} 会话数据不完整，缺少字段: {missing_fields}')
                raise NewApiError(ErrorCode.SessionNotExist, f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
            
            session_phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            session_fg_times = session_data.get('fg_times', 0)
            
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
            
            # 调用API
            await self._upload_fingerprint(session_data, file["filename"], file["body"])
            
            await self._save_fingerprint(session_data, file["body"], session_bankname, session_payment_id, session_phone)
            
            self.logger.info(f'{self._log_key(funcName)} 正在更新会话状态')
            await self._update_session_status(
                redis_key, session_data, LoginStatus.FINGERPRINT_UPLOADED,
                {
                    'fg_times': session_fg_times,
                    'last_error': None,
                }
            )
            
            result = {
                'status': 'success',
                'message': '指纹上传成功',
                'data': {
                    'maximum': FINGERPRINT_UPLOAD_ATTEMPTS_MAXIMUM,
                    'current': session_fg_times,
                    'phase': LoginStatus.FINGERPRINT_UPLOADED,
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
        """账户查询"""
        funcName = 'query_accts_http'
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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            
            # [LOCK] 获取基于真实payment_id的接口锁
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error
            
            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            redis_key = session_ctx.get('redis_key')
            session_data = session_ctx.get('session_data')
            if not session_data:
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call second_login_http first')
            if session_ctx.get('is_aliased'):
                self.logger.info(
                    f'{self._log_key(funcName)} payment_id桥接: requested={requested_payment_id} -> resolved={payment_id}'
                )

            self._assert_status_transition(
                session_data,
                LoginStatus.SECOND_LOGIN_PASSED,
                LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                funcName,
            )

            api_result = await self._query_accts(session_data['phone'])
            
            accts_json = api_result.get('data')
            accts_data = json.loads(accts_json)
            if len(accts_data) == 0:
                raise NewApiError(ErrorCode.QueryAccts, f'can not find any account')

            active_accounts = [item for item in accts_data if item.get('accountStatus', '') == "ACTIVE"]
            if not active_accounts:
                raise NewApiError(ErrorCode.QueryAccts, 'can not find any active account')
            
            self.logger.info(f'{self._log_key(funcName)} 正在更新payment...')
            await self._update_payment(payment_id, session_data, account_entire=accts_json)
            await self._update_session_status(
                redis_key,
                session_data,
                LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                {
                    'account_entire': accts_json,
                    'accounts': active_accounts,
                    'last_error': None,
                }
            )
            
            result = {
                'status': 'success',
                'data': {
                    'account_selected': session_data.get('account_accno', ''),
                    'account_entire': active_accounts,
                    'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
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

    @staticmethod
    def _load_account_list(raw_accounts):
        if not raw_accounts:
            return []
        if isinstance(raw_accounts, list):
            return raw_accounts
        try:
            data = json.loads(raw_accounts)
        except (json.JSONDecodeError, TypeError):
            return []
        return data if isinstance(data, list) else []

    @staticmethod
    def _filter_active_accounts(accounts):
        return [
            item for item in accounts
            if str(item.get('accountStatus', '')).upper() == 'ACTIVE'
        ]

    @staticmethod
    def _selected_account_business_status(wallet_status, status, certified, manual_status):
        business_enabled = (
            int(wallet_status or 0) == 1
            and int(status or 0) == 1
            and int(certified or 0) == 1
        )
        return {
            'collection_status': 1 if business_enabled and int(manual_status or 0) == 0 else 0,
            'payout_status': 1 if business_enabled else 0,
        }

    async def _query_bound_accounts(self, payment):
        funcName = 'query_bound_accounts'
        api_result = await self._query_accts(payment.phone)
        accounts = self._load_account_list(api_result.get('data'))
        if not accounts:
            raise NewApiError(ErrorCode.QueryAccts, 'can not find any account')

        active_accounts = self._filter_active_accounts(accounts)
        if not active_accounts:
            raise NewApiError(ErrorCode.QueryAccts, 'can not find any active account')

        raw_json = json.dumps(accounts, ensure_ascii=False)
        with self.handler.db_orm.sessionmaker() as session:
            session.execute(
                update(Payment)
                .where(Payment.id == payment.id)
                .values(account_entire=raw_json)
            )
            session.commit()

        payment.account_entire = raw_json
        self.logger.info(
            f'{self._log_key(funcName)} payment_id={payment.id}, active_accounts={len(active_accounts)}'
        )
        return raw_json, active_accounts

    async def query_bound_accounts_http(self, payment):
        raw_json, active_accounts = await self._query_bound_accounts(payment)
        return {
            'status': 'success',
            'data': {
                'payment_id': payment.id,
                'account_selected': payment.account_accno or '',
                'account_entire': active_accounts,
                'account_entire_raw': raw_json,
            }
        }

    async def select_bound_account_http(self, payment, accno):
        funcName = 'select_bound_account_http'
        raw_json = payment.account_entire
        accounts = self._load_account_list(raw_json)
        if not accounts:
            raw_json, _ = await self._query_bound_accounts(payment)
            accounts = self._load_account_list(raw_json)

        active_accounts = self._filter_active_accounts(accounts)
        selected_account = next(
            (acc for acc in active_accounts if str(acc.get('accno', '')) == str(accno)),
            None,
        )
        if not selected_account:
            raise NewApiError(ErrorCode.SelectAccts, 'Selected account is not available')

        iban = selected_account.get('IBAN') or selected_account.get('iban')
        if not iban:
            raise NewApiError(ErrorCode.SelectAccts, 'IBAN can not be found')

        account_type_str = self._determine_account_type(
            json.dumps(selected_account, ensure_ascii=False),
            account_accno=accno,
            account_iban=iban,
        )
        account_type_value = self._convert_account_type_to_int(account_type_str)
        business_status = self._selected_account_business_status(
            1,
            getattr(payment, 'status', 0),
            getattr(payment, 'certified', 0),
            getattr(payment, 'manual_status', 0),
        )

        with self.handler.db_orm.sessionmaker() as session:
            session.execute(
                update(Payment)
                .where(Payment.id == payment.id)
                .values(
                    account_entire=raw_json,
                    account_accno=accno,
                    account_iban=iban,
                    account_type=account_type_value,
                    wallet_status=1,
                    **business_status,
                )
            )
            session.commit()

        payment.account_entire = raw_json
        payment.account_accno = accno
        payment.account_iban = iban
        payment.account_type = account_type_value
        self.logger.info(
            f'{self._log_key(funcName)} payment_id={payment.id}, accno={accno}, account_type={account_type_value}'
        )
        return {
            'status': 'success',
            'data': {
                'payment_id': payment.id,
                'account_selected': accno,
                'account': selected_account,
                'account_type': account_type_value,
            }
        }

    async def select_accts_http(self, data):
        """账户选择"""
        funcName = 'select_accts_http'
        lockName = 'select_accts'
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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            accno = data['accno']
            
            # [LOCK] 获取基于真实payment_id的接口锁
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error
            
            session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
            redis_key = session_ctx.get('redis_key')
            session_data = session_ctx.get('session_data')
            if not session_data:
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call query_accts_http first')
            if session_ctx.get('is_aliased'):
                self.logger.info(
                    f'{self._log_key(funcName)} payment_id桥接: requested={requested_payment_id} -> resolved={payment_id}'
                )

            self._assert_status_transition(
                session_data,
                LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                LoginStatus.ACTIVE_SUCCESSFUL,
                funcName,
            )

            raw = session_data.get('account_entire')
            accounts = json.loads(raw) if raw else []
            iban = next((acc['IBAN'] for acc in accounts if acc['accno'] == accno), None)
            if not iban:
                raise NewApiError(ErrorCode.SelectAccts, f'IBAN can not be found')
            
            # 检测账户类型
            account_type_value = ACCOUNT_TYPE_UNKNOWN
            phone = session_data.get('phone', '')
            payment_id = session_data.get('id', '')
            try:
                self.logger.info(f'[Phone: {phone}] [PaymentID: {payment_id}] 开始检测账户类型...')
                # 从账户列表中找到选中的账户
                selected_account = next((acc for acc in accounts if acc['accno'] == accno), None)
                if selected_account:
                    # 将选中的账户转换为JSON字符串进行检测
                    selected_account_json = json.dumps(selected_account)
                    account_type_str = self._determine_account_type(
                        account_entire=selected_account_json,
                        account_accno=accno,
                        account_iban=iban
                    )
                    account_type_value = self._convert_account_type_to_int(account_type_str)
                    self.logger.info(f'[Phone: {phone}] [PaymentID: {payment_id}] 检测到账户类型: {account_type_str} (值={account_type_value})')
            except Exception as e:
                self.logger.error(f'[Phone: {phone}] [PaymentID: {payment_id}] 账户类型检测失败: {str(e)}', exc_info=True)
                account_type_value = ACCOUNT_TYPE_UNKNOWN
            
            self.logger.info(f'{self._log_key(funcName)} 正在更新payment...')
            await self._update_payment(payment_id, session_data, account_accno=accno, account_iban=iban, account_type=account_type_value)
            await self._update_session_status(
                redis_key,
                session_data,
                LoginStatus.ACTIVE_SUCCESSFUL,
                {
                    'account_accno': accno,
                    'account_iban': iban,
                    'last_error': None,
                }
            )
            
            result = {
                'status': 'success',
                'data': {
                    'phase': LoginStatus.ACTIVE_SUCCESSFUL,
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
            raise NewApiError(ErrorCode.SelectAccts, f'Select Account failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')

    async def select_acct_http(self, data):
        return await self.select_accts_http(data)

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
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            payment_ids = data['payment_ids']
            paymentIDArray = [x.strip() for x in payment_ids.split(",") if x.strip()]
            
            next_action_map = {
                LoginStatus.PRE_LOGIN_CREATED: 'get_otp',
                LoginStatus.OTP_SENT: 'verify_otp',
                LoginStatus.OTP_VERIFIED: 'verify_otp',
                LoginStatus.FINGERPRINT_UPLOAD_REQUIRED: 'upload_fingerprint',
                LoginStatus.FINGERPRINT_UPLOADED: 'verify_fingerprint',
                LoginStatus.FINGERPRINT_VERIFIED: 'second_login',
                LoginStatus.SECOND_LOGIN_READY: 'second_login',
                LoginStatus.SECOND_LOGIN_PASSED: 'query_accts',
                LoginStatus.AWAITING_PIN_CHANGE: 'change_pin',
                LoginStatus.ACCOUNT_SELECTION_REQUIRED: 'select_accts',
                LoginStatus.ACTIVE_SUCCESSFUL: 'ready',
            }

            objs = []
            for payment_id in paymentIDArray:
                session_ctx = await self._resolve_session_context(bankname, payment_id)
                resolved_payment_id = session_ctx.get('resolved_payment_id') or payment_id
                session_data = session_ctx.get('session_data')
                if not session_data:
                    continue

                obj = {
                    "payment_id": payment_id,
                    "resolved_payment_id": resolved_payment_id if resolved_payment_id != payment_id else None,
                    "status": session_data.get('status', ''),
                    "error": session_data.get('last_error'),
                    "cd_until": session_data.get('cd_until', 0),
                    "next_action": next_action_map.get(session_data.get('status'), 'unknown'),
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
    async def _is_account_registered(self, phone):
        funcName = '云机注册检查'
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_is_account_registered_request(phone)

        response = self.retry_make_request(method='POST', url=url, data=request_data)
        self._log_response(funcName, response)

        if not response or response.status_code != 200:
            raise NewApiError(
                'EP_REGISTER_CHECK_FAILED',
                'Could not confirm EasyPaisa cloud registration; refusing to run loginStep1'
            )

        response_data = self._decode_indus_response(funcName, response.text)
        if not isinstance(response_data, dict):
            raise NewApiError(
                'EP_REGISTER_CHECK_FAILED',
                'Invalid EasyPaisa cloud registration response'
            )

        if response_data.get('code') != 200:
            raise NewApiError(
                'EP_REGISTER_CHECK_FAILED',
                response_data.get('msg') or 'EasyPaisa cloud registration check failed'
            )

        return response_data.get('data') is True

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
        if status in [ 100, 200 ]:
            return {
                'status': 'success',
                'message': 'OTP验证成功',
                'data': {'serv_gen_id': serv_gen_id}
            }
        else:
            raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {status_desc}')

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
            # 【v1.8版本】跳过指纹验证
            if EASYPAISA_API_VERSION == 'v1.8':
                self.logger.info(f'{self._log_key(funcName)} v1.8模式: 跳过指纹验证')
                isNeedFingerPring = False
            else:
                # 【v1.6版本】先验证指纹，后验证PIN
                funcName = f'{baseName} - 指纹信息'
                # region verify_fingerprint
                # 构建请求数据
                request_data = self._build_verify_fingerprint_request(session_data)
                
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
                status_desc = response_data.get('msg')
                
                self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')
                # endregion verify_fingerprint
            
                if status in [ 100, 200 ]:
                    isNeedFingerPring = False
                else:
                    isNeedFingerPring = True
                    # 指纹验证失败，直接返回，不再执行PIN验证
                    self.logger.warning(f'{self._log_key(funcName)} 指纹验证失败，跳过PIN验证')
                    result.IsNeedFingerPrint = isNeedFingerPring
                    return result
            
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
            status_desc = (response_data.get("data") or {}).get("msgCd", "无状态描述")
            
            self.logger.info(f'{self._log_key(funcName)} 银行响应状态分析: status: {status}, statusDesc: {status_desc}')
            # endregion verify_account
            
            # 1. 网络不稳定（503）- 抛异常重试
            if status in [ 503 ]:
                raise NewApiError(ErrorCode.Retry, 'unstable network, please try agagin')
        
            # 2. 会话过期（501 + URM10004）- 最高优先级处理，立即返回
            if status == 501 and status_desc == 'URM10004':
                self.logger.warning(f'{self._log_key(funcName)} 检测到会话过期 (501 + URM10004)，需要强制下线')
                result.IsNeedRelogin = True
                result.IsSuccess = False
                result.IsNeedFingerPrint = isNeedFingerPring
                return result
        
            # 3. 其他非成功状态码的细分处理
            if status not in [ 100, 200 ]:
                if status_desc in [ 'URM40008' ]:
                    result.IsInCoolDown = True
                if status_desc in [ 'URM20060' ]:
                    result.IsNeedRelogin = True
                if status_desc in [ 'URM20008', 'URM20017' ]:
                    result.IsNeedChangePin = True
        
        # 4. 设置指纹状态
        # v1.8版本：强制设置为False
        if EASYPAISA_API_VERSION == 'v1.8':
            result.IsNeedFingerPrint = False
            self.logger.info(f'{self._log_key(funcName)} v1.8模式: 强制设置 IsNeedFingerPrint=False')
        else:
            result.IsNeedFingerPrint = isNeedFingerPring
        
        # 5. 最终判断是否成功
        if not result.IsInCoolDown and not result.IsNeedRelogin and not result.IsNeedChangePin and not result.IsNeedFingerPrint:
            result.IsSuccess = True
        else:
            result.IsSuccess = False
            
        return result

    async def _force_logout(self, payment_id, bankname, reason='UNKNOWN'):
        """
        强制下线账号，清理所有相关状态
        参考 pakistanpay_v2.py 的 on_off(_on=0) 逻辑
        
        Args:
            payment_id: 支付账号ID
            bankname: 银行名称 (如 'easypaisa')
            reason: 下线原因 (如 'URM10004_SESSION_EXPIRED')
            
        Returns:
            bool: 是否成功
        """
        funcName = '强制下线'
        
        try:
            self.logger.warning(f'{self._log_key(funcName)} 开始执行: payment_id={payment_id}, bankname={bankname}, reason={reason}')

            # === 1. 查询 payment / phone / channel，用于统一当前登录会话下线 ===
            payment = None
            try:
                with self.handler.db_orm.sessionmaker() as session:
                    payment = session.query(Payment).filter(Payment.id == payment_id).first()

                if not payment:
                    self.logger.error(f'{self._log_key(funcName)} [1/4] 数据库中未找到 payment_id={payment_id}，将仅清理 Redis 残留')
                else:
                    self.logger.info(f'{self._log_key(funcName)} [1/4] 查询 payment 成功: phone={getattr(payment, "phone", None)}, channel={getattr(payment, "channel", None)}')

            except Exception as e:
                self.logger.error(f'{self._log_key(funcName)} [1/4] 查询 payment 失败: {e}')

            resolved_phone = None
            if payment and getattr(payment, 'phone', None):
                resolved_phone = payment.phone
            # === 2. 清理当前上号会话；历史 Redis 垃圾交由独立脚本处理 ===
            login_session_keys = self._current_login_session_keys(payment_id, resolved_phone)
            deleted_sessions = await self.redis.delete(*login_session_keys)
            await self.redis.hdel('hash_easypaisa', payment_id)
            await self.redis.zrem('set_easypaisa', payment_id)
            self.logger.info(
                f'{self._log_key(funcName)} [2/4] 当前会话队列清理完成: '
                f'phone={resolved_phone}, deleted={deleted_sessions}'
            )

            # === 3. 清理会话数据，避免下次登录被旧 session / pre_login 卡住 ===
            pre_login_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            deleted_session = await self.redis.delete(pre_login_key)
            self.logger.info(f'{self._log_key(funcName)} [3/4] 清理会话完成: pre_login={pre_login_key}, deleted={deleted_session}')

            # === 4. 更新数据库 payment.status = 0, certified = 0 ===
            try:
                if not payment:
                    self.logger.warning(f'{self._log_key(funcName)} [4/4] payment 不存在，跳过数据库更新（Redis 已清理）')
                else:
                    with self.handler.db_orm.sessionmaker() as session:
                        result = session.execute(
                            update(Payment).where(
                                Payment.id == payment_id
                            ).values(
                                status=0,
                                certified=0,
                                wallet_status=0,
                                collection_status=0,
                                payout_status=0,
                            )
                        )
                        session.commit()

                        if result.rowcount > 0:
                            self.logger.info(f'{self._log_key(funcName)} [4/4] 更新数据库成功: payment_id={payment_id}, status=0, certified=0, rows={result.rowcount}')
                        else:
                            self.logger.warning(f'{self._log_key(funcName)} [4/4] 更新数据库: 没有匹配的记录 (rowcount=0)')

            except Exception as e:
                self.logger.error(f'{self._log_key(funcName)} [4/4] 更新数据库失败: {e}')
                return False

            self.logger.warning(f'{self._log_key(funcName)} 执行完成: payment_id={payment_id}, reason={reason}')
            return True
            
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.logger.error(f'{self._log_key(funcName)} 执行失败: {e}\n{tb_str}')
            return False

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

    async def _perform_verify_fingerprint(self, session_data):
        funcName = '指纹验证'
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_verify_fingerprint_request(session_data)

        response = self.retry_make_request(method='POST', url=url, data=request_data)
        self._log_response(funcName, response)

        if not response:
            return {'outcome': 'transient', 'message': 'empty response'}

        if response.status_code != 200:
            message = (response.text or '').strip()
            if self._is_verify_fingerprint_rejected_message(message):
                return {'outcome': 'rejected', 'message': message}
            return {'outcome': 'transient', 'message': f'http {response.status_code}'}

        raw_text = response.text
        normalized = raw_text.strip().strip('"').lower()
        if normalized == 'true':
            return {'outcome': 'success'}

        response_data = self._decode_indus_response(funcName, raw_text)
        if isinstance(response_data, bool):
            return {'outcome': 'success' if response_data else 'transient', 'message': raw_text}

        if isinstance(response_data, str):
            normalized = response_data.strip().strip('"').lower()
            if normalized == 'true':
                return {'outcome': 'success'}
            if self._is_verify_fingerprint_rejected_message(response_data):
                return {'outcome': 'rejected', 'message': response_data}
            return {'outcome': 'transient', 'message': response_data}

        if not isinstance(response_data, dict):
            return {'outcome': 'transient', 'message': raw_text}

        code = response_data.get('code')
        msg = response_data.get('msg', '')
        data_field = response_data.get('data') or {}
        msg_cd = data_field.get('msgCd') if isinstance(data_field, dict) else ''
        message = msg_cd or msg or raw_text

        if code in [100, 200]:
            return {'outcome': 'success'}
        if message == 'URM10004':
            return {'outcome': 'session_expired', 'message': message}
        if message == 'URM40008':
            return {'outcome': 'cooldown', 'message': message}
        if self._is_verify_fingerprint_rejected_message(message):
            return {'outcome': 'rejected', 'message': message}
        return {'outcome': 'transient', 'message': message or raw_text}

    @staticmethod
    def _is_verify_fingerprint_rejected_message(message) -> bool:
        if not message:
            return False

        text = str(message)
        normalized = text.lower()
        return any(
            marker in text or marker in normalized
            for marker in (
                '缺少指纹数据',
                '不支持的action',
                '指纹数据失败',
                '指纹数据包',
                'fingerprint data corruption',
            )
        )

    async def _perform_second_login(self, session_data):
        funcName = '二次登录'
        url = self.API_ENDPOINTS['base_url']
        request_data = self._build_verify_account_request(session_data)

        response = self.retry_make_request(method='POST', url=url, data=request_data)
        self._log_response(funcName, response)

        if not response:
            return {'outcome': 'upstream_error', 'message': 'empty response'}
        if response.status_code != 200:
            return {'outcome': 'upstream_error', 'message': f'http {response.status_code}'}

        response_data = self._decode_indus_response(funcName, response.text)
        if not isinstance(response_data, dict):
            return {'outcome': 'upstream_error', 'message': response.text}

        status = response_data.get('code')
        msg = response_data.get('msg', '')
        data_field = response_data.get('data') or {}
        msg_cd = data_field.get('msgCd') if isinstance(data_field, dict) else ''
        message = msg_cd or msg

        if status in [100, 200]:
            return {'outcome': 'success', 'message': message}
        if message == 'URM10004':
            return {'outcome': 'session_expired', 'message': message}
        if message == 'URM40008':
            return {'outcome': 'cooldown', 'message': message}
        if message in ['URM20008', 'URM20017']:
            return {'outcome': 'needs_pin_change', 'message': message}
        return {'outcome': 'upstream_error', 'message': message or response.text}

    def _is_server_busy(self, message: str) -> bool:
        return '423' in str(message) or 'ServerBusy' in str(message)

    async def _fallback_to_first_login(self, session_data: dict, redis_key: str, reason: str) -> dict:
        """secondLogin失败后回退到loginStep1，重新发送OTP"""
        phone = session_data.get('phone', '')
        payment_id = session_data.get('payment_id') or session_data.get('id', '')

        self.logger.warning(
            f'{self._log_key("_fallback_to_first_login")} secondLogin失败({reason})，'
            f'回退到loginStep1, phone={phone}, payment_id={payment_id}'
        )

        try:
            # 先尝试 loginStep1，成功前不清理旧 session。
            otp_result = await self._send_otp(session_data)

            otp_status = otp_result.get('outcome') or otp_result.get('status') if otp_result else ''
            if otp_status != 'success':
                # loginStep1 也失败时保留旧 session。
                self.logger.warning(
                    f'{self._log_key("_fallback_to_first_login")} loginStep1也失败，'
                    f'保留旧session, phone={phone}'
                )
                return {
                    'status': 'error',
                    'message': f'secondLogin失败且loginStep1也失败: {reason}',
                    'data': {
                        'code': 'SL_UPSTREAM_ERROR',
                        'phase': 'failed',
                    }
                }

            # loginStep1 成功后，将同一个 Redis key 覆盖为 otpSent 状态。
            new_session = {
                'phone': phone,
                'payment_id': payment_id,
                'id': payment_id,
                'bankname': session_data.get('bankname', ''),
                'pinCode': session_data.get('pinCode', ''),
                'partner_id': session_data.get('partner_id', ''),
                'device_id': session_data.get('device_id', ''),
                'app_version': session_data.get('app_version', ''),
                'status': 'otpSent',
                'fallback_from': 'secondLogin',
                'fallback_reason': reason,
            }

            await self._persist_session_data(redis_key, new_session)
            await self.redis.expire(redis_key, 300)

            # 释放登录流程锁，允许用户按 OTP 流程重新注册。
            if payment_id:
                lock_key = self._login_lock_payment_key(payment_id)
                await self.redis.delete(lock_key)
            if phone:
                lock_key = self._login_lock_phone_key(phone)
                await self.redis.delete(lock_key)

            self.logger.info(
                f'{self._log_key("_fallback_to_first_login")} 回退成功，'
                f'已发送OTP, phone={phone}, payment_id={payment_id}'
            )

            return {
                'status': 'error',
                'message': 'secondLogin失败，已回退到OTP验证',
                'data': {
                    'code': 'SL_RESTARTED',
                    'phase': 'otpSent',
                }
            }

        except Exception as e:
            self.logger.error(
                f'{self._log_key("_fallback_to_first_login")} 回退异常: {str(e)}, '
                f'phone={phone}, payment_id={payment_id}'
            )
            return {
                'status': 'error',
                'message': f'回退失败: {str(e)}',
                'data': {
                    'code': 'SL_UPSTREAM_ERROR',
                    'phase': 'failed',
                }
            }

    def _get_payment_fingerprint_path(self, payment_id):
        funcName = '读取 payment.fingerprint_path'
        try:
            with self.handler.db_orm.sessionmaker() as session:
                payment = session.query(Payment).filter(Payment.id == payment_id).first()
                if not payment:
                    return None
                return payment.fingerprint_path
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _clear_payment_fingerprint_path(self, payment_id):
        funcName = '清理 payment.fingerprint_path'
        try:
            with self.handler.db_orm.sessionmaker() as session:
                session.execute(
                    update(Payment).where(Payment.id == payment_id).values(fingerprint_path=None)
                )
                session.commit()
            self.logger.info(f'{self._log_key(funcName)} 已清空 payment_id={payment_id} 的指纹路径')
        except Exception as e:
            self.logger.warning(f'{self._log_key(funcName)} 清理失败但忽略: {str(e)}')

    async def _replay_saved_fingerprint(self, payment_id, phone) -> bool:
        funcName = '重放本地指纹'
        try:
            fingerprint_path = self._get_payment_fingerprint_path(payment_id)
            if not fingerprint_path:
                return False
            if not os.path.exists(fingerprint_path):
                return False

            with open(fingerprint_path, 'rb') as fp:
                file_body = fp.read()

            file_name = os.path.basename(fingerprint_path)
            session_data = {
                'bankname': SVRNAME,
                'phone': phone,
            }
            request_data, files = self._build_upload_fingerprint_request(session_data, file_name, file_body)
            response = self.retry_make_request(
                method='',
                url=self.API_ENDPOINTS['fingerprint_upload_url'],
                data=request_data,
                files=files,
            )
            if not response:
                return False
            if response.status_code != 200:
                return False
            return response.text == 'ok'
        except Exception as e:
            self.logger.warning(f'{self._log_key(funcName)} 重放失败: {str(e)}')
            return False

    async def _query_accts(self, phone):
        funcName = '账户查询'
            
        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')
        
        # 构建请求数据
        request_data = self._build_query_accts_request(phone)
        
        if ISTEST:
            data = [
                {
                    "accno": "88521642", 
                    "accountFri": "FRI:88521642/MM", 
                    "accountKey": "icLQm3g6KW7HvLXP0SKaTw==", 
                    "accountLevel": "3", 
                    "accountProfile": "L1", 
                    "accountName": "Easypaisa Wallet", 
                    "accountNameUr": "ایزی پیسہ والیٹ", 
                    "accountBalance": "20763.00", 
                    "accountStatus": "ACTIVE", 
                    "eligibleForAda": "false", 
                    "IBAN": "PK12TMFB0000000088521642"
                },
                {
                    "accno": "88521643", 
                    "accountFri": "FRI:88521643/MM", 
                    "accountKey": "icLQm3g6KW7HvLXP0SKaTw==", 
                    "accountLevel": "3", 
                    "accountProfile": "L1", 
                    "accountName": "abcd", 
                    "accountNameUr": "abcedfg", 
                    "accountBalance": "500.00", 
                    "accountStatus": "ACTIVE", 
                    "eligibleForAda": "false", 
                    "IBAN": "PK12TMFB0000000088521643"
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
            raise NewApiError(ErrorCode.ChangePin, f"Query Accounts failed: {response_data.get('msg')}")

    def _query_accts_default(self, accounts):
        record = next((acc for acc in accounts if acc.get("accountName") == "Easypaisa Wallet"), None)
        return record

    # ================== 请求构建方法 ==================
    def _build_is_account_registered_request(self, phone):
        funcName = '构建云机注册检查'
        request_msg = {
            "account_id": phone,
        }
        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')
        return self._encode_indus_request(funcName, 'isAccountRegistered', request_msg)

    def _build_send_otp_request(self, session_data):
        funcName = '构建OTP发送'
        
        # 获取基础参数
        phone = session_data.get('phone')
        pinCode = session_data.get('pinCode')
        
        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, pin: ******')
        
        request_msg = {
            "account_id": phone,
            "phone": phone,
            "pwd": pinCode
        }
        
        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')
        
        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['send_otp'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')
        
        return encoded_msg

    def _build_verify_otp_request(self, session_data, otp):
        funcName = '构建OTP验证'
        
        # 获取基础参数
        phone = session_data.get('phone')
        
        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, otp: {otp}')
        
        request_msg = {
            "account_id": phone,
            "otpcode": otp
        }
        
        # v1.8版本：添加 should_verify_fingerprint 参数禁用指纹验证
        if EASYPAISA_API_VERSION == 'v1.8':
            request_msg["should_verify_fingerprint"] = False
            self.logger.info(f'{self._log_key(funcName)} v1.8模式: 已添加 should_verify_fingerprint=False')
        
        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')
        
        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['verify_otp'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')
        
        return encoded_msg

    def _build_verify_account_request(self, session_data):
        funcName = '构建账号验证'
        
        # 获取基础参数
        phone = session_data.get('phone')
        
        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')
        
        request_msg = {
            "account_id": phone,
        }
        
        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f'{self._log_key(funcName)} 原始JSON: {json_str}')
        
        encoded_msg = self._encode_indus_request(funcName, self.API_ENDPOINTS['verify_account'], json_str)
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')
        
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
        
        encoded_msg = self._encode_indus_request(
            funcName,
            self.API_ENDPOINTS['verify_fingerprint'],
            request_msg,
        )
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')
        
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
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')
        
        return encoded_msg

    def _build_upload_fingerprint_request(self, session_data, file_name, file_body):
        funcName = '构建指纹上传'
        
        # 获取基础参数
        bankname = session_data.get('bankname')
        phone = session_data.get('phone')
        
        self.logger.info(f'{self._log_key(funcName)} 构建请求所需参数: bankname: {bankname}, phone: {phone}, file: ***')
        
        data = {
            "app": bankname,
            "phone": phone,
        }
        
        files = {
            "file": (file_name, file_body, "application/zip"),
        }
        
        # request_msg = aiohttp.FormData()
        # request_msg.add_field("app", "easypaisa")
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
        self.logger.info(f'{self._log_key(funcName)} 加密完成, 长度: {len(encoded_msg)}, 预览: {encoded_msg[:100]}...')
        
        return encoded_msg

    def _encode_indus_request(self, funcName, action: str, payload: dict) -> str:
        funcName = '消息编码'
        try:
            
            outer = dict()
            
            # 置随机UUID
            outer["id"] = str(uuid.uuid4())
            
            # 设置业务方法
            outer["action"] = action
            
            # 设置业务数据
            outer["payload"] = payload
            
            # 转JSON字符串
            outer_json = json.dumps(outer)
            
            # Base64编码
            outer_base64 = base64.b64encode(outer_json.encode('utf-8')).decode('utf-8')
            
            # 拼接密钥并MD5
            outer_base64_combine_secret = outer_base64 + APISECRET
            
            sign = hashlib.md5(outer_base64_combine_secret.encode('utf-8')).hexdigest()
            result = f'user_id={APIKEY}&data={outer_base64}&sign={sign}'
            self.logger.info(f'{self._log_key(funcName)} 加密成功，原文：{outer_json}, 签名: {sign}, 最终: {result}')
            
            return result
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return ''

    def _decode_indus_response(self, funcName, response_data):
        funcName = funcName + ' 消息解码'
        try:
            result = {}
            self.logger.info(f'{self._log_key(funcName)} 解码前: {response_data}')
            if isinstance(response_data, dict):
                # 检查是否有加密的resp字段
                if 'resp' in response_data:
                    # 解码加密的响应
                    decoded_resp = self.decode_message(response_data['resp'])
                    result = json.loads(decoded_resp)
                else:
                    # 如果已经是字典且没有resp字段，直接返回
                    result = response_data
            elif isinstance(response_data, str):
                # 如果是字符串，尝试JSON解析
                result = json.loads(response_data)
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
            
            # 查询现有记录。手机号归属是业务唯一约束，不能只看当前码商。
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
                        'wallet_status': getattr(existing_payment, 'wallet_status', 0),
                        'time_create': existing_payment.created_at.isoformat() if existing_payment.created_at else None,
                        'account_entire': existing_payment.account_entire,
                        'account_accno': existing_payment.account_accno,
                        'account_iban': existing_payment.account_iban,
                    }
                    return payment_info
                else:
                    self.logger.info(f'{self._log_key(funcName)} 未找到')
            return None
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _query_bound_payment_for_current_partner(self, bankname, payment_id):
        funcName = '查询当前码商绑定payment'
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

        is_registered = await self._is_account_registered(phone)
        if not is_registered:
            raise NewApiError(
                'EP_CLOUD_NOT_REGISTERED',
                'Bound EasyPaisa account is not registered on cloud machine; reset manually before first login'
            )

        now_ts = int(time.time())
        return {
            'id': payment_id,
            'partner_id': getattr(payment, 'user_id', None),
            'phone': phone,
            'original_phone': phone,
            'status': LoginStatus.SECOND_LOGIN_READY,
            'status_history': [LoginStatus.SECOND_LOGIN_READY],
            'time': now_ts,
            'try_count': 0,
            'bankname': bankname,
            'pinCode': getattr(payment, 'pin', None),
            'password': getattr(payment, 'net_trade_pw', None),
            'name': getattr(payment, 'name', '') or '',
            'is_new_user': False,
            'last_status_change': now_ts,
            'last_request_time': now_ts,
            'account_entire': getattr(payment, 'account_entire', None),
            'account_accno': getattr(payment, 'account_accno', None),
            'account_iban': getattr(payment, 'account_iban', None),
            'qr_channel': getattr(payment, 'channel', None) or 1001,
        }

    async def _save_payment(self, session_data, name=None, pin=None, fingerprint_path=None):
        funcName = '保存payment数据到数据库'
        try:
            # 从session_data获取必要信息
            bankname = session_data['bankname']
            phone = session_data['phone']
            partner_id = session_data.get('partner_id')
            
            self.logger.info(f'{self._log_key(funcName)} 参数: partner_id={partner_id}, bankname={bankname}, phone={phone}')
            
            existing_payment = await self._check_payment(bankname, phone, partner_id)
            if not existing_payment:
                return await self._create_payment(session_data, name)
            else:
                return await self._update_payment(existing_payment['id'], session_data, name, pin, fingerprint_path)
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _create_payment(self, session_data, name):
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
                'account_entire': None, # 第三方账号-完整的
                'account_accno': None, # 第三方账号-选中的accno
                'account_iban': None,  # 第三方账号-选中的iban
                'account_type': ACCOUNT_TYPE_UNKNOWN,  # 账户类型：0=未知，10=钱包，20=银行账户，30=商户账户
                # created_at字段有默认值，不需要手动设置
            }
            
            # 只有当name不为空时才设置name字段
            if name:
                payment_data['name'] = name
                self.logger.info(f'{self._log_key(funcName)} 设置 name: {name}')
            
            # 使用SQLAlchemy插入数据
            with self.handler.db_orm.sessionmaker() as session:
                new_payment = Payment(**payment_data)
                session.add(new_payment)
                try:
                    session.commit()
                except IntegrityError as exc:
                    session.rollback()
                    self.logger.warning(
                        f'{self._log_key(funcName)} 命中唯一键冲突，尝试复用现有payment: '
                        f'partner_id={partner_id}, bankname={bankname}, phone={phone}, error={exc}'
                    )
                    existing_payment = await self._check_payment(bankname, phone, partner_id)
                    if existing_payment:
                        if existing_payment.get('user_id') == partner_id:
                            self.logger.info(
                                f'{self._log_key(funcName)} 唯一键冲突后复用既有payment: {existing_payment.get("id")}'
                            )
                            return existing_payment.get('id')
                        raise NewApiError('10402', 'UPI already occupied by another user')
                    raise
                payment_id = new_payment.id
                
            self.logger.info(f'{self._log_key(funcName)} 数据库插入成功: ID={payment_id}')
            return payment_id
            
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
            return None

    async def _update_payment(self, existing_payment_id, session_data, name=None, pin=None, fingerprint_path=None, account_entire=None, account_accno=None, account_iban=None, account_type=None):
        funcName = '更新现有payment记录'
        try:
            phone = session_data.get('phone', '')
            isOn = 1 if session_data.get('status', '') == LoginStatus.ACTIVE_SUCCESSFUL else 0
            current_payment_state = None
            if account_accno:
                with self.handler.db_orm.sessionmaker() as session:
                    current_payment_state = session.query(
                        Payment.status,
                        Payment.certified,
                        Payment.manual_status,
                    ).filter(Payment.id == existing_payment_id).first()
            
            # 构建更新数据（使用正确的Python模型字段名）
            update_data = {
                'remarks': None,  # 清理remarks字段，重新登录时清空之前的错误信息
                'upi': phone,
                'upi_list': ','.join([ phone ]),  # UPI列表，逗号分隔
            }
            
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
                update_data['wallet_status'] = 1
                next_status = 1 if isOn == 1 else getattr(current_payment_state, 'status', 0)
                next_certified = getattr(current_payment_state, 'certified', 0)
                next_manual_status = getattr(current_payment_state, 'manual_status', 0)
                update_data.update(
                    self._selected_account_business_status(
                        1,
                        next_status,
                        next_certified,
                        next_manual_status,
                    )
                )
                self.logger.info(f'{self._log_key(funcName)} 更新 account_accno: {account_accno}')
            
            if account_iban:
                update_data['account_iban'] = account_iban
                self.logger.info(f'{self._log_key(funcName)} 更新 account_iban: {account_iban}')
            
            if account_type is not None:
                update_data['account_type'] = account_type
                self.logger.info(f'[Phone: {phone}] [PaymentID: {existing_payment_id}] 更新 account_type: {account_type}')
            
            if isOn == 1:
                update_data['status'] = 1
                self.logger.info(f'{self._log_key(funcName)} 更新 status: {1}')
            
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

    async def _save_fingerprint(self, session_data, file_body, bankname, payment_id, phone) -> bool:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.FINGERPRINT_PATH)
        os.makedirs(path, exist_ok=True)
        save_path = os.path.join(path, self.FINGERPRINT_FILENAME.format(bankname=bankname, payment_id=payment_id, phone=phone))
        with open(save_path, "wb") as f:
            f.write(file_body)
        return await self._save_payment(session_data, fingerprint_path=save_path)
