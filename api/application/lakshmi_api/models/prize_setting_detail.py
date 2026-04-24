from decimal import Decimal

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func, Numeric, FLOAT
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizeSettingDetail(Base):
    __tablename__ = "prize_setting_detail"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    prize_id: Mapped[Integer] = Column("prize_id", Integer)
    prize_title: Mapped[str] = Column("prize_title", String)
    title: Mapped[str] = Column("title", String)
    prize_limit_min: Mapped[Integer] = Column("prize_limit_min", Integer)
    prize_limit_max: Mapped[Integer] = Column("prize_limit_max", Integer)
    prize_type: Mapped[SmallInteger] = Column("prize_type", SmallInteger)
    money: Mapped[Decimal] = Column("money", Numeric(10, 2))
    ratio: Mapped[Decimal] = Column("ratio", Numeric(10, 6))
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())
    status: Mapped[SmallInteger] = Column("status", SmallInteger)

