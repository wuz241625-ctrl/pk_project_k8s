from decimal import Decimal
from sqlalchemy import Column, Numeric, String, Integer, SmallInteger
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped
from application.lakshmi_api.models.base import Base
from sqlalchemy.dialects.postgresql import JSON


class SysInfo(Base):
    __tablename__ = "sys_info"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    sys_ip_w: Mapped[str] = Column("sys_ip_w", String)
    api_ip_b: Mapped[str] = Column("api_ip_b", String)
    bulletin: Mapped[str] = Column("bulletin", String(255))
    telegram: Mapped[str] = Column("telegram", String(255))
    rate_df: Mapped[Decimal] = Column("rate_df", Numeric(14, 4))
    status_df: Mapped[SmallInteger] = Column("status_df", SmallInteger, default=0)
    usdt_exchange_rate: Mapped[Decimal] = Column("usdt_exchange_rate", Numeric(7, 4))
    usdt_exchange_status: Mapped[SmallInteger] = Column("usdt_exchange_status", SmallInteger, default=0)
    usdt_exchange_bonus_rate: Mapped[Decimal] = Column("usdt_exchange_bonus_rate", Numeric(5, 4))
    app_info: Mapped = Column("app_info", JSON)
    deposit_order_extra_bonus: Mapped = Column("range_df", JSON)
    range_usdt_df: Mapped = Column("range_usdt_df", JSON)
    usdt_received_address = Column(LONGTEXT)
    usdt_amount_limit = Column(Numeric(12, 4), default=0)
    merchant_ids: Mapped[str] = Column("merchant_ids", String)
