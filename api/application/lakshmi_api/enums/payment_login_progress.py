from enum import Enum


"""
payment登录进度
"""
class PaymentLoginProgress(Enum):

    """
    协议获取发送短信的数据
    协议获取客户端要发送短信的内容及号码，
    协议调用 POST /v1/websocket/get_send_sms_info 通知api服务
    成功通知的参数：
    form-data参数："payment_id"={payment.id}
    form-data参数："to_phone"="999999999"
    form-data参数："content"="xxx"

    失败通知的参数：
    form-data参数："payment_id"={payment.id},
    form-data参数："error_msg"=xxx
    """
    DATA_TO_SEND_SMS = "Get data for sending SMS messages"

    """
    协议检查客户端发送短信的结果
    协议调用 POST /v1/websocket/payment_protocol_status_notify 通知api服务
    成功：
    form-data参数："type"="send_sms_check", 
    form-data参数："is_success"=true,
    form-data参数："payment_id"={payment.id}
    失败：
    form-data参数："type"="send_sms_check", 
    form-data参数："is_success"=false,
    form-data参数："payment_id"={payment.id}, 
    form-data参数："error_msg"=xxx
    """
    SEND_SMS_CHECK = "Check result of SMS sending"

    """
    协议申请获取OTP状态
    也作为缓存键，存储OTP的发送状态
    协议调用 POST /v1/websocket/push_upi_opt_success 通知api服务 申请发送OTP成功
    form-data 参数： id={payment.id}
    协议调用 POST /v1/websocket/push_upi_opt_fail 通知api服务 申请发送OTP失败
    form-data 参数： id={payment.id}, 
    form-data 参数： error_message=xxx
    """
    STATUS_OF_SENDING_OTP = "Get the sending status of OTP"

    """
    协议检查客户端输入OTP的结果
    协议调用 POST /v1/websocket/payment_protocol_status_notify 通知api服务 输入otp的检查结果
    成功：
    form-data参数："type"="status_of_verify_otp", 
    form-data参数："is_success"=true,
    form-data参数："payment_id"={payment.id}
    失败：
    form-data参数："type"="status_of_verify_otp", 
    form-data参数："is_success"=false,
    form-data参数："payment_id"={payment.id}, 
    form-data参数："error_msg"=xxx
    """
    STATUS_OF_VERIFY_OTP = "Verify the status of the input otp"

    """
    协议检查客户端输入MPIN的结果
    协议调用 POST /v1/websocket/payment_protocol_status_notify 通知api服务 输入MPIN的检查结果
    成功：
    form-data参数："type"="status_of_verify_mpin", 
    form-data参数："is_success"=true,
    form-data参数："payment_id"={payment.id}
    失败：
    form-data参数："type"="status_of_verify_mpin", 
    form-data参数："is_success"=false,
    form-data参数："payment_id"={payment.id}, 
    form-data参数："error_msg"=xxx
    """
    STATUS_OF_VERIFY_MPIN = "Verify the status of the mpin"

    """
    协议获取协议登录用户的信息
    协议调用 POST /v1/websocket/payment_protocol_status_notify 通知api服务
    成功：
    form-data参数："type"="get_profile", 
    form-data参数："is_success"=true,
    form-data参数："payment_id"={payment.id}
    失败：
    form-data参数："type"="get_profile", 
    form-data参数："is_success"=false,
    form-data参数："payment_id"={payment.id}, 
    form-data参数："error_code"="fail", 
    form-data参数："error_msg"=xxx
    """
    GET_PROFILE = "Get profile"

    """
    协议登录状态
    协议调用 POST /v1/websocket/payment_protocol_status_notify 通知api服务
    成功：
    form-data参数："type"="status_of_login",
    form-data参数："is_success"=true,
    form-data参数："payment_id"={payment.id}
    失败：
    form-data参数："type"="status_of_login",
    form-data参数："is_success"=false,
    form-data参数："payment_id"={payment.id},
    form-data参数："error_msg"="xxx"
    """
    STATUS_OF_LOGIN = "Get login status"


# 将字符串转换为枚举
def string_to_enum(enum_name_str):
    try:
        return PaymentLoginProgress[enum_name_str]
    except KeyError:
        return None