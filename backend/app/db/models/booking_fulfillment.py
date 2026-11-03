"""Immutable staff intake evidence; unrelated to receipt/accounting allocation."""
from sqlalchemy import Column, String, Text, Integer, Date, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class VisitRequestEvent(BaseModel):
    __tablename__ = 'visit_request_events'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'idempotency_key', name='uq_visit_request_event_key'),
        UniqueConstraint('tenant_id', 'request_id', 'request_version', name='uq_visit_request_event_version'),
        ForeignKeyConstraint(['tenant_id', 'request_id'], ['visit_requests.tenant_id', 'visit_requests.id']),
        ForeignKeyConstraint(['tenant_id', 'repair_order_id'], ['repair_orders.tenant_id', 'repair_orders.id']),
        ForeignKeyConstraint(['tenant_id', 'reviewed_vehicle_id'], ['vehicles.tenant_id', 'vehicles.id']),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    request_version = Column(Integer, nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    actor_name_snapshot = Column(String(255), nullable=False)
    event_type = Column(String(32), nullable=False)
    before_status = Column(String(24), nullable=False)
    after_status = Column(String(24), nullable=False)
    arrival_date = Column(Date)
    internal_note = Column(Text)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    repair_order_id = Column(UUID(as_uuid=True))
    reviewed_vehicle_id = Column(UUID(as_uuid=True))


class BookingRepairOrderLink(BaseModel):
    __tablename__ = 'booking_repair_order_links'
    __table_args__ = (
        UniqueConstraint('tenant_id', 'idempotency_key', name='uq_booking_ro_link_key'),
        UniqueConstraint('tenant_id', 'appointment_id', name='uq_booking_ro_link_appointment'),
        UniqueConstraint('tenant_id', 'repair_order_id', name='uq_booking_ro_link_order'),
        ForeignKeyConstraint(['tenant_id', 'appointment_id'], ['appointments.tenant_id', 'appointments.id']),
        ForeignKeyConstraint(['tenant_id', 'repair_order_id'], ['repair_orders.tenant_id', 'repair_orders.id']),
        ForeignKeyConstraint(['tenant_id', 'customer_id'], ['customers.tenant_id', 'customers.id']),
        ForeignKeyConstraint(['tenant_id', 'reviewed_vehicle_id'], ['vehicles.tenant_id', 'vehicles.id']),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), nullable=False)
    repair_order_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    reviewed_vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    actor_name_snapshot = Column(String(255), nullable=False)
    reason = Column(Text, nullable=False)
    old_repair_order_id = Column(UUID(as_uuid=True))
    snapshot_sha256 = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
