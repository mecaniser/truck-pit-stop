"""Audit and external-source identity records for permanent vehicle merges."""

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import BaseModel


class VehicleSourceAlias(BaseModel):
    """An importer identity that resolves to the surviving canonical vehicle."""

    __tablename__ = "vehicle_source_aliases"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    vehicle_id = Column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source = Column(String(50), nullable=False)
    external_id = Column(String(100), nullable=False)

    vehicle = relationship("Vehicle")

    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id", name="uq_vehicle_source_alias"),
    )


class VehicleMergeRecord(BaseModel):
    """Immutable audit record describing a completed, reversible-by-admin merge."""

    __tablename__ = "vehicle_merge_records"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    canonical_vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    duplicate_vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False, index=True)
    merged_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    merged_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    snapshot = Column(JSONB, nullable=False)

    __table_args__ = (
        Index("ix_vehicle_merge_records_tenant_merged_at", "tenant_id", "merged_at"),
    )
