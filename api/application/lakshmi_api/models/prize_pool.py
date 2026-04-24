from decimal import Decimal

from sqlalchemy import Column, String, Integer, SmallInteger, DateTime, func, Numeric, FLOAT
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models.base import Base


class PrizePool(Base):
    __tablename__ = "prize_pool"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    pool_amount: Mapped[Decimal] = Column("pool_amount", Numeric(14, 4))
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())

