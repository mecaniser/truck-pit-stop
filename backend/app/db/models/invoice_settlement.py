"""DB-048 repair-invoice settlement and financial audit aggregates.

The mutable rows in this module are lockable operational projections.  The
ledger and credit-entry rows are append-only evidence and are additionally
protected by PostgreSQL triggers in migration 129.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Boolean,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, BaseModel


MONEY = Numeric(12, 2)


class InvoiceSettlement(BaseModel):
    __tablename__ = "invoice_settlements"
    __table_args__ = (
        UniqueConstraint("invoice_id", name="uq_invoice_settlements_invoice"),
        UniqueConstraint("tenant_id", "invoice_id", name="uq_invoice_settlements_tenant_invoice"),
        ForeignKeyConstraint(
            ["tenant_id", "initial_provider_configuration_version"],
            [
                "tenant_payment_provider_configurations.tenant_id",
                "tenant_payment_provider_configurations.version",
            ],
            name="fk_invoice_settlement_initial_provider_configuration",
        ),
        CheckConstraint("currency = 'USD'", name="ck_invoice_settlement_currency"),
        CheckConstraint("principal_total >= 0", name="ck_invoice_settlement_principal"),
        CheckConstraint("confirmed_principal >= 0", name="ck_invoice_settlement_confirmed"),
        CheckConstraint("active_pending_principal >= 0", name="ck_invoice_settlement_pending"),
        CheckConstraint("unapplied_credit >= 0", name="ck_invoice_settlement_unapplied"),
        CheckConstraint("refund_pending >= 0", name="ck_invoice_settlement_refund_pending"),
        CheckConstraint("version >= 1", name="ck_invoice_settlement_version"),
        CheckConstraint(
            "accounting_composition_version IN ('legacy_principal_v1','gross_invoice_v1')",
            name="ck_invoice_settlement_composition",
        ),
        CheckConstraint(
            "(qbo_realm_snapshot IS NULL AND initial_provider_configuration_version IS NULL) "
            "OR (qbo_realm_snapshot IS NOT NULL AND initial_provider_configuration_version >= 1)",
            name="ck_invoice_settlement_accounting_realm_pair",
        ),
        Index("ix_invoice_settlements_tenant_state", "tenant_id", "state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    principal_total = Column(MONEY, nullable=False)
    max_card_fee = Column(MONEY, nullable=False, default=0)
    max_card_fee_tax = Column(MONEY, nullable=False, default=0)
    sales_tax_rate_snapshot = Column(Numeric(7, 4), nullable=False, default=0)
    card_fee_rate_snapshot = Column(Numeric(7, 4), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="USD")
    confirmed_principal = Column(MONEY, nullable=False, default=0)
    active_pending_principal = Column(MONEY, nullable=False, default=0)
    unapplied_credit = Column(MONEY, nullable=False, default=0)
    refund_pending = Column(MONEY, nullable=False, default=0)
    state = Column(String(40), nullable=False, default="unpaid", index=True)
    version = Column(Integer, nullable=False, default=1)
    last_event_sequence = Column(Integer, nullable=False, default=0)
    accounting_sync_status = Column(String(32), nullable=False, default="not_required", index=True)
    accounting_composition_version = Column(
        String(32), nullable=False, default="legacy_principal_v1",
        server_default="legacy_principal_v1",
    )
    accounting_projection_revision = Column(String(64), nullable=True)
    accounting_fee_line_ids = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    accounting_projection_snapshot = Column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    # Frozen by the first DB-048 attempt. Later provider configurations may be
    # used only when they belong to this same QuickBooks company.
    qbo_realm_snapshot = Column(String(255), nullable=True)
    initial_provider_configuration_version = Column(Integer, nullable=True)
    legacy_reconciliation_status = Column(String(48), nullable=False, default="native")
    legacy_reconciliation_note = Column(Text, nullable=True)


class TenantPaymentProviderConfiguration(BaseModel):
    __tablename__ = "tenant_payment_provider_configurations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_tenant_payment_provider_version"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_payment_provider_idempotency"),
        CheckConstraint("version >= 1", name="ck_tenant_payment_provider_version"),
        CheckConstraint(
            "selected_provider IN ('stripe_connect','quickbooks_payments')",
            name="ck_tenant_payment_provider_name",
        ),
        CheckConstraint(
            "writer_strategy IN ('dieselbridge','intuit_native')",
            name="ck_tenant_payment_provider_writer",
        ),
        Index("ix_tenant_payment_provider_active", "tenant_id", "is_active"),
        Index(
            "uq_tenant_payment_provider_one_active",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    selected_provider = Column(String(32), nullable=False)
    readiness_state = Column(String(48), nullable=False, default="not_ready")
    is_active = Column(Boolean, nullable=False, default=True)
    effective_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    actor_name_snapshot = Column(String(255), nullable=False)
    provider_account_snapshot = Column(String(255), nullable=True)
    qbo_realm_snapshot = Column(String(255), nullable=True)
    writer_strategy = Column(String(32), nullable=False, default="dieselbridge")
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    stripe_clearing_account = Column(String(255), nullable=True)
    qbp_clearing_account = Column(String(255), nullable=True)
    check_deposit_account = Column(String(255), nullable=True)
    zelle_ach_account = Column(String(255), nullable=True)
    card_fee_income_account = Column(String(255), nullable=True)
    qbo_card_fee_item_id = Column(String(255), nullable=True)
    qbo_card_fee_tax_code_id = Column(String(255), nullable=True)
    processor_fee_expense_account = Column(String(255), nullable=True)
    sales_tax_liability_account = Column(String(255), nullable=True)
    checking_account = Column(String(255), nullable=True)


class InvoicePaymentAttempt(BaseModel):
    __tablename__ = "invoice_payment_attempts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_invoice_payment_attempt_idempotency"),
        UniqueConstraint("provider", "provider_account_id", "provider_event_id", name="uq_invoice_payment_provider_event"),
        UniqueConstraint(
            "tenant_id", "customer_id", "rail", "manual_reference_fingerprint",
            name="uq_invoice_payment_manual_reference",
        ),
        CheckConstraint("currency = 'USD'", name="ck_invoice_payment_attempt_currency"),
        CheckConstraint("principal_amount > 0", name="ck_invoice_payment_attempt_principal"),
        CheckConstraint("card_fee_amount >= 0", name="ck_invoice_payment_attempt_card_fee"),
        CheckConstraint("card_fee_tax_amount >= 0", name="ck_invoice_payment_attempt_fee_tax"),
        CheckConstraint("applied_card_fee_amount >= 0", name="ck_invoice_payment_attempt_applied_card_fee"),
        CheckConstraint("applied_card_fee_tax_amount >= 0", name="ck_invoice_payment_attempt_applied_fee_tax"),
        CheckConstraint(
            "received_amount IS NULL OR received_amount >= 0",
            name="ck_invoice_payment_attempt_received_nonnegative",
        ),
        CheckConstraint(
            "applied_principal_amount >= 0 AND applied_principal_amount <= principal_amount",
            name="ck_invoice_payment_attempt_applied_principal_bounds",
        ),
        CheckConstraint(
            "received_amount IS NULL OR applied_principal_amount <= received_amount",
            name="ck_invoice_payment_attempt_applied_not_over_received",
        ),
        CheckConstraint("unapplied_amount >= 0", name="ck_invoice_payment_attempt_unapplied_nonnegative"),
        CheckConstraint(
            "applied_card_fee_amount <= card_fee_amount",
            name="ck_invoice_payment_attempt_applied_card_fee_bound",
        ),
        CheckConstraint(
            "applied_card_fee_tax_amount <= card_fee_tax_amount",
            name="ck_invoice_payment_attempt_applied_fee_tax_bound",
        ),
        CheckConstraint(
            "(state IN ('pending','failed','expired') AND received_amount IS NULL "
            "AND applied_principal_amount = 0 AND unapplied_amount = 0 "
            "AND applied_card_fee_amount = 0 AND applied_card_fee_tax_amount = 0 "
            "AND processor_fee_amount = 0) "
            "OR (state IN ('confirmed','refunded','reversed') "
            "AND received_amount IS NOT NULL AND received_amount > 0)",
            name="ck_invoice_payment_attempt_state_money",
        ),
        CheckConstraint(
            "received_amount IS NULL OR "
            "(source = 'backfill' AND state = 'refunded' "
            "AND received_amount = provider_charge_amount "
            "AND card_fee_amount = 0 AND card_fee_tax_amount = 0 "
            "AND applied_principal_amount = 0 AND unapplied_amount = 0 "
            "AND applied_card_fee_amount = 0 AND applied_card_fee_tax_amount = 0 "
            "AND processor_fee_amount = 0) OR "
            "(received_amount + (card_fee_amount - applied_card_fee_amount) "
            "+ (card_fee_tax_amount - applied_card_fee_tax_amount) "
            "= applied_principal_amount + unapplied_amount)",
            name="ck_invoice_payment_attempt_received_allocation",
        ),
        CheckConstraint("provider_charge_amount > 0", name="ck_invoice_payment_attempt_charge"),
        CheckConstraint("processor_fee_amount >= 0", name="ck_invoice_payment_attempt_processor_fee"),
        CheckConstraint("rail IN ('card','zelle','check','ach')", name="ck_invoice_payment_attempt_rail"),
        CheckConstraint(
            "provider IN ('stripe_connect','quickbooks_payments','manual')",
            name="ck_invoice_payment_attempt_provider",
        ),
        CheckConstraint(
            "state IN ('pending','confirmed','failed','expired','refunded','reversed')",
            name="ck_invoice_payment_attempt_state",
        ),
        CheckConstraint("version >= 1", name="ck_invoice_payment_attempt_version"),
        Index("ix_invoice_payment_attempt_invoice_created", "tenant_id", "invoice_id", "created_at", "id"),
        Index("ix_invoice_payment_attempt_pending", "tenant_id", "state", "expires_at"),
        Index("ix_invoice_payment_attempt_provider_identity", "provider", "provider_account_id", "provider_intent_id"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    settlement_id = Column(UUID(as_uuid=True), ForeignKey("invoice_settlements.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True, unique=True)
    source = Column(String(40), nullable=False)
    rail = Column(String(16), nullable=False)
    provider = Column(String(32), nullable=False)
    state = Column(String(20), nullable=False, default="pending", index=True)
    principal_amount = Column(MONEY, nullable=False)
    card_fee_amount = Column(MONEY, nullable=False, default=0)
    card_fee_tax_amount = Column(MONEY, nullable=False, default=0)
    # Creation-time surcharge snapshots above are immutable money evidence.
    # These additive projections record only the portion ultimately earned by
    # principal actually applied after a late provider success.
    applied_card_fee_amount = Column(MONEY, nullable=False, default=0)
    applied_card_fee_tax_amount = Column(MONEY, nullable=False, default=0)
    provider_charge_amount = Column(MONEY, nullable=False)
    received_amount = Column(MONEY, nullable=True)
    applied_principal_amount = Column(MONEY, nullable=False, default=0)
    unapplied_amount = Column(MONEY, nullable=False, default=0)
    processor_fee_amount = Column(MONEY, nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="USD")
    provider_configuration_version = Column(Integer, nullable=False)
    provider_account_id = Column(String(255), nullable=True)
    provider_intent_id = Column(String(255), nullable=True)
    provider_charge_id = Column(String(255), nullable=True)
    provider_event_id = Column(String(255), nullable=True)
    provider_reference = Column(String(255), nullable=True)
    manual_reference_fingerprint = Column(String(64), nullable=True)
    manual_evidence = Column(JSON, nullable=False, default=dict)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_name_snapshot = Column(String(255), nullable=False)
    actor_role_snapshot = Column(String(64), nullable=True)
    subject_type = Column(String(32), nullable=False)
    subject_id = Column(UUID(as_uuid=True), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_code = Column(String(100), nullable=True)


class InvoicePaymentLedgerEvent(Base):
    __tablename__ = "invoice_payment_ledger_events"
    __table_args__ = (
        UniqueConstraint("settlement_id", "sequence", name="uq_invoice_payment_ledger_sequence"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_invoice_payment_ledger_idempotency"),
        Index(
            "ix_invoice_payment_ledger_invoice",
            "tenant_id", "invoice_id", text("occurred_at DESC"), text("id DESC"),
        ),
        Index("ix_invoice_payment_ledger_attempt", "tenant_id", "attempt_id", "occurred_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False)
    settlement_id = Column(UUID(as_uuid=True), ForeignKey("invoice_settlements.id"), nullable=False)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("invoice_payment_attempts.id"), nullable=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_name_snapshot = Column(String(255), nullable=False)
    actor_role_snapshot = Column(String(64), nullable=True)
    sequence = Column(Integer, nullable=False)
    correlation_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    idempotency_key = Column(String(255), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    event_type = Column(String(64), nullable=False)
    prior_state = Column(String(32), nullable=True)
    new_state = Column(String(32), nullable=True)
    principal_delta = Column(MONEY, nullable=False, default=0)
    pending_delta = Column(MONEY, nullable=False, default=0)
    unapplied_delta = Column(MONEY, nullable=False, default=0)
    refund_pending_delta = Column(MONEY, nullable=False, default=0)
    money_snapshot = Column(JSON, nullable=False, default=dict)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)


class PaymentOverpayment(BaseModel):
    __tablename__ = "payment_overpayments"
    __table_args__ = (
        UniqueConstraint("source_attempt_id", name="uq_payment_overpayment_attempt"),
        CheckConstraint("amount > 0", name="ck_payment_overpayment_amount"),
        Index("ix_payment_overpayment_tenant_state", "tenant_id", "state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    settlement_id = Column(UUID(as_uuid=True), ForeignKey("invoice_settlements.id"), nullable=False)
    source_attempt_id = Column(UUID(as_uuid=True), ForeignKey("invoice_payment_attempts.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    amount = Column(MONEY, nullable=False)
    state = Column(String(40), nullable=False, default="refund_required")
    consent_channel = Column(String(32), nullable=True)
    consent_note = Column(Text, nullable=True)
    consent_actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    consented_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class CustomerCreditEntry(Base):
    __tablename__ = "customer_credit_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_customer_credit_entry_idempotency"),
        CheckConstraint("amount > 0", name="ck_customer_credit_entry_amount"),
        CheckConstraint("entry_type IN ('issued','applied','refunded','reversed')", name="ck_customer_credit_entry_type"),
        Index(
            "ix_customer_credit_entries_customer",
            "tenant_id", "customer_id", text("occurred_at DESC"), text("id DESC"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    entry_type = Column(String(20), nullable=False)
    amount = Column(MONEY, nullable=False)
    origin_overpayment_id = Column(UUID(as_uuid=True), ForeignKey("payment_overpayments.id"), nullable=True)
    target_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    source_entry_id = Column(UUID(as_uuid=True), ForeignKey("customer_credit_entries.id"), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_name_snapshot = Column(String(255), nullable=False)
    consent_channel = Column(String(32), nullable=True)
    consent_note = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CustomerCreditDueDiligenceEvent(Base):
    """Append-only evidence that a shop contacted a credit holder.

    This is deliberately separate from the credit ledger: due-diligence work
    cannot rewrite the issued amount, consent, age, or disposition of money.
    """

    __tablename__ = "customer_credit_due_diligence_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key",
            name="uq_customer_credit_due_diligence_idempotency",
        ),
        CheckConstraint(
            "channel IN ('email','phone','mail','in_person','other')",
            name="ck_customer_credit_due_diligence_channel",
        ),
        Index(
            "ix_customer_credit_due_diligence_credit",
            "tenant_id", "credit_id", text("occurred_at DESC"), text("id DESC"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    credit_id = Column(UUID(as_uuid=True), ForeignKey("customer_credit_entries.id"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    actor_name_snapshot = Column(String(255), nullable=False)
    channel = Column(String(24), nullable=False)
    note = Column(Text, nullable=False)
    next_review_at = Column(DateTime(timezone=True), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaymentRefund(BaseModel):
    __tablename__ = "payment_refunds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_payment_refund_idempotency"),
        CheckConstraint("amount > 0", name="ck_payment_refund_amount"),
        CheckConstraint("state IN ('pending','manual_action_required','succeeded','failed','cancelled')", name="ck_payment_refund_state"),
        Index("ix_payment_refunds_tenant_state", "tenant_id", "state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    source_attempt_id = Column(UUID(as_uuid=True), ForeignKey("invoice_payment_attempts.id"), nullable=False)
    overpayment_id = Column(UUID(as_uuid=True), ForeignKey("payment_overpayments.id"), nullable=True)
    amount = Column(MONEY, nullable=False)
    reason = Column(Text, nullable=False)
    destination_rail = Column(String(16), nullable=False)
    mode = Column(String(16), nullable=False)
    state = Column(String(32), nullable=False, default="pending")
    provider_reference = Column(String(255), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_name_snapshot = Column(String(255), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class PaymentProviderDispute(BaseModel):
    __tablename__ = "payment_provider_disputes"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_account_id", "provider_dispute_id",
            name="uq_payment_provider_dispute_identity",
        ),
        CheckConstraint("currency = 'USD'", name="ck_payment_provider_dispute_currency"),
        CheckConstraint("disputed_gross_amount > 0", name="ck_payment_provider_dispute_gross"),
        CheckConstraint("reversed_principal_amount >= 0", name="ck_payment_provider_dispute_principal"),
        CheckConstraint("reversed_card_fee_amount >= 0", name="ck_payment_provider_dispute_fee"),
        CheckConstraint("reversed_card_fee_tax_amount >= 0", name="ck_payment_provider_dispute_fee_tax"),
        CheckConstraint("reversed_unapplied_amount >= 0", name="ck_payment_provider_dispute_unapplied"),
        CheckConstraint("reversed_unapplied_principal_amount >= 0", name="ck_payment_provider_dispute_unapplied_principal"),
        CheckConstraint("reversed_unearned_surcharge_amount >= 0", name="ck_payment_provider_dispute_unearned_surcharge"),
        CheckConstraint("state IN ('open','won','lost')", name="ck_payment_provider_dispute_state"),
        Index("ix_payment_provider_dispute_attempt", "tenant_id", "attempt_id", "state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("invoice_payment_attempts.id"), nullable=False)
    provider = Column(String(32), nullable=False, default="stripe_connect")
    provider_account_id = Column(String(255), nullable=False)
    provider_dispute_id = Column(String(255), nullable=False)
    provider_charge_id = Column(String(255), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    disputed_gross_amount = Column(MONEY, nullable=False)
    reversed_principal_amount = Column(MONEY, nullable=False, default=0)
    reversed_card_fee_amount = Column(MONEY, nullable=False, default=0)
    reversed_card_fee_tax_amount = Column(MONEY, nullable=False, default=0)
    reversed_unapplied_amount = Column(MONEY, nullable=False, default=0)
    reversed_unapplied_principal_amount = Column(MONEY, nullable=False, default=0)
    reversed_unearned_surcharge_amount = Column(MONEY, nullable=False, default=0)
    state = Column(String(16), nullable=False, default="open")
    reason = Column(String(100), nullable=True)
    created_provider_event_id = Column(String(255), nullable=False)
    closed_provider_event_id = Column(String(255), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)


class PaymentAccountingLink(BaseModel):
    __tablename__ = "payment_accounting_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "financial_object_type", "financial_object_id", "operation_version", name="uq_payment_accounting_object_version"),
        Index("ix_payment_accounting_links_tenant_state", "tenant_id", "sync_state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("invoice_payment_attempts.id"), nullable=True)
    refund_id = Column(UUID(as_uuid=True), ForeignKey("payment_refunds.id"), nullable=True)
    financial_object_type = Column(String(40), nullable=False)
    financial_object_id = Column(UUID(as_uuid=True), nullable=False)
    operation_version = Column(Integer, nullable=False, default=1)
    principal_amount_snapshot = Column(MONEY, nullable=False, default=0)
    gross_amount_snapshot = Column(MONEY, nullable=False, default=0)
    owning_writer = Column(String(32), nullable=False)
    account_mapping_snapshot = Column(JSON, nullable=False, default=dict)
    qbo_realm_snapshot = Column(String(255), nullable=True)
    sync_state = Column(String(32), nullable=False, default="pending", index=True)
    provider_object_id = Column(String(255), nullable=True)
    provider_deposit_id = Column(String(255), nullable=True)
    provider_fee_journal_id = Column(String(255), nullable=True)
    sync_error = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), nullable=True)


class ProviderSettlementBatch(BaseModel):
    __tablename__ = "provider_settlement_batches"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", "provider_batch_id", name="uq_provider_settlement_batch"),
        CheckConstraint("currency = 'USD'", name="ck_provider_settlement_batch_currency"),
        Index("ix_provider_settlement_batch_tenant_state", "tenant_id", "reconciliation_state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    provider_account_id = Column(String(255), nullable=False)
    provider_batch_id = Column(String(255), nullable=False)
    # The accounting realm that owned this payout when Stripe emitted it.
    # Provider/account switches are prospective; historical payouts may never
    # be delivered into the tenant's newly connected QBO company.
    qbo_realm_snapshot = Column(String(255), nullable=True)
    currency = Column(String(3), nullable=False, default="USD")
    gross_receipts = Column(MONEY, nullable=False, default=0)
    customer_card_fees = Column(MONEY, nullable=False, default=0)
    card_fee_tax = Column(MONEY, nullable=False, default=0)
    refunds = Column(MONEY, nullable=False, default=0)
    disputes = Column(MONEY, nullable=False, default=0)
    processor_fees = Column(MONEY, nullable=False, default=0)
    net_payout = Column(MONEY, nullable=False, default=0)
    entry_manifest_hash = Column(String(64), nullable=False)
    reconciliation_state = Column(String(32), nullable=False, default="pending")
    qbo_deposit_id = Column(String(255), nullable=True)
    qbo_journal_id = Column(String(255), nullable=True)
    mismatch_reason = Column(Text, nullable=True)
    settled_at = Column(DateTime(timezone=True), nullable=True)


class ProviderSettlementEntry(Base):
    __tablename__ = "provider_settlement_entries"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id", "provider_entry_id", name="uq_provider_settlement_entry"),
        ForeignKeyConstraint(
            ["tenant_id", "provider_configuration_version"],
            [
                "tenant_payment_provider_configurations.tenant_id",
                "tenant_payment_provider_configurations.version",
            ],
            name="fk_provider_settlement_entry_configuration",
        ),
        Index("ix_provider_settlement_entry_batch", "tenant_id", "batch_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("provider_settlement_batches.id"), nullable=False)
    provider = Column(String(32), nullable=False)
    provider_account_id = Column(String(255), nullable=False)
    provider_entry_id = Column(String(255), nullable=False)
    entry_type = Column(String(32), nullable=False)
    amount = Column(MONEY, nullable=False)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("invoice_payment_attempts.id"), nullable=True)
    refund_id = Column(UUID(as_uuid=True), ForeignKey("payment_refunds.id"), nullable=True)
    dispute_id = Column(UUID(as_uuid=True), ForeignKey("payment_provider_disputes.id"), nullable=True)
    provider_configuration_version = Column(Integer, nullable=False)
    qbo_realm_snapshot = Column(String(255), nullable=False)
    owning_writer = Column(String(32), nullable=False)
    account_mapping_snapshot = Column(JSON, nullable=False)
    account_mapping_hash = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    safe_payload_hash = Column(String(64), nullable=False)


class InvoiceSettlementBackfillRun(BaseModel):
    __tablename__ = "invoice_settlement_backfill_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cutoff_at", name="uq_invoice_settlement_backfill_run"),
        CheckConstraint("state IN ('running','failed','reconciled','verified')", name="ck_invoice_settlement_backfill_state"),
    )

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    cutoff_at = Column(DateTime(timezone=True), nullable=False)
    state = Column(String(24), nullable=False, default="running")
    batch_cursor = Column(String(255), nullable=True)
    source_counts = Column(JSON, nullable=False, default=dict)
    inserted_counts = Column(JSON, nullable=False, default=dict)
    source_checksums = Column(JSON, nullable=False, default=dict)
    error_summary = Column(Text, nullable=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)


def _reject_orm_mutation(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__class__.__tablename__} is append-only")


def _reject_attempt_delete(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__class__.__tablename__} attempts cannot be deleted")


def _reject_attempt_soft_delete(_mapper, _connection, target) -> None:
    if inspect(target).attrs.deleted_at.history.has_changes():
        raise ValueError(f"{target.__class__.__tablename__} attempts cannot be deleted")


def _attribute_changed(target, name: str) -> bool:
    return inspect(target).attrs[name].history.has_changes()


def _guard_provider_configuration_update(_mapper, _connection, target) -> None:
    """Keep historical provider/accounting identity immutable.

    Readiness is an operational projection and may be refreshed. The only
    identity lifecycle change is an atomic active -> inactive transition with
    its first deactivation timestamp.
    """
    frozen = (
        "id", "tenant_id", "version", "selected_provider", "effective_at",
        "actor_user_id", "actor_name_snapshot", "provider_account_snapshot",
        "qbo_realm_snapshot", "writer_strategy", "idempotency_key",
        "request_hash", "stripe_clearing_account", "qbp_clearing_account",
        "check_deposit_account", "zelle_ach_account", "card_fee_income_account",
        "qbo_card_fee_item_id", "qbo_card_fee_tax_code_id",
        "processor_fee_expense_account", "sales_tax_liability_account",
        "checking_account", "created_at", "deleted_at",
    )
    if any(_attribute_changed(target, field) for field in frozen):
        raise ValueError("tenant_payment_provider_configurations frozen fields are immutable")
    state = inspect(target)
    active_history = state.attrs.is_active.history
    deactivated_history = state.attrs.deactivated_at.history
    if active_history.has_changes() or deactivated_history.has_changes():
        prior_active = active_history.deleted[0] if active_history.deleted else target.is_active
        prior_deactivated = (
            deactivated_history.deleted[0]
            if deactivated_history.deleted
            else target.deactivated_at
        )
        if not (
            prior_active is True
            and target.is_active is False
            and prior_deactivated is None
            and target.deactivated_at is not None
        ):
            raise ValueError(
                "tenant_payment_provider_configurations lifecycle transition is invalid"
            )


def _guard_invoice_settlement_realm_update(_mapper, connection, target) -> None:
    """Permit one config-backed realm bind, then freeze it permanently."""
    if _attribute_changed(target, "accounting_composition_version"):
        raise ValueError("invoice_settlements accounting composition is immutable")
    if not (
        _attribute_changed(target, "qbo_realm_snapshot")
        or _attribute_changed(target, "initial_provider_configuration_version")
    ):
        return

    settlement = InvoiceSettlement.__table__
    current = connection.execute(
        select(
            settlement.c.qbo_realm_snapshot,
            settlement.c.initial_provider_configuration_version,
        ).where(settlement.c.id == target.id)
    ).one_or_none()
    if current is None:
        return
    old_realm, old_version = current
    new_realm = target.qbo_realm_snapshot
    new_version = target.initial_provider_configuration_version
    if old_realm == new_realm and old_version == new_version:
        return

    config = TenantPaymentProviderConfiguration.__table__
    exact_config = connection.execute(
        select(config.c.id).where(
            config.c.tenant_id == target.tenant_id,
            config.c.version == new_version,
            config.c.qbo_realm_snapshot == new_realm,
            config.c.qbo_realm_snapshot.is_not(None),
            config.c.deleted_at.is_(None),
        ).limit(1)
    ).scalar_one_or_none()
    attempts = InvoicePaymentAttempt.__table__
    disqualifying_attempt = connection.execute(
        select(attempts.c.id).select_from(
            attempts.outerjoin(
                config,
                (config.c.tenant_id == attempts.c.tenant_id)
                & (config.c.version == attempts.c.provider_configuration_version),
            )
        ).where(
            attempts.c.settlement_id == target.id,
            (attempts.c.source != "backfill")
            | config.c.id.is_(None)
            | config.c.qbo_realm_snapshot.is_not(None),
        ).limit(1)
    ).scalar_one_or_none()
    links = PaymentAccountingLink.__table__
    prior_link = connection.execute(
        select(links.c.id).where(
            links.c.tenant_id == target.tenant_id,
            links.c.invoice_id == target.invoice_id,
        ).limit(1)
    ).scalar_one_or_none()
    if (
        old_realm is None
        and old_version is None
        and new_realm is not None
        and new_version is not None
        and exact_config is not None
        and disqualifying_attempt is None
        and prior_link is None
    ):
        return
    raise ValueError("invoice_settlements accounting realm binding is immutable")


def _guard_accounting_link_update(_mapper, _connection, target) -> None:
    frozen = (
        "id", "tenant_id", "invoice_id", "attempt_id", "refund_id",
        "financial_object_type", "financial_object_id", "operation_version",
        "principal_amount_snapshot", "gross_amount_snapshot", "owning_writer",
        "account_mapping_snapshot", "qbo_realm_snapshot", "created_at",
        "deleted_at",
    )
    if any(_attribute_changed(target, field) for field in frozen):
        raise ValueError("payment_accounting_links frozen fields are immutable")


def _reject_financial_projection_delete(_mapper, _connection, target) -> None:
    raise ValueError(f"{target.__class__.__tablename__} cannot be deleted")


event.listen(InvoicePaymentAttempt, "before_update", _reject_attempt_soft_delete)
event.listen(InvoicePaymentAttempt, "before_delete", _reject_attempt_delete)
event.listen(
    InvoiceSettlement,
    "before_update",
    _guard_invoice_settlement_realm_update,
)
event.listen(
    TenantPaymentProviderConfiguration,
    "before_update",
    _guard_provider_configuration_update,
)
event.listen(
    TenantPaymentProviderConfiguration,
    "before_delete",
    _reject_financial_projection_delete,
)
event.listen(PaymentAccountingLink, "before_update", _guard_accounting_link_update)
event.listen(
    PaymentAccountingLink,
    "before_delete",
    _reject_financial_projection_delete,
)


for _append_only_model in (
    InvoicePaymentLedgerEvent,
    CustomerCreditEntry,
    CustomerCreditDueDiligenceEvent,
    ProviderSettlementEntry,
):
    event.listen(_append_only_model, "before_update", _reject_orm_mutation)
    event.listen(_append_only_model, "before_delete", _reject_orm_mutation)
