from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, BigInteger, SmallInteger
from application.lakshmi_api.models.base import Base

class UserMessage(Base):
    __tablename__ = 'user_message'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    msg_id = Column(BigInteger, nullable=False)
    user_id = Column(Integer, nullable=False)
    status = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now) 