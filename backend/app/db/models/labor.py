from sqlalchemy import Column, String, Numeric, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal
from app.db.base import BaseModel


class Labor(BaseModel):
    __tablename__ = "labor"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="labor")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, index=True)
    repair_order = relationship("RepairOrder", back_populates="labor_items")
    
    service_code = Column(String(50), nullable=True)
    description = Column(Text, nullable=False)
    hours = Column(Numeric(5, 2), nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)
    total_cost = Column(Numeric(10, 2), nullable=False)
    
    mechanic_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    mechanic = relationship("User", foreign_keys=[mechanic_id])

