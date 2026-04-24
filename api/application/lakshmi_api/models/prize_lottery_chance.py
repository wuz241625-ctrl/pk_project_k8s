from decimal import Decimal

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func, Numeric, FLOAT
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizeLotteryChance(Base):
    __tablename__ = "prize_lottery_chance"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Integer] = Column("user_id", Integer)
    chance_num: Mapped[Integer] = Column("chance_num", Integer)
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())

