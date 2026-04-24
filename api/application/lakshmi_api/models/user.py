import random
import string
from decimal import Decimal
from typing import List

from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, String, Numeric, Column, DateTime, event, func
from sqlalchemy.orm import Mapped, relationship, registry, Session

mapper_registry = registry()
mapper_registry.configure()


class User(Base):
    __tablename__ = "partner"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = Column("name", String(64))
    cellphone: Mapped[str] = Column("cellphone", String(32))
    hash_login: Mapped[str] = Column("hash_login", String(128))
    hash_trade: Mapped[str] = Column("hash_trade", String(128))
    balance: Mapped[Decimal] = Column("balance", Numeric(14, 4), default=0.0)
    balance_frozen: Mapped[Decimal] = Column("balance_frozen", Numeric(14, 4), default=0.0)
    balance_deposit: Mapped[Decimal] = Column("balance_deposit", Numeric(14, 4), default=0.0)
    vip: Mapped[int] = Column("vip", Integer, default=1)
    pid: Mapped[int] = Column("pid", Integer)
    status: Mapped[int] = Column("status", Integer, default=1)
    certified: Mapped[int] = Column("certified", Integer, default=0)
    ip: Mapped[int] = Column("ip", Integer, default=0)
    created_at: Mapped[DateTime] = Column("time_create", DateTime, default=func.now())
    updated_at: Mapped[DateTime] = Column("time_update", DateTime, default=func.now())
    genre: Mapped[int] = Column("type", Integer, default=1, info={"comment": "码商类型 0内部 1外部"})
    invitation_code: Mapped[str] = Column("invitation_code", String(8))
    authentication_token: Mapped[str] = Column("authentication_token", String(64))
    email: Mapped[str] = Column("email", String(50))

    balance_change_records: Mapped[List["BalanceRecord"]] = relationship("BalanceRecord",
                                                                         back_populates="user",
                                                                         lazy='dynamic')
    deposit_orders: Mapped[List["DepositOrder"]] = relationship("DepositOrder",
                                                                back_populates="user",
                                                                lazy='dynamic')

    withdraw_orders: Mapped[List["WithdrawOrder"]] = relationship("WithdrawOrder",
                                                                  back_populates="user",
                                                                  lazy='dynamic')
    payments: Mapped[List["Payment"]] = relationship("Payment",
                                                     back_populates="user",
                                                     lazy='dynamic')
    bank_records: Mapped[List["BankRecord"]] = relationship("BankRecord", back_populates="user", lazy="dynamic")
    usdt_orders: Mapped[List["UsdtDepositOrder"]] = relationship("UsdtDepositOrder",
                                                                 back_populates="user",
                                                                 lazy='dynamic')


@event.listens_for(User, 'before_insert')
def generate_invitation_code(mapper, connection, target):
    while True:
        invitation_code = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        with Session(bind=connection) as session:
            existing_user = session.query(User).filter_by(invitation_code=invitation_code).first()
            if not existing_user:
                target.invitation_code = invitation_code
                break


from application.lakshmi_api.models.withdraw_order import WithdrawOrder
from application.lakshmi_api.models.deposit_order import DepositOrder
from application.lakshmi_api.models.balance_record import BalanceRecord
from application.lakshmi_api.models.payment import Payment
from application.lakshmi_api.models.bank_record import BankRecord
from application.lakshmi_api.models.usdt_deposit_order import UsdtDepositOrder


class PartnerLoginLog(Base):
    __tablename__ = 'partner_login_log'

    id = Column(Integer, primary_key=True, autoincrement=True)
    partner_id = Column(Integer, nullable=False)
    ip = Column(String(45), nullable=False)
    ref = Column(String(255), nullable=True)
    loc = Column(String(255), nullable=True)
    created_at: Mapped[DateTime] = Column("created_at", DateTime, default=func.now())
