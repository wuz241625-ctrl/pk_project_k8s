import argparse
import hashlib
import json
import time
from datetime import datetime
from decimal import Decimal


class StringUtils:

    # 向数组中添加一个对象，并返回唯一数组
    @staticmethod
    def to_unique_array(array: []) -> []:
        unique_array = []
        for item in array:
            if item and item not in unique_array:
                unique_array.append(item)
        return unique_array

    # 向数组中添加一个对象，并返回唯一数组
    @staticmethod
    def append_object_to_unique_array(array: [], new_object: str) -> []:
        array.append(new_object)
        return StringUtils.to_unique_array(array)

    # 向以逗号分隔的字符串中，追加一个唯一字符串
    @staticmethod
    def append_unique_string(original_str: str, new_str: str) -> str:
        if original_str is None:
            original_str = ''
        # 将原始字符串拆分为列表，同时去除可能的空格
        arrays = [item.strip() for item in original_str.split(',')]
        arrays = StringUtils.append_object_to_unique_array(arrays, new_str.strip())
        # 将列表重新连接为逗号分隔的字符串
        return ','.join(arrays)

    @staticmethod
    def is_valid_json(json_str: str) -> bool:
        """
        检查字符串是否是有效的 JSON 格式。
        :param json_str: 要检查的字符串
        :return: 如果是有效的 JSON，返回 True；否则返回 False
        """
        try:
            json.loads(json_str)  # 尝试解析 JSON
            return True
        except json.JSONDecodeError:
            return False  # 解析失败，不是有效的 JSON
        except TypeError:
            return False  # 输入不是字符串类型

"""
命令行工具类
"""
class CommandLineUtils:

    def str_to_bool(self, value):
        if value.lower() in ("yes", "true", "t", "y", "1"):
            return True
        elif value.lower() in ("no", "false", "f", "n", "0"):
            return False
        else:
            raise argparse.ArgumentTypeError("布尔值应为 'yes'/'no'、'true'/'false'、'1'/'0' 等")

    def get_parameters(self):
        # 创建 ArgumentParser 对象
        parser = argparse.ArgumentParser(description="处理命令行参数")
        # 添加参数
        parser.add_argument("--local_mock", type=self.str_to_bool, default=False, help="本地模拟测试")
        # 解析参数
        args = parser.parse_args()

        # 解析参数
        parameters = {
            "local_mock": args.local_mock
        }
        return parameters

    def get_local_mock(self):
        parameters = self.get_parameters()
        local_mock = parameters.get("local_mock", False)
        return local_mock

class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return super().default(obj)

class HashUtils:
    """
    哈希工具类，用于生成简短的版本号。
    """
    def generate_short_version(data=None):
        """
        生成一个类似 Git 的 8 位简短版本号。
        :param data: 可选，输入数据（如时间戳或随机字符串）。如果为 None，则使用当前时间戳。
        :return: 8 位的简短版本号（字符串）。
        """
        if data is None:
            # 如果没有提供数据，使用当前时间戳作为输入
            data = str(time.time()).encode('utf-8')
        else:
            # 如果提供了数据，确保它是字节类型
            if isinstance(data, str):
                data = data.encode('utf-8')

        # 使用 SHA-1 哈希算法生成哈希值
        hash_object = hashlib.sha1(data)
        hex_digest = hash_object.hexdigest()  # 获取 40 位的十六进制哈希值

        # 取前 8 位作为简短版本号
        short_version = hex_digest[:8]
        return short_version


# 示例用法
if __name__ == "__main__":
    # 生成一个基于当前时间戳的版本号
    version = HashUtils.generate_short_version()
    print("生成的简短版本号:", version)

    # 生成一个基于自定义字符串的版本号
    custom_version = HashUtils.generate_short_version("F17406730030414027792")
    print("基于自定义数据的版本号:", custom_version)

    name = "ASDTI QWEOITQLEOIASDFWEITOA"
    print(f"name: {len(name)}, {name}")
    name = name[0:20]
    print(f"name: {len(name)}, {name}")
