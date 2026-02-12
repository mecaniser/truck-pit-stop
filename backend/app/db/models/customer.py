from sqlalchemy import Column, String, Text, ForeignKey, Numeric, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Customer(BaseModel):
    __tablename__ = "customers"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="customers")
    
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    company_name = Column(String(255), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    
    billing_address_line1 = Column(String(255), nullable=True)
    billing_address_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_state = Column(String(50), nullable=True)
    billing_zip = Column(String(20), nullable=True)
    billing_country = Column(String(100), nullable=True, default="USA")
    
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=True, index=True)  # e.g. zelle, walk_in, portal
    sms_opt_out = Column(Boolean, nullable=False, default=False, index=True)
    sms_opted_out_at = Column(DateTime(timezone=True), nullable=True)
    sms_opt_out_source = Column(String(50), nullable=True)
    
    # Auto-approve quotes at or below this amount (None = disabled)
    auto_approval_threshold = Column(Numeric(10, 2), nullable=True, default=None)
    
    # Stripe
    stripe_customer_id = Column(String(255), nullable=True, unique=True)
    
    vehicles = relationship("Vehicle", back_populates="customer", cascade="all, delete-orphan")
    repair_orders = relationship("RepairOrder", back_populates="customer")
