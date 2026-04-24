from decimal import Decimal

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func, Numeric, FLOAT
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizeLotteryChanceLog(Base):
    __tablename__ = "prize_lottery_chance_log"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Integer] = Column("user_id", Integer)
    prize_id: Mapped[Integer] = Column("prize_id", Integer)
    before_num: Mapped[Integer] = Column("before_num", Integer)
    num: Mapped[Integer] = Column("num", Integer)
    after_num: Mapped[Integer] = Column("after_num", Integer)
    remark: Mapped[str] = Column("remark", String)
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())

