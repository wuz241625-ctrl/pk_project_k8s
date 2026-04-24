import json

from sqlalchemy.orm import DeclarativeBase

from application.utils import CustomJsonEncoder


class Base(DeclarativeBase):
    __abstract__ = True

    def __repr__(self):
        table_columns = set(column.name for column in self.__table__.columns)
        return f"{self.__class__.__name__}({', '.join(f'{k}={v}' for k, v in vars(self).items() if not k.startswith('_') and k in table_columns)})"

    def to_dict(self):
        """
        将 DeclarativeBase 对象转换为字典。
        """
        # 获取表的列名
        table_columns = set(column.name for column in self.__table__.columns)
        # 构建字典
        dict = {k: v for k, v in vars(self).items() if not k.startswith('_') and k in table_columns}
        dict_str = json.dumps(dict, cls=CustomJsonEncoder)
        return json.loads(dict_str)