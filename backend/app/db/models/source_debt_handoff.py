"""One source receivable, its native collection copy, and receipt acknowledgements."""
from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import BaseModel
J = JSON().with_variant(JSONB, 'postgresql')

class SourceDebtHandoff(BaseModel):
    __tablename__ = 'source_debt_handoffs'
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id'), nullable=False)
    source_kind = Column(String(32), nullable=False, default='easy_truck_shop')
    ets_shop_id = Column(String(160), nullable=False)
    ets_service_internal_id = Column(String(160), nullable=False)
    ets_invoice_internal_id = Column(String(160), nullable=False)
    source_invoice_number = Column(String(80), nullable=False)
    source_service_number = Column(String(80), nullable=False)
    source_dbn_invoice_id = Column(UUID(as_uuid=True), nullable=False)
    source_repair_order_id = Column(UUID(as_uuid=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    native_invoice_id = Column(UUID(as_uuid=True), nullable=True, unique=True)
    source_capture_document = Column(J, nullable=False)
    source_capture_sha256 = Column(String(64), nullable=False)
    source_observed_at = Column(DateTime(timezone=True), nullable=False)
    original_issued_total = Column(Numeric(12,2), nullable=False)
    source_prior_allocated = Column(Numeric(12,2), nullable=False)
    opening_principal = Column(Numeric(12,2), nullable=False)
    currency = Column(String(3), nullable=False, default='USD')
    state = Column(String(32), nullable=False, default='prepared')
    source_revision = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    owner_acknowledged_at = Column(DateTime(timezone=True), nullable=False)
    owner_acknowledged_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    accounting_state = Column(String(48), nullable=False, default='external_reconciliation_pending')
    accounting_owner = Column(String(32), nullable=False, default='external_manual')
    idempotency_key = Column(String(255), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint('tenant_id','id',name='uq_source_handoff_tenant_id'),
        UniqueConstraint('tenant_id','ets_shop_id','ets_invoice_internal_id',name='uq_source_handoff_debt'),
        UniqueConstraint('tenant_id','idempotency_key',name='uq_source_handoff_idempotency'),
        ForeignKeyConstraint(['tenant_id','source_dbn_invoice_id'],['invoices.tenant_id','invoices.id'],name='fk_source_handoff_invoice',use_alter=True),
        ForeignKeyConstraint(['tenant_id','native_invoice_id'],['invoices.tenant_id','invoices.id'],name='fk_source_handoff_native',use_alter=True),
        ForeignKeyConstraint(['tenant_id','source_repair_order_id'],['repair_orders.tenant_id','repair_orders.id'],name='fk_source_handoff_order'),
        ForeignKeyConstraint(['tenant_id','customer_id'],['customers.tenant_id','customers.id'],name='fk_source_handoff_customer'),
        CheckConstraint("currency='USD' AND source_kind='easy_truck_shop'",name='ck_source_handoff_identity'),
        CheckConstraint("state IN ('prepared','active','source_conflict','closed') AND version>=1",name='ck_source_handoff_state'),
        CheckConstraint('opening_principal>0 AND source_prior_allocated>=0 AND original_issued_total=source_prior_allocated+opening_principal',name='ck_source_handoff_money'),
        CheckConstraint("accounting_owner='external_manual' AND accounting_state IN ('external_reconciliation_pending','verified_external')",name='ck_source_handoff_accounting'),
    )

class EtsReceiptUpdateTask(BaseModel):
    __tablename__ = 'ets_receipt_update_tasks'
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    handoff_id = Column(UUID(as_uuid=True), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), nullable=False)
    payment_id = Column(UUID(as_uuid=True), ForeignKey('payments.id'), nullable=False)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('invoice_payment_attempts.id'), nullable=True)
    principal_amount = Column(Numeric(12,2), nullable=False)
    received_amount = Column(Numeric(12,2), nullable=False)
    fee_amount = Column(Numeric(12,2), nullable=False, default=0)
    unapplied_amount = Column(Numeric(12,2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default='USD')
    effective_at = Column(DateTime(timezone=True), nullable=False)
    expected_source_revision = Column(String(64), nullable=False)
    state = Column(String(32), nullable=False, default='pending_manual')
    version = Column(Integer, nullable=False, default=1)
    claimed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    claim_expires_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint('tenant_id','id',name='uq_ets_task_tenant_id'),
        UniqueConstraint('tenant_id','payment_id',name='uq_ets_task_payment'),
        ForeignKeyConstraint(['tenant_id','handoff_id'],['source_debt_handoffs.tenant_id','source_debt_handoffs.id'],name='fk_ets_task_handoff'),
        ForeignKeyConstraint(['tenant_id','invoice_id'],['invoices.tenant_id','invoices.id'],name='fk_ets_task_invoice'),
        CheckConstraint("state IN ('pending_manual','claimed','awaiting_verification','verified','conflict') AND version>=1",name='ck_ets_task_state'),
        CheckConstraint("currency='USD' AND principal_amount>0 AND received_amount>=principal_amount AND fee_amount>=0 AND unapplied_amount>=0",name='ck_ets_task_money'),
    )

class SourceReceiptLink(BaseModel):
    __tablename__ = 'source_receipt_links'
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    handoff_id = Column(UUID(as_uuid=True), nullable=False)
    ets_shop_id = Column(String(160), nullable=False)
    ets_invoice_internal_id = Column(String(160), nullable=False)
    source_allocation_id = Column(String(160), nullable=False)
    source_payment_id = Column(String(160), nullable=False)
    source_revision = Column(String(64), nullable=False)
    source_capture_sha256 = Column(String(64), nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    amount = Column(Numeric(12,2), nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=False)
    origin = Column(String(24), nullable=False)
    native_payment_id = Column(UUID(as_uuid=True), ForeignKey('payments.id'), nullable=True)
    task_id = Column(UUID(as_uuid=True), nullable=True)
    reverses_id = Column(UUID(as_uuid=True), ForeignKey('source_receipt_links.id'), nullable=True)
    __table_args__ = (
        UniqueConstraint('tenant_id','ets_shop_id','ets_invoice_internal_id','source_allocation_id',name='uq_source_receipt_allocation'),
        ForeignKeyConstraint(['tenant_id','handoff_id'],['source_debt_handoffs.tenant_id','source_debt_handoffs.id'],name='fk_source_receipt_handoff'),
        ForeignKeyConstraint(['tenant_id','task_id'],['ets_receipt_update_tasks.tenant_id','ets_receipt_update_tasks.id'],name='fk_source_receipt_task'),
        CheckConstraint("amount>0 AND origin IN ('dbn_ack','ets_external')",name='ck_source_receipt_amount'),
    )

class SourceDebtEvent(BaseModel):
    __tablename__ = 'source_debt_events'
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    handoff_id = Column(UUID(as_uuid=True), nullable=False)
    task_id = Column(UUID(as_uuid=True), nullable=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    event_type = Column(String(48), nullable=False)
    request_key = Column(String(255), nullable=False)
    request_sha256 = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    evidence = Column(J, nullable=False, default=dict)
    __table_args__ = (
        UniqueConstraint('tenant_id','request_key',name='uq_source_debt_event_request'),
        ForeignKeyConstraint(['tenant_id','handoff_id'],['source_debt_handoffs.tenant_id','source_debt_handoffs.id'],name='fk_source_debt_event_handoff'),
        ForeignKeyConstraint(['tenant_id','task_id'],['ets_receipt_update_tasks.tenant_id','ets_receipt_update_tasks.id'],name='fk_source_debt_event_task'),
        CheckConstraint('version>=1',name='ck_source_debt_event_version'),
    )
