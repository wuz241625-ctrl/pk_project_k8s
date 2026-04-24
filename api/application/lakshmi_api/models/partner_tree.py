from application.lakshmi_api.models.base import Base
from sqlalchemy import Integer, Column, UniqueConstraint
from sqlalchemy.orm import Mapped


class PartnerTree(Base):
    __tablename__ = "partner_tree"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    parent = Column(Integer)
    child = Column(Integer, index=True)
    distance = Column(Integer)

    __table_args__ = (UniqueConstraint('parent', 'child', 'distance', name="partner_child_distance_idx"),)
