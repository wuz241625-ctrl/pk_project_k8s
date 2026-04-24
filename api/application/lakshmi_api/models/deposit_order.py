from decimal import Decimal

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, func, ForeignKey, Index
from sqlalchemy.orm import Mapped, relationship


class DepositOrder(Base):
    __tablename__ = "orders_df"

    id: Mapped[int] = Column(primary_key=True)
    serial_number: Mapped[str] = Column("code", String(64), unique=True)
    amount: Mapped[Decimal] = Column("amount", Numeric(12, 2))
    real_pay: Mapped[Decimal] = Column("realpay", Numeric(14, 4))
    poundage: Mapped[Decimal] = Column("poundage", Numeric(14, 4))
    status: Mapped[int] = Column("status", Integer, default=0)
    payment_name: Mapped[str] = Column("payment_name", String(64))
    payment_account: Mapped[str] = Column("payment_account", String(64))
    payment_bank: Mapped[str] = Column("payment_bank", String(64))
    ifsc: Mapped[str] = Column("ifsc", String(64))
    notice_api: Mapped[str] = Column("notice_api", String(64))
    notify: Mapped[str] = Column("notify", String(128))
    remark: Mapped[str] = Column("remark", String(128))
    merchant_id: Mapped[int] = Column("merchant_id", Integer)
    merchant_code: Mapped[str] = Column("merchant_code", String(64), index=True)
    merchant_rate: Mapped[Decimal] = Column("merchant_rate", Numeric(10, 4))
    earn_merchant: Mapped[Decimal] = Column("earn_merchant", Numeric(10, 4))
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    order_placed_at: Mapped[DateTime] = Column("time_accept", DateTime)
    paid_at: Mapped[DateTime] = Column("time_payed", DateTime)
    success_at: Mapped[DateTime] = Column("time_success", DateTime)
    updated_at: Mapped[DateTime] = Column("time_updated", DateTime, default=func.now())
    user_id = Column("partner_id", Integer, ForeignKey('partner.id'), index=True)
    payment_id = Column(Integer, ForeignKey('payment.id'))
    benefit: Mapped[Decimal] = Column("earn_partner_self", Numeric(14, 4))
    other_pay: Mapped[str] = Column("otherpay", String(64))
    earn_system: Mapped[Decimal] = Column("earn_system", Numeric(10, 4))
    payment_img: Mapped[int] = Column("payment_img", Integer, default=0)
    sys_remark: Mapped[str] = Column("sys_remark", String(255))
    utr: Mapped[str] = Column("utr", String(64))
    
    # --- 新增属性 ---
    # is_split: tinyint(1) 对应 SQLAlchemy 的 Integer 类型，默认值为 0
    # 通常 1 表示是母订单（已拆分），0 表示是子订单或普通未拆分订单
    is_split: Mapped[int] = Column("is_split", Integer, default=0)

    # parent_id: varchar(64) 默认值为空字符串 ''
    # 如果是子订单，存储其母订单的 'code'。如果是母订单或独立订单，则为空字符串。
    parent_id: Mapped[str] = Column("parent_id", String(64), default='')
    # --- 新增属性结束 ---

    __table_args__ = (
        Index('merchant_id_merchant_code', 'merchant_id', 'merchant_code'),
    )

    user: Mapped["User"] = relationship("User", back_populates="deposit_orders")
    payment: Mapped["Payment"] = relationship("Payment", back_populates="deposit_orders")


from application.lakshmi_api.models.user import User
from application.lakshmi_api.models.payment import Payment
