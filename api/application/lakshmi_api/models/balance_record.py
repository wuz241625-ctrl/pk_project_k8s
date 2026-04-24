from decimal import Decimal

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, relationship


class BalanceRecord(Base):
    __tablename__ = "balance_record"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = Column("code", String(64), index=True)
    change_before: Mapped[Decimal] = Column("change_before", Numeric(14, 4))
    amount: Mapped[Decimal] = Column("amount", Numeric(14, 4))
    change_after: Mapped[Decimal] = Column("change_after", Numeric(14, 4))
    record_type: Mapped[int] = Column("record_type", Integer, default=0)
    admin_id: Mapped[int] = Column("admin_id", Integer, ForeignKey('admin.id'))
    user_type: Mapped[int] = Column("user_type", Integer)
    user_id: Mapped[int] = Column("user_id", Integer, ForeignKey('partner.id'))
    remark: Mapped[str] = Column("remark", String(64))
    merchant_code: Mapped[str] = Column("merchant_code", String(100))
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now(), index=True)

    user: Mapped["User"] = relationship("User", back_populates="balance_change_records")
    admin: Mapped["Admin"] = relationship("Admin", back_populates="balance_change_records")


from application.lakshmi_api.models.user import User
from application.lakshmi_api.models.admin import Admin
