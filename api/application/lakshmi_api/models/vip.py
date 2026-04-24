from decimal import Decimal

from application.lakshmi_api.models.base import Base
from sqlalchemy import Column, Integer, SmallInteger, Numeric
from sqlalchemy.orm import Mapped


class Vip(Base):
    __tablename__ = 'vip'

    vip: Mapped[int] = Column("vip", Integer, primary_key=True)
    conditions: Mapped[Decimal] = Column("conditions", Numeric(12, 2))
    withdraw_min: Mapped[Decimal] = Column("ds_min", Numeric(12, 2))
    withdraw_max: Mapped[Decimal] = Column("ds_max", Numeric(12, 2))
    deposit_min: Mapped[Decimal] = Column("df_min", Numeric(12, 2))
    deposit_max: Mapped[Decimal] = Column("df_max", Numeric(12, 2))
    top_card: Mapped[int] = Column("top_card", Integer, default=1)
    security_deposit: Mapped[int] = Column("deposit_ratio", SmallInteger, default=20)
