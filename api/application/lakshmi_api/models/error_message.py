from typing import Optional
from pydantic import BaseModel

class ErrorMessage(BaseModel):
    code: str
    module: str
    severity: str
    technical_message: str
    zh_title: str
    zh_message: str
    zh_action: Optional[str] = None
    en_title: Optional[str] = None
    en_message: Optional[str] = None
    en_action: Optional[str] = None
    hi_title: Optional[str] = None
    hi_message: Optional[str] = None
    hi_action: Optional[str] = None

    def get_localized_message(self, lang: str = 'en') -> dict:
        """获取指定语言的错误消息"""
        if lang == 'zh' and self.zh_message:
            return {
                'title': self.zh_title,
                'message': self.zh_message,
                'action': self.zh_action
            }
        elif lang == 'hi' and self.hi_message:
            return {
                'title': self.hi_title,
                'message': self.hi_message,
                'action': self.hi_action
            }
        # 默认返回英文
        return {
            'title': self.en_title or self.zh_title,  # 如果英文标题为空，回退到中文
            'message': self.en_message or self.technical_message,  # 如果英文消息为空，回退到技术消息
            'action': self.en_action
        } 