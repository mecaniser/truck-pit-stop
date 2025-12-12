from sqlalchemy import Column, String, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class Vehicle(BaseModel):
    __tablename__ = "vehicles"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="vehicles")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer = relationship("Customer", back_populates="vehicles")
    
    vin = Column(String(17), nullable=True, index=True)
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    year = Column(Integer, nullable=True)
    license_plate = Column(String(20), nullable=True, index=True)
    color = Column(String(50), nullable=True)
    mileage = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    
    repair_orders = relationship("RepairOrder", back_populates="vehicle")


