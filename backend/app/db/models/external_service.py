"""Private outside-shop history, independent of shop work and accounting."""
from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import BaseModel


class ExternalServiceRecord(BaseModel):
    __tablename__ = "external_service_records"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    original_vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    provider_name = Column(String(160), nullable=False)
    service_date = Column(Date, nullable=False)
    description = Column(Text, nullable=False)
    odometer = Column(Integer, nullable=True)
    reference = Column(String(100), nullable=True)
    reported_cost = Column(Numeric(12, 2), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    voided_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_by_name = Column(String(255), nullable=False)
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    updated_by_name = Column(String(255), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_external_service_tenant_id"),
        ForeignKeyConstraint(["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"], name="fk_external_service_vehicle", ondelete="RESTRICT"),
        CheckConstraint("version >= 1", name="ck_external_service_version"),
        CheckConstraint("odometer IS NULL OR (odometer >= 0 AND odometer <= 99999999)", name="ck_external_service_odometer"),
        CheckConstraint("reported_cost IS NULL OR (reported_cost >= 0 AND reported_cost <= 9999999999.99)", name="ck_external_service_cost"),
        Index("ix_external_service_vehicle_date", "tenant_id", "vehicle_id", "service_date", "id"),
    )


class ExternalServiceEvent(BaseModel):
    __tablename__ = "external_service_events"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    request_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    action = Column(String(16), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), nullable=False)
    actor_name = Column(String(255), nullable=False)
    reason = Column(String(500), nullable=True)
    snapshot = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "record_id"], ["external_service_records.tenant_id", "external_service_records.id"], name="fk_external_service_event_record", ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "request_id", name="uq_external_service_request"),
        UniqueConstraint("tenant_id", "record_id", "version", name="uq_external_service_revision"),
        CheckConstraint("version >= 1", name="ck_external_service_event_version"),
        CheckConstraint("action IN ('create','update','void','restore')", name="ck_external_service_action"),
    )
