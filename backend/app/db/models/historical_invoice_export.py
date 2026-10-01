"""Owner-reviewed historical bill-to grants and their immutable trail."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel


class HistoricalInvoiceEvidence(BaseModel):
    __tablename__ = "historical_invoice_evidence"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_historical_evidence_tenant_id"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    repair_order_id = Column(UUID(as_uuid=True), ForeignKey("repair_orders.id"), nullable=False)
    source_type = Column(String(40), nullable=False)
    source_reference = Column(String(500), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    source_document = Column(LargeBinary, nullable=False)
    source_content_type = Column(String(80), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    original_bill_to_name = Column(String(255), nullable=False)
    original_customer_id = Column(UUID(as_uuid=True), nullable=True)
    merge_lineage_reference = Column(String(500), nullable=True)
    recorded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_target_customer_id = Column(UUID(as_uuid=True), nullable=True)
    verified_target_legal_name = Column(String(255), nullable=True)
    verification_note = Column(Text, nullable=True)


class HistoricalInvoiceMapping(BaseModel):
    __tablename__ = "historical_invoice_mappings"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id", name="uq_historical_mapping_invoice"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, unique=True)
    target_customer_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("historical_invoice_evidence.id"), nullable=True)
    version = Column(Integer, nullable=False, default=0)


class HistoricalInvoiceDecision(BaseModel):
    __tablename__ = "historical_invoice_decisions"
    __table_args__ = (UniqueConstraint("tenant_id", "invoice_id", "idempotency_key",
                                        name="uq_historical_decision_idempotency"),)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("historical_invoice_evidence.id"), nullable=True)
    evidence_sha256 = Column(String(64), nullable=True)
    original_bill_to_name = Column(String(255), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    old_customer_id = Column(UUID(as_uuid=True), nullable=True)
    new_customer_id = Column(UUID(as_uuid=True), nullable=True)
    action = Column(String(20), nullable=False)
    reason = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_sha256 = Column(String(64), nullable=False)


class FleetInvoiceScopeEvent(BaseModel):
    __tablename__ = "fleet_invoice_scope_events"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("historical_invoice_decisions.id"), nullable=False)
    kind = Column(String(32), nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=False, index=True)
