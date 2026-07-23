"""Tenant-scoped QuickBooks Online authorization records.

QuickBooks uses rotating OAuth credentials.  The raw credentials are never
stored in this model: they are encrypted before persistence by
``quickbooks_service``.  A separate short-lived state table keeps OAuth
callbacks bound to the shop administrator who initiated consent and prevents
state replay.
"""
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref, relationship

from app.db.base import BaseModel


class QuickBooksConnection(BaseModel):
    __tablename__ = "quickbooks_connections"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True)
    tenant = relationship("Tenant", backref=backref("quickbooks_connection", uselist=False))

    # A QuickBooks company must only be connected to one TruckPitStop tenant.
    # Clearing it during disconnect releases that company for a future, explicit
    # connection without retaining a provider identifier unnecessarily.
    realm_id = Column(String(64), nullable=True, unique=True)
    scopes = Column(String(500), nullable=False, default="")
    status = Column(String(32), nullable=False, default="disconnected", index=True)

    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    last_token_refresh_at = Column(DateTime(timezone=True), nullable=True)
    last_token_refresh_error = Column(Text, nullable=True)
    last_webhook_at = Column(DateTime(timezone=True), nullable=True)
    last_webhook_event = Column(String(160), nullable=True)
    last_webhook_error = Column(Text, nullable=True)
    last_cdc_at = Column(DateTime(timezone=True), nullable=True)
    last_cdc_error = Column(Text, nullable=True)


class QuickBooksOAuthState(BaseModel):
    __tablename__ = "quickbooks_oauth_states"

    # Store only a SHA-256 digest of the browser state value.  The state itself
    # never lands in the database, logs, or response payloads.
    state_hash = Column(String(64), nullable=False, unique=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    initiated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    tenant = relationship("Tenant")
    initiated_by_user = relationship("User")


class QuickBooksWebhookEvent(BaseModel):
    """Durable Intuit webhook deduplication and reconciliation audit record."""

    __tablename__ = "quickbooks_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "realm_id", "entity_name", "entity_id", "operation", "last_updated_at",
            name="uq_quickbooks_webhook_delivery",
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    realm_id = Column(String(64), nullable=False, index=True)
    entity_name = Column(String(64), nullable=False)
    entity_id = Column(String(64), nullable=False)
    operation = Column(String(32), nullable=False)
    last_updated_at = Column(String(64), nullable=False, default="")
    status = Column(String(20), nullable=False, default="pending", index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)

    tenant = relationship("Tenant")
