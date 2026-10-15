"""Private retained receipt bytes, metadata and append-only action evidence."""
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, Index, Integer, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import deferred

from app.db.base import BaseModel


class ExternalServiceReceipt(BaseModel):
    __tablename__ = "external_service_receipts"
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    uploaded_vehicle_id = Column(UUID(as_uuid=True), nullable=False)
    filename = Column(String(180), nullable=False)
    media_type = Column(String(32), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    removed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    created_by_name = Column(String(255), nullable=False)
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    updated_by_name = Column(String(255), nullable=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_external_receipt_tenant_id"),
        UniqueConstraint("tenant_id", "record_id", "id", name="uq_external_receipt_record_id"),
        UniqueConstraint("tenant_id", "record_id", "content_sha256", name="uq_external_receipt_content"),
        ForeignKeyConstraint(["tenant_id", "record_id"], ["external_service_records.tenant_id", "external_service_records.id"], name="fk_external_receipt_record", ondelete="RESTRICT"),
        CheckConstraint("version >= 1", name="ck_external_receipt_version"),
        CheckConstraint("size_bytes BETWEEN 1 AND 5242880", name="ck_external_receipt_size"),
        CheckConstraint("media_type IN ('application/pdf','image/jpeg','image/png')", name="ck_external_receipt_type"),
        Index("ix_external_receipt_record_created", "tenant_id", "record_id", "created_at", "id"),
    )


class ExternalServiceReceiptBlob(BaseModel):
    __tablename__ = "external_service_receipt_blobs"
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    receipt_id = Column(UUID(as_uuid=True), nullable=False)
    content = deferred(Column(LargeBinary, nullable=False), raiseload=True)
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_id", name="uq_external_receipt_blob"),
        ForeignKeyConstraint(["tenant_id", "receipt_id"], ["external_service_receipts.tenant_id", "external_service_receipts.id"], name="fk_external_receipt_blob", ondelete="RESTRICT"),
        CheckConstraint("octet_length(content) BETWEEN 1 AND 5242880", name="ck_external_receipt_blob_size").ddl_if(dialect="postgresql"),
    )


class ExternalServiceReceiptEvent(BaseModel):
    __tablename__ = "external_service_receipt_events"
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    receipt_id = Column(UUID(as_uuid=True), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    request_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    action = Column(String(16), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), nullable=False)
    actor_name = Column(String(255), nullable=False)
    reason = Column(String(500), nullable=True)
    snapshot = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "record_id", "receipt_id"], ["external_service_receipts.tenant_id", "external_service_receipts.record_id", "external_service_receipts.id"], name="fk_external_receipt_event", ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "request_id", name="uq_external_receipt_request"),
        UniqueConstraint("tenant_id", "receipt_id", "version", name="uq_external_receipt_revision"),
        CheckConstraint("version >= 1", name="ck_external_receipt_event_version"),
        CheckConstraint("action IN ('upload','remove','restore')", name="ck_external_receipt_action"),
    )
