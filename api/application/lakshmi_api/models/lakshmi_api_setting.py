from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, DateTime, Column, func
from sqlalchemy.orm import Mapped


class LakshmiApiSetting(Base):
    __tablename__ = 'lakshmi_api_settings'

    id: Mapped[int] = Column(Integer, primary_key=True)
    genre: Mapped[str] = Column("genre", String)
    name: Mapped[str] = Column("name", String)
    key: Mapped[str] = Column("key", String)
    value: Mapped[str] = Column("value", String)
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
