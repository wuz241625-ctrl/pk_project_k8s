from decimal import Decimal

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, func
from sqlalchemy.orm import Mapped


class Channel(Base):
    __tablename__ = "channel"

    id: Mapped[int] = Column(primary_key=True)
    code: Mapped[int] = Column(Integer, unique=True)
    name: Mapped[str] = Column("name", String(64))
    genre: Mapped[int] = Column("type", Integer)
    url: Mapped[str] = Column("url", String(255))
    rate: Mapped[Decimal] = Column("rate", Numeric(14, 4))
    rates: Mapped[str] = Column("rates", String(64))
    amount_min: Mapped[Decimal] = Column("amount_min", Numeric(12, 2))
    amount_max: Mapped[Decimal] = Column("amount_max", Numeric(12, 2))
    amount_fixed: Mapped[str] = Column("amount_fixed", String(255))
    fixed: Mapped[int] = Column("fixed", Integer)
    status: Mapped[int] = Column("status", Integer, default=1)
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("time_update", DateTime, default=func.now())
