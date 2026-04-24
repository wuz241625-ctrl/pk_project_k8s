from decimal import Decimal
from typing import List, Dict

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, func, ForeignKey, Index, and_, text, case
from sqlalchemy.orm import Mapped, relationship


class WithdrawOrder(Base):
    __tablename__ = "orders_ds"

    id: Mapped[int] = Column(primary_key=True)
    serial_number: Mapped[str] = Column("code", String(64), unique=True)
    amount: Mapped[Decimal] = Column("amount", Numeric(14, 2))
    real_pay: Mapped[Decimal] = Column("realpay", Numeric(14, 4))
    poundage: Mapped[Decimal] = Column("poundage", Numeric(14, 4))
    channel_code: Mapped[int] = Column("channel_code", Integer)
    status: Mapped[int] = Column("status", Integer, default=0)
    callback: Mapped[str] = Column("callback", String(128))
    notice_api: Mapped[str] = Column("notice_api", String(64))
    notify: Mapped[str] = Column("notify", String(256))
    player_ip: Mapped[str] = Column("player_ip", String(64))
    remark: Mapped[str] = Column("remark", String(128))
    pay_url: Mapped[str] = Column("pay_url", String(128))
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    order_placed_at: Mapped[DateTime] = Column("time_accept", DateTime)
    paid_at: Mapped[DateTime] = Column("time_payed", DateTime)
    order_finished_at: Mapped[DateTime] = Column("time_success", DateTime)
    updated_at: Mapped[DateTime] = Column("time_updated", DateTime, default=func.now())
    merchant_id: Mapped[int] = Column("merchant_id", Integer)
    merchant_code: Mapped[str] = Column("merchant_code", String(128), index=True)
    merchant_rate: Mapped[Decimal] = Column("merchant_rate", Numeric(10, 4))
    earn_merchant: Mapped[Decimal] = Column("earn_merchant", Numeric(10, 4))
    user_id = Column("partner_id", Integer, ForeignKey('partner.id'), index=True)
    benefit: Mapped[Decimal] = Column("earn_partner_self", Numeric(14, 4))
    earn_partner: Mapped[Decimal] = Column("earn_partner", Numeric(10, 4))
    payment_id = Column(Integer, ForeignKey('payment.id'))
    utr: Mapped[str] = Column("utr", String(64))
    auth_code: Mapped[str] = Column("auth_code", String(64), index=True)
    real_name: Mapped[str] = Column("realname", String(64))
    player_provence: Mapped[str] = Column("player_provence", String(64))
    other_pay: Mapped[str] = Column("otherpay", String(64))
    earn_system: Mapped[Decimal] = Column("earn_system", Numeric(10, 4), default=0.0000)
    upi: Mapped[str] = Column("upi", String(32))

    __table_args__ = (
        Index('merchant_id_merchant_code', 'merchant_id', 'merchant_code'),
        Index('merchant_id_updated_at', 'merchant_id', 'time_updated'),
        Index('payment_id_status_updated_at', 'payment_id', 'status', 'time_updated'),
    )

    user: Mapped["User"] = relationship("User", back_populates="withdraw_orders")
    payment: Mapped["Payment"] = relationship("Payment", back_populates="withdraw_orders")

    @classmethod
    def get_today_order_summary(cls, session, payment_ids: List[int]) -> Dict[int, Dict[str, int]]:
        return session.query(
            cls.payment_id,
            func.count(cls.id).label('total_orders'),
            func.sum(case((cls.status == 4, 1), else_=0)).label('success_orders'),
            func.sum(case((cls.status != 4, 1), else_=0)).label('fail_orders')
        ).filter(
            and_(
                cls.payment_id.in_(payment_ids),
                text("DATE(DATE_SUB(time_create, INTERVAL 7 HOUR)) = CURRENT_DATE")
            )
        ).group_by(cls.payment_id).all()


from application.lakshmi_api.models.user import User
from application.lakshmi_api.models.payment import Payment
