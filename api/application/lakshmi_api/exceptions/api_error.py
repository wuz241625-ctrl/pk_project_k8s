class NewApiError(Exception):
    """API错误异常统一类
    
    使用统一的错误类和错误码系统，与数据库错误消息表集成
    错误码对应关系：
    - 10201: 验证错误/参数错误
    - 10202: 认证错误
    - 10301: 支付未找到或无权访问
    - 10401: UPI已存在且属于当前用户
    - 10402: UPI已被占用
    - 10403: 发送OTP失败
    - 10601: 业务处理失败/操作频繁
    - 10901: 系统错误
    """
    def __init__(self, code: str, message: str = None):
        self.code = code
        self.message = message
        super().__init__(message or code)



class ValidationError(NewApiError):
    """验证错误"""
    def __init__(self, message: str = None):
        super().__init__('10201', message or '验证错误')

class AuthenticationError(NewApiError):
    """认证错误"""
    def __init__(self, message: str = None):
        super().__init__('10202', message or '认证失败')

class PaymentError(NewApiError):
    """支付错误"""
    def __init__(self, message: str = None):
        super().__init__('10301', message or '支付未找到或无权访问')

class UpiExistsError(NewApiError):
    """UPI已存在错误"""
    def __init__(self, message: str = None):
        super().__init__('10401', message or 'UPI已存在且属于当前用户')

class UpiOccupiedError(NewApiError):
    """UPI已被占用错误"""
    def __init__(self, message: str = None):
        super().__init__('10402', message or 'UPI已被占用')

class OtpError(NewApiError):
    """OTP发送失败错误"""
    def __init__(self, message: str = None):
        super().__init__('10403', message or '发送OTP失败')

class BusinessError(NewApiError):
    """业务逻辑错误"""
    def __init__(self, message: str = None):
        super().__init__('10601', message or '业务处理失败')

class SystemError(NewApiError):
    """系统错误"""
    def __init__(self, message: str = None):
        super().__init__('10901', message or '系统错误') 