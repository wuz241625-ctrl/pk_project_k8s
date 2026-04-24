from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, DateTime, Column, func
from sqlalchemy.orm import Mapped


class TextMaterial(Base):
    __tablename__ = "text_materials"

    id: Mapped[int] = Column(Integer, primary_key=True)
    genre: Mapped[str] = Column("genre", String)
    title: Mapped[str] = Column("title", String)
    content: Mapped[str] = Column("content", String)
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
    