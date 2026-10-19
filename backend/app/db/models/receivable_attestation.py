"""DB-135 immutable historical receivable evidence read models.

Migration 179 owns the database guards. These mappings have no update/delete
service path and do not represent tender, settlement or a payment instruction.
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class InvoiceReceivableAttestationRun(Base):
    __tablename__ = "invoice_receivable_attestation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    manifest_digest = Column(String(64), nullable=False)
    invoice_ids = Column(JSONB, nullable=False)
    approved_entries = Column(JSONB, nullable=False)
    fingerprint_version = Column(String(32), nullable=False)
    expected_insert_count = Column(Integer, nullable=False)
    authorization_reference = Column(String(255), nullable=False)
    reviewer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    executor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    state = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)


class InvoiceReceivableAttestation(Base):
    __tablename__ = "invoice_receivable_attestations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    repair_order_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    run_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    supersedes_id = Column(UUID(as_uuid=True))
    decision = Column(String(32), nullable=False)
    currency = Column(String(3), nullable=False)
    principal_total_cents = Column(BigInteger, nullable=False)
    confirmed_principal_cents = Column(BigInteger, nullable=False)
    source_fingerprint = Column(String(64), nullable=False)
    fingerprint_version = Column(String(32), nullable=False)
    evidence_digest = Column(String(64), nullable=False)
    manifest_digest = Column(String(64), nullable=False)
    reviewer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    executor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)
    audit_reference = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
