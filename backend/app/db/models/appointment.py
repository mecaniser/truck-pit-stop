from sqlalchemy import Column, String, Integer, ForeignKey, Text, Enum as SQLEnum, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.db.base import BaseModel


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"  # Awaiting payment
    CONFIRMED = "confirmed"  # Paid and scheduled
    IN_PROGRESS = "in_progress"  # Currently being serviced
    COMPLETED = "completed"  # Service finished
    CANCELLED = "cancelled"  # Cancelled by customer or garage
    NO_SHOW = "no_show"  # Customer didn't show up


class Appointment(BaseModel):
    """Customer appointment for a service"""
    __tablename__ = "appointments"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="appointments")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    customer = relationship("Customer", backref="appointments")
    
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=True, index=True)
    vehicle = relationship("Vehicle", backref="appointments")
    
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False, index=True)
    service = relationship("Service", back_populates="appointments")
    
    # Scheduling
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False)  # Copy from service at booking time
    
    # Status
    status = Column(
        SQLEnum(AppointmentStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AppointmentStatus.PENDING,
        index=True
    )
    
    # Pricing (locked in at booking time)
    price = Column(Numeric(10, 2), nullable=False)
    
    # Payment
    stripe_payment_intent_id = Column(String(255), nullable=True, unique=True, index=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notes
    customer_notes = Column(Text, nullable=True)  # Customer's notes when booking
    internal_notes = Column(Text, nullable=True)  # Garage internal notes
    
    # Reference number for easy lookup
    confirmation_number = Column(String(20), unique=True, nullable=False, index=True)
    
    # If this appointment creates a repair order
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=True)
    repair_order = relationship("RepairOrder", backref="appointment")
