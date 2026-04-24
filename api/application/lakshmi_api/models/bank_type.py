from typing import List

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Column, Boolean
from sqlalchemy.orm import Mapped, relationship


class BankType(Base):
    __tablename__ = "bank_type"

    id: Mapped[int] = Column(primary_key=True)
    name: Mapped[str] = Column("name", String(32))
    url: Mapped[str] = Column("url", String(128))
    genre: Mapped[int] = Column("type", Integer, default=0)
    status: Mapped[bool] = Column("status", Boolean, default=True)
    logo_url: Mapped[str] = Column("logo_url", String)
    payments: Mapped[List["Payment"]] = relationship("Payment",
                                                     back_populates="bank",
                                                     lazy='dynamic')


from application.lakshmi_api.models.payment import Payment
