import json
from typing import Optional, NamedTuple

from urllib3 import BaseHTTPResponse

from encryption_utils import EncryptionUtils

# 检查是否json并包含指定key
def is_valid_json_with_keys(json_string, required_keys):
    try:
        # 尝试解析 JSON 字符串
        data = json.loads(json_string)

        # 检查解析后的数据是否为字典
        if not isinstance(data, dict):
            return False

        # 检查所有必需键是否存在于字典中
        for key in required_keys:
            if key not in data:
                return False

        return True
    except json.JSONDecodeError:
        # 如果解析失败，则字符串不是有效的 JSON
        return False

class PreRequestResult(NamedTuple):
    request_data: dict = {}
    action: str = ""

class ResponseResult(NamedTuple):
    status: int = -9
    is_success: bool = False
    data: dict = {}
    data_str: str = ""
    error_message: str = ""


class EncryptionInterceptor:
    def __init__(self, user_info, logger):
        self.user_info = user_info
        self.logger = logger
        
    def pre_request(self, request_body: dict, method_name=None) -> PreRequestResult:
        """在请求发送前处理请求数据"""
        if not request_body:
            return PreRequestResult(request_body, None)
            
        if all(key in request_body for key in ["data1", "data2", "uniquerequestId"]):
            unique_request_id = request_body["uniquerequestId"]
            data1 = request_body["data1"]
            data2 = request_body["data2"]
            
            action = unique_request_id.split("|")[-1]
            is_vmn_or_mobile_verification = action in ["GetVMN", "MobileVerificationService"]
            
            self.logger.info(f"{method_name}(), request_body: {request_body}")
            # 生成加密key
            if is_vmn_or_mobile_verification:
                key = EncryptionUtils.gen_key(self.user_info.key, self.user_info.deviceId)
                self.logger.info(f"{method_name}(), 加解密key: {key}, key: {self.user_info.key}, device_id: {self.user_info.deviceId}")
                action = "key"
            elif "sessionId" in data1:
                key = EncryptionUtils.gen_key(self.user_info.sessionId, self.user_info.deviceId)
                self.logger.info(f"{method_name}(), 加解密key: {key}, session_id: {self.user_info.sessionId}, device_id: {self.user_info.deviceId}")
                action = "sessionId"
            else:
                key = EncryptionUtils.gen_key(self.user_info.phone, self.user_info.deviceId)
                self.logger.info(f"{method_name}(), 加解密key: {key}, phone: {self.user_info.phone}, device_id: {self.user_info.deviceId}")
                action = "phone"
            # 构建新的请求体
            encrypted_body = {
                "data1": EncryptionUtils.encrypt(data1, key),
                "data2": EncryptionUtils.encrypt(data2, key),
                "uniquerequestId": EncryptionUtils.encrypt(unique_request_id, self.user_info.key),
                "entityId": "BOM",
                "appVersion": "1.0.34",
                "deviceId": self.user_info.deviceId
            }
            
            if not is_vmn_or_mobile_verification:
                encrypted_body["mobileNo"] = self.user_info.phone
                
            return PreRequestResult(encrypted_body, action)
            
        return PreRequestResult(request_body, None)
        
    def post_response(self, response: BaseHTTPResponse, action: Optional[str] = None, method_name=None) -> ResponseResult:
        """处理响应数据"""
        if not response.data:
            return ResponseResult(status = response.status, error_message = "response.data 响应数据为空")
            
        response_body = response.data.decode('utf-8')
        action = action or getattr(self, 'current_action', None)
        
        self.logger.info(f"{method_name}() action: {action}, responseBody: {response_body}")
        
        try:
            response_data_dict = json.loads(response_body)
            if "data" not in response_data_dict:
                return ResponseResult(status = response.status, is_success= True, data = response_data_dict)

            # 根据不同action解密
            if action == "key":
                key = EncryptionUtils.gen_key(self.user_info.key, self.user_info.deviceId)
                self.logger.info(f"{method_name}(), 加解密key: {key}, key: {self.user_info.key}, deviceId: {self.user_info.deviceId}")
            elif action == "phone":
                key = EncryptionUtils.gen_key(self.user_info.phone, self.user_info.deviceId)
                self.logger.info(f"{method_name}(), 加解密key: {key}, phone: {self.user_info.phone}, deviceId: {self.user_info.deviceId}")
            elif action == "sessionId":
                key = EncryptionUtils.gen_key(self.user_info.sessionId, self.user_info.deviceId)
                self.logger.info(f"{method_name}(), 加解密key: {key}, session_id: {self.user_info.sessionId}, deviceId: {self.user_info.deviceId}")

            if isinstance(response_data_dict["data"], dict) or is_valid_json_with_keys(response_data_dict["data"], ['status']):
                decrypted_response = response_data_dict["data"]
            else:
                decrypted_response = EncryptionUtils.decrypt(response_data_dict["data"], key)
            self.logger.info(f"{method_name}(), action: {action}, 加解密key: {key}, 加密内容: {response_data_dict["data"]}")
            self.logger.info(f"{method_name}(), action: {action}, 解密后内容: {decrypted_response}")

        except Exception as e:
            self.logger.error(f"{method_name}(), Error processing response: {e}")
            return ResponseResult(status = response.status, error_message = f"处理响应数据失败 {e}")

        # 构建新的响应
        try:
            if isinstance(decrypted_response, dict):
                return ResponseResult(status=response.status, is_success=True, data=decrypted_response, error_message=None)
            elif is_valid_json_with_keys(decrypted_response, ['status']):
                decrypted_response_data = json.loads(decrypted_response.encode())
                return ResponseResult(status=response.status, is_success=True, data=decrypted_response_data, data_str = decrypted_response, error_message=None)
            else:
                self.logger.error(f"{method_name}(), 发现不能处理的响应数据：response_data_dict: {response_data_dict}, decrypted_response: {decrypted_response}")
                return ResponseResult(status=response.status, is_success=False, data=None, data_str = decrypted_response, error_message=None)
        except Exception as e:
            self.logger.error(f"{method_name}(), 处理的响应数据有异常, decrypted_response: {decrypted_response}, e: {e}")
            return ResponseResult(status=response.status, data_str=decrypted_response)


