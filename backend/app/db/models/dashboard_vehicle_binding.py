"""Explicit reviewed identity for a source vehicle without a displayed genuine VIN."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class DashboardVehicleBinding(BaseModel):
    __tablename__ = "dashboard_vehicle_bindings"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_customer_id = Column(UUID(as_uuid=True), nullable=False)
    fleet_membership_id = Column(UUID(as_uuid=True), nullable=False)
    source_company_id = Column(String(120), nullable=False)
    source_company_label = Column(String(255), nullable=False)
    provider_vehicle_id = Column(String(120), nullable=False)
    placeholder_vin = Column(String(17), nullable=False)
    reviewed_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True))
    revoked_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    revocation_reason = Column(String(80))
    revoked_source_vin = Column(String(17))
    revoked_source_read_at = Column(DateTime(timezone=True))
    revoked_source_sha256 = Column(String(64))
    review_note = Column(String(1000), nullable=False)
    review_manifest_sha256 = Column(String(64), nullable=False)
    source_evidence_sha256 = Column(String(64), nullable=False)
    source_evidence_read_at = Column(DateTime(timezone=True), nullable=False)
    source_vin_state = Column(String(30), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "vehicle_id",
            "fleet_membership_id",
            "id",
            name="uq_dashboard_binding_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"]
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
        CheckConstraint(
            "effective_from >= reviewed_at AND (effective_to IS NULL OR effective_to > effective_from)",
            name="ck_dashboard_binding_interval",
        ),
        Index(
            "uq_dashboard_binding_vehicle_active",
            "tenant_id",
            "vehicle_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND deleted_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL AND deleted_at IS NULL"),
        ),
        Index(
            "uq_dashboard_binding_provider_active",
            "tenant_id",
            "source_company_id",
            "provider_vehicle_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND deleted_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL AND deleted_at IS NULL"),
        ),
    )
