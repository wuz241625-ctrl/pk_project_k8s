import json

"""
用户信息
对象转字符串： json.dumps({obj}.to_dict())
字符串转对象： user_info = UserInfo.from_json({str})
"""
class UserInfo:
    def __init__(self):
        self.phone: str = ""
        self.accountNumber: str = ""
        self.deviceId: str = ""
        self.key: str = ""
        self.customerId: str = ""
        self.customerName: str = ""
        self.password: str = ""
        self.mpin: str = ""
        self.tpin: str = ""

        self.os: str = ""
        self.osVersion: str = ""
        self.longitude: str = ""
        self.latitude: str = ""
        self.location: str = ""
        self.ipv6Address: str = ""

        self.token: str = ""
        self.vmn: str = ""
        self.verificationCode: str = ""
        self.authenticationNo: str = ""

        self.sessionId: str = ""

    def to_dict(self) -> dict:
        """将对象转换为字典"""
        return {
            'phone': self.phone,
            'accountNumber': self.accountNumber,
            'deviceId': self.deviceId,
            'key': self.key,
            'customerId': self.customerId,
            'customerName': self.customerName,
            'password': self.password,
            'mpin': self.mpin,
            'tpin': self.tpin,
            'os': self.os,
            'osVersion': self.osVersion,
            'longitude': self.longitude,
            'latitude': self.latitude,
            'location': self.location,
            'ipv6Address': self.ipv6Address,
            'token': self.token,
            'vmn': self.vmn,
            'verificationCode': self.verificationCode,
            'authenticationNo': self.authenticationNo,
            'sessionId': self.sessionId
        }

    def __str__(self) -> str:
        """将对象转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'UserInfo':
        """从JSON字符串创建UserInfo对象
        
        Args:
            json_str: JSON字符串
            
        Returns:
            UserInfo: 新的UserInfo对象
        """
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UserInfo':
        """从字典创建UserInfo对象
        
        Args:
            data: 包含UserInfo数据的字典
            
        Returns:
            UserInfo: 新的UserInfo对象
        """
        user_info = cls()
        for key, value in data.items():
            if hasattr(user_info, key):
                setattr(user_info, key, value)
        return user_info
