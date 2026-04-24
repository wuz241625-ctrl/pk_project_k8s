from decimal import Decimal
from typing import List

from sqlalchemy.ext.hybrid import hybrid_property

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, relationship
from sqlalchemy.dialects.mysql import LONGTEXT

class Payment(Base):
    __tablename__ = 'payment'
    __table_args__ = (
        UniqueConstraint('bank_type_id', 'phone', name='uk_payment_bank_phone'),
    )

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    bank_type: Mapped[str] = Column("bank_type", String)
    account_type: Mapped[int] = Column("account_type", Integer)
    upi: Mapped[str] = Column("upi", String(32))
    ifsc: Mapped[str] = Column("ifsc", String(32))
    account: Mapped[str] = Column("account", String(32), index=True)
    name: Mapped[str] = Column("name", String(32))
    net_id: Mapped[str] = Column("net_id", String(32))
    net_pw: Mapped[str] = Column("net_pw", String(32))
    net_trade_pw: Mapped[str] = Column("net_trade_pw", String(32))
    phone: Mapped[str] = Column("phone", String(16))
    pin: Mapped[str] = Column("pin", String(64))
    tpin: Mapped[str] = Column("tpin", String(64))
    email: Mapped[str] = Column("gmail", String(64), index=True)
    gmail_pw: Mapped[str] = Column("gmail_pw", String(32))
    sys_balance: Mapped[Decimal] = Column("sys_balance", Numeric(12, 2), default=0.00)
    balance: Mapped[Decimal] = Column("balance", Numeric(12, 2), default=0.00)
    user_id: Mapped[int] = Column("partner_id", Integer, ForeignKey('partner.id'), index=True)
    certified: Mapped[int] = Column("certified", Integer, default=0)
    status: Mapped[int] = Column("status", Integer, default=0)
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    amount_top: Mapped[Decimal] = Column("amount_top", Numeric(12, 2))
    manual_status: Mapped[bool] = Column("manual_status", Boolean, default=False)
    bank_type_id: Mapped[int] = Column("bank_type_id", Integer, ForeignKey('bank_type.id'), index=True)
    upi_list: Mapped[str] = Column("upi_list", String(500))
    remarks = Column(LONGTEXT, comment='保存换upi或登出的错误消息')
    channel: Mapped[int] = Column("channel", Integer, default=1001)
    priority_collection: Mapped[int] = Column("priority_collection", Integer, default=0)
    tpin_is_true: Mapped[int] = Column("tpin_is_true", Integer, default=1)
    updated_at: Mapped[DateTime] = Column("time_update", DateTime, default=func.now())
    fingerprint_path = Column(LONGTEXT, comment='指纹文件存储位置')
    account_entire = Column(LONGTEXT, comment='账户完整列表')
    account_accno: Mapped[str] = Column("account_accno", String(50))
    account_iban: Mapped[str] = Column("account_iban", String(50))

    user: Mapped["User"] = relationship("User", back_populates="payments")
    bank: Mapped["BankType"] = relationship("BankType", back_populates="payments")
    # set a virtual field for assign summary
    _today_withdraw_order_summary = None

    @hybrid_property
    def today_withdraw_order_summary(self):
        return self._today_withdraw_order_summary

    @today_withdraw_order_summary.setter
    def today_withdraw_order_summary(self, value):
        self._today_withdraw_order_summary = value

    withdraw_orders: Mapped[List["WithdrawOrder"]] = relationship("WithdrawOrder",
                                                                  back_populates="payment",
                                                                  lazy='dynamic')
    deposit_orders: Mapped[List["DepositOrder"]] = relationship("DepositOrder",
                                                                back_populates="payment",
                                                                lazy='dynamic')
    bank_records: Mapped[List["BankRecord"]] = relationship("BankRecord", back_populates="payment", lazy="dynamic")


from application.lakshmi_api.models.user import User
from application.lakshmi_api.models.bank_type import BankType
from application.lakshmi_api.models.withdraw_order import WithdrawOrder
from application.lakshmi_api.models.deposit_order import DepositOrder
from application.lakshmi_api.models.bank_record import BankRecord
