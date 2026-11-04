"""Append-only booking liability applications and externally owned review work."""
from sqlalchemy import (Column, String, Integer, BigInteger, Text, Boolean, ForeignKey,
    ForeignKeyConstraint, UniqueConstraint, CheckConstraint, event, inspect)
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import BaseModel


class BookingReceiptApplication(BaseModel):
    __tablename__ = 'booking_receipt_applications'
    __table_args__ = (
        UniqueConstraint('tenant_id','id',name='uq_booking_application_tenant_id'),
        UniqueConstraint('tenant_id','idempotency_key',name='uq_booking_application_key'),
        ForeignKeyConstraint(['tenant_id','receipt_id'],['booking_receipts.tenant_id','booking_receipts.id']),
        ForeignKeyConstraint(['tenant_id','appointment_id'],['appointments.tenant_id','appointments.id']),
        ForeignKeyConstraint(['tenant_id','repair_order_id'],['repair_orders.tenant_id','repair_orders.id']),
        ForeignKeyConstraint(['tenant_id','invoice_id'],['invoices.tenant_id','invoices.id']),
        ForeignKeyConstraint(['tenant_id','customer_id'],['customers.tenant_id','customers.id']),
        ForeignKeyConstraint(['tenant_id','configuration_version'],['tenant_payment_provider_configurations.tenant_id','tenant_payment_provider_configurations.version']),
        CheckConstraint("amount_minor>0 AND currency='usd'",name='ck_booking_application_amount'),
        CheckConstraint('receipt_version_before>=1 AND booking_version_before>=1',name='ck_booking_application_versions'),
        CheckConstraint("environment IN ('sandbox','production') AND provider IN ('quickbooks_payments','stripe_connect')",name='ck_booking_application_provider'),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False,index=True)
    receipt_id=Column(UUID(as_uuid=True),nullable=False,index=True)
    appointment_id=Column(UUID(as_uuid=True),nullable=False)
    repair_order_id=Column(UUID(as_uuid=True),nullable=False)
    invoice_id=Column(UUID(as_uuid=True),nullable=False,index=True)
    settlement_id=Column(UUID(as_uuid=True),ForeignKey('invoice_settlements.id'),nullable=False)
    customer_id=Column(UUID(as_uuid=True),nullable=False)
    amount_minor=Column(BigInteger,nullable=False)
    currency=Column(String(3),nullable=False)
    receipt_version_before=Column(Integer,nullable=False)
    booking_version_before=Column(Integer,nullable=False)
    provider=Column(String(32),nullable=False)
    provider_account_id=Column(String(255),nullable=False)
    environment=Column(String(24),nullable=False)
    configuration_version=Column(Integer,nullable=False)
    qbo_realm_snapshot=Column(String(255),nullable=True)
    receipt_proof_sha256=Column(String(64),nullable=False)
    invoice_economics_sha256=Column(String(64),nullable=False)
    actor_user_id=Column(UUID(as_uuid=True),ForeignKey('users.id'),nullable=False)
    actor_name_snapshot=Column(String(255),nullable=False)
    idempotency_key=Column(String(200),nullable=False)
    request_sha256=Column(String(64),nullable=False)


class BookingAccountingReviewTask(BaseModel):
    __tablename__='booking_accounting_review_tasks'
    __table_args__=(
        UniqueConstraint('tenant_id','id',name='uq_booking_review_task_tenant_id'),
        UniqueConstraint('tenant_id','object_kind','financial_object_id','operation_version',name='uq_booking_review_object'),
        ForeignKeyConstraint(['tenant_id','receipt_id'],['booking_receipts.tenant_id','booking_receipts.id']),
        ForeignKeyConstraint(['tenant_id','application_id'],['booking_receipt_applications.tenant_id','booking_receipt_applications.id']),
        ForeignKeyConstraint(['tenant_id','invoice_id'],['invoices.tenant_id','invoices.id']),
        CheckConstraint("object_kind IN ('booking_receipt_liability','booking_receipt_application')",name='ck_booking_review_kind'),
        CheckConstraint("state IN ('awaiting_manual_ack','externally_reconciled','needs_review')",name='ck_booking_review_state'),
        CheckConstraint("amount_minor>0 AND currency='usd' AND owning_writer='external_manual'",name='ck_booking_review_money'),
        CheckConstraint('version>=1 AND operation_version>=1',name='ck_booking_review_version'),
        CheckConstraint("(object_kind='booking_receipt_liability' AND application_id IS NULL AND invoice_id IS NULL AND financial_object_id=receipt_id) OR (object_kind='booking_receipt_application' AND application_id IS NOT NULL AND invoice_id IS NOT NULL AND financial_object_id=application_id)",name='ck_booking_review_object_binding'),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False,index=True)
    receipt_id=Column(UUID(as_uuid=True),nullable=False,index=True)
    application_id=Column(UUID(as_uuid=True),nullable=True)
    invoice_id=Column(UUID(as_uuid=True),nullable=True,index=True)
    object_kind=Column(String(40),nullable=False)
    financial_object_id=Column(UUID(as_uuid=True),nullable=False)
    operation_version=Column(Integer,nullable=False,default=1)
    state=Column(String(32),nullable=False,default='awaiting_manual_ack')
    version=Column(Integer,nullable=False,default=1)
    provider=Column(String(32),nullable=False)
    provider_account_id=Column(String(255),nullable=False)
    environment=Column(String(24),nullable=False)
    configuration_version=Column(Integer,nullable=False)
    qbo_realm_snapshot=Column(String(255),nullable=True)
    amount_minor=Column(BigInteger,nullable=False)
    currency=Column(String(3),nullable=False)
    owning_writer=Column(String(24),nullable=False,default='external_manual')
    evidence_snapshot_sha256=Column(String(64),nullable=False)


class BookingAccountingReviewEvent(BaseModel):
    __tablename__='booking_accounting_review_events'
    __table_args__=(
        ForeignKeyConstraint(['tenant_id','task_id'],['booking_accounting_review_tasks.tenant_id','booking_accounting_review_tasks.id']),
        UniqueConstraint('tenant_id','idempotency_key',name='uq_booking_review_ack_key'),
        CheckConstraint("after_state IN ('externally_reconciled','needs_review')",name='ck_booking_review_ack_state'),
    )
    tenant_id=Column(UUID(as_uuid=True),ForeignKey('tenants.id'),nullable=False)
    task_id=Column(UUID(as_uuid=True),nullable=False)
    actor_user_id=Column(UUID(as_uuid=True),ForeignKey('users.id'),nullable=True)
    source_event_id=Column(UUID(as_uuid=True),ForeignKey('booking_payment_events.id'),nullable=True)
    actor_name_snapshot=Column(String(255),nullable=False)
    before_state=Column(String(32),nullable=False)
    after_state=Column(String(32),nullable=False)
    receipt_liability_recorded=Column(Boolean,nullable=False)
    application_to_ar_recorded=Column(Boolean,nullable=False)
    evidence_reference=Column(Text,nullable=False)
    external_company_reference=Column(String(255),nullable=False)
    review_note=Column(Text,nullable=False)
    idempotency_key=Column(String(200),nullable=False)
    request_sha256=Column(String(64),nullable=False)


def _immutable(mapper,connection,target):
    raise ValueError('Booking financial evidence is append-only')


def _task_update(mapper,connection,target):
    state=inspect(target)
    if any(state.attrs[field].history.has_changes() for field in
           state.mapper.column_attrs.keys() if field not in {'state','version','updated_at'}):
        raise ValueError('Booking accounting review provenance is immutable')

for _model in (BookingReceiptApplication,BookingAccountingReviewEvent):
    event.listen(_model,'before_update',_immutable)
    event.listen(_model,'before_delete',_immutable)
event.listen(BookingAccountingReviewTask,'before_update',_task_update)
event.listen(BookingAccountingReviewTask,'before_delete',_immutable)
