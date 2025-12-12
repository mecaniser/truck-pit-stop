from sqlalchemy import Column, DateTime, ForeignKey, Numeric, Text, Boolean, String
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal
from app.db.base import BaseModel


class Quote(BaseModel):
    __tablename__ = "quotes"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="quotes")
    
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False, unique=True)
    repair_order = relationship("RepairOrder", back_populates="quote")
    
    quote_number = Column(String(50), unique=True, nullable=False, index=True)
    total_amount = Column(Numeric(10, 2), nullable=False)
    notes = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_approved = Column(Boolean, default=False, nullable=False)

