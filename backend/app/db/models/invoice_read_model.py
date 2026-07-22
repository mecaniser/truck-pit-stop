from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class InvoiceReadModel(Base):
    """Transactionally maintained payload for the invoice list screen."""

    __tablename__ = "invoice_read_models"

    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    status = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    refreshed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
