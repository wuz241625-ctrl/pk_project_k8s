from decimal import Decimal

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, SmallInteger, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, relationship


class BankRecord(Base):
    __tablename__ = 'bank_record'

    id: Mapped[int] = Column(primary_key=True)
    amount: Mapped[Decimal] = Column("amount", Numeric(14, 4))
    content: Mapped[str] = Column("content", String)
    trade_type: Mapped[int] = Column("trade_type", Integer, default=0)
    utr: Mapped[str] = Column("utr", String(32))
    code: Mapped[str] = Column("code", String(32))
    ifsc: Mapped[str] = Column("ifsc", String(32))
    order_code: Mapped[str] = Column("order_code", String(64))
    callback: Mapped[int] = Column("callback", Integer, default=0)
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    ew_code: Mapped[str] = Column("ew_code", String(64))
    invalid: Mapped[int] = Column("invalid", Integer, default=0)
    if_ew: Mapped[int] = Column("if_ew", SmallInteger, default=0)
    admin_id: Mapped[int] = Column("admin_id", Integer, ForeignKey('admin.id'))
    payment_id = Column(Integer, ForeignKey('payment.id'))
    user_id = Column("partner_id", Integer, ForeignKey('partner.id'), index=True)

    __table_args__ = (
        Index("ind_partner_id_time_create", 'partner_id', 'time_create'),
        Index("payment_id_trade_type_if_ew_invalid_callback", 'payment_id', 'trade_type', 'if_ew', 'invalid',
              'callback')
    )

    admin: Mapped["Admin"] = relationship("Admin", back_populates="bank_records")
    payment: Mapped["Payment"] = relationship("Payment", back_populates="bank_records")
    user: Mapped["User"] = relationship("User", back_populates="bank_records")


from application.lakshmi_api.models.admin import Admin
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.models.user import User
