"""A dated physical pairing of two permanent serviceable asset identities."""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class FleetAssetAttachment(BaseModel):
    __tablename__ = "fleet_asset_attachments"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    tractor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    trailer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    attached_at = Column(DateTime(timezone=True), nullable=False)
    detached_at = Column(DateTime(timezone=True), nullable=True)
    attached_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    detached_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "tractor_id"], ["vehicles.tenant_id", "vehicles.id"], name="fk_fleet_attachment_tractor"),
        ForeignKeyConstraint(["tenant_id", "trailer_id"], ["vehicles.tenant_id", "vehicles.id"], name="fk_fleet_attachment_trailer"),
        CheckConstraint("tractor_id != trailer_id", name="ck_fleet_attachment_distinct_assets"),
        CheckConstraint("detached_at IS NULL OR detached_at >= attached_at", name="ck_fleet_attachment_dates"),
        Index("uq_fleet_attachment_active_tractor", "tractor_id", unique=True,
              postgresql_where=text("detached_at IS NULL AND deleted_at IS NULL"),
              sqlite_where=text("detached_at IS NULL AND deleted_at IS NULL")),
        Index("uq_fleet_attachment_active_trailer", "trailer_id", unique=True,
              postgresql_where=text("detached_at IS NULL AND deleted_at IS NULL"),
              sqlite_where=text("detached_at IS NULL AND deleted_at IS NULL")),
    )
