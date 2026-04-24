from decimal import Decimal

from sqlalchemy import Integer, String, Numeric, Column, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped

from application.lakshmi_api.models import DepositOrder
from application.lakshmi_api.models.base import Base


class DepositOrderCancel(Base):
    __tablename__ = "orders_df_cancel"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
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

    @classmethod
    def copy(cls, original_order: DepositOrder):
        # 复制原订单到 DepositOrderCancel 表
        canceled_order = DepositOrderCancel(
            serial_number=original_order.serial_number,
            amount=original_order.amount,
            real_pay=original_order.real_pay,
            poundage=original_order.poundage,
            status=original_order.status,
            payment_name=original_order.payment_name,
            payment_account=original_order.payment_account,
            payment_bank=original_order.payment_bank,
            ifsc=original_order.ifsc,
            notice_api=original_order.notice_api,
            notify=original_order.notify,
            remark=original_order.remark,
            merchant_id=original_order.merchant_id,
            merchant_code=original_order.merchant_code,
            merchant_rate=original_order.merchant_rate,
            earn_merchant=original_order.earn_merchant,
            created_at=original_order.created_at,
            order_placed_at=original_order.order_placed_at,
            paid_at=original_order.paid_at,
            success_at=original_order.success_at,
            updated_at=original_order.updated_at,
            user_id=original_order.user_id,
            payment_id=original_order.payment_id,
            benefit=original_order.benefit,
            other_pay=original_order.other_pay,
            earn_system=original_order.earn_system,
            payment_img=original_order.payment_img,
            sys_remark=original_order.sys_remark,
            utr=original_order.utr
        )
        return canceled_order