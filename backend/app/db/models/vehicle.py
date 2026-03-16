from sqlalchemy import Column, String, Integer, ForeignKey, Text, Float, DateTime
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
    unit_number = Column(String(50), nullable=True, index=True)  # Fleet/company unit identifier
    make = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    year = Column(Integer, nullable=True)
    license_plate = Column(String(20), nullable=True, index=True)
    color = Column(String(50), nullable=True)
    mileage = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # Persisted NHTSA/vPIC decode snapshot used for normalized labor-memory matching.
    nhtsa_make = Column(String(100), nullable=True)
    nhtsa_model = Column(String(100), nullable=True)
    nhtsa_model_year = Column(Integer, nullable=True)
    nhtsa_vehicle_type = Column(String(100), nullable=True)
    nhtsa_body_class = Column(String(150), nullable=True)
    nhtsa_drive_type = Column(String(100), nullable=True)
    nhtsa_fuel_type = Column(String(100), nullable=True)
    nhtsa_engine_cylinders = Column(Integer, nullable=True)
    nhtsa_engine_displacement_l = Column(Float, nullable=True)
    nhtsa_engine_hp = Column(Integer, nullable=True)
    nhtsa_transmission = Column(String(100), nullable=True)
    nhtsa_gvwr = Column(String(100), nullable=True)
    nhtsa_decoded_at = Column(DateTime(timezone=True), nullable=True)
    
    repair_orders = relationship("RepairOrder", back_populates="vehicle")

