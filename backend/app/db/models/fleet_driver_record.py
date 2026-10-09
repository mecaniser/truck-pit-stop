"""Immutable provider driver observations bound to verified fleet assignments."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class FleetDriverRecordCapture(BaseModel):
    __tablename__ = "fleet_driver_record_captures"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_membership_id = Column(UUID(as_uuid=True), nullable=False)
    verified_vin = Column(String(17), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    provider_driver_id = Column(String(120), nullable=False)
    driver_name = Column(String(160), nullable=False)
    local_driver_name = Column(String(160))
    local_driver_phone = Column(String(20))
    driver_assignment_revision = Column(Integer, nullable=False)
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
    payload = Column(JSON, nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "client_request_id", name="uq_driver_record_request"
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
        CheckConstraint("source = 'motive_dashboard'", name="ck_driver_record_source"),
        CheckConstraint(
            "source_read_at <= captured_at", name="ck_driver_record_read_time"
        ),
        CheckConstraint(
            "driver_assignment_revision >= 0",
            name="ck_driver_record_assignment_revision",
        ),
        Index(
            "ix_driver_record_vehicle_read", "tenant_id", "vehicle_id", "source_read_at"
        ),
        Index(
            "ix_driver_record_provider",
            "tenant_id",
            "source_company_id",
            "provider_driver_id",
        ),
    )


class FleetDriverDirectoryCapture(BaseModel):
    """Latest complete directory invalidates former-driver projections, including empty runs."""

    __tablename__ = "fleet_driver_directory_captures"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    source_company_id = Column(String(120), nullable=False)
    source_company_label = Column(String(255), nullable=False)
    source_read_at = Column(DateTime(timezone=True), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    assignments = Column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "fleet_customer_id"], ["customers.tenant_id", "customers.id"]
        ),
        UniqueConstraint(
            "tenant_id",
            "fleet_customer_id",
            "source_sha256",
            name="uq_driver_directory_source",
        ),
        Index(
            "ix_driver_directory_customer_read",
            "tenant_id",
            "fleet_customer_id",
            "source_read_at",
        ),
    )
