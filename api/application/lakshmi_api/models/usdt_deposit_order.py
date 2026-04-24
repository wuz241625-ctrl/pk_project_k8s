from datetime import datetime
from decimal import Decimal
import random

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, func, ForeignKey, event, Boolean
from sqlalchemy.orm import Mapped, relationship, Session


class UsdtDepositOrder(Base):
    __tablename__ = "usdt_deposit_orders"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    serial_number: Mapped[str] = Column("serial_number", String(64), unique=True, index=True)
    status: Mapped[int] = Column("status", default=0)
    usdt_amount: Mapped[Decimal] = Column("usdt_amount", Numeric(12, 4))
    exchange_rate: Mapped[Decimal] = Column("exchange_rate", Numeric(8, 4))
    currency_amount: Mapped[Decimal] = Column("currency_amount", Numeric(12, 4))
    total_amount: Mapped[Decimal] = Column("total_amount", Numeric(12, 4))
    block_chain: Mapped[str] = Column("block_chain", String(64))
    bonus_rate: Mapped[Decimal] = Column("bonus_rate", Numeric(6, 4))
    bonus: Mapped[Decimal] = Column("bonus", Numeric(10, 4))
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("updated_at", DateTime, default=func.now())
    paid_at: Mapped[DateTime] = Column("paid_at", DateTime)
    request_at: Mapped[DateTime] = Column("request_at", DateTime)
    address: Mapped[str] = Column("address", String(255))
    receipt_image: Mapped[bool] = Column("receipt_image", Boolean, default=False)
    user_id = Column("user_id", Integer, ForeignKey('partner.id'), index=True)
    admin_id = Column("admin_id", Integer)
    txid: Mapped[str] = Column("txid", String(255))
    user: Mapped["User"] = relationship("User", back_populates="usdt_orders")


@event.listens_for(UsdtDepositOrder, 'before_insert')
def generate_code_and_assign_usdt_rate(mapper, connection, target):
    from .sys_info import SysInfo
    # random serial_number
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day = now.strftime("%d")
    random_number = ''.join(["{}".format(random.randint(0, 9)) for num in range(0, 8)])
    target.serial_number = "U{}{}{}{}".format(year[2:], month, day, random_number)
    # read all rate from db
    with Session(bind=connection) as session:
        sys_info = session.query(SysInfo).first()
        target.exchange_rate = Decimal(sys_info.usdt_exchange_rate)
        target.bonus_rate = Decimal(sys_info.usdt_exchange_bonus_rate)
        target.currency_amount = Decimal(target.exchange_rate * target.usdt_amount)
        target.bonus = Decimal(target.currency_amount * target.bonus_rate)
        target.total_amount = Decimal(target.currency_amount + target.bonus)


from application.lakshmi_api.models.user import User
