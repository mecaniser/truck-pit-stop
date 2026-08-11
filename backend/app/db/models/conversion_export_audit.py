"""Append-only audit records for sensitive conversion-export operations."""
from sqlalchemy import Column, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class ConversionExportAudit(BaseModel):
    __tablename__ = "conversion_export_audits"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    actor_api_key_id = Column(UUID(as_uuid=True), ForeignKey("conversion_api_keys.id"), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    target_type = Column(String(40), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
