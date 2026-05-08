"""EasyPaisa 旧导入路径。

实际实现已收敛到 `jobs.common.db`，这里仅作为明确的过渡出口保留。
退出机制：新代码禁止继续从本模块导入；旧测试和历史模块迁完后删除本文件。
"""
from jobs.common.db import DBConnection

__all__ = ["DBConnection"]
