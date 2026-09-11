from sqlalchemy import Column, String, UniqueConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import BaseModel


class CustomerTaxExemptionAudit(BaseModel):
    __tablename__ = "customer_tax_exemption_audits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_tax_exemption_key"),
        UniqueConstraint("customer_id", "version", name="uq_customer_tax_exemption_version"),
    )
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    # Archived identity, deliberately not a delete-blocking FK. The database
    # checks tenant/customer coherence on INSERT; audit survives lawful merges.
    customer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    evidence = Column(JSONB, nullable=False)
