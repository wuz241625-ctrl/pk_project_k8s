import random
import string
import time

def generate_android_13_device_id():
    """
    生成符合Android 13特征的16位设备ID
    返回: 16位字符串，格式类似：'a1b2c3d4e5f6g7h8'
    """
    # 常用的设备ID前缀
    prefixes = ['a', 'b', 'c', 'd', 'e']
    
    # 生成时间戳的一部分作为设备ID的一部分（确保唯一性）
    timestamp = hex(int(time.time()))[2:6]
    
    # 选择一个前缀
    device_id = random.choice(prefixes)
    
    # 添加时间戳部分
    device_id += timestamp
    
    # 剩余位数用随机字符填充
    remaining_length = 16 - len(device_id)
    characters = string.ascii_lowercase + string.digits
    device_id += ''.join(random.choice(characters) for _ in range(remaining_length))
    
    return device_id
