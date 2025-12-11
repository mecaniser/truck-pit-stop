from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Customer(BaseModel):
    __tablename__ = "customers"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="customers")
    
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    
    billing_address_line1 = Column(String(255), nullable=True)
    billing_address_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_state = Column(String(50), nullable=True)
    billing_zip = Column(String(20), nullable=True)
    billing_country = Column(String(100), nullable=True, default="USA")
    
    notes = Column(Text, nullable=True)
    
    vehicles = relationship("Vehicle", back_populates="customer", cascade="all, delete-orphan")
    repair_orders = relationship("RepairOrder", back_populates="customer")

