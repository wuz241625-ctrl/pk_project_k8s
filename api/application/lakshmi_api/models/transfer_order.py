from decimal import Decimal

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, func, ForeignKey, Index
from sqlalchemy.orm import Mapped


class TransferOrder(Base):
    __tablename__ = "transfer"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = Column("code", String(64), unique=True)
    user_id = Column("partner_id", Integer, ForeignKey('partner.id'), index=True)
    to_user_id: Mapped[str] = Column("to_partner_id", Integer, ForeignKey('partner.id'), index=True)
    amount: Mapped[Decimal] = Column(Numeric(12, 2))
    admin_id: Mapped[str] = Column("admin_id", Integer, ForeignKey('partner.id'), index=True)
    status: Mapped[int] = Column("status", Integer, default=1)
    success_at: Mapped[DateTime] = Column("time_success", DateTime)
    updated_at: Mapped[DateTime] = Column("time_updated", DateTime, default=func.now())
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    type: Mapped[int] = Column("type", Integer, default=1)
    remark: Mapped[str] = Column("remark", String(255))
