from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, SmallInteger
from application.lakshmi_api.models.base import Base

class Message(Base):
    __tablename__ = 'message'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    to_id = Column(String(500), nullable=True)
    from_id = Column(Integer, nullable=False)
    type = Column(SmallInteger, nullable=False, default=1)
    subject = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    send_time = Column(DateTime, nullable=False)
    status = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now) 