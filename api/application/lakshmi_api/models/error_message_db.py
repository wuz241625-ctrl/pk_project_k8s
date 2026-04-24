from sqlalchemy import Column, String, Text, DateTime, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class ErrorMessageDB(Base):
    """错误消息数据库模型，对应error_messages表"""
    __tablename__ = 'error_messages'

    error_code = Column(String(10), primary_key=True)
    module = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    technical_message = Column(Text, nullable=False)
    zh_title = Column(String(100), nullable=False)
    zh_message = Column(Text, nullable=False)
    zh_action = Column(Text)
    en_title = Column(String(100))
    en_message = Column(Text)
    en_action = Column(Text)
    hi_title = Column(String(100))
    hi_message = Column(Text)
    hi_action = Column(Text)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    def __repr__(self):
        return f"<ErrorMessageDB(error_code='{self.error_code}', module='{self.module}')>" 