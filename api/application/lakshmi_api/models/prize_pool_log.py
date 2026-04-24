from decimal import Decimal

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func, Numeric, FLOAT
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizePoolLog(Base):
    __tablename__ = "prize_pool_log"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = Column("code", String)
    record_type: Mapped[SmallInteger] = Column("record_type", SmallInteger)
    change_before: Mapped[Decimal] = Column("change_before", Numeric(14, 4))
    amount: Mapped[Decimal] = Column("amount", Numeric(14, 4))
    change_after: Mapped[Decimal] = Column("change_after", Numeric(14, 4))
    user_type: Mapped[Integer] = Column("user_type", Integer)
    user_id: Mapped[Integer] = Column("user_id", Integer)
    remark: Mapped[str] = Column("remark", String)
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())

