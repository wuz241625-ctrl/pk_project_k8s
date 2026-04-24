from decimal import Decimal

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func, Numeric
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizeEarnLog(Base):
    __tablename__ = "prize_earn_log"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Integer] = Column("user_id", Integer)
    user_name: Mapped[str] = Column("user_name", String)
    prize_id: Mapped[Integer] = Column("prize_id", Integer)
    prize_detail_id: Mapped[Integer] = Column("prize_detail_id", Integer)
    prize_title: Mapped[str] = Column("prize_title", String)
    money: Mapped[Decimal] = Column("money", Numeric(10, 2))
    remark: Mapped[str] = Column("remark", String)
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
