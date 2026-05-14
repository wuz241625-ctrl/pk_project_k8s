import json
import time
import asyncio
import hashlib
import base64
import random
import bcrypt
import logging
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
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
ACCOUNT_TYPE_UNKNOWN = 0     # 未知/未检测
ACCOUNT_TYPE_WALLET = 10     # 钱包账户
ACCOUNT_TYPE_BANK = 20       # 银行账户
ACCOUNT_TYPE_MERCHANT = 30   # 商户账户（仅JazzCash）
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
class LoginStatus:
    PRE_LOGIN_CREATED = "preLoginCreated"
    OTP_SENT = "otpSent"
    OTP_VERIFIED = "otpVerified"
    FINGERPRINT_VERIFIED = "fingerprintVerified"
    AWAITING_PIN_CHANGE = "awaitingPinChange"
    ACCOUNT_SELECTION_REQUIRED = "accountSelectionRequired"
    ACTIVE_SUCCESSFUL = "activeSuccessful"
    NEEDS_RELOGIN = "needsRelogin"

STATUS_TRANSITIONS = {
    LoginStatus.PRE_LOGIN_CREATED: [
        LoginStatus.OTP_SENT,
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        LoginStatus.OTP_VERIFIED,
        LoginStatus.AWAITING_PIN_CHANGE,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.OTP_SENT: [
        LoginStatus.OTP_SENT,
        LoginStatus.OTP_VERIFIED,
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        LoginStatus.PRE_LOGIN_CREATED,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.OTP_VERIFIED: [
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.FINGERPRINT_VERIFIED: [
        LoginStatus.ACCOUNT_SELECTION_REQUIRED,
        LoginStatus.AWAITING_PIN_CHANGE,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.AWAITING_PIN_CHANGE: [
        LoginStatus.FINGERPRINT_VERIFIED,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.ACCOUNT_SELECTION_REQUIRED: [
        LoginStatus.ACTIVE_SUCCESSFUL,
        LoginStatus.NEEDS_RELOGIN,
    ],
    LoginStatus.ACTIVE_SUCCESSFUL: [],
    LoginStatus.NEEDS_RELOGIN: [],
}
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
    # === v1.9 重构错误码映射（Task 0 commitment）===
    # 实现 *_http 方法时，所有 spec 中 EP_xxx 占位符按下表映射成 APP 已识别码：
    #   EP_LOGINED            → ErrorCode.Logined        (20101)
    #   EP_MISSING_PARAMS     → ErrorCode.MissingParams  (20001)
    #   EP_INVALID_PASSWORD   → ErrorCode.InvalidPaswd   (20004)
    #   EP_LOGIN_ATTEMPS      → ErrorCode.LoginAttemps   (20106)
    #   EP_PAYMENT_NOT_FOUND  → ErrorCode.InvalidBankOrPayment (20003)
    #   EP_PERMISSION_DENIED  → '10402'
    #   EP_PAYMENT_PHONE_MISMATCH → ErrorCode.PaymentPhoneMismatch (20005)
    #   EP_OTP_INVALID        → ErrorCode.VerifyOTPFail  (20307)
    #   EP_BAD_STATE/THROTTLED/BAD_REQUEST → 'INVALID_TRANSITION' + state hint
    #   EP_NETWORK/QUERY_FAIL/SYSTEM_ERROR  → 'SL_UPSTREAM_ERROR'
    #   EP_FP_PUSH_FAIL       → 'FP_UPSTREAM_REJECTED'
    #   EP_FP_FILE_MISSING    → 'EP_FP_FILE_MISSING' (本次唯一新增；APP 暂回退 needsRelogin)
    # ===============================================
class EasyPaisa:
    LOGIN_TYPE = 'sms_otp_pin'
    BANK_NAME_MAPPING = {
        'easypaisa': 'EASYPAISA',
    }
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
        self.name = SVRNAME
        self.login_data = {}  # 登录数据，用于错误日志
        self.lock_time_payment_interface = 300  # 操作锁的锁定时间（秒） - 5分钟
        self.lock_time_payment_interface_diff = 10  # 操作锁的锁定时间（秒） - 10秒差
        self.lock_time_login_duplicate_avoid = 600  # 操作锁的锁定时间（秒） - 10分钟
        self.expire_time_login_pending = 300
        self.RESEND_COOLDOWN_SECONDS = 20
        self.error_manager = ErrorManager()
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
        if not account_entire:
            self.logger.debug(f'{self._log_key(funcName)} account_entire为空，返回unknown')
            return "unknown"
        try:
            account_data = json.loads(account_entire)
            self.logger.debug(f'{self._log_key(funcName)} 成功解析account_entire，包含字段: {list(account_data.keys())}')
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f'{self._log_key(funcName)} 解析account_entire失败: {str(e)}，返回unknown')
            return "unknown"
        customer_type = account_data.get("customerType", "")
        scope = account_data.get("scope", "")
        if customer_type == "merchant" or scope == "merchant":
            self.logger.info(f'{self._log_key(funcName)} 检测到商户账户 (customerType={customer_type}, scope={scope})，返回merchant')
            return "merchant"
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
        account_profile = account_data.get("accountProfile", "")
        if account_profile in ["L0", "L1"]:
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accountProfile={account_profile})，返回wallet')
            return "wallet"
        if account_profile in [
            "ADA", "DA", 
            "Current MA", "Savings MA",
            "Joint Current MA", "Joint Savings MA"
        ]:
            self.logger.info(f'{self._log_key(funcName)} 检测到银行账户 (accountProfile={account_profile})，返回bank')
            return "bank"
        iban = account_iban or account_data.get("IBAN") or account_data.get("iban", "")
        if iban:
            iban_upper = iban.upper()
            if "TMFB" in iban_upper:
                self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (IBAN包含TMFB: {iban})，返回wallet')
                return "wallet"
            if "JCMA" in iban_upper:
                if "businessDetails" in account_data:
                    self.logger.info(f'{self._log_key(funcName)} 检测到商户账户 (IBAN包含JCMA且有businessDetails: {iban})，返回merchant')
                    return "merchant"
                else:
                    self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (IBAN包含JCMA但无businessDetails: {iban})，返回wallet')
                    return "wallet"  # JazzCash 个人账户
        accno = account_accno or account_data.get("accno", "")
        if accno and len(str(accno)) == 8 and str(accno).isdigit():
            self.logger.info(f'{self._log_key(funcName)} 检测到钱包账户 (accno为8位数字: {accno})，返回wallet')
            return "wallet"
        if account_name and account_name not in [
            "Easypaisa Wallet", 
            "JazzCash Wallet", 
            "JazzCash Account",
            ""
        ]:
            self.logger.info(f'{self._log_key(funcName)} 检测到银行账户 (accountName={account_name})，返回bank')
            return "bank"
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
                await self._record_login_failed_attempt(phone)
                raise NewApiError(ErrorCode.LoginAttemps, 'Payment password verification failed')
            else:
                await self._clear_login_failed_attempts(phone)
        except NewApiError:
            raise  # 重新抛出 NewApiError
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
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
            if response is None:
                self.logger.error(f'{self._log_key(funcName)} 响应为None，无法记录日志')
                return
            self.logger.info(f"{self._log_key(funcName)} 请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f'{self._log_key(funcName)} 请求URL: {response.url}')
            self.logger.info(f'{self._log_key(funcName)} 请求方法: {response.request.method}')
            self.logger.info(f'{self._log_key(funcName)} 状态码: {response.status_code}')
            self.logger.info(f'{self._log_key(funcName)} 状态码: {response.status_code}')
            reqHeaders = ""
            for key, value in dict(response.request.headers).items():
                reqHeaders = f'{key}: {value}, '
            self.logger.info(f'{self._log_key(funcName)} 请求头: {reqHeaders}')
            rspHeaders = ""
            for key, value in dict(response.headers).items():
                rspHeaders = f'{key}: {value}, '
            self.logger.info(f'{self._log_key(funcName)} 响应头: {rspHeaders}')
            self.logger.info(f'{self._log_key(funcName)} HTTP状态码: {response.status_code}')
            try:
                json_data = response.json()
                self.logger.info(f'{self._log_key(funcName)} 响应体: {json.dumps(json_data, ensure_ascii=False, indent=2)}')
            except:
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
            if hasattr(response, 'encoding'):
                self.logger.info(f'{self._log_key(funcName)} 响应编码: {response.encoding}')
            if hasattr(response, 'elapsed'):
                self.logger.info(f'{self._log_key(funcName)} 请求耗时: {response.elapsed.total_seconds():.3f} 秒')
            if hasattr(response, 'history') and response.history:
                redicHis = ""
                for hist in response.history:
                    redicHis = f'{hist.status_code} -> {hist.url}, '
                self.logger.info(f'{self._log_key(funcName)} 重定向历史: {redicHis}')
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}', exc_info=True)
    async def _select_proxy_ip(self, bankname):
        """
        选择代理IP，保持一致性
        参考历史代理实现的_select_proxy_ip方法
        """
        funcName = '选择代理IP'
        try:            
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
        try:
            redis_key = self.PROXIES_IP_KEY.format(bankname=bankname)
            indian_socks_ip = await self.redis.get(redis_key)
            if not indian_socks_ip:
                self.logger.error(f'{self._log_key(funcName)} Redis中无{redis_key}代理IP配置')
                return False
            if isinstance(indian_socks_ip, bytes):
                indian_socks_ip = indian_socks_ip.decode('utf-8')
            proxy_list = indian_socks_ip.split(',')
            proxy_list = [item.strip() for item in proxy_list if item.strip()]
            if not proxy_list:
                self.logger.error(f'{self._log_key(funcName)} {redis_key}代理IP列表为空')
                return False
            import random
            selected_proxy = random.choice(proxy_list)
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
            socks_ip = session_data.get('socks_ip', '')
            if not socks_ip:
                return None
            proxy_url = f'socks5://{socks_ip}'
            proxy_dict = {
                'http': proxy_url,
                'https': proxy_url
            }
            self.logger.info(f'{self._log_key(funcName)} 获取请求代理配置: {proxy_url}')
            return proxy_dict
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}')
            return None
    async def _get_payment_interface_lock(self, payment_id, operation_name):
        """获取基于payment_id的接口锁"""
        funcName = '获取基于payment_id的接口锁'
        try:
            lock_key = self.PAYMENT_INTERFACE_LOCK_KEY.format(payment_id=payment_id, operation_name=operation_name)
            lock_value = f'{int(time.time())}_{random.randint(1000, 9999)}'
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
                ttl_residue = await self.redis.ttl(lock_id)
                if ttl_residue == -2:
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, key已经不存在')
                    return True
                if ttl_residue == -1:
                    await self.redis.delete(lock_id)
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, key没有设置TTL')
                    return True
                if ttl_residue == 0:
                    self.logger.info(f'{self._log_key(funcName)} 释放接口锁成功: {lock_id}, key已经过期')
                    return True
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

    async def _force_terminal_needs_relogin(
        self,
        redis_key: str,
        session_data: dict,
        reason: str,
        error_code: str,
        message: str | None = None,
    ) -> dict:
        """spec §3.1.2：所有 needsRelogin 必须经过这里。

        Why: 统一可观测性（grep _force_terminal_needs_relogin 看所有终止点）+
        保留 5 秒窗口让 APP 拉 last_error 后再删 key。
        """
        funcName = '_force_terminal_needs_relogin'
        current = session_data.get('status', LoginStatus.PRE_LOGIN_CREATED)
        if LoginStatus.NEEDS_RELOGIN not in STATUS_TRANSITIONS.get(current, []):
            msg = f'INVALID_TRANSITION: {current} -> NEEDS_RELOGIN not allowed'
            self.logger.error(f'{self._log_key(funcName)} {msg}')
            raise NewApiError('INVALID_TRANSITION', msg)
        self.logger.warning(
            f'{self._log_key(funcName)} 状态推进: {current} → {LoginStatus.NEEDS_RELOGIN}, reason={reason}'
        )
        session_data['status'] = LoginStatus.NEEDS_RELOGIN
        session_data.setdefault('status_history', []).append(LoginStatus.NEEDS_RELOGIN)
        session_data['last_error'] = {
            'code': error_code,
            'message': message,
            'reason': reason,
            'timestamp': int(time.time()),
        }
        session_data['last_status_change'] = int(time.time())
        await self.redis.setex(redis_key, 5, json.dumps(session_data))
        await self.redis.expire(redis_key, 5)
        return {
            'status': 'error',
            'message': message or '账户需要重新登录',
            'data': {
                'code': error_code,
                'phase': LoginStatus.NEEDS_RELOGIN,
            },
        }

    # spec §3.3.1：残留状态到下一步的映射
    NEXT_STEP_MAP = {
        LoginStatus.PRE_LOGIN_CREATED:          'send_otp',
        LoginStatus.OTP_SENT:                   'verify_otp',
        LoginStatus.OTP_VERIFIED:               'upload_fingerprint',
        LoginStatus.FINGERPRINT_VERIFIED:       'second_login',
        LoginStatus.AWAITING_PIN_CHANGE:        'change_pin',
        LoginStatus.ACCOUNT_SELECTION_REQUIRED: 'select_accts',
    }

    async def _build_resumed_session_response(self, redis_key: str, session_data: dict) -> dict:
        """spec §3.3.1：复用残留 session，引导 APP 接续上次进度。"""
        funcName = '_build_resumed_session_response'
        status = session_data.get('status', LoginStatus.PRE_LOGIN_CREATED)
        next_step = self.NEXT_STEP_MAP.get(status, 'send_otp')
        ttl_remaining = await self.redis.ttl(redis_key)
        data = {
            'resumed': True,
            'phase': status,
            'next_step': next_step,
            'expires_in': max(0, int(ttl_remaining or 0)),
            'id': session_data.get('id'),
        }
        # ACCOUNT_SELECTION_REQUIRED 时附上 accounts 让 APP 无需再调 query_accts
        if status == LoginStatus.ACCOUNT_SELECTION_REQUIRED:
            raw = session_data.get('account_entire')
            if raw:
                try:
                    accounts = json.loads(raw) if isinstance(raw, str) else raw
                    data['accounts'] = accounts
                except (json.JSONDecodeError, TypeError):
                    self.logger.warning(f'{self._log_key(funcName)} 解析 account_entire 失败: {raw}')
        self.logger.info(f'{self._log_key(funcName)} 复用 session: phase={status} next_step={next_step} ttl={ttl_remaining}')
        return {
            'status': 'success',
            'message': '复用残留 session',
            'data': data,
        }

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
                response = self.session.post(url, headers=headers, data=data, files=files, proxies=proxies, verify=False, allow_redirects=True, timeout=(30, 30))
            if response is not None:
                self.logger.info(f'请求 {method} {url}, data:{data}, response: {response}, response.text: {response.text}')
            return response
        except Exception as e:
            self.logger.error(f'网络请求错误： 错误详情:{e}')
            return None
    def retry_make_request(self, *args, **kwargs):
        """简化的retry_make_request - 保持与历史代理实现一致"""
        res = self.make_request(*args, **kwargs)
        if res is not None and (200 <= res.status_code < 300):
            return res
        self.logger.info(f'make_request() second try, args: {args}, kwargs: {kwargs}')
        res = self.make_request(*args, **kwargs)
        if res is None or not (200 <= res.status_code < 300):
            self.logger.warning(f'make_request() 两次尝试均失败, args: {str(args)}, kwargs: {str(kwargs)}')
        return res
    async def pre_login_http(self, data):
        """v1.9 重写：见 spec §3.3。"""
        funcName = 'pre_login_http'
        lockName = 'pre_login'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            self.logger.info(f'=== code_ver: {CODE_VER} ===')
            self.logger.info(f'{self._log_key(funcName)} 请求参数: {data}')
            if data.get('step', 'unknown') != 'complete_login':
                raise NewApiError(ErrorCode.Unsupported, f"Unsupported step: {data.get('step', 'unknown')}")
            required = ['bankname', 'phone', 'password', 'pin', 'name']
            missing = [f for f in required if not data.get(f)]
            if missing:
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing)}")
            bankname = data['bankname']
            original_phone = data['phone']
            phone = self._format_phone_number(original_phone)
            password = data['password']
            pin = data['pin']
            name = data['name']
            if not self._validate_phone_number(phone):
                raise NewApiError(ErrorCode.InvalidPhone, f'Invalid phone number format: {phone}')
            if await self._check_login_failed_attempts(phone):
                raise NewApiError(ErrorCode.LoginAttemps, 'Try too many times, try again after two hours.')
            await self._verify_payment_password_bcrypt(password, self.handler.current_user.hash_trade, phone)
            user_id = self.handler.current_user.id
            is_new_user = data.get('is_new_user', True)
            payment_id = data.get('payment_id')
            bound_payment = None
            if payment_id and await self.redis.get(self._login_lock_payment_key(payment_id)):
                raise NewApiError(ErrorCode.Logined, 'Account is in login process, please try again later')
            if phone and await self.redis.get(self._login_lock_phone_key(phone)):
                raise NewApiError(ErrorCode.Logined, 'Account is in login process, please try again later')
            if payment_id:
                bank_type_id = await self._get_bank_type_id(bankname)
                if not bank_type_id:
                    raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Bank type not found for: {bankname}')
                with self.handler.db_orm.sessionmaker() as session:
                    existing_payment = session.query(Payment).filter(
                        Payment.id == payment_id, Payment.bank_type_id == bank_type_id
                    ).first()
                    if not existing_payment:
                        raise NewApiError(ErrorCode.InvalidBankOrPayment, f'Payment record not found: {payment_id}')
                    if existing_payment.phone != phone:
                        raise NewApiError(ErrorCode.PaymentPhoneMismatch, f'Phone mismatch payment {payment_id}')
                    if int(getattr(existing_payment, 'user_id', 0) or 0) != int(user_id):
                        raise NewApiError('10402', 'UPI already occupied by another user')
                    bound_payment = {
                        'id': existing_payment.id,
                        'phone': existing_payment.phone,
                        'user_id': existing_payment.user_id,
                        'wallet_status': getattr(existing_payment, 'wallet_status', 0),
                        'fingerprint_path': getattr(existing_payment, 'fingerprint_path', None),
                    }
            else:
                existing = await self._check_payment(bankname, phone, user_id)
                is_new_user = existing is None
                if existing:
                    if existing.get('user_id') == user_id:
                        payment_id = existing.get('id')
                        bound_payment = existing
                    else:
                        raise NewApiError('10402', 'UPI already occupied by another user')
                else:
                    payment_id = phone
            lock_result = await self._get_payment_interface_lock(payment_id, lockName)
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            # spec §3.3 ⑦：已 ACTIVE 直接返回 ready（修复 533264）
            if bound_payment and int(bound_payment.get('wallet_status', 0) or 0) == 1:
                self.logger.info(f'{self._log_key(funcName)} 已 active，返回 ready: payment_id={payment_id}')
                return {
                    'status': 'success',
                    'message': '账号已激活',
                    'data': {
                        'id': payment_id,
                        'next_step': 'ready',
                        'phase': LoginStatus.ACTIVE_SUCCESSFUL,
                    },
                }
            # spec §3.3 ⑦.1：残留 session 复用（修复 Blocker 4）
            existing_session = await self._get_session_data(redis_key)
            if existing_session:
                cur_status = existing_session.get('status')
                if cur_status in (
                    LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED,
                    LoginStatus.FINGERPRINT_VERIFIED, LoginStatus.AWAITING_PIN_CHANGE,
                    LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                ):
                    # 状态合理性：phone 必须匹配
                    if existing_session.get('phone') == phone:
                        return await self._build_resumed_session_response(redis_key, existing_session)
                    self.logger.warning(f'{self._log_key(funcName)} 残留 session phone 不匹配，删除后重建')
                    await self.redis.delete(redis_key)
                elif cur_status == LoginStatus.NEEDS_RELOGIN:
                    # 终态，删 key 重新走
                    await self.redis.delete(redis_key)
                # PRE_LOGIN_CREATED / ACTIVE_SUCCESSFUL 走下面正常分支
            # spec §3.3 ⑧：创建新 session
            proxy_ip = await self._select_proxy_ip(bankname)
            expire_second = self.expire_time_login_pending
            session_data = {
                'id': payment_id,
                'partner_id': user_id,
                'phone': phone,
                'original_phone': original_phone,
                'status': LoginStatus.PRE_LOGIN_CREATED,
                'status_history': [LoginStatus.PRE_LOGIN_CREATED],
                'time': int(time.time()),
                'try_count': 0,
                'socks_ip': proxy_ip or '',
                'to': self.name,
                'qr_channel': data.get('channel', 1001),
                'pinCode': pin,
                'bankname': bankname,
                'password': password,
                'account': data.get('account', ''),
                'is_new_user': is_new_user,
                'name': name,
                'login_time': int(time.time()),
                'last_status_change': int(time.time()),
                'last_request_time': int(time.time()),
                'expires_at': int(time.time()) + expire_second,
                'sendOTPTime': 0,
                'selected_upi': '',
                'upi_list': [],
                'fallback_from_urm90040': False,
            }
            await self._persist_session_data(redis_key, session_data)
            # spec §3.3 ⑨：调云机 isAccountRegistered
            is_registered = await self._is_account_registered(phone)
            if not is_registered:
                # 首次上号：仅 session 初始化，不调 loginStep1
                self.logger.info(f'{self._log_key(funcName)} 首次上号 next_step=send_otp')
                return {
                    'status': 'success',
                    'message': '成功',
                    'data': {
                        'id': payment_id,
                        'redis_key': redis_key,
                        'expires_in': expire_second,
                        'is_new_user': True,
                        'bank_type': self.LOGIN_TYPE,
                        'next_step': 'send_otp',
                    },
                }
            # spec §3.3 ⑩：二次上号续推（详细路径在 Task 8）
            return await self._pre_login_second_time_chain(redis_key, session_data, bound_payment)
        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
            raise NewApiError(ErrorCode.LoginAttemps, str(e))
        finally:
            if payment_lock_id and payment_lock_value:
                await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)

    async def _pre_login_second_time_chain(self, redis_key, session_data, bound_payment):
        """spec §3.3 ⑩：二次上号内部续推 upload_data + verifyFingerprint + secondLogin + queryAccountList。"""
        funcName = '_pre_login_second_time_chain'
        fingerprint_path = (bound_payment or {}).get('fingerprint_path')
        # spec §3.3 边界：本地 ZIP 丢失 → 直接 needsRelogin
        if not fingerprint_path or not os.path.exists(fingerprint_path):
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason=f'Local fingerprint ZIP missing: {fingerprint_path}',
                error_code='EP_FP_FILE_MISSING',
                message='本地指纹文件缺失，请联系运维介入',
            )
        # a. upload_data 推 ZIP
        pushed = await self._call_upload_data(session_data, fingerprint_path)
        if not pushed:
            session_data['last_error'] = {'code': 'FP_UPSTREAM_REJECTED', 'reason': 'upload_data failed'}
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': 'upload_data 失败，请重试 pre_login',
                'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'pre_login'},
            }
        # b. verifyFingerprint
        fp_result = await self._call_verify_fingerprint(session_data)
        if fp_result.get('outcome') != 'success':
            self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                           LoginStatus.OTP_VERIFIED, funcName)
            session_data['status'] = LoginStatus.OTP_VERIFIED
            session_data['status_history'].append(LoginStatus.OTP_VERIFIED)
            session_data['last_error'] = {'code': 'FP_UPSTREAM_REJECTED',
                                          'reason': fp_result.get('message', '')}
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '指纹验证被拒，请重新上传',
                'data': {'code': 'FP_UPSTREAM_REJECTED', 'next_step': 'upload_fingerprint',
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        # c. secondLogin
        sl_result = await self._call_second_login(session_data)
        outcome = sl_result.get('outcome')
        if outcome == 'urm90040':
            return await self._urm90040_fallback(redis_key, session_data, sl_result.get('message', ''))
        if outcome == 'needs_pin_change':
            self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                           LoginStatus.AWAITING_PIN_CHANGE, funcName)
            session_data['status'] = LoginStatus.AWAITING_PIN_CHANGE
            session_data['status_history'].append(LoginStatus.AWAITING_PIN_CHANGE)
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': '需要修改 PIN',
                'data': {'code': 'SL_NEEDS_PIN_CHANGE', 'next_step': 'change_pin',
                         'phase': LoginStatus.AWAITING_PIN_CHANGE},
            }
        if outcome != 'success':
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason=f'secondLogin outcome={outcome} msg={sl_result.get("message", "")}',
                error_code='SL_NEEDS_RELOGIN' if outcome == 'session_expired' else 'SL_UPSTREAM_ERROR',
            )
        # d. queryAccountList
        qal_result = await self._call_query_account_list(session_data)
        if qal_result.get('outcome') != 'success':
            self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                           LoginStatus.FINGERPRINT_VERIFIED, funcName)
            session_data['status'] = LoginStatus.FINGERPRINT_VERIFIED
            session_data['status_history'].append(LoginStatus.FINGERPRINT_VERIFIED)
            await self._persist_session_data(redis_key, session_data)
            return {
                'status': 'error',
                'message': 'queryAccountList 失败',
                'data': {'code': 'SL_UPSTREAM_ERROR', 'next_step': 'second_login',
                         'phase': LoginStatus.FINGERPRINT_VERIFIED},
            }
        # 全成功：直接跳到 ACCOUNT_SELECTION_REQUIRED
        self._assert_status_transition(session_data, LoginStatus.PRE_LOGIN_CREATED,
                                       LoginStatus.ACCOUNT_SELECTION_REQUIRED, funcName)
        session_data['status'] = LoginStatus.ACCOUNT_SELECTION_REQUIRED
        session_data['status_history'].append(LoginStatus.ACCOUNT_SELECTION_REQUIRED)
        session_data['account_entire'] = qal_result.get('accounts_json')
        await self._persist_session_data(redis_key, session_data)
        self.logger.info(f'{self._log_key(funcName)} 二次上号续推完成，状态 → ACCOUNT_SELECTION_REQUIRED')
        return {
            'status': 'success',
            'message': '二次上号续推成功',
            'data': {
                'id': session_data['id'],
                'next_step': 'second_login',
                'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
            },
        }

    async def _call_upload_data(self, session_data, fingerprint_path):
        """Task 11 will implement upload_data action call. Placeholder returns False for now."""
        self.logger.warning('STUB: _call_upload_data not implemented')
        return False

    async def _call_verify_fingerprint(self, session_data):
        """Task 12 placeholder."""
        return {'outcome': 'rejected', 'message': 'STUB'}

    async def _call_second_login(self, session_data):
        """Task 13 placeholder."""
        return {'outcome': 'session_expired', 'message': 'STUB'}

    async def _call_query_account_list(self, session_data):
        """Task 14 placeholder."""
        return {'outcome': 'rejected'}

    async def _urm90040_fallback(self, redis_key, session_data, msg):
        """Task 15 placeholder."""
        return await self._force_terminal_needs_relogin(
            redis_key=redis_key, session_data=session_data,
            reason='URM90040 fallback stub', error_code='SL_NEEDS_RELOGIN',
        )

    async def send_otp_http(self, data):
        """v1.9 重写：纯 loginStep1 + 20s 节流。spec §3.3.2。"""
        funcName = 'send_otp_http'
        lockName = 'send_otp'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            required = ['bankname', 'payment_id']
            missing = [f for f in required if f not in data]
            if missing:
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing)}")
            bankname = data['bankname']
            payment_id = data['payment_id']
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            lock_result = await self._get_payment_interface_lock(payment_id, lockName)
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')
            session_data = await self._get_session_data(redis_key)
            if not session_data:
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')
            required_fields = ['phone', 'id', 'bankname']
            missing_fields = [f for f in required_fields if not session_data.get(f)]
            if missing_fields:
                raise NewApiError(ErrorCode.SessionNotExist, f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
            current_status = session_data.get('status')
            # 节流：sendOTPTime 距今 < 20s 则不调云机
            last_send = int(session_data.get('sendOTPTime') or 0)
            now_ts = int(time.time())
            if last_send and (now_ts - last_send) < self.RESEND_COOLDOWN_SECONDS:
                wait_left = self.RESEND_COOLDOWN_SECONDS - (now_ts - last_send)
                raise NewApiError(
                    ErrorCode.PaymentLocked,
                    f'Please wait {wait_left}s before requesting a new OTP',
                )
            # 允许 PRE_LOGIN_CREATED → OTP_SENT 或 OTP_SENT → OTP_SENT(resend)
            if current_status not in (LoginStatus.PRE_LOGIN_CREATED, LoginStatus.OTP_SENT):
                raise NewApiError(
                    'INVALID_TRANSITION',
                    f'send_otp expected PRE_LOGIN_CREATED/OTP_SENT, got {current_status}'
                )
            # 调云机 loginStep1
            api_result = await self._send_otp(session_data)
            is_resend = current_status == LoginStatus.OTP_SENT
            await self._update_session_status(
                redis_key, session_data, LoginStatus.OTP_SENT,
                {
                    'sendOTPTime': now_ts,
                    'resend_count': int(session_data.get('resend_count', 0)) + (1 if is_resend else 0),
                }
            )
            return {
                'status': 'success',
                'message': 'OTP 已发送',
                'data': {
                    'next_step': 'verify_otp',
                    'phase': LoginStatus.OTP_SENT,
                    'expires_in': 120,
                },
            }
        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
            raise NewApiError(ErrorCode.SendOTPFail, f'OTP Sending failed: {e}')
        finally:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)

    async def verify_otp_http(self, data):
        """v1.9 重写：纯 loginStep2(should_verify_fingerprint=false) + 区分首次/fallback。spec §3.4。"""
        funcName = 'verify_otp_http'
        lockName = 'verify_otp'
        payment_lock_id = None
        payment_lock_value = None
        self.login_data = data
        try:
            required = ['bankname', 'payment_id', 'otp']
            missing = [f for f in required if f not in data]
            if missing:
                raise NewApiError(ErrorCode.MissingParams, f"Missing: {', '.join(missing)}")
            bankname = data['bankname']
            payment_id = self._normalize_payment_id(data['payment_id'])
            otp = data['otp'].strip()
            if not otp:
                raise NewApiError(ErrorCode.MissingParams, 'OTP code cannot be empty')
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            lock_result = await self._get_payment_interface_lock(payment_id, lockName)
            payment_lock_id = lock_result.get('lock_id')
            payment_lock_value = lock_result.get('lock_value')
            session_data = await self._get_session_data(redis_key)
            if not session_data:
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist')
            self._assert_status_transition(
                session_data, LoginStatus.OTP_SENT, LoginStatus.OTP_VERIFIED, funcName
            )
            # 调云机 loginStep2(should_verify_fingerprint=false)
            api_result = await self._verify_otp(session_data, otp)
            session_data['serv_gen_id'] = api_result.get('data', {}).get('requestId')
            name = session_data.get('name', '')
            real_payment_id = await self._save_payment(session_data, name=name)
            if not real_payment_id:
                raise NewApiError(ErrorCode.DBWriteFail, 'Database write failed, please retry')
            old_payment_id = self._normalize_payment_id(session_data.get('id'))
            real_payment_id_text = self._normalize_payment_id(real_payment_id)
            if old_payment_id != real_payment_id_text:
                await self.redis.delete(redis_key)
                redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=real_payment_id_text)
            session_phone = session_data.get('phone')
            await self.redis.setex(
                self._login_lock_payment_key(real_payment_id),
                self.lock_time_login_duplicate_avoid, 1
            )
            await self.redis.setex(
                self._login_lock_phone_key(session_phone),
                self.lock_time_login_duplicate_avoid, 1
            )
            session_data.update({
                'id': real_payment_id,
                'real_payment_id': real_payment_id,
                'previous_payment_id': old_payment_id,
                'selected_upi': session_phone,
                'upi_list': [session_phone],
                'completion_time': int(time.time()),
                'last_error': None,
            })
            await self._update_session_status(redis_key, session_data, LoginStatus.OTP_VERIFIED)
            # 区分首次 / fallback
            if session_data.get('fallback_from_urm90040'):
                return await self._verify_otp_fallback_chain(redis_key, session_data)
            # 首次：返回 next_phase='fingerprintUploadRequired'，APP 切到指纹采集 UI
            return {
                'status': 'success',
                'message': 'OTP 验证成功',
                'data': {
                    'next_phase': 'fingerprintUploadRequired',
                    'payment_id': real_payment_id,
                    'previous_payment_id': old_payment_id,
                    'phase': LoginStatus.OTP_VERIFIED,
                },
            }
        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {e}', exc_info=True)
            raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification failed: {e}')
        finally:
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)

    async def _verify_otp_fallback_chain(self, redis_key, session_data):
        """spec §3.4 fallback 路径：upload_data + verifyFingerprint + secondLogin + queryAccountList。"""
        funcName = '_verify_otp_fallback_chain'
        payment_id = session_data.get('id')
        payment = await self._query_payment(payment_id) if payment_id else None
        fingerprint_path = payment.get('fingerprint_path') if payment else None
        if not fingerprint_path or not os.path.exists(fingerprint_path):
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason='fallback path: local fingerprint missing',
                error_code='EP_FP_FILE_MISSING',
            )
        pushed = await self._call_upload_data(session_data, fingerprint_path)
        if not pushed:
            return {
                'status': 'error',
                'message': '上传指纹失败',
                'data': {'next_phase': 'fingerprintUploadRequired', 'code': 'FP_UPSTREAM_REJECTED',
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        fp = await self._call_verify_fingerprint(session_data)
        if fp.get('outcome') != 'success':
            return {
                'status': 'error',
                'message': '指纹验证被拒',
                'data': {'next_phase': 'fingerprintUploadRequired', 'code': 'FP_UPSTREAM_REJECTED',
                         'phase': LoginStatus.OTP_VERIFIED},
            }
        sl = await self._call_second_login(session_data)
        if sl.get('outcome') == 'urm90040':
            # fallback 路径再 URM90040 → 不再 fallback，直接 needsRelogin
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason='fallback secondLogin URM90040 again', error_code='SL_NEEDS_RELOGIN',
            )
        if sl.get('outcome') == 'needs_pin_change':
            self._assert_status_transition(session_data, LoginStatus.OTP_VERIFIED,
                                           LoginStatus.AWAITING_PIN_CHANGE, funcName)
            await self._update_session_status(redis_key, session_data, LoginStatus.AWAITING_PIN_CHANGE,
                                              {'last_error': {'code': 'SL_NEEDS_PIN_CHANGE'}})
            return {
                'status': 'error',
                'message': '需要修改 PIN',
                'data': {'code': 'SL_NEEDS_PIN_CHANGE', 'next_step': 'change_pin'},
            }
        if sl.get('outcome') != 'success':
            return await self._force_terminal_needs_relogin(
                redis_key=redis_key, session_data=session_data,
                reason=f'fallback secondLogin {sl.get("outcome")}',
                error_code='SL_NEEDS_RELOGIN' if sl.get('outcome') == 'session_expired' else 'SL_UPSTREAM_ERROR',
            )
        qal = await self._call_query_account_list(session_data)
        if qal.get('outcome') != 'success':
            await self._update_session_status(redis_key, session_data, LoginStatus.FINGERPRINT_VERIFIED,
                                              {'last_error': {'code': 'SL_UPSTREAM_ERROR'}})
            return {
                'status': 'error',
                'message': 'queryAccountList 失败',
                'data': {'code': 'SL_UPSTREAM_ERROR', 'next_step': 'second_login',
                         'phase': LoginStatus.FINGERPRINT_VERIFIED},
            }
        self._assert_status_transition(session_data, LoginStatus.OTP_VERIFIED,
                                       LoginStatus.ACCOUNT_SELECTION_REQUIRED, funcName)
        await self._update_session_status(redis_key, session_data, LoginStatus.ACCOUNT_SELECTION_REQUIRED,
                                          {'account_entire': qal.get('accounts_json'),
                                           'last_error': None})
        return {
            'status': 'success',
            'message': 'fallback 续推成功',
            'data': {
                'next_phase': 'fingerprintUploaded',
                'next_step': 'second_login',
                'phase': LoginStatus.ACCOUNT_SELECTION_REQUIRED,
            },
        }

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
                raise NewApiError(ErrorCode.SessionNotExist, 'Session data does not exist, please call pre_login_http first')
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
            message = second_login_result.get('message', '')
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
            if '501' in str(message) or 'AccountInvalid' in str(message):
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
            required_fields = ['bankname', 'payment_id', 'pin']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            pin = data['pin']
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error
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
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            if not file:
                raise NewApiError(ErrorCode.MissingParams, 'file cannot be empty')
            if file["content_type"] not in ["application/zip", "application/x-zip-compressed", "multipart/x-zip"]:
                raise NewApiError(ErrorCode.MissingParams, 'file ext should be .zip')
            if len(file["body"]) > 1024 * 1024 * 16:
                raise NewApiError(ErrorCode.MissingParams, 'file size can not over 16MB')
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                resolved_payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(resolved_payment_id, lockName)
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f'{self._log_key(funcName)} 接口锁限制: {lock_error.message}')
                raise lock_error
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
            session_fg_times = session_fg_times + 1
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
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
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
            required_fields = ['bankname', 'payment_id', 'accno']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
            bankname = data['bankname']
            requested_payment_id = self._normalize_payment_id(data['payment_id'])
            accno = data['accno']
            try:
                session_ctx = await self._resolve_session_context(bankname, requested_payment_id)
                payment_id = session_ctx.get('resolved_payment_id') or requested_payment_id
                lock_result = await self._get_payment_interface_lock(payment_id, lockName)
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
            account_type_value = ACCOUNT_TYPE_UNKNOWN
            phone = session_data.get('phone', '')
            payment_id = session_data.get('id', '')
            try:
                self.logger.info(f'[Phone: {phone}] [PaymentID: {payment_id}] 开始检测账户类型...')
                selected_account = next((acc for acc in accounts if acc['accno'] == accno), None)
                if selected_account:
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
            await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
            self.logger.info(f'{self._log_key(funcName)} 释放payment锁: id={payment_lock_id}, value={payment_lock_value}')
    async def select_acct_http(self, data):
        return await self.select_accts_http(data)
    async def payment_status_http(self, data):
        funcName = 'payment_status_http'
        self.login_data = data
        try:
            required_fields = ['bankname', 'payment_ids']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f'{self._log_key(funcName)} 参数验证失败: 缺少必要参数 {required_fields}')
                self.logger.error(f'{self._log_key(funcName)} 实际收到的参数: {list(data.keys())}')
                raise NewApiError(ErrorCode.MissingParams, f"Missing required parameters: {', '.join(missing_fields)}")
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
        request_data = self._build_send_otp_request(session_data)
        if ISTEST:
            status = 100
            status_desc = ''
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
            )
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
            )
            self._log_response(funcName, response)
            if not response:
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification request failed')
            status_code = response.status_code
            if status_code != 200:
                self.logger.error(f'{self._log_key(funcName)} HTTP状态码错误: {status_code}')
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification request failed')
            self.logger.info(f'{self._log_key(funcName)} HTTP请求成功!')
            response_data = self._decode_indus_response(funcName, response.text)
            if not response_data:
                self.logger.error(f'{self._log_key(funcName)} 解码失败!')
                raise NewApiError(ErrorCode.VerifyOTPFail, f'OTP verification decode failed')
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
            login_session_keys = self._current_login_session_keys(payment_id, resolved_phone)
            deleted_sessions = await self.redis.delete(*login_session_keys)
            await self.redis.hdel('hash_easypaisa', payment_id)
            await self.redis.zrem('set_easypaisa', payment_id)
            self.logger.info(
                f'{self._log_key(funcName)} [2/4] 当前会话队列清理完成: '
                f'phone={resolved_phone}, deleted={deleted_sessions}'
            )
            pre_login_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            deleted_session = await self.redis.delete(pre_login_key)
            self.logger.info(f'{self._log_key(funcName)} [3/4] 清理会话完成: pre_login={pre_login_key}, deleted={deleted_session}')
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
        request_data = self._build_verify_fingerprint_request(session_data)
        if ISTEST:
            status = 200
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
            )
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
        request_data = self._build_change_pin_request(session_data, pin)
        if ISTEST:
            status = 200
            status_desc = ''
        else:
            response = self.retry_make_request(
                method='POST',
                url=url,
                data=request_data,
            )
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
            )
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
            otp_result = await self._send_otp(session_data)
            otp_status = otp_result.get('outcome') or otp_result.get('status') if otp_result else ''
            if otp_status != 'success':
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
            new_session = {
                'phone': phone,
                'payment_id': payment_id,
                'id': payment_id,
                'bankname': session_data.get('bankname', ''),
                'pinCode': session_data.get('pinCode', ''),
                'partner_id': session_data.get('partner_id', ''),
                'socks_ip': session_data.get('socks_ip', ''),
                'name': session_data.get('name', ''),
                'status': LoginStatus.OTP_SENT,
                'fallback_from': 'secondLogin',
                'fallback_reason': reason,
            }
            await self._persist_session_data(redis_key, new_session)
            await self.redis.expire(redis_key, 300)
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
    async def _query_accts(self, phone):
        funcName = '账户查询'
        url = self.API_ENDPOINTS['base_url']
        self.logger.info(f'{self._log_key(funcName)} 请求URL: {url}')
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
            )
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
    def _build_is_account_registered_request(self, phone):
        funcName = '构建云机注册检查'
        request_msg = {
            "account_id": phone,
        }
        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}')
        return self._encode_indus_request(funcName, 'isAccountRegistered', request_msg)
    def _build_send_otp_request(self, session_data):
        funcName = '构建OTP发送'
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
        phone = session_data.get('phone')
        self.logger.info(f'{self._log_key(funcName)} 参数 phone: {phone}, otp: {otp}')
        request_msg = {
            "account_id": phone,
            "otpcode": otp
        }
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
            outer["id"] = str(uuid.uuid4())
            outer["action"] = action
            outer["payload"] = payload
            outer_json = json.dumps(outer)
            outer_base64 = base64.b64encode(outer_json.encode('utf-8')).decode('utf-8')
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
                if 'resp' in response_data:
                    decoded_resp = self.decode_message(response_data['resp'])
                    result = json.loads(decoded_resp)
                else:
                    result = response_data
            elif isinstance(response_data, str):
                result = json.loads(response_data)
            self.logger.info(f'{self._log_key(funcName)} 解码后: {result}')
            return result
        except Exception as e:
            self.logger.error(f'{self._log_key(funcName)} 异常: {str(e)}, raw data: {response_data}', exc_info=True)
            return response_data if isinstance(response_data, dict) else {}
    async def _get_bank_type_id(self, bankname):
        funcName = '获取银行类型ID'
        try:
            normalized_bankname = self.BANK_NAME_MAPPING.get(bankname.lower(), bankname.upper())
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
            bank_type_id = await self._get_bank_type_id(bankname)
            if not bank_type_id:
                return None
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
    async def _save_payment(self, session_data, name=None, pin=None, fingerprint_path=None):
        funcName = '保存payment数据到数据库'
        try:
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
            bank_type_id = await self._get_bank_type_id(bankname)
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
            }
            if name:
                payment_data['name'] = name
                self.logger.info(f'{self._log_key(funcName)} 设置 name: {name}')
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
