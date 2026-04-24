# 定义基类，包含通用的方法
import decimal
from datetime import datetime
from enum import Enum

import simplejson

from beneficiary import Beneficiary
from account_balance import AccountBalance
from user_info import UserInfo


def dict_to_class(dict_data, cls):
    """
    将字典转换为自定义类的实例。
    :param dict_data: 字典数据
    :param cls: 目标类
    :return: 自定义类的实例
    """
    if not isinstance(dict_data, dict):
        raise ValueError("输入必须是字典类型")

    # 获取类的构造函数参数
    init_params = cls.__init__.__code__.co_varnames[1:cls.__init__.__code__.co_argcount]

    # 处理枚举和其他复杂类型的属性
    processed_data = {}
    for key, value in dict_data.items():
        if key in init_params:
            # 如果属性是枚举类型，将值转换为枚举
            if hasattr(cls, key) and isinstance(getattr(cls, key), property):
                # 如果属性是通过 property 定义的，获取其类型注解
                annotations = cls.__annotations__
                if key in annotations and issubclass(annotations[key], Enum):
                    processed_data[key] = annotations[key](value)
            else:
                processed_data[key] = value

    # 创建类的实例
    return cls(**processed_data)

class BaseClass:

    def to_dict(self) -> dict:
        """将对象转换为字典"""
        result = {}
        for key, value in self.__dict__.items():
            if callable(value):  # 检查是否是函数或可调用对象
                result[key] = value.__name__  # 输出函数的名字
            elif isinstance(value, str) or isinstance(value, dict) or isinstance(value, float) or isinstance(value, int):
                result[key] = value
            elif isinstance(value, Enum):
                result[key] = value.name
            elif isinstance(value, datetime):
                result[key] = value.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(value, decimal.Decimal):
                result[key] = value.__str__()
            elif isinstance(value, Beneficiary):
                result[key] = value.to_dict()
            elif isinstance(value, UserInfo):
                result[key] = value.to_dict()
            elif isinstance(value, AccountBalance):
                result[key] = value.to_dict()
            else:
                result[key] = value  # 其他类型直接输出
        return result

    def to_json_str(self) -> str:
        """将对象转换为JSON字符串"""
        # return json.dumps(self.to_dict(), ensure_ascii=False)
        return simplejson.dumps(self.to_dict(), skipkeys = True)

