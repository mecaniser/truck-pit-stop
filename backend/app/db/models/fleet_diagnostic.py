"""Immutable dashboard diagnostic observations, separate from fault lifecycle."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class FleetDiagnosticCapture(BaseModel):
    __tablename__ = "fleet_diagnostic_captures"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_membership_id = Column(UUID(as_uuid=True), nullable=False)
    verified_vin = Column(String(17), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    source_company_id = Column(String(120), nullable=False)
    source_company_label = Column(String(255), nullable=False)
    source = Column(String(40), nullable=False)
    source_read_at = Column(DateTime(timezone=True), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    captured_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    client_request_id = Column(UUID(as_uuid=True), nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    coverage = Column(String(20), nullable=False)
    explicit_empty = Column(Boolean, nullable=False)
    source_scope = Column(String(80), nullable=False)
    codes = Column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "client_request_id", name="uq_diagnostic_capture_request"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id", "fleet_customer_id", "fleet_membership_id"],
            [
                "fleet_memberships.tenant_id",
                "fleet_memberships.vehicle_id",
                "fleet_memberships.fleet_customer_id",
                "fleet_memberships.id",
            ],
        ),
        CheckConstraint("source = 'motive_dashboard'", name="ck_diagnostic_source"),
        CheckConstraint("coverage = 'complete'", name="ck_diagnostic_coverage"),
        CheckConstraint(
            "source_scope = 'Current fault codes'", name="ck_diagnostic_scope"
        ),
        CheckConstraint(
            "source_read_at <= captured_at", name="ck_diagnostic_read_time"
        ),
        Index(
            "ix_diagnostic_vehicle_read", "tenant_id", "vehicle_id", "source_read_at"
        ),
    )
