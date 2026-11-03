from sqlalchemy import Column, String, Integer, ForeignKey, Text, Enum as SQLEnum, DateTime, Numeric, UniqueConstraint, ForeignKeyConstraint, CheckConstraint
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
    __table_args__ = (
        UniqueConstraint('tenant_id', 'id', name='uq_booking_appointment_tenant_id'),
        CheckConstraint("booking_payment_version IS NULL OR (booking_payment_version=1 AND booking_kind='reserve' AND booking_payment_state IS NOT NULL AND booking_payment_state IN ('unpaid_hold','payment_processing','paid','expired_unpaid','payment_received_review','refund_pending','refunded') AND booking_version IS NOT NULL AND booking_version>=1 AND hold_expires_at IS NOT NULL AND price_snapshot_sha256 IS NOT NULL AND length(price_snapshot_sha256)=64 AND booking_idempotency_key IS NOT NULL AND booking_request_sha256 IS NOT NULL AND booking_currency='usd' AND price>=0.50 AND booking_provider_configuration_version IS NOT NULL AND booking_provider_environment IS NOT NULL AND booking_provider_environment IN ('sandbox','production'))",name="ck_verified_booking_snapshot"),
        UniqueConstraint('tenant_id', 'booking_idempotency_key', name='uq_booking_reservation_request'),
        ForeignKeyConstraint(['tenant_id','booking_provider_configuration_version'], ['tenant_payment_provider_configurations.tenant_id','tenant_payment_provider_configurations.version'], name='fk_booking_reservation_configuration'),
        ForeignKeyConstraint(['tenant_id','confirmed_receipt_id'], ['booking_receipts.tenant_id','booking_receipts.id'], use_alter=True, name='fk_booking_confirmed_receipt'),
    )
    booking_kind = Column(String(16), nullable=True)
    booking_payment_version = Column(Integer, nullable=True)
    booking_payment_state = Column(String(32), nullable=True)
    booking_version = Column(Integer, nullable=True)
    hold_expires_at = Column(DateTime(timezone=True), nullable=True)
    price_snapshot_sha256 = Column(String(64), nullable=True)
    booking_idempotency_key = Column(String(200), nullable=True)
    booking_request_sha256 = Column(String(64), nullable=True)
    confirmed_receipt_id = Column(UUID(as_uuid=True), nullable=True)
    booking_currency = Column(String(3), nullable=True)
    booking_provider_configuration_version = Column(Integer, nullable=True)
    booking_provider_environment = Column(String(24), nullable=True)

    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tenant = relationship("Tenant", backref="appointments")
    
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    # No backref to Customer: unused elsewhere, and an unguarded backref on a
    # nullable=False FK risks SQLAlchemy nullifying it during unrelated
    # unit-of-work flushes (see MessageThread.customer for the incident this
    # pattern caused during customer merges).
    customer = relationship("Customer")
    
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
