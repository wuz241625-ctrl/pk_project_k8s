from typing import List

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Column, DateTime, func
from sqlalchemy.orm import Mapped, relationship


class Admin(Base):
    __tablename__ = 'admin'

    id: Mapped[int] = Column(Integer, primary_key=True)
    account: Mapped[str] = Column(String(64))
    hash_login: Mapped[str] = Column(String(128))
    name: Mapped[str] = Column(String(64))
    role: Mapped[int] = Column(Integer)
    gg_key: Mapped[str] = Column("ggkey", String(64))
    status: Mapped[int] = Column(Integer, default=1)
    updated_at: Mapped[DateTime] = Column("time_update", DateTime, default=func.now())
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())

    balance_change_records: Mapped[List["BalanceRecord"]] = relationship("BalanceRecord",
                                                                         back_populates="admin",
                                                                         lazy='dynamic')
    bank_records: Mapped[List["BankRecord"]] = relationship("BankRecord", back_populates="admin", lazy="dynamic")


from application.lakshmi_api.models.balance_record import BalanceRecord
from application.lakshmi_api.models.bank_record import BankRecord
