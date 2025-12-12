from sqlalchemy import Column, String, Integer, Numeric, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from decimal import Decimal
from app.db.base import BaseModel


class ServiceCategory(BaseModel):
    """Categories for services (e.g., Maintenance, Repairs, Inspections)"""
    __tablename__ = "service_categories"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="service_categories")
    
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)  # emoji or icon name
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    services = relationship("Service", back_populates="category", cascade="all, delete-orphan")


class Service(BaseModel):
    """Individual services offered by the garage"""
    __tablename__ = "services"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="services")
    
    category_id = Column(UUID(as_uuid=True), ForeignKey("service_categories.id"), nullable=True, index=True)
    category = relationship("ServiceCategory", back_populates="services")
    
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Duration in minutes
    duration_minutes = Column(Integer, default=60, nullable=False)
    
    # Pricing
    base_price = Column(Numeric(10, 2), nullable=False)
    
    # Availability
    is_active = Column(Boolean, default=True, nullable=False)
    requires_vehicle = Column(Boolean, default=True, nullable=False)
    
    # For display
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    
    appointments = relationship("Appointment", back_populates="service")
