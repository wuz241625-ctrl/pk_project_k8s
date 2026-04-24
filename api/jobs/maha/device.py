import string
import random
import json

"""
Android设备信息
对象转字符串： json.dumps({obj}.to_dict())
字符串转对象： device_info = AndroidDeviceInfo.from_json({str})
"""
class AndroidDeviceInfo:
    def __init__(self):
        """ a random 16-character Android ID """
        self.android_id: str = self.generate_android_id()
        self.latitude: str = "40.7228"
        self.longitude: str = "-74.0160"
        self.location: str = "New York"
        self.ipv6Address: str = "FE80::021A:2BFF:FE3C:4D5E"

    def to_dict(self) -> dict:
        """将对象转换为字典"""
        return {
            'android_id': self.android_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'location': self.location,
            'ipv6Address': self.ipv6Address
        }

    @staticmethod
    def generate_android_id():
        """Generate a random 16-character Android ID."""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(16))

    def __str__(self) -> str:
        """将对象转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> 'AndroidDeviceInfo':
        """从JSON字符串创建DeviceInfo对象

        Args:
            json_str: JSON字符串

        Returns:
            AndroidDeviceInfo: 新的DeviceInfo对象
        """
        import json
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> 'AndroidDeviceInfo':
        """从字典创建DeviceInfo对象

        Args:
            data: 包含DeviceInfo数据的字典

        Returns:
            AndroidDeviceInfo: 新的DeviceInfo对象
        """
        obj = cls()
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj

