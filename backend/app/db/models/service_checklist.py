"""Immutable service task snapshots with retained execution evidence."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class RepairOrderChecklistItem(BaseModel):
    __tablename__ = "repair_order_checklist_items"
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    repair_order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repair_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    labor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("labor.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    labor_id_snapshot = Column(UUID(as_uuid=True), nullable=False)
    source_service_id_snapshot = Column(UUID(as_uuid=True), nullable=False)
    source_template_item_id = Column(UUID(as_uuid=True), nullable=False)
    source_template_version = Column(Integer, nullable=False)
    service_name_snapshot = Column(String(255), nullable=False)
    label = Column(String(300), nullable=False)
    required = Column(Boolean, nullable=False, default=True)
    position = Column(Integer, nullable=False)
    is_completed = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    completed_by_name = Column(String(255), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    removed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index(
            "ix_ro_checklist_scope",
            "tenant_id",
            "repair_order_id",
            "removed_at",
            "position",
            "id",
        ),
        UniqueConstraint(
            "labor_id", "source_template_item_id", name="uq_ro_checklist_labor_template"
        ),
        CheckConstraint("position >= 0", name="ck_ro_checklist_position"),
        CheckConstraint("version > 0", name="ck_ro_checklist_version"),
        CheckConstraint(
            "length(trim(label)) BETWEEN 1 AND 300", name="ck_ro_checklist_label"
        ),
        CheckConstraint(
            "(is_completed AND completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL AND completed_by_name IS NOT NULL) OR (NOT is_completed AND completed_at IS NULL AND completed_by_user_id IS NULL AND completed_by_name IS NULL)",
            name="ck_ro_checklist_evidence",
        ),
    )
