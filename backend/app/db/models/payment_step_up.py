"""Server-enforced step-up grants for payment-source configuration.

The browser receives an opaque bearer value exactly once.  Only its digest is
persisted so a database read cannot be turned into an authorization header.
Audit events are append-only and intentionally omit passwords, raw grants, QR
contents, OAuth material, and provider secrets.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import BaseModel


class PaymentStepUpGrant(BaseModel):
    __tablename__ = "payment_step_up_grants"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    target_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    session_jti = Column(String(64), nullable=False, index=True)
    token_version = Column(Integer, nullable=False, default=0)
    scope = Column(String(96), nullable=False, index=True)
    token_digest = Column(String(64), nullable=False, unique=True, index=True)
    one_time = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)


class PaymentStepUpAuditEvent(BaseModel):
    """Append-only security event for grant issuance and use."""

    __tablename__ = "payment_step_up_audit_events"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    target_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    grant_id = Column(UUID(as_uuid=True), ForeignKey("payment_step_up_grants.id"), nullable=True, index=True)
    event_type = Column(String(24), nullable=False, index=True)
    scope = Column(String(96), nullable=False, index=True)
    provider = Column(String(32), nullable=True, index=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    metadata_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
