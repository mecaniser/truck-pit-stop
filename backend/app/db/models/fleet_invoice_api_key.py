from sqlalchemy import Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class FleetInvoiceApiKey(BaseModel):
    __tablename__ = "fleet_invoice_api_keys"
    __table_args__ = (
        Index("ux_fleet_invoice_active_scope", "tenant_id", "customer_id", unique=True,
              postgresql_where=text("revoked_at IS NULL"),
              sqlite_where=text("revoked_at IS NULL")),
    )
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    # Keep opaque historical scope even if a customer is merged/deleted.
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    key_prefix = Column(String(16), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
