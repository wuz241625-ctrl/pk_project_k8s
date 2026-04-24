from sqlalchemy import Integer, Index, String, Column, DateTime

from application.lakshmi_api.models.base import Base

"""
payment UPI 变更历史
"""
class PaymentUpiHistory(Base):
    __tablename__ = 'payment_upi_history'
    __table_args__ = (
        Index('uk_payment_id_upi', 'payment_id', 'upi', unique=True),
        {'comment': 'payment UPI 变更历史'}
    )

    id = Column(Integer, primary_key=True, comment='ID')
    payment_id = Column(Integer, nullable=False, comment='payment.id')
    partner_id = Column(Integer, nullable=False, comment='partner.id')
    bank_id = Column(Integer, nullable=False, comment='bank_type.id')
    upi = Column(String(500), nullable=False, comment='upi')
    time_create = Column(DateTime, nullable=False, comment='创建时间')