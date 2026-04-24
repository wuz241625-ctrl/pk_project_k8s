import json
import time
import asyncio
import hashlib
import base64
import random
import string
import secrets
import simplejson
import bcrypt
from functools import wraps
from Cryptodome.Cipher import AES
import traceback
import logging
from typing import Dict, Any, Optional

# 错误处理相关导入
from application.lakshmi_api.services.error_manager import ErrorManager
from application.lakshmi_api.exceptions.api_error import NewApiError
from application.lakshmi_api.models.payment import Payment


# Redis状态常量
class LoginStatus:
    PRE_LOGIN = "preLogin"                  # 预登录状态
    SEND_OTP = "sendOtp"                    # 发送OTP验证码
    VERIFY_OTP = "verifyOtp"                # 验证OTP和MPIN
    FACE_VERIFY = "faceVerify"              # 人脸验证
    SMS_VERIFY = "smsVerify"                # 短信验证
    LOGIN_SUCCESSFUL = "loginSuccessful"    # 登录成功

# 状态转换规则定义
GCASH_STATUS_TRANSITIONS = {
    LoginStatus.PRE_LOGIN: [LoginStatus.SEND_OTP],
    LoginStatus.SEND_OTP: [LoginStatus.VERIFY_OTP],
    LoginStatus.VERIFY_OTP: [
        LoginStatus.FACE_VERIFY,
        LoginStatus.SMS_VERIFY,
        LoginStatus.LOGIN_SUCCESSFUL
    ],
    LoginStatus.FACE_VERIFY: [
        LoginStatus.SMS_VERIFY,
        LoginStatus.LOGIN_SUCCESSFUL
    ],
    LoginStatus.SMS_VERIFY: [LoginStatus.LOGIN_SUCCESSFUL],
    LoginStatus.LOGIN_SUCCESSFUL: []  # 终态
}

# 删除 _get_paylist_from_indus
# 删除 _build_get_paylist_request
# 删除 _process_upi_list
# 删除 _check_proxy

class GCashBank:
    
    # 登录失败次数限制常量
    LOGIN_FAILED_COUNT_KEY = '{name}_login_failed_count_{phone}'
    LOGIN_FAILED_MAX_ATTEMPTS = 3  # 最大失败次数
    LOGIN_FAILED_LOCK_TIME = 60 * 60 * 2  # 锁定时间：2小时
    
    LOGIN_LOCK_PHONE_KEY = 'login_on_{bankname}_{phone}'
    LOGIN_LOCK_PAYMENT_KEY = 'login_on_{bankname}_{payment_id}'
    PROXIES_IP_KEY = 'indian_socks_ip_{bankname}'
    PRELOGIN_KEY = 'pre_login_{bankname}_{payment_id}'
    PAYMENT_LOCK_KEY = 'payment_lock:{payment_id}'
    PAYMENT_INTERFACE_LOCK_KEY = 'payment_interface_lock:{payment_id}:{operation_name}'
    PAYMENT_ALLREF_KEY = '*{payment_id}*'
    PRELOGIN_ALLREF_KEY = 'pre_login_*'
    
    def __init__(self, request_handler):
        self.handler = request_handler
        self.redis = request_handler.redis
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # 添加锁相关的属性
        self.name = 'gcash'
        self.lock_time = 300  # 操作锁的锁定时间（秒） - 5分钟
        self.login_data = {}  # 登录数据，用于错误日志
        
        # 添加错误管理器
        self.error_manager = ErrorManager()
    
    # ================== 基础工具方法 ==================
    async def _check_login_failed_attempts(self, phone):
        """检查登录失败次数是否超过限制"""
        try:
            failed_key = self.LOGIN_FAILED_COUNT_KEY.format(name=self.name, phone=phone)
            failed_count = await self.redis.get(failed_key)
            
            if failed_count and int(failed_count) >= self.LOGIN_FAILED_MAX_ATTEMPTS:
                self.logger.warning(f"IndusBank用户 {phone} 登录失败超过{self.LOGIN_FAILED_MAX_ATTEMPTS}次，限制登录")
                return True
            return False
        except Exception as e:
            self.logger.error(f"检查登录失败次数异常: {str(e)}")
            return False
    
    async def _record_login_failed_attempt(self, phone):
        """记录登录失败次数"""
        try:
            failed_key = self.LOGIN_FAILED_COUNT_KEY.format(name=self.name, phone=phone)
            failed_count = await self.redis.get(failed_key)
            
            if failed_count:
                failed_count = int(failed_count) + 1
            else:
                failed_count = 1
            
            # 设置Redis键，过期时间为2小时
            await self.redis.set(failed_key, failed_count, self.LOGIN_FAILED_LOCK_TIME)
            self.logger.warning(f"IndusBank用户 {phone} 登录失败，当前失败次数: {failed_count}")
            
            return failed_count
        except Exception as e:
            self.logger.error(f"记录登录失败次数异常: {str(e)}")
            return 0
    
    async def _clear_login_failed_attempts(self, phone):
        """清除登录失败次数（登录成功时调用）"""
        try:
            failed_key = self.LOGIN_FAILED_COUNT_KEY.format(phone=phone)
            await self.redis.delete(failed_key)
            self.logger.info(f"IndusBank用户 {phone} 登录成功，清除失败计数")
        except Exception as e:
            self.logger.error(f"清除登录失败次数异常: {str(e)}")

    async def _verify_payment_password_bcrypt(self, password, hashed_password, phone):
        """验证交易密码 - 使用bcrypt算法"""
        if not password:
            raise NewApiError('20106', 'Payment password cannot be empty')
        if not hashed_password:
            raise NewApiError('20106', 'User payment password not set')
        
        try:
            if not bcrypt.checkpw(password.encode('utf8'), hashed_password.encode('utf8')):
                # 记录登录失败次数
                await self._record_login_failed_attempt(phone)
                raise NewApiError('20106', 'Payment password verification failed')
            else:
                # 密码验证成功，清除失败计数
                await self._clear_login_failed_attempts(phone)
        except NewApiError:
            raise  # 重新抛出 NewApiError
        except Exception as e:
            self.logger.error(f"Password verification exception: {str(e)}")
            # 记录登录失败次数
            await self._record_login_failed_attempt(phone)
            raise NewApiError('20004', 'Payment password verification failed')
    
    def format_phone_number(self, phone):
        """格式化手机号"""
        if not phone:
            return phone
        # 移除空格和特殊字符
        phone = phone.strip().replace(' ', '').replace('-', '')
        # 如果没有区号，添加印度区号91
        if len(phone) == 10 and phone.isdigit():
            phone = '91' + phone
        return phone

    def validate_phone_number(self, phone):
        """验证手机号格式"""
        if not phone:
            return False
        # 移除可能的空格和特殊字符
        phone = phone.strip().replace(' ', '').replace('-', '')
        # 印度手机号：91 + 10位数字
        return len(phone) == 12 and phone.startswith('91') and phone[2:].isdigit()

    def log_response(self, response):
        """详细记录HTTP响应信息 - 参考jio_bank.py的log_response方法"""
        try:
            from datetime import datetime
            # 基本信息
            self.logger.info("=" * 50)
            self.logger.info(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"请求URL: {response.url}")
            self.logger.info(f"请求方法: {response.request.method}")
            self.logger.info(f"状态码: {response.status_code}")
            
            # 请求头信息
            self.logger.info("请求头:")
            for key, value in dict(response.request.headers).items():
                self.logger.info(f"    {key}: {value}")
            
            # 响应头信息
            self.logger.info("响应头:")
            for key, value in dict(response.headers).items():
                self.logger.info(f"    {key}: {value}")
            
            # 响应体信息
            self.logger.info("响应体:")
            
            # 尝试解析为JSON
            try:
                json_data = response.json()
                self.logger.info("JSON格式响应:")
                self.logger.info(json.dumps(json_data, ensure_ascii=False, indent=2))
            except:
                self.logger.info("非JSON格式响应:")
                # 尝试获取文本内容
                try:
                    text_content = response.text
                    if text_content:
                        if len(text_content) > 1000:
                            self.logger.info(f"{text_content[:1000]}... (内容已截断)")
                        else:
                            self.logger.info(text_content)
                    else:
                        self.logger.info("响应体为空")
                except Exception as e:
                    self.logger.error(f"读取响应体文本失败: {str(e)}")
            
            # 响应编码信息
            if hasattr(response, 'encoding'):
                self.logger.info(f"响应编码: {response.encoding}")
            
            # 耗时信息
            if hasattr(response, 'elapsed'):
                self.logger.info(f"请求耗时: {response.elapsed.total_seconds():.3f} 秒")
            
            # 如果是重定向，记录重定向历史
            if hasattr(response, 'history') and response.history:
                self.logger.info("重定向历史:")
                for hist in response.history:
                    self.logger.info(f"    {hist.status_code} -> {hist.url}")
            
        except Exception as e:
            self.logger.error(f"日志记录过程发生错误: {str(e)}")
        finally:
            self.logger.info("=" * 50)
    
    # ================== 银行配置 ==================
    LOGIN_TYPE = 'sms_otp_pin'

    # Indus UPI配置
    API_ENDPOINTS = {
        'base_url': 'https://indusupiprd.indusind.com',
        'handshake': '/upi/oauth2ClientHandshake',
        'auth_token': '/oauth/token',
        'check_device1': '/upi/api/checkDeviceIdWeb',
        'check_device2': '/upi/api/checkDeviceIdWeb',
        'send_otp': '/upi/api/sendOtpServiceJson',
        'verify_otp': '/upi/api/re_verify_servgenid',
        'verify_pin': '/upi/api/verifyAppPinWeb',  # 修正：使用与PHP版本一致的端点
        'get_paylist': '/upi/api/getPaycollLstWebPrd'
    }

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
        uuid_formatted = f"{uuid_hex[:8]}-{uuid_hex[8:12]}-4{uuid_hex[13:16]}-{random.choice('89ab')}{uuid_hex[17:20]}-{uuid_hex[20:]}"
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
            
            return f"{lat},{lng}"
            
        except ImportError:
            # 如果faker库不可用，使用备用方案
            # 印度的大致坐标范围
            lat = round(random.uniform(8.0, 37.0), 6)
            lng = round(random.uniform(68.0, 97.0), 6)
            return f"{lat},{lng}"

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
            location = f"{city},{state},India"
            
            return location
            
        except ImportError:
            # 如果faker库不可用，使用备用方案
            # 简单的印度地址格式
            cities = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune", "Ahmedabad"]
            states = ["Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "West Bengal", "Telangana", "Gujarat"]
            
            city = random.choice(cities)
            state = random.choice(states)
            
            return f"{city},{state},India"

    @staticmethod
    def encode_message(data):
        """Indus消息编码 - 与PHP版本的enc方法一致"""
        import logging
        logger = logging.getLogger('IndusBank.encode_message')
        
        try:
            from Cryptodome.Cipher import AES
            from Cryptodome.Util.Padding import pad
            
            logger.info("使用Cryptodome库进行AES加密")
            
            # 使用与PHP相同的AES-128-ECB加密
            hex_key = "f89e2d511390414a91a89fc5e0f8f5e4"
            key = bytes.fromhex(hex_key)
            
            # 创建AES-ECB加密器
            cipher = AES.new(key, AES.MODE_ECB)
            
            # PKCS7填充并加密
            padded_data = pad(data.encode('utf-8'), AES.block_size)
            encrypted_data = cipher.encrypt(padded_data)
            
            # 转换为大写十六进制
            result = encrypted_data.hex().upper()
            logger.info(f"AES加密成功，结果长度: {len(result)}")
            return result
            
        except ImportError as e:
            # 降级到base64编码
            logger.error(f"Cryptodome库不可用: {e}")
            logger.warning("降级使用base64编码（可能导致403错误）")
            import base64
            result = base64.b64encode(data.encode()).decode()
            logger.info(f"base64编码完成，结果长度: {len(result)}")
            return result
        except Exception as e:
            # 最简单的降级方案
            logger.error(f"加密过程发生错误: {e}")
            logger.warning("降级使用base64编码（可能导致403错误）")
            import base64
            result = base64.b64encode(data.encode()).decode()
            logger.info(f"base64编码完成，结果长度: {len(result)}")
            return result

    @staticmethod
    def decode_message(data):
        """Indus消息解码 - 与PHP版本的de方法一致"""
        try:
            from Cryptodome.Cipher import AES
            from Cryptodome.Util.Padding import unpad
            import binascii
            
            # 使用与PHP相同的AES-128-ECB解密
            hex_key = "f89e2d511390414a91a89fc5e0f8f5e4"
            key = bytes.fromhex(hex_key)
            
            # 验证输入数据格式
            if not data or len(data) % 2 != 0:
                raise ValueError(f"Invalid hex data: {data}")
            
            # 从十六进制转换为字节
            try:
                encrypted_data = bytes.fromhex(data)
            except ValueError as e:
                raise ValueError(f"Invalid hex format: {data}, error: {e}")
            
            # 验证数据长度是否为16的倍数（AES block size）
            if len(encrypted_data) % 16 != 0:
                raise ValueError(f"Data length {len(encrypted_data)} is not multiple of 16")
            
            # 创建AES-ECB解密器
            cipher = AES.new(key, AES.MODE_ECB)
            decrypted_padded = cipher.decrypt(encrypted_data)
            
            # 移除PKCS7填充
            decrypted_data = unpad(decrypted_padded, AES.block_size)
            
            # 转换为UTF-8字符串
            result = decrypted_data.decode('utf-8')
            return result
            
        except ImportError as e:
            # Cryptodome库不可用，记录错误
            import logging
            logger = logging.getLogger('IndusBank.decode_message')
            logger.error(f"Cryptodome库不可用: {e}, 使用原始数据")
            return data
        except Exception as e:
            # 解密失败，记录详细错误信息
            import logging
            logger = logging.getLogger('IndusBank.decode_message')
            logger.error(f"解密失败: {e}, 输入数据: {data}")
            # 返回原始数据而不是空字符串，这样上层可以判断是否解密成功
            return data

    # ================== 核心登录流程方法 ==================
    async def pre_login_http(self, data):
        """
        IndusBank预登录HTTP接口 - 处理用户登录前的准备工作
        
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
        - 过期时间：300秒（5分钟）
        
        📤 返回格式：
        {
            'status': 'success/error',
            'message': '描述信息',
            'data': {
                'id': payment_id,
                'redis_key': 'pre_login_indus_xxx',
                'expires_in': 300,
                'next_step': 'send_sms'
            }
        }
        
        🔄 下一步：调用 send_sms_http
        """
        payment_lock_id = None
        payment_lock_value = None
        
        try:
            self.logger.info(f"=== IndusBank预登录HTTP接口开始 ===")
            self.logger.info(f"IndusBank预登录请求数据: {data}")
            
            # 检查用户类型 完成登录信息提交
            if 'step' not in data or data['step'] == 'complete_login':
                self.logger.info(f"执行预登录步骤: {data.get('step', 'complete_login')}")
                
                required_fields = ['bankname', 'phone', 'password']
                if not all(field in data and data[field] for field in required_fields):
                    missing_fields = [field for field in required_fields if field not in data or not data[field]]
                    error_msg = f"Missing required parameters: {', '.join(missing_fields)}"
                    self.logger.error(f"IndusBank预登录参数验证失败: {error_msg}")
                    raise NewApiError('20001', error_msg)
                
                bankname = data['bankname']
                original_phone = data['phone']  # 保存原始号码
                phone = self.format_phone_number(data['phone'])
                password = data['password']
                
                # 检查登录失败次数限制
                self.logger.info(f"IndusBank检查登录失败次数: 手机号={phone}")
                is_locked = await self._check_login_failed_attempts(phone)
                if is_locked:
                    self.logger.error(f"IndusBank用户 {phone} 登录失败次数超过限制，拒绝登录")
                    raise NewApiError('20106', 'Try too many times, try again after two hours.')
                
                # 验证交易密码 - 参考UPI controller的密码验证逻辑
                try:
                    await self._verify_payment_password_bcrypt(password, self.handler.current_user.hash_trade, phone)
                    self.logger.info(f"IndusBank预登录密码验证成功: 用户={self.handler.current_user.id}, 手机号={phone}")
                except Exception as e:
                    self.logger.error(f"IndusBank预登录密码验证失败: 用户={self.handler.current_user.id}, 手机号={phone}, 错误={str(e)}")
                    raise NewApiError('20106', 'Payment password verification failed')
                
                # 从认证的用户信息中获取码商ID
                user_id = self.handler.current_user.id  # ← 获取码商ID
                is_new_user = data.get('is_new_user', True)
                payment_id = data.get('payment_id')  # 获取payment_id
                
                self.logger.info(f"IndusBank预登录参数: 银行={bankname}, 手机号={phone}, 码商ID={user_id}")
                self.logger.info(f"IndusBank当前认证用户信息: ID={user_id}, 手机号={getattr(self.handler.current_user, 'cellphone', 'Unknown')}")
                
                if not self.validate_phone_number(phone):
                    raise NewApiError('20002', f'Invalid phone number format: {phone}, should start with 91 and be 12 digits long')

                # 立即检查协议进程锁 - 在任何复杂处理前进行早期检查
                # 检查 payment_id 登录状态
                if payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=bankname, payment_id=payment_id)):
                    raise NewApiError('20101', f'Account is in login process, please try again later')
                
                # 检查 phone 登录状态  
                if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=bankname, phone=phone)):
                    raise NewApiError('20101', f'Account is in login process, please try again later')

                # 如果提供了payment_id，验证phone是否匹配
                if payment_id:
                    # 获取银行类型ID
                    bank_type_id = await self._get_bank_type_id(bankname)
                    if not bank_type_id:
                        raise NewApiError('20003', f'Bank type not found for: {bankname}')
                    
                    with self.handler.db_orm.sessionmaker() as session:
                        existing_payment = session.query(Payment).filter(
                            Payment.id == payment_id,
                            Payment.bank_type == bank_type_id
                        ).first()
                        if not existing_payment:
                            raise NewApiError('20003', f'Payment record not found: {payment_id}')
                        if existing_payment.phone != phone and existing_payment.phone != original_phone:
                            raise NewApiError('20005', f'Phone number mismatch for payment {payment_id}, expected {existing_payment.phone}')
                        self.logger.info(f"Payment record validation successful: {payment_id}")
                else:
                    # 检查现有payment记录
                    existing_payment = await self._check_existing_payment(bankname, original_phone, user_id)
                    is_new_user = existing_payment is None
                    self.logger.info(f"IndusBank用户类型检查: {phone} - partner_id: {user_id} - 新用户: {is_new_user}")

                    if existing_payment:
                        # UPI已存在且属于当前用户，应该去UPI列表激活而不是重新登录
                        self.logger.error(f"IndusBank UPI已存在且属于当前用户: phone={phone}, user_id={user_id}")
                        raise NewApiError('10401')  # UPI已存在且属于当前用户
                    else:
                        payment_id = phone  # 直接使用手机号作为临时ID
                        self.logger.info(f"IndusBank使用手机号作为payment_id: {payment_id}")

                # [LOCK] 获取基于payment_id的接口锁
                try:
                    lock_result = await self._get_payment_interface_lock(payment_id, 'pre_login')
                    # 保存锁信息用于finally块释放
                    payment_lock_id = lock_result.get('lock_id')
                    payment_lock_value = lock_result.get('lock_value')
                except NewApiError as lock_error:
                    self.logger.warning(f"IndusBank预登录接口锁限制: {lock_error.message}")
                    raise lock_error
                

                # 创建Redis登录会话
                redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
                self.logger.info(f"IndusBank创建Redis会话key: {redis_key}")
                
                # 检查是否已存在会话
                existing_session = await self._get_session_data(redis_key)
                if existing_session:
                    current_status = existing_session.get('status')
                    self.logger.warning(f"IndusBank发现已存在会话: {redis_key} - 状态: {current_status}")
                    if current_status == LoginStatus.LOGIN_SUCCESSFUL:
                        self.logger.error(f"IndusBank账户已登录成功，拒绝重复登录")
                        raise NewApiError('20102', f'Account already logged in successfully, duplicate login denied')
                    elif current_status == LoginStatus.PRE_LOGIN:
                        self.logger.error(f"IndusBank已经开始走登录流程，拒绝重复登录")
                        raise NewApiError('20103', f'Account already started login process, duplicate login denied')
                    elif current_status in [LoginStatus.SEND_SMS, LoginStatus.VERIFY_SMS, LoginStatus.SEND_OTP, LoginStatus.VERIFY_OTP, LoginStatus.VERIFY_PIN, LoginStatus.GET_PAYLIST]:
                        self.logger.error(f"IndusBank登录流程进行中，拒绝重复登录")
                        raise NewApiError('20104', f' status: {current_status}')
                
                # 选择代理IP
                proxy_ip = await self._select_proxy_ip(bankname)
                self.logger.info(f"IndusBank选择代理IP: {proxy_ip}")

                # 一次生成、整个流程不变的设备标识
                android_id = self.generate_android_id()
                safety_net_id = self.generate_safety_net_id()
                app_gen_id = self.generate_app_gen_id()  # 重要：一次生成，后续复用
                
                # 生成动态设备信息
                device_model = self.generate_device_model()
                india_geocode = self.generate_india_geocode()
                india_location = self.generate_india_location()
                
                # 构建IndusBank特定的会话数据（纯会话初始化，不调用银行API）
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
                    'to': 'indus',                              # 目标key
                    'qr_channel': data.get('channel', 1001),    # 渠道
                    'pinCode': data.get('pin', ''),             # PIN码

                    # === 扩展必要字段 ===
                    'bankname': bankname,                       # 银行名称
                    'password': password,                       # 密码
                    'account': data.get('account', ''),         # 账户信息
                    'is_new_user': is_new_user,                 # 是否新用户
                    'status_history': [LoginStatus.PRE_LOGIN], # 状态历史
                    
                    # === 时间管理 ===
                    'login_time': int(time.time()),             # 登录开始时间
                    'last_status_change': int(time.time()),     # 最后状态变更时间
                    'last_request_time': int(time.time()),      # 最后请求时间
                    'expires_at': int(time.time()) + 300,       # 过期时间
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
                    
                    # === IndusBank特定的认证数据 ===
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
                    
                    # === IndusBank特定数据 ===
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

                # 存储到Redis
                await self.redis.setex(redis_key, 300, json.dumps(session_data))
                self.logger.info(f"IndusBank会话数据已存储到Redis: {redis_key} - 过期时间: 1800秒(30分钟)")
                
                self.logger.info(f"IndusBank预登录成功: {phone} - {payment_id} - 新用户: {is_new_user}")
                self.logger.info(f"=== IndusBank预登录完成 ===")
                
                result = {
                    'status': 'success',
                    'message': 'IndusBank预登录成功',
                    'data': {
                        'id': payment_id,
                        'redis_key': redis_key,
                        'expires_in': 300,
                        'total_timeout': 120,
                        'is_new_user': is_new_user,
                        'bank_type': self.LOGIN_TYPE,
                        'next_step': 'send_sms'
                    }
                }
                self.logger.info(f"IndusBank预登录返回结果: {result}")
                return result
            
            else:
                step = data.get('step', 'unknown')
                raise NewApiError('20105', f'Unsupported step: {step}')
                
        except NewApiError:
            raise  # 重新抛出NewApiError，不要重新包装
        except Exception as e:
            self.logger.error(f"IndusBank预登录异常: {str(e)}")
            raise NewApiError('20106', f'{str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            if payment_lock_id and payment_lock_value:
                await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
                self.logger.info(f"IndusBank预登录释放payment锁: id={payment_lock_id}")

    async def send_sms_http(self, data):
        """
        IndusBank发送短信验证 - 获取短信配置信息
        
        📋 功能说明：
        - 在这里进行银行交互：握手+认证+设备检查+获取短信配置
        - 生成短信内容和接收号码，返回给前端
        - 用户需要手动发送短信到指定号码
        
        📥 输入参数：
        - bankname: 银行名称 (必需)
        - payment_id: 支付ID (必需，来自pre_login_http返回)
        
        [SESSION] 会话数据要求：
        - 必须存在Redis会话: pre_login_{bankname}_{payment_id}
        - 当前状态必须是: preLogin
        - 包含完整的设备标识信息
        
        🔄 处理流程：
        1. 验证会话状态
        2. 握手验证
        3. 获取认证令牌
        4. 第一次设备检查
        5. 生成短信配置（号码+内容）
        6. 通知外部API
        
        [SESSION] 会话数据更新：
        - 状态变更为: sendSMS
        - 保存短信配置信息
        - 更新认证令牌
        
        📤 返回格式：
        {
            'status': 'success/error',
            'message': '描述信息',
            'data': {
                'id': payment_id,
                'receive_sms_number': '+919650869940',
                'receive_sms_content': 'INDB...',
                'sms_instruction': '请使用目标手机发送以上内容',
                'expires_in': 600,
                'next_step': 'verify_sms'
            }
        }
        
        🔄 下一步：用户发送短信后调用 verify_sms_http
        """
        try:
            bankname = data.get('bankname')
            payment_id = data.get('payment_id') or data.get('id')
            redis_key = f"pre_login_{bankname}_{payment_id}"
            
            self.logger.info(f"=== IndusBank获取短信配置开始 ===")
            self.logger.info(f"请求参数: bankname={bankname}, payment_id={payment_id}")
            
            # 验证会话状态
            session_data = await self._get_session_data(redis_key)
            if not session_data:
                raise NewApiError('20201', f'Send SMS session does not exist or has expired: {redis_key}')

            # 检查登录锁状态
            phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=phone)):
                raise NewApiError('20101', f'Account is in login process, please try again later')

            # 验证状态转换
            status_check = await self._validate_status_transition(
                session_data, LoginStatus.PRE_LOGIN, LoginStatus.SEND_SMS, "IndusBank获取短信配置"
            )
            if not status_check.get('valid'):
                raise NewApiError('20202', f'Status transition failed: {status_check.get("message", "Unknown error")}')

            # 执行银行API交互流程：握手 -> 认证 -> 设备检查 -> 生成短信配置
            self.logger.info(f"开始银行API交互流程...")
            
            # 1. 握手
            self.logger.info(f"步骤1: 执行握手...")
            handshake_result = await self._handshake(session_data)
            if not handshake_result.get('status') == 'success':
                raise NewApiError('20301', f'Handshake failed: {handshake_result.get("message", "Unknown error")}')

            # 2. 获取认证令牌
            self.logger.info(f"步骤2: 获取认证令牌...")
            auth_result = await self._get_auth_token(session_data)
            if not auth_result.get('status') == 'success':
                raise NewApiError('20302', f'Authentication failed: {auth_result.get("message", "Unknown error")}')

            # 3. 第一次设备检查
            self.logger.info(f"步骤3: 第一次设备检查...")
            device_check_result = await self._check_device_web1(session_data)
            if not device_check_result.get('status') == 'success':
                raise NewApiError('20303', f'Device check failed: {device_check_result.get("message", "Unknown error")}')

            # 4. 生成短信内容
            self.logger.info(f"步骤4: 生成短信配置...")
            sms_result = await self._generate_sms_content(session_data)
            if not sms_result.get('status') == 'success':
                raise NewApiError('20304', f'Generate SMS configuration failed: {sms_result.get("message", "Unknown error")}')

            # 获取生成的短信配置
            sms_number = session_data.get('bank_specific_data', {}).get('sms_number', '')
            sms_content = session_data.get('bank_specific_data', {}).get('sms_content', '')
            
            self.logger.info(f"检查短信配置: sms_number={sms_number}, sms_content_length={len(sms_content) if sms_content else 0}")
            self.logger.info(f"session_data keys: {list(session_data.keys())}")
            self.logger.info(f"bank_specific_data: {session_data.get('bank_specific_data', {})}")
            
            if not sms_number or not sms_content:
                # 更详细的错误信息
                missing_fields = []
                if not sms_number:
                    missing_fields.append('sms_number')
                if not sms_content:
                    missing_fields.append('sms_content')
                error_msg = f'IndusBank SMS configuration retrieval failed, missing fields: {", ".join(missing_fields)}'
                self.logger.error(error_msg)
                raise NewApiError('20305', error_msg)



            # 更新会话状态和时间
            await self._update_session_status(
                redis_key, session_data, LoginStatus.SEND_SMS,
                {
                    'sendSMSTime': int(time.time()),
                    'bank_specific_data': {
                        **session_data.get('bank_specific_data', {}),
                        'sms_sent': False,  # 注意：这里是False，因为用户还没有手动发送短信
                        'sms_config_obtained': True  # 标记短信配置已获取
                    }
                }
            )

            self.logger.info(f"IndusBank短信配置获取成功:")
            self.logger.info(f"  短信号码: {sms_number}")
            self.logger.info(f"  短信内容: {sms_content[:50]}...")
            self.logger.info(f"=== IndusBank获取短信配置完成 ===")

            return {
                'status': 'success',
                'message': 'IndusBank短信配置获取成功，请手动发送短信',
                'data': {
                    'id': payment_id,
                    'receive_sms_number': sms_number,
                    'receive_sms_content': sms_content,
                    'sms_instruction': f'Please send SMS "{sms_content}" to {sms_number}',
                    'expires_in': 600,
                    'next_step': 'verify_sms'
                }
            }

        except NewApiError:
            raise  # 重新抛出API错误
        except Exception as e:
            self.logger.error(f"IndusBank获取短信配置失败: {str(e)}")
            raise NewApiError('20305', f'Get SMS configuration exception: {str(e)}')

    async def verify_sms_http(self, data):
        """验证短信发送状态"""
        try:
            self.logger.info(f"=== IndusBank验证短信开始 ===")
            self.logger.info(f"请求参数: {data}")
            
            # 验证必要参数
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                error_msg = f"验证短信缺少必要参数: {', '.join(missing_fields)}"
                self.logger.error(f"IndusBank验证短信参数验证失败: {error_msg}")
                raise NewApiError('20001', error_msg)
            
            self.logger.info(f"[SUCCESS] 参数验证通过")
            
            # 检查是否先调用了send_sms_http
            bankname = data['bankname']
            payment_id = data['payment_id']
            
            self.logger.info(f"[DATA] 处理参数: bankname={bankname}, payment_id={payment_id}")
            
            # 检查正确的调用流程提示
            self.logger.info(f"[INFO] 正确的调用流程应该是:")
            self.logger.info(f"   1. pre_login_http (初始化会话)")
            self.logger.info(f"   2. send_sms_http (获取短信配置)")  
            self.logger.info(f"   3. verify_sms_http (验证短信) <- 当前步骤")
            self.logger.info(f"如果没有按顺序调用，会导致会话数据不存在的错误")
            redis_key = f"pre_login_{bankname}_{payment_id}"
            self.logger.info(f"IndusBank验证短信: 银行={bankname}, payment_id={payment_id}, redis_key={redis_key}")
            
            # 获取会话数据
            self.logger.info(f"尝试从Redis获取会话数据: {redis_key}")
            session_data = await self._get_session_data(redis_key)
            self.logger.info(f"从Redis获取的会话数据: {session_data}")
            
            if not session_data:
                self.logger.error(f"IndusBank会话不存在或已过期: {redis_key}")
                
                # 额外调试：检查Redis中所有相关的键
                try:
                    # 尝试检查Redis中是否有其他相关键
                    all_keys = await self.redis.keys(self.PAYMENT_ALLREF_KEY.format(payment_id=payment_id))
                    self.logger.info(f"Redis中包含payment_id的所有键: {all_keys}")
                    
                    # 尝试检查pre_login前缀的键
                    pre_login_keys = await self.redis.keys(self.PRELOGIN_ALLREF_KEY)
                    self.logger.info(f"Redis中所有pre_login_*键: {pre_login_keys}")
                    
                except Exception as e:
                    self.logger.error(f"检查Redis键失败: {str(e)}")
                
                # 提供解决方案建议
                self.logger.error(f"🔧 解决方案建议:")
                self.logger.error(f"   1. 检查是否先调用了 pre_login_http 初始化会话")
                self.logger.error(f"   2. 检查是否先调用了 send_sms_http 获取短信配置")
                self.logger.error(f"   3. 检查 payment_id 是否一致: {payment_id}")
                self.logger.error(f"   4. 检查会话是否过期 (30分钟TTL)")
                
                raise NewApiError('20208', f'SMS verification session does not exist or has expired: {redis_key}')

            # 检查登录锁状态
            phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=phone)):
                raise NewApiError('20101', f'Account is in login process, please try again later')

            # 验证状态转换
            status_check = await self._validate_status_transition(
                session_data, LoginStatus.SEND_SMS, LoginStatus.VERIFY_SMS, "IndusBank验证短信"
            )
            if not status_check['valid']:
                raise NewApiError('20202', f'Status transition failed: {status_check.get("message", "Unknown error")}')

            # === 关键修复：重新获取认证信息（参考PHP版本continue_after_sms.php）===
            self.logger.info(f"=== 第1步：重新获取认证信息 ===")
            
            # 1. 重新握手
            self.logger.info(f"1.1 重新握手验证...")
            handshake_result = await self._handshake(session_data)
            if not handshake_result.get('status') == 'success':
                raise NewApiError('20306', f'Re-handshake failed: {handshake_result.get("message", "Unknown error")}')
            self.logger.info(f"重新握手成功 [SUCCESS]")
            
            # 2. 重新获取认证令牌
            self.logger.info(f"1.2 重新获取认证令牌...")
            auth_result = await self._get_auth_token(session_data)
            if not auth_result.get('status') == 'success':
                raise NewApiError('20307', f'Re-authentication failed: {auth_result.get("message", "Unknown error")}')
            self.logger.info(f"重新获取认证令牌成功 [SUCCESS]")

            # === 第2步：第二次设备验证 ===
            self.logger.info(f"=== 第2步：第二次设备验证 (checkDeviceIdWeb2) ===")
            self.logger.info(f"[INFO] 此步骤验证短信是否已成功发送给运营商")
            
            # 第二次设备检查，确认短信是否成功发送
            device_check2_result = await self._check_device_web2(session_data)
            self.logger.info(f"IndusBank第二次设备检查结果: {device_check2_result}")
            
            # [ERROR] 第二次设备检查失败时直接报错，不再继续流程
            if device_check2_result.get('status') != 'success':
                error_message = device_check2_result.get('message', 'Second device check failed')
                self.logger.error(f"[CRITICAL ERROR] IndusBank第二次设备检查失败: {error_message}")
                self.logger.error(f"[INFO] 可能原因:")
                self.logger.error(f"   1. 短信未成功发送到运营商")
                self.logger.error(f"   2. 短信内容格式不正确")
                self.logger.error(f"   3. 银行检测到安全问题")
                self.logger.error(f"   4. 需要等待更长时间让运营商处理短信")
                raise NewApiError('20308', f'Device verification failed: {error_message}')
            else:
                self.logger.info(f"[SUCCESS] IndusBank第二次设备检查成功")

            # 更新状态（无论设备检查是否成功都继续）
            await self._update_session_status(
                redis_key, session_data, LoginStatus.VERIFY_SMS
            )

            self.logger.info(f"IndusBank短信验证流程完成，可以申请OTP")
            self.logger.info(f"=== IndusBank验证短信完成 ===")
            
            return {
                'status': 'success',
                'message': 'IndusBank短信验证流程完成，可以申请OTP',
                'data': {
                    'id': payment_id,
                    'next_step': 'send_otp',
                    'device_check_passed': device_check2_result.get('success', False),
                    'device_check_message': device_check2_result.get('message', '')
                }
            }

        except NewApiError:
            raise  # 重新抛出API错误
        except Exception as e:
            self.logger.error(f"IndusBank验证短信失败: {str(e)}")
            import traceback
            self.logger.error(f"IndusBank验证短信异常堆栈: {traceback.format_exc()}")
            raise NewApiError('20309', f'SMS verification exception: {str(e)}')

    async def send_otp_http(self, data):
        """发送OTP验证码"""
        try:
            self.logger.info(f"=== IndusBank发送OTP开始 ===")
            self.logger.info(f"原始请求参数: {data}")
            
            # 验证必要参数
            required_fields = ['bankname', 'payment_id']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f"IndusBank发送OTP参数验证失败: 缺少必要参数 {required_fields}")
                self.logger.error(f"实际收到的参数: {list(data.keys())}")
                raise NewApiError('20001', f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            redis_key = f"pre_login_{bankname}_{payment_id}"
            
            self.logger.info(f"参数验证通过！")
            self.logger.info(f"处理参数: bankname={bankname}, payment_id={payment_id}")
            self.logger.info(f"Redis键: {redis_key}")
            
            # 获取会话数据
            self.logger.info(f"正在从Redis获取会话数据...")
            session_data = await self._get_session_data(redis_key)
            
            if not session_data:
                self.logger.error(f"会话数据不存在: {redis_key}")
                self.logger.error(f"请确保按正确流程调用:")
                self.logger.error(f"   1. pre_login_http (初始化会话)")
                self.logger.error(f"   2. send_sms_http (获取短信配置)") 
                self.logger.error(f"   3. verify_sms_http ← 可能缺少这一步")
                self.logger.error(f"   4. send_otp_http ← 当前步骤")
                raise NewApiError('20201', 'Session data does not exist, please call verify_sms_http first')

            # 检查登录锁状态
            phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=phone)):
                raise NewApiError('20101', f'Account is in login process, please try again later')

            self.logger.info(f"成功获取会话数据！")
            self.logger.info(f"=== 会话数据详细信息 ===")
            self.logger.info(f"当前状态: {session_data.get('status', 'UNKNOWN')}")
            self.logger.info(f"手机号: {session_data.get('phone', 'UNKNOWN')}")
            self.logger.info(f"app_gen_id: {session_data.get('app_gen_id', 'UNKNOWN')}")
            self.logger.info(f"android_id: {session_data.get('androidId', 'UNKNOWN')}")
            self.logger.info(f"safety_net_id: {session_data.get('safetyNetId', 'UNKNOWN')}")
            self.logger.info(f"authorization存在: {'是' if session_data.get('authorization') else '否'}")
            if session_data.get('authorization'):
                auth_preview = session_data.get('authorization')[:50] + "..." if len(session_data.get('authorization', '')) > 50 else session_data.get('authorization')
                self.logger.info(f"authorization预览: {auth_preview}")
            
            # 检查必需字段
            required_session_fields = ['phone', 'app_gen_id', 'androidId', 'safetyNetId', 'authorization']
            missing_fields = []
            for field in required_session_fields:
                if not session_data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                self.logger.error(f"会话数据不完整，缺少字段: {missing_fields}")
                self.logger.error(f"这通常说明:")
                self.logger.error(f"   - verify_sms_http 没有成功完成")
                self.logger.error(f"   - 会话数据被部分清除")
                self.logger.error(f"   - 需要重新开始登录流程")
                raise NewApiError('20201', f"Session data incomplete, missing fields: {', '.join(missing_fields)}")
            
            self.logger.info(f"会话数据完整性检查通过！")

            # 验证状态转换
            self.logger.info(f"正在验证状态转换...")
            self.logger.info(f"当前状态: {session_data.get('status')}")
            self.logger.info(f"期望状态: {LoginStatus.VERIFY_SMS}")
            self.logger.info(f"目标状态: {LoginStatus.SEND_OTP}")
            
            status_check = await self._validate_status_transition(
                session_data, LoginStatus.VERIFY_SMS, LoginStatus.SEND_OTP, "IndusBank发送OTP"
            )
            if not status_check['valid']:
                current_status = session_data.get('status', 'unknown')
                self.logger.error(f"状态转换无效!")
                self.logger.error(f"当前状态: {current_status}")
                self.logger.error(f"期望状态: {LoginStatus.VERIFY_SMS}")
                self.logger.error(f"请确保按正确顺序调用API:")
                self.logger.error(f"   当前状态 {current_status} → 需要状态 {LoginStatus.VERIFY_SMS}")
                raise NewApiError('20102', f"Invalid status transition, current status: {current_status}, please call verify_sms_http first")

            self.logger.info(f"状态转换验证通过！")

            # === 关键步骤：重新获取认证信息（参考PHP版本continue_after_sms.php）===
            self.logger.info(f"=== 第1步：重新获取认证信息 ===")
            self.logger.info(f"根据PHP版本的逻辑，每次API调用前都需要重新获取认证")
            
            # 1. 重新握手
            self.logger.info(f"1.1 重新握手验证...")
            handshake_result = await self._handshake(session_data)
            if not handshake_result.get('status') == 'success':
                self.logger.error(f"重新握手失败: {handshake_result['message']}")
                raise NewApiError('20301', f'Re-handshake failed: {handshake_result["message"]}')
            self.logger.info(f"重新握手成功！")
            
            # 2. 重新获取认证令牌
            self.logger.info(f"1.2 重新获取认证令牌...")
            auth_result = await self._get_auth_token(session_data)
            if not auth_result.get('status') == 'success':
                self.logger.error(f"重新认证失败: {auth_result['message']}")
                raise NewApiError('20301', f'Re-authentication failed: {auth_result["message"]}')
            self.logger.info(f"重新获取认证令牌成功！")
            self.logger.info(f"新的Authorization: {session_data.get('authorization', '')[:50]}...")



            # 调用Indus API发送OTP
            self.logger.info(f"=== 开始调用银行API发送OTP ===")
            self.logger.info(f"API端点: {self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['send_otp']}")
            
            # 显示将要发送的关键参数
            self.logger.info(f"将要发送的关键参数:")
            self.logger.info(f"   手机号: {session_data.get('phone')}")
            self.logger.info(f"   app_gen_id: {session_data.get('app_gen_id')}")
            self.logger.info(f"   android_id: {session_data.get('android_id')}")
            self.logger.info(f"   safety_net_id: {session_data.get('safety_net_id')}")
            
            otp_result = await self._send_otp_to_indus(session_data)
            
            self.logger.info(f"银行API响应结果:")
            self.logger.info(f"   成功: {otp_result.get('status') == 'success'}")
            self.logger.info(f"   消息: {otp_result.get('message')}")
            
            if not otp_result.get('status') == 'success':
                self.logger.error(f"银行API调用失败!")
                self.logger.error(f"失败原因: {otp_result['message']}")
                raise NewApiError('20401', f"Send OTP failed: {otp_result['message']}")

            self.logger.info(f"银行API调用成功！")

            # 更新状态
            self.logger.info(f"正在更新会话状态...")
            self.logger.info(f"状态变更: {session_data.get('status')} → {LoginStatus.SEND_OTP}")
            
            await self._update_session_status(
                redis_key, session_data, LoginStatus.SEND_OTP
            )

            self.logger.info(f"会话状态更新成功！")
            self.logger.info(f"=== IndusBank OTP发送完全成功！===")
            self.logger.info(f"用户手机 {session_data.get('phone')} 应该会收到OTP验证码短信")
            self.logger.info(f"下一步: 用户收到OTP后调用 verify_otp_http")
            self.logger.info(f"=== IndusBank发送OTP完成 ===")
            
            return {
                'status': 'success',
                'message': 'OTP发送成功，请输入收到的验证码',
                'data': {
                    'next_status': LoginStatus.VERIFY_OTP,
                    'phone': session_data.get('phone'),
                    'instruction': f"请查看手机 {session_data.get('phone')} 收到的OTP验证码短信"
                }
            }

        except Exception as e:
            self.logger.error(f"=== IndusBank发送OTP异常 ===")
            self.logger.error(f"异常类型: {type(e).__name__}")
            self.logger.error(f"异常信息: {str(e)}")
            import traceback
            self.logger.error(f"完整异常堆栈:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f"   {line}")
            raise NewApiError('20309', f'Send OTP failed: {str(e)}')

    async def verify_otp_http(self, data):
        """验证OTP验证码"""
        try:
            self.logger.info(f"=== IndusBank验证OTP开始 ===")
            self.logger.info(f"原始请求参数: {data}")
            
            # 验证必要参数
            required_fields = ['bankname', 'payment_id', 'otp']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f"IndusBank验证OTP参数验证失败: 缺少必要参数 {required_fields}")
                self.logger.error(f"实际收到的参数: {list(data.keys())}")
                raise NewApiError('20001', f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            otp_code = data.get('otp', '').strip()
            redis_key = f"pre_login_{bankname}_{payment_id}"
            
            self.logger.info(f"参数验证通过！")
            self.logger.info(f"处理参数: bankname={bankname}, payment_id={payment_id}, otp=***")
            self.logger.info(f"Redis键: {redis_key}")
            
            # 获取会话数据
            self.logger.info(f"正在从Redis获取会话数据...")
            session_data = await self._get_session_data(redis_key)
            
            if not session_data:
                self.logger.error(f"会话数据不存在: {redis_key}")
                self.logger.error(f"请确保按正确流程调用:")
                self.logger.error(f"   1. pre_login_http (初始化会话)")
                self.logger.error(f"   2. send_sms_http (获取短信配置)") 
                self.logger.error(f"   3. verify_sms_http (验证短信)")
                self.logger.error(f"   4. send_otp_http (发送OTP)")
                self.logger.error(f"   5. verify_otp_http ← 当前步骤")
                raise NewApiError('20201', 'Session data does not exist, please call send_otp_http first')

            # 检查登录锁状态
            phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=phone)):
                raise NewApiError('20101', f'Account is in login process, please try again later')

            if not otp_code:
                self.logger.error(f"OTP验证码为空")
                raise NewApiError('20001', 'OTP code cannot be empty')
            
            self.logger.info(f"成功获取会话数据！")
            self.logger.info(f"=== 会话数据详细信息 ===")
            self.logger.info(f"当前状态: {session_data.get('status', 'UNKNOWN')}")
            self.logger.info(f"手机号: {session_data.get('phone', 'UNKNOWN')}")
            self.logger.info(f"输入OTP: ***（已隐藏）")

            # 验证状态转换
            status_check = await self._validate_status_transition(
                session_data, LoginStatus.SEND_OTP, LoginStatus.VERIFY_OTP, "IndusBank验证OTP"
            )
            if not status_check['valid']:
                raise NewApiError('20102', 'Invalid status transition')

            # === 关键步骤：重新获取认证信息（参考PHP版本verify_otp.php）===
            self.logger.info(f"=== 第1步：重新获取认证信息 ===")
            self.logger.info(f"根据PHP版本的逻辑，每次API调用前都需要重新获取认证")
            
            # 1. 重新握手
            self.logger.info(f"1.1 重新握手验证...")
            handshake_result = await self._handshake(session_data)
            if not handshake_result.get('status') == 'success':
                self.logger.error(f"重新握手失败: {handshake_result['message']}")
                raise NewApiError('20301', f'Re-handshake failed: {handshake_result["message"]}')
            self.logger.info(f"重新握手成功！")
            
            # 2. 重新获取认证令牌
            self.logger.info(f"1.2 重新获取认证令牌...")
            auth_result = await self._get_auth_token(session_data)
            if not auth_result.get('status') == 'success':
                self.logger.error(f"重新认证失败: {auth_result['message']}")
                raise NewApiError('20301', f'Re-authentication failed: {auth_result["message"]}')
            self.logger.info(f"重新获取认证令牌成功！")
            self.logger.info(f"新的Authorization: {session_data.get('authorization', '')[:50]}...")

            # 调用Indus API验证OTP
            self.logger.info(f"=== 开始调用银行API验证OTP ===")
            self.logger.info(f"API端点: {self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['verify_otp']}")
            self.logger.info(f"OTP验证码: {otp_code}")
            
            verify_result = await self._verify_otp_with_indus(session_data, otp_code)
            if not verify_result.get('status') == 'success':
                return verify_result

            # 更新状态并保存servGenId
            self.logger.info(f"正在更新会话状态...")
            session_data['serv_gen_id'] = verify_result['data'].get('serv_gen_id')
            await self._update_session_status(
                redis_key, session_data, LoginStatus.VERIFY_OTP
            )

            self.logger.info(f"会话状态更新成功！")
            self.logger.info(f"=== IndusBank OTP验证完全成功！===")
            self.logger.info(f"ServGenId: {verify_result['data'].get('serv_gen_id')}")
            self.logger.info(f"下一步: 用户输入PIN码后调用 verify_pin_http")
            self.logger.info(f"=== IndusBank验证OTP完成 ===")

            return {
                'status': 'success',
                'message': 'OTP验证成功，请输入PIN码',
                'data': {
                    'next_status': LoginStatus.VERIFY_PIN,
                    'serv_gen_id': verify_result['data'].get('serv_gen_id')
                }
            }

        except Exception as e:
            self.logger.error(f"验证OTP失败: {str(e)}")
            raise NewApiError('20309', f'OTP verification failed: {str(e)}')

    async def get_upi_list_http(self, data):
        """验证PIN码"""
        try:
            self.logger.info(f"=== IndusBank验证PIN开始 ===")
            self.logger.info(f"原始请求参数: {data}")
            
            # 验证必要参数
            required_fields = ['bankname', 'payment_id', 'pin']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f"IndusBank验证PIN参数验证失败: 缺少必要参数 {required_fields}")
                self.logger.error(f"实际收到的参数: {list(data.keys())}")
                raise NewApiError('20001', f"Missing required parameters: {', '.join(missing_fields)}")
            
            # 获取参数
            bankname = data['bankname']
            payment_id = data['payment_id']
            pin_code = data.get('pin', '').strip()
            redis_key = self.PRELOGIN_KEY.format(bankname=bankname, payment_id=payment_id)
            
            self.logger.info(f"参数验证通过！")
            self.logger.info(f"处理参数: bankname={bankname}, payment_id={payment_id}, pin=***")
            self.logger.info(f"Redis键: {redis_key}")
            
            # 获取会话数据
            self.logger.info(f"正在从Redis获取会话数据...")
            session_data = await self._get_session_data(redis_key)
            
            if not session_data:
                self.logger.error(f"会话数据不存在: {redis_key}")
                self.logger.error(f"请确保按正确流程调用:")
                self.logger.error(f"   1. pre_login_http (初始化会话)")
                self.logger.error(f"   2. send_sms_http (获取短信配置)") 
                self.logger.error(f"   3. verify_sms_http (验证短信)")
                self.logger.error(f"   4. send_otp_http (发送OTP)")
                self.logger.error(f"   5. verify_otp_http (验证OTP)")
                self.logger.error(f"   6. verify_pin_http ← 当前步骤")
                raise NewApiError('20201', 'Session data does not exist, please call verify_otp_http first')

            # 检查登录锁状态
            phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=phone)):
                raise NewApiError('20101', f'Account is in login process, please try again later')

            if not pin_code:
                self.logger.error(f"PIN码为空")
                raise NewApiError('20001', 'PIN code cannot be empty')
            
            # 更新session中的pinCode
            session_data['pinCode'] = pin_code
            await self.redis.setex(redis_key, 300, json.dumps(session_data))
            self.logger.info(f"已更新session中的pinCode: ***")
            
            self.logger.info(f"成功获取会话数据！")
            self.logger.info(f"=== 会话数据详细信息 ===")
            self.logger.info(f"当前状态: {session_data.get('status', 'UNKNOWN')}")
            self.logger.info(f"手机号: {session_data.get('phone', 'UNKNOWN')}")
            self.logger.info(f"ServGenId: {session_data.get('serv_gen_id', 'UNKNOWN')}")
            self.logger.info(f"输入PIN: ***（已隐藏）")

            # 验证状态转换
            status_check = await self._validate_status_transition(
                session_data, LoginStatus.VERIFY_OTP, LoginStatus.VERIFY_PIN, "IndusBank验证PIN"
            )
            if not status_check['valid']:
                raise NewApiError('20102', 'Invalid status transition')

            # === 关键步骤：重新获取认证信息（参考PHP版本verify_pin.php）===
            self.logger.info(f"=== 第1步：重新获取认证信息 ===")
            self.logger.info(f"根据PHP版本的逻辑，每次API调用前都需要重新获取认证")
            
            # 1. 重新握手
            self.logger.info(f"1.1 重新握手验证...")
            handshake_result = await self._handshake(session_data)
            if not handshake_result.get('status') == 'success':
                self.logger.error(f"重新握手失败: {handshake_result['message']}")
                raise NewApiError('20301', f'Re-handshake failed: {handshake_result["message"]}')
            self.logger.info(f"重新握手成功！")
            
            # 2. 重新获取认证令牌
            self.logger.info(f"1.2 重新获取认证令牌...")
            auth_result = await self._get_auth_token(session_data)
            if not auth_result.get('status') == 'success':
                self.logger.error(f"重新认证失败: {auth_result['message']}")
                raise NewApiError('20302', f'Re-authentication failed: {auth_result["message"]}')
            self.logger.info(f"重新获取认证令牌成功！")
            self.logger.info(f"新的Authorization: {session_data.get('authorization', '')[:50]}...")

            # 调用Indus API验证PIN
            self.logger.info(f"=== 开始调用银行API验证PIN ===")
            self.logger.info(f"API端点: {self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['verify_pin']}")
            self.logger.info(f"PIN码: ****(已隐藏)")
            
            pin_result = await self._verify_pin_with_indus(session_data, pin_code)
            if not pin_result.get('status') == 'success':
                return pin_result

            # 提取virtualAddress信息
            self.logger.info(f"=== 处理PIN验证返回的virtualAddress信息 ===")
            pin_data = pin_result.get('data', {})
            virtual_addresses = pin_data.get('virtual_addresses', [])
            
            self.logger.info(f"从PIN验证结果中提取到 {len(virtual_addresses)} 个virtualAddress:")
            for i, va in enumerate(virtual_addresses):
                self.logger.info(f"   {i+1}. {va.get('virtualAddress')} (来源: {va.get('source')})")
            
            # 整理virtualAddress列表，返回给前端 - 只返回virtualAddress字符串
            formatted_virtual_addresses = []
            for va in virtual_addresses:
                virtual_address = va.get('virtualAddress')
                if virtual_address and virtual_address not in formatted_virtual_addresses:
                    formatted_virtual_addresses.append(virtual_address)
            
            self.logger.info(f"去重后返回给前端的virtualAddress列表: {formatted_virtual_addresses}")
            self.logger.info(f"同时更新session_data中的upi_list: {formatted_virtual_addresses}")
                
            # 保存virtualAddress信息到会话中（保留详细信息用于内部处理）
            additional_data = {
                'pin_verification_data': pin_data,
                'available_virtual_addresses_detailed': virtual_addresses,  # 详细信息
                'available_virtual_addresses': formatted_virtual_addresses,  # 简化的字符串列表
                'upi_list': formatted_virtual_addresses  # 同时更新upi_list，保持与available_virtual_addresses一致
            }

            # 更新状态
            self.logger.info(f"正在更新会话状态...")
            await self._update_session_status(
                redis_key, session_data, LoginStatus.VERIFY_PIN, additional_data
            )

            self.logger.info(f"会话状态更新成功！")
            self.logger.info(f"=== IndusBank PIN验证完全成功！===")
            
            # 根据是否找到virtualAddress决定下一步
            if formatted_virtual_addresses:
                self.logger.info(f"找到 {len(formatted_virtual_addresses)} 个virtualAddress，可以直接选择UPI")
                self.logger.info(f"下一步: 前端可以调用 set_upi_http 选择具体的virtualAddress")
                next_step_message = f"PIN验证成功，找到 {len(formatted_virtual_addresses)} 个UPI账户"
                next_status = "select_upi"
            else:
                self.logger.info(f"未找到virtualAddress，需要调用 get_upi_list_http 获取完整账单列表")
                next_step_message = "PIN验证成功，未找到UPI"

            self.logger.info(f"=== IndusBank验证PIN完成 ===")

            return {
                'status': 'success',
                'message': next_step_message,
                'data': {
                    'next_status': next_status,
                    'virtual_addresses': formatted_virtual_addresses,
                    'virtual_address_count': len(formatted_virtual_addresses),
                    'has_virtual_addresses': len(formatted_virtual_addresses) > 0
                }
            }

        except Exception as e:
            self.logger.error(f"验证PIN失败: {str(e)}")
            raise NewApiError('20309', f'PIN verification failed: {str(e)}')

    async def set_upi_http(self, data):
        """设置UPI接口 - HttpLogin.py兼容版本"""
        payment_lock_id = None
        payment_lock_value = None
        
        try:
            self.logger.info(f"[START] === IndusBank设置UPI开始 === [START]")
            self.logger.info(f"[INPUT] 接收到UPI设置请求: {data}")
            
            # 获取payment_id用于锁控制
            payment_id = data.get('payment_id')
            if not payment_id:
                raise NewApiError('20001', 'Missing payment_id parameter')
            
            # [LOCK] 获取基于payment_id的接口锁
            try:
                lock_result = await self._get_payment_interface_lock(payment_id, 'set_upi')
                # 保存锁信息用于finally块释放
                payment_lock_id = lock_result.get('lock_id')
                payment_lock_value = lock_result.get('lock_value')
            except NewApiError as lock_error:
                self.logger.warning(f"IndusBank设置UPI接口锁限制: {lock_error.message}")
                raise lock_error
            
            # 验证必要参数
            required_fields = ['bankname', 'payment_id', 'selected_upi']
            if not all(field in data for field in required_fields):
                missing_fields = [field for field in required_fields if field not in data]
                self.logger.error(f"[ERROR] IndusBank设置UPI参数验证失败: 缺少必要参数 {required_fields}")
                raise NewApiError('20001', f"Missing required parameters: {', '.join(missing_fields)}")
            
            bankname = data['bankname']
            payment_id = data['payment_id']
            selected_upi = data['selected_upi']
            redis_key = f"pre_login_{bankname}_{payment_id}"
            
            self.logger.info(f"[SUCCESS] 参数验证通过！")
            self.logger.info(f"[DATA] 处理参数: bankname={bankname}, payment_id={payment_id}, selected_upi={selected_upi}")
            self.logger.info(f"[KEY] Redis键: {redis_key}")
            
            # 验证会话状态
            session_data = await self._get_session_data(redis_key)
            if not session_data:
                raise NewApiError('20201', 'IndusBank session does not exist or has expired, please start login again')
            
            # 检查登录锁状态
            phone = session_data.get('phone')
            session_payment_id = session_data.get('id')
            session_bankname = session_data.get('bankname')
            if session_payment_id and await self.redis.get(self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=session_bankname, payment_id=session_payment_id)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            if phone and await self.redis.get(self.LOGIN_LOCK_PHONE_KEY.format(bankname=session_bankname, phone=phone)):
                raise NewApiError('20101', f'Account is in login process, please try again later')
            
            # 验证状态转换 - 支持从 verify_pin_http 或 get_upi_list_http 过来
            current_status = session_data.get('status')
            self.logger.info(f"[INFO] 当前会话状态: {current_status}")
            
            valid_previous_statuses = [LoginStatus.VERIFY_PIN, LoginStatus.GET_PAYLIST]
            if current_status not in valid_previous_statuses:
                self.logger.error(f"[ERROR] 状态转换无效！")
                self.logger.error(f"   当前状态: {current_status}")
                self.logger.error(f"   有效的前置状态: {valid_previous_statuses}")
                self.logger.error(f"[INFO] 请先完成以下步骤之一：")
                self.logger.error(f"   - verify_pin_http (验证PIN)")
                self.logger.error(f"   - get_upi_list_http (获取UPI列表)")
                raise NewApiError('20102', 'Invalid status transition, please complete PIN verification or UPI list retrieval first')
            
            # [INFO] 检查UPI来源并验证
            available_virtual_addresses = session_data.get('available_virtual_addresses', [])
            upi_list = session_data.get('upi_list', [])
            
            self.logger.info(f"[INFO] === UPI来源检查 ===")
            self.logger.info(f"[DATA] PIN验证获取的virtualAddress: {available_virtual_addresses}")
            self.logger.info(f"[DATA] get_upi_list获取的UPI列表: {len(upi_list)} 个")
            
            # 支持两种流程：
            # 1. verify_pin_http → set_upi_http (使用available_virtual_addresses)
    
            if available_virtual_addresses:
                # 流程1：直接从PIN验证结果中选择
                self.logger.info(f"[SUCCESS] 使用PIN验证获取的virtualAddress列表 ({len(available_virtual_addresses)} 个)")
                if selected_upi not in available_virtual_addresses:
                    self.logger.error(f"[ERROR] 选择的UPI无效: {selected_upi}")
                    self.logger.error(f"[INFO] 可用的virtualAddress: {available_virtual_addresses}")
                    raise NewApiError('20501', f'Selected UPI is invalid: {selected_upi}')
                
                self.logger.info(f"[SUCCESS] UPI验证通过：{selected_upi}")
                
            elif session_data.get('upi_list_fetched') and upi_list:
                # 流程2：从完整UPI列表中选择
                self.logger.info(f"[SUCCESS] 使用get_upi_list获取的完整UPI列表 ({len(upi_list)} 个)")
                valid_upi = any(
                    upi.get('virtual_address') == selected_upi or 
                    upi.get('upi') == selected_upi 
                    for upi in upi_list
                )
                if not valid_upi:
                    self.logger.error(f"[ERROR] 选择的UPI无效: {selected_upi}")
                    self.logger.error(f"[INFO] 可用的UPI列表: {[upi.get('virtual_address', upi.get('upi', '')) for upi in upi_list]}")
                    raise NewApiError('20501', f'Selected UPI is invalid: {selected_upi}')
                
                self.logger.info(f"[SUCCESS] UPI验证通过：{selected_upi}")
                
            else:
                # 两种流程都没有完成
                self.logger.error(f"[ERROR] 未找到UPI数据源")
                self.logger.error(f"[INFO] 请先调用以下接口之一：")
                self.logger.error(f"   - verify_pin_http (如果能获取到virtualAddress)")
                self.logger.error(f"   - get_upi_list_http (获取完整UPI列表)")
                raise NewApiError('20501', 'Please get UPI list or verify PIN first')
            
            # 写入payment数据库
            self.logger.info(f"[DB] === 开始保存payment到数据库 ===")
            # 获取前端传递的name参数
            name = data.get('name')
            if name:
                self.logger.info(f"[DB] 前端传递的name参数: {name}")
            else:
                self.logger.info(f"[DB] 前端未传递name参数或name为空")
            
            real_payment_id = await self._save_payment_to_database(session_data, selected_upi, name)
            
            if real_payment_id:
                # 建立登录进程锁 - 防止5分钟内重复登录
                phone = session_data.get('phone', '')
                bankname = session_data.get('bankname', 'indus')
                
                # 1. 手机号锁 - 防止用户用手机号重复登录
                login_on_phone_key = self.LOGIN_LOCK_PHONE_KEY.format(bankname=bankname, phone=phone)
                await self.redis.setex(login_on_phone_key, 600, 1)  # 10分钟
                
                # 2. Payment ID锁 - 防止用户用payment_id重复登录
                login_on_payment_key = self.LOGIN_LOCK_PAYMENT_KEY.format(bankname=bankname, payment_id=real_payment_id)
                await self.redis.setex(login_on_payment_key, 600, 1)  # 10分钟
                
                self.logger.info(f"[LOCK] 已建立登录进程锁:")
                self.logger.info(f"[LOCK]   - 手机号锁: {login_on_phone_key} (10分钟)")
                self.logger.info(f"[LOCK]   - Payment锁: {login_on_payment_key} (10分钟)")
                
                # 更新状态为登录成功
                await self._update_session_status(
                    redis_key, session_data, LoginStatus.LOGIN_SUCCESSFUL,
                    {
                        'real_payment_id': real_payment_id,
                        'selected_upi': selected_upi,
                        'completion_time': int(time.time())
                    }
                )
                
                self.logger.info(f"[SUCCESS] IndusBank登录流程完成！")
                self.logger.info(f"[STATS] 银行: {bankname}")
                self.logger.info(f"[STATS] Payment ID: {payment_id} → 数据库ID: {real_payment_id}")
                self.logger.info(f"[STATS] 选择的UPI: {selected_upi}")
                self.logger.info(f"[END] === IndusBank设置UPI完成 === [END]")
                
                return {
                    'status': 'success',
                    'message': 'IndusBank登录成功',
                    'data': {
                        'id': real_payment_id,
                        'selected_upi': selected_upi
                    }
                }
            else:
                raise NewApiError('20601', 'Database write failed, please retry')
                
        except Exception as e:
            self.logger.error(f"[EXCEPTION] IndusBank设置UPI异常: {str(e)}")
            import traceback
            self.logger.error(f"[STACK] 异常堆栈: {traceback.format_exc()}")
            raise NewApiError('20309', f'UPI setup failed: {str(e)}')
        finally:
            # [UNLOCK] 释放payment接口锁
            if payment_lock_id and payment_lock_value:
                await self._release_payment_interface_lock(payment_lock_id, payment_lock_value)
                self.logger.info(f"IndusBank设置UPI释放payment锁: id={payment_lock_id}")

    # ================== 内部辅助方法 ==================
    async def _handshake(self, session_data):
        """执行握手验证"""
        try:
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['handshake']}"
            
            # 构建请求数据
            request_data = {
                "pspId": "10001",
                "requestMsg": self._build_handshake_request(session_data)
            }

            headers = self._get_standard_headers(session_data)
            
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            # 使用 retry_make_request 方法（从 jio_bank.py 拷贝）
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=json.dumps(request_data),
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            
            if not response or response.status_code != 200:
                raise NewApiError('20301', 'Handshake request failed')

            # 解析响应 - 需要解密
            try:
                response_data = response.json() if response.text else {}
            except:
                response_data = response.text
                
            decoded_response = self._decode_indus_response(response_data)
            if decoded_response.get('status') == 'S':
                session_data['client_secret'] = decoded_response.get('clientSecret')
                session_data['play_integrity_nonce'] = decoded_response.get('play_integrity_nonce')
                session_data['enablePlayIntegrity'] = decoded_response.get('enablePlayIntegrity')
                return {
                    'status': 'success',
                    'message': '握手成功'
                }
            else:
                raise NewApiError('20301', f"Handshake failed: {decoded_response.get('statusDesc', 'Unknown error')}")

        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f"握手验证失败: {str(e)}")
            raise NewApiError('20301')

    async def _get_auth_token(self, session_data):
        """获取认证令牌"""
        try:
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['auth_token']}"
            
            # 构建请求数据
            request_data = "password=05003060310b30090603550406130239&grant_type=password&client_secret=indusupiapp&client_id=indusupiapp&username=10001&"

            headers = self._get_standard_headers(session_data)
            headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=request_data,
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            if not response or response.status_code != 200:
                raise NewApiError('20302')

            # 解析响应
            response_data = response.json() if response.text else {}
            if response_data.get('access_token'):
                authorization = f"{response_data.get('token_type', 'bearer')} {response_data.get('access_token')}"
                session_data['authorization'] = authorization
                return {
                    'status': 'success',
                    'message': '获取认证令牌成功'
                }
            else:
                raise NewApiError('20302', 'Invalid authentication token response format')

        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f"获取认证令牌失败: {str(e)}")
            raise NewApiError('20302', f'Get authentication token failed: {str(e)}')

    async def _check_device_web1(self, session_data):
        """第一次设备检查"""
        try:
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['check_device1']}"
            
            # 构建请求数据
            request_data = {
                "check_root_detection": False,
                "requestMsg": self._build_device_check_request(session_data),
                "pspId": "10001",
                "device_integrity_data": json.dumps({
                    "appVersionCode": 59,
                    "check_root_detection": False,
                    "isMerchant": False,
                    "merchCustFlag": False,
                    "recoveryOptionFlag": 0,
                    "sendRegSms": False,
                    "updateFlag": 0
                })
            }

            headers = self._get_standard_headers(session_data)
            headers['Authorization'] = session_data.get('authorization')
            
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=json.dumps(request_data),
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            if not response or response.status_code != 200:
                raise NewApiError('20303', 'Device check request failed')

            # 解析响应并提取短信信息
            response_data = self._decode_indus_response(response.json() if response.text else {})
            
            self.logger.info(f"[INFO] 第一次设备检查响应解析:")
            self.logger.info(f"   完整解密数据: {response_data}")
            
            if response_data.get('status') == 'S':
                # 提取短信网关信息
                sms_number = response_data.get('smsGateWayNo')
                sms_gateway_content = response_data.get('smsGateWayContent')
                sms_gateway_key = response_data.get('smsGateWayKey')
                
                # 保存到session
                session_data['sms_number'] = sms_number
                session_data['sms_gateway_content'] = sms_gateway_content
                session_data['sms_gateway_key'] = sms_gateway_key
                
                self.logger.info(f"[SUCCESS] 设备检查成功，获取到短信网关信息:")
                self.logger.info(f"   smsGateWayNo: '{sms_number}'")
                self.logger.info(f"   smsGateWayContent: '{sms_gateway_content}'")
                self.logger.info(f"   smsGateWayKey: '{sms_gateway_key}'")
                
                # 验证关键字段
                if not sms_gateway_content:
                    self.logger.warning(f"⚠️ 警告：smsGateWayContent为空！这可能导致后续步骤失败")
                if not sms_number:
                    self.logger.warning(f"⚠️ 警告：smsGateWayNo为空！这可能导致后续步骤失败")
                
                return {
                    'status': 'success',
                    'message': '设备检查成功'
                }
            else:
                raise NewApiError('20303', f"Device check failed: {response_data.get('statusDesc', 'Unknown error')}")

        except NewApiError:
            raise
        except Exception as e:
            self.logger.error(f"设备检查失败: {str(e)}")
            raise NewApiError('20303', f'Device check failed: {str(e)}')

    async def _generate_sms_content(self, session_data):
        """生成短信内容"""
        try:
            self.logger.info("开始生成短信内容...")
            
            # 使用session中保存的app_gen_id，不再重新生成
            app_gen_id = session_data.get('app_gen_id')
            if not app_gen_id:
                self.logger.error("session中缺少app_gen_id")
                raise NewApiError('20304', 'Missing app_gen_id in session')
            
            self.logger.info(f"获取到app_gen_id: {app_gen_id}")
            
            # 获取网关内容
            gateway_content = session_data.get('sms_gateway_content', '')
            phone = session_data.get('phone', '').replace('+', '')
            
            self.logger.info(f"[INFO] 检查短信参数:")
            self.logger.info(f"   gateway_content='{gateway_content}'")
            self.logger.info(f"   phone={phone}")
            
            # [ERROR] 绝不使用默认值！短信内容必须基于银行真实数据
            if not gateway_content:
                self.logger.error("[CRITICAL ERROR] 致命错误：没有从银行获取到 smsGateWayContent！")
                self.logger.error("[INFO] 这说明设备检查步骤失败，无法继续")
                self.logger.error("[INFO] smsGateWayContent 必须从银行服务器的 checkDeviceIdWeb1 API 获取")
                raise NewApiError('20304', 'Device check failed: Bank SMS gateway content not received, please restart login process')
            
            self.logger.info(f"[SUCCESS] 使用银行返回的真实网关内容: '{gateway_content}'")
            
            # 设置当前会话数据供_build_sms_content使用
            self._current_session_data = session_data
            
            # 构建短信内容
            self.logger.info("[START] 开始构建短信内容...")
            try:
                sms_content = self._build_sms_content(gateway_content, phone, app_gen_id)
                self.logger.info(f"[SUCCESS] 短信内容构建完成，长度: {len(sms_content)}")
            except Exception as build_error:
                self.logger.error(f"[ERROR] 短信内容构建失败: {str(build_error)}")
                raise NewApiError('20304', f'SMS content build failed: {str(build_error)}')
            
            # 获取短信号码（应该从设备检查响应中获取，不是固定值）
            sms_number = session_data.get('sms_number', '')
            if not sms_number:
                self.logger.error("session中缺少sms_number，这应该在设备检查中获取")
                raise NewApiError('20304', 'Missing SMS number information in session')
            
            # 保存到session_data的顶层和bank_specific_data中
            session_data['sms_content'] = sms_content
            session_data['sms_number'] = sms_number
            
            # 初始化bank_specific_data如果不存在
            if 'bank_specific_data' not in session_data:
                session_data['bank_specific_data'] = {}
            
            # 更新bank_specific_data
            session_data['bank_specific_data'].update({
                'sms_content': sms_content,
                'sms_number': sms_number
            })
            
            self.logger.info(f"短信配置生成成功: 号码={sms_number}, 内容长度={len(sms_content)}")
            self.logger.info(f"短信内容预览: {sms_content[:100]}...")
            
            return {
                'status': 'success',
                'message': '短信内容生成成功'
            }

        except Exception as e:
            self.logger.error(f"生成短信内容失败: {str(e)}")
            import traceback
            self.logger.error(f"错误堆栈: {traceback.format_exc()}")
            raise NewApiError('20304', f'Generate SMS content failed: {str(e)}')

    async def _check_device_web2(self, session_data):
        """第二次设备检查，验证短信是否发送成功"""
        try:
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['check_device2']}"
            
            # 构建请求数据
            request_data = {
                "check_root_detection": False,
                "requestMsg": self._build_device_check2_request(session_data),
                "pspId": "10001"
            }

            headers = self._get_standard_headers(session_data)
            headers['Authorization'] = session_data.get('authorization')
            
            self.logger.info(f"=== IndusBank第二次设备检查开始 ===")
            self.logger.info(f"请求URL: {url}")
            self.logger.info(f"请求头: {headers}")
            
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=json.dumps(request_data),
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            if not response or response.status_code != 200:
                error_msg = f"第二次设备检查请求失败: HTTP {response.status_code if response else 'None'}"
                self.logger.error(error_msg)
                raise NewApiError('20305', 'Second device check request failed')

            # 详细记录原始响应
            raw_response = response.json() if response.text else {}
            self.logger.info(f"原始响应数据: {raw_response}")
            
            # 解析响应
            try:
                response_data = self._decode_indus_response(raw_response)
                self.logger.info(f"解密后响应数据: {response_data}")
                
                # 提取关键字段
                status = response_data.get('status', 'NULL')
                reVerify = response_data.get('reVerify', 'NULL') 
                userMsg = response_data.get('userMsg', '')
                deviceStatus = response_data.get('deviceStatus', '')
                statusDesc = response_data.get('statusDesc', '')
                
                self.logger.info(f"关键字段解析:")
                self.logger.info(f"  status: {status}")
                self.logger.info(f"  reVerify: {reVerify}")
                self.logger.info(f"  userMsg: {userMsg}")
                self.logger.info(f"  deviceStatus: {deviceStatus}")
                self.logger.info(f"  statusDesc: {statusDesc}")
                
                # 根据PHP版本的逻辑判断：reVerify必须为"Y"才表示成功
                if reVerify == "Y":
                    self.logger.info(f"[SUCCESS] 第二次设备检查成功: reVerify={reVerify}")
                    return {
                        'status': 'success',
                        'message': 'SMS verification successful, ready for OTP process'
                    }
                else:
                    error_message = userMsg if userMsg else (statusDesc if statusDesc else 'SMS verification failed')
                    self.logger.error(f"[ERROR] 第二次设备检查失败: reVerify={reVerify}, 错误: {error_message}")
                    raise NewApiError('20305', f"{statusDesc}")
                    
            except Exception as decode_error:
                self.logger.error(f"解码响应失败: {str(decode_error)}")
                self.logger.error(f"原始响应: {raw_response}")
                raise NewApiError('20305', f'Response decode failed: {str(decode_error)}')

        except Exception as e:
            self.logger.error(f"第二次设备检查异常: {str(e)}")
            import traceback
            self.logger.error(f"异常堆栈: {traceback.format_exc()}")
            raise NewApiError('20305', f'Second device check failed: {str(e)}')

    async def _send_otp_to_indus(self, session_data):
        """向Indus发送OTP请求"""
        try:
            self.logger.info(f"=== 开始构建OTP请求 ===")
            
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['send_otp']}"
            self.logger.info(f"请求URL: {url}")
            
            # 构建请求数据
            self.logger.info(f"[HTTP] 正在构建请求消息...")
            request_msg = self._build_send_otp_request(session_data)
            self.logger.info(f"[DATA] 请求消息长度: {len(request_msg)} 字符")
            self.logger.info(f"[DATA] 请求消息预览: {request_msg[:100]}...")
            
            request_data = {
                "pspId": "10001",
                "requestMsg": request_msg
            }
            self.logger.info(f"[DATA] 完整请求数据: {request_data}")

            # 构建请求头
            headers = self._get_standard_headers(session_data)
            authorization = session_data.get('authorization')
            headers['Authorization'] = authorization
            
            self.logger.info(f"[HEADERS] 请求头信息:")
            for key, value in headers.items():
                if key == 'Authorization':
                    preview = value[:50] + "..." if len(value) > 50 else value
                    self.logger.info(f"   {key}: {preview}")
                else:
                    self.logger.info(f"   {key}: {value}")
            
            self.logger.info(f"[HTTP] 正在发送HTTP POST请求...")
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=json.dumps(request_data),
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            
            self.logger.info(f"[RESPONSE] === HTTP响应信息 ===")
            if not response:
                self.logger.error(f"[ERROR] HTTP响应为空!")
                raise NewApiError('20305', 'HTTP response is empty')
            
            status_code = response.status_code
            self.logger.info(f"[STATS] HTTP状态码: {status_code}")
            
            if status_code != 200:
                self.logger.error(f"[ERROR] HTTP状态码错误: {status_code}")
                raise NewApiError('20305', 'HTTP request failed')
            
            self.logger.info(f"[SUCCESS] HTTP请求成功!")

            # 解析响应
            self.logger.info(f"[RESPONSE] === 开始解析响应数据 ===")
            raw_response_data = response.json() if response.text else {}
            self.logger.info(f"[DATA] 原始响应数据: {raw_response_data}")
            
            response_data = self._decode_indus_response(raw_response_data)
            self.logger.info(f"[DECRYPTED] 解码后响应数据: {response_data}")
            
            if not response_data:
                self.logger.error(f"[ERROR] 响应数据解码失败!")
                raise NewApiError('20305', 'Response data decode failed')
            
            # 分析响应状态
            status = response_data.get('status')
            status_desc = response_data.get('statusDesc', '无状态描述')
            
            self.logger.info(f"[RESPONSE] === 银行响应状态分析 ===")
            self.logger.info(f"[STATS] status: {status}")
            self.logger.info(f"[STATS] statusDesc: {status_desc}")
            
            if status == 'S':
                self.logger.info(f"[SUCCESS] 银行API返回成功状态!")
                self.logger.info(f"[INFO] OTP短信应该已发送到用户手机")
                return {
                    'status': 'success',
                    'message': 'OTP发送成功'
                }
            else:
                self.logger.error(f"[ERROR] 银行API返回失败状态!")
                self.logger.error(f"[ERROR] 状态: {status}")
                self.logger.error(f"[ERROR] 描述: {status_desc}")
                raise NewApiError('20306', f"OTP sending failed: {response_data.get('statusDesc', 'Unknown error')}")


        except Exception as e:
            self.logger.error(f"[EXCEPTION] === _send_otp_to_indus 异常 ===")
            self.logger.error(f"[ERROR] 异常类型: {type(e).__name__}")
            self.logger.error(f"[ERROR] 异常信息: {str(e)}")
            import traceback
            self.logger.error(f"[STACK] 异常堆栈:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.error(f"   {line}")
            raise NewApiError('20306', f'OTP sending failed: {str(e)}')

    async def _verify_otp_with_indus(self, session_data, otp_code):
        """向Indus验证OTP"""
        try:
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['verify_otp']}"
            
            # 构建请求数据
            request_data = {
                "pspId": "10001",
                "requestMsg": self._build_verify_otp_request(session_data, otp_code)
            }

            headers = self._get_standard_headers(session_data)
            headers['Authorization'] = session_data.get('authorization')
            
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=json.dumps(request_data),
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            if not response or response.status_code != 200:
                raise NewApiError('20307', 'OTP verification request failed')


            # 解析响应
            response_data = self._decode_indus_response(response.json() if response.text else {})
            if response_data.get('status') == 'S':
                serv_gen_id = response_data.get('deviceInfo', {}).get('servGenId')
                if serv_gen_id:
                    return {
                        'status': 'success',
                        'message': 'OTP验证成功',
                        'data': {'serv_gen_id': serv_gen_id}
                    }
                else:
                                        raise NewApiError('20307', f"OTP verification successful but servGenId not obtained")

            else:
                error_code = response_data.get('errCode', '')
                error_msg = self.INDUS_ERROR_CODES.get(error_code, response_data.get('statusDesc', '未知错误'))
                raise NewApiError('20307', f"OTP verification failed: {response_data.get('statusDesc', 'Unknown error')}")


        except Exception as e:
            self.logger.error(f"[ERROR] 验证OTP失败: {str(e)}")
            raise NewApiError('20307', f'OTP verification failed: {str(e)}')

    async def _verify_pin_with_indus(self, session_data, pin_code):
        """向Indus验证PIN码"""
        try:
            self.logger.info(f"[REQUEST] === IndusBank PIN验证报文详情 ===")
            
            url = f"{self.API_ENDPOINTS['base_url']}{self.API_ENDPOINTS['verify_pin']}"
            self.logger.info(f"[URL] 请求URL: {url}")
            
            # 构建请求数据 - 保持原有逻辑
            encrypted_request_msg = self._build_verify_pin_request(session_data, pin_code)
            request_data = {
                "pspId": "10001",
                "requestMsg": encrypted_request_msg
            }
            
            # 打印请求明文（通过解密刚生成的加密数据）
            self.logger.info(f"[REQUEST] === PIN验证请求明文数据 ===")
            try:
                decrypted_request = self.decode_message(encrypted_request_msg)
                self.logger.info(f"[DATA] 请求明文JSON:")
                import json
                request_json = json.loads(decrypted_request)
                self.logger.info(f"{json.dumps(request_json, ensure_ascii=False, indent=2)}")
            except Exception as decrypt_error:
                self.logger.warning(f"[WARN] 解密请求数据用于显示失败: {decrypt_error}")
            
            self.logger.info(f"[ENCRYPTED] 加密后的请求消息:")
            self.logger.info(f"[DATA] 长度: {len(encrypted_request_msg)} 字符")
            self.logger.info(f"[DATA] 内容: {encrypted_request_msg}")
            
            self.logger.info(f"[REQUEST] 完整HTTP请求数据:")
            self.logger.info(f"{json.dumps(request_data, ensure_ascii=False, indent=2)}")

            headers = self._get_standard_headers(session_data)
            headers['Authorization'] = session_data.get('authorization')
            
            self.logger.info(f"[HEADERS] 请求头信息:")
            for key, value in headers.items():
                if key == 'Authorization':
                    preview = value[:50] + "..." if len(value) > 50 else value
                    self.logger.info(f"   {key}: {preview}")
                else:
                    self.logger.info(f"   {key}: {value}")
            
            # 发送HTTP请求
            self.logger.info(f"[HTTP] 正在发送HTTP请求...")
            # 获取代理配置
            proxies = await self._get_proxy_for_request(session_data)
            
            response = self.retry_make_request(
                method='POST',
                url=url,
                headers=headers,
                data=json.dumps(request_data),
                proxies=proxies
            )
            
            # 记录响应的详细信息
            self.log_response(response)
            
            if not response or response.status_code != 200:
                self.logger.error(f"[ERROR] HTTP请求失败: {response}")
                raise NewApiError('20308', 'PIN verification request failed')


            # [INFO] 解析并打印返回明文
            self.logger.info(f"[RESPONSE] === 银行返回数据解析 ===")
            raw_response_data = response.json() if response.text else {}
            self.logger.info(f"[DATA] 原始返回数据: {raw_response_data}")
            
            response_data = self._decode_indus_response(raw_response_data)
            self.logger.info(f"[DECRYPTED] === 解密后返回明文数据 ===")
            self.logger.info(f"{json.dumps(response_data, ensure_ascii=False, indent=2)}")
            
            # 分析返回结果
            status = response_data.get('status')
            status_desc = response_data.get('statusDesc', '无状态描述')
            user_msg = response_data.get('userMsg', '')
            
            self.logger.info(f"[STATS] 关键字段解析:")
            self.logger.info(f"   [STATS] status: {status}")
            self.logger.info(f"   [DATA] statusDesc: {status_desc}")
            self.logger.info(f"   [MSG] userMsg: {user_msg}")
            
            if status == 'S':
                self.logger.info(f"[SUCCESS] PIN验证成功!")
                
                # [INFO] 提取virtualAddress信息
                self.logger.info(f"[INFO] === 提取virtualAddress信息 ===")
                virtual_addresses = []
                
                # 检查可能包含virtualAddress的字段
                vpa_account_details = response_data.get('vpaAccountDetails', [])
                customer_details = response_data.get('customerDetails', {})
                account_info = response_data.get('accountInfo', [])
                
                self.logger.info(f"[STATS] 银行返回数据结构分析:")
                self.logger.info(f"   vpaAccountDetails: {len(vpa_account_details) if isinstance(vpa_account_details, list) else 'Not a list'}")
                self.logger.info(f"   customerDetails: {'存在' if customer_details else '不存在'}")
                self.logger.info(f"   accountInfo: {len(account_info) if isinstance(account_info, list) else 'Not a list'}")
                
                # 方法1: 从vpaAccountDetails提取
                if isinstance(vpa_account_details, list):
                    for vpa_detail in vpa_account_details:
                        if isinstance(vpa_detail, dict):
                            virtual_address = vpa_detail.get('virtualAddress')
                            if virtual_address:
                                virtual_addresses.append({
                                    'virtualAddress': virtual_address,
                                    'source': 'vpaAccountDetails',
                                    'accountInfo': vpa_detail.get('accountInfo', []),
                                    'details': vpa_detail
                                })
                                self.logger.info(f"   [INFO] 找到virtualAddress: {virtual_address}")
                
                # 方法2: 从customerDetails提取
                if isinstance(customer_details, dict):
                    customer_virtual_address = customer_details.get('virtualAddress')
                    if customer_virtual_address:
                        virtual_addresses.append({
                            'virtualAddress': customer_virtual_address,
                            'source': 'customerDetails',
                            'details': customer_details
                        })
                        self.logger.info(f"   [INFO] 从customerDetails找到virtualAddress: {customer_virtual_address}")
                
                # 方法3: 从accountInfo提取
                if isinstance(account_info, list):
                    for account in account_info:
                        if isinstance(account, dict):
                            account_virtual_address = account.get('virtualAddress')
                            if account_virtual_address:
                                virtual_addresses.append({
                                    'virtualAddress': account_virtual_address,
                                    'source': 'accountInfo',
                                    'details': account
                                })
                                self.logger.info(f"   [INFO] 从accountInfo找到virtualAddress: {account_virtual_address}")
                
                # 方法4: 递归搜索所有可能的字段
                def find_virtual_addresses_recursive(data, path=""):
                    """递归搜索所有virtualAddress字段"""
                    found = []
                    if isinstance(data, dict):
                        for key, value in data.items():
                            current_path = f"{path}.{key}" if path else key
                            if key.lower() in ['virtualaddress', 'virtual_address', 'vpa', 'upiid']:
                                if value and isinstance(value, str):
                                    found.append({
                                        'virtualAddress': value,
                                        'source': current_path,
                                        'details': {'field': key, 'value': value}
                                    })
                                    self.logger.info(f"   [INFO] 递归搜索找到virtualAddress: {value} (路径: {current_path})")
                            else:
                                found.extend(find_virtual_addresses_recursive(value, current_path))
                    elif isinstance(data, list):
                        for i, item in enumerate(data):
                            current_path = f"{path}[{i}]" if path else f"[{i}]"
                            found.extend(find_virtual_addresses_recursive(item, current_path))
                    return found
                
                # 执行递归搜索
                recursive_results = find_virtual_addresses_recursive(response_data)
                for result in recursive_results:
                    # 避免重复添加
                    if not any(va['virtualAddress'] == result['virtualAddress'] for va in virtual_addresses):
                        virtual_addresses.append(result)
                
                self.logger.info(f"[SUMMARY] 总共找到 {len(virtual_addresses)} 个virtualAddress:")
                for i, va in enumerate(virtual_addresses):
                    self.logger.info(f"   {i+1}. {va['virtualAddress']} (来源: {va['source']})")
                
                self.logger.info(f"[END] === IndusBank PIN验证报文详情完成 === [END]")
                return {
                    'status': 'success',
                    'message': 'PIN验证成功',
                    'data': {
                        'raw_response': response_data,  # 完整的银行返回数据
                        'virtual_addresses': virtual_addresses  # 提取的virtualAddress列表
                    }
                }
            else:
                self.logger.error(f"[ERROR] PIN验证失败!")
                self.logger.error(f"[ERROR] 失败原因: {status_desc}")
                self.logger.info(f"[END] === IndusBank PIN验证报文详情完成 === [END]")
                raise NewApiError('20308', f"PIN verification failed: {response_data.get('statusDesc', 'Unknown error')}")


        except Exception as e:
            self.logger.error(f"[EXCEPTION] PIN验证异常: {str(e)}")
            import traceback
            self.logger.error(f"[STACK] 异常堆栈: {traceback.format_exc()}")
            raise NewApiError('20308', f'PIN verification failed: {str(e)}')

    # ================== 请求构建方法 ==================
    def _build_handshake_request(self, session_data):
        """构建握手请求消息"""
        # 使用session中保存的固定值
        app_gen_id = session_data.get('app_gen_id')
        android_id = session_data.get('androidId')
        safety_net_id = session_data.get('safetyNetId')
        
        self.logger.info(f"🔧 构建握手请求 - 关键参数:")
        self.logger.info(f"   app_gen_id: {app_gen_id}")
        self.logger.info(f"   android_id: {android_id}")
        self.logger.info(f"   safety_net_id: {safety_net_id}")
        
        request_msg = {
            "appVersionCode": 0,
            "check_root_detection": False,
            "deviceInfo": {
                "androidId": android_id,
                "app_gen_id": app_gen_id,
                "appName": "com.mgs.induspsp",
                "appVersionCode": "59",
                "appVersionName": "3.3.32",
                "bluetoothMac": "00:00:00:00:00:00",
                "capability": "5200000200010004000639292929292",
                "deviceAnalytics": {
                    "androidApiLevel": 33,
                    "androidId": android_id,
                    "androidOSName": "TIRAMISU",
                    "brand": "Redmi",
                    "carrierNameOne": "46001",
                    "carrierNameTwo": "",
                    "locale": "中文",
                    "model": session_data.get('model', '55041234C'),
                    "ramSize": "5.34 GB",
                    "screenDensity": "XXHDPI",
                    "screenSize": "6.1"
                },
                "deviceId": android_id,
                "deviceType": "MOB",
                "fcmToken": session_data.get('fcmToken', "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R"),
                "geoCode": session_data.get('geoCode', '23.556977,116.368093'),
                "ip": "192.168.0.115", 
                "location": session_data.get('location', 'Jie Yang Shi,Guang Dong Sheng,China'),
                "mobileNo": "",
                "os": "Android13",
                "regId": "NA",
                "relayButton": "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU=",
                "safetyNetId": safety_net_id,
                "selectedSimSlot": 0,
                "simId": android_id + "2",
                "wifiMac": "02:00:00:00:00:00"
            },
            "isMerchant": False,
            "merchCustFlag": False,
            "recoveryOptionFlag": 0,
            "requestInfo": {
                "pspId": "10001",
                "pspRefNo": safety_net_id
            },
            "sendRegSms": False,
            "updateFlag": 0
        }
        
        # 构建JSON字符串
        json_string = json.dumps(request_msg)
        self.logger.info(f"🔧 握手请求明文长度: {len(json_string)} 字符")
        
        # 加密处理
        self.logger.info(f"🔐 开始加密握手请求...")
        encrypted_msg = self.encode_message(json_string)
        self.logger.info(f"🔐 加密完成，长度: {len(encrypted_msg)} 字符")
        self.logger.info(f"🔐 加密结果预览: {encrypted_msg[:50]}...")
        
        return encrypted_msg

    def _build_device_check_request(self, session_data):
        """构建设备检查请求消息"""
        # 使用session中保存的固定值
        app_gen_id = session_data.get('app_gen_id')
        android_id = session_data.get('androidId')
        safety_net_id = session_data.get('safetyNetId')
        
        request_msg = {
            "appVersionCode": 0,
            "check_root_detection": False,
            "deviceInfo": {
                "androidId": android_id,
                "app_gen_id": app_gen_id,
                "appName": "com.mgs.induspsp",
                "appVersionCode": "59",
                "appVersionName": "3.3.32",
                "bluetoothMac": "00:00:00:00:00:00",
                "capability": "5200000200010004000639292929292",
                "deviceId": android_id,
                "deviceType": "MOB",
                "fcmToken": session_data.get('fcmToken', "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R"),
                "geoCode": session_data.get('geoCode', '23.556977,116.368093'),
                "ip": "192.168.0.115",
                "location": session_data.get('location', 'Jie Yang Shi,Guang Dong Sheng,China'),
                "mobileNo": "",
                "os": "Android13",
                "regId": "NA",
                "relayButton": "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU=",
                "safetyNetId": safety_net_id,
                "selectedSimSlot": 0,
                "simId": android_id + "2",
                "wifiMac": "02:00:00:00:00:00"
            },
            "isMerchant": False,
            "merchCustFlag": False,
            "recoveryOptionFlag": 0,
            "requestInfo": {
                "pspId": "10001",
                "pspRefNo": safety_net_id
            },
            "sendRegSms": False,
            "updateFlag": 0
        }
        
        return self.encode_message(json.dumps(request_msg))

    def _build_device_check2_request(self, session_data):
        """构建第二次设备检查请求消息"""
        self.logger.info(f"[BUILD] === Python版本 第二次设备检查 请求构建开始 ===")
        
        # 使用session中保存的固定值
        app_gen_id = session_data.get('app_gen_id')
        android_id = session_data.get('androidId')
        safety_net_id = session_data.get('safetyNetId')
        
        self.logger.info(f"[KEY] 构建参数:")
        self.logger.info(f"   app_gen_id: {app_gen_id}")
        self.logger.info(f"   android_id: {android_id}")
        self.logger.info(f"   safety_net_id: {safety_net_id}")
        
        request_msg = {
            "appVersionCode": 0,
            "check_root_detection": False,
            "deviceInfo": {
                "androidId": android_id,
                "app_gen_id": app_gen_id,
                "appName": "com.mgs.induspsp",
                "appVersionCode": "59",
                "appVersionName": "3.3.32",
                "bluetoothMac": "00:00:00:00:00:00",
                "capability": "5200000200010004000639292929292",
                "deviceId": android_id,
                "deviceType": "MOB",
                "fcmToken": session_data.get('fcmToken', "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R"),
                "geoCode": session_data.get('geoCode', '23.556977,116.368093'),
                "ip": "192.168.0.115",
                "location": session_data.get('location', 'Jie Yang Shi,Guang Dong Sheng,China'),
                "mobileNo": "",
                "os": "Android13",
                "regId": "NA",
                "relayButton": "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU=",
                "safetyNetId": safety_net_id,
                "selectedSimSlot": 0,
                "simId": android_id + "2",
                "wifiMac": "02:00:00:00:00:00"
            },
            "isMerchant": False,
            "merchCustFlag": False,
            "recoveryOptionFlag": 0,
            "requestInfo": {
                "pspId": "10001",
                "pspRefNo": safety_net_id
            },
            "sendRegSms": False,
            "updateFlag": 0
        }
        
        self.logger.info(f"[REQUEST] === Python版本 第二次设备检查 请求明文 ===")
        import json
        request_json = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f"[DATA] 明文请求数据 JSON:\n{request_json}")
        
        self.logger.info(f"[ENCRYPT] 开始加密请求消息...")
        encoded_msg = self.encode_message(json.dumps(request_msg))
        self.logger.info(f"[SUCCESS] 请求消息加密完成")
        self.logger.info(f"[DATA] 加密后长度: {len(encoded_msg)} 字符")
        self.logger.info(f"[DATA] 加密后预览: {encoded_msg[:100]}...")
        
        return encoded_msg

    def _build_send_otp_request(self, session_data):
        """构建发送OTP请求消息"""
        self.logger.info(f"🔧 === 开始构建发送OTP请求消息 ===")
        
        # 获取基础参数
        android_id = session_data.get('androidId')
        safety_net_id = session_data.get('safetyNetId')
        phone = session_data.get('phone')
        
        # ⭐⭐⭐ 关键修复：使用从短信内容中提取的app_gen_id ⭐⭐⭐
        # 根据PHP版本逻辑，申请OTP需要使用从短信内容中提取的app_gen_id，不是原始生成的
        sms_content = session_data.get('sms_content', '')
        if sms_content:
            # 从短信内容中提取app_gen_id（短信内容的最后一段）
            sms_parts = sms_content.split('!')
            if len(sms_parts) >= 2:
                extracted_app_gen_id = sms_parts[-1].strip()  # 最后一段
                self.logger.info(f"🎯 从短信内容中提取的app_gen_id: {extracted_app_gen_id}")
                app_gen_id = extracted_app_gen_id
            else:
                self.logger.warning(f"⚠️ 无法从短信内容中提取app_gen_id，使用原始值")
                app_gen_id = session_data.get('app_gen_id')
        else:
            self.logger.warning(f"⚠️ 会话中没有短信内容，使用原始app_gen_id")
            app_gen_id = session_data.get('app_gen_id')
        
        self.logger.info(f"[DATA] 构建请求所需参数:")
        self.logger.info(f"   [PHONE] phone: {phone}")
        self.logger.info(f"   [KEY] app_gen_id (用于OTP): {app_gen_id}")
        self.logger.info(f"   [KEY] 原始app_gen_id: {session_data.get('app_gen_id')}")
        self.logger.info(f"   [DEVICE] android_id: {android_id}")
        self.logger.info(f"   [SECURITY] safety_net_id: {safety_net_id}")
        
        request_msg = {
            "appVersionCode": 0,
            "check_root_detection": False,
            "deviceInfo": {
                "androidId": android_id,
                "app_gen_id": app_gen_id,
                "appName": "com.mgs.induspsp",
                "appVersionCode": "59",
                "appVersionName": "3.3.32",
                "bluetoothMac": "00:00:00:00:00:00",
                "capability": "5200000200010004000639292929292",
                "deviceId": android_id,
                "deviceType": "MOB",
                "fcmToken": session_data.get('fcmToken', "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R"),
                "geoCode": session_data.get('geoCode', '23.556977,116.368093'),
                "ip": "192.168.0.115",
                "location": session_data.get('location', 'Jie Yang Shi,Guang Dong Sheng,China'),
                "mobileNo": phone,
                "os": "Android13",
                "regId": "NA",
                "relayButton": "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU=",
                "safetyNetId": safety_net_id,
                "selectedSimSlot": 0,
                "simId": android_id + "2",
                "wifiMac": "02:00:00:00:00:00"
            },
            "isMerchant": False,
            "merchCustFlag": False,
            "reVerify": "Y",
            "recoveryOptionFlag": 0,
            "requestInfo": {
                "pspId": "10001",
                "pspRefNo": safety_net_id
            },
            "sendRegSms": False,
            "updateFlag": 0
        }
        
        self.logger.info(f"[SUCCESS] 请求消息结构构建完成")
        self.logger.info(f"[DATA] 原始请求消息JSON:")
        import json
        json_str = json.dumps(request_msg, ensure_ascii=False, indent=2)
        self.logger.info(f"{json_str}")
        
        self.logger.info(f"[SECURITY] 开始加密请求消息...")
        encoded_msg = self.encode_message(json_str)
        self.logger.info(f"[SUCCESS] 请求消息加密完成")
        self.logger.info(f"[STATS] 加密后长度: {len(encoded_msg)} 字符")
        self.logger.info(f"[INFO] 加密后预览: {encoded_msg[:100]}...")
        
        return encoded_msg

    def _build_verify_otp_request(self, session_data, otp_code):
        """构建验证OTP请求消息"""
        # 使用session中保存的固定值，参考PHP的verifyOtp方法
        app_gen_id = session_data.get('app_gen_id')
        android_id = session_data.get('androidId')
        safety_net_id = session_data.get('safetyNetId')
        phone = session_data.get('phone')
        
        # 关键修正：在PHP版本中，pspRefNo实际使用的是app_gen_id，不是safety_net_id！
        psp_ref_no = app_gen_id  # 修正：使用app_gen_id作为pspRefNo
        
        # 计算rvh字段：固定前缀 + pspRefNo的SHA256哈希
        import hashlib
        rvh_prefix = "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU="
        psp_ref_no_hash = hashlib.sha256(psp_ref_no.encode()).hexdigest()
        rvh = rvh_prefix + psp_ref_no_hash
        
        # 调试日志
        self.logger.info(f"[SECURITY] === OTP验证请求参数计算 ===")
        self.logger.info(f"[KEY] app_gen_id (pspRefNo): {psp_ref_no}")
        self.logger.info(f"[SECURITY] safety_net_id: {safety_net_id}")
        self.logger.info(f"[SECURITY] psp_ref_no_hash: {psp_ref_no_hash}")
        self.logger.info(f"[DATA] rvh: {rvh}")
        self.logger.info(f"[DATA] otp_code: {otp_code}")
        
        request_msg = {
            "appVersionCode": 0,
            "check_root_detection": False,
            "deviceInfo": {
                "androidId": android_id,
                "app_gen_id": app_gen_id,
                "appName": "com.mgs.induspsp",
                "appVersionCode": "59",
                "appVersionName": "3.3.32",
                "bluetoothMac": "00:00:00:00:00:00",
                "capability": "5200000200010004000639292929292",
                "deviceId": android_id,
                "deviceType": "MOB",
                "fcmToken": session_data.get('fcmToken', "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R"),
                "geoCode": session_data.get('geoCode', '23.556977,116.368093'),
                "ip": "192.168.0.115",
                "location": session_data.get('location', 'Jie Yang Shi,Guang Dong Sheng,China'),
                "mobileNo": phone,
                "os": "Android13",
                "regId": "NA",
                "relayButton": "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU=",
                "safetyNetId": safety_net_id,
                "selectedSimSlot": 0,
                "simId": android_id + "2",
                "wifiMac": "02:00:00:00:00:00"
            },
            "isMerchant": False,
            "merchCustFlag": False,
            "otp": otp_code,  # 修正：使用"otp"而不是"otpValue"
            "recoveryOptionFlag": 0,
            "requestInfo": {
                "pspId": "10001",
                "pspRefNo": psp_ref_no  # 修正：使用app_gen_id作为pspRefNo
            },
            "rvh": rvh,  # 添加关键的rvh字段
            "sendRegSms": False,
            "updateFlag": 0
        }
        
        # 调试：输出完整的请求消息
        request_json = json.dumps(request_msg, indent=2)
        self.logger.info(f"[SECURITY] === 完整OTP验证请求消息 ===")
        self.logger.info(f"[DATA] JSON内容:\n{request_json}")
        self.logger.info(f"================================")
        
        return self.encode_message(json.dumps(request_msg))

    def _build_verify_pin_request(self, session_data, pin_code):
        """构建验证PIN请求消息"""
        # 使用session中保存的固定值，参考PHP的verifyPin方法
        android_id = session_data.get('androidId')
        safety_net_id = session_data.get('safetyNetId')
        phone = session_data.get('phone')
        serv_gen_id = session_data.get('serv_gen_id')  # 从OTP验证后获得
        
        request_msg = {
            "appPin": {
                "atmCrdLength": 0,
                "credentialDataLength": 0,
                "credentialDataValue": pin_code,
                "otpCrdLength": 0
            },
            "deviceInfo": {
                "androidId": android_id,
                "app_gen_id": serv_gen_id,  # PIN验证使用servGenId
                "appName": "com.mgs.induspsp",
                "appVersionCode": "59",
                "appVersionName": "3.3.32",
                "bluetoothMac": "00:00:00:00:00:00",
                "capability": "5200000200010004000639292929292",
                "deviceId": android_id,
                "deviceType": "MOB",
                "fcmToken": session_data.get('fcmToken', "99KMIQYLS9WgUgtr9xHCDC:KMA91bFNivbb_n_22Jjwe746zpGvZDo9NVbQF7pAQazC9fRmUzuiEpdYOoF5ecizF53EjgaypHF4-zKljSpY-eOx2aSaQ-3ESR6ShfcRGJfb_NOTs765gFqHlttppTgw9cSZrOcVFg5R"),
                "geoCode": session_data.get('geoCode', '23.556977,116.368093'),
                "ip": "192.168.0.115",
                "location": session_data.get('location', 'Jie Yang Shi,Guang Dong Sheng,China'),
                "mobileNo": phone,
                "os": "Android13",
                "regId": "NA",
                "relayButton": "Yn5V925x5gVk7MCtgk57hT9ELJRwGW6L1fFLpFHE+rU=",
                "safetyNetId": safety_net_id,
                "selectedSimSlot": 0,
                "simId": android_id + "2",
                "wifiMac": "02:00:00:00:00:00"
            },
            "requestInfo": {
                "pspId": "10001",
                "pspRefNo": safety_net_id
            }
        }
        
        return self.encode_message(json.dumps(request_msg))

    def _build_sms_content(self, gateway_content, phone, app_gen_id):
        """构建短信内容 - 与PHP版本的sms_txt方法一致"""
        import hashlib
        
        try:
            self.logger.info(f"[START] 开始构建短信内容:")
            self.logger.info(f"   gateway_content: '{gateway_content}'")
            self.logger.info(f"   phone: '{phone}'")
            self.logger.info(f"   app_gen_id: '{app_gen_id}'")
            
            # 参考PHP版本的逻辑 - 从会话数据中获取androidId
            android_id = getattr(self, '_current_session_data', {}).get('androidId')
            if not android_id:
                android_id = self.generate_android_id()
                self.logger.info(f"[KEY] 生成新的androidId: {android_id}")
            else:
                self.logger.info(f"[KEY] 使用已有的androidId: {android_id}")
                
            password = android_id
            salt = app_gen_id + phone
            iterations = 250
            key_length = 64  # 修正：与PHP版本保持一致（64字节 = 128个十六进制字符）
            
            self.logger.info(f"[SECURITY] PBKDF2参数:")
            self.logger.info(f"   password: {password}")
            self.logger.info(f"   salt: {salt}")
            self.logger.info(f"   iterations: {iterations}")
            self.logger.info(f"   key_length: {key_length}")
            
            # 使用PBKDF2生成哈希
            dk = hashlib.pbkdf2_hmac('sha1', password.encode(), salt.encode(), iterations, key_length)
            res_hex = dk.hex()
            
            self.logger.info(f"[SECURITY] PBKDF2结果:")
            self.logger.info(f"   res_hex长度: {len(res_hex)}")
            self.logger.info(f"   res_hex: {res_hex}")
            
            # 获取最后三个字符
            res_hex_len = len(res_hex)
            last_char = res_hex[res_hex_len - 1]
            second_last_char = res_hex[res_hex_len - 2] 
            third_last_char = res_hex[res_hex_len - 3]
            
            self.logger.info(f"[DATA] 最后三个字符:")
            self.logger.info(f"   third_last_char: '{third_last_char}'")
            self.logger.info(f"   second_last_char: '{second_last_char}'")
            self.logger.info(f"   last_char: '{last_char}'")
            
            # 将字符转换为ASCII码值
            last_char_value = ord(last_char)
            second_last_char_value = ord(second_last_char)
            third_last_char_value = ord(third_last_char)
            
            self.logger.info(f"[DATA] ASCII码值:")
            self.logger.info(f"   third_last_char_value: {third_last_char_value}")
            self.logger.info(f"   second_last_char_value: {second_last_char_value}")
            self.logger.info(f"   last_char_value: {last_char_value}")
            
            # 计算结果并对15取模
            h2 = (second_last_char_value + last_char_value + third_last_char_value) % 15
            i2 = h2 + 35
            result = res_hex[h2:i2]
            
            self.logger.info(f"[DATA] 计算结果:")
            self.logger.info(f"   h2: {h2}")
            self.logger.info(f"   i2: {i2}")
            self.logger.info(f"   result: '{result}'")
            
            # 构建最终短信内容
            sms_content = f"{gateway_content} Confidential:Dont share if asked!{result}!{app_gen_id}"
            
            self.logger.info(f"[SUCCESS] 短信内容构建成功:")
            self.logger.info(f"   短信内容: '{sms_content}'")
            self.logger.info(f"   长度: {len(sms_content)}")
            
            return sms_content
            
        except Exception as e:
            self.logger.error(f"[CRITICAL ERROR] 构建短信内容失败: {str(e)}")
            import traceback
            self.logger.error(f"[ERROR] 错误堆栈: {traceback.format_exc()}")
            
            # [ERROR] 不使用降级方案！短信内容格式错误会导致银行安全检测失败
            # 必须修复根本问题，而不是使用错误的格式
            raise NewApiError('20304', f"SMS content construction failed, cannot use fallback: {str(e)}")

    def _decode_indus_response(self, response_data):
        """解码Indus响应消息"""
        try:
            if isinstance(response_data, dict):
                # 检查是否有加密的resp字段
                if 'resp' in response_data:
                    # 解码加密的响应
                    decoded_resp = self.decode_message(response_data['resp'])
                    return json.loads(decoded_resp)
                else:
                        # 如果已经是字典且没有resp字段，直接返回
                    return response_data
            elif isinstance(response_data, str):
                # 如果是字符串，尝试JSON解析
                return json.loads(response_data)
            else:
                return {}
        except Exception as e:
            self.logger.warning(f"Response decoding failed: {str(e)}, raw data: {response_data}")
            return response_data if isinstance(response_data, dict) else {}

    # ================== 会话管理方法 ==================
    async def _get_session_data(self, redis_key):
        """获取会话数据"""
        try:
            if not redis_key:
                return None
            
            session_json = await self.redis.get(redis_key)
            if session_json:
                return json.loads(session_json)
            return None
        except Exception as e:
            self.logger.error(f"获取会话数据失败: {str(e)}")
            return None

    async def _update_session_status(self, redis_key, session_data, new_status, additional_data=None):
        """更新会话状态"""
        try:
            session_data['status'] = new_status
            session_data['last_status_change'] = int(time.time())
            session_data['last_request_time'] = int(time.time())
            
            # 添加状态历史记录
            if 'status_history' not in session_data:
                session_data['status_history'] = []
            session_data['status_history'].append(new_status)
            
            if additional_data:
                session_data.update(additional_data)
            
            # 根据状态设置不同的过期时间
            if new_status == LoginStatus.LOGIN_SUCCESSFUL:
                expire_time = 600   # 登录成功后10分钟
                expire_desc = "10分钟"
            else:
                expire_time = 300   # 登录流程中5分钟
                expire_desc = "5分钟"
            
            await self.redis.setex(redis_key, expire_time, json.dumps(session_data))
            
            self.logger.info(f"会话状态更新: {redis_key} -> {new_status} (过期时间: {expire_desc})")
            return True
        except Exception as e:
            self.logger.error(f"更新会话状态失败: {str(e)}")
            return False

    async def _validate_status_transition(self, session_data, expected_current_status, target_status, operation_name):
        """验证状态转换是否有效"""
        current_status = session_data.get('status')
        
        if current_status != expected_current_status:
            message = f"状态转换无效 {operation_name}: 期望 {expected_current_status}, 实际 {current_status}"
            self.logger.error(message)
            return {'valid': False, 'message': message}
            
        if target_status not in STATUS_TRANSITIONS.get(current_status, []):
            message = f"状态转换无效 {operation_name}: {current_status} -> {target_status}"
            self.logger.error(message)
            return {'valid': False, 'message': message}
            
        return {'valid': True, 'message': '状态转换有效'}

    # ================== HTTP请求方法 ==================
    def make_request(self, method, url, headers=None, params=None, data=None, json_data=None, proxies=None):
        """简化的make_request实现 - 统一使用data参数（从jio_bank.py拷贝）"""
        self.logger.info('请求 {method} {url}, params:{params} data:{data}  代理： {proxies}'.format(
            method=method, url=url, params=params, data=data, proxies=proxies))
        try:
            import requests
            if not hasattr(self, 'session'):
                self.session = requests.Session()
            
            response = None
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params, proxies=proxies, verify=False, allow_redirects=True, timeout=(10, 10))
            elif method.upper() == 'POST':
                if data is not None:
                    response = self.session.post(url, headers=headers, data=data, proxies=proxies, verify=False, allow_redirects=True, timeout=(10, 10))
                else:
                    response = self.session.post(url, headers=headers, proxies=proxies, verify=False, timeout=(10, 10))
            else:
                response = None
            if response is not None:
                self.logger.info(f'请求 {method} {url}, params:{params}, data:{data}, response: {response}, response.text: {response.text}')
            return response
        except Exception as e:
            self.logger.error(f"网络请求错误： 错误详情:{e}")
            return None

    def retry_make_request(self, *args, **kwargs):
        """简化的retry_make_request - 保持与jio_bank.py一致"""
        # 第一次尝试
        res = self.make_request(*args, **kwargs)
        if res is not None and (200 <= res.status_code < 300):
            return res
            
        # 第二次尝试
        self.logger.info(f"make_request() second try, args: {args}, kwargs: {kwargs}")
        res = self.make_request(*args, **kwargs)
        
        if res is None or not (200 <= res.status_code < 300):
            self.logger.warning(f"make_request() 两次尝试均失败, args: {str(args)}, kwargs: {str(kwargs)}")
            
        return res

    def log_response(self, response):
        """原始的log_response函数 - 直接来自jio_bank.py的ResponseLogger.log_response"""
        try:
            from datetime import datetime
            
            # 检查response是否为None
            if response is None:
                self.logger.error("响应为None，无法记录日志")
                return
                
            # 基本信息
            self.logger.info("=" * 50)
            self.logger.info(f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info(f"请求URL: {response.url}")
            self.logger.info(f"请求方法: {response.request.method}")
            self.logger.info(f"状态码: {response.status_code}")
            
            # 请求头信息
            self.logger.info("请求头:")
            for key, value in dict(response.request.headers).items():
                self.logger.info(f"    {key}: {value}")
            
            # 响应头信息
            self.logger.info("响应头:")
            for key, value in dict(response.headers).items():
                self.logger.info(f"    {key}: {value}")
            
            # 响应体信息
            self.logger.info("响应体:")
            response_text = response.text
            if len(response_text) > 1000:
                self.logger.info(f"    {response_text[:500]}...{response_text[-500:]}")
            else:
                self.logger.info(f"    {response_text}")
            
            self.logger.info("=" * 50)
            
        except Exception as e:
            self.logger.error(f"记录响应日志失败: {str(e)}")

    # ================== 基础支持方法 ==================
    async def _check_existing_payment(self, bankname, phone, partner_id):
        """检查是否存在现有payment记录"""
        try:
            self.logger.info(f"=== IndusBank开始检查现有payment记录 ===")
            self.logger.info(f"参数: bankname={bankname}, phone={phone}, partner_id={partner_id}")
            
            from application.lakshmi_api.models.payment import Payment
            
            # 银行名称映射
            bank_name_mapping = {
                'indus': 'INDUS',
                'indusbank': 'INDUS',
                'indus_bank': 'INDUS'
            }
            
            normalized_bankname = bank_name_mapping.get(bankname.lower(), bankname.upper())
            self.logger.info(f"normalized_bankname: {normalized_bankname}")
            
            # 获取银行类型ID
            bank_type_id = await self._get_bank_type_id(bankname)
            if not bank_type_id:
                self.logger.warning(f"未找到银行类型ID: {normalized_bankname}")
                return None
            
            # 查询现有记录
            with self.handler.db_orm.sessionmaker() as session:
                existing_payment = session.query(Payment).filter(
                    Payment.bank_type == bank_type_id,
                    Payment.bank_type_id == bank_type_id,
                    Payment.phone == phone
                ).filter(
                    # 如果有partner_id，则也需要匹配；如果没有，则忽略此条件
                    (Payment.user_id == partner_id) if partner_id else True
                ).first()
                
                if existing_payment:
                    payment_info = {
                        'id': existing_payment.id,
                        'bank_type': existing_payment.bank_type,
                        'phone': existing_payment.phone,
                        'upi': existing_payment.upi,
                        'user_id': existing_payment.user_id,
                        'status': existing_payment.status,
                        'time_create': existing_payment.created_at.isoformat() if existing_payment.created_at else None
                    }
                    self.logger.info(f"找到现有payment记录: {payment_info}")
                    self.logger.info(f"=== IndusBank检查现有payment记录完成 - 找到 ===")
                    return payment_info
                else:
                    self.logger.info(f"未找到现有payment记录")
                    self.logger.info(f"=== IndusBank检查现有payment记录完成 - 未找到 ===")
            return None
                    
        except Exception as e:
            self.logger.error(f"检查现有payment失败: {str(e)}", exc_info=True)
            self.logger.info(f"=== IndusBank检查现有payment记录完成 - 异常 ===")
            return None

    async def _select_proxy_ip(self, bankname):
        """
        选择代理IP，保持一致性
        参考jio_bank.py的_select_proxy_ip方法
        """
        try:
            self.logger.info(f"=== {bankname}选择代理IP开始 ===")
            
            # 获取新的代理IP（返回纯净字符串格式，用于存储到session）
            proxy_ip = await self._get_proxies(bankname)
            if not proxy_ip:
                self.logger.error(f"{bankname}无可用代理IP")
                return ""
            
            self.logger.info(f"{bankname}选择代理IP成功（session存储格式）: {proxy_ip}")
            
            return proxy_ip
            
        except Exception as e:
            self.logger.error(f"{bankname}选择代理IP异常: {str(e)}")
            return ""

    async def _get_proxies(self, bankname):
        """
        从Redis获取可用的代理IP列表并随机选择一个
        参考jio_bank.py的_get_proxies()方法（使用被注释的Redis逻辑）
        """
        
        # ================ Redis代理获取逻辑 (来自jio_bank.py注释代码) ================
        try:
            # 从Redis获取印度SOCKS代理IP列表
            redis_key = self.PROXIES_IP_KEY.format(bankname=bankname)
            indian_socks_ip = await self.redis.get(redis_key)
            
            if not indian_socks_ip:
                self.logger.error(f"Redis中无{redis_key}代理IP配置")
                return False
            
            # 解析代理IP列表
            if isinstance(indian_socks_ip, bytes):
                indian_socks_ip = indian_socks_ip.decode('utf-8')
            
            proxy_list = indian_socks_ip.split(',')
            proxy_list = [item.strip() for item in proxy_list if item.strip()]
            
            if not proxy_list:
                self.logger.error(f"{redis_key}代理IP列表为空")
                return False
            
            # 随机选择一个代理IP
            import random
            selected_proxy = random.choice(proxy_list)
            
            # 确保返回的是纯净的字符串格式（去掉socks5://前缀）
            if selected_proxy.startswith('socks5://'):
                selected_proxy = selected_proxy[9:]  # 移除 'socks5://' 前缀
            
            self.logger.info(f"从{len(proxy_list)}个Redis代理中选择: {selected_proxy}")
            return selected_proxy  # 返回字符串格式，用于存储到session
            
        except Exception as e:
            self.logger.error(f"获取Redis代理IP异常: {str(e)}")
            return False

    async def _get_proxy_for_request(self, session_data):
        """
        为HTTP请求获取代理配置
        返回requests库可用的代理字典格式
        """
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
            
            self.logger.info(f"获取请求代理配置: {proxy_url}")
            return proxy_dict
            
        except Exception as e:
            self.logger.error(f"选择代理IP失败: {str(e)}")
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
        try:
            lock_key = self.PAYMENT_INTERFACE_LOCK_KEY.format(payment_id=payment_id, operation_name=operation_name)
            lock_value = f"{int(time.time())}_{random.randint(1000, 9999)}"
            
            # 尝试获取锁，如果成功设置过期时间
            lock_acquired = await self.redis.set(lock_key, lock_value, nx=True, ex=self.lock_time)
            
            if lock_acquired:
                self.logger.info(f"获取接口锁成功: {payment_id}:{operation_name}")
                return {
                    'status': 'success',
                    'lock_id': lock_key,
                    'lock_value': lock_value
                }
            else:
                self.logger.warning(f"获取接口锁失败，已被占用: {payment_id}:{operation_name}")
                raise NewApiError('20203', 'Operation too frequent, please try again later')
                
        except NewApiError:
            raise  # 重新抛出NewApiError
        except Exception as e:
            self.logger.error(f"获取接口锁异常: {str(e)}")
            raise NewApiError('20203', 'System error')

    async def _release_payment_interface_lock(self, lock_id, lock_value):
        """释放基于payment_id的接口锁"""
        try:
            # 使用Lua脚本确保原子性操作
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            
            result = await self.redis.eval(lua_script, 1, lock_id, lock_value)
            if result:
                self.logger.info(f"释放接口锁成功: {lock_id}")
                return True
            else:
                self.logger.warning(f"释放接口锁失败，锁值不匹配: {lock_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"释放接口锁异常: {str(e)}")
            return False

    # ================== 锁管理方法 ==================
    async def get_lock(self, payment_id):
        """获取支付接口锁"""
        try:
            lock_key = self.PAYMENT_LOCK_KEY.format(payment_id=payment_id)
            lock_value = f"{int(time.time())}_{random.randint(1000, 9999)}"
            
            # 尝试获取锁，如果成功设置过期时间
            lock_acquired = await self.redis.set(lock_key, lock_value, nx=True, ex=self.lock_time)
            
            if lock_acquired:
                self.logger.info(f"获取支付锁成功: {payment_id}")
                return lock_value
            else:
                self.logger.warning(f"获取支付锁失败，已被占用: {payment_id}")
                return None
                
        except Exception as e:
            self.logger.error(f"获取支付锁异常: {str(e)}")
            return None

    async def del_lock(self, payment_id, lock_value):
        """释放支付接口锁"""
        try:
            lock_key = f"payment_lock:{payment_id}"
            
            # 使用Lua脚本确保原子性操作
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            
            result = await self.redis.eval(lua_script, 1, lock_key, lock_value)
            if result:
                self.logger.info(f"释放支付锁成功: {payment_id}")
                return True
            else:
                self.logger.warning(f"释放支付锁失败，锁值不匹配: {payment_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"释放支付锁异常: {str(e)}")
            return False 

    # =========================== 数据库操作方法 ===========================
    async def _save_payment_to_database(self, session_data, selected_upi, name):
        """保存payment数据到数据库"""
        try:
            self.logger.info(f"=== IndusBank开始保存payment到数据库 ===")
            self.logger.info(f"selected_upi: {selected_upi}")
            
            from application.lakshmi_api.models.payment import Payment
            from application.lakshmi_api.models.bank_type import BankType
            from sqlalchemy import update
            from datetime import datetime
            
            # 从session_data获取必要信息
            bankname = session_data['bankname']
            phone = session_data['original_phone']  # 使用原始号码
            password = session_data.get('password', '')
            partner_id = session_data.get('partner_id')
            
            self.logger.info(f"IndusBank数据库保存参数: 银行={bankname}, 手机号={phone}, partner_id={partner_id}, UPI={selected_upi}")
            
            # 检查是否存在现有payment记录
            self.logger.info(f"IndusBank检查现有payment记录")
            existing_payment = await self._check_existing_payment(bankname, phone, partner_id)
            
            if existing_payment:
                # 更新现有记录
                return await self._update_existing_payment(existing_payment['id'], session_data, selected_upi, name)
            else:
                # 创建新记录
                return await self._create_new_payment(session_data, selected_upi, name)
                
        except Exception as e:
            self.logger.error(f"IndusBank数据库写入异常: {str(e)}")
            return None

    async def _create_new_payment(self, session_data, selected_upi, name=None):
        """创建新的payment记录"""
        try:
            self.logger.info(f"=== IndusBank开始创建新payment记录 ===")
            
            from application.lakshmi_api.models.payment import Payment
            from application.lakshmi_api.models.bank_type import BankType
            from datetime import datetime
            import json
            
            bankname = session_data['bankname']
            phone = session_data['original_phone']  # 使用原始号码
            password = session_data.get('password', '')
            partner_id = session_data.get('partner_id')
            
            self.logger.info(f"_create_new_payment - 参数: bankname={bankname}, phone={phone}, partner_id={partner_id}, upi={selected_upi}")
            self.logger.info(f"_create_new_payment - 使用原始号码: {phone}")
            
            # 获取银行类型ID
            self.logger.info(f"_create_new_payment - 获取银行类型ID")
            bank_type_id = await self._get_bank_type_id(bankname)
            self.logger.info(f"_create_new_payment - 银行类型ID: {bank_type_id}")
            
            # 构建payment数据（使用正确的Python模型字段名）
            payment_data = {
                'bank_type': bank_type_id,  # 存储银行名称字符串
                'bank_type_id': bank_type_id,   # 存储银行类型ID
                'upi': selected_upi,
                'phone': phone,
                'pin': password,  # 将MPIN存储在pin字段
                'net_trade_pw': password,  # 同时也存储在net_trade_pw字段
                'user_id': partner_id,  # 对应数据库中的partner_id字段
                'status': 1,  # 激活状态
                'certified': 1,  # 已认证
                'upi_list': ','.join(session_data.get('upi_list', [])),  # UPI列表，逗号分隔
                'remarks': None,  # 清理remarks字段，新建时清空之前的错误信息
                # created_at字段有默认值，不需要手动设置
            }
            
            # 只有当name不为空时才设置name字段
            if name:
                payment_data['name'] = name
                self.logger.info(f"_create_new_payment - 设置name字段: {name}")
            else:
                self.logger.info(f"_create_new_payment - name参数为空，不设置name字段")
            
            self.logger.info(f"_create_new_payment - 构建payment数据完成")
            
            # 使用SQLAlchemy插入数据
            self.logger.info(f"_create_new_payment - 开始数据库插入操作")
            with self.handler.db_orm.sessionmaker() as session:
                new_payment = Payment(**payment_data)
                session.add(new_payment)
                session.commit()
                payment_id = new_payment.id
                
            self.logger.info(f"_create_new_payment - 数据库插入成功: ID={payment_id}")
            self.logger.info(f"=== IndusBank创建新payment记录完成 - 成功 ===")
            return payment_id
            
        except Exception as e:
            self.logger.error(f"_create_new_payment - 创建payment记录异常: {str(e)}", exc_info=True)
            self.logger.info(f"=== IndusBank创建新payment记录完成 - 失败 ===")
            return None

    async def _update_existing_payment(self, existing_payment_id, session_data, selected_upi, name=None):
        """更新现有payment记录"""
        try:
            self.logger.info(f"=== IndusBank开始更新现有payment记录 ===")
            
            from application.lakshmi_api.models.payment import Payment
            from sqlalchemy import update
            from datetime import datetime
            import json
            
            bankname = session_data['bankname']
            password = session_data.get('password', '')
            
            self.logger.info(f"_update_existing_payment - 参数: payment_id={existing_payment_id}, bankname={bankname}, upi={selected_upi}")
            
            # 构建更新数据（使用正确的Python模型字段名）
            update_data = {
                'upi': selected_upi,
                'pin': password,  # 更新MPIN
                'net_trade_pw': password,  # 同时更新net_trade_pw
                'status': 1,  # 确保状态为激活
                'certified': 1,  # 确保已认证
                'upi_list': ','.join(session_data.get('upi_list', [])),  # 更新UPI列表，逗号分隔
                'remarks': None  # 清理remarks字段，重新登录时清空之前的错误信息
            }
            
            # 只有当name不为空时才更新name字段
            if name:
                update_data['name'] = name
                self.logger.info(f"_update_existing_payment - 更新name字段: {name}")
            else:
                self.logger.info(f"_update_existing_payment - name参数为空，不更新name字段")
            
            self.logger.info(f"_update_existing_payment - 构建更新数据完成")
            
            # 使用SQLAlchemy更新数据
            self.logger.info(f"_update_existing_payment - 开始数据库更新操作")
            with self.handler.db_orm.sessionmaker() as session:
                session.execute(
                    update(Payment).
                    where(Payment.id == existing_payment_id).
                    values(**update_data)
                )
                session.commit()
                
            self.logger.info(f"_update_existing_payment - 数据库更新成功: ID={existing_payment_id}")
            self.logger.info(f"=== IndusBank更新现有payment记录完成 - 成功 ===")
            return existing_payment_id
            
        except Exception as e:
            self.logger.error(f"_update_existing_payment - Update payment record exception: {str(e)}", exc_info=True)
            self.logger.info(f"=== IndusBank更新现有payment记录完成 - 失败 ===")
            return None

    async def _get_bank_type_id(self, bankname):
        """获取银行类型ID"""
        try:
            self.logger.info(f"=== IndusBank开始获取银行类型ID ===")
            self.logger.info(f"bankname: {bankname}")
            
            from application.lakshmi_api.models.bank_type import BankType
            
            # 银行名称映射
            bank_name_mapping = {
                'indus': 'INDUS',
                'indusbank': 'INDUS',
                'indus_bank': 'INDUS'
            }
            
            normalized_bankname = bank_name_mapping.get(bankname.lower(), bankname.upper())
            self.logger.info(f"normalized_bankname: {normalized_bankname}")
            
            # 查询银行类型ID
            with self.handler.db_orm.sessionmaker() as session:
                bank_type = session.query(BankType).filter(
                    BankType.name == normalized_bankname
                ).first()
                
                if bank_type:
                    bank_type_id = bank_type.id
                    self.logger.info(f"找到银行类型ID: {bank_type_id}")
                    self.logger.info(f"=== IndusBank获取银行类型ID完成 - 成功 ===")
                    return bank_type_id
                else:
                    self.logger.warning(f"未找到银行类型: {normalized_bankname}")
                    self.logger.info(f"=== IndusBank获取银行类型ID完成 - 未找到 ===")
                    return None
                    
        except Exception as e:
            self.logger.error(f"Get bank type ID exception: {str(e)}", exc_info=True)
            self.logger.info(f"=== IndusBank获取银行类型ID完成 - 异常 ===")
            return None