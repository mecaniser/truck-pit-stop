from sqlalchemy import Column, ForeignKey, String, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import BaseModel


class InvoiceChargeAdjustment(BaseModel):
    __tablename__ = "invoice_charge_adjustments"
    __table_args__ = (
        UniqueConstraint("invoice_id", "version", name="uq_invoice_charge_adjustment_version"),
        UniqueConstraint("invoice_id", "idempotency_key", name="uq_invoice_charge_adjustment_key"),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    evidence = Column(JSONB, nullable=False)
