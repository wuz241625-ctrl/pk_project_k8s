import json

"""
maha协议请求官方接口的结果状态类
"""
class MahaResultStatusAttributes:

    def __init__(
            self,
            code: int = None,
            description: str = None,
            en_cue_words: str = None,
            zh_cue_words: str = None
    ):
        self.code: int = code  # 代码
        self.description: str = description  # 说明
        self.en_cue_words: str = en_cue_words  # 英文提示语
        self.zh_cue_words: str = zh_cue_words  # 中文提示语

    @classmethod
    def from_dict(cls, data: dict) -> 'MahaResultStatusAttributes':
        obj = MahaResultStatusAttributes()
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj

    @classmethod
    def from_json_str(cls, json_str: str) -> 'MahaResultStatusAttributes':

        data = json.loads(json_str)
        return cls.from_dict(data)
