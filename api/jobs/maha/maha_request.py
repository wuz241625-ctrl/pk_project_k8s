import inspect
import json
import logging
import random
import string
import time
import uuid
from datetime import datetime
from functools import wraps
from typing import Optional, Dict

import socks
import urllib3
from urllib3.contrib.socks import SOCKSProxyManager

from account_balance import AccountBalance
from beneficiary import Beneficiary
from customer_adapter import create_ssl_context
from device_id_generator import generate_android_13_device_id
from encryption_interceptor import EncryptionInterceptor, ResponseResult
from encryption_utils import EncryptionUtils
from maha_result_status import MahaResultStatusCode, PayProcessStatus
from maha_result import MahaResult
from user_info import UserInfo

# 定义检查受益人时间间隔
CHECK_BENEFICIARY_AUDIT_INTERVALS = [10, 5, 5, 5, 5, 2, 1, 1, 1, 1]  # 单位：分钟

def setup_logger():
    """配置日志"""
    logger = logging.getLogger('maha_request')
    logger.setLevel(logging.INFO)

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)

    # 添加处理器到logger
    logger.addHandler(console_handler)

    return logger

def get_current_method_name():
    # 获取当前方法的名称
    return inspect.currentframe().f_back.f_code.co_name


class MahaRequest:
    def __init__(self, user_info: UserInfo, proxies, logger=None, local_mock: bool = False):
        self.user_info = user_info
        self.beneficiary: Optional[Beneficiary] = None
        self.proxies = proxies
        self.logger = logger or setup_logger()
        self.local_mock = local_mock

        # 禁用SSL警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        # 设置基本请求头
        self.headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 13; IN2010 Build/TQ3A.230901.001.B1)'
        }

        # 创建SSL上下文
        ssl_context = create_ssl_context()

        # 创建SOCKS代理管理器
        self.proxy_manager = SOCKSProxyManager(
            proxy_url=proxies['https'],
            ssl_context=ssl_context,
            retries=urllib3.Retry(2),
            timeout=urllib3.Timeout(connect=30, read=30)
        )

        # 添加拦截器
        self.interceptor = EncryptionInterceptor(user_info, self.logger)

    @staticmethod
    def generate_random_names() -> Dict[str, str]:
        """生成随机名字"""
        first_name = ''.join(random.choices(string.ascii_letters, k=5))
        last_name = ''.join(random.choices(string.ascii_letters, k=5))
        customer_name = f"{first_name} {last_name}"

        return {
            "customerName": customer_name,
            "firstName": first_name,
            "lastName": last_name
        }

    @staticmethod
    def get_random_number() -> str:
        """生成4位随机数"""
        return f"{random.randint(0, 9999):04d}"

    @staticmethod
    def get_secure_number() -> str:
        """生成8位随机数"""
        return f"{random.randint(0, 99999999):08d}"

    @staticmethod
    def get_txn_id() -> str:
        """生成交易ID"""
        return f"LVBM{uuid.uuid4().hex}"

    @staticmethod
    def get_formatted_current_datetime() -> str:
        """获取格式化的当前时间"""
        return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    def make_request(self, url, payload=None, headers=None, max_retries=1, timeout=10, proxies=None, method_name=None) -> MahaResult:
        self.logger.info(f"{method_name}(), maha请求 url: {url}, payload: {payload}")
        # 请求前处理
        preRequestResult = self.interceptor.pre_request(payload, method_name)
        encrypted_body = preRequestResult.request_data
        action = preRequestResult.action
        self.logger.info(f"{method_name}(), 发起请求url: {url}, payload密文: {encrypted_body}")

        mahaResult = MahaResult(
            is_success=False,
            status_code=MahaResultStatusCode.FALSE,
            error_message="The request api encountered a problem"
        )
        """
        发送POST请求到Maha API
        """
        for attempt in range(max_retries):
            try:
                # 打印完整的请求信息
                self.logger.info(
                    f"{method_name}(), (尝试 {attempt + 1}/{max_retries}) 请求. "
                    f"{"="*10} "
                    f"原始请求体: {json.dumps(payload, ensure_ascii=False)}, "
                    f"请求头: {json.dumps(headers, ensure_ascii=False)}, "
                    f"代理设置: {self.proxy_manager.proxy_url}, "
                    f"加密后请求体: {json.dumps(encrypted_body, ensure_ascii=False)}, "
                    f"POST {url}, "
                    f"{"="*10} "
                )

                response = self.proxy_manager.request(
                    'POST',
                    url,
                    body=json.dumps(encrypted_body),
                    headers=headers,
                    preload_content=True,
                )

                # 打印响应信息
                self.logger.info(
                    f"{method_name}(), (尝试 {attempt + 1}/{max_retries}) 请求的响应详情. "
                    f"{"="*10} "
                    f"响应体数据类型: {type(response.data)}, 响应体: {response.data}, "
                    f"响应状态码: {response.status}, "
                    f"响应头: {json.dumps(dict(response.headers), ensure_ascii=False)}, "
                    f"POST {url}, "
                    f"{"="*10} "
                )
                if response.data is None:
                    error_message = f"{method_name}(), 响应体 为空 {url}"
                    self.logger.error(error_message)
                    return MahaResult(status_code=MahaResultStatusCode.LOGOUT, error_message=error_message)
                elif isinstance(response.data, bytes):
                    response_body = response.data.decode('utf-8')
                    try:
                        # 尝试格式化JSON响应
                        formatted_response = json.dumps(json.loads(response_body), ensure_ascii=False)
                        self.logger.info(f"{method_name}(), 响应体 response.data: {formatted_response}")
                    except:
                        self.logger.info(f"{method_name}(), 响应体 response.data except: {response_body}")


                if response.status == 200:
                    post_response_result = self.interceptor.post_response(response, action, method_name)
                    self.logger.info(f"{method_name}(), maha请求 响应的解密结果: {post_response_result}")
                    # status = post_response_result.status
                    # data = post_response_result.data
                    # data_str = post_response_result.data_str
                    # error_message = post_response_result.error_message
                    return MahaResult(is_success=True, data = post_response_result._asdict())
                elif 400 <= response.status <= 499:
                    error_message = f"Service may be moving, come back later!"
                    self.logger.error(f"{method_name}(), status: {response.status}, {error_message}")
                    mahaResult = MahaResult(is_success=False, status_code=MahaResultStatusCode.LOGOUT, error_message=error_message)
                elif response.status == 503:
                    error_message = f"This server is temporarily unable to service requests."
                    self.logger.error(f"{method_name}(), status: {response.status}, {error_message}")
                    mahaResult = MahaResult(is_success=False, status_code = MahaResultStatusCode.LOGOUT, error_message=error_message)
                elif 500 <= response.status <= 599:
                    error_message = f"Service is temporarily unavailable. Please try again later."
                    self.logger.error(f"{method_name}(), status: {response.status}, {error_message}")
                    mahaResult = MahaResult(is_success=False, status_code = MahaResultStatusCode.LOGOUT, error_message=error_message)
                else:
                    try:
                        self.logger.warning(f"{method_name}(), 状态码: {response.status}")
                        self.logger.warning(f"{method_name}(), 响应头: {dict(response.headers)}")
                        self.logger.warning(f"{method_name}(), 响应体: {response.data}")
                    except Exception as e:
                        self.logger.error(f"{method_name}(), 打印响应详情失败: {e}")
                    if isinstance(response.data, str):
                        error_message=f"{method_name}(), 发现未处理的失败响应体str: {response.data}"
                        self.logger.error(error_message)
                        mahaResult = MahaResult(data = json.loads(response.data), status_code = MahaResultStatusCode.LOGOUT, error_message=error_message)
                    elif isinstance(response.data, dict):
                        error_message=f"{method_name}(), 发现未处理的失败响应体 dict: {response.data}"
                        self.logger.error(error_message)
                        mahaResult = MahaResult(data = response.data, status_code = MahaResultStatusCode.LOGOUT, error_message=error_message)
                    else:
                        error_message=f"{method_name}(), 发现未处理的失败响应体 {type(response.data)}: {response.data}"
                        self.logger.error(error_message)
                        mahaResult = MahaResult(status_code = MahaResultStatusCode.LOGOUT, error_message=error_message)

            except urllib3.exceptions.SSLError as e:
                self.logger.error(f"{method_name}(), 请求接口异常：SSL错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise

            except urllib3.exceptions.ProxyError as e:
                self.logger.error(f"{method_name}(), 请求接口异常：代理连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise

            except urllib3.exceptions.TimeoutError as e:
                self.logger.error(f"{method_name}(), 请求接口异常：请求超时 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise

            except urllib3.exceptions.ConnectionError as e:
                self.logger.error(f"{method_name}(), 请求接口异常：连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise

            except socks.SOCKS5Error as e:
                self.logger.error(f"{method_name}(), 请求接口异常：SOCKS5代理错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise

            except json.JSONDecodeError as e:
                self.logger.error(f"{method_name}(), 请求接口异常：JSON解析错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                raise

            except Exception as e:
                self.logger.error(f"{method_name}(), 请求接口异常：请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                raise

            time.sleep(1)  # 重试前等待1秒
        return mahaResult

    # 获取要发送短信的目标号码、内容
    def get_vmn(self) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                data={"targetPhoneNumber": "9999999999", "targetSmsContent": "Mock Data"},
                user_info=self.user_info
            )

        """获取VMN"""
        input_param = {
            "entityId": "BOM",
            "deviceId": self.user_info.deviceId,
            "country": "India"
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "GetVMN",
                        "subAction": "GetVMN",
                        "inputParam": input_param,
                        "deviceId": self.user_info.deviceId,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|GetVMN"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)

        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)

        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, error_message: {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data['status'] != "00" or "responseParameter" not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 {error_message}, data: {data}")
            return MahaResult(error_message=error_message)
        responseParameter = data.get("responseParameter", {})
        key = EncryptionUtils.gen_key(self.user_info.key, self.user_info.deviceId)

        # 要发送短信的目标号码
        targetPhoneNumber = EncryptionUtils.decrypt(responseParameter['VMN'], key)
        self.user_info.vmn = targetPhoneNumber

        verificationCode = EncryptionUtils.get_random_string(6)

        self.user_info.token = data['uniquerequestId']
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        self.user_info.verificationCode = verificationCode

        # 拼装短信内容源数据
        sms_content_source = f"BOM|{self.user_info.deviceId}|{targetPhoneNumber}|{verificationCode}|A|{self.user_info.accountNumber}"
        # 短信内容源数据加密
        sms_content_encrypt = EncryptionUtils.encrypt(sms_content_source, self.user_info.key)
        # 要发送短信的内容
        targetSmsContent = f"BOMPRD {sms_content_encrypt}"

        self.logger.info(
            f"获取发送短信的目标号码及内容\n"
            f"{'=' * 50}"
            f"\n"
            f"{targetPhoneNumber}"
            f"\n"
            f"{'=' * 50}"
            f"\n"
            f"{targetSmsContent}"
            f"\n"
            f"{'=' * 50}"
        )

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            data = {"targetPhoneNumber": targetPhoneNumber, "targetSmsContent": targetSmsContent},
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 验证是否发短信，获取customerId
    def verification_client_send_sms(self) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info
            )

        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        """获取VMN"""
        input_param = {
            "entityId": "BOM",
            "verificationCode": self.user_info.verificationCode,
            "customerId": self.user_info.accountNumber,
            "language": "en_US",
            "isRegdUpi": "Y",
            "vmn": self.user_info.vmn,
            "isRegdMbanking": "Y",
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "MobileVerificationService",
                        "subAction": "MobileVerificationService",
                        "inputParam": input_param,
                        "entityId": "BOM",
                        "deviceId": self.user_info.deviceId,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|MobileVerificationService"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","msg":"Mobile is Already Registered.","uniquerequestId":"YCn2INgYYmQuZKS40LNTTb6KNGUKxBMu3SBpqd2qS9uw0MSuythndh4oKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGV1oaVFPvH+9fsiaR1isouXg=","responseParameter":{"authenticationNo":"OmyrdDvT4HP6DEclVTl42Uq5E04=","entityId":"BOM","IsMigratedUser":"N","mobileNo":"8167411813","encryptionKey":"c592eb91208ac6d7","isBomCustomer":"Y","aadharFlag":"N","customerName":"Mobile Banking User","isRegUpi":"Y","isRegMbanking":"Y","aadharNumber":"NA","customerId":"40292402141","appUpdate":{"id":3,"version":1,"entityId":"BOM","os":"Android","subVersion":34.0,"isActive":"Y","isForceUpdate":"Y","message":"New Version of Mahamobile Plus is now available. Click update.","createdTime":1701801000000,"appUrl":"https://play.google.com/store/apps/details?id=com.kiya.mahaplus"}}}
        {"status":"01","msg":"Vmn time difference greater than 30 sec","uniquerequestId":"YCn2INgYYmcqb6S40LNTTb6KNGwExBMu3SBpqd2qS9uw08CuzdxndBwoKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGV3enBEWlmA0/1lRT5+BgWys=","responseParameter":{}}
        {"status":"01","msg":"Authentication failed as SMS has not reached the server.","uniquerequestId":"YCn2INgYYmMqZKS40LNTTb6KNGwExBMu3SBpqd2qS9uw08Cuzd1ndhsoKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGV+fpTTrh7RtbDSS4/KwV+EA=","responseParameter":{"encryptionKey":"c592eb91208ac6d7"}}
        {"status":"01","msg":"Invalid Mobile No.","responseCode":"58","validateResp":"01","uniquerequestId":"YCn2INgYYmMqZaS40LNTTb6KNGwExBMu3SBpqd2qS9uw08CuzdhncxooKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGV4Day82F3zWse2ndZw3bLv8=","responseParameter":{"aadharNumber":"NA","aadharFlag":"N"}}
        {"status":"01","msg":"Wrong Vmn matched via SMS","uniquerequestId":"YCn2INgYYmQobqS40LNTTb6KNGwExBMu3SBpqd2qS9uw08CuyN1ndRQoKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGVzoarLpqKbS20wIueCNICEc=","responseParameter":{}}
        {"status":"01","msg":"Your device is locked due to three consecutive failed registration attempts. Please try again after Tue Jan 28 19:29:06 IST 2025. Error Code: 99002","uniquerequestId":"YCn2INgYYmQuZKS40LNTTb6KNGUKxBMu3SBpqd2qS9uw08KuzdBndhwoKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGV+eG2erd5opRzY2eDQcpJnA=","responseParameter":{}}
        {"status":"01","msg":"Authentication is failed, please retry again after sometime.","uniquerequestId":"YCn2INgccDB3Nq613vkEA76PJTYMxBMh3SBqqd2qS9uw0Meuy9xndhsoKX9BcGljn9kVK1ihvT9dhd41S1YkruHzcrhSVQ11EmcGV6TQcCS/1Z1yQJhjVbmjsA8=","responseParameter":{"authenticationNo":"O26jfTd3edoaKP6JQBQ270d+XAo=","aadharNumber":"NA","isBomCustomer":"Y","aadharFlag":"N"}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data.get("status") == "01" and "Your device is locked due to three consecutive failed registration attempts." in data.get("msg"):
            error_message = data.get("msg")
            self.logger.warning(f"response failed, error_message: {error_message} data: {data}")
            return MahaResult(status_code=MahaResultStatusCode.DEVICE_LOCKED, error_message=error_message)
        elif data.get("status") == "01":
            error_message = data.get("msg")
            self.logger.warning(f"response failed, error_message: {error_message} data: {data}")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT, error_message=error_message)
        elif data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        response_param = data.get("responseParameter", {})
        self.user_info.customerId = response_param.get("customerId")
        self.user_info.customerName = response_param.get("customerName")
        self.user_info.key = response_param.get("encryptionKey")
        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 客户登录IB服务 暂时无用
    def customer_login_ib_service(self) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info
            )

        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        """客户登录IB服务"""
        input_param = {
            "customerId": self.user_info.customerId,
            "mobileNo": self.user_info.phone,
            "password": self.user_info.password,
            "ibPassword": self.user_info.password,
            "entityId": "BOM",
            "language": "en_US",
            "channelName": "MBANKING",
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "CustomerLoginIBService",
                        "subAction": "CustomerLoginIBService",
                        "entityId": "BOM",
                        "inputParam": input_param,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|CustomerLoginIBService"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","msg":"Mobile is Already Registered.","responseCode":"00","uniquerequestId":"OmyodZZJJWQrY/eng/1YQ73aMWIEgBYswHZgv5OoTsGg0NymyNtoZx9nXgw4BBMZrdMrJ3mInR1/r/gyUUQioOX1V7hbbwZOJl0AQB7C/+QrCynH3RXnulV+AjZIMFUo","responseParameter":{"isRegUpi":"Y","isRegMbanking":"Y","entityId":"BOM","appUpdate":{"id":3,"version":1,"entityId":"BOM","os":"Android","subVersion":34.0,"isActive":"Y","isForceUpdate":"Y","message":"New Version of Mahamobile Plus is now available. Click update.","createdTime":1701801000000,"appUrl":"https://play.google.com/store/apps/details?id=com.kiya.mahaplus"},"mobileNo":"8167411813","encryptionKey":"c592eb91208ac6d7"}}
        {"status":"01","msg":"Customer Id is required.","uniquerequestId":"","responseParameter":{}}
        {"status":"01","msg":"Invalid Credentials","responseCode":"01","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoTsGg0NymyNtoZx9nXgg4BBMbrdMrJ3mInR1/r/gyUUQioOX1V7hbbwZOJl0AQB7C/+RiVdZTPai8jO+WGNt6pHaj","responseParameter":{"Result":"No Key","rrn":"502721053847"}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 注册服务
    def complete_registration_service(self) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info
            )

        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        """完成注册服务"""
        user_details = self.generate_random_names()
        input_param = {
            "entityId": "BOM",
            "registeredChannel": "RTIB",
            "mobileNo": self.user_info.phone,
            "customerName": user_details["customerName"],
            "customerId": self.user_info.customerId,
            "firstName": user_details["firstName"],
            "lastName": user_details["lastName"],
            "emailId": "",
            "cbsmpin": EncryptionUtils.encrypt(self.user_info.mpin, self.user_info.key),
            "mpin": EncryptionUtils.encrypt_password(self.user_info.mpin),
            "language": "en_US",
            "appVersion": "1.0.34",
            "biometricEnabled": "Y",
            "registeredMode": "MBANKING",
            "isRegdUpi": "Y",
            "isRegdMbanking": "Y",
            "authenticationNo": "PWmofrXRhwFcEgpskRF7e1ZXZr8=",
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "CompleteRegistrationService",
                        "subAction": "CompleteRegistrationService",
                        "inputParam": input_param,
                        "entityId": "BOM",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|CompleteRegistrationService"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：{"status":"00","msg":"Login MPIN has been set successfully","uniquerequestId":"OmyodZZJJWQrY/eng/1ZTrjaMWIEgBYswHZpsZOoTsGg0NymyNtoZxxjXg8xBBMdrdMrJ3mInR1/r/goT0AhqPTiSbJbbxtzFm8RWwfFz+QAx823Wkj9/nBOTdyNQSNhvhkLwx4=","responseParameter":{"biometricEnabled":"Y","emailId":"","language":"en_US","mobileNo":"8167411813","encryptionKey":"c592eb91208ac6d7","transactionTime":"27 Jan 2025, 14:51:17","isGenerateTPin":"Y","customerName":"sGwpY 7KSTC","responseCode":"02","isRegdMbanking":"Y","customerId":"40292402141","isRegdUpi":"Y"}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(error_message)
            return MahaResult(error_message=error_message)
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 重置交易PIN 没有用到它
    def reset_transaction_pin(self, reset_times=1) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info
            )

        self.logger.info(f"第{reset_times}次重置tpin, phone: {self.user_info.phone}， tpin: {self.user_info.tpin}")
        """重置交易PIN"""
        input_param = {
            "entityId": "BOM",
            "language": "en_US",
            "mobileNo": self.user_info.phone,
            "credData": EncryptionUtils.encrypt_password(self.user_info.tpin),
            "cbstpin": EncryptionUtils.encrypt(self.user_info.tpin, self.user_info.key),
            "customerId": ""
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "ResetTransactionPin",
                        "subAction": "ResetTransactionPin",
                        "inputParam": input_param,
                        "deviceId": self.user_info.deviceId,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|ResetTransactionPin"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","msg":"New transaction Pin Set Successfully.","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoTsGg0NymyNtoZx9nXgg4BBMbrdMrJ3mInR1/r+kiUVU5mfLmdaRdZRxuC2A1WwYqPPmRIzyzya9Ie5ID1nsp","responseParameter":{}}
        {'status': '01', 'msg': 'New Transactions TPIN should not be matched with your last five New Transactions TPIN', 'uniquerequestId': 'Omyoe51OI2cvY/eni+8FA/nLNidL1k1oxHwq8JOrTcGg09ymyNtoZx9lXg42BBcdrdMrJ3mInR1/r+kiUVU5mfLmdaRdZRxuC2A1WwZt+ZJz312ntBHAmHPCY5cT', 'responseParameter': {}}
        {'status': '01', 'msg': 'New Transactions TPIN should not be matched with your last five New Transactions TPIN', 'uniquerequestId': 'Omyoe51OI2cvY/eniPldHLrXODNKwlRoy3ou85OrTcGg09ymyNtoZx9mXgg3BBIYrdMrJ3mInR1/r+kiUVU5mfLmdaRdZRxuC2A1WwbMgaYvya+Fp3Ywj1z4jnZ8', 'responseParameter': {}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)

        if data['status'] == "09" and "Session Expired" == data['msg']:
            if reset_times > 2:
                self.logger.warning(f"已重试{reset_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(3)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.reset_transaction_pin(reset_times+1)
        if data['status'] == "01" and data.get('msg') == "New Transactions TPIN should not be matched with your last five New Transactions TPIN":
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"response failed, error_message: {error_message} data: {data}")
            return MahaResult(status_code=MahaResultStatusCode.RESET_TPIN, error_message=error_message, user_info=self.user_info)
        elif data['status'] != "00":
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 获取banner图片
    def get_banner_images(self, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info
            )

        """获取banner图片"""
        input_param = {
            "mobileNo": self.user_info.phone,
            "language": "en_US"
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "GetBannerImages",
                        "subAction": "GetBannerImages",
                        "inputParam": input_param,
                        "entityID": "BOM",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|GetBannerImages"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：{"status":"00","msg":"SUCCESS","uniquerequestId":"OmyodZZJJWQrY/eng/1ZT7zaMWIEgBYswHZgv5OoTsGg0NymyNtoZx9mXg00BBITrdMrJ3mInR1/r/wiVnIso+7iaZ5RZw9iF4YeoOoqZUZSzYDjlpEOtwQ=","responseParameter":{"bannerList":[{"id":22,"entityId":"BOM","bannerName":"Gold Loan","imageName":"goldLoan.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/goldLoan.jpg","createdOn":1657173473000,"createdBy":"Admin","updatedOn":1657173473000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/information_on_maha_bank_gold_loan?utm_source=banner&utm_medium=mahamobile&utm_campaign=goldloan_mahamobilebanner"},{"id":23,"entityId":"BOM","bannerName":"Car loan","imageName":"carLoan.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/carLoan.jpg","createdOn":1657173473000,"createdBy":"Admin","updatedOn":1657173473000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/personal-banking/loans/car-loan?utm_source=banner&utm_medium=mahamobile&utm_campaign=carloan_mahamobilebanner"},{"id":24,"entityId":"BOM","bannerName":"DoorStep banking","imageName":"doorStepBanking.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/doorStepBanking.jpg","createdOn":1657173473000,"createdBy":"Admin","updatedOn":1657173473000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/doorstep_banking_services?utm_source=banner&utm_medium=mahamobile&utm_campaign=doorstepbanking_mahamobilebanner"},{"id":25,"entityId":"BOM","bannerName":"Maha UPI","imageName":"mahaUPI.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/mahaUPI.jpg","createdOn":1657173473000,"createdBy":"Admin","updatedOn":1657173473000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/maha_upi?utm_source=banner&utm_medium=mahamobile&utm_campaign=mahaupi_mahamobilebanner"},{"id":26,"entityId":"BOM","bannerName":"MSME loans","imageName":"msme.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/msme.jpg","createdOn":1657173473000,"createdBy":"Admin","updatedOn":1657173473000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/msme_schematic_loans?utm_source=banner&utm_medium=mahamobile&utm_campaign=msmeloans_mahamobilebanner"},{"id":27,"entityId":"BOM","bannerName":"MKSY","imageName":"mksy.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/mksy.jpg","createdOn":1657173473000,"createdBy":"Admin","updatedOn":1657173473000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/maha-krishi-samrudhi-yojana?utm_source=banner&utm_medium=mahamobile&utm_campaign=mksy_mahamobilebanner"},{"id":28,"entityId":"BOM","bannerName":"Maha Arogyam","imageName":"mahaarogyam.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/mahaarogyam.jpg","createdOn":1657277880000,"createdBy":"Admin","updatedOn":1657277880000,"updatedBy":"Admin","isActive":"Y"},{"id":29,"entityId":"BOM","bannerName":"Maha Sahyog","imageName":"mahasahyog.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/mahasahyog.jpg","createdOn":1657277882000,"createdBy":"Admin","updatedOn":1657277882000,"updatedBy":"Admin","isActive":"Y"},{"id":30,"entityId":"BOM","bannerName":"Maha Sanjeevani","imageName":"mahasanjeevani.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/mahasanjeevani.jpg","createdOn":1657277884000,"createdBy":"Admin","updatedOn":1657277884000,"updatedBy":"Admin","isActive":"Y"},{"id":31,"entityId":"BOM","bannerName":"Food Harvesting","imageName":"foodHarvesting.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/foodHarvesting.jpg","createdOn":1657277887000,"createdBy":"Admin","updatedOn":1657277887000,"updatedBy":"Admin","isActive":"Y"},{"id":32,"entityId":"BOM","bannerName":"Nationwide Awareness","imageName":"Nationwide-awareness_poster.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/Nationwide-awareness_poster.jpg","createdOn":1679300213000,"createdBy":"Admin","updatedOn":1679300213000,"updatedBy":"Admin","isActive":"Y"},{"id":33,"entityId":"BOM","bannerName":"RBI Ombudsman Scheme","imageName":"RBI-IOS_Full-Pg_English.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/RBI-IOS_Full-Pg_English.jpg","createdOn":1679300236000,"createdBy":"Admin","updatedOn":1679300236000,"updatedBy":"Admin","isActive":"Y"},{"id":34,"entityId":"BOM","bannerName":"BOM-NEWS-Maha-Mobile-Banner","imageName":"BOM-NEWS-Maha-Mobile-Banner.jpg","imagePath":"https://mahamobilemb.infrasofttech.com/mobilityMiddleware/resources/images/BOM-NEWS-Maha-Mobile-Banner.jpg","createdOn":1686811684000,"createdBy":"Admin","updatedOn":1686811684000,"updatedBy":"Admin","isActive":"Y","redirectUrl":"https://bankofmaharashtra.in/news"}],"transactionTime":"27 Jan 2025, 19:34:11"}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)

        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(3)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.get_banner_images(retry_times + 1)
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 客户登录服务
    def customer_login_service(self) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info
            )

        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        """客户登录服务"""
        input_param = {
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            },
            "entityId": "BOM",
            "language": "en_US",
            "mobileNo": self.user_info.phone,
            "customerName": "Mobile Banking User",
            "token": self.user_info.token,
            "customerId": self.user_info.customerId,
            "mpin": EncryptionUtils.encrypt_password(self.user_info.mpin),
            "sessionToken": "",
            "eMail": "",
            "authenticationNo": "",
            "biometricEnabled": "N"
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "CustomerLoginService",
                        "subAction": "CustomerLoginService",
                        "inputParam": input_param,
                        "entityID": "BOM",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|CustomerLoginService"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：{"msg":"Success","sessionId":"tiYHBHXGSYmDCkFqAlhIX4IaT2UBSoay0NwCQL9me+Fo5hPXq7AV3xI+Zghv4dWibbwJOg==","responseParameter":{"lastLogin":"27 Jan 2025, 16:16:42 IST","isSecured":"N","mpassbookDaysLimit":"90","customerInfo":{"mobileNo":"8167411813","customerName":"TLQRX AbuvS","customerId":"40292402141","id":182636299},"isTpinSet":"Y","encryptionKey":"c592eb91208ac6d7","customerName":"TLQRX AbuvS","isRegUpi":"Y","isRegMbanking":"Y","preApprovedLoanServiceFlag":"N","customerId":"40292402141","appUpdate":{"id":0,"version":0,"subVersion":0.0}},"uniquerequestId":"OmyodZZJJWQrY/enh7kNT+mKNm1ejkQtlCE6vpOoTsGg0NymyNtoZxxtXg00BBIZrdMrJ3mInR1/r/gyUUQioOX1V7hbbwZUAXwTWwvODy0LGP+sk+eJbXehaHRUUg==","status":"00"}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        # 处理 session 过期
        if data['status'] == "09" and 'Session Expired' == data.get("msg"):
            return MahaResult(status_code=MahaResultStatusCode.SESSION_EXPIRED, error_message="Session Expired")
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        session_id = EncryptionUtils.decrypt(
            data.get("sessionId", ""),
            EncryptionUtils.gen_key(input_param["mpin"], self.user_info.deviceId)
        )
        self.user_info.sessionId = session_id
        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取sessionId: {self.user_info.sessionId}")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        customer_info = data.get("responseParameter", {}).get("customerInfo", {})
        self.user_info.customerName = customer_info.get("customerName")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 读取账单
    def mini_statement_service(self, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info,
                data={"transactionDetails": []}
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        """读取账单"""
        input_param = {
            "customerName": self.user_info.customerName,
            "mobileNo": self.user_info.phone,
            "accNum": self.user_info.accountNumber,
            "accountFlag": "0",
            "language": "en_US",
            "customerId": self.user_info.customerId,
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "MiniStatementService",
                        "subAction": "MiniStatementService",
                        "entityID": "BOM",
                        "inputParam": input_param,
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|MiniStatementService"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"data":{"status":"09","msg":"Session Expired","responseParameter":{}}} 
        {
            "status":"00","msg":"SUCCESS","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXg0xBBAcrdMrJ3mInR1/r/YuTFkeueHzfrpZaBxUAXwTWwvOREdng91eViosy+Aru5ArKg==",
            "responseParameter":{
                "transactionDetails":[
                    {"tranDate":"27/01/25","serialNo":"1","drCRIndicator":"DR","tranAmount":"100","tranParticulars":" UPI / IMPS DEB UPI 502797669744/IDIB/Mr Matla Sreekanth/M4Ol4","balAfterTran":"412.5 CR"},
                    {"tranDate":"27/01/25","serialNo":"2","drCRIndicator":"DR","tranAmount":"511","tranParticulars":" UPI / IMPS DEB UPI 502714196561/fdrl/ALTHAF HUSSAIN K/Payment Ini","balAfterTran":"512.5 CR"},
                    {"tranDate":"27/01/25","serialNo":"3","drCRIndicator":"CR","tranAmount":"1000","tranParticulars":" UPI / IMPS CRE UPI 240251782873/IDIB/Mr Matla Sreekanth/Payment f","balAfterTran":"1023.5 CR"},
                    {"tranDate":"26/01/25","serialNo":"4","drCRIndicator":"DR","tranAmount":"650","tranParticulars":" UPI / IMPS DEB UPI 502613044394/ipos/GOPAL KUMAR/Payment Initiate","balAfterTran":"23.5 CR"},
                    {"tranDate":"26/01/25","serialNo":"5","drCRIndicator":"CR","tranAmount":"2","tranParticulars":" UPI / IMPS CRE UPI 906640707524/IDIB/Mr Matla Sreekanth/Payment f","balAfterTran":"673.5 CR"}],
                    "accountNo":"60517594284","opstatus":"00",
                    "transactionTime":"27 Jan 2025, 21:31:27",
                    "cust_id":"00000040294035959",
                    "customerName":"Mr. JAFAR KHAN RAHIM KHAN","rrn":"502721065562"
            }
        }
        """
        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(status_code=MahaResultStatusCode.LOGOUT, error_message=error_message)
        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 1:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            error_message = f"{data}"
            self.logger.error(f"{error_message}")
            time.sleep(2)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.mini_statement_service(retry_times + 1)
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # data.get("responseParameter") -> {"transactionDetails":[{"tranDate":"27/01/25","serialNo":"1","drCRIndicator":"DR","tranAmount":"100","tranParticulars":" UPI / IMPS DEB UPI 502797669744/IDIB/Mr Matla Sreekanth/M4Ol4","balAfterTran":"412.5 CR"},{"tranDate":"27/01/25","serialNo":"2","drCRIndicator":"DR","tranAmount":"511","tranParticulars":" UPI / IMPS DEB UPI 502714196561/fdrl/ALTHAF HUSSAIN K/Payment Ini","balAfterTran":"512.5 CR"},{"tranDate":"27/01/25","serialNo":"3","drCRIndicator":"CR","tranAmount":"1000","tranParticulars":" UPI / IMPS CRE UPI 240251782873/IDIB/Mr Matla Sreekanth/Payment f","balAfterTran":"1023.5 CR"},{"tranDate":"26/01/25","serialNo":"4","drCRIndicator":"DR","tranAmount":"650","tranParticulars":" UPI / IMPS DEB UPI 502613044394/ipos/GOPAL KUMAR/Payment Initiate","balAfterTran":"23.5 CR"},{"tranDate":"26/01/25","serialNo":"5","drCRIndicator":"CR","tranAmount":"2","tranParticulars":" UPI / IMPS CRE UPI 906640707524/IDIB/Mr Matla Sreekanth/Payment f","balAfterTran":"673.5 CR"}],"accountNo":"60517594284","opstatus":"00","transactionTime":"27 Jan 2025, 21:28:14","cust_id":"00000040294035959","customerName":"Mr. JAFAR KHAN RAHIM KHAN","rrn":"502721053960"}
        # transactionDetails[0].get("drCRIndicator") CR: 收入, DR: 支出
        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data=data.get("responseParameter")
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 查看受益人
    def view_beneficiary(self, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        """查看受益人"""
        input_param = {
            "mobileNo": self.user_info.phone,
            "entityId": "BOM",
            "customerId": self.user_info.customerId,
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            },
            "language": "en_US",
            "channelDetails": {
                "channelType": "",
                "branchCode": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "ViewBeneficiary",
                        "subAction": "ViewBeneficiary",
                        "entityID": "BOM",
                        "inputParam": input_param,
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|ViewBeneficiary"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","message":"SUCCESS","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXgw0BBYcnNwoKHyKmhREhdIiVXIoo+XhcrRVZxp+n96Iwy5zfUaSY/lllpo9zA==","responseParameter":{"PendingBeneficiaries":[{"transactionType":"ACC","beneName":"MATLASREEKANTH","beneNickName":"MATLASREEKANTH","beneficiaryStatus":"P"}],"BeneficiaryList":[{"transactionType":"ACC","beneName":"AKUMALLA","beneNickName":"AKUMALLA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ALOKPALLAI","beneNickName":"ALOKPALLAI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"AMITYADAV","beneNickName":"AMITYADAV","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ANSHU","beneNickName":"ANSHU","beneficiaryStatus":"A"}]}}
        {"status": "failed", "msg": "No Beneficiaries Found", "message": "FAILED", "uniquerequestId": "Omyoe51OI2cvY/en3/AAT+DbJTYIzkdpnHUp8ZOoTsGg09ymyNtoZx9mXg4yBBIdrdMrJ3mInR1/r+0uR0cPqO7ifb5fbwl1HcvUv1DCP7wsgEWp5ltJmyc=", "responseParameter": {"PendingBeneficiaries": [], "BeneficiaryList": [], "rrn": "505822231106"}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(2)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.view_beneficiary(retry_times + 1)
        if data['status'] == "failed" and data.get('msg') == "No Beneficiaries Found":
            self.user_info.token = data.get("uniquerequestId")
            self.logger.info(f"设置并读取token: {self.user_info.token}")
            # 定义返回结果对象
            mahaResult = MahaResult(
                is_success=True,
                status_code=MahaResultStatusCode.TRUE,
                user_info=self.user_info,
                data=data.get("responseParameter", {})
            )
            self.logger.info(f"response ok, return mahaResult: {mahaResult}")
            return mahaResult
        elif data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        # data 示例数据: {"PendingBeneficiaries":[],"BeneficiaryList":[{"transactionType":"ACC","beneName":"AKUMALLA","beneNickName":"AKUMALLA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ALOKPALLAI","beneNickName":"ALOKPALLAI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"AMITYADAV","beneNickName":"AMITYADAV","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ANSHU","beneNickName":"ANSHU","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ARIVILLI","beneNickName":"ARIVILLI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ARVAJKHAN","beneNickName":"ARVAJKHAN","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ASHISHKUMARJATAV","beneNickName":"ASHISHKUMARJATAV","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ASHUSINGHCHAUHAN","beneNickName":"ASHUSINGHCHAUHAN","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ATIKULMONDAL","beneNickName":"ATIKULMONDAL","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"BERSPTIYAKUMAR","beneNickName":"BERSPTIYAKUMAR","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"BHAGIRATHMAL","beneNickName":"BHAGIRATHMAL","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"BHARATKUMAR","beneNickName":"BHARATKUMAR","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"BHIMLABAIBITHALE","beneNickName":"BHIMLABAIBITHALE","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"BUKKE","beneNickName":"BUKKE","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"CHAUDHURIAK","beneNickName":"CHAUDHURIAK","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"CHINTALAGOURAMMA","beneNickName":"CHINTALAGOURAMMA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"DEEPAKSINGH","beneNickName":"DEEPAKSINGH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"DNINDINREDDY","beneNickName":"DNINDINREDDY","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"DOPEKASHMAINA","beneNickName":"DOPEKASHMAINA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"GADEELASRIKANTH","beneNickName":"GADEELASRIKANTH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"GAURAV","beneNickName":"GAURAV","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"GUDDU","beneNickName":"GUDDU","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"HARISHABS","beneNickName":"HARISHABS","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"INDEJITSINGH","beneNickName":"INDEJITSINGH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"JAYAPRAKASHPENUMAJJI","beneNickName":"JAYAPRAKASHPENUMAJJI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"JITEN","beneNickName":"JITEN","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"KAMMALAPELLISRIKANTH","beneNickName":"KAMMALAPELLISRIKANTH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"KANDOJUSRIHARI","beneNickName":"KANDOJUSRIHARI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"KARTHEEKKONDA","beneNickName":"KARTHEEKKONDA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"KUMMAMATA","beneNickName":"KUMMAMATA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"LOLICE","beneNickName":"LOLICE","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"MADHUSUDAN","beneNickName":"MADHUSUDAN","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"MAHADEVBISWAL","beneNickName":"MAHADEVBISWAL","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"MAHENDRASINGH","beneNickName":"MAHENDRASINGH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"MANGALAT","beneNickName":"MANGALAT","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"MUNEERKHAN","beneNickName":"MUNEERKHAN","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"NANCHARAYYA","beneNickName":"NANCHARAYYA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"NANTHAKUMAR","beneNickName":"NANTHAKUMAR","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"NARENDRA","beneNickName":"NARENDRA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"NPARAJUKUMAR","beneNickName":"NPARAJUKUMAR","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"PAT","beneNickName":"PAT","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"PRASHANT","beneNickName":"PRASHANT","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"PRI","beneNickName":"PRI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"RKBHANUPRAKASH","beneNickName":"RKBHANUPRAKASH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"ROHIT","beneNickName":"ROHIT","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SAMEER","beneNickName":"SAMEER","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SANTHOSH","beneNickName":"SANTHOSH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SANTOS","beneNickName":"SANTOS","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SHAILESHRAM","beneNickName":"SHAILESHRAM","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SHAKEEL","beneNickName":"SHAKEEL","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SOMASEKHAREDDY","beneNickName":"SOMASEKHAREDDY","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SREENUMANDA","beneNickName":"SREENUMANDA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SUB","beneNickName":"SUB","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SUBBARAYUD","beneNickName":"SUBBARAYUD","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SUBHASH","beneNickName":"SUBHASH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SUNILKUMAR","beneNickName":"SUNILKUMAR","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SURA","beneNickName":"SURA","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SURYAKANTTIWARI","beneNickName":"SURYAKANTTIWARI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"SUVENDUSIAL","beneNickName":"SUVENDUSIAL","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"TADEPUPRAKASH","beneNickName":"TADEPUPRAKASH","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"THATI","beneNickName":"THATI","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"TORUKMAKTO","beneNickName":"TORUKMAKTO","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"VIJAYKUMAR","beneNickName":"VIJAYKUMAR","beneficiaryStatus":"A"},{"transactionType":"ACC","beneName":"VIVI","beneNickName":"VIVI","beneficiaryStatus":"A"}]}
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data=data.get("responseParameter", {})
        )
        self.logger.info(f"response ok, return mahaResult: {mahaResult}")
        return mahaResult

    # 查看受益人详细信息
    def view_beneficiary_details(self, beneficiary: Beneficiary, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取beneficiary: {beneficiary.__str__()}")
        nick_name = beneficiary.nick_name
        """查看受益人详细信息"""
        input_param = {
            "mobileNo": self.user_info.phone,
            "entityId": "BOM",
            "customerId": self.user_info.customerId,
            "beneficiaryNickName": nick_name,
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            },
            "language": "en_US",
            "rrn": ""
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "ViewBeneficiaryDetails",
                        "subAction": "ViewBeneficiaryDetails",
                        "entityID": "BOM",
                        "inputParam": input_param,
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|ViewBeneficiaryDetails"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"01","responseCode":"96","uniquerequestId":"OmyodZZJJWQrY/eng/1ZT7zaMWIEgBYswHZgv5OoTsGg0NymyNtoZx9mXg8zBBcTnNwoKHyKmhREhdIiVXIoo+XhcrRVZxp+IGsRUwHH71N1d4Fp7U/nkyyFRlRxc9I=","responseParameter":{"transactionTime":"27 Jan 2025, 19:53:59","rrn":"502719657645"}}
        {"status":"00","responseCode":"00","message":"SUCCESS","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXg80BBIanNwoKHyKmhREhdIiVXIoo+XhcrRVZxp+IGsRUwHH73SyzqfSXjKZbNmrs8iKNoM=","responseParameter":{"getBeneficiaryDetails":[{"beneIfsc":"IDIB000G023","beneAccNo":"7932051569","beneName":"Matla Sreekanth","beneNickName":"MATLASREEKANTH","beneMobileNo":"7207609925","beneficiaryStatus":"I","beneBankName":"INDIAN BANK","beneBranchName":"GUNTUR","beneAccountType":"10-SAVINGS","address1":"NA","address2":".","address3":".","pinccode":"NA","emailId":"NA","relationship":"NA"}]}}
        """
        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(2)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.view_beneficiary_details(beneficiary, retry_times + 1)
        elif data['status'] == "01" and 'responseCode' in data and data.get("responseCode") == "96":
            error_message = f"Beneficiary is not exist, status: {data['status']}, responseCode: {data['responseCode']}"
            self.logger.warning(f"response error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.BENEFICIARY_INFO_ERROR)
        elif data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        beneficiary_details = data.get("responseParameter", {}).get("getBeneficiaryDetails", [])[0]

        self.beneficiary = Beneficiary()
        self.beneficiary.bene_ifsc = beneficiary_details.get("beneIfsc", "")
        self.beneficiary.bene_acc_no = beneficiary_details.get("beneAccNo", "")
        self.beneficiary.bene_name = beneficiary_details.get("beneName", "")
        self.beneficiary.nick_name = beneficiary_details.get("beneNickName", "")
        self.beneficiary.mobile_no = beneficiary_details.get("beneMobileNo", "")
        self.beneficiary.beneficiary_status = beneficiary_details.get("beneficiaryStatus", "")
        self.beneficiary.bene_account_type = beneficiary_details.get("beneAccountType", "")

        self.logger.info(f"设置并读取beneficiary: {self.beneficiary.__str__()}")

        # 定义返回结果对象
        # data 示例数据: {"getBeneficiaryDetails":[{"beneIfsc":"IDIB000G023","beneAccNo":"7932051569","beneName":"Matla Sreekanth","beneNickName":"MATLASREEKANTH","beneMobileNo":"7207609925","beneficiaryStatus":"I","beneBankName":"INDIAN BANK","beneBranchName":"GUNTUR","beneAccountType":"10-SAVINGS","address1":"NA","address2":".","address3":".","pinccode":"NA","emailId":"NA","relationship":"NA"}]}
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data=self.beneficiary.to_dict(),
            beneficiary=self.beneficiary,
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 删除受益人
    def delete_beneficiary(self, nick_name, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取要删除受益人的昵称: {nick_name}")
        """删除受益人"""
        input_param = {
            "customerId": self.user_info.customerId,
            "language": "en_US",
            "mobileNo": self.user_info.phone,
            "nickName": nick_name,
            "rrn": "",
            "userId": "",
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "DeleteBeneficiary",
                        "subAction": "DeleteBeneficiary",
                        "entityID": "BOM",
                        "inputParam": input_param,
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|DeleteBeneficiary"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)

        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)

        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(2)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.delete_beneficiary(nick_name, retry_times + 1)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data=data.get("responseParameter", {})
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 添加受益人
    def add_beneficiary(self, beneficiary: Beneficiary, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取beneficiary: {beneficiary.__str__()}")
        """添加受益人"""
        input_param = {
            "entityId": "BOM",
            "paymentMode": "CPD",
            "flag": "2",
            "customerId": self.user_info.customerId,
            "mobileNo": self.user_info.phone,
            "transactionType": "CPD",
            "language": "en_US",
            "benefecDetail": {
                "benefId": self.get_random_number(),
                "benCustName": beneficiary.bene_name,
                "mmid": "",
                "mobileNo": self.user_info.phone,
                "beneficiaryAccountNo": beneficiary.bene_acc_no,
                "beneIFSC": beneficiary.bene_ifsc,
                "isFavourite": "",
                "nickName": beneficiary.bene_name.replace(" ", ""),
                "accType": "10"
            },
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "AddBeneficiary",
                        "subAction": "AddBeneficiary",
                        "inputParam": input_param,
                        "entityID": "BOM",
                        "language": "en_US",
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|AddBeneficiary"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","msg":"Beneficiary added Successfully.Please approve the beneficiary","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXg0xBBEardMrJ3mInR1/r/ojRnIoo+XhcrRVZxp+dPgaDtprFBFbxdhO6340rg==","responseParameter":{"beneficiaryAccountNo":"7932051569","beneficiaryName":"Matla Sreekanth","nickName":"MatlaSreekanth","rrn":"502721065844"}}
        {"status":"01","msg":"Beneficiary with given Nick Name already exists.","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXgwzBBcardMrJ3mInR1/r/ojRnIoo+XhcrRVZxp+Qo89Npnb0gPjukW2I7W6mQ==","responseParameter":{"rrn":"502721113598"}}
        {"status": "01", "msg": "Beneficiary cannot be added now. Please try later.", "uniquerequestId": "Omyoe51OI2cvY/ennrxeGf3cJTkI30B7wHMx55OqSMGg0tymyNtoZx9nXg0xBBITrdMrJ3mInR1/r/ojRnIoo+XhcrRVZxp+qXnrQSMU9ltlcHO+67osaw==", "responseParameter": {"rrn": "506023419556"}} 
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(status_code = MahaResultStatusCode.FALSE, error_message=error_message)
        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(2)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.add_beneficiary(beneficiary, retry_times + 1)
        elif data['status'] == "01" and data.get("msg") == "Beneficiary with given Nick Name already exists.":
            error_message = f"Beneficiary with given Nick Name already exists. {beneficiary.bene_name}"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(is_success= True, status_code = MahaResultStatusCode.ADDED_BENEFICIARY_REPEAT, error_message=error_message)
        elif data['status'] == "01" and data.get("msg") == "Beneficiary cannot be added now. Please try later.":
            error_message = f"受益人添加失败, account: {beneficiary.bene_acc_no}, ifsc: {beneficiary.bene_ifsc}"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(status_code=MahaResultStatusCode.ADDED_BENEFICIARY_FAILED, error_message=error_message)
        elif data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        # self.user_info.token = data.get("uniquerequestId")
        # self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        # data 示例数据: {"beneficiaryAccountNo":"7932051569","beneficiaryName":"Matla Sreekanth","nickName":"MatlaSreekanth","rrn":"502719657230"}
        beneficiary.bene_name = data.get("responseParameter").get("beneficiaryName")
        beneficiary.nick_name = data.get("responseParameter").get("nickName")
        mahaResult = MahaResult(
            is_success = True,
            status_code=MahaResultStatusCode.TRUE,
            user_info = self.user_info,
            data = data.get("responseParameter"),
            beneficiary = beneficiary
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 查看账号的昵称 （暂时废弃不用，因为有些账号查不到）
    def verify_beneficiary_imps(self, beneficiary: Beneficiary, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取beneficiary: {beneficiary.__str__()}")
        input_param = {
            "beneficiaryAccountNo": beneficiary.bene_acc_no,
            "beneIFSC": beneficiary.bene_ifsc,
            "customerId": self.user_info.customerId,
            "mobileNo": self.user_info.phone,
            "entityId": "BOM",
            "channelName": "MB"
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "VerifyBeneficiaryImps",
                        "subAction": "VerifyBeneficiaryImps",
                        "inputParam": input_param,
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|VerifyBeneficiaryImps"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","uniquerequestId":"OmyodZZJJWQrY/eng/1YQ73aMWIEgBYswHZgv5OoTsGg0NymyNtoZx9nXg4yBBcYrdMrJ3mInR1/r+0iUFkrtMLidbJabwtuBXwcewXb75wfj8LNhqVUWz7rZha1cOg=","responseParameter":{"Imps_response":"{\"refNo\":\"502721954560\",\"rrNo\":\"502721233652\",\"status\":\"SUCCESS\",\"responseCode\":\"00\",\"message\":\"NA\",\"internalRefNo\":\"P120250127210253675891\",\"benefName\":\"Matla Sreekanth\",\"error\":false}","benefName":"Matla Sreekanth","internalRefNo":"P120250127210253675891","responseCode":"00","rrn":"502721954560"}}
        {'status': '01', 'msg': 'Failure', 'uniquerequestId': 'Omyoe51OI2cvY/ennrxeGf3cJTkI30B7wHMx55OqS8Gg0tymyNtoZxxjXg83BBIerdMrJ3mInR1/r+0iUFkrtMLidbJabwtuBXwcewXb74ogIeLvpbdAARdziHTWdW4=', 'responseParameter': {'rrn': '506117527530'}}
        {"status": "01", "msg": "Failure", "uniquerequestId": "Omyoe51OI2cvY/ennrxeGf3cJTkI30B7wHMx55OqSsGg0tymyNtoZxxlXgk3BBEbrdMrJ3mInR1/r+0iUFkrtMLidbJabwtuBXwcewXb76vKYIUzHT1gsYaS1haSIuI=", "responseParameter": {"rrn": "506211510856"}}  
        """
        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)

        if (data['status'] == "09" and "Session Expired" == data['msg']):
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(3)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.verify_beneficiary_imps(beneficiary, retry_times + 1)

        if (data['status'] == "01" and "Failure" == data['msg']):
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            time.sleep(15)
            return self.verify_beneficiary_imps(beneficiary)

        if data['status'] == "01" and 'responseParameter' in data and data['msg'] == 'Failure':
            responseParameter = data.get("responseParameter", {})
            if "Imps_response" in responseParameter:
                imps_response = json.loads(responseParameter.get("Imps_response"))
                if "status" in imps_response and imps_response.get("status") == "ERROR":
                    error_message = imps_response.get("message")
                    return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.BENEFICIARY_INFO_ERROR)
            error_message = f"查询受益人名称时，发现未处理的结果"
            self.logger.error(f"{error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.ADDED_BENEFICIARY_FAILED)

        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        benef_name = data.get("responseParameter", {}).get("benefName")
        self.logger.info("VerifyBeneficiaryImps, benefName: %s", benef_name)
        self.beneficiary = beneficiary
        self.beneficiary.bene_name = benef_name
        self.beneficiary.nick_name = benef_name.replace(" ", "").upper()

        self.logger.info(f"设置并读取beneficiary: {self.beneficiary.__str__()}")

        # 定义返回结果对象
        # data 示例数据: {"Imps_response":"{\"refNo\":\"502720688017\",\"rrNo\":\"502720229175\",\"status\":\"SUCCESS\",\"responseCode\":\"00\",\"message\":\"NA\",\"internalRefNo\":\"P120250127200035639201\",\"benefName\":\"Matla Sreekanth\",\"error\":false}","benefName":"Matla Sreekanth","internalRefNo":"P120250127200035639201","responseCode":"00","rrn":"502720688017"}
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data= data.get("responseParameter"),
            beneficiary= self.beneficiary
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 申请审核受益人
    def approve_beneficiary(self, beneficiary: Beneficiary, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取beneficiary: {beneficiary.__str__()}")
        input_param = {
            "benefecDetail": {
                "nickName": beneficiary.nick_name,
                "beneType": "Other Bank",
                "benCustName": beneficiary.nick_name
            },
            "channelName": "MBANKING",
            "credData": EncryptionUtils.encrypt_password(self.user_info.tpin),
            "customerId": self.user_info.customerId,
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            },
            "entityId": "BOM",
            "mobileNo": self.user_info.phone
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "ApproveBeneficiary",
                        "subAction": "ApproveBeneficiary",
                        "inputParam": input_param,
                        "entityID": "BOM",
                        "language": "en_US",
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|ApproveBeneficiary"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"01","msg":"No of TPIN tries Exceeded","uniquerequestId":"OmyodZZJJWQrY/eng/1YQ73aMWIEgBYswHZgv5OoTsGg0NymyNtoZx9nXg8wBBYerdMrJ3mInR1/r/o3UkIiu+XFfrlZYAFkDW8XSy6xPNJOzeVitXhzUn7Xu3c=","responseParameter":{"transactionTime":"27 Jan 2025, 20:50:45","rrn":"502720904065"}}
        {"status":"01","msg":"You have exceeded the maximum number of attempts, MTPIN will be auto unlocked after 24 hours from the last incorrect attempt.","uniquerequestId":"OmyodZZJJWQrY/eng/1YQ73aMWIEgBYswHZgv5OoTsGg0NymyNtoZx9nXg4yBBcerdMrJ3mInR1/r/o3UkIiu+XFfrlZYAFkDW8XS/vTOgLnmTDjYeU9Tk/WEWY=","responseParameter":{"transactionTime":"27 Jan 2025, 21:02:55","rrn":"502721954715"}}
        {"status":"01","msg":"Please enter valid MTPIN.","uniquerequestId":"OmyodZZJJWQrY/eng/1ZT7zaMWIEgBYswHZgv5OoTsGg0NymyNtoZx9mXg8zBBccrdMrJ3mInR1/r/o3UkIiu+XFfrlZYAFkDW8XS/p7X9huxDIKNOGln78RQSw=","responseParameter":{"transactionTime":"27 Jan 2025, 19:53:57","rrn":"502719657437"}}
        {"status":"01","msg":"Fail to approve beneficiary.","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXgwzBBcbrdMrJ3mInR1/r/o3UkIiu+XFfrlZYAFkDW8XSzQYEybrHCNSruSab2koxoo=","responseParameter":{}}
        {"status":"00","msg":"Beneficiary has been approved Successfully","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXgw0BBcerdMrJ3mInR1/r/o3UkIiu+XFfrlZYAFkDW8XS1MbOZVW+ejC4p+tIVwKvnQ=","responseParameter":{"beneficiaryName":"MATLASREEKANTH","rrn":"502721117826"}}
        """

        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)

        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(3)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.approve_beneficiary(beneficiary, retry_times + 1)
        elif data['status'] == "01" and data.get("msg") == "Please enter valid MTPIN.":
            error_message = f"需要修改正确的TPIN"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.TPIN_ERROR)
        elif data['status'] == "01" and data.get("msg") == "Fail to approve beneficiary.":
            if retry_times > 2:
                error_message = f"需要再次申请审核"
                self.logger.error(f"已重试{retry_times}次，仍然失败，{error_message} data: {data}")
                return MahaResult(
                    is_success=False,
                    error_message=error_message,
                    status_code=MahaResultStatusCode.FAIL_TO_APPROVE_BENEFICIARY
                )
            time.sleep(3)
            return self.approve_beneficiary(beneficiary, retry_times + 1)
        elif data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        # self.user_info.token = data.get("uniquerequestId")
        # self.logger.info(f"设置并读取token: {self.user_info.token}")

        # 定义返回结果对象
        # 成功的示例数据: { "beneficiaryName": "MATLASREEKANTH", "rrn": "502721117826" }
        beneficiary.nick_name = data.get("responseParameter").get("beneficiaryName")
        self.beneficiary=beneficiary
        self.logger.info(f"设置并读取beneficiary: {self.beneficiary.__str__()}")
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data= data.get("responseParameter"),
            beneficiary=beneficiary
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    # 查询账户详情
    def account_enquiry(self, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        input_param = {
            "mobileNo": self.user_info.phone,
            "accountno": self.user_info.accountNumber,
            "entityId": "BOM",
            "language": "en_US"
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "AccountEnquiry",
                        "subAction": "AccountEnquiry",
                        "entityID": "BOM",
                        "inputParam": input_param,
                        "mobileNo": self.user_info.phone,
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|AccountEnquiry"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)

        """
        data示例数据：
        """
        self.logger.info(f"响应字典数据: {response_data_str}")
        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(2)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.account_enquiry(retry_times + 1)
        if data['status'] == "01" and "FAILED" == data['msg']:
            self.logger.warning(f"查询账号信息不正常, data: {data}")
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.RESPONSE_01_FAILED
            )
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        self.user_info.token = data.get("uniquerequestId")
        self.logger.info(f"设置并读取token: {self.user_info.token}")

        data = data.get("responseParameter")

        # 定义返回结果对象
        # 成功的示例数据: { "transactionTime": "27 Jan 2025, 21:54:02", "rrn": "502721155432" }
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.TRUE,
            user_info=self.user_info,
            data= data,
            account_balance = AccountBalance(data.get("AvailableBalance"), data.get("CurrentBalance"), data.get("AmountOnHold"))
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

    def get_response_data_str(self, data) -> str:
        if data is None:
            return ""
        if isinstance(data, dict):
            response_data_str = json.dumps(data)
        elif isinstance(data, str):
            response_data_str = data
        else:
            response_data_str = f"发现未知的数据类型, type(data): {type(data)}"
        return response_data_str

    # 转账
    def funds_transfer_service(self, beneficiary: Beneficiary, retry_times: int = 0) -> MahaResult:

        if self.local_mock:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.FALSE,
                user_info=self.user_info
            )

        self.logger.info(f"读取sessionId: {self.user_info.sessionId}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取token: {self.user_info.token}, user_info: {self.user_info.__str__()}")
        self.logger.info(f"读取beneficiary: {beneficiary.__str__()}")
        input_param = {
            "txnId": self.get_txn_id(),
            "paymentMode": beneficiary.payment_mode,
            "txnType": "01",
            "credData": EncryptionUtils.encrypt_password(self.user_info.tpin),
            "mpin": "NA",
            "entityId": "BOM",
            "language": "en_US",
            "mobileNo": self.user_info.phone,
            "customerName": self.user_info.customerId,
            "sessionToken": "",
            "channelName": "MBANKING",
            "remarks": beneficiary.orders_df_code,
            "customerId": self.user_info.customerId,
            "txnAmount": beneficiary.transfer_amount,
            "channelRefId": self.get_secure_number(),
            "payerDetails": {
                "payerAccount": self.user_info.accountNumber,
                "payerAccountType": "Current Account",
                "payerMobile": self.user_info.phone,
                "payerIfsc": "",
                "payerMmid": "",
                "payerName": self.user_info.customerName
            },
            "payeeDetails": {
                "payeeCode": "",
                "payeeAccount": beneficiary.bene_acc_no,
                "payeeMmid": "",
                "payeeName": beneficiary.bene_name,
                "payeeAccountType": beneficiary.bene_account_type,
                "payeeType": "ACC",
                "payeeIfsc": beneficiary.bene_ifsc,
                "payeeMobile": "",
                "payeeAddr": "",
                "payeeAadhaarNum": ""
            },
            "device": {
                "token": self.user_info.token,
                "app": "BOM",
                "deviceId": self.user_info.deviceId,
                "deviceIp": "",
                "deviceOs": self.user_info.os,
                "deviceVersion": self.user_info.osVersion,
                "longitude": self.user_info.longitude,
                "latitude": self.user_info.latitude,
                "location": self.user_info.location,
                "imei1": "",
                "imei2": "",
                "imsi": "",
                "operatorId": "SIM1",
                "simSerialNo": "",
                "telecom": "",
                "ipv4": "",
                "ipv6": self.user_info.ipv6Address,
                "uuid": ""
            }
        }
        try:
            url = "https://mahamobilemb.infrasofttech.com:7071/mobilityMiddleware/services/request"
            response_result = self.make_request(
                url = url,
                payload = {
                    "data1": json.dumps({
                        "action": "FundsTransferService",
                        "subAction": "FundsTransferService",
                        "inputParam": input_param,
                        "entityID": "BOM",
                        "language": "en_US",
                        "sessionId": self.user_info.sessionId,
                        "customerId": self.user_info.customerId,
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                    }),
                    "data2": json.dumps({
                        "entityID": "BOM",
                        "appID": "com.kiya.mahaplus",
                        "deviceId": self.user_info.deviceId,
                        "mobileNo": self.user_info.phone,
                        "st": self.user_info.deviceId,
                        "version": "1.0.34"
                    }),
                    "uniquerequestId": f"{self.user_info.customerId or 'null'}|{self.user_info.deviceId}|{self.get_formatted_current_datetime()}|MBANKING|FundsTransferService"
                },
                headers = self.headers,
                max_retries = 2,
                method_name=get_current_method_name()
            )
            if not response_result.is_success:
                return response_result
            response_result_data = ResponseResult(**response_result.data)

        except Exception as e:
            error_message= f"请求接口异常：{e}"
            self.logger.error(f"response failed, {error_message}")
            return MahaResult(error_message=error_message)
        data = response_result_data.data

        response_data_str = self.get_response_data_str(data)
        
        """
        data示例数据：
        {"status":"00","msg":"Transaction Completed Successfully","response":"","responseCode":"00","cbsResponseCode":"00","message":"SUCCESS","uniquerequestId":"OmyodZBNJmMjYv+ng/1aSr7aMWIEgBYswHZgv5OoQcGg0NymyNtoZx1kXg80BBIardMrJ3mInR1/r/0yTFQ+mfLmdaRaYxpUAXwTWwvODr4WS6GNOhA3RupGwiqO9g==","responseParameter":{"transactionTime":"27 Jan 2025, 21:54:02","rrn":"502721155432"}}
        {"status":"01","msg":"Remitter Account blocked.","responseCode":"ERROR","error":"00","message":"Remitter Account blocked.","uniquerequestId":"OmyodZFII28rYPKnh+8NF+rQPGxO11gsxWc6t5OqTcGg0tymyNtoZxxsXgkxBBYZrdMrJ3mInR1/r/0yTFQ+mfLmdaRaYxpUAXwTWwvOipXYLTcoB51ff4yLamILLg==","responseParameter":{"transactionTime":"04 Mar 2025, 18:41:43","rrn":"506318015480"}}
        {"status": "01", "msg": "There are some connectivity issues, please try after sometime", "responseCode": "001", "error": "00", "uniquerequestId": "Omyoe51OI2cvY/ennrxeGf3cJTkI30B7wHMx55OrSsGg0tymyNtoZxxgXggyBBMbrdMrJ3mInR1/r/0yTFQ+mfLmdaRaYxpUAXwTWwvOb65HnbNwr4P0tdPCGzH7pg==", "responseParameter": {"transactionTime": "13 Mar 2025, 14:52:11", "rrn": "507214904818"}} 
        """
        self.logger.info(f"响应字典数据: {response_data_str}")

        if 'status' not in data:
            error_message = f"响应数据异常，没有参数：status"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message)
        if data['status'] == "09" and "Session Expired" == data['msg']:
            if retry_times > 2:
                self.logger.warning(f"已重试{retry_times}次，仍然失败")
                return MahaResult(status_code= MahaResultStatusCode.SESSION_EXPIRED, error_message=data['msg'])
            time.sleep(3)
            mahaResult = self.customer_login_service()
            if not mahaResult.is_success and (MahaResultStatusCode.LOGOUT == mahaResult.status_code or MahaResultStatusCode.SESSION_EXPIRED == mahaResult.status_code):
                return mahaResult
            return self.funds_transfer_service(beneficiary, retry_times + 1)
        if data['status'] == "01" and "Remitter Account blocked." == data['msg']:
            error_message = f"{data['msg']}"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.LOGOUT)
        if data['status'] == "09" and "Please enter valid MTPIN." == data['msg']:
            error_message = f"需要修改正确的TPIN"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.TPIN_ERROR)
        if data['status'] == "01" and "Please enter valid MTPIN." == data['msg']:
            error_message = f"需要修改正确的TPIN"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.TPIN_ERROR)
        if data['status'] == "01" and "You have exceeded the maximum number of attempts" in data['msg']:
            error_message = f"Account blocked"
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.ACCOUNT_BLOCKED)
        if data['status'] == "01" and "Credit not allowed on same account." in data['msg']:
            error_message = f"You can't transfer money to yourself."
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.CANNOT_TRANSFER_TO_YOURSELF)
        if data['status'] == "01" and "There are some connectivity issues" in data['msg']:
            error_message = f"There are some connectivity issues, please try after sometime."
            self.logger.error(f"response failed, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.FUND_SOME_CONNECTIVITY_ISSUES)
        if data['status'] == "09" and "No of TPIN tries Exceeded" == data['msg']:
            error_message = data['msg']
            self.logger.error(f"TPIN尝试错误次数过多, {error_message} data: {data}")
            return MahaResult(error_message=error_message, status_code=MahaResultStatusCode.TPIN_ERROR)
        if data['status'] == "01" and "Remitter Account blocked." == data['msg']:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.ACCOUNT_BLOCKED,
                error_message = data['msg']
            )
        if data['status'] == "01" and "NA" == data['msg']:
            return MahaResult(
                is_success=False,
                status_code=MahaResultStatusCode.ACCOUNT_BLOCKED,
                error_message = MahaResultStatusCode.TRANSFER_BLOCKED.en_cue_words
            )
        if data['status'] != "00" or 'responseParameter' not in data:
            error_message = f"Failed response, status: {data['status']}, msg: {data['msg']}"
            self.logger.warning(f"未处理的响应数据 error: {error_message}, data: {data}")
            return MahaResult(error_message=error_message)

        # self.user_info.token = data.get("uniquerequestId")
        # self.logger.info(f"设置并读取token: {self.user_info.token}")
        if "NEFT" == beneficiary.payment_mode:
            if "referenceId" not in data or "status" not in data.get("responseParameter") or "O.K." != data.get("responseParameter").get("status"):
                error_message = f"付款完成，但响应结果不符合逾期，不包含属性referenceId, 或status!='O.K.', {json.dumps(data)}"
                self.logger.error(error_message)
                return MahaResult(status_code=MahaResultStatusCode.LOGOUT, error_message=error_message)
            beneficiary.utr = data.get("referenceId")

        # 定义返回结果对象
        # 成功的示例数据: { "transactionTime": "27 Jan 2025, 21:54:02", "rrn": "502721155432" }
        mahaResult = MahaResult(
            is_success=True,
            status_code=MahaResultStatusCode.PAID_SUCCESS,
            user_info=self.user_info,
            data= data.get("responseParameter"),
            beneficiary=beneficiary
        )
        self.logger.info(f"user_info: {self.user_info.__str__()}, return mahaResult: {mahaResult}")
        return mahaResult

# 获得要发送短信的目标号码及内容
def get_vmn(account_number, account_password, phone):
    # 创建用户信息实例
    user_info = UserInfo()
    user_info.accountNumber = account_number
    user_info.password = account_password
    user_info.phone = phone
    user_info.os = "Android"
    user_info.osVersion = "13"
    user_info.deviceId = generate_android_13_device_id()
    user_info.latitude = "40.7128"
    user_info.longitude = "-74.0060"
    user_info.location = "New York"
    user_info.ipv6Address = "FE80::021A:2BFF:FE3C:4D5E"
    user_info.mpin = "2580"
    user_info.tpin = "1359"
    user_info.key = "c592eb91208ac6d7"

    proxies = {
        'http': 'socks5h://ceshi:ceshi@34.131.66.127:13563',
        'https': 'socks5h://ceshi:ceshi@34.131.66.127:13563'
    }

    # 创建主类实例，使用配置好的logger
    logger = setup_logger()
    maha = MahaRequest(user_info=user_info, proxies=proxies, logger=logger)

    # 执行操作流程
    result = maha.get_vmn()
    logger.info(f"result: {result}")
    return result

if __name__ == '__main__':
    get_vmn('60517594284', 'Ana@321@@', '7207609925')