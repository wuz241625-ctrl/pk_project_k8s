from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizeSetting(Base):
    __tablename__ = "prize_setting"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = Column("title", String)
    content: Mapped[str] = Column("content", String)
    type: Mapped[SmallInteger] = Column("type", SmallInteger, default=0)
    participant: Mapped[str] = Column("participant", String(4096))
    pic: Mapped[str] = Column("pic", String(255))
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())
    status: Mapped[SmallInteger] = Column("status", SmallInteger, default=1)
    is_app_show: Mapped[SmallInteger] = Column("is_app_show", SmallInteger, default=1)
    begin_at: Mapped[DateTime] = Column("begin_at", DateTime, default=func.now())
    end_at: Mapped[DateTime] = Column("end_at", DateTime, default=func.now())
    lottery_chance_setting: Mapped[SmallInteger] = Column("lottery_chance_setting", SmallInteger, default=1)

